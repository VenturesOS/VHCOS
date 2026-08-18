"""
Capture Diagnostics — root-cause analyzer for Naukri extension captures.

Aggregates existing `naukri_capture_logs` entries into actionable patterns so
we can figure out WHY the extension misses fields, not just WHICH fields miss.

Endpoints (admin only):
  GET  /api/admin/capture-diagnostics/summary?days=30
  GET  /api/admin/capture-diagnostics/failures?field=&cause=&days=30&limit=100
  GET  /api/admin/capture-diagnostics/capture/{log_id}      (admin@vhc.in only)
"""
from __future__ import annotations
import re
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from utils.auth import require_role

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/capture-diagnostics", tags=["Capture Diagnostics"])


async def get_db():
    from config import db
    return db


# Fields we care about. Ordered by business impact.
TRACKED_FIELDS = [
    "name", "email", "phone", "current_company", "designation", "location",
    "experience_years", "current_salary", "expected_salary",
    "notice_period", "skills", "education", "resume_url",
]


def _classify_cause(log: dict) -> str:
    """Assign a root-cause bucket to a failed/partial capture based on the
    signals the extension already emits."""
    reason = (log.get("failure_reason") or "").lower()
    step = (log.get("failed_step") or "").lower()
    duration = log.get("capture_duration_ms") or 0
    missing = log.get("data_missing_fields") or []
    url = log.get("profile_url") or ""

    # Explicit failure reasons take priority (extension already told us)
    if "timeout" in reason or "timed out" in reason:
        return "timeout"
    if "selector" in reason or "not found" in reason or "queryselector" in reason:
        return "selector_not_found"
    if "auth" in reason or "login" in reason or "401" in reason or "403" in reason:
        return "auth_or_login_wall"
    if "network" in reason or "fetch" in reason or "cors" in reason:
        return "network_error"
    if "parse" in reason or "json" in reason or "syntaxerror" in reason:
        return "parse_error"
    if step:
        return f"step_failed:{step}"

    # Heuristics when the extension didn't log a reason
    contact_fields = {"phone", "email"}
    missing_set = set(missing)
    # Strong signal: multiple contact-section fields missing together
    if len(contact_fields & missing_set) >= 2:
        return "contact_section_collapsed"
    # Very fast capture + many misses → page not ready
    if duration and duration < 500 and len(missing) >= 3:
        return "page_not_fully_loaded"
    # Only tag search-result variant when it's a HEAVY miss (>=4 fields) —
    # a single missing field on a search-URL page is usually just data absence.
    if len(missing) >= 4 and ("naukri.com/mnjuser/search" in url.lower()
                              or "/search-results" in url.lower()):
        return "search_result_variant_dom"
    if not missing:
        return "success"
    # Single field missing → the field is likely genuinely not on the profile
    if len(missing) == 1:
        return "field_absent_on_profile"
    return "partial_capture_unknown"


def _cause_action(cause: str) -> str:
    """Human-readable fix hint for each cause bucket."""
    return {
        "timeout":                    "Increase MAX_WAIT_MS or wait for a stronger DOM signal before extracting.",
        "selector_not_found":         "Naukri changed the DOM — update selectors in content-script for this field.",
        "auth_or_login_wall":         "User was logged out or hit a login/paywall interstitial. Add re-login prompt.",
        "network_error":              "API call from extension failed. Check CORS/host-permissions in manifest.",
        "parse_error":                "Captured HTML did not parse. Log the raw HTML snippet on parse failure.",
        "contact_section_collapsed":  "The 'Show contact' button was not clicked before extraction — add explicit click+wait step.",
        "page_not_fully_loaded":      "Capture fired < 500ms after page nav. Add MutationObserver-based readiness check.",
        "search_result_variant_dom":  "Search-result page uses a different DOM tree than saved profiles. Add a URL-routed extractor.",
        "field_absent_on_profile":    "Only one field missed — likely truly not on the profile, not an extension bug.",
        "partial_capture_unknown":    "Multiple fields missed but no clear pattern — inspect raw log to identify selector.",
        "success":                    "No action needed.",
    }.get(cause, "Investigate manually — check the raw capture log below.")


