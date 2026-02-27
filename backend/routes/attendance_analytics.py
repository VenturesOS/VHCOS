"""
Attendance Analytics & Intelligence Routes
- Extensible analytics payload: {metrics, charts, insights}
- Pattern detection (rule-based)
- Health scores
- Notification management
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from collections import defaultdict
from fastapi import APIRouter, Depends, Query
from config import db
from utils import require_role
from services.attendance_cron_service import (
    calculate_health_score,
    run_attendance_reminders,
    run_auto_absent_marking,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/attendance/analytics", tags=["Attendance Analytics"])

# Indian Standard Time (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))


# ═══════════════════════════════════════
# ANALYTICS ENDPOINT
# ═══════════════════════════════════════

@router.get("")
async def get_attendance_analytics(
    days: int = Query(30, ge=7, le=365),
    team_only: bool = False,
    user=Depends(require_role(["admin", "employer"])),
):
    """
    Attendance analytics with extensible payload.
    Admin sees all, employer sees team only.
    """
    end_date = datetime.now(IST).strftime("%Y-%m-%d")
    start_date = (datetime.now(IST) - timedelta(days=days)).strftime("%Y-%m-%d")

    # Build user filter
    user_filter = {"role": {"$in": ["employer", "recruiter"]}, "is_active": True}
    if user.get("role") == "employer":
        team_only = True

    users = await db.users.find(user_filter, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}).to_list(500)
    user_ids = [u["id"] for u in users]
    user_map = {u["id"]: u for u in users}

    if user.get("role") == "employer":
        recruiter_ids = [u["id"] for u in users if u["role"] == "recruiter"]
        user_ids = recruiter_ids + [user["id"]]

    # Fetch records
    records = await db.attendance_records.find(
        {"user_id": {"$in": user_ids}, "date": {"$gte": start_date, "$lte": end_date}},
        {"_id": 0}
    ).to_list(50000)

    # Fetch settings
    settings = await db.attendance_settings.find_one({"id": "global"}, {"_id": 0}) or {}
    weekend_days = settings.get("weekend_days", [0, 6])

    # Count working days
    working_days = 0
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    while current <= end:
        if (current.weekday() + 1) % 7 not in weekend_days:
            working_days += 1
        current += timedelta(days=1)

    # ── METRICS ──
    total_records = len(records)
    present = sum(1 for r in records if r.get("status") in ("present", "wfh"))
    absent = sum(1 for r in records if r.get("status") == "absent")
    half_days = sum(1 for r in records if r.get("status") == "half_day")
    leaves = sum(1 for r in records if r.get("status") == "leave")
    late = sum(1 for r in records if r.get("is_late"))
    wfh = sum(1 for r in records if r.get("work_mode") == "wfh" or r.get("status") == "wfh")
    office = sum(1 for r in records if r.get("work_mode") == "office" and r.get("status") == "present")
    field = sum(1 for r in records if r.get("work_mode") == "field")
    total_hours = round(sum(r.get("hours_worked", 0) for r in records), 1)
    total_overtime = sum(r.get("overtime_minutes", 0) for r in records)
    avg_hours = round(total_hours / max(present, 1), 1)

    metrics = {
        "period": {"start": start_date, "end": end_date, "days": days, "working_days": working_days},
        "headcount": len(user_ids),
        "total_records": total_records,
        "present": present,
        "absent": absent,
        "half_days": half_days,
        "leaves": leaves,
        "late": late,
        "wfh": wfh,
        "office": office,
        "field": field,
        "total_hours": total_hours,
        "total_overtime_minutes": total_overtime,
        "avg_hours_per_day": avg_hours,
        "attendance_rate": round(present / max(working_days * len(user_ids), 1) * 100, 1),
        "absentee_rate": round(absent / max(working_days * len(user_ids), 1) * 100, 1),
        "late_rate": round(late / max(present, 1) * 100, 1),
    }

    # ── CHARTS ──

    # 1. Daily attendance trend (last N days)
    daily_trend = defaultdict(lambda: {"present": 0, "absent": 0, "leave": 0, "late": 0, "wfh": 0})
    for r in records:
        d = r.get("date", "")
        if r.get("status") in ("present", "wfh"):
            daily_trend[d]["present"] += 1
        elif r.get("status") == "absent":
            daily_trend[d]["absent"] += 1
        elif r.get("status") == "leave":
            daily_trend[d]["leave"] += 1
        if r.get("is_late"):
            daily_trend[d]["late"] += 1
        if r.get("work_mode") == "wfh" or r.get("status") == "wfh":
            daily_trend[d]["wfh"] += 1

    trend_data = [{"date": d, **daily_trend[d]} for d in sorted(daily_trend.keys())]

    # 2. Weekly late arrivals
    weekly_late = defaultdict(int)
    for r in records:
        if r.get("is_late"):
            dt = datetime.strptime(r["date"], "%Y-%m-%d")
            week_start = (dt - timedelta(days=dt.weekday())).strftime("%Y-%m-%d")
            weekly_late[week_start] += 1
    weekly_late_data = [{"week": w, "late_count": c} for w, c in sorted(weekly_late.items())]

    # 3. Team comparison (per user)
    team_data = []
    for uid in user_ids:
        u = user_map.get(uid, {})
        user_recs = [r for r in records if r["user_id"] == uid]
        u_present = sum(1 for r in user_recs if r.get("status") in ("present", "wfh"))
        u_absent = sum(1 for r in user_recs if r.get("status") == "absent")
        u_late = sum(1 for r in user_recs if r.get("is_late"))
        u_hours = round(sum(r.get("hours_worked", 0) for r in user_recs), 1)
        team_data.append({
            "name": u.get("name", "Unknown"),
            "role": u.get("role", ""),
            "present": u_present,
            "absent": u_absent,
            "late": u_late,
            "hours": u_hours,
        })

    # 4. Work mode distribution
    work_mode_dist = [
        {"name": "Office", "value": office},
        {"name": "WFH", "value": wfh},
        {"name": "Field", "value": field},
    ]

    charts = {
        "daily_trend": trend_data,
        "weekly_late": weekly_late_data,
        "team_comparison": sorted(team_data, key=lambda x: x["present"], reverse=True),
        "work_mode_distribution": work_mode_dist,
    }

    # ── INSIGHTS (Pattern Detection) ──
    insights = await _detect_patterns(records, user_ids, user_map, working_days, settings)

    return {"metrics": metrics, "charts": charts, "insights": insights}


# ═══════════════════════════════════════
# PATTERN DETECTION ENGINE
# ═══════════════════════════════════════

async def _detect_patterns(records, user_ids, user_map, working_days, settings):
    """Rule-based pattern detection. Returns list of insight objects."""
    insights = []
    late_threshold = settings.get("late_threshold_minutes", 15)
    overtime_threshold = settings.get("overtime_threshold_minutes", 60)

    for uid in user_ids:
        u = user_map.get(uid, {})
        name = u.get("name", "Unknown")
        user_recs = [r for r in records if r["user_id"] == uid]
        if not user_recs:
            continue

        present_count = sum(1 for r in user_recs if r.get("status") in ("present", "wfh"))
        absent_count = sum(1 for r in user_recs if r.get("status") == "absent")
        late_count = sum(1 for r in user_recs if r.get("is_late"))
        overtime_days = sum(1 for r in user_recs if r.get("overtime_minutes", 0) > overtime_threshold)
        short_days = sum(1 for r in user_recs if r.get("hours_worked", 0) > 0 and r.get("hours_worked", 0) < 4)

        # Rule 1: Chronic lateness (>5 late in 30 days)
        if late_count >= 5:
            severity = "critical" if late_count >= 10 else "warning"
            insights.append({
                "type": "chronic_lateness",
                "severity": severity,
                "user_id": uid,
                "user_name": name,
                "title": f"{name} — Frequent Late Arrivals",
                "description": f"Late {late_count} times in the period. Threshold: 5.",
                "value": late_count,
            })

        # Rule 2: Overtime spike (>5 overtime days)
        if overtime_days >= 5:
            severity = "warning" if overtime_days < 10 else "critical"
            insights.append({
                "type": "overtime_spike",
                "severity": severity,
                "user_id": uid,
                "user_name": name,
                "title": f"{name} — Overtime Spike",
                "description": f"Worked overtime on {overtime_days} days. May indicate workload issues.",
                "value": overtime_days,
            })

        # Rule 3: Frequent absences (>3 in 30 days)
        if absent_count >= 3:
            severity = "critical" if absent_count >= 7 else "warning" if absent_count >= 5 else "info"
            insights.append({
                "type": "frequent_absence",
                "severity": severity,
                "user_id": uid,
                "user_name": name,
                "title": f"{name} — Frequent Absences",
                "description": f"Absent {absent_count} days. Needs attention.",
                "value": absent_count,
            })

        # Rule 4: Short check-ins (worked <4h on multiple days)
        if short_days >= 3:
            insights.append({
                "type": "short_checkins",
                "severity": "info",
                "user_id": uid,
                "user_name": name,
                "title": f"{name} — Short Work Sessions",
                "description": f"{short_days} days with <4 hours worked.",
                "value": short_days,
            })

    # Sort: critical first, then warning, then info
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    insights.sort(key=lambda x: severity_order.get(x.get("severity", "info"), 2))

    return insights


# ═══════════════════════════════════════
# HEALTH SCORE ENDPOINT
# ═══════════════════════════════════════

@router.get("/health-scores")
async def get_health_scores(
    days: int = Query(30, ge=7, le=365),
    user=Depends(require_role(["admin", "employer"])),
):
    """Get attendance health scores for all relevant users."""
    user_filter = {"role": {"$in": ["employer", "recruiter"]}, "is_active": True}
    users = await db.users.find(user_filter, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}).to_list(500)

    if user.get("role") == "employer":
        users = [u for u in users if u["role"] == "recruiter" or u["id"] == user["id"]]

    scores = []
    for u in users:
        result = await calculate_health_score(u["id"], days)
        scores.append({
            "user_id": u["id"],
            "name": u["name"],
            "email": u["email"],
            "role": u["role"],
            **result,
        })

    scores.sort(key=lambda x: x["score"], reverse=True)
    avg_score = round(sum(s["score"] for s in scores) / max(len(scores), 1))

    return {"scores": scores, "average_score": avg_score}


# ═══════════════════════════════════════
# NOTIFICATION ENDPOINTS
# ═══════════════════════════════════════

@router.get("/notifications")
async def get_my_notifications(
    limit: int = Query(20, ge=1, le=100),
    user=Depends(require_role(["admin", "recruiter", "employer"])),
):
    """Get in-app notifications for current user."""
    events = await db.notification_events.find(
        {"recipient_id": user["id"]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(limit)

    unread = sum(1 for e in events if not e.get("is_read"))
    return {"notifications": events, "unread_count": unread}


@router.put("/notifications/{event_id}/read")
async def mark_notification_read(event_id: str, user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Mark a notification as read."""
    await db.notification_events.update_one(
        {"id": event_id, "recipient_id": user["id"]},
        {"$set": {"is_read": True}}
    )
    return {"message": "Marked as read"}


