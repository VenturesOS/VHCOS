"""
Attendance Cron Service
- Job-lock mechanism for idempotent execution
- Attendance reminders (configurable time)
- Auto-absent marking (end of day)
- should_remind() decision layer
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from config import db
from services.email_service import send_email

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════
# JOB LOCK MECHANISM
# ═══════════════════════════════════════

async def acquire_lock(job_name: str, lock_ttl_seconds: int = 600) -> bool:
    """Acquire an exclusive lock for a cron job. Returns True if acquired."""
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(seconds=lock_ttl_seconds)

    result = await db.cron_job_locks.find_one_and_update(
        {"job_name": job_name, "$or": [
            {"locked": False},
            {"expires_at": {"$lt": now.isoformat()}},
        ]},
        {"$set": {
            "locked": True,
            "locked_at": now.isoformat(),
            "expires_at": expiry.isoformat(),
        }},
        upsert=True,
        return_document=True,
    )
    return result is not None


async def release_lock(job_name: str):
    """Release a cron job lock."""
    await db.cron_job_locks.update_one(
        {"job_name": job_name},
        {"$set": {"locked": False}},
    )


async def log_job_execution(job_name: str, status: str, details: dict):
    """Log cron job execution for audit."""
    await db.cron_job_logs.insert_one({
        "id": str(uuid.uuid4()),
        "job_name": job_name,
        "status": status,
        "details": details,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    })


# ═══════════════════════════════════════
# NOTIFICATION HELPERS
# ═══════════════════════════════════════

async def create_notification_event(
    event_type: str,
    recipient_id: str,
    recipient_email: str,
    title: str,
    message: str,
    channels: list = None,
    metadata: dict = None,
):
    """Create a notification event and queue delivery."""
    now = datetime.now(timezone.utc).isoformat()
    event_id = str(uuid.uuid4())

    event = {
        "id": event_id,
        "event_type": event_type,
        "recipient_id": recipient_id,
        "recipient_email": recipient_email,
        "title": title,
        "message": message,
        "channels": channels or ["in_app", "email"],
        "metadata": metadata or {},
        "is_read": False,
        "created_at": now,
    }
    await db.notification_events.insert_one(event)

    # Create delivery logs per channel
    for channel in event.get("channels", []):
        delivery_log = {
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "channel": channel,
            "recipient_id": recipient_id,
            "recipient_email": recipient_email,
            "status": "pending",
            "attempts": 0,
            "max_retries": 3,
            "last_attempt_at": None,
            "delivered_at": None,
            "error": None,
            "created_at": now,
        }
        await db.notification_delivery_logs.insert_one(delivery_log)

    return event_id


async def process_email_delivery(event_id: str):
    """Process pending email delivery for a notification event."""
    event = await db.notification_events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        return

    log = await db.notification_delivery_logs.find_one(
        {"event_id": event_id, "channel": "email", "status": {"$in": ["pending", "retry"]}},
        {"_id": 0}
    )
    if not log:
        return

    now = datetime.now(timezone.utc).isoformat()
    attempts = log.get("attempts", 0) + 1

    try:
        result = await send_email(
            recipient_email=event["recipient_email"],
            subject=event["title"],
            html_content=event["message"],
        )

        status = "delivered" if result.get("status") == "sent" else "failed"
        if result.get("status") == "skipped":
            status = "skipped"

        await db.notification_delivery_logs.update_one(
            {"id": log["id"]},
            {"$set": {
                "status": status,
                "attempts": attempts,
                "last_attempt_at": now,
                "delivered_at": now if status == "delivered" else None,
                "error": result.get("message") if status == "failed" else None,
            }}
        )
    except Exception as e:
        retry_status = "retry" if attempts < log.get("max_retries", 3) else "failed"
        await db.notification_delivery_logs.update_one(
            {"id": log["id"]},
            {"$set": {
                "status": retry_status,
                "attempts": attempts,
                "last_attempt_at": now,
                "error": str(e),
            }}
        )


# ═══════════════════════════════════════
# SETTINGS HELPER
# ═══════════════════════════════════════

async def _get_settings():
    """Get attendance settings with defaults."""
    settings = await db.attendance_settings.find_one({"id": "global"}, {"_id": 0})
    defaults = {
        "work_start_time": "09:00",
        "work_end_time": "18:00",
        "late_threshold_minutes": 15,
        "half_day_hours": 4.5,
        "full_day_hours": 9.0,
        "reminder_time": "10:00",
        "auto_absent_time": "18:30",
        "overtime_threshold_minutes": 60,
        "grace_window_minutes": 30,
        "weekend_days": [0, 6],
    }
    if settings:
        defaults.update({k: v for k, v in settings.items() if k != "id"})
    return defaults


# ═══════════════════════════════════════
# DECISION LAYER: should_remind()
# ═══════════════════════════════════════

async def should_remind(user_id: str, date_str: str, settings: dict) -> tuple:
    """
    Determine if an employee should receive a check-in reminder.
    Returns (should_remind: bool, reason: str).
    """
    # 1. Check if weekend
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    weekday = dt.weekday()  # Mon=0, Sun=6
    day_of_week = (weekday + 1) % 7  # Convert: Sun=0, Mon=1, ..., Sat=6
    weekend_days = settings.get("weekend_days", [0, 6])
    if day_of_week in weekend_days:
        return False, "weekend"

    # 2. Check if holiday
    holiday = await db.holidays.find_one({"date": date_str}, {"_id": 0})
    if holiday and not holiday.get("is_optional", False):
        return False, f"holiday:{holiday.get('name', '')}"

    # 3. Check if already checked in
    record = await db.attendance_records.find_one(
        {"user_id": user_id, "date": date_str}, {"_id": 0}
    )
    if record and record.get("check_in"):
        return False, "already_checked_in"

    # 4. Check if on approved leave
    leave = await db.leave_requests.find_one({
        "user_id": user_id,
        "status": "approved",
        "start_date": {"$lte": date_str},
        "end_date": {"$gte": date_str},
    }, {"_id": 0})
    if leave:
        return False, f"on_leave:{leave.get('leave_type', '')}"

    # 5. Check if already reminded today
    existing_notif = await db.notification_events.find_one({
        "recipient_id": user_id,
        "event_type": "attendance_reminder",
        "created_at": {"$gte": f"{date_str}T00:00:00"},
    }, {"_id": 0})
    if existing_notif:
        return False, "already_reminded"

    return True, "eligible"


# ═══════════════════════════════════════
# CRON JOB: ATTENDANCE REMINDER
# ═══════════════════════════════════════

def _reminder_email_html(user_name: str, date_str: str) -> str:
    """Generate reminder email HTML."""
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:24px;">
      <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:20px;text-align:center;">
        <h2 style="color:#15803d;margin:0 0 8px;">Check-In Reminder</h2>
        <p style="color:#374151;margin:0 0 12px;">Hi <strong>{user_name}</strong>,</p>
        <p style="color:#6b7280;margin:0 0 16px;">You haven't checked in today ({date_str}). Please check in to mark your attendance.</p>
        <p style="color:#9ca3af;font-size:12px;margin:0;">— VHC Talent OS · Attendance System</p>
      </div>
    </div>
    """