@router.get("/summary")
async def diagnostics_summary(
    days: int = Query(30, ge=1, le=180),
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """Aggregate all captures in the given window → returns per-field failure
    stats, top root-causes, weekly trend, and top failing URL patterns."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cursor = db.naukri_capture_logs.find(
        {"timestamp": {"$gte": cutoff}},
        {"_id": 0, "timestamp": 1, "status": 1, "data_missing_fields": 1,
         "capture_duration_ms": 1, "failure_reason": 1, "failed_step": 1,
         "profile_url": 1, "retry_count": 1},
    )

    total = 0
    successful = 0
    field_miss = Counter()               # field -> count
    cofailure = defaultdict(Counter)     # field -> {other_field: count}
    causes = Counter()                   # cause -> count
    cause_by_field = defaultdict(Counter)  # field -> {cause: count}
    duration_buckets = Counter()         # bucket -> count
    weekly = defaultdict(lambda: {"total": 0, "clean": 0})   # yyyy-ww -> {..}
    url_host_fail = Counter()

    async for log in cursor:
        total += 1
        missing = list(log.get("data_missing_fields") or [])
        cause = _classify_cause(log)
        causes[cause] += 1
        if cause == "success" and not missing:
            successful += 1

        for f in missing:
            if f in TRACKED_FIELDS:
                field_miss[f] += 1
                cause_by_field[f][cause] += 1
                for other in missing:
                    if other != f and other in TRACKED_FIELDS:
                        cofailure[f][other] += 1

        d = log.get("capture_duration_ms") or 0
        if d == 0:
            duration_buckets["0"] += 1
        elif d < 500:
            duration_buckets["<500ms"] += 1
        elif d < 1500:
            duration_buckets["500-1500ms"] += 1
        elif d < 5000:
            duration_buckets["1500-5000ms"] += 1
        else:
            duration_buckets[">5s"] += 1

        try:
            ts = datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00"))
            wk = f"{ts.isocalendar().year}-W{ts.isocalendar().week:02d}"
        except Exception:
            wk = "unknown"
        weekly[wk]["total"] += 1
        if not missing:
            weekly[wk]["clean"] += 1

        url = log.get("profile_url") or ""
        if missing:
            m = re.search(r"://([^/]+)(/[^?]*)", url)
            host_path = f"{m.group(1)}{m.group(2)[:40]}" if m else "unknown"
            url_host_fail[host_path] += 1

    top_causes = [
        {"cause": c, "count": n,
         "pct": round(100 * n / max(total, 1), 1),
         "action": _cause_action(c)}
        for c, n in causes.most_common()
    ]

    field_stats = []
    for f in TRACKED_FIELDS:
        miss_n = field_miss[f]
        top_cause = cause_by_field[f].most_common(1)
        top_co = cofailure[f].most_common(3)
        field_stats.append({
            "field": f,
            "missed": miss_n,
            "miss_rate_pct": round(100 * miss_n / max(total, 1), 2),
            "top_cause": top_cause[0][0] if top_cause else None,
            "top_cofailures": [{"field": k, "count": v} for k, v in top_co],
        })
    field_stats.sort(key=lambda x: -x["missed"])

    weekly_series = [
        {"week": wk, "total": v["total"], "clean": v["clean"],
         "clean_pct": round(100 * v["clean"] / max(v["total"], 1), 1)}
        for wk, v in sorted(weekly.items())
    ]

    return {
        "window_days": days,
        "total_captures": total,
        "clean_captures": successful,
        "success_rate_pct": round(100 * successful / max(total, 1), 2),
        "field_stats": field_stats,
        "top_causes": top_causes,
        "duration_distribution": dict(duration_buckets),
        "weekly_trend": weekly_series,
        "top_failing_urls": [
            {"host_path": hp, "count": n} for hp, n in url_host_fail.most_common(10)
        ],
    }


@router.get("/failures")
async def diagnostics_failures(
    field: Optional[str] = Query(None, description="Filter to captures missing this field"),
    cause: Optional[str] = Query(None, description="Filter to a root-cause bucket"),
    days: int = Query(30, ge=1, le=180),
    limit: int = Query(100, ge=1, le=500),
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """Drilldown list of failed/partial captures. Each row includes the
    inferred cause + a link to the Naukri profile so you can inspect the
    live DOM against the selectors."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    q = {"timestamp": {"$gte": cutoff}}
    if field:
        q["data_missing_fields"] = field

    rows = []
    cursor = db.naukri_capture_logs.find(q, {"_id": 0}).sort("timestamp", -1).limit(limit * 2)
    async for log in cursor:
        c = _classify_cause(log)
        if cause and c != cause:
            continue
        rows.append({
            "id": log.get("id"),
            "timestamp": log.get("timestamp"),
            "candidate_name": log.get("candidate_name"),
            "profile_url": log.get("profile_url"),
            "captured_by_name": log.get("captured_by_name"),
            "missing_fields": log.get("data_missing_fields") or [],
            "capture_duration_ms": log.get("capture_duration_ms"),
            "failure_reason": log.get("failure_reason"),
            "failed_step": log.get("failed_step"),
            "retry_count": log.get("retry_count", 0),
            "cause": c,
            "action_hint": _cause_action(c),
        })
        if len(rows) >= limit:
            break
    return {"rows": rows, "count": len(rows)}


@router.get("/capture/{log_id}")
async def diagnostics_capture_detail(
    log_id: str,
    db=Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    """Full raw capture blob for a single log entry. Restricted to
    admin@vhc.in for candidate-data privacy."""
    if (user.get("email") or "").lower() != "admin@vhc.in":
        raise HTTPException(403, "Raw capture inspection restricted to admin@vhc.in")

    log = await db.naukri_capture_logs.find_one({"id": log_id}, {"_id": 0})
    if not log:
        raise HTTPException(404, "Capture log not found")
    log["_cause"] = _classify_cause(log)
    log["_action_hint"] = _cause_action(log["_cause"])
    return log