@router.put("/notifications/read-all")
async def mark_all_read(user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Mark all notifications as read."""
    await db.notification_events.update_many(
        {"recipient_id": user["id"], "is_read": False},
        {"$set": {"is_read": True}}
    )
    return {"message": "All marked as read"}


# ═══════════════════════════════════════
# CRON JOB MANAGEMENT (Admin)
# ═══════════════════════════════════════

@router.get("/cron-logs")
async def get_cron_logs(
    job_name: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    user=Depends(require_role(["admin"])),
):
    """Admin: View cron job execution logs."""
    query = {}
    if job_name:
        query["job_name"] = job_name

    logs = await db.cron_job_logs.find(query, {"_id": 0}).sort("executed_at", -1).to_list(limit)
    return {"logs": logs}


@router.post("/cron/trigger-reminders")
async def trigger_reminders(user=Depends(require_role(["admin"]))):
    """Admin: Manually trigger attendance reminders."""
    await run_attendance_reminders()
    return {"message": "Reminders triggered"}


@router.post("/cron/trigger-auto-absent")
async def trigger_auto_absent(user=Depends(require_role(["admin"]))):
    """Admin: Manually trigger auto-absent marking."""
    await run_auto_absent_marking()
    return {"message": "Auto-absent marking triggered"}