async def run_attendance_reminders():
    """Cron job: Send reminders to employees who haven't checked in."""
    job_name = "attendance_reminder"

    if not await acquire_lock(job_name):
        logger.info(f"[CRON] {job_name}: Lock not acquired, skipping.")
        return

    try:
        settings = await _get_settings()

        # Skip if attendance is paused
        if settings.get("is_paused"):
            await log_job_execution(job_name, "skipped", {"reason": "attendance_paused"})
            logger.info(f"[CRON] {job_name}: Skipped — attendance is paused.")
            return

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Get all active employers/recruiters
        users = await db.users.find(
            {"role": {"$in": ["employer", "recruiter"]}, "is_active": True},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
        ).to_list(500)

        reminded = 0
        skipped = 0

        for user in users:
            should, reason = await should_remind(user["id"], today, settings)
            if should:
                event_id = await create_notification_event(
                    event_type="attendance_reminder",
                    recipient_id=user["id"],
                    recipient_email=user["email"],
                    title="Check-In Reminder",
                    message=_reminder_email_html(user.get("name", user["email"]), today),
                    channels=["in_app", "email"],
                    metadata={"date": today, "trigger": "cron"},
                )
                await process_email_delivery(event_id)
                reminded += 1
            else:
                skipped += 1

        await log_job_execution(job_name, "success", {
            "date": today,
            "reminded": reminded,
            "skipped": skipped,
            "total_users": len(users),
        })
        logger.info(f"[CRON] {job_name}: Reminded {reminded}, skipped {skipped}")

    except Exception as e:
        logger.error(f"[CRON] {job_name} FAILED: {e}")
        await log_job_execution(job_name, "failed", {"error": str(e)})
    finally:
        await release_lock(job_name)


# ═══════════════════════════════════════
# CRON JOB: AUTO ABSENT MARKING
# ═══════════════════════════════════════

async def should_mark_absent(user_id: str, date_str: str, settings: dict) -> tuple:
    """
    Determine if an employee should be auto-marked absent.
    Returns (should_mark: bool, reason: str).
    """
    # 1. Check weekend
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    weekday = dt.weekday()
    day_of_week = (weekday + 1) % 7
    weekend_days = settings.get("weekend_days", [0, 6])
    if day_of_week in weekend_days:
        return False, "weekend"

    # 2. Check holiday
    holiday = await db.holidays.find_one({"date": date_str}, {"_id": 0})
    if holiday and not holiday.get("is_optional", False):
        return False, f"holiday:{holiday.get('name', '')}"

    # 3. Check if already has attendance
    record = await db.attendance_records.find_one(
        {"user_id": user_id, "date": date_str}, {"_id": 0}
    )
    if record:
        return False, f"has_record:{record.get('status', '')}"

    # 4. Check approved leave
    leave = await db.leave_requests.find_one({
        "user_id": user_id,
        "status": "approved",
        "start_date": {"$lte": date_str},
        "end_date": {"$gte": date_str},
    }, {"_id": 0})
    if leave:
        return False, f"on_leave:{leave.get('leave_type', '')}"

    return True, "no_check_in_no_leave"


