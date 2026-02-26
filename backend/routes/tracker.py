"""
Client Submission Tracker Routes
- Template CRUD (column structure, required fields)
- Tracker CRUD (linked to mandate/client/employer)
- Tracker Row operations (add candidate, inline edit, bulk ops)
- Download validation + Excel export/import
- Master column definitions
"""
import uuid
import io
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from config import db
from utils import require_role
from services.master_columns import (
    MASTER_COLUMNS, COLUMN_CATEGORIES, COLUMN_MAP, FIELD_TYPES,
    DEFAULT_TEMPLATE_COLUMNS, AUTO_FILL_KEYS,
)
from services.tracker_sync import (
    add_candidate_to_tracker, sync_tracker_to_pipeline, sync_pipeline_to_tracker,
)
from services.pipeline_events import log_pipeline_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tracker", tags=["Tracker"])


# ── Pydantic Models ──

class ColumnDef(BaseModel):
    key: str
    label: str
    category: str = "Custom"
    field_type: str = "text"
    required: bool = False
    order: int = 0
    dropdown_options: Optional[List[str]] = None
    is_custom: bool = False


class TemplateCreate(BaseModel):
    name: str
    description: str = ""
    client_id: Optional[str] = None
    employer_id: Optional[str] = None
    columns: List[ColumnDef]


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    columns: Optional[List[ColumnDef]] = None


class TrackerCreate(BaseModel):
    name: str
    mandate_id: str
    client_id: Optional[str] = None
    employer_id: Optional[str] = None
    team_id: Optional[str] = None
    template_id: str


class AddRowRequest(BaseModel):
    candidate_id: str
    application_id: str
    data: Optional[dict] = None


class UpdateRowRequest(BaseModel):
    data: dict


class UpdateRowStatusRequest(BaseModel):
    submission_status: str


# ── Master Columns ──

