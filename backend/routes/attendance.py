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

# Indian Standard Time (UTC+5:30) — all attendance times must use IST
IST = timezone(timedelta(hours=5, minutes=30))

def _now_ist():
    """Current datetime in IST."""
    return datetime.now(IST)


import math

def _haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance in meters between two lat/lon points using Haversine formula."""
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


router = APIRouter(prefix="/api/attendance", tags=["Attendance"])

# ── Pydantic Models ──

class CheckInRequest(BaseModel):
    notes: Optional[str] = None
    work_mode: str = "office"  # office, wfh, field
    latitude: Optional[float] = None
    longitude: Optional[float] = None

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
    # Geo-fencing
    geo_fencing_enabled: Optional[bool] = None
    geo_fence_radius_meters: Optional[int] = None  # default 500
    offices: Optional[list] = None  # [{name: "HQ", latitude: 28.45, longitude: 77.02}, ...]
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
async def check_in(req: CheckInRequest, request: Request, user=Depends(require_role(["admin", "recruiter", "employer", "accounts"]))):
    """Self check-in. One check-in per day."""
    settings = await _get_settings()
    if settings.get("is_paused"):
        raise HTTPException(status_code=403, detail="Attendance tracking is temporarily paused by admin.")

    # Geo-fencing check (skip for WFH/field modes)
    if settings.get("geo_fencing_enabled") and req.work_mode == "office":
        offices = settings.get("offices", [])
        radius = settings.get("geo_fence_radius_meters", 500)
        if offices:
            if req.latitude is None or req.longitude is None:
                raise HTTPException(status_code=400, detail="Location access is required for office check-in. Please enable GPS.")
            # Check if user is within radius of ANY office
            nearest_distance = float('inf')
            nearest_office = None
            for office in offices:
                o_lat = office.get("latitude")
                o_lon = office.get("longitude")
                if o_lat and o_lon:
                    dist = _haversine_distance(req.latitude, req.longitude, o_lat, o_lon)
                    if dist < nearest_distance:
                        nearest_distance = dist
                        nearest_office = office.get("name", "Office")
            if nearest_distance > radius:
                raise HTTPException(status_code=403, detail=f"You are {int(nearest_distance)}m from nearest office ({nearest_office}). Check-in allowed within {radius}m radius only.")

    today = _now_ist().strftime("%Y-%m-%d")
    user_id = user.get("id", "")

    existing = await db.attendance_records.find_one(
        {"user_id": user_id, "date": today}, {"_id": 0}
    )
    if existing and existing.get("check_in"):
        raise HTTPException(status_code=409, detail="Already checked in today")

    settings = await _get_settings()
    now_time = _now_ist().strftime("%H:%M")
    late_minutes = _calc_late_minutes(now_time, settings.get("work_start_time", "09:00"))

    client_ip = request.client.host if request.client else ""

    now_iso = _now_ist().isoformat()
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
        "latitude": req.latitude,
        "longitude": req.longitude,
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
async def check_out(req: CheckOutRequest, user=Depends(require_role(["admin", "recruiter", "employer", "accounts"]))):
    """Self check-out. Must have checked in first."""
    settings = await _get_settings()
    if settings.get("is_paused"):
        raise HTTPException(status_code=403, detail="Attendance tracking is temporarily paused by admin.")

    today = _now_ist().strftime("%Y-%m-%d")
    user_id = user.get("id", "")

    record = await db.attendance_records.find_one(
        {"user_id": user_id, "date": today}, {"_id": 0}
    )
    if not record or not record.get("check_in"):
        raise HTTPException(status_code=400, detail="No check-in found for today")
    if record.get("check_out"):
        raise HTTPException(status_code=409, detail="Already checked out today")

    settings = await _get_settings()
    now_time = _now_ist().strftime("%H:%M")
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
            "updated_at": _now_ist().isoformat(),
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
    user=Depends(require_role(["admin", "recruiter", "employer", "accounts"])),
):
    """Get my attendance records for a given month."""
    now = datetime.now(IST)
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
async def get_today_status(user=Depends(require_role(["admin", "recruiter", "employer", "accounts"]))):
    """Get today's attendance status for the current user."""
    today = datetime.now(IST).strftime("%Y-%m-%d")
    record = await db.attendance_records.find_one(
        {"user_id": user["id"], "date": today}, {"_id": 0}
    )
    return {"today": record}


