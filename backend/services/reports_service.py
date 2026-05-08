"""
Automated Daily & Weekly Recruiter Performance Reports.

Delivery:
- Daily: every evening at 18:30 IST (13:00 UTC). Window = previous day 18:30 IST → today 18:30 IST.
- Weekly: every Monday at 09:00 IST (03:30 UTC). Window = previous Mon 00:00 IST → Sun 23:59:59 IST.

Each report is:
- Scoped per team → aggregated across all recruiters in that team
- Emailed to the team's employer (team_leader)
- Delivered as Excel (.xlsx) attachment

Key Metrics:
- Profile Captured   = new doc in candidate_bank in window (captured_by = recruiter)
- Profile Shared     = pipeline_events transition new_stage='submitted_to_client' (changed_by = recruiter)
- Shortlisted        = new_stage='shortlisted'
- Interviewed        = new_stage='interview'
- Selected           = new_stage='hired'
- Offered            = new_stage='offered'
- Joined             = new_stage='joined'
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from services.email_service import send_email

logger = logging.getLogger(__name__)

IST_OFFSET = timedelta(hours=5, minutes=30)
DAILY_CUTOFF_HOUR_IST = 18  # 6 PM
DAILY_CUTOFF_MIN_IST = 30  # :30


# ─────────────────────────────────────────────────────────────────────────────
# Time helpers
# ─────────────────────────────────────────────────────────────────────────────
def _ist_now() -> datetime:
    return datetime.now(timezone.utc) + IST_OFFSET


def _ist_to_utc_iso(ist_naive: datetime) -> str:
    """Convert a naive IST datetime -> UTC ISO string (as stored in Mongo)."""
    return (ist_naive - IST_OFFSET).replace(tzinfo=timezone.utc).isoformat()


def compute_daily_window(today_ist: Optional[datetime] = None) -> Tuple[str, str, str]:
    """Returns (start_iso_utc, end_iso_utc, label_for_report).
    Daily window = previous day 18:30 IST → today 18:30 IST.
    """
    if today_ist is None:
        today_ist = _ist_now()
    end_ist = today_ist.replace(hour=DAILY_CUTOFF_HOUR_IST, minute=DAILY_CUTOFF_MIN_IST, second=0, microsecond=0)
    start_ist = end_ist - timedelta(days=1)
    label = end_ist.strftime("%a, %d %b %Y")
    return _ist_to_utc_iso(start_ist), _ist_to_utc_iso(end_ist), label


def compute_weekly_window(today_ist: Optional[datetime] = None) -> Tuple[str, str, str]:
    """Returns (start_iso_utc, end_iso_utc, label_for_report).
    Weekly window = last Monday 00:00 IST → last Sunday 23:59:59 IST (previous calendar week).
    Triggered on Monday 09:00 IST.
    """
    if today_ist is None:
        today_ist = _ist_now()
    # today_ist is a Monday (when triggered); weekday()==0. Go back to previous Monday.
    days_since_monday = today_ist.weekday()
    this_monday = today_ist.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
    last_monday = this_monday - timedelta(days=7)
    last_sunday_end = this_monday - timedelta(microseconds=1)
    label = f"{last_monday.strftime('%d %b')} – {last_sunday_end.strftime('%d %b %Y')}"
    return _ist_to_utc_iso(last_monday), _ist_to_utc_iso(last_sunday_end), label


# ─────────────────────────────────────────────────────────────────────────────
# Data aggregation
# ─────────────────────────────────────────────────────────────────────────────
STAGE_KEY_MAP = {
    "submitted_to_client": "shared",
    "shortlisted": "shortlisted",
    "interview": "interviewed",
    "offered": "offered",
    "hired": "selected",
    "joined": "joined",
}


async def _get_teams(db) -> List[Dict]:
    """Return active teams with employer/recruiter details resolved."""
    teams = await db.teams.find({"status": "active"}, {"_id": 0}).to_list(length=None)
    return teams


async def _recruiter_lookup(db, recruiter_ids: List[str]) -> Dict[str, Dict]:
    """id -> user doc (id, name, email)."""
    if not recruiter_ids:
        return {}
    rows = await db.users.find(
        {"id": {"$in": recruiter_ids}},
        {"_id": 0, "id": 1, "name": 1, "email": 1},
    ).to_list(length=None)
    return {r["id"]: r for r in rows}


async def _get_employer(db, employer_id: str) -> Optional[Dict]:
    return await db.users.find_one({"id": employer_id}, {"_id": 0, "id": 1, "name": 1, "email": 1})


async def _job_lookup(db, job_ids: List[str]) -> Dict[str, Dict]:
    """job_id -> {title, client_name, company_id}."""
    if not job_ids:
        return {}
    jobs = await db.jobs.find(
        {"id": {"$in": job_ids}},
        {"_id": 0, "id": 1, "title": 1, "client_name": 1, "company_id": 1},
    ).to_list(length=None)
    # also fetch company names if company_id is set
    company_ids = [j.get("company_id") for j in jobs if j.get("company_id")]
    comp_map: Dict[str, str] = {}
    if company_ids:
        comps = await db.companies.find({"id": {"$in": company_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(length=None)
        comp_map = {c["id"]: c.get("name", "") for c in comps}
    result = {}
    for j in jobs:
        result[j["id"]] = {
            "title": j.get("title") or "(untitled)",
            "client_name": j.get("client_name") or comp_map.get(j.get("company_id", ""), "—"),
        }
    return result


async def aggregate_daily(
    db,
    recruiter_ids: List[str],
    start_iso: str,
    end_iso: str,
) -> List[Dict]:
    """Per-recruiter per-mandate metrics for daily report.
    Returns list of rows: [{recruiter_id, recruiter_name, mandate_id, mandate_title, client_name, captured, shared}]
    """
    # 1. Captures grouped by (recruiter_id, mandate_id)
    # Use $or to match either captured_by (newer) or created_by (legacy / bulk imports)
    cap_pipeline = [
        {"$match": {
            "$and": [
                {"created_at": {"$gte": start_iso, "$lt": end_iso}},
                {"$or": [
                    {"captured_by": {"$in": recruiter_ids}},
                    {"created_by": {"$in": recruiter_ids}},
                ]},
            ],
        }},
        {"$addFields": {
            "_recruiter_id": {"$ifNull": ["$captured_by", "$created_by"]},
        }},
        {"$unwind": {"path": "$linked_mandates", "preserveNullAndEmptyArrays": True}},
        {"$group": {
            "_id": {"recruiter_id": "$_recruiter_id", "mandate_id": "$linked_mandates"},
            "count": {"$sum": 1},
        }},
    ]
    capture_rows = await db.candidate_bank.aggregate(cap_pipeline).to_list(length=None)

    # 2. Pipeline events (profile shared) grouped by (recruiter_id, mandate_id)
    # Collection: tracker_events; field: user_id (not changed_by); field: mandate_id (not job_id)
    ev_pipeline = [
        {"$match": {
            "user_id": {"$in": recruiter_ids},
            "new_stage": "submitted_to_client",
            "timestamp": {"$gte": start_iso, "$lt": end_iso},
        }},
        {"$group": {
            "_id": {"recruiter_id": "$user_id", "mandate_id": "$mandate_id"},
            "count": {"$sum": 1},
        }},
    ]
    share_rows = await db.tracker_events.aggregate(ev_pipeline).to_list(length=None)

    # Merge into a cell-matrix
    matrix: Dict[Tuple[str, str], Dict] = {}
    for r in capture_rows:
        key = (r["_id"].get("recruiter_id") or "", r["_id"].get("mandate_id") or "")
        matrix.setdefault(key, {"captured": 0, "shared": 0})
        matrix[key]["captured"] = r["count"]
    for r in share_rows:
        key = (r["_id"].get("recruiter_id") or "", r["_id"].get("mandate_id") or "")
        matrix.setdefault(key, {"captured": 0, "shared": 0})
        matrix[key]["shared"] = r["count"]

    # Enrich with names
    all_job_ids = list({k[1] for k in matrix.keys() if k[1]})
    job_map = await _job_lookup(db, all_job_ids)
    rec_map = await _recruiter_lookup(db, recruiter_ids)

    rows = []
    for (rec_id, mand_id), counts in matrix.items():
        rec = rec_map.get(rec_id, {})
        mand = job_map.get(mand_id, {})
        rows.append({
            "recruiter_id": rec_id,
            "recruiter_name": rec.get("name") or "(unknown)",
            "recruiter_email": rec.get("email") or "",
            "mandate_id": mand_id or "(no mandate)",
            "mandate_title": mand.get("title") or ("(no mandate)" if not mand_id else mand_id),
            "client_name": mand.get("client_name") or "—",
            "captured": counts["captured"],
            "shared": counts["shared"],
        })
    # Stable sort: recruiter name, then client, then mandate
    rows.sort(key=lambda r: (r["recruiter_name"].lower(), r["client_name"].lower(), r["mandate_title"].lower()))
    return rows


async def aggregate_weekly(
    db,
    recruiter_ids: List[str],
    start_iso: str,
    end_iso: str,
) -> Dict[str, Dict]:
    """Per-recruiter weekly aggregates.
    Returns { recruiter_id: { name, email, mandates: [{title, client}], captured, shared, shortlisted, interviewed, offered, selected, joined } }
    """
    rec_map = await _recruiter_lookup(db, recruiter_ids)
    out: Dict[str, Dict] = {}
    for rid, u in rec_map.items():
        out[rid] = {
            "name": u.get("name") or "(unknown)",
            "email": u.get("email") or "",
            "mandate_ids": set(),
            "captured": 0,
            "shared": 0,
            "shortlisted": 0,
            "interviewed": 0,
            "offered": 0,
            "selected": 0,
            "joined": 0,
        }

    # 1. Captures (profiles captured this week AND mandates captured on)
    # Use $or to match either captured_by or created_by (legacy)
    cap_pipeline = [
        {"$match": {
            "$and": [
                {"created_at": {"$gte": start_iso, "$lt": end_iso}},
                {"$or": [
                    {"captured_by": {"$in": recruiter_ids}},
                    {"created_by": {"$in": recruiter_ids}},
                ]},
            ],
        }},
        {"$addFields": {
            "_recruiter_id": {"$ifNull": ["$captured_by", "$created_by"]},
        }},
        {"$project": {"_recruiter_id": 1, "linked_mandates": 1, "_id": 0}},
    ]
    async for doc in db.candidate_bank.aggregate(cap_pipeline):
        rid = doc.get("_recruiter_id")
        if rid not in out:
            continue
        out[rid]["captured"] += 1
        for mid in doc.get("linked_mandates") or []:
            out[rid]["mandate_ids"].add(mid)

    # 2. Stage-transition metrics (include any transition in the week, regardless of mandate age)
    # Collection: tracker_events; field: user_id (not changed_by); field: mandate_id (not job_id)
    ev_pipeline = [
        {"$match": {
            "user_id": {"$in": recruiter_ids},
            "new_stage": {"$in": list(STAGE_KEY_MAP.keys())},
            "timestamp": {"$gte": start_iso, "$lt": end_iso},
        }},
        {"$project": {"user_id": 1, "new_stage": 1, "mandate_id": 1, "_id": 0}},
    ]
    async for doc in db.tracker_events.aggregate(ev_pipeline):
        rid = doc.get("user_id")
        if rid not in out:
            continue
        key = STAGE_KEY_MAP.get(doc.get("new_stage") or "")
        if key:
            out[rid][key] += 1
        if doc.get("mandate_id"):
            out[rid]["mandate_ids"].add(doc["mandate_id"])

    # Resolve mandate names
    all_ids = set()
    for rec in out.values():
        all_ids.update(rec["mandate_ids"])
    job_map = await _job_lookup(db, list(all_ids))

    for rec in out.values():
        mands = []
        for mid in rec["mandate_ids"]:
            m = job_map.get(mid, {})
            mands.append({
                "id": mid,
                "title": m.get("title") or mid,
                "client_name": m.get("client_name") or "—",
            })
        mands.sort(key=lambda x: (x["client_name"].lower(), x["title"].lower()))
        rec["mandates"] = mands
        rec["mandates_count"] = len(mands)
        del rec["mandate_ids"]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Excel generators
# ─────────────────────────────────────────────────────────────────────────────
HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)
TOTAL_FILL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
TOTAL_FONT = Font(bold=True)


def _autosize(ws):
    for col_cells in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col_cells[0].column)
        for cell in col_cells:
            v = cell.value
            if v is None:
                continue
            max_len = max(max_len, len(str(v)))
        ws.column_dimensions[col_letter].width = min(max(12, max_len + 2), 55)


def build_daily_excel(team_name: str, label: str, rows: List[Dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Daily Summary"

    # Title row
    ws.cell(row=1, column=1, value=f"Daily Performance — {team_name}").font = Font(bold=True, size=14)
    ws.cell(row=2, column=1, value=f"Period: previous 24h ending {label} · 6:30 PM IST").font = Font(italic=True, color="666666")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=6)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=6)

    headers = ["Recruiter", "Client", "Mandate / Job", "Profiles Captured", "Profiles Shared", "Mandate ID"]
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=4, column=col, value=h)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = Alignment(horizontal="left", vertical="center")

    if not rows:
        ws.cell(row=5, column=1, value="No activity recorded in this window.").font = Font(italic=True, color="888888")
    else:
        r = 5
        # Sub-totals per recruiter
        current_recruiter = None
        rec_totals = {"captured": 0, "shared": 0}

        def flush_rec_total(row_idx, rec_name):
            ws.cell(row=row_idx, column=1, value=f"  Subtotal — {rec_name}").font = TOTAL_FONT
            ws.cell(row=row_idx, column=1).fill = TOTAL_FILL
            ws.cell(row=row_idx, column=4, value=rec_totals["captured"]).font = TOTAL_FONT
            ws.cell(row=row_idx, column=4).fill = TOTAL_FILL
            ws.cell(row=row_idx, column=5, value=rec_totals["shared"]).font = TOTAL_FONT
            ws.cell(row=row_idx, column=5).fill = TOTAL_FILL
            for c_ in (2, 3, 6):
                ws.cell(row=row_idx, column=c_).fill = TOTAL_FILL

        for row in rows:
            if current_recruiter and row["recruiter_name"] != current_recruiter:
                flush_rec_total(r, current_recruiter)
                rec_totals = {"captured": 0, "shared": 0}
                r += 1
            current_recruiter = row["recruiter_name"]
            ws.cell(row=r, column=1, value=row["recruiter_name"])
            ws.cell(row=r, column=2, value=row["client_name"])
            ws.cell(row=r, column=3, value=row["mandate_title"])
            ws.cell(row=r, column=4, value=row["captured"])
            ws.cell(row=r, column=5, value=row["shared"])
            ws.cell(row=r, column=6, value=row["mandate_id"])
            rec_totals["captured"] += row["captured"]
            rec_totals["shared"] += row["shared"]
            r += 1
        flush_rec_total(r, current_recruiter)
        r += 2

        # Grand totals
        total_cap = sum(x["captured"] for x in rows)
        total_shr = sum(x["shared"] for x in rows)
        ws.cell(row=r, column=1, value="GRAND TOTAL").font = Font(bold=True, size=12)
        ws.cell(row=r, column=4, value=total_cap).font = Font(bold=True)
        ws.cell(row=r, column=5, value=total_shr).font = Font(bold=True)

    _autosize(ws)

    # Return bytes
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_weekly_excel(team_name: str, label: str, per_recruiter: Dict[str, Dict]) -> bytes:
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"

    summary.cell(row=1, column=1, value=f"Weekly Performance — {team_name}").font = Font(bold=True, size=14)
    summary.cell(row=2, column=1, value=f"Week: {label}").font = Font(italic=True, color="666666")
    summary.merge_cells(start_row=1, start_column=1, end_row=1, end_column=9)
    summary.merge_cells(start_row=2, start_column=1, end_row=2, end_column=9)

    headers = ["Recruiter", "Mandates", "Captured", "Shared", "Shortlisted", "Interviewed", "Offered", "Selected", "Joined"]
    for col, h in enumerate(headers, start=1):
        c = summary.cell(row=4, column=col, value=h)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL

    if not per_recruiter:
        summary.cell(row=5, column=1, value="No active recruiters in this team.").font = Font(italic=True, color="888888")
    else:
        r = 5
        totals = {k: 0 for k in ["mandates_count", "captured", "shared", "shortlisted", "interviewed", "offered", "selected", "joined"]}
        for rid, data in sorted(per_recruiter.items(), key=lambda x: x[1]["name"].lower()):
            summary.cell(row=r, column=1, value=data["name"])
            summary.cell(row=r, column=2, value=data["mandates_count"])
            summary.cell(row=r, column=3, value=data["captured"])
            summary.cell(row=r, column=4, value=data["shared"])
            summary.cell(row=r, column=5, value=data["shortlisted"])
            summary.cell(row=r, column=6, value=data["interviewed"])
            summary.cell(row=r, column=7, value=data["offered"])
            summary.cell(row=r, column=8, value=data["selected"])
            summary.cell(row=r, column=9, value=data["joined"])
            for k in totals:
                totals[k] += data[k]
            r += 1

        # Grand total row
        summary.cell(row=r, column=1, value="TOTAL").font = TOTAL_FONT
        for idx, key in enumerate(["mandates_count", "captured", "shared", "shortlisted", "interviewed", "offered", "selected", "joined"], start=2):
            summary.cell(row=r, column=idx, value=totals[key]).font = TOTAL_FONT
            summary.cell(row=r, column=idx).fill = TOTAL_FILL
        summary.cell(row=r, column=1).fill = TOTAL_FILL

    _autosize(summary)

    # Per-recruiter sheets (one tab each with mandate breakdown)
    for rid, data in per_recruiter.items():
        sheet_name = (data["name"] or rid)[:28] or rid[:8]
        # openpyxl sheet names can't contain :\/?*[]
        safe = "".join(ch for ch in sheet_name if ch not in r":\/?*[]").strip() or rid[:8]
        ws = wb.create_sheet(title=safe)
        ws.cell(row=1, column=1, value=f"{data['name']} — Weekly Detail").font = Font(bold=True, size=13)
        ws.cell(row=2, column=1, value=f"Week: {label}").font = Font(italic=True, color="666666")
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=4)

        # KPIs block
        kpis = [
            ("Profiles Captured", data["captured"]),
            ("Profiles Shared", data["shared"]),
            ("Shortlisted", data["shortlisted"]),
            ("Interviewed", data["interviewed"]),
            ("Offered", data["offered"]),
            ("Selected", data["selected"]),
            ("Joined", data["joined"]),
        ]
        ws.cell(row=4, column=1, value="KPI").font = HEADER_FONT
        ws.cell(row=4, column=1).fill = HEADER_FILL
        ws.cell(row=4, column=2, value="Count").font = HEADER_FONT
        ws.cell(row=4, column=2).fill = HEADER_FILL
        for i, (k, v) in enumerate(kpis, start=5):
            ws.cell(row=i, column=1, value=k)
            ws.cell(row=i, column=2, value=v)

        # Mandates worked list
        start = 5 + len(kpis) + 2
        ws.cell(row=start, column=1, value="Mandates Worked This Week").font = Font(bold=True, size=12)
        for col, h in enumerate(["#", "Client", "Mandate / Job", "Mandate ID"], start=1):
            c = ws.cell(row=start + 1, column=col, value=h)
            c.font = HEADER_FONT
            c.fill = HEADER_FILL
        if not data["mandates"]:
            ws.cell(row=start + 2, column=1, value="(No mandates worked in this window)").font = Font(italic=True, color="888888")
        else:
            for i, m in enumerate(data["mandates"], start=1):
                ws.cell(row=start + 1 + i, column=1, value=i)
                ws.cell(row=start + 1 + i, column=2, value=m["client_name"])
                ws.cell(row=start + 1 + i, column=3, value=m["title"])
                ws.cell(row=start + 1 + i, column=4, value=m["id"])

        _autosize(ws)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────────
def _daily_email_html(team_name: str, label: str, total_captured: int, total_shared: int) -> str:
    return f"""
    <div style="font-family: Arial, sans-serif; color: #333; max-width: 600px;">
      <h2 style="color: #1F4E78; margin-bottom: 4px;">Daily Performance Summary</h2>
      <p style="color: #666; margin-top: 0;">Team: <strong>{team_name}</strong> · {label}</p>
      <div style="padding: 16px; background: #F2F6FC; border-left: 4px solid #1F4E78; margin: 16px 0;">
        <table style="width: 100%; border-collapse: collapse;">
          <tr>
            <td><strong>Total Profiles Captured</strong></td>
            <td style="text-align: right; font-size: 18px; color: #1F4E78;"><strong>{total_captured}</strong></td>
          </tr>
          <tr>
            <td><strong>Total Profiles Shared</strong></td>
            <td style="text-align: right; font-size: 18px; color: #1F4E78;"><strong>{total_shared}</strong></td>
          </tr>
        </table>
      </div>
      <p>Detailed per-recruiter + per-mandate breakdown is in the attached Excel.</p>
      <p style="color: #888; font-size: 12px; margin-top: 32px;">
        This report is auto-generated daily at 6:30 PM IST. Activity past 6:30 PM rolls into the next day.
      </p>
    </div>
    """


def _weekly_email_html(team_name: str, label: str, per_recruiter: Dict[str, Dict]) -> str:
    total_cap = sum(r["captured"] for r in per_recruiter.values())
    total_shr = sum(r["shared"] for r in per_recruiter.values())
    total_joined = sum(r["joined"] for r in per_recruiter.values())
    rec_count = len(per_recruiter)
    return f"""
    <div style="font-family: Arial, sans-serif; color: #333; max-width: 640px;">
      <h2 style="color: #1F4E78; margin-bottom: 4px;">Weekly Performance Summary</h2>
      <p style="color: #666; margin-top: 0;">Team: <strong>{team_name}</strong> · {label}</p>
      <div style="padding: 16px; background: #F2F6FC; border-left: 4px solid #1F4E78; margin: 16px 0;">
        <table style="width: 100%; border-collapse: collapse;">
          <tr><td><strong>Recruiters</strong></td><td style="text-align: right;"><strong>{rec_count}</strong></td></tr>
          <tr><td><strong>Total Captured</strong></td><td style="text-align: right;"><strong>{total_cap}</strong></td></tr>
          <tr><td><strong>Total Shared</strong></td><td style="text-align: right;"><strong>{total_shr}</strong></td></tr>
          <tr><td><strong>Candidates Joined</strong></td><td style="text-align: right; color: #1F4E78;"><strong>{total_joined}</strong></td></tr>
        </table>
      </div>
      <p>The attached Excel contains a <strong>Summary</strong> sheet plus a dedicated tab for each recruiter with their mandate-level breakdown.</p>
      <p style="color: #888; font-size: 12px; margin-top: 32px;">
        This report is auto-generated every Monday at 9:00 AM IST and covers the previous Monday–Sunday.
      </p>
    </div>
    """


async def _acquire_run_lock(db, job_name: str, window_key: str) -> bool:
    """Attempt to insert a run-lock. Returns True only for the worker that succeeds.
    Prevents duplicate sends when multiple gunicorn workers each schedule the same job.
    """
    try:
        await db.report_job_locks.create_index(
            [("job_name", 1), ("window_key", 1)], unique=True, background=True
        )
    except Exception:
        pass
    try:
        await db.report_job_locks.insert_one({
            "job_name": job_name,
            "window_key": window_key,
            "acquired_at": datetime.now(timezone.utc).isoformat(),
        })
        return True
    except Exception:
        return False


async def generate_and_send_daily_reports(db) -> Dict:
    """Called by APScheduler at 18:30 IST daily."""
    start_iso, end_iso, label = compute_daily_window()
    if not await _acquire_run_lock(db, "daily_recruiter_report", end_iso):
        logger.info(f"[DailyReport] Skipping — another worker already ran this window ({label})")
        return {"sent": 0, "skipped": 0, "failed": 0, "window_label": label, "deduped": True}
    logger.info(f"[DailyReport] window={start_iso} → {end_iso} ({label})")
    teams = await _get_teams(db)
    sent, skipped, failed = 0, 0, 0
    for team in teams:
        team_name = team.get("name") or "(unnamed team)"
        recruiter_ids = team.get("recruiter_ids") or []
        if not recruiter_ids:
            skipped += 1
            continue
        employer = await _get_employer(db, team.get("employer_id") or "")
        if not employer or not employer.get("email"):
            logger.warning(f"[DailyReport] Team '{team_name}' has no employer email — skipping")
            skipped += 1
            continue
        rows = await aggregate_daily(db, recruiter_ids, start_iso, end_iso)
        total_cap = sum(r["captured"] for r in rows)
        total_shr = sum(r["shared"] for r in rows)
        excel_bytes = build_daily_excel(team_name, label, rows)
        html = _daily_email_html(team_name, label, total_cap, total_shr)
        subject = f"Daily Recruiter Report — {team_name} — {label}"
        filename = f"Daily_Report_{team_name.replace(' ', '_')}_{label.replace(',', '').replace(' ', '_')}.xlsx"
        resp = await send_email(
            recipient_email=employer["email"],
            subject=subject,
            html_content=html,
            attachments=[{"filename": filename, "content": excel_bytes}],
        )
        if resp.get("status") == "sent":
            sent += 1
        else:
            failed += 1
        # Audit trail
        await db.report_dispatches.insert_one({
            "type": "daily",
            "team_id": team.get("id"),
            "team_name": team_name,
            "employer_email": employer["email"],
            "window_start": start_iso,
            "window_end": end_iso,
            "total_captured": total_cap,
            "total_shared": total_shr,
            "status": resp.get("status"),
            "email_id": resp.get("email_id"),
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
    logger.info(f"[DailyReport] done — sent={sent} skipped={skipped} failed={failed}")
    return {"sent": sent, "skipped": skipped, "failed": failed, "window_label": label}


async def generate_and_send_weekly_reports(db) -> Dict:
    """Called by APScheduler at 09:00 IST every Monday."""
    start_iso, end_iso, label = compute_weekly_window()
    if not await _acquire_run_lock(db, "weekly_recruiter_report", end_iso):
        logger.info(f"[WeeklyReport] Skipping — another worker already ran this window ({label})")
        return {"sent": 0, "skipped": 0, "failed": 0, "window_label": label, "deduped": True}
    logger.info(f"[WeeklyReport] window={start_iso} → {end_iso} ({label})")
    teams = await _get_teams(db)
    sent, skipped, failed = 0, 0, 0
    for team in teams:
        team_name = team.get("name") or "(unnamed team)"
        recruiter_ids = team.get("recruiter_ids") or []
        if not recruiter_ids:
            skipped += 1
            continue
        employer = await _get_employer(db, team.get("employer_id") or "")
        if not employer or not employer.get("email"):
            logger.warning(f"[WeeklyReport] Team '{team_name}' has no employer email — skipping")
            skipped += 1
            continue
        per_rec = await aggregate_weekly(db, recruiter_ids, start_iso, end_iso)
        excel_bytes = build_weekly_excel(team_name, label, per_rec)
        html = _weekly_email_html(team_name, label, per_rec)
        subject = f"Weekly Recruiter Report — {team_name} — Week of {label}"
        filename = f"Weekly_Report_{team_name.replace(' ', '_')}_{label.replace(' ', '_').replace('–', '-')}.xlsx"
        resp = await send_email(
            recipient_email=employer["email"],
            subject=subject,
            html_content=html,
            attachments=[{"filename": filename, "content": excel_bytes}],
        )
        if resp.get("status") == "sent":
            sent += 1
        else:
            failed += 1
        await db.report_dispatches.insert_one({
            "type": "weekly",
            "team_id": team.get("id"),
            "team_name": team_name,
            "employer_email": employer["email"],
            "window_start": start_iso,
            "window_end": end_iso,
            "recruiters_count": len(per_rec),
            "status": resp.get("status"),
            "email_id": resp.get("email_id"),
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
    logger.info(f"[WeeklyReport] done — sent={sent} skipped={skipped} failed={failed}")
    return {"sent": sent, "skipped": skipped, "failed": failed, "window_label": label}
