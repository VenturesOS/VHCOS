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
from fastapi import APIRouter, HTTPException, Depends, Query
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


# ── Template CRUD ──

@router.post("/templates")
async def create_template(req: TemplateCreate, user=Depends(require_role(["admin", "recruiter"]))):
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
async def update_template(template_id: str, req: TemplateUpdate, user=Depends(require_role(["admin", "recruiter"]))):
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
async def clone_template(template_id: str, name: str = Query(...), user=Depends(require_role(["admin", "recruiter"]))):
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
async def delete_template(template_id: str, user=Depends(require_role(["admin"]))):
    """Delete a template."""
    result = await db.tracker_templates.delete_one({"id": template_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"message": "Template deleted"}


# ── Tracker CRUD ──

@router.post("/trackers")
async def create_tracker(req: TrackerCreate, user=Depends(require_role(["admin", "recruiter"]))):
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


@router.get("/trackers")
async def list_trackers(
    mandate_id: Optional[str] = None,
    client_id: Optional[str] = None,
    employer_id: Optional[str] = None,
    user=Depends(require_role(["admin", "recruiter", "employer"])),
):
    """List submission trackers, optionally filtered."""
    query = {}
    if mandate_id:
        query["mandate_id"] = mandate_id
    if client_id:
        query["client_id"] = client_id
    if employer_id:
        query["employer_id"] = employer_id

    trackers = await db.submission_trackers.find(query, {"_id": 0}).to_list(500)

    # Enrich with row counts
    for t in trackers:
        t["row_count"] = await db.tracker_rows.count_documents({"tracker_id": t["id"]})

    return {"trackers": trackers}


@router.get("/trackers/{tracker_id}")
async def get_tracker(tracker_id: str, user=Depends(require_role(["admin", "recruiter", "employer"]))):
    """Get tracker with all rows."""
    tracker = await db.submission_trackers.find_one({"id": tracker_id}, {"_id": 0})
    if not tracker:
        raise HTTPException(status_code=404, detail="Tracker not found")

    rows = await db.tracker_rows.find(
        {"tracker_id": tracker_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(10000)

    tracker["rows"] = rows
    tracker["row_count"] = len(rows)
    return tracker


@router.delete("/trackers/{tracker_id}")
async def delete_tracker(tracker_id: str, user=Depends(require_role(["admin"]))):
    """Delete tracker and all its rows."""
    result = await db.submission_trackers.delete_one({"id": tracker_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tracker not found")
    await db.tracker_rows.delete_many({"tracker_id": tracker_id})
    return {"message": "Tracker deleted"}


# ── Row Operations ──

@router.post("/trackers/{tracker_id}/rows")
async def add_row(tracker_id: str, req: AddRowRequest, user=Depends(require_role(["admin", "recruiter"]))):
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
    user=Depends(require_role(["admin", "recruiter"])),
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
    user=Depends(require_role(["admin", "recruiter"])),
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
    user=Depends(require_role(["admin", "recruiter"])),
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
    user=Depends(require_role(["admin", "recruiter"])),
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
    candidate = await db.candidates.find_one({"id": candidate_id}, {"_id": 0})
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
        "current_company": c.get("current_company", a.get("current_company", "")),
        "current_designation": c.get("current_designation", a.get("current_title", "")),
        "total_experience": c.get("total_experience", a.get("experience_summary", "")),
        "current_location": c.get("current_location", a.get("location", "")),
        "current_ctc": c.get("current_salary") or a.get("current_salary", ""),
        "expected_ctc": c.get("expected_salary") or a.get("expected_salary", ""),
        "notice_period": c.get("notice_period", a.get("notice_period", "")),
        "highest_qualification": c.get("highest_qualification", ""),
        "primary_skills": ", ".join(c.get("skills", [])) if isinstance(c.get("skills"), list) else c.get("skills", ""),
        "ai_resume_score": a.get("match_score", ""),
    }

    for key, value in auto_map.items():
        if key not in row_data or not row_data[key]:
            if value:
                row_data[key] = str(value) if not isinstance(value, str) else value