@router.post("/admin/mark")
async def admin_mark_attendance(req: AdminMarkRequest, user=Depends(require_role(["admin", "accounts"]))):
    """Admin: Mark or override attendance for any user."""
    target = await db.users.find_one({"id": req.user_id}, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Accounts users cannot mark their own attendance — only admin can
    if user.get("role") == "accounts" and req.user_id == user["id"]:
        raise HTTPException(status_code=403, detail="You cannot manually mark your own attendance. Please use the Check In/Out feature or contact Admin.")

    settings = await _get_settings()
    hours = 0
    late_minutes = 0
    overtime = 0
    if req.check_in and req.check_out:
        hours = _calc_hours(req.check_in, req.check_out)
        late_minutes = _calc_late_minutes(req.check_in, settings.get("work_start_time", "09:00"))
        overtime = _calc_overtime(req.check_out, settings.get("work_end_time", "18:00"))

    now_iso = datetime.now(IST).isoformat()
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
        now = datetime.now(IST)
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
    user=Depends(require_role(["admin", "accounts"])),
):
    """Admin: Get all attendance records."""
    now = datetime.now(IST)
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
        {"role": {"$in": ["employer", "recruiter", "accounts"]}, "is_active": True},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    ).to_list(200)

    return {"records": records, "users": users, "month": m, "year": y}


# ── Monthly Report & Export ──

