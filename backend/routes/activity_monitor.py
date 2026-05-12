"""
Activity Monitor — Admin-only user activity tracking.

Aggregates from existing collections to measure portal adoption.
"""
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/activity-monitor", tags=["Activity Monitor"])


async def get_db():
    from config import db
    return db


from utils.auth import get_current_user
from services.leaderboard_kpis import (
    compute_leaderboard_kpis,
    parse_extended_date_range,
)


def _parse_date_range(period: str, start_date: Optional[str], end_date: Optional[str]):
    """Convert period filter to start/end datetime. Supports
    today/week/month/quarter/year/all/custom."""
    now = datetime.now(timezone.utc)
    if period == "custom" and start_date and end_date:
        start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        return start, end
    if period == "all":
        return datetime(1970, 1, 1, tzinfo=timezone.utc), now
    offsets = {"today": 0, "week": 7, "month": 30, "quarter": 90, "year": 365}
    days = offsets.get(period, 30)
    if days == 0:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now - timedelta(days=days)
    return start, now


def _init_user_map(users):
    """Build zeroed-out user activity map."""
    metrics = [
        "profiles_captured", "profiles_updated", "profiles_viewed",
        "profiles_edited", "stage_changes", "notes_added", "cv_uploads",
        "mandates_created", "applications_created", "trackers_created",
        "batch_uploads", "logins",
    ]
    return {u["id"]: {
        "user_id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"],
        **{m: 0 for m in metrics}, "total_actions": 0, "last_active": None,
    } for u in users}


ACTION_FIELD_MAP = {
    "captured": "profiles_captured",
    "updated": "profiles_updated",
    "viewed": "profiles_viewed",
    "profile_edited": "profiles_edited",
    "stage_changed": "stage_changes",
    "note_added": "notes_added",
    "cv_uploaded": "cv_uploads",
}


async def _aggregate_activity_logs(db, user_ids, start_iso, end_iso, user_map):
    """Aggregate activity_logs by user and action type."""
    pipeline = [
        {"$match": {"timestamp": {"$gte": start_iso, "$lte": end_iso}, "performed_by": {"$in": user_ids}}},
        {"$group": {"_id": {"user": "$performed_by", "action": "$action"}, "count": {"$sum": 1}, "last_ts": {"$max": "$timestamp"}}}
    ]
    for r in await db.activity_logs.aggregate(pipeline, allowDiskUse=True).to_list(1000):
        uid, action = r["_id"]["user"], r["_id"]["action"]
        if uid not in user_map:
            continue
        field = ACTION_FIELD_MAP.get(action)
        if field:
            user_map[uid][field] = r["count"]
        last_ts = r.get("last_ts")
        if last_ts and (not user_map[uid]["last_active"] or last_ts > user_map[uid]["last_active"]):
            user_map[uid]["last_active"] = last_ts


async def _aggregate_collection(db, collection, match_field, user_ids, start_iso, end_iso):
    """Generic count-by-user aggregation."""
    pipeline = [
        {"$match": {"created_at": {"$gte": start_iso, "$lte": end_iso}, match_field: {"$in": user_ids}}},
        {"$group": {"_id": f"${match_field}", "count": {"$sum": 1}}}
    ]
    return {r["_id"]: r["count"] for r in await db[collection].aggregate(pipeline).to_list(500) if r["_id"]}


