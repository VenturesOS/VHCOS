"""
Daily Team Performance Digest — Phase 54.15

Generates a WhatsApp-ready text digest of recruiter+employer performance
for any given IST date. Runs at 18:00 IST daily via APScheduler and
caches the result in `daily_team_digests`. Admin UI reads from the cache
so refreshing the page is instant.

Perf: a single regen sweeps the last 14 IST days for ALL recruiters in
3 bulk Mongo aggregations (tracker_events, candidate_bank-adds,
candidate_bank-captures) → builds a per-user-per-day metric matrix in
memory → derives all rankings/deltas from that. Avoids the N×M
per-user-per-day query explosion of the naïve approach.

KPI definitions (weights):
- Pipeline points: joined +10, hired +7, offered +5, interview +3,
  shortlisted +2, submitted_to_client +1, sourced +0.5, on_hold 0,
  rejected -1.
- Activity score = Σ pipeline_points + 0.5 × candidates_added
                                       + 1.0 × cv_uploads.
- Capture quality % = avg fill-rate of 6 required fields (contact OR,
  current_company, current_designation, notice_period, current_ctc,
  expected_ctc) on the day's captures, with 30 percentage-point penalty
  per capture edited >60 s after first save (proxy for "recapture").
- Mandate efficiency % = sum(submissions_to_client) / sum(captures)
  across mandates the recruiter touched today; capture==0 and
  submissions>0 → 100 %; everything 0 → not counted.

Ranking rules:
- Recruiters ranked individually by activity_score.
- Employers ranked by **average** activity_score of their team's
  recruiters (their team output IS their score).
- DoD comparison uses the recruiter's *last active* working day (skips
  days with 0 activity).
- WoW = mean of last-7-days vs mean of 7-14 days ago.
- Inactive = activity_score==0 AND captures_count==0 AND no pipeline
  events for the day; surfaced for both recruiters AND employers.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

IST_OFFSET = timedelta(hours=5, minutes=30)

# ─────────────────────────────────────────────────────────────────────
# Constants — KPI weights
# ─────────────────────────────────────────────────────────────────────
PIPELINE_POINTS: Dict[str, float] = {
    "joined": 10,
    "hired": 7,
    "offered": 5,
    "interview": 3,
    "shortlisted": 2,
    "submitted_to_client": 1,
    "sourced": 0.5,
    "on_hold": 0,
    "rejected": -1,
}

LOW_ACTIVITY_THRESHOLD = 5.0
RECAPTURE_PENALTY_PCT = 30
RECAPTURE_GRACE_SECS = 60

# Lifetime Mandate Efficiency thresholds
MIN_MANDATES_FOR_RANKING = 10   # < 10 mandates → "Building track record" bucket
MIN_CAPTURES_PER_MANDATE = 5    # mandates with <5 captures excluded as noise
LIFETIME_TOP_N = 5              # top-N shown in the WhatsApp digest

# Real `source` values in candidate_bank (verified via /_audit/today endpoint)
EXTENSION_CAPTURE_SOURCES = {"naukri_extension", "linkedin_extension"}
CV_UPLOAD_SOURCES = {"cv_upload", "batch_upload", "resume_upload", "bulk_upload"}

REQUIRED_CAPTURE_FIELDS = [
    "current_company",
    "current_designation",
    "notice_period",
    "current_ctc",
    "expected_ctc",
]


# ─────────────────────────────────────────────────────────────────────
# Time helpers
# ─────────────────────────────────────────────────────────────────────
def _ist_now() -> datetime:
    return datetime.now(timezone.utc) + IST_OFFSET


def _ist_day_bounds_utc(date_ist: datetime) -> Tuple[str, str]:
    start_ist = date_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    end_ist = date_ist.replace(hour=23, minute=59, second=59, microsecond=999999)
    start_utc = (start_ist - IST_OFFSET).replace(tzinfo=timezone.utc)
    end_utc = (end_ist - IST_OFFSET).replace(tzinfo=timezone.utc)
    return start_utc.isoformat(), end_utc.isoformat()


def _parse_iso(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    try:
        s = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _iso_to_ist_date_str(iso: str) -> Optional[str]:
    """Convert UTC ISO timestamp → IST calendar date string YYYY-MM-DD."""
    dt = _parse_iso(iso)
    if not dt:
        return None
    ist = dt.astimezone(timezone.utc) + IST_OFFSET
    return ist.strftime("%Y-%m-%d")


# ─────────────────────────────────────────────────────────────────────
# Quality scoring (per-doc)
# ─────────────────────────────────────────────────────────────────────
def _capture_quality_for_doc(doc: Dict[str, Any]) -> float:
    total_slots = len(REQUIRED_CAPTURE_FIELDS) + 1  # +1 for contact slot

    filled = 0
    if doc.get("phone") or doc.get("email"):
        filled += 1
    for fld in REQUIRED_CAPTURE_FIELDS:
        val = doc.get(fld)
        if isinstance(val, str):
            if val.strip():
                filled += 1
        elif val not in (None, "", 0):
            filled += 1

    pct = (filled / total_slots) * 100

    captured_at = _parse_iso(
        doc.get("captured_at")
        or (doc.get("source_details") or {}).get("captured_at")
        or doc.get("created_at")
    )
    updated_at = _parse_iso(doc.get("updated_at"))
    if (
        captured_at
        and updated_at
        and (updated_at - captured_at).total_seconds() > RECAPTURE_GRACE_SECS
    ):
        pct = max(0.0, pct - RECAPTURE_PENALTY_PCT)
    return round(pct, 1)


# ─────────────────────────────────────────────────────────────────────
# BULK aggregation — 14-day metric matrix per user
# ─────────────────────────────────────────────────────────────────────
async def _build_metric_matrix(
    db,
    recruiter_ids: List[str],
    end_date_ist: datetime,
    days: int = 14,
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Return {user_id: {YYYY-MM-DD: metrics}} for the last N IST days.
    Sweeps everything in 3 bulk Mongo queries — no per-user query loop.
    """
    end_day = end_date_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    start_day = end_day - timedelta(days=days - 1)
    window_start_utc, _ = _ist_day_bounds_utc(start_day)
    _, window_end_utc = _ist_day_bounds_utc(end_date_ist)

    # Initialize sparse matrix
    rec_set = set(recruiter_ids)
    matrix: Dict[str, Dict[str, Dict[str, Any]]] = {
        rid: {} for rid in recruiter_ids
    }

    def _empty_metric() -> Dict[str, Any]:
        return {
            "pipeline_points": 0.0,
            "stage_counts": defaultdict(int),
            "candidates_added": 0,
            "cv_uploads": 0,
            "captures_count": 0,
            "capture_qualities": [],
            "mandate_captures": defaultdict(int),
            "mandate_subs": defaultdict(int),
        }

    def _get_cell(uid: str, day: str) -> Optional[Dict[str, Any]]:
        if uid not in rec_set or not day:
            return None
        cell = matrix[uid].get(day)
        if cell is None:
            cell = _empty_metric()
            matrix[uid][day] = cell
        return cell

    # 1) Pipeline events (tracker_events)
    async for ev in db.tracker_events.find(
        {
            "user_id": {"$in": recruiter_ids},
            "timestamp": {"$gte": window_start_utc, "$lte": window_end_utc},
        },
        {"_id": 0, "user_id": 1, "timestamp": 1, "new_stage": 1, "mandate_id": 1},
    ):
        day = _iso_to_ist_date_str(ev.get("timestamp"))
        cell = _get_cell(ev.get("user_id"), day)
        if not cell:
            continue
        stage = ev.get("new_stage")
        if stage in PIPELINE_POINTS:
            cell["pipeline_points"] += PIPELINE_POINTS[stage]
            cell["stage_counts"][stage] += 1
        if stage == "submitted_to_client" and ev.get("mandate_id"):
            cell["mandate_subs"][ev["mandate_id"]] += 1

    # 2) Candidates added (candidate_bank rows)
    async for doc in db.candidate_bank.find(
        {
            "$or": [
                {"created_by": {"$in": recruiter_ids}},
                {"captured_by": {"$in": recruiter_ids}},
                {"source_details.captured_by": {"$in": recruiter_ids}},
            ],
            "created_at": {"$gte": window_start_utc, "$lte": window_end_utc},
        },
        {
            "_id": 0,
            "source": 1, "source_details": 1,
            "created_by": 1, "captured_by": 1,
            "created_at": 1, "captured_at": 1, "updated_at": 1,
            "mandate_id": 1,
            "phone": 1, "email": 1,
            "current_company": 1, "current_designation": 1,
            "notice_period": 1, "current_ctc": 1, "expected_ctc": 1,
        },
    ):
        day = _iso_to_ist_date_str(doc.get("created_at"))
        sd = doc.get("source_details") or {}
        uid = (
            sd.get("captured_by")
            or doc.get("captured_by")
            or doc.get("created_by")
        )
        cell = _get_cell(uid, day)
        if not cell:
            continue
        cell["candidates_added"] += 1
        source = (doc.get("source") or "").lower()
        if source in EXTENSION_CAPTURE_SOURCES:
            cell["captures_count"] += 1
            cell["capture_qualities"].append(_capture_quality_for_doc(doc))
            mid = sd.get("mandate_id") or doc.get("mandate_id")
            if mid:
                cell["mandate_captures"][mid] += 1
        elif source in CV_UPLOAD_SOURCES:
            cell["cv_uploads"] += 1

    # Finalize aggregates per cell
    for uid, days_map in matrix.items():
        for day, cell in days_map.items():
            # Capture quality avg
            qs = cell["capture_qualities"]
            cell["capture_quality"] = round(sum(qs) / len(qs), 1) if qs else 0.0
            # Mandate efficiency
            ratios = []
            mids = set(cell["mandate_captures"].keys()) | set(cell["mandate_subs"].keys())
            for mid in mids:
                c = cell["mandate_captures"].get(mid, 0)
                s = cell["mandate_subs"].get(mid, 0)
                if c == 0 and s == 0:
                    continue
                if c == 0 and s > 0:
                    ratios.append(100.0)
                else:
                    ratios.append(min(100.0, (s / c) * 100))
            cell["mandate_efficiency"] = (
                round(sum(ratios) / len(ratios), 1) if ratios else -1.0
            )
            # Activity score
            cell["activity_score"] = round(
                cell["pipeline_points"]
                + 0.5 * cell["candidates_added"]
                + 1.0 * cell["cv_uploads"],
                1,
            )
            # Convert defaultdicts to dicts for JSON serialization
            cell["stage_counts"] = dict(cell["stage_counts"])
            cell["pipeline_points"] = round(cell["pipeline_points"], 1)
            del cell["capture_qualities"]
            del cell["mandate_captures"]
            del cell["mandate_subs"]
    return matrix