async def run_auto_absent_marking():
    """Cron job: Auto-mark absent for employees with no check-in and no leave."""
    job_name = "auto_absent"

    if not await acquire_lock(job_name):
        logger.info(f"[CRON] {job_name}: Lock not acquired, skipping.")
        return

    try:
        settings = await _get_settings()

        # Skip if attendance is paused
        if settings.get("is_paused"):
            await log_job_execution(job_name, "skipped", {"reason": "attendance_paused"})
            logger.info(f"[CRON] {job_name}: Skipped — attendance is paused.")
            return

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        users = await db.users.find(
            {"role": {"$in": ["employer", "recruiter"]}, "is_active": True},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
        ).to_list(500)

        marked = 0
        skipped = 0
        now_iso = datetime.now(timezone.utc).isoformat()

        for user in users:
            should, reason = await should_mark_absent(user["id"], today, settings)
            if should:
                record = {
                    "id": str(uuid.uuid4()),
                    "user_id": user["id"],
                    "user_name": user.get("name", ""),
                    "user_email": user.get("email", ""),
                    "user_role": user.get("role", ""),
                    "date": today,
                    "check_in": None,
                    "check_out": None,
                    "status": "absent",
                    "work_mode": "",
                    "hours_worked": 0,
                    "late_minutes": 0,
                    "overtime_minutes": 0,
                    "is_late": False,
                    "ip_address": "",
                    "notes": "Auto-marked absent — no check-in or approved leave",
                    "marked_by": "system:auto_absent",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
                await db.attendance_records.insert_one(record)
                marked += 1
            else:
                skipped += 1

        await log_job_execution(job_name, "success", {
            "date": today,
            "marked_absent": marked,
            "skipped": skipped,
            "total_users": len(users),
        })
        logger.info(f"[CRON] {job_name}: Marked {marked} absent, skipped {skipped}")

    except Exception as e:
        logger.error(f"[CRON] {job_name} FAILED: {e}")
        await log_job_execution(job_name, "failed", {"error": str(e)})
    finally:
        await release_lock(job_name)


# ═══════════════════════════════════════
# HEALTH SCORE CALCULATOR
# ═══════════════════════════════════════

async def calculate_health_score(user_id: str, days: int = 30) -> dict:
    """
    Calculate attendance health score (0-100) for a user.
    Based on: punctuality, consistency, absenteeism, overtime patterns.
    """
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    records = await db.attendance_records.find(
        {"user_id": user_id, "date": {"$gte": start_date, "$lte": end_date}},
        {"_id": 0}
    ).to_list(200)

    if not records:
        return {"score": 50, "breakdown": {}, "label": "No Data"}

    settings = await _get_settings()
    weekend_days = settings.get("weekend_days", [0, 6])

    # Count working days in period
    working_days = 0
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    while current <= end:
        day_of_week = (current.weekday() + 1) % 7
        if day_of_week not in weekend_days:
            working_days += 1
        current += timedelta(days=1)

    present_count = sum(1 for r in records if r.get("status") in ("present", "wfh"))
    absent_count = sum(1 for r in records if r.get("status") == "absent")
    late_count = sum(1 for r in records if r.get("is_late"))
    half_day_count = sum(1 for r in records if r.get("status") == "half_day")
    leave_count = sum(1 for r in records if r.get("status") == "leave")

    total_hours = sum(r.get("hours_worked", 0) for r in records)
    avg_hours = total_hours / max(present_count, 1)
    overtime_days = sum(1 for r in records if r.get("overtime_minutes", 0) > settings.get("overtime_threshold_minutes", 60))

    # Score calculation (weighted)
    punctuality = max(0, 100 - (late_count / max(present_count, 1)) * 100) * 0.30
    consistency = (present_count / max(working_days, 1)) * 100 * 0.35
    no_absence = max(0, 100 - (absent_count / max(working_days, 1)) * 200) * 0.25
    work_hours = min(100, (avg_hours / settings.get("full_day_hours", 9.0)) * 100) * 0.10

    score = round(punctuality + consistency + no_absence + work_hours)
    score = max(0, min(100, score))

    label = "Excellent" if score >= 90 else "Good" if score >= 75 else "Average" if score >= 50 else "Needs Improvement"

    result = {
        "score": score,
        "label": label,
        "breakdown": {
            "punctuality": round(punctuality / 0.30) if punctuality else 0,
            "consistency": round(consistency / 0.35) if consistency else 0,
            "no_absence": round(no_absence / 0.25) if no_absence else 0,
            "work_hours": round(work_hours / 0.10) if work_hours else 0,
        },
        "stats": {
            "working_days": working_days,
            "present": present_count,
            "absent": absent_count,
            "late": late_count,
            "half_days": half_day_count,
            "leaves": leave_count,
            "avg_hours": round(avg_hours, 1),
            "overtime_days": overtime_days,
        },
    }

    # Store for later retrieval
    await db.attendance_health_scores.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "score": score,
            "label": label,
            "breakdown": result["breakdown"],
            "stats": result["stats"],
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )

    return result
