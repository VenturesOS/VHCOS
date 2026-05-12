"""
Leaderboard KPI computation — Feb 2026.

Mirrors the WhatsApp daily-digest KPI engine but aggregates over an
arbitrary date range (today / week / month / quarter / year / all)
instead of a single IST day.

Returns one record per user_id with:
- activity_score        (Σ pipeline_points + 0.5 × captures + 1.0 × cv_uploads)
- pipeline_points       (weighted sum of stage transitions)
- captures              (extension captures count)
- cv_uploads            (CV / batch upload count)
- capture_quality       (avg fill-rate %, recapture-penalised)
- mandate_efficiency    (% submissions ÷ captures across touched mandates)
- composite_score       (0.6 × activity_score_norm
                        + 0.2 × capture_quality
                        + 0.2 × mandate_efficiency)

The composite normalises activity_score by dividing by the global max
across the queried population so all three components live on the
same 0-100 scale, then the weighted sum produces the final ranking.

Single bulk-Mongo sweep — no per-user query loop, safe for 100+ users.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from services.team_digest_service import (
    PIPELINE_POINTS,
    EXTENSION_CAPTURE_SOURCES,
    CV_UPLOAD_SOURCES,
    _capture_quality_for_doc,
)

CANDIDATE_BANK_PROJECTION = {
    "_id": 0,
    "source": 1, "source_details": 1,
    "created_by": 1, "captured_by": 1,
    "created_at": 1, "captured_at": 1, "updated_at": 1,
    "mandate_id": 1,
    "phone": 1, "email": 1,
    "current_company": 1, "current_designation": 1,
    "notice_period": 1, "current_ctc": 1, "expected_ctc": 1,
}


def _empty() -> Dict:
    return {
        "pipeline_points": 0.0,
        "captures": 0,
        "cv_uploads": 0,
        "candidates_added": 0,
        "_qualities": [],
        "_mandate_captures": defaultdict(int),
        "_mandate_subs": defaultdict(int),
    }


async def compute_leaderboard_kpis(
    db,
    user_ids: List[str],
    start_iso: str,
    end_iso: Optional[str] = None,
) -> Dict[str, Dict]:
    """Aggregate digest-style KPIs across a date range for the given users.

    start_iso / end_iso are UTC ISO strings; pass `end_iso=None` for "now".
    Returns {user_id: kpi_dict}; missing users get an empty record.
    """
    uid_set = set(user_ids)
    matrix: Dict[str, Dict] = {uid: _empty() for uid in user_ids}

    time_window: Dict = {"$gte": start_iso}
    if end_iso:
        time_window["$lte"] = end_iso

    # 1) Pipeline events — tracker_events
    cursor = db.tracker_events.find(
        {"user_id": {"$in": user_ids}, "timestamp": time_window},
        {"_id": 0, "user_id": 1, "new_stage": 1, "mandate_id": 1},
    )
    async for ev in cursor:
        uid = ev.get("user_id")
        if uid not in uid_set:
            continue
        cell = matrix[uid]
        stage = ev.get("new_stage")
        if stage in PIPELINE_POINTS:
            cell["pipeline_points"] += PIPELINE_POINTS[stage]
        if stage == "submitted_to_client" and ev.get("mandate_id"):
            cell["_mandate_subs"][ev["mandate_id"]] += 1

    # 2) Candidate bank — captures + CV uploads + quality + mandate denominators
    cursor = db.candidate_bank.find(
        {
            "$or": [
                {"created_by": {"$in": user_ids}},
                {"captured_by": {"$in": user_ids}},
                {"source_details.captured_by": {"$in": user_ids}},
            ],
            "created_at": time_window,
        },
        CANDIDATE_BANK_PROJECTION,
    )
    async for doc in cursor:
        sd = doc.get("source_details") or {}
        uid = sd.get("captured_by") or doc.get("captured_by") or doc.get("created_by")
        if uid not in uid_set:
            continue
        cell = matrix[uid]
        cell["candidates_added"] += 1
        source = (doc.get("source") or "").lower()
        if source in EXTENSION_CAPTURE_SOURCES:
            cell["captures"] += 1
            cell["_qualities"].append(_capture_quality_for_doc(doc))
            mid = sd.get("mandate_id") or doc.get("mandate_id")
            if mid:
                cell["_mandate_captures"][mid] += 1
        elif source in CV_UPLOAD_SOURCES:
            cell["cv_uploads"] += 1

    # 3) Finalise per-user derived metrics
    for uid, cell in matrix.items():
        qs = cell.pop("_qualities")
        cell["capture_quality"] = round(sum(qs) / len(qs), 1) if qs else 0.0

        m_caps = cell.pop("_mandate_captures")
        m_subs = cell.pop("_mandate_subs")
        ratios: List[float] = []
        for mid in set(m_caps) | set(m_subs):
            c = m_caps.get(mid, 0)
            s = m_subs.get(mid, 0)
            if c == 0 and s == 0:
                continue
            if c == 0 and s > 0:
                ratios.append(100.0)
            else:
                ratios.append(min(100.0, (s / c) * 100))
        cell["mandate_efficiency"] = round(sum(ratios) / len(ratios), 1) if ratios else 0.0

        cell["activity_score"] = round(
            cell["pipeline_points"] + 0.5 * cell["captures"] + 1.0 * cell["cv_uploads"], 1
        )

    # 4) Composite score — normalise activity to 0-100 against the global max
    max_act = max((c["activity_score"] for c in matrix.values()), default=0.0) or 1.0
    for cell in matrix.values():
        norm_act = (cell["activity_score"] / max_act) * 100 if max_act else 0
        cell["composite_score"] = round(
            0.6 * norm_act + 0.2 * cell["capture_quality"] + 0.2 * cell["mandate_efficiency"], 2
        )

    return matrix


# ─────────────────────────────────────────────────────────────────────
# Period helpers — accepts today/week/month/quarter/year/all
# ─────────────────────────────────────────────────────────────────────
PERIOD_OFFSETS_DAYS = {
    "today": 0,
    "week": 7,
    "month": 30,
    "quarter": 90,
    "year": 365,
    "all": None,
}


def parse_extended_date_range(
    period: str,
    start_date: Optional[str],
    end_date: Optional[str],
) -> Tuple[str, str, str]:
    """Returns (start_iso, end_iso, period_label).

    Supports today/week/month/quarter/year/all/custom. For 'all' the
    start sentinel is 1970-01-01 so we still respect Mongo's index
    behaviour but match every document.
    """
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    if period == "custom" and start_date and end_date:
        s = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        return s.isoformat(), e.isoformat(), "Custom Range"

    if period == "all":
        s = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return s.isoformat(), now.isoformat(), "All Time"

    days = PERIOD_OFFSETS_DAYS.get(period, 30)
    if days == 0:
        s = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        s = now - timedelta(days=days)
    label = {
        "today": "Today",
        "week": "Last 7 Days",
        "month": "Last 30 Days",
        "quarter": "Last 90 Days",
        "year": "Last 365 Days",
    }.get(period, "Last 30 Days")
    return s.isoformat(), now.isoformat(), label