def _empty_day_metric() -> Dict[str, Any]:
    return {
        "pipeline_points": 0.0,
        "stage_counts": {},
        "candidates_added": 0,
        "cv_uploads": 0,
        "captures_count": 0,
        "capture_quality": 0.0,
        "mandate_efficiency": -1.0,
        "activity_score": 0.0,
    }


# ─────────────────────────────────────────────────────────────────────
# LIFETIME Mandate Efficiency (separate from daily KPIs)
# ─────────────────────────────────────────────────────────────────────
async def _compute_lifetime_mandate_efficiency(
    db, recruiter_ids: List[str]
) -> Dict[str, Dict[str, Any]]:
    """For each recruiter, compute lifetime mandate efficiency.

    Rules (locked-in with user 2026-05-11):
    - "Worked on mandate" = captured ≥ 1 candidate against it via extension.
    - Window = lifetime (no time bound, ends only when user is deleted).
    - Submission cap = 1 per candidate (resubmits don't double-count).
    - Min mandates worked on = 10 to be ranked; else "building track record".
    - Min captures per mandate = 5 (drops noisy one-shot mandates).
    - Avg method = capture-weighted overall =
            total_submissions_capped / total_qualifying_captures × 100
            (capped at 100 % to absorb edge cases).

    Returns:
        {user_id: {
            "total_captures": int,
            "total_submissions": int,
            "mandates_worked": int,
            "qualifying_mandates": int,
            "efficiency_pct": float,
            "eligible": bool,
        }}
    """
    rec_set = set(recruiter_ids)

    # 1) Per-mandate captures per recruiter
    captures_by_mandate: Dict[str, Dict[str, int]] = {rid: {} for rid in recruiter_ids}
    cap_pipeline = [
        {"$match": {"source": {"$in": list(EXTENSION_CAPTURE_SOURCES)}}},
        {"$addFields": {
            "_uid": {"$ifNull": [
                "$source_details.captured_by",
                {"$ifNull": ["$captured_by", "$created_by"]},
            ]},
            "_mid": {"$ifNull": [
                "$mandate_id",
                "$source_details.mandate_id",
            ]},
        }},
        {"$match": {"_uid": {"$ne": None}, "_mid": {"$ne": None}}},
        {"$group": {
            "_id": {"uid": "$_uid", "mid": "$_mid"},
            "captures": {"$sum": 1},
        }},
    ]
    async for r in db.candidate_bank.aggregate(cap_pipeline, allowDiskUse=True):
        uid = r["_id"]["uid"]
        if uid not in rec_set:
            continue
        captures_by_mandate[uid][r["_id"]["mid"]] = r["captures"]

    # 2) Distinct submissions per (recruiter, mandate, candidate) — cap = 1
    subs_by_mandate: Dict[str, Dict[str, int]] = {rid: {} for rid in recruiter_ids}
    sub_pipeline = [
        {"$match": {
            "new_stage": "submitted_to_client",
            "user_id": {"$in": recruiter_ids},
        }},
        # Dedupe per (user, mandate, candidate) — submission cap = 1
        {"$group": {
            "_id": {
                "uid": "$user_id",
                "mid": "$mandate_id",
                "cand": "$candidate_id",
            },
        }},
        # Roll up to (user, mandate) → count distinct candidates submitted
        {"$group": {
            "_id": {"uid": "$_id.uid", "mid": "$_id.mid"},
            "submissions": {"$sum": 1},
        }},
    ]
    async for r in db.tracker_events.aggregate(sub_pipeline, allowDiskUse=True):
        uid = r["_id"]["uid"]
        mid = r["_id"]["mid"]
        if uid not in rec_set or not mid:
            continue
        subs_by_mandate[uid][mid] = r["submissions"]

    # 3) Compute per-recruiter aggregates
    out: Dict[str, Dict[str, Any]] = {}
    for uid in recruiter_ids:
        caps = captures_by_mandate.get(uid, {})
        subs = subs_by_mandate.get(uid, {})
        mandates_worked = len(caps)

        # Qualifying mandates = ≥ MIN_CAPTURES_PER_MANDATE captures
        qual_mid = {m for m, c in caps.items() if c >= MIN_CAPTURES_PER_MANDATE}
        qual_captures = sum(c for m, c in caps.items() if m in qual_mid)
        # Cap subs at captures per mandate (subs can't outnumber captures by same recruiter)
        qual_subs = 0
        for m in qual_mid:
            qual_subs += min(subs.get(m, 0), caps.get(m, 0))

        eff = round((qual_subs / qual_captures * 100), 1) if qual_captures > 0 else 0.0
        eff = min(eff, 100.0)  # safety cap

        out[uid] = {
            "total_captures": sum(caps.values()),
            "total_submissions": sum(min(subs.get(m, 0), caps.get(m, 0)) for m in caps),
            "mandates_worked": mandates_worked,
            "qualifying_mandates": len(qual_mid),
            "qualifying_captures": qual_captures,
            "qualifying_submissions": qual_subs,
            "efficiency_pct": eff,
            "eligible": mandates_worked >= MIN_MANDATES_FOR_RANKING,
        }
    return out