@router.get("/report/monthly")
async def monthly_report(
    month: Optional[int] = None,
    year: Optional[int] = None,
    user=Depends(require_role(["admin", "accounts"])),
):
    """Admin: Monthly attendance summary for all users."""
    now = datetime.now(IST)
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
        {"role": {"$in": ["employer", "recruiter", "accounts"]}, "is_active": True},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    ).to_list(200)

    holidays = await db.holidays.find(
        {"date": {"$gte": start, "$lt": end}}, {"_id": 0}
    ).to_list(50)
    {h["date"] for h in holidays}

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
    user=Depends(require_role(["admin", "accounts"])),
):
    """Admin: Export monthly attendance as Power BI-style Excel with employee dropdown & daily timestamps."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.formatting.rule import CellIsRule
    import calendar

    report = await monthly_report(month, year, user)
    m = report["month"]
    y = report["year"]
    summaries = report["summaries"]
    holiday_dates = {h["date"] for h in report.get("holidays", [])}
    holiday_names = {h["date"]: h.get("name", "Holiday") for h in report.get("holidays", [])}

    # Fetch all daily attendance records for the month
    start = f"{y}-{m:02d}-01"
    end_month = m + 1 if m < 12 else 1
    end_year = y if m < 12 else y + 1
    end = f"{end_year}-{end_month:02d}-01"

    all_records = await db.attendance_records.find(
        {"date": {"$gte": start, "$lt": end}}, {"_id": 0}
    ).to_list(10000)

    # Build lookup: (user_id, date) -> record
    record_map = {}
    for r in all_records:
        record_map[(r["user_id"], r["date"])] = r

    # Days in month
    num_days = calendar.monthrange(y, m)[1]
    month_name = calendar.month_name[m]
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    # Build employee list
    employees = sorted(
        [(s["user_id"], s["name"], s["email"], s["role"]) for s in summaries],
        key=lambda x: x[1]
    )
    emp_names = [e[1] for e in employees]

    # ── Styles ──
    DARK_BLUE = "1F4E79"
    MED_BLUE = "2E75B6"
    GREEN_BG = "C6EFCE"
    GREEN_FT = "006100"
    RED_BG = "FFC7CE"
    RED_FT = "9C0006"
    ORANGE_BG = "FFEB9C"
    ORANGE_FT = "9C5700"
    BLUE_BG = "BDD7EE"
    BLUE_FT = "1F4E79"
    GRAY_BG = "D9D9D9"
    GRAY_FT = "595959"
    WHITE = "FFFFFF"

    title_font = Font(name="Calibri", bold=True, size=16, color=DARK_BLUE)
    subtitle_font = Font(name="Calibri", bold=True, size=12, color=MED_BLUE)
    header_font = Font(name="Calibri", bold=True, color=WHITE, size=11)
    header_fill = PatternFill(start_color=DARK_BLUE, end_color=DARK_BLUE, fill_type="solid")
    cell_font = Font(name="Calibri", size=10)
    bold_font = Font(name="Calibri", bold=True, size=10)
    border = Border(
        left=Side(style="thin", color="B4C6E7"),
        right=Side(style="thin", color="B4C6E7"),
        top=Side(style="thin", color="B4C6E7"),
        bottom=Side(style="thin", color="B4C6E7"),
    )
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")


    wb = Workbook()

    # ═══════════════════════════════════════
    # SHEET 1: DATA (hidden, for VLOOKUP)
    # ═══════════════════════════════════════
    ws_data = wb.active
    ws_data.title = "Data"

    data_headers = ["Key", "Employee", "Date", "Day", "Check-In (IST)", "Check-Out (IST)", "Hours", "Status", "Late", "Notes"]
    for ci, h in enumerate(data_headers, 1):
        cell = ws_data.cell(row=1, column=ci, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border

    data_row = 2
    for uid, name, email, role in employees:
        for day in range(1, num_days + 1):
            date_str = f"{y}-{m:02d}-{day:02d}"
            dt = date(y, m, day)
            day_name = day_names[dt.weekday()]
            rec = record_map.get((uid, date_str))
            is_holiday = date_str in holiday_dates

            if rec:
                check_in = rec.get("check_in", "")
                check_out = rec.get("check_out", "")
                hours = rec.get("hours_worked", 0)
                status = rec.get("status", "present")
                is_late = "Yes" if rec.get("is_late") else "No"
                notes = rec.get("notes", "")
            elif is_holiday:
                check_in = ""
                check_out = ""
                hours = 0
                status = "holiday"
                is_late = ""
                notes = holiday_names.get(date_str, "Holiday")
            else:
                check_in = ""
                check_out = ""
                hours = 0
                status = ""
                is_late = ""
                notes = ""

            # Composite lookup key
            lookup_key = f"{name}|{date_str}"
            row_vals = [lookup_key, name, date_str, day_name, check_in, check_out, hours, status, is_late, notes]
            for ci, val in enumerate(row_vals, 1):
                cell = ws_data.cell(row=data_row, column=ci, value=val)
                cell.font = cell_font
                cell.border = border
            data_row += 1

    # Auto-width for Data sheet
    for ci in range(1, len(data_headers) + 1):
        ws_data.column_dimensions[get_column_letter(ci)].width = 18

    # ═══════════════════════════════════════
    # SHEET 2: DASHBOARD (Interactive)
    # ═══════════════════════════════════════
    ws_dash = wb.create_sheet("Dashboard", 0)  # Make it first visible

    # Title
    ws_dash.merge_cells("A1:G1")
    ws_dash["A1"] = f"Attendance Dashboard — {month_name} {y}"
    ws_dash["A1"].font = title_font
    ws_dash["A1"].alignment = left_align

    # Employee selector
    ws_dash["A3"] = "Select Employee:"
    ws_dash["A3"].font = subtitle_font
    ws_dash.merge_cells("B3:D3")
    emp_cell = ws_dash["B3"]
    emp_cell.font = Font(name="Calibri", bold=True, size=12)
    emp_cell.fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
    emp_cell.border = Border(
        left=Side(style="medium", color=DARK_BLUE),
        right=Side(style="medium", color=DARK_BLUE),
        top=Side(style="medium", color=DARK_BLUE),
        bottom=Side(style="medium", color=DARK_BLUE),
    )
    emp_cell.alignment = left_align

    # Set default employee name
    if emp_names:
        emp_cell.value = emp_names[0]

    # Data validation dropdown
    emp_list_str = ",".join(emp_names) if len(",".join(emp_names)) <= 255 else None
    if emp_list_str:
        dv = DataValidation(type="list", formula1=f'"{emp_list_str}"', allow_blank=False)
        dv.error = "Please select an employee from the list"
        dv.errorTitle = "Invalid Employee"
        dv.prompt = "Select an employee"
        dv.promptTitle = "Employee Name"
        ws_dash.add_data_validation(dv)
        dv.add("B3")
    else:
        # Too many employees for inline list — use named range from Data sheet
        # Create a unique list of employee names in a helper column
        emp_col = len(data_headers) + 2  # Column after data
        for i, name in enumerate(emp_names):
            ws_data.cell(row=i + 1, column=emp_col, value=name)
        emp_range = f"Data!${get_column_letter(emp_col)}$1:${get_column_letter(emp_col)}${len(emp_names)}"
        dv = DataValidation(type="list", formula1=emp_range, allow_blank=False)
        ws_dash.add_data_validation(dv)
        dv.add("B3")

    # Calendar Headers
    cal_headers = ["Date", "Day", "Check-In (IST)", "Check-Out (IST)", "Hours Worked", "Status", "Late"]
    for ci, h in enumerate(cal_headers, 1):
        cell = ws_dash.cell(row=5, column=ci, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = center_align

    # Calendar rows with VLOOKUP formulas
    data_row - 1
    for day in range(1, num_days + 1):
        row = day + 5
        date_str = f"{y}-{m:02d}-{day:02d}"
        dt = date(y, m, day)
        day_name = day_names[dt.weekday()]
        is_weekend = dt.weekday() in (5, 6)  # Sat, Sun

        # Date column — static text
        date_cell = ws_dash.cell(row=row, column=1, value=f"{day:02d}-{month_name[:3]}-{y}")
        date_cell.font = bold_font
        date_cell.border = border
        date_cell.alignment = center_align

        # Day column — static text
        day_cell = ws_dash.cell(row=row, column=2, value=day_name)
        day_cell.font = bold_font
        day_cell.border = border
        day_cell.alignment = center_align

        # VLOOKUP key: $B$3&"|"&"YYYY-MM-DD"
        vlookup_key = f'$B$3&"|"&"{date_str}"'

        # Check-In: =IFERROR(VLOOKUP(key, Data!A:J, 5, FALSE), "")
        for col_idx, data_col_num in [(3, 5), (4, 6), (5, 7), (6, 8), (7, 9)]:
            formula = f'=IFERROR(VLOOKUP({vlookup_key},Data!$A:$J,{data_col_num},FALSE),"")'
            cell = ws_dash.cell(row=row, column=col_idx)
            cell.value = formula
            cell.font = cell_font
            cell.border = border
            cell.alignment = center_align

        # Weekend row shading
        if is_weekend:
            weekend_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
            for ci in range(1, 8):
                ws_dash.cell(row=row, column=ci).fill = weekend_fill

    # Summary stats row
    stats_row = num_days + 7
    ws_dash.cell(row=stats_row, column=1, value="Monthly Summary").font = subtitle_font
    stat_labels = ["Present", "Absent", "Half Days", "Leave", "WFH", "Late Days"]
    for ci, label in enumerate(stat_labels, 1):
        cell = ws_dash.cell(row=stats_row + 1, column=ci, value=label)
        cell.font = header_font
        cell.fill = PatternFill(start_color=MED_BLUE, end_color=MED_BLUE, fill_type="solid")
        cell.border = border
        cell.alignment = center_align

    # COUNTIF formulas for stats
    status_range = f"$F$6:$F${num_days + 5}"
    late_range = f"$G$6:$G${num_days + 5}"
    countif_map = [
        (1, f'=COUNTIF({status_range},"present")+COUNTIF({status_range},"Present")'),
        (2, f'=COUNTIF({status_range},"absent")+COUNTIF({status_range},"Absent")'),
        (3, f'=COUNTIF({status_range},"half_day")+COUNTIF({status_range},"Half Day")'),
        (4, f'=COUNTIF({status_range},"leave")+COUNTIF({status_range},"Leave")'),
        (5, f'=COUNTIF({status_range},"wfh")+COUNTIF({status_range},"WFH")'),
        (6, f'=COUNTIF({late_range},"Yes")'),
    ]
    for ci, formula in countif_map:
        cell = ws_dash.cell(row=stats_row + 2, column=ci)
        cell.value = formula
        cell.font = Font(name="Calibri", bold=True, size=14, color=DARK_BLUE)
        cell.border = border
        cell.alignment = center_align

    # Conditional formatting for Status column (F6:F{end})
    status_col_range = f"F6:F{num_days + 5}"
    ws_dash.conditional_formatting.add(status_col_range,
        CellIsRule(operator="equal", formula=['"present"'], fill=PatternFill(bgColor=GREEN_BG), font=Font(color=GREEN_FT, bold=True)))
    ws_dash.conditional_formatting.add(status_col_range,
        CellIsRule(operator="equal", formula=['"absent"'], fill=PatternFill(bgColor=RED_BG), font=Font(color=RED_FT, bold=True)))
    ws_dash.conditional_formatting.add(status_col_range,
        CellIsRule(operator="equal", formula=['"half_day"'], fill=PatternFill(bgColor=ORANGE_BG), font=Font(color=ORANGE_FT, bold=True)))
    ws_dash.conditional_formatting.add(status_col_range,
        CellIsRule(operator="equal", formula=['"leave"'], fill=PatternFill(bgColor=BLUE_BG), font=Font(color=BLUE_FT, bold=True)))
    ws_dash.conditional_formatting.add(status_col_range,
        CellIsRule(operator="equal", formula=['"wfh"'], fill=PatternFill(bgColor="E2EFDA"), font=Font(color="375623", bold=True)))
    ws_dash.conditional_formatting.add(status_col_range,
        CellIsRule(operator="equal", formula=['"holiday"'], fill=PatternFill(bgColor=GRAY_BG), font=Font(color=GRAY_FT, bold=True)))

    # Late column conditional formatting
    late_col_range = f"G6:G{num_days + 5}"
    ws_dash.conditional_formatting.add(late_col_range,
        CellIsRule(operator="equal", formula=['"Yes"'], fill=PatternFill(bgColor=RED_BG), font=Font(color=RED_FT, bold=True)))

    # Column widths for Dashboard
    dash_widths = [14, 8, 16, 16, 14, 14, 10]
    for ci, w in enumerate(dash_widths, 1):
        ws_dash.column_dimensions[get_column_letter(ci)].width = w

    # Legend
    legend_row = stats_row + 4
    ws_dash.cell(row=legend_row, column=1, value="Legend:").font = subtitle_font
    legend_items = [
        ("Present", GREEN_BG, GREEN_FT),
        ("Absent", RED_BG, RED_FT),
        ("Half Day", ORANGE_BG, ORANGE_FT),
        ("Leave", BLUE_BG, BLUE_FT),
        ("WFH", "E2EFDA", "375623"),
        ("Holiday", GRAY_BG, GRAY_FT),
    ]
    for ci, (label, bg, ft) in enumerate(legend_items, 2):
        cell = ws_dash.cell(row=legend_row, column=ci, value=label)
        cell.fill = PatternFill(start_color=bg, end_color=bg, fill_type="solid")
        cell.font = Font(name="Calibri", bold=True, size=10, color=ft)
        cell.border = border
        cell.alignment = center_align

    # Instruction text
    ws_dash.cell(row=legend_row + 2, column=1, value="How to use: Click on cell B3 and select an employee from the dropdown. The calendar will auto-populate.").font = Font(name="Calibri", italic=True, size=10, color="666666")

    # ═══════════════════════════════════════
    # SHEET 3: SUMMARY (existing overview)
    # ═══════════════════════════════════════
    ws_sum = wb.create_sheet("Summary")
    ws_sum.merge_cells("A1:L1")
    ws_sum["A1"] = f"Attendance Summary — {month_name} {y}"
    ws_sum["A1"].font = title_font

    sum_headers = ["#", "Name", "Email", "Role", "Present", "Absent", "Half Days", "Leaves", "WFH", "Late Days", "Total Hours", "Overtime (min)"]
    for ci, h in enumerate(sum_headers, 1):
        cell = ws_sum.cell(row=3, column=ci, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border

    for ri, s in enumerate(summaries, 4):
        row_data = [ri - 3, s["name"], s["email"], s["role"], s["present"], s["absent"], s["half_days"], s["leaves"], s["wfh"], s["late_count"], s["total_hours"], s["total_overtime_minutes"]]
        for ci, val in enumerate(row_data, 1):
            cell = ws_sum.cell(row=ri, column=ci, value=val)
            cell.border = border
            cell.font = cell_font

    for ci, h in enumerate(sum_headers, 1):
        ws_sum.column_dimensions[get_column_letter(ci)].width = max(12, len(h) + 4)

    # Hide Data sheet (it's just for VLOOKUP)
    ws_data.sheet_state = "hidden"

    # Set Dashboard as the active sheet
    wb.active = wb.sheetnames.index("Dashboard")

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
async def get_attendance_settings(user=Depends(require_role(["admin", "accounts"]))):
    """Get attendance settings."""
    return await _get_settings()


@router.put("/settings")
async def update_attendance_settings(req: AttendanceSettingsUpdate, user=Depends(require_role(["admin", "accounts"]))):
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
    if req.geo_fencing_enabled is not None:
        updates["geo_fencing_enabled"] = req.geo_fencing_enabled
    if req.offices is not None:
        updates["offices"] = req.offices
    if req.geo_fence_radius_meters is not None:
        updates["geo_fence_radius_meters"] = req.geo_fence_radius_meters

    await db.attendance_settings.update_one(
        {"id": "global"}, {"$set": updates}, upsert=True
    )
    return await _get_settings()


# ═══════════════════════════════════════
# LEAVE MANAGEMENT ENDPOINTS
# ═══════════════════════════════════════

@router.post("/leave/request")
async def create_leave_request(req: LeaveRequestCreate, user=Depends(require_role(["admin", "recruiter", "employer", "accounts"]))):
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

    now_iso = datetime.now(IST).isoformat()
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
    user=Depends(require_role(["admin", "recruiter", "employer", "accounts"])),
):
    """Get my leave requests."""
    y = year or datetime.now(IST).year
    start = f"{y}-01-01"
    end = f"{y + 1}-01-01"

    requests = await db.leave_requests.find(
        {"user_id": user["id"], "start_date": {"$gte": start, "$lt": end}},
        {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return {"requests": requests}


@router.get("/leave/requests/pending")
async def pending_leave_requests(user=Depends(require_role(["admin", "accounts"]))):
    """Admin: Get all pending leave requests."""
    requests = await db.leave_requests.find(
        {"status": "pending"}, {"_id": 0}
    ).sort("created_at", 1).to_list(200)
    return {"requests": requests}


@router.get("/leave/requests/all")
async def all_leave_requests(
    year: Optional[int] = None,
    status: Optional[str] = None,
    user=Depends(require_role(["admin", "accounts"])),
):
    """Admin: Get all leave requests."""
    query = {}
    y = year or datetime.now(IST).year
    query["start_date"] = {"$gte": f"{y}-01-01", "$lt": f"{y + 1}-01-01"}
    if status:
        query["status"] = status

    requests = await db.leave_requests.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"requests": requests}


@router.put("/leave/requests/{request_id}/approve")
async def approve_leave(request_id: str, req: LeaveActionRequest, user=Depends(require_role(["admin", "accounts"]))):
    """Admin: Approve a leave request."""
    leave = await db.leave_requests.find_one({"id": request_id}, {"_id": 0})
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if leave["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already {leave['status']}")

    now_iso = datetime.now(IST).isoformat()
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
            "marked_by": "system:leave_approved",
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
async def reject_leave(request_id: str, req: LeaveActionRequest, user=Depends(require_role(["admin", "accounts"]))):
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
            "approved_at": datetime.now(IST).isoformat(),
            "admin_notes": req.notes,
            "updated_at": datetime.now(IST).isoformat(),
        }}
    )
    return {"message": "Leave rejected", "status": "rejected"}


# ── Leave Balance ──

@router.get("/leave/balance")
async def get_my_leave_balance(
    year: Optional[int] = None,
    user=Depends(require_role(["admin", "recruiter", "employer", "accounts"])),
):
    """Get my leave balance."""
    y = year or datetime.now(IST).year
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
    user=Depends(require_role(["admin", "accounts"])),
):
    """Admin: Get a specific user's leave balance."""
    y = year or datetime.now(IST).year
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
    user=Depends(require_role(["admin", "accounts"])),
):
    """Admin: Set leave balance for a user."""
    target = await db.users.find_one({"id": target_user_id}, {"_id": 0, "id": 1, "name": 1, "email": 1})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    y = year or datetime.now(IST).year
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
    user=Depends(require_role(["admin", "accounts"])),
):
    """Admin: Get all users' leave balances."""
    y = year or datetime.now(IST).year
    balances = await db.leave_balances.find({"year": y}, {"_id": 0}).to_list(200)

    users = await db.users.find(
        {"role": {"$in": ["employer", "recruiter", "accounts"]}, "is_active": True},
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
    user=Depends(require_role(["admin", "recruiter", "employer", "accounts"])),
):
    """List holidays for a year."""
    y = year or datetime.now(IST).year
    holidays = await db.holidays.find(
        {"date": {"$gte": f"{y}-01-01", "$lt": f"{y + 1}-01-01"}},
        {"_id": 0}
    ).sort("date", 1).to_list(100)
    return {"holidays": holidays, "year": y}


