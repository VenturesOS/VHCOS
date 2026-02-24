"""
Attendance & Leave Management Routes
- Self check-in/check-out with IP logging
- Admin override for marking attendance
- Leave request/approval workflow
- Leave balance management (admin sets per user)
- Holiday calendar (admin managed)
- Monthly reports with Excel export
"""
import uuid
import io
import logging
from datetime import datetime, timezone, date, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from config import db
from utils import require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/attendance", tags=["Attendance"])

# ── Pydantic Models ──

class CheckInRequest(BaseModel):
    notes: Optional[str] = None
    work_mode: str = "office"  # office, wfh, field

class CheckOutRequest(BaseModel):
    notes: Optional[str] = None

class AdminMarkRequest(BaseModel):
    user_id: str
    date: str  # YYYY-MM-DD
    status: str  # present, absent, half_day, leave, wfh, holiday
    check_in: Optional[str] = None  # HH:MM
    check_out: Optional[str] = None  # HH:MM
    notes: Optional[str] = None

class LeaveRequestCreate(BaseModel):
    leave_type: str  # casual, sick, earned, comp_off
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD
    reason: str
    half_day: bool = False

class LeaveActionRequest(BaseModel):
    notes: Optional[str] = None

class LeaveBalanceSet(BaseModel):
    casual_leave: Optional[int] = None
    sick_leave: Optional[int] = None
    earned_leave: Optional[int] = None
    comp_off: Optional[int] = None

class HolidayCreate(BaseModel):
    name: str
    date: str  # YYYY-MM-DD
    holiday_type: str = "national"  # national, festival, company, optional
    is_optional: bool = False

class HolidayUpdate(BaseModel):
    name: Optional[str] = None
    date: Optional[str] = None
    holiday_type: Optional[str] = None
    is_optional: Optional[bool] = None

class AttendanceSettingsUpdate(BaseModel):
    work_start_time: Optional[str] = None  # HH:MM
    work_end_time: Optional[str] = None  # HH:MM
    late_threshold_minutes: Optional[int] = None
    half_day_hours: Optional[float] = None
    full_day_hours: Optional[float] = None
    reminder_time: Optional[str] = None  # HH:MM (default 10:00)
    auto_absent_time: Optional[str] = None  # HH:MM (default 18:30)
    overtime_threshold_minutes: Optional[int] = None  # default 60
    grace_window_minutes: Optional[int] = None  # default 30
    weekend_days: Optional[list] = None  # [0,6] = Sun,Sat
    is_paused: Optional[bool] = None

class PreLaunchResetRequest(BaseModel):
    confirmation: str  # Must be "RESET DATA"


# ── Helper Functions ──

async def _get_settings():
    """Get attendance settings or return defaults."""
    settings = await db.attendance_settings.find_one({"id": "global"}, {"_id": 0})
    defaults = {
        "id": "global",
        "work_start_time": "09:00",
        "work_end_time": "18:00",
        "late_threshold_minutes": 15,
        "half_day_hours": 4.5,
        "full_day_hours": 9.0,
        "reminder_time": "10:00",
        "auto_absent_time": "18:30",
        "overtime_threshold_minutes": 60,
        "grace_window_minutes": 30,
        "weekend_days": [0, 6],  # Sunday=0, Saturday=6
        "is_paused": False,
    }
    if settings:
        defaults.update(settings)
    return defaults

def _calc_hours(check_in_str, check_out_str):
    """Calculate hours between check-in and check-out."""
    try:
        fmt = "%H:%M"
        ci = datetime.strptime(check_in_str, fmt)
        co = datetime.strptime(check_out_str, fmt)
        diff = (co - ci).total_seconds() / 3600
        return round(max(0, diff), 2)
    except Exception:
        return 0

def _calc_late_minutes(check_in_str, work_start_str):
    """Calculate late minutes."""
    try:
        fmt = "%H:%M"
        ci = datetime.strptime(check_in_str, fmt)
        ws = datetime.strptime(work_start_str, fmt)
        diff = (ci - ws).total_seconds() / 60
        return max(0, int(diff))
    except Exception:
        return 0