# ─────────────────────────────────────────────────────────────────────
# Public API — build the full digest
# ─────────────────────────────────────────────────────────────────────
async def build_daily_digest(db, date_ist: Optional[datetime] = None) -> Dict[str, Any]:
    if date_ist is None:
        date_ist = _ist_now()
    today_str = date_ist.strftime("%Y-%m-%d")
    weekday = date_ist.strftime("%a")
    pretty = date_ist.strftime("%d %b %Y")

    # Fetch users + teams — STRICT active filter to exclude deactivated/disabled users.
    # The previous `status != "inactive"` left through `status="deactivated"`,
    # `status="disabled"`, and users with `is_active: false`. We now require both
    # an active-ish status AND is_active not explicitly false.
    ACTIVE_STATUSES = ["active", "Active", None]  # None = field missing → legacy active user
    _active_user_filter = {
        "status": {"$in": ACTIVE_STATUSES},
        "is_active": {"$ne": False},
    }
    recruiters = await db.users.find(
        {**_active_user_filter, "role": "recruiter"},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(length=500)
    employers = await db.users.find(
        {**_active_user_filter, "role": "employer"},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(length=200)
    teams = await db.teams.find(
        {"status": {"$in": ACTIVE_STATUSES}},
        {"_id": 0, "id": 1, "name": 1, "employer_id": 1, "recruiter_ids": 1},
    ).to_list(length=200)

    recruiter_ids = [r["id"] for r in recruiters]
    if not recruiter_ids:
        return _empty_digest_response(today_str, weekday, pretty)

    # Build the 14-day matrix in ONE pass (3 bulk queries inside)
    matrix = await _build_metric_matrix(db, recruiter_ids, date_ist, days=14)

    # Today's per-recruiter metrics
    team_by_recruiter: Dict[str, Dict[str, Any]] = {}
    for t in teams:
        for rid in t.get("recruiter_ids") or []:
            team_by_recruiter[rid] = t
    employer_by_id: Dict[str, Dict[str, Any]] = {e["id"]: e for e in employers}

    recruiter_metrics: List[Dict[str, Any]] = []
    for r in recruiters:
        today_cell = matrix.get(r["id"], {}).get(today_str) or _empty_day_metric()
        team = team_by_recruiter.get(r["id"])
        recruiter_metrics.append({
            "user_id": r["id"],
            "name": r.get("name") or "(unnamed)",
            "team_id": team["id"] if team else None,
            "team_name": team["name"] if team else "Unassigned",
            "employer_id": team["employer_id"] if team else None,
            **today_cell,
        })

    # DoD: last *active* working day for each user from matrix
    dod_deltas: List[Dict[str, Any]] = []
    for rm in recruiter_metrics:
        prev_day = None
        prev_score = None
        for offset in range(1, 8):
            probe = date_ist - timedelta(days=offset)
            probe_str = probe.strftime("%Y-%m-%d")
            cell = matrix.get(rm["user_id"], {}).get(probe_str)
            if cell and (cell["activity_score"] > 0 or cell["captures_count"] > 0):
                prev_day = probe
                prev_score = cell["activity_score"]
                break
        if prev_day is None:
            continue
        delta = rm["activity_score"] - prev_score
        dod_deltas.append({
            "user_id": rm["user_id"],
            "name": rm["name"],
            "today": rm["activity_score"],
            "previous": prev_score,
            "previous_date": prev_day.strftime("%a %d %b"),
            "delta": round(delta, 1),
        })

    # WoW: 7d-now avg vs 7-14d-prev avg from matrix
    wow_deltas: List[Dict[str, Any]] = []
    for rm in recruiter_metrics:
        scores_now = []
        scores_prev = []
        for offset in range(0, 7):
            d = (date_ist - timedelta(days=offset)).strftime("%Y-%m-%d")
            scores_now.append(
                (matrix.get(rm["user_id"], {}).get(d) or _empty_day_metric())["activity_score"]
            )
        for offset in range(7, 14):
            d = (date_ist - timedelta(days=offset)).strftime("%Y-%m-%d")
            scores_prev.append(
                (matrix.get(rm["user_id"], {}).get(d) or _empty_day_metric())["activity_score"]
            )
        now_avg = round(sum(scores_now) / 7, 1)
        prev_avg = round(sum(scores_prev) / 7, 1)
        if prev_avg == 0 and now_avg == 0:
            continue
        if prev_avg == 0:
            pct = 100.0
        else:
            pct = round(((now_avg - prev_avg) / prev_avg) * 100, 1)
        wow_deltas.append({
            "user_id": rm["user_id"],
            "name": rm["name"],
            "this_week_avg": now_avg,
            "last_week_avg": prev_avg,
            "pct_change": pct,
        })

    # Employer scores (avg of team)
    employer_scores: List[Dict[str, Any]] = []
    for emp in employers:
        team = next((t for t in teams if t["employer_id"] == emp["id"]), None)
        if not team:
            continue
        team_recs = [
            rm for rm in recruiter_metrics
            if rm["user_id"] in (team.get("recruiter_ids") or [])
        ]
        if not team_recs:
            continue
        avg_score = round(
            sum(r["activity_score"] for r in team_recs) / len(team_recs), 1
        )
        employer_scores.append({
            "user_id": emp["id"],
            "name": emp.get("name") or "(unnamed)",
            "team_name": team["name"],
            "team_size": len(team_recs),
            "activity_score": avg_score,
        })

    # Rankings
    top_overall = sorted(
        recruiter_metrics, key=lambda x: x["activity_score"], reverse=True
    )[:3]
    by_team: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for rm in recruiter_metrics:
        by_team[rm["team_name"]].append(rm)
    top_per_team = []
    for team_name, members in by_team.items():
        if team_name == "Unassigned":
            continue
        best = max(members, key=lambda x: x["activity_score"])
        team_obj = next((t for t in teams if t["name"] == team_name), None)
        leader = (
            employer_by_id.get(team_obj["employer_id"], {}).get("name")
            if team_obj else None
        )
        top_per_team.append({
            "team_name": team_name,
            "leader_name": leader or "(unassigned)",
            "top_recruiter": best["name"],
            "top_score": best["activity_score"],
        })
    top_per_team.sort(key=lambda x: x["top_score"], reverse=True)

    improving_dod = sorted(
        [d for d in dod_deltas if d["delta"] > 0],
        key=lambda x: x["delta"], reverse=True,
    )[:3]
    falling_dod = sorted(
        [d for d in dod_deltas if d["delta"] < 0],
        key=lambda x: x["delta"],
    )[:3]
    improving_wow = sorted(
        [w for w in wow_deltas if w["pct_change"] > 0],
        key=lambda x: x["pct_change"], reverse=True,
    )[:3]
    falling_wow = sorted(
        [w for w in wow_deltas if w["pct_change"] < 0],
        key=lambda x: x["pct_change"],
    )[:3]

    inactive_recruiters = [
        rm["name"]
        for rm in recruiter_metrics
        if rm["activity_score"] < LOW_ACTIVITY_THRESHOLD
        and rm["captures_count"] == 0
        and not rm["stage_counts"]
    ]
    inactive_employers = [
        e["name"]
        for e in employer_scores
        if e["activity_score"] < LOW_ACTIVITY_THRESHOLD
    ]

    captures_made = [rm for rm in recruiter_metrics if rm["captures_count"] > 0]
    best_quality = (
        max(captures_made, key=lambda x: x["capture_quality"])
        if captures_made else None
    )
    # Only highlight mandate efficiency if at least one submission happened —
    # else the "best" is just the alphabetically-first 0%, which is misleading.
    eff_made = [rm for rm in recruiter_metrics if rm["mandate_efficiency"] > 0]
    best_efficiency = (
        max(eff_made, key=lambda x: x["mandate_efficiency"])
        if eff_made else None
    )

    # Lifetime mandate efficiency (separate from today's daily metric)
    lifetime_eff_map = await _compute_lifetime_mandate_efficiency(db, recruiter_ids)
    uid_to_name_local = {rm["user_id"]: rm["name"] for rm in recruiter_metrics}
    lifetime_ranked = []
    building = []
    for uid, m in lifetime_eff_map.items():
        name = uid_to_name_local.get(uid)
        if not name:
            continue
        entry = {"user_id": uid, "name": name, **m}
        if m["eligible"]:
            lifetime_ranked.append(entry)
        elif m["mandates_worked"] > 0:
            building.append(entry)
    lifetime_ranked.sort(key=lambda x: x["efficiency_pct"], reverse=True)
    building.sort(key=lambda x: x["mandates_worked"], reverse=True)
    lifetime_top = lifetime_ranked[:LIFETIME_TOP_N]

    payload = {
        "date": today_str,
        "weekday": weekday,
        "pretty_date": pretty,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recruiter_count": len(recruiter_metrics),
        "employer_count": len(employer_scores),
        "top_overall": top_overall,
        "top_per_team": top_per_team,
        "improving_dod": improving_dod,
        "falling_dod": falling_dod,
        "improving_wow": improving_wow,
        "falling_wow": falling_wow,
        "inactive_recruiters": inactive_recruiters,
        "inactive_employers": inactive_employers,
        "best_quality": best_quality,
        "best_efficiency": best_efficiency,
        "lifetime_mandate_efficiency_top": lifetime_top,
        "lifetime_mandate_efficiency_building": building[:10],
        "employer_scores": sorted(
            employer_scores, key=lambda x: x["activity_score"], reverse=True
        ),
        "all_recruiter_metrics": sorted(
            recruiter_metrics, key=lambda x: x["activity_score"], reverse=True
        ),
    }
    payload["whatsapp_text"] = format_whatsapp_message(payload)
    return payload


def _empty_digest_response(date_str, weekday, pretty) -> Dict[str, Any]:
    base = {
        "date": date_str,
        "weekday": weekday,
        "pretty_date": pretty,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recruiter_count": 0,
        "employer_count": 0,
        "top_overall": [],
        "top_per_team": [],
        "improving_dod": [],
        "falling_dod": [],
        "improving_wow": [],
        "falling_wow": [],
        "inactive_recruiters": [],
        "inactive_employers": [],
        "best_quality": None,
        "best_efficiency": None,
        "lifetime_mandate_efficiency_top": [],
        "lifetime_mandate_efficiency_building": [],
        "employer_scores": [],
        "all_recruiter_metrics": [],
    }
    base["whatsapp_text"] = format_whatsapp_message(base)
    return base


# ─────────────────────────────────────────────────────────────────────
# WhatsApp message formatter
# ─────────────────────────────────────────────────────────────────────
def _fmt_score(v: float) -> str:
    if v == int(v):
        return str(int(v))
    return f"{v:.1f}"


def format_whatsapp_message(d: Dict[str, Any]) -> str:
    L: List[str] = []
    L.append(f"*Daily Performance — {d['pretty_date']} ({d['weekday']})*")
    L.append(f"_{d['recruiter_count']} recruiters · {d['employer_count']} team leads_")
    L.append("")

    L.append("*TOP 3 OVERALL*")
    if d["top_overall"]:
        for i, t in enumerate(d["top_overall"], 1):
            stage_brief = ""
            if t.get("stage_counts"):
                parts = []
                for stg in ("joined", "hired", "offered", "interview", "shortlisted", "submitted_to_client"):
                    if t["stage_counts"].get(stg):
                        parts.append(f"{t['stage_counts'][stg]} {stg.replace('_to_client', '')}")
                if parts:
                    stage_brief = " · " + ", ".join(parts[:3])
            L.append(
                f"{i}. {t['name']} — {_fmt_score(t['activity_score'])} pts "
                f"({t['captures_count']} captures{stage_brief})"
            )
    else:
        L.append("_no activity today_")
    L.append("")

    L.append("*TOP PER TEAM*")
    if d["top_per_team"]:
        for t in d["top_per_team"]:
            L.append(
                f"• {t['team_name']} (Lead: {t['leader_name']}) — "
                f"{t['top_recruiter']}: {_fmt_score(t['top_score'])} pts"
            )
    else:
        L.append("_no team activity_")
    L.append("")

    L.append("*IMPROVING (vs last active day)*")
    if d["improving_dod"]:
        for i, x in enumerate(d["improving_dod"], 1):
            L.append(f"{i}. {x['name']} +{_fmt_score(x['delta'])} pts (vs {x['previous_date']})")
    else:
        L.append("_no improvers_")
    L.append("")
    L.append("*FALLING (vs last active day)*")
    if d["falling_dod"]:
        for i, x in enumerate(d["falling_dod"], 1):
            L.append(f"{i}. {x['name']} {_fmt_score(x['delta'])} pts (vs {x['previous_date']})")
    else:
        L.append("_no decliners_")
    L.append("")

    L.append("*WEEK-OVER-WEEK*")
    if d["improving_wow"]:
        L.append("_Biggest gains:_")
        for i, x in enumerate(d["improving_wow"], 1):
            L.append(
                f"  {i}. {x['name']} +{_fmt_score(x['pct_change'])}% "
                f"({_fmt_score(x['this_week_avg'])} vs {_fmt_score(x['last_week_avg'])} pts/day)"
            )
    if d["falling_wow"]:
        L.append("_Biggest drops:_")
        for i, x in enumerate(d["falling_wow"], 1):
            L.append(
                f"  {i}. {x['name']} {_fmt_score(x['pct_change'])}% "
                f"({_fmt_score(x['this_week_avg'])} vs {_fmt_score(x['last_week_avg'])} pts/day)"
            )
    if not d["improving_wow"] and not d["falling_wow"]:
        L.append("_steady — no major shifts_")
    L.append("")

    if d["inactive_recruiters"]:
        L.append(f"*INACTIVE TODAY ({len(d['inactive_recruiters'])} recruiters)*")
        L.append("• " + ", ".join(d["inactive_recruiters"][:15]))
        L.append("")

    # Positive team-output framing — ranked highest → lowest by team avg score.
    # Replaces the older "Low Team Output" block which highlighted laggards.
    if d.get("employer_scores"):
        L.append("*TEAM RANKING*")
        medals = ["🥇", "🥈", "🥉"]
        for i, e in enumerate(d["employer_scores"]):
            prefix = medals[i] if i < 3 else f"  {i + 1}."
            L.append(
                f"{prefix} {e['team_name']} (Lead: {e['name']}) — "
                f"{_fmt_score(e['activity_score'])} pts/recruiter · {e['team_size']} on team"
            )
        L.append("")

    quality_lines = []
    if d.get("best_quality"):
        bq = d["best_quality"]
        quality_lines.append(
            f"📋 Best capture quality: {bq['name']} ({_fmt_score(bq['capture_quality'])}% over {bq['captures_count']} captures)"
        )
    if d.get("best_efficiency"):
        be = d["best_efficiency"]
        quality_lines.append(
            f"🎯 Best mandate efficiency: {be['name']} ({_fmt_score(be['mandate_efficiency'])}% submit rate)"
        )
    if quality_lines:
        L.append("*QUALITY HIGHLIGHTS*")
        L.extend(quality_lines)
        L.append("")

    # Lifetime mandate efficiency (capture → submission ratio) — top 5
    lifetime_top = d.get("lifetime_mandate_efficiency_top") or []
    building = d.get("lifetime_mandate_efficiency_building") or []
    if lifetime_top or building:
        L.append(f"*MANDATE EFFICIENCY — LIFETIME (top {LIFETIME_TOP_N}, min {MIN_MANDATES_FOR_RANKING} mandates)*")
        medals = ["🥇", "🥈", "🥉", "4.", "5."]
        for i, e in enumerate(lifetime_top):
            prefix = medals[i] if i < len(medals) else f"{i + 1}."
            L.append(
                f"{prefix} {e['name']} — {_fmt_score(e['efficiency_pct'])}% "
                f"({e['qualifying_submissions']} submits / {e['qualifying_captures']} captures · "
                f"{e['qualifying_mandates']} qualifying mandates of {e['mandates_worked']} worked)"
            )
        if building:
            names = [
                f"{b['name']} ({b['mandates_worked']})"
                for b in building[:6]
            ]
            extra = f" +{len(building) - 6} more" if len(building) > 6 else ""
            L.append(f"_Building track record:_ {', '.join(names)}{extra}")
        L.append("")

    L.append("_Generated by VHC Talent OS._")
    return "\n".join(L)


# ─────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────
DIGEST_COLLECTION = "daily_team_digests"


async def store_digest(db, digest: Dict[str, Any]) -> None:
    await db[DIGEST_COLLECTION].update_one(
        {"date": digest["date"]},
        {"$set": digest},
        upsert=True,
    )
    logger.info(f"[TeamDigest] Stored digest for {digest['date']}")


async def get_stored_digest(db, date_str: str) -> Optional[Dict[str, Any]]:
    return await db[DIGEST_COLLECTION].find_one({"date": date_str}, {"_id": 0})


# ─────────────────────────────────────────────────────────────────────
# Scheduler entry
# ─────────────────────────────────────────────────────────────────────
async def run_daily_digest(db) -> None:
    try:
        ist_now = _ist_now()
        logger.warning(f"[TeamDigest] Building digest for {ist_now.date()}…")
        digest = await build_daily_digest(db, ist_now)
        await store_digest(db, digest)
        logger.warning(
            f"[TeamDigest] ✅ Done — {len(digest['top_overall'])} top, "
            f"{len(digest['inactive_recruiters'])} inactive recruiters"
        )
    except Exception as e:
        logger.exception(f"[TeamDigest] Failed: {e}")