@router.post("/holidays")
async def create_holiday(req: HolidayCreate, user=Depends(require_role(["admin", "accounts"]))):
    """Admin: Add a holiday."""
    existing = await db.holidays.find_one({"date": req.date}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=409, detail="A holiday already exists on this date")

    now_iso = datetime.now(IST).isoformat()
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
async def update_holiday(holiday_id: str, req: HolidayUpdate, user=Depends(require_role(["admin", "accounts"]))):
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
async def delete_holiday(holiday_id: str, user=Depends(require_role(["admin", "accounts"]))):
    """Admin: Delete a holiday."""
    result = await db.holidays.delete_one({"id": holiday_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Holiday not found")
    return {"message": "Holiday deleted"}


# ═══════════════════════════════════════
# PAUSE STATUS & PRE-LAUNCH RESET
# ═══════════════════════════════════════

@router.get("/status")
async def get_attendance_status(user=Depends(require_role(["admin", "recruiter", "employer", "accounts"]))):
    """Get attendance system status (paused/active)."""
    settings = await _get_settings()
    return {"is_paused": settings.get("is_paused", False)}


@router.post("/admin/pre-launch-reset")
async def pre_launch_reset(req: PreLaunchResetRequest, user=Depends(require_role(["admin", "accounts"]))):
    """Admin: Clear all operational data for pre-launch reset. Requires 'RESET DATA' confirmation."""
    if req.confirmation != "RESET DATA":
        raise HTTPException(status_code=400, detail="Invalid confirmation. Type 'RESET DATA' to proceed.")

    now_iso = datetime.now(IST).isoformat()
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



# ═══════════════════════════════════════
# EMPLOYER TEAM ATTENDANCE (Read-only)
# ═══════════════════════════════════════

async def _get_employer_team_user_ids(employer_user: dict) -> list:
    """Get user IDs of recruiters in the same team as the employer."""
    user_id = employer_user["id"]

    # Find the employer's active team
    team = await db.teams.find_one(
        {"employer_id": user_id, "status": "active"},
        {"_id": 0, "recruiter_ids": 1, "employer_id": 1}
    )

    team_user_ids = set()
    team_user_ids.add(user_id)  # Always include the employer

    if team:
        for rid in (team.get("recruiter_ids") or []):
            team_user_ids.add(rid)

    return list(team_user_ids)


@router.get("/team/all")
async def get_employer_team_attendance(
    month: Optional[int] = None,
    year: Optional[int] = None,
    user=Depends(require_role(["employer"])),
):
    """Employer: Get attendance records for their team members only."""
    team_user_ids = await _get_employer_team_user_ids(user)

    now = datetime.now(IST)
    m = month or now.month
    y = year or now.year
    start = f"{y}-{m:02d}-01"
    end_month = m + 1 if m < 12 else 1
    end_year = y if m < 12 else y + 1
    end = f"{end_year}-{end_month:02d}-01"

    records = await db.attendance_records.find(
        {"date": {"$gte": start, "$lt": end}, "user_id": {"$in": team_user_ids}},
        {"_id": 0}
    ).sort("date", 1).to_list(5000)

    users = await db.users.find(
        {"id": {"$in": team_user_ids}, "is_active": True},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    ).to_list(200)

    return {"records": records, "users": users, "month": m, "year": y}


@router.get("/team/report/monthly")
async def employer_team_monthly_report(
    month: Optional[int] = None,
    year: Optional[int] = None,
    user=Depends(require_role(["employer"])),
):
    """Employer: Monthly attendance summary for their team members only."""
    team_user_ids = await _get_employer_team_user_ids(user)

    now = datetime.now(IST)
    m = month or now.month
    y = year or now.year
    start = f"{y}-{m:02d}-01"
    end_month = m + 1 if m < 12 else 1
    end_year = y if m < 12 else y + 1
    end = f"{end_year}-{end_month:02d}-01"

    records = await db.attendance_records.find(
        {"date": {"$gte": start, "$lt": end}, "user_id": {"$in": team_user_ids}},
        {"_id": 0}
    ).to_list(10000)

    users = await db.users.find(
        {"id": {"$in": team_user_ids}, "is_active": True},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    ).to_list(200)

    holidays = await db.holidays.find(
        {"date": {"$gte": start, "$lt": end}}, {"_id": 0}
    ).to_list(50)

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


@router.get("/team/today")
async def get_employer_team_today(user=Depends(require_role(["employer"]))):
    """Employer: Today's attendance snapshot for their team."""
    team_user_ids = await _get_employer_team_user_ids(user)
    today_str = _now_ist().strftime("%Y-%m-%d")

    records = await db.attendance_records.find(
        {"date": today_str, "user_id": {"$in": team_user_ids}},
        {"_id": 0}
    ).to_list(200)

    users = await db.users.find(
        {"id": {"$in": team_user_ids}, "is_active": True},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    ).to_list(200)

    record_map = {r["user_id"]: r for r in records}

    member_statuses = []
    present = absent = late = on_leave = wfh = not_checked_in = 0
    for u in users:
        rec = record_map.get(u["id"])
        if rec:
            status = rec.get("status", "unknown")
            member_statuses.append({
                "user_id": u["id"],
                "name": u["name"],
                "email": u["email"],
                "role": u["role"],
                "status": status,
                "check_in": rec.get("check_in"),
                "check_out": rec.get("check_out"),
                "hours_worked": rec.get("hours_worked", 0),
                "is_late": rec.get("is_late", False),
                "work_mode": rec.get("work_mode", "office"),
            })
            if status == "present":
                present += 1
                if rec.get("is_late"):
                    late += 1
            elif status == "absent":
                absent += 1
            elif status == "leave":
                on_leave += 1
            elif status == "wfh":
                wfh += 1
            elif status == "half_day":
                present += 1
        else:
            member_statuses.append({
                "user_id": u["id"],
                "name": u["name"],
                "email": u["email"],
                "role": u["role"],
                "status": "not_checked_in",
                "check_in": None,
                "check_out": None,
                "hours_worked": 0,
                "is_late": False,
                "work_mode": None,
            })
            not_checked_in += 1

    # Check if today is a holiday
    holiday = await db.holidays.find_one({"date": today_str}, {"_id": 0})

    return {
        "date": today_str,
        "is_holiday": holiday is not None,
        "holiday_name": holiday.get("name") if holiday else None,
        "total_team": len(users),
        "present": present,
        "absent": absent,
        "late": late,
        "on_leave": on_leave,
        "wfh": wfh,
        "not_checked_in": not_checked_in,
        "members": member_statuses,
    }