def _calc_overtime(check_out_str, work_end_str):
    """Calculate overtime minutes."""
    try:
        fmt = "%H:%M"
        co = datetime.strptime(check_out_str, fmt)
        we = datetime.strptime(work_end_str, fmt)
        diff = (co - we).total_seconds() / 60
        return max(0, int(diff))
    except Exception:
        return 0


# ═══════════════════════════════════════
# ATTENDANCE ENDPOINTS
# ═══════════════════════════════════════

@router.post("/check-in")
async def check_in(req: CheckInRequest, request: Request, user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Self check-in. One check-in per day."""
    settings = await _get_settings()
    if settings.get("is_paused"):
        raise HTTPException(status_code=403, detail="Attendance tracking is temporarily paused by admin.")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    user_id = user.get("id", "")

    existing = await db.attendance_records.find_one(
        {"user_id": user_id, "date": today}, {"_id": 0}
    )
    if existing and existing.get("check_in"):
        raise HTTPException(status_code=409, detail="Already checked in today")

    settings = await _get_settings()
    now_time = datetime.now(timezone.utc).strftime("%H:%M")
    late_minutes = _calc_late_minutes(now_time, settings.get("work_start_time", "09:00"))

    client_ip = request.client.host if request.client else ""

    now_iso = datetime.now(timezone.utc).isoformat()
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "user_name": user.get("name", ""),
        "user_email": user.get("email", ""),
        "user_role": user.get("role", ""),
        "date": today,
        "check_in": now_time,
        "check_out": None,
        "status": "present",
        "work_mode": req.work_mode,
        "hours_worked": 0,
        "late_minutes": late_minutes,
        "overtime_minutes": 0,
        "is_late": late_minutes > settings.get("late_threshold_minutes", 15),
        "ip_address": client_ip,
        "notes": req.notes or "",
        "marked_by": "self",
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    if existing:
        await db.attendance_records.update_one(
            {"user_id": user_id, "date": today},
            {"$set": {k: v for k, v in record.items() if k not in ("id", "created_at")}}
        )
        record["id"] = existing["id"]
    else:
        await db.attendance_records.insert_one(record)

    record.pop("_id", None)
    return record


@router.post("/check-out")
async def check_out(req: CheckOutRequest, user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Self check-out. Must have checked in first."""
    settings = await _get_settings()
    if settings.get("is_paused"):
        raise HTTPException(status_code=403, detail="Attendance tracking is temporarily paused by admin.")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    user_id = user.get("id", "")

    record = await db.attendance_records.find_one(
        {"user_id": user_id, "date": today}, {"_id": 0}
    )
    if not record or not record.get("check_in"):
        raise HTTPException(status_code=400, detail="No check-in found for today")
    if record.get("check_out"):
        raise HTTPException(status_code=409, detail="Already checked out today")

    settings = await _get_settings()
    now_time = datetime.now(timezone.utc).strftime("%H:%M")
    hours = _calc_hours(record["check_in"], now_time)
    overtime = _calc_overtime(now_time, settings.get("work_end_time", "18:00"))

    status = record.get("status", "present")
    if hours < settings.get("half_day_hours", 4.5):
        status = "half_day"

    await db.attendance_records.update_one(
        {"user_id": user_id, "date": today},
        {"$set": {
            "check_out": now_time,
            "hours_worked": hours,
            "overtime_minutes": overtime,
            "status": status,
            "notes": req.notes or record.get("notes", ""),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )

    updated = await db.attendance_records.find_one(
        {"user_id": user_id, "date": today}, {"_id": 0}
    )
    return updated


@router.get("/my")
async def get_my_attendance(
    month: Optional[int] = None,
    year: Optional[int] = None,
    user=Depends(require_role(["admin", "recruiter", "employer"])),
):
    """Get my attendance records for a given month."""
    now = datetime.now(timezone.utc)
    m = month or now.month
    y = year or now.year

    start = f"{y}-{m:02d}-01"
    end_month = m + 1 if m < 12 else 1
    end_year = y if m < 12 else y + 1
    end = f"{end_year}-{end_month:02d}-01"

    records = await db.attendance_records.find(
        {"user_id": user["id"], "date": {"$gte": start, "$lt": end}},
        {"_id": 0}
    ).sort("date", 1).to_list(50)

    # Also get today's status
    today = now.strftime("%Y-%m-%d")
    today_record = next((r for r in records if r["date"] == today), None)

    return {
        "records": records,
        "month": m,
        "year": y,
        "today": today_record,
    }


@router.get("/today")
async def get_today_status(user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Get today's attendance status for the current user."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    record = await db.attendance_records.find_one(
        {"user_id": user["id"], "date": today}, {"_id": 0}
    )
    return {"today": record}


@router.post("/admin/mark")
async def admin_mark_attendance(req: AdminMarkRequest, user=Depends(require_role(["admin"]))):
    """Admin: Mark or override attendance for any user."""
    target = await db.users.find_one({"id": req.user_id}, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    settings = await _get_settings()
    hours = 0
    late_minutes = 0
    overtime = 0
    if req.check_in and req.check_out:
        hours = _calc_hours(req.check_in, req.check_out)
        late_minutes = _calc_late_minutes(req.check_in, settings.get("work_start_time", "09:00"))
        overtime = _calc_overtime(req.check_out, settings.get("work_end_time", "18:00"))

    now_iso = datetime.now(timezone.utc).isoformat()
    record = {
        "user_id": req.user_id,
        "user_name": target.get("name", ""),
        "user_email": target.get("email", ""),
        "user_role": target.get("role", ""),
        "date": req.date,
        "check_in": req.check_in,
        "check_out": req.check_out,
        "status": req.status,
        "work_mode": "office",
        "hours_worked": hours,
        "late_minutes": late_minutes,
        "overtime_minutes": overtime,
        "is_late": late_minutes > settings.get("late_threshold_minutes", 15),
        "ip_address": "",
        "notes": req.notes or "",
        "marked_by": f"admin:{user.get('name', user.get('email', ''))}",
        "updated_at": now_iso,
    }

    existing = await db.attendance_records.find_one(
        {"user_id": req.user_id, "date": req.date}, {"_id": 0}
    )
    if existing:
        await db.attendance_records.update_one(
            {"user_id": req.user_id, "date": req.date},
            {"$set": record}
        )
        record["id"] = existing["id"]
    else:
        record["id"] = str(uuid.uuid4())
        record["created_at"] = now_iso
        await db.attendance_records.insert_one(record)

    record.pop("_id", None)
    return record


@router.get("/team")
async def get_team_attendance(
    month: Optional[int] = None,
    year: Optional[int] = None,
    date_str: Optional[str] = Query(None, alias="date"),
    user=Depends(require_role(["admin", "employer"])),
):
    """Employer: See team attendance. Admin: See all."""
    query = {}

    if date_str:
        query["date"] = date_str
    else:
        now = datetime.now(timezone.utc)
        m = month or now.month
        y = year or now.year
        start = f"{y}-{m:02d}-01"
        end_month = m + 1 if m < 12 else 1
        end_year = y if m < 12 else y + 1
        end = f"{end_year}-{end_month:02d}-01"
        query["date"] = {"$gte": start, "$lt": end}

    if user.get("role") == "employer":
        # Employer sees recruiters in their team + their own
        team_members = await db.users.find(
            {"role": "recruiter"}, {"_id": 0, "id": 1}
        ).to_list(200)
        team_ids = [m["id"] for m in team_members] + [user["id"]]
        query["user_id"] = {"$in": team_ids}

    records = await db.attendance_records.find(query, {"_id": 0}).sort("date", 1).to_list(5000)
    return {"records": records}


@router.get("/all")
async def get_all_attendance(
    month: Optional[int] = None,
    year: Optional[int] = None,
    user_id: Optional[str] = None,
    user=Depends(require_role(["admin"])),
):
    """Admin: Get all attendance records."""
    now = datetime.now(timezone.utc)
    m = month or now.month
    y = year or now.year
    start = f"{y}-{m:02d}-01"
    end_month = m + 1 if m < 12 else 1
    end_year = y if m < 12 else y + 1
    end = f"{end_year}-{end_month:02d}-01"

    query = {"date": {"$gte": start, "$lt": end}}
    if user_id:
        query["user_id"] = user_id

    records = await db.attendance_records.find(query, {"_id": 0}).sort("date", 1).to_list(5000)

    # Get all employer/recruiter users for summary
    users = await db.users.find(
        {"role": {"$in": ["employer", "recruiter"]}, "is_active": True},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    ).to_list(200)

    return {"records": records, "users": users, "month": m, "year": y}


# ── Monthly Report & Export ──

@router.get("/report/monthly")
async def monthly_report(
    month: Optional[int] = None,
    year: Optional[int] = None,
    user=Depends(require_role(["admin"])),
):
    """Admin: Monthly attendance summary for all users."""
    now = datetime.now(timezone.utc)
    m = month or now.month
    y = year or now.year
    start = f"{y}-{m:02d}-01"
    end_month = m + 1 if m < 12 else 1
    end_year = y if m < 12 else y + 1
    end = f"{end_year}-{end_month:02d}-01"

    records = await db.attendance_records.find(
        {"date": {"$gte": start, "$lt": end}}, {"_id": 0}
    ).to_list(10000)

    users = await db.users.find(
        {"role": {"$in": ["employer", "recruiter"]}, "is_active": True},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    ).to_list(200)

    holidays = await db.holidays.find(
        {"date": {"$gte": start, "$lt": end}}, {"_id": 0}
    ).to_list(50)
    holiday_dates = {h["date"] for h in holidays}

    # Build per-user summary
    summaries = []
    for u in users:
        user_records = [r for r in records if r["user_id"] == u["id"]]
        present = sum(1 for r in user_records if r.get("status") == "present")
        absent = sum(1 for r in user_records if r.get("status") == "absent")
        half_days = sum(1 for r in user_records if r.get("status") == "half_day")
        leaves = sum(1 for r in user_records if r.get("status") == "leave")
        wfh = sum(1 for r in user_records if r.get("status") == "wfh" or r.get("work_mode") == "wfh")
        late_count = sum(1 for r in user_records if r.get("is_late"))
        total_hours = round(sum(r.get("hours_worked", 0) for r in user_records), 1)
        total_overtime = sum(r.get("overtime_minutes", 0) for r in user_records)

        summaries.append({
            "user_id": u["id"],
            "name": u["name"],
            "email": u["email"],
            "role": u["role"],
            "present": present,
            "absent": absent,
            "half_days": half_days,
            "leaves": leaves,
            "wfh": wfh,
            "late_count": late_count,
            "total_hours": total_hours,
            "total_overtime_minutes": total_overtime,
        })

    return {
        "month": m,
        "year": y,
        "summaries": summaries,
        "holidays": holidays,
        "holiday_count": len(holidays),
    }


@router.get("/report/export")
async def export_attendance_excel(
    month: Optional[int] = None,
    year: Optional[int] = None,
    user=Depends(require_role(["admin"])),
):
    """Admin: Export monthly attendance as Excel."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    report = await monthly_report(month, year, user)
    m = report["month"]
    y = report["year"]

    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance Report"

    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
    cell_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    # Title
    ws.merge_cells("A1:K1")
    ws["A1"] = f"Attendance Report — {datetime(y, m, 1).strftime('%B %Y')}"
    ws["A1"].font = Font(name="Calibri", bold=True, size=14, color="1F4E79")

    # Headers
    headers = ["#", "Name", "Email", "Role", "Present", "Absent", "Half Days", "Leaves", "WFH", "Late Days", "Total Hours", "Overtime (min)"]
    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=3, column=ci, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = cell_border

    for ri, s in enumerate(report["summaries"], 4):
        row_data = [ri - 3, s["name"], s["email"], s["role"], s["present"], s["absent"], s["half_days"], s["leaves"], s["wfh"], s["late_count"], s["total_hours"], s["total_overtime_minutes"]]
        for ci, val in enumerate(row_data, 1):
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.border = cell_border
            cell.font = Font(name="Calibri", size=10)

    # Auto-width
    from openpyxl.utils import get_column_letter
    for ci, h in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(ci)].width = max(12, len(h) + 4)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="attendance_{y}_{m:02d}.xlsx"'},
    )


# ── Settings ──

@router.get("/settings")
async def get_attendance_settings(user=Depends(require_role(["admin"]))):
    """Get attendance settings."""
    return await _get_settings()


@router.put("/settings")
async def update_attendance_settings(req: AttendanceSettingsUpdate, user=Depends(require_role(["admin"]))):
    """Update attendance settings."""
    updates = {}
    if req.work_start_time is not None:
        updates["work_start_time"] = req.work_start_time
    if req.work_end_time is not None:
        updates["work_end_time"] = req.work_end_time
    if req.late_threshold_minutes is not None:
        updates["late_threshold_minutes"] = req.late_threshold_minutes
    if req.half_day_hours is not None:
        updates["half_day_hours"] = req.half_day_hours
    if req.full_day_hours is not None:
        updates["full_day_hours"] = req.full_day_hours
    if req.reminder_time is not None:
        updates["reminder_time"] = req.reminder_time
    if req.auto_absent_time is not None:
        updates["auto_absent_time"] = req.auto_absent_time
    if req.overtime_threshold_minutes is not None:
        updates["overtime_threshold_minutes"] = req.overtime_threshold_minutes
    if req.grace_window_minutes is not None:
        updates["grace_window_minutes"] = req.grace_window_minutes
    if req.weekend_days is not None:
        updates["weekend_days"] = req.weekend_days
    if req.is_paused is not None:
        updates["is_paused"] = req.is_paused

    await db.attendance_settings.update_one(
        {"id": "global"}, {"$set": updates}, upsert=True
    )
    return await _get_settings()


# ═══════════════════════════════════════
# LEAVE MANAGEMENT ENDPOINTS
# ═══════════════════════════════════════

@router.post("/leave/request")
async def create_leave_request(req: LeaveRequestCreate, user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Submit a leave request."""
    # Validate dates
    try:
        start = datetime.strptime(req.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(req.end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    if end < start:
        raise HTTPException(status_code=400, detail="End date must be after start date")

    days = (end - start).days + 1
    if req.half_day:
        days = 0.5

    # Check leave balance
    year = start.year
    balance = await db.leave_balances.find_one(
        {"user_id": user["id"], "year": year}, {"_id": 0}
    )
    if balance:
        type_key = f"{req.leave_type}_used"
        total_key = f"{req.leave_type}_total"
        used = balance.get(type_key, 0)
        total = balance.get(total_key, 0)
        if total > 0 and (used + days) > total:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient {req.leave_type} leave balance. Available: {total - used}, Requested: {days}"
            )

    now_iso = datetime.now(timezone.utc).isoformat()
    leave_req = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "user_name": user.get("name", ""),
        "user_email": user.get("email", ""),
        "user_role": user.get("role", ""),
        "leave_type": req.leave_type,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "days": days,
        "half_day": req.half_day,
        "reason": req.reason,
        "status": "pending",
        "approved_by": None,
        "approved_at": None,
        "admin_notes": None,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.leave_requests.insert_one(leave_req)
    leave_req.pop("_id", None)
    return leave_req


@router.get("/leave/requests/my")
async def my_leave_requests(
    year: Optional[int] = None,
    user=Depends(require_role(["admin", "recruiter", "employer"])),
):
    """Get my leave requests."""
    y = year or datetime.now(timezone.utc).year
    start = f"{y}-01-01"
    end = f"{y + 1}-01-01"

    requests = await db.leave_requests.find(
        {"user_id": user["id"], "start_date": {"$gte": start, "$lt": end}},
        {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return {"requests": requests}


@router.get("/leave/requests/pending")
async def pending_leave_requests(user=Depends(require_role(["admin"]))):
    """Admin: Get all pending leave requests."""
    requests = await db.leave_requests.find(
        {"status": "pending"}, {"_id": 0}
    ).sort("created_at", 1).to_list(200)
    return {"requests": requests}


@router.get("/leave/requests/all")
async def all_leave_requests(
    year: Optional[int] = None,
    status: Optional[str] = None,
    user=Depends(require_role(["admin"])),
):
    """Admin: Get all leave requests."""
    query = {}
    y = year or datetime.now(timezone.utc).year
    query["start_date"] = {"$gte": f"{y}-01-01", "$lt": f"{y + 1}-01-01"}
    if status:
        query["status"] = status

    requests = await db.leave_requests.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"requests": requests}


@router.put("/leave/requests/{request_id}/approve")
async def approve_leave(request_id: str, req: LeaveActionRequest, user=Depends(require_role(["admin"]))):
    """Admin: Approve a leave request."""
    leave = await db.leave_requests.find_one({"id": request_id}, {"_id": 0})
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if leave["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already {leave['status']}")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.leave_requests.update_one(
        {"id": request_id},
        {"$set": {
            "status": "approved",
            "approved_by": user.get("name", user.get("email", "")),
            "approved_at": now_iso,
            "admin_notes": req.notes,
            "updated_at": now_iso,
        }}
    )

    # Deduct from balance
    year = int(leave["start_date"][:4])
    days = leave.get("days", 1)
    type_key = f"{leave['leave_type']}_used"
    await db.leave_balances.update_one(
        {"user_id": leave["user_id"], "year": year},
        {"$inc": {type_key: days}},
        upsert=True
    )

    # Mark attendance as leave for those dates
    start = datetime.strptime(leave["start_date"], "%Y-%m-%d").date()
    end = datetime.strptime(leave["end_date"], "%Y-%m-%d").date()
    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        existing = await db.attendance_records.find_one(
            {"user_id": leave["user_id"], "date": date_str}
        )
        att_record = {
            "user_id": leave["user_id"],
            "user_name": leave.get("user_name", ""),
            "user_email": leave.get("user_email", ""),
            "user_role": leave.get("user_role", ""),
            "date": date_str,
            "status": "leave",
            "work_mode": "leave",
            "notes": f"{leave['leave_type'].title()} Leave — {leave.get('reason', '')}",
            "marked_by": f"system:leave_approved",
            "updated_at": now_iso,
        }
        if existing:
            await db.attendance_records.update_one(
                {"user_id": leave["user_id"], "date": date_str},
                {"$set": att_record}
            )
        else:
            att_record["id"] = str(uuid.uuid4())
            att_record["check_in"] = None
            att_record["check_out"] = None
            att_record["hours_worked"] = 0
            att_record["late_minutes"] = 0
            att_record["overtime_minutes"] = 0
            att_record["is_late"] = False
            att_record["ip_address"] = ""
            att_record["created_at"] = now_iso
            await db.attendance_records.insert_one(att_record)
        current += timedelta(days=1)

    return {"message": "Leave approved", "status": "approved"}


@router.put("/leave/requests/{request_id}/reject")
async def reject_leave(request_id: str, req: LeaveActionRequest, user=Depends(require_role(["admin"]))):
    """Admin: Reject a leave request."""
    leave = await db.leave_requests.find_one({"id": request_id}, {"_id": 0})
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if leave["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already {leave['status']}")

    await db.leave_requests.update_one(
        {"id": request_id},
        {"$set": {
            "status": "rejected",
            "approved_by": user.get("name", user.get("email", "")),
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "admin_notes": req.notes,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )
    return {"message": "Leave rejected", "status": "rejected"}


# ── Leave Balance ──

@router.get("/leave/balance")
async def get_my_leave_balance(
    year: Optional[int] = None,
    user=Depends(require_role(["admin", "recruiter", "employer"])),
):
    """Get my leave balance."""
    y = year or datetime.now(timezone.utc).year
    balance = await db.leave_balances.find_one(
        {"user_id": user["id"], "year": y}, {"_id": 0}
    )
    if not balance:
        balance = {
            "user_id": user["id"],
            "year": y,
            "casual_leave_total": 0, "casual_leave_used": 0,
            "sick_leave_total": 0, "sick_leave_used": 0,
            "earned_leave_total": 0, "earned_leave_used": 0,
            "comp_off_total": 0, "comp_off_used": 0,
        }
    return balance


@router.get("/leave/balance/{target_user_id}")
async def get_user_leave_balance(
    target_user_id: str,
    year: Optional[int] = None,
    user=Depends(require_role(["admin"])),
):
    """Admin: Get a specific user's leave balance."""
    y = year or datetime.now(timezone.utc).year
    balance = await db.leave_balances.find_one(
        {"user_id": target_user_id, "year": y}, {"_id": 0}
    )
    if not balance:
        target = await db.users.find_one({"id": target_user_id}, {"_id": 0, "name": 1, "email": 1})
        balance = {
            "user_id": target_user_id,
            "user_name": target.get("name", "") if target else "",
            "year": y,
            "casual_leave_total": 0, "casual_leave_used": 0,
            "sick_leave_total": 0, "sick_leave_used": 0,
            "earned_leave_total": 0, "earned_leave_used": 0,
            "comp_off_total": 0, "comp_off_used": 0,
        }
    return balance


@router.put("/leave/admin/balance/{target_user_id}")
async def set_user_leave_balance(
    target_user_id: str,
    req: LeaveBalanceSet,
    year: Optional[int] = None,
    user=Depends(require_role(["admin"])),
):
    """Admin: Set leave balance for a user."""
    target = await db.users.find_one({"id": target_user_id}, {"_id": 0, "id": 1, "name": 1, "email": 1})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    y = year or datetime.now(timezone.utc).year
    updates = {"year": y, "user_id": target_user_id, "user_name": target.get("name", ""), "user_email": target.get("email", "")}
    if req.casual_leave is not None:
        updates["casual_leave_total"] = req.casual_leave
    if req.sick_leave is not None:
        updates["sick_leave_total"] = req.sick_leave
    if req.earned_leave is not None:
        updates["earned_leave_total"] = req.earned_leave
    if req.comp_off is not None:
        updates["comp_off_total"] = req.comp_off

    # Initialize _used fields if not already present
    existing_balance = await db.leave_balances.find_one({"user_id": target_user_id, "year": y})
    if not existing_balance:
        updates.setdefault("casual_leave_used", 0)
        updates.setdefault("sick_leave_used", 0)
        updates.setdefault("earned_leave_used", 0)
        updates.setdefault("comp_off_used", 0)

    await db.leave_balances.update_one(
        {"user_id": target_user_id, "year": y},
        {"$set": updates},
        upsert=True,
    )

    return await get_user_leave_balance(target_user_id, y, user)


@router.get("/leave/admin/balances")
async def get_all_leave_balances(
    year: Optional[int] = None,
    user=Depends(require_role(["admin"])),
):
    """Admin: Get all users' leave balances."""
    y = year or datetime.now(timezone.utc).year
    balances = await db.leave_balances.find({"year": y}, {"_id": 0}).to_list(200)

    users = await db.users.find(
        {"role": {"$in": ["employer", "recruiter"]}, "is_active": True},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    ).to_list(200)

    balance_map = {b["user_id"]: b for b in balances}
    result = []
    for u in users:
        b = balance_map.get(u["id"], {})
        result.append({
            "user_id": u["id"],
            "name": u["name"],
            "email": u["email"],
            "role": u["role"],
            "year": y,
            "casual_leave_total": b.get("casual_leave_total", 0),
            "casual_leave_used": b.get("casual_leave_used", 0),
            "sick_leave_total": b.get("sick_leave_total", 0),
            "sick_leave_used": b.get("sick_leave_used", 0),
            "earned_leave_total": b.get("earned_leave_total", 0),
            "earned_leave_used": b.get("earned_leave_used", 0),
            "comp_off_total": b.get("comp_off_total", 0),
            "comp_off_used": b.get("comp_off_used", 0),
        })

    return {"balances": result, "year": y}


# ═══════════════════════════════════════
# HOLIDAY MANAGEMENT
# ═══════════════════════════════════════

@router.get("/holidays")
async def list_holidays(
    year: Optional[int] = None,
    user=Depends(require_role(["admin", "recruiter", "employer"])),
):
    """List holidays for a year."""
    y = year or datetime.now(timezone.utc).year
    holidays = await db.holidays.find(
        {"date": {"$gte": f"{y}-01-01", "$lt": f"{y + 1}-01-01"}},
        {"_id": 0}
    ).sort("date", 1).to_list(100)
    return {"holidays": holidays, "year": y}


@router.post("/holidays")
async def create_holiday(req: HolidayCreate, user=Depends(require_role(["admin"]))):
    """Admin: Add a holiday."""
    existing = await db.holidays.find_one({"date": req.date}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=409, detail="A holiday already exists on this date")

    now_iso = datetime.now(timezone.utc).isoformat()
    holiday = {
        "id": str(uuid.uuid4()),
        "name": req.name,
        "date": req.date,
        "holiday_type": req.holiday_type,
        "is_optional": req.is_optional,
        "created_by": user.get("id", ""),
        "created_at": now_iso,
    }
    await db.holidays.insert_one(holiday)
    holiday.pop("_id", None)
    return holiday


@router.put("/holidays/{holiday_id}")
async def update_holiday(holiday_id: str, req: HolidayUpdate, user=Depends(require_role(["admin"]))):
    """Admin: Update a holiday."""
    updates = {}
    if req.name is not None:
        updates["name"] = req.name
    if req.date is not None:
        updates["date"] = req.date
    if req.holiday_type is not None:
        updates["holiday_type"] = req.holiday_type
    if req.is_optional is not None:
        updates["is_optional"] = req.is_optional

    result = await db.holidays.update_one({"id": holiday_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Holiday not found")
    return {"message": "Holiday updated"}


@router.delete("/holidays/{holiday_id}")
async def delete_holiday(holiday_id: str, user=Depends(require_role(["admin"]))):
    """Admin: Delete a holiday."""
    result = await db.holidays.delete_one({"id": holiday_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Holiday not found")
    return {"message": "Holiday deleted"}


# ═══════════════════════════════════════
# PAUSE STATUS & PRE-LAUNCH RESET
# ═══════════════════════════════════════

@router.get("/status")
async def get_attendance_status(user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Get attendance system status (paused/active)."""
    settings = await _get_settings()
    return {"is_paused": settings.get("is_paused", False)}


@router.post("/admin/pre-launch-reset")
async def pre_launch_reset(req: PreLaunchResetRequest, user=Depends(require_role(["admin"]))):
    """Admin: Clear all operational data for pre-launch reset. Requires 'RESET DATA' confirmation."""
    if req.confirmation != "RESET DATA":
        raise HTTPException(status_code=400, detail="Invalid confirmation. Type 'RESET DATA' to proceed.")

    now_iso = datetime.now(timezone.utc).isoformat()
    results = {}

    # Attendance & Leave
    r = await db.attendance_records.delete_many({})
    results["attendance_records"] = r.deleted_count
    r = await db.leave_requests.delete_many({})
    results["leave_requests"] = r.deleted_count
    r = await db.leave_balances.delete_many({})
    results["leave_balances"] = r.deleted_count
    r = await db.attendance_health_scores.delete_many({})
    results["attendance_health_scores"] = r.deleted_count

    # Notifications & Automation
    r = await db.notification_events.delete_many({})
    results["notification_events"] = r.deleted_count
    r = await db.notification_delivery_logs.delete_many({})
    results["notification_delivery_logs"] = r.deleted_count
    r = await db.cron_job_logs.delete_many({})
    results["cron_job_logs"] = r.deleted_count

    # Business / Operational Data
    r = await db.jobs.delete_many({})
    results["jobs"] = r.deleted_count
    for coll_name in ["revenue_entries", "invoices", "revenue_analytics"]:
        try:
            r = await db[coll_name].delete_many({})
            results[coll_name] = r.deleted_count
        except Exception:
            results[coll_name] = 0

    # Log the reset action
    await db.system_audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "action": "pre_launch_reset",
        "performed_by": user.get("id", ""),
        "performed_by_name": user.get("name", user.get("email", "")),
        "results": results,
        "timestamp": now_iso,
    })

    return {"message": "Pre-launch reset completed", "deleted": results, "timestamp": now_iso}