@router.get("/columns")
async def get_master_columns(user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Get all available master columns grouped by category."""
    return {
        "columns": MASTER_COLUMNS,
        "categories": COLUMN_CATEGORIES,
        "field_types": FIELD_TYPES,
    }


@router.post("/parse-template-file")
async def parse_template_file(
    file: UploadFile = File(...),
    user=Depends(require_role(["admin", "recruiter", "employer"])),
):
    """Parse an uploaded Excel/CSV file and return header mapping suggestions for template creation."""
    filename = file.filename or ""
    content = await file.read()

    try:
        if filename.endswith(".csv"):
            import csv
            reader = csv.reader(io.StringIO(content.decode("utf-8-sig")))
            headers = [str(h).strip() for h in next(reader)]
            sample_rows = []
            for i, row in enumerate(reader):
                if i >= 3:
                    break
                if any(row):
                    sample_rows.append(row)
        elif filename.endswith((".xlsx", ".xls")):
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(content), read_only=True)
            ws = wb.active
            rows_iter = ws.iter_rows(values_only=True)
            headers = [str(h or "").strip() for h in next(rows_iter)]
            sample_rows = []
            for i, row in enumerate(rows_iter):
                if i >= 3:
                    break
                if any(c for c in row):
                    sample_rows.append([str(c or "") for c in row])
        else:
            raise HTTPException(status_code=400, detail="Only .xlsx and .csv files supported")
    except StopIteration:
        raise HTTPException(status_code=400, detail="File is empty")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)[:200]}")

    label_map = {c["label"].strip().lower().replace(" ", "_").replace("/", "_"): c for c in MASTER_COLUMNS}
    key_map = {c["key"]: c for c in MASTER_COLUMNS}

    mapped = []
    for idx, header in enumerate(headers):
        h_clean = header.strip().lower().replace(" ", "_").replace("/", "_")
        mc = key_map.get(h_clean) or label_map.get(h_clean)
        mapped.append({
            "index": idx,
            "header": header,
            "master_column": mc if mc else None,
            "matched": mc is not None,
        })

    return {
        "headers": headers,
        "mapping": mapped,
        "sample_rows": sample_rows,
        "total_headers": len(headers),
        "matched_count": sum(1 for m in mapped if m["matched"]),
    }



# ── Template CRUD ──

@router.post("/templates")
async def create_template(req: TemplateCreate, user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Create a new tracker template."""
    if not req.columns:
        raise HTTPException(status_code=400, detail="Template must have at least one column")

    now = datetime.now(timezone.utc).isoformat()
    template = {
        "id": str(uuid.uuid4()),
        "name": req.name,
        "description": req.description,
        "client_id": req.client_id,
        "employer_id": req.employer_id,
        "columns": [c.dict() for c in req.columns],
        "created_by": user.get("id", ""),
        "created_at": now,
        "updated_at": now,
    }
    await db.tracker_templates.insert_one(template)
    template.pop("_id", None)
    return template


@router.get("/templates")
async def list_templates(
    client_id: Optional[str] = None,
    employer_id: Optional[str] = None,
    user=Depends(require_role(["admin", "recruiter", "employer"])),
):
    """List tracker templates, optionally filtered."""
    query = {}
    if client_id:
        query["$or"] = [{"client_id": client_id}, {"client_id": None}]
    if employer_id:
        query["$or"] = [{"employer_id": employer_id}, {"employer_id": None}]

    templates = await db.tracker_templates.find(query, {"_id": 0}).to_list(500)
    return {"templates": templates}


@router.get("/templates/{template_id}")
async def get_template(template_id: str, user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Get a specific template."""
    template = await db.tracker_templates.find_one({"id": template_id}, {"_id": 0})
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.put("/templates/{template_id}")
async def update_template(template_id: str, req: TemplateUpdate, user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Update a template."""
    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if req.name is not None:
        updates["name"] = req.name
    if req.description is not None:
        updates["description"] = req.description
    if req.columns is not None:
        updates["columns"] = [c.dict() for c in req.columns]

    result = await db.tracker_templates.update_one({"id": template_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"message": "Template updated"}


@router.post("/templates/{template_id}/clone")
async def clone_template(template_id: str, name: str = Query(...), user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Clone a template with a new name."""
    original = await db.tracker_templates.find_one({"id": template_id}, {"_id": 0})
    if not original:
        raise HTTPException(status_code=404, detail="Template not found")

    now = datetime.now(timezone.utc).isoformat()
    clone = {
        **original,
        "id": str(uuid.uuid4()),
        "name": name,
        "created_by": user.get("id", ""),
        "created_at": now,
        "updated_at": now,
    }
    await db.tracker_templates.insert_one(clone)
    clone.pop("_id", None)
    return clone


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Delete a template."""
    result = await db.tracker_templates.delete_one({"id": template_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"message": "Template deleted"}


# ── Tracker CRUD ──

@router.post("/trackers")
async def create_tracker(req: TrackerCreate, user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Create a new submission tracker for a mandate."""
    template = await db.tracker_templates.find_one({"id": req.template_id}, {"_id": 0})
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Get mandate (job) info
    job = await db.jobs.find_one({"id": req.mandate_id}, {"_id": 0, "id": 1, "title": 1, "company_name": 1, "company_id": 1})
    if not job:
        raise HTTPException(status_code=404, detail="Mandate/Job not found")

    now = datetime.now(timezone.utc).isoformat()
    tracker = {
        "id": str(uuid.uuid4()),
        "name": req.name,
        "mandate_id": req.mandate_id,
        "mandate_name": job.get("title", ""),
        "client_id": req.client_id or job.get("company_id"),
        "employer_id": req.employer_id or job.get("posted_by"),
        "team_id": req.team_id,
        "template_id": req.template_id,
        "columns": template.get("columns", []),
        "created_by": user.get("id", ""),
        "created_at": now,
        "updated_at": now,
    }
    await db.submission_trackers.insert_one(tracker)
    tracker.pop("_id", None)
    return tracker


class DuplicateTrackerRequest(BaseModel):
    name: str
    mandate_id: Optional[str] = None


@router.post("/trackers/{tracker_id}/duplicate")
async def duplicate_tracker(tracker_id: str, req: DuplicateTrackerRequest, user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Duplicate a tracker's structure (columns, template) for a new mandate. No rows are copied."""
    source = await db.submission_trackers.find_one({"id": tracker_id}, {"_id": 0})
    if not source:
        raise HTTPException(status_code=404, detail="Source tracker not found")

    mandate_id = req.mandate_id or source.get("mandate_id")
    job = await db.jobs.find_one({"id": mandate_id}, {"_id": 0, "id": 1, "title": 1, "company_name": 1, "company_id": 1})

    now = datetime.now(timezone.utc).isoformat()
    new_tracker = {
        "id": str(uuid.uuid4()),
        "name": req.name,
        "mandate_id": mandate_id,
        "mandate_name": job.get("title", "") if job else source.get("mandate_name", ""),
        "client_id": job.get("company_id") if job else source.get("client_id"),
        "employer_id": job.get("posted_by") if job else source.get("employer_id"),
        "team_id": source.get("team_id"),
        "template_id": source.get("template_id"),
        "columns": source.get("columns", []),
        "created_by": user.get("id", ""),
        "created_at": now,
        "updated_at": now,
    }
    await db.submission_trackers.insert_one(new_tracker)
    new_tracker.pop("_id", None)
    return new_tracker




@router.get("/trackers")
async def list_trackers(
    mandate_id: Optional[str] = None,
    client_id: Optional[str] = None,
    employer_id: Optional[str] = None,
    user=Depends(require_role(["admin", "recruiter", "employer"])),
):
    """List submission trackers with role-based visibility filtering."""
    query = {}
    if mandate_id:
        query["mandate_id"] = mandate_id
    if client_id:
        query["client_id"] = client_id
    if employer_id:
        query["employer_id"] = employer_id

    role = user.get("role", "")
    user_id = user.get("id", "")

    # Role-based visibility: non-admin users see only relevant trackers
    if role == "recruiter":
        # Find mandates this recruiter is assigned to
        assigned_jobs = await db.jobs.find(
            {"assigned_recruiters": user_id}, {"_id": 0, "id": 1}
        ).to_list(500)
        assigned_mandate_ids = [j["id"] for j in assigned_jobs]

        or_conditions = [{"created_by": user_id}]
        if assigned_mandate_ids:
            or_conditions.append({"mandate_id": {"$in": assigned_mandate_ids}})

        role_filter = {"$or": or_conditions}
        query = {**query, **role_filter} if not query else {"$and": [query, role_filter]}

    elif role == "employer":
        # Find mandates this employer posted
        posted_jobs = await db.jobs.find(
            {"posted_by": user_id}, {"_id": 0, "id": 1}
        ).to_list(500)
        posted_mandate_ids = [j["id"] for j in posted_jobs]

        or_conditions = [
            {"created_by": user_id},
            {"employer_id": user_id},
        ]
        if posted_mandate_ids:
            or_conditions.append({"mandate_id": {"$in": posted_mandate_ids}})
        user_company_id = user.get("company_id")
        if user_company_id:
            or_conditions.append({"client_id": user_company_id})

        role_filter = {"$or": or_conditions}
        query = {**query, **role_filter} if not query else {"$and": [query, role_filter]}

    trackers = await db.submission_trackers.find(query, {"_id": 0}).to_list(500)

    # Enrich with row counts
    for t in trackers:
        t["row_count"] = await db.tracker_rows.count_documents({"tracker_id": t["id"]})

    return {"trackers": trackers}


@router.get("/trackers/{tracker_id}")
async def get_tracker(tracker_id: str, user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Get tracker with all rows. Enforces role-based visibility."""
    tracker = await db.submission_trackers.find_one({"id": tracker_id}, {"_id": 0})
    if not tracker:
        raise HTTPException(status_code=404, detail="Tracker not found")

    # Visibility check for non-admin users
    role = user.get("role", "")
    user_id = user.get("id", "")
    if role in ("recruiter", "employer"):
        allowed = tracker.get("created_by") == user_id or tracker.get("employer_id") == user_id
        if not allowed:
            mandate_id = tracker.get("mandate_id")
            if mandate_id:
                if role == "recruiter":
                    job = await db.jobs.find_one({"id": mandate_id, "assigned_recruiters": user_id}, {"_id": 0, "id": 1})
                else:
                    job = await db.jobs.find_one({"id": mandate_id, "posted_by": user_id}, {"_id": 0, "id": 1})
                allowed = job is not None
            if not allowed and role == "employer":
                user_company_id = user.get("company_id")
                if user_company_id and tracker.get("client_id") == user_company_id:
                    allowed = True
        if not allowed:
            raise HTTPException(status_code=403, detail="Access denied to this tracker")

    rows = await db.tracker_rows.find(
        {"tracker_id": tracker_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(10000)

    tracker["rows"] = rows
    tracker["row_count"] = len(rows)
    return tracker


@router.delete("/trackers/{tracker_id}")
async def delete_tracker(tracker_id: str, user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Delete tracker and all its rows."""
    result = await db.submission_trackers.delete_one({"id": tracker_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tracker not found")
    await db.tracker_rows.delete_many({"tracker_id": tracker_id})
    return {"message": "Tracker deleted"}


# ── Row Operations ──

@router.post("/trackers/{tracker_id}/rows")
async def add_row(tracker_id: str, req: AddRowRequest, user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Add a candidate to the tracker. Auto-syncs pipeline to submitted_to_client."""
    tracker = await db.submission_trackers.find_one({"id": tracker_id}, {"_id": 0})
    if not tracker:
        raise HTTPException(status_code=404, detail="Tracker not found")

    mandate_id = tracker.get("mandate_id", "")

    # Auto-fill data from candidate + application
    row_data = req.data or {}
    await _auto_fill_row(row_data, req.candidate_id, req.application_id, mandate_id, user)

    row, error = await add_candidate_to_tracker(
        tracker_id=tracker_id,
        candidate_id=req.candidate_id,
        application_id=req.application_id,
        mandate_id=mandate_id,
        row_data=row_data,
        user_id=user.get("id", ""),
        user_name=user.get("name", user.get("email", "")),
    )

    if error:
        raise HTTPException(status_code=409, detail=error)

    return row


@router.put("/trackers/{tracker_id}/rows/{row_id}")
async def update_row(
    tracker_id: str, row_id: str, req: UpdateRowRequest,
    user=Depends(require_role(["admin", "recruiter", "employer"])),
):
    """Inline edit a tracker row's data fields."""
    now = datetime.now(timezone.utc).isoformat()
    update_fields = {f"data.{k}": v for k, v in req.data.items()}
    update_fields["updated_at"] = now

    result = await db.tracker_rows.update_one(
        {"id": row_id, "tracker_id": tracker_id},
        {"$set": update_fields}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Row not found")
    return {"message": "Row updated"}


@router.put("/trackers/{tracker_id}/rows/{row_id}/status")
async def update_row_status(
    tracker_id: str, row_id: str, req: UpdateRowStatusRequest,
    user=Depends(require_role(["admin", "recruiter", "employer"])),
):
    """Update row submission status — triggers pipeline sync."""
    row = await db.tracker_rows.find_one(
        {"id": row_id, "tracker_id": tracker_id}, {"_id": 0}
    )
    if not row:
        raise HTTPException(status_code=404, detail="Row not found")

    old_status = row.get("submission_status", "submitted")
    now = datetime.now(timezone.utc).isoformat()

    await db.tracker_rows.update_one(
        {"id": row_id},
        {"$set": {
            "submission_status": req.submission_status,
            "updated_at": now,
        }}
    )

    # Log event
    await log_pipeline_event(
        candidate_id=row.get("candidate_id", ""),
        mandate_id=row.get("mandate_id", ""),
        application_id=row.get("application_id", ""),
        previous_stage=old_status,
        new_stage=req.submission_status,
        source="tracker",
        user_id=user.get("id", ""),
        user_name=user.get("name", user.get("email", "")),
        metadata={"tracker_id": tracker_id, "row_id": row_id},
    )

    # Sync tracker → pipeline
    await sync_tracker_to_pipeline(
        row_id=row_id,
        application_id=row.get("application_id", ""),
        new_submission_status=req.submission_status,
        user_id=user.get("id", ""),
        user_name=user.get("name", user.get("email", "")),
    )

    return {"message": "Status updated", "submission_status": req.submission_status}


@router.delete("/trackers/{tracker_id}/rows/{row_id}")
async def delete_row(
    tracker_id: str, row_id: str,
    user=Depends(require_role(["admin", "recruiter", "employer"])),
):
    """Remove a candidate row from tracker."""
    result = await db.tracker_rows.delete_one({"id": row_id, "tracker_id": tracker_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Row not found")
    return {"message": "Row removed"}


# ── Download Validation ──

@router.get("/trackers/{tracker_id}/validation")
async def validate_tracker(tracker_id: str, user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """
    Validate tracker for download readiness.
    Returns green/yellow/red status based on missing required fields.
    """
    tracker = await db.submission_trackers.find_one({"id": tracker_id}, {"_id": 0})
    if not tracker:
        raise HTTPException(status_code=404, detail="Tracker not found")

    columns = tracker.get("columns", [])
    required_keys = [c["key"] for c in columns if c.get("required")]

    rows = await db.tracker_rows.find(
        {"tracker_id": tracker_id}, {"_id": 0}
    ).to_list(10000)

    issues = []
    for row in rows:
        data = row.get("data", {})
        for key in required_keys:
            val = data.get(key)
            if not val or (isinstance(val, str) and not val.strip()):
                col_label = COLUMN_MAP.get(key, {}).get("label", key)
                issues.append({
                    "row_id": row["id"],
                    "candidate_name": data.get("full_name", "Unknown"),
                    "field": key,
                    "field_label": col_label,
                })

    total_rows = len(rows)
    if total_rows == 0:
        status = "red"
        message = "No candidates in tracker."
    elif not issues:
        status = "green"
        message = "All required fields complete. Ready to download."
    else:
        status = "yellow"
        message = f"{len(issues)} missing required field(s) across {len(set(i['row_id'] for i in issues))} candidate(s)."

    return {
        "status": status,
        "message": message,
        "total_rows": total_rows,
        "issues": issues[:50],
        "total_issues": len(issues),
    }


# ── Event History ──

@router.get("/events")
async def get_tracker_events(
    tracker_id: Optional[str] = None,
    application_id: Optional[str] = None,
    mandate_id: Optional[str] = None,
    limit: int = Query(50, le=200),
    user=Depends(require_role(["admin", "recruiter", "employer"])),
):
    """Get tracker/pipeline events for audit."""
    query = {}
    if tracker_id:
        query["metadata.tracker_id"] = tracker_id
    if application_id:
        query["application_id"] = application_id
    if mandate_id:
        query["mandate_id"] = mandate_id

    events = await db.tracker_events.find(
        query, {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)

    return {"events": events}


# ── Helpers ──

async def _auto_fill_row(row_data: dict, candidate_id: str, application_id: str, mandate_id: str, user: dict):
    """Auto-fill row data from candidate profile and application data."""
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    application = await db.applications.find_one({"id": application_id}, {"_id": 0})
    job = await db.jobs.find_one({"id": mandate_id}, {"_id": 0}) if mandate_id else {}

    c = candidate or {}
    a = application or {}
    j = job or {}

    auto_map = {
        "candidate_id": candidate_id,
        "full_name": a.get("candidate_name") or c.get("name", ""),
        "position_role": j.get("title", ""),
        "mandate_name": j.get("title", ""),
        "job_code": j.get("id", "")[:8],
        "recruiter_name": user.get("name", user.get("email", "")),
        "submission_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "mobile_number": c.get("phone", ""),
        "email": c.get("email", a.get("candidate_email", "")),
        "current_company": c.get("current_employer", a.get("current_employer", "")),
        "current_designation": c.get("designation", a.get("designation", "")),
        "total_experience": str(c.get("experience_years", "")) or a.get("experience_summary", ""),
        "current_location": c.get("location", a.get("location", "")),
        "current_ctc": c.get("current_salary") or a.get("current_salary", ""),
        "expected_ctc": c.get("expected_salary") or a.get("expected_salary", ""),
        "notice_period": c.get("notice_period", a.get("notice_period", "")),
        "highest_qualification": c.get("ug_course") or (c.get("education", [{}])[0].get("degree") if c.get("education") else "") or "",
        "primary_skills": ", ".join(c.get("skills", [])) if isinstance(c.get("skills"), list) else c.get("skills", ""),
        "ai_resume_score": a.get("match_score", ""),
    }

    for key, value in auto_map.items():
        if key not in row_data or not row_data[key]:
            if value:
                row_data[key] = str(value) if not isinstance(value, str) else value



# ── Excel Export ──

@router.get("/trackers/{tracker_id}/export")
async def export_tracker_excel(tracker_id: str, user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Export tracker as formatted Excel file, client-ready."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    tracker = await db.submission_trackers.find_one({"id": tracker_id}, {"_id": 0})
    if not tracker:
        raise HTTPException(status_code=404, detail="Tracker not found")

    rows = await db.tracker_rows.find({"tracker_id": tracker_id}, {"_id": 0}).sort("created_at", 1).to_list(10000)
    columns = tracker.get("columns", [])

    wb = Workbook()
    ws = wb.active
    ws.title = "Submission Tracker"

    # Styles
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
    required_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
    missing_fill = PatternFill(start_color="FFE0E0", end_color="FFE0E0", fill_type="solid")
    cell_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    # Title row
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(columns) + 2)
    title_cell = ws.cell(row=1, column=1, value=tracker.get("name", "Submission Tracker"))
    title_cell.font = Font(name="Calibri", bold=True, size=14, color="1F4E79")
    ws.cell(row=2, column=1, value=f"Mandate: {tracker.get('mandate_name', '')} | Exported: {datetime.now(timezone.utc).strftime('%d %b %Y')}")
    ws.cell(row=2, column=1).font = Font(name="Calibri", size=10, color="666666")

    # Headers (row 4)
    header_row = 4
    ws.cell(row=header_row, column=1, value="#").font = header_font
    ws.cell(row=header_row, column=1).fill = header_fill
    ws.cell(row=header_row, column=1).alignment = Alignment(horizontal="center")

    for ci, col in enumerate(columns, start=2):
        cell = ws.cell(row=header_row, column=ci, value=col.get("label", col.get("key", "")))
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="left", wrap_text=True)

    status_col = len(columns) + 2
    cell = ws.cell(row=header_row, column=status_col, value="Status")
    cell.font = header_font
    cell.fill = header_fill

    # Data rows
    required_keys = {c["key"] for c in columns if c.get("required")}
    for ri, row in enumerate(rows, start=header_row + 1):
        ws.cell(row=ri, column=1, value=ri - header_row).border = cell_border
        data = row.get("data", {})
        for ci, col in enumerate(columns, start=2):
            val = data.get(col["key"], "")
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.border = cell_border
            cell.font = Font(name="Calibri", size=10)
            if col["key"] in required_keys and not val:
                cell.fill = missing_fill

        status = STATUS_MAP_LABEL.get(row.get("submission_status", ""), row.get("submission_status", ""))
        ws.cell(row=ri, column=status_col, value=status).border = cell_border

    # Column widths
    ws.column_dimensions["A"].width = 5
    for ci, col in enumerate(columns, start=2):
        col_letter = chr(64 + ci) if ci <= 26 else chr(64 + (ci // 26)) + chr(64 + (ci % 26))
        from openpyxl.utils import get_column_letter
        col_letter = get_column_letter(ci)
        ws.column_dimensions[col_letter].width = max(15, len(col.get("label", "")) + 4)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    safe_name = (tracker.get("name", "tracker")).replace(" ", "_")[:50]
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.xlsx"'},
    )


# Status label map for export
STATUS_MAP_LABEL = {
    "submitted": "Submitted",
    "interview_scheduled": "Interview Scheduled",
    "interviewed": "Interviewed",
    "offer_issued": "Offer Issued",
    "offer_accepted": "Offer Accepted",
    "joining_confirmed": "Joining Confirmed",
    "rejected": "Rejected",
    "on_hold": "On Hold",
}


# ── Excel/CSV Upload ──

@router.post("/trackers/{tracker_id}/upload")
async def upload_tracker_data(
    tracker_id: str,
    file: UploadFile = File(...),
    user=Depends(require_role(["admin", "recruiter", "employer"])),
):
    """
    Upload Excel/CSV to a tracker. Auto-detects headers and maps to master columns.
    Returns mapping suggestions for confirmation.
    """
    tracker = await db.submission_trackers.find_one({"id": tracker_id}, {"_id": 0})
    if not tracker:
        raise HTTPException(status_code=404, detail="Tracker not found")

    filename = file.filename or ""
    content = await file.read()

    try:
        if filename.endswith(".csv"):
            import csv
            reader = csv.reader(io.StringIO(content.decode("utf-8-sig")))
            headers = next(reader)
            data_rows = [row for row in reader if any(row)]
        elif filename.endswith((".xlsx", ".xls")):
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(content), read_only=True)
            ws = wb.active
            rows_iter = ws.iter_rows(values_only=True)
            headers = [str(h or "").strip() for h in next(rows_iter)]
            data_rows = [[str(c or "") for c in row] for row in rows_iter if any(c for c in row)]
        else:
            raise HTTPException(status_code=400, detail="Only .xlsx and .csv files are supported")
    except StopIteration:
        raise HTTPException(status_code=400, detail="File is empty")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)[:200]}")

    # Auto-map headers to master columns
    header_lower = {h.strip().lower().replace(" ", "_").replace("/", "_"): i for i, h in enumerate(headers)}
    all_columns_lower = {c["key"]: c for c in MASTER_COLUMNS}
    label_map = {c["label"].strip().lower().replace(" ", "_").replace("/", "_"): c["key"] for c in MASTER_COLUMNS}

    mapping = {}
    unmapped = []
    for idx, header in enumerate(headers):
        h_clean = header.strip().lower().replace(" ", "_").replace("/", "_")
        if h_clean in all_columns_lower:
            mapping[idx] = h_clean
        elif h_clean in label_map:
            mapping[idx] = label_map[h_clean]
        else:
            unmapped.append({"index": idx, "header": header})

    # Import rows
    now = datetime.now(timezone.utc).isoformat()
    imported = 0
    for data_row in data_rows:
        row_data = {}
        for col_idx, master_key in mapping.items():
            if col_idx < len(data_row):
                row_data[master_key] = data_row[col_idx]

        row = {
            "id": str(uuid.uuid4()),
            "tracker_id": tracker_id,
            "candidate_id": row_data.get("candidate_id", ""),
            "application_id": "",
            "mandate_id": tracker.get("mandate_id", ""),
            "pipeline_stage": "submitted_to_client",
            "submission_status": "submitted",
            "data": row_data,
            "created_by": user.get("id", ""),
            "created_at": now,
            "updated_at": now,
        }
        await db.tracker_rows.insert_one(row)
        imported += 1

    return {
        "message": f"Imported {imported} rows",
        "imported": imported,
        "total_headers": len(headers),
        "mapped_columns": len(mapping),
        "unmapped_headers": unmapped,
    }