@router.get("/summary")
async def get_activity_summary(
    period: str = Query("month", regex="^(today|week|month|quarter|year|all|custom)$"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Returns per-user activity summary with all metrics. Admin-only.

    Ranking is by a **blended composite score** that mirrors the WhatsApp
    Daily Digest KPIs:
        composite = 0.6 × activity_score_normalised
                  + 0.2 × capture_quality_pct
                  + 0.2 × mandate_efficiency_pct
    Existing action counts (captures, views, pipeline, stages, mandates,
    logins, …) are still included for transparency + the expanded row.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    start, end = _parse_date_range(period, start_date, end_date)
    start_iso, end_iso = start.isoformat(), end.isoformat()

    users = await db.users.find(
        {"role": {"$in": ["admin", "recruiter", "employer", "accounts"]}, "is_active": True},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    ).to_list(500)

    user_map = _init_user_map(users)
    user_ids = list(user_map.keys())

    # 1. Activity logs
    await _aggregate_activity_logs(db, user_ids, start_iso, end_iso, user_map)

    # 2. Jobs/mandates (uses posted_by)
    jobs_counts = await _aggregate_collection(db, "jobs", "posted_by", user_ids, start_iso, end_iso)
    for uid, count in jobs_counts.items():
        if uid in user_map:
            user_map[uid]["mandates_created"] = count

    # 3. Applications
    apps_counts = await _aggregate_collection(db, "applications", "created_by", user_ids, start_iso, end_iso)
    for uid, count in apps_counts.items():
        if uid in user_map:
            user_map[uid]["applications_created"] = count

    # 4. Submission trackers
    tracker_counts = await _aggregate_collection(db, "submission_trackers", "created_by", user_ids, start_iso, end_iso)
    for uid, count in tracker_counts.items():
        if uid in user_map:
            user_map[uid]["trackers_created"] = count

    # 5. Batch uploads
    batch_counts = await _aggregate_collection(db, "bulk_import_batches", "uploaded_by", user_ids, start_iso, end_iso)
    for uid, count in batch_counts.items():
        if uid in user_map:
            user_map[uid]["batch_uploads"] = count

    # 6. Login sessions
    login_pipeline = [
        {"$match": {"created_at": {"$gte": start_iso, "$lte": end_iso}, "user_id": {"$in": user_ids}}},
        {"$group": {"_id": "$user_id", "count": {"$sum": 1}, "last_login": {"$max": "$created_at"}}}
    ]
    for r in await db.refresh_tokens.aggregate(login_pipeline).to_list(500):
        uid = r["_id"]
        if uid in user_map:
            user_map[uid]["logins"] = r["count"]
            last_login = r.get("last_login")
            if last_login and (not user_map[uid]["last_active"] or str(last_login) > str(user_map[uid]["last_active"])):
                user_map[uid]["last_active"] = last_login

    # Calculate totals (action counts — kept for transparency)
    metric_keys = list(ACTION_FIELD_MAP.values()) + ["mandates_created", "applications_created", "trackers_created", "batch_uploads", "logins"]
    user_list = []
    for data in user_map.values():
        data["total_actions"] = sum(data[k] for k in metric_keys)
        user_list.append(data)

    # ── Blended composite KPI ranking (Phase 54.19) ────────────────────
    # Mirrors WhatsApp Daily Digest scoring: activity score + quality +
    # mandate efficiency. Bulk Mongo sweep, safe for 100+ users.
    kpi_matrix = await compute_leaderboard_kpis(db, user_ids, start_iso, end_iso)
    for u in user_list:
        kpi = kpi_matrix.get(u["user_id"], {})
        u["activity_score"] = kpi.get("activity_score", 0.0)
        u["pipeline_points"] = round(kpi.get("pipeline_points", 0.0), 1)
        u["capture_quality"] = kpi.get("capture_quality", 0.0)
        u["mandate_efficiency"] = kpi.get("mandate_efficiency", 0.0)
        u["composite_score"] = kpi.get("composite_score", 0.0)
        # Digest-side capture count (extension only, source-filtered) —
        # different from `profiles_captured` (activity_logs-based).
        u["captures_digest"] = kpi.get("captures", 0)
        u["cv_uploads_digest"] = kpi.get("cv_uploads", 0)

    # Rank by composite, fall back to activity_score, then total_actions
    user_list.sort(
        key=lambda x: (
            -x["composite_score"],
            -x["activity_score"],
            -x["total_actions"],
        )
    )

    platform_totals = {k: sum(u[k] for u in user_list) for k in metric_keys}
    platform_totals["total_actions"] = sum(u["total_actions"] for u in user_list)
    platform_totals["active_users"] = sum(1 for u in user_list if u["total_actions"] > 0)
    platform_totals["inactive_users"] = sum(1 for u in user_list if u["total_actions"] == 0)
    platform_totals["total_users"] = len(user_list)

    return {"period": period, "start_date": start_iso, "end_date": end_iso, "platform_totals": platform_totals, "users": user_list}


@router.get("/trend")
async def get_activity_trend(
    period: str = Query("month", regex="^(today|week|month|quarter|year|all|custom)$"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Returns daily activity counts for trend chart."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    start, end = _parse_date_range(period, start_date, end_date)
    pipeline = [
        {"$match": {"timestamp": {"$gte": start.isoformat(), "$lte": end.isoformat()}}},
        {"$addFields": {"date_str": {"$substr": ["$timestamp", 0, 10]}}},
        {"$group": {"_id": {"date": "$date_str", "action": "$action"}, "count": {"$sum": 1}}},
        {"$sort": {"_id.date": 1}}
    ]
    results = await db.activity_logs.aggregate(pipeline, allowDiskUse=True).to_list(5000)

    action_map = {"captured": "captured", "updated": "updated", "viewed": "viewed", "profile_edited": "edited", "stage_changed": "stage_changed"}
    daily = {}
    for r in results:
        date = r["_id"]["date"]
        if date not in daily:
            daily[date] = {"date": date, "captured": 0, "updated": 0, "viewed": 0, "edited": 0, "stage_changed": 0, "total": 0}
        field = action_map.get(r["_id"]["action"])
        if field:
            daily[date][field] = r["count"]
        daily[date]["total"] += r["count"]

    return {"period": period, "trend": sorted(daily.values(), key=lambda x: x["date"])}
