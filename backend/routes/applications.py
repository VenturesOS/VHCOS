"""
VHC Talent OS - Applications & AI Matching Routes
Handles all application lifecycle operations including CRUD, stage transitions,
AI screening, candidate-job matching, and audit history.
"""
import uuid
import logging
import re
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Request, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
import aiofiles
from routes.notifications import create_notification
from models.application import (
    ApplicantReviewResponse, CandidateApprovalRequest,
    ShortlistRequest, LinkCandidateRequest,
)

# Concurrency limiter for matching endpoint
_MATCH_SEMAPHORE = asyncio.Semaphore(10)  # Max 10 concurrent DB operations

# In-memory cache for quick match results (key -> (results, timestamp))
_match_cache: dict = {}
_MATCH_CACHE_TTL = 120  # 2 minutes cache for identical queries
_match_locks: dict = {}  # Per-key asyncio locks to prevent thundering herd

# Import configuration
from config import db, UPLOAD_DIR

# Import models
from models import (
    ApplicationCreate, ApplicationResponse, ApplicationUpdate,
    CandidateProfile, MatchResult, MatchRequest, JobMatchForCandidate,
    NoteCreate, ApplicationDetailUpdate
)

# Import utilities
from utils import get_current_user, require_role
from utils.governance import (
    add_application_to_history, update_application_in_history,
    create_profile_audit_entry
)

# Import AI matching engine
from services.matching_engine import (
    parse_resume_with_ai,
    parse_job_description_with_ai,
    calculate_candidate_job_match,
    apply_must_have_filters,
    generate_resume_fingerprint,
    find_similar_candidate,
    parse_job_requirements_fast,
    calculate_fast_match_score,
)

# Import embeddings service for semantic search
from services.embeddings import embedding_service

# Import service helpers
from services.application_service import (
    match_cache_key as _match_cache_key,
    extract_text_from_pdf,
    calculate_career_stability,
)
from services.activity_log_service import (
    log_activity, ACTION_STAGE_CHANGED, ACTION_NOTE_ADDED,
    ACTION_APPROVAL, ACTION_APPLIED, ACTION_SHORTLISTED, ACTION_LINKED,
    ACTION_MATCH_SCORED, ACTION_VIEWED, ACTION_REJECTED,
)

# Create router for applications endpoints
applications_router = APIRouter(prefix="/api", tags=["Applications"])

logger = logging.getLogger(__name__)


# ============== APPLICATION RESUME DOWNLOAD ==============

@applications_router.get("/applications/{app_id}/resume")
async def download_application_resume(
    app_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Download candidate resume with proper naming: Firstname_Lastname_VHC.ext
    
    Permission checks:
    - Admin: Can access any resume
    - Employer/Recruiter: Only resumes for candidates who applied to their jobs
    """
    # Get application
    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Permission check for non-admin
    if current_user["role"] != "admin":
        job = await db.jobs.find_one({"id": application["job_id"]}, {"_id": 0})
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Check if user has access to this job
        has_access = (
            job.get("created_by") == current_user["id"] or
            job.get("company_id") == current_user.get("company_id") or
            job.get("assigned_recruiter") == current_user["id"]
        )
        if not has_access:
            raise HTTPException(status_code=403, detail="Access denied to this resume")
    
    # Get resume URL
    resume_url = application.get("resume_url")
    if not resume_url:
        # Try to get from candidate profile (check both candidates and candidate_bank)
        if application.get("candidate_id"):
            candidate = await db.candidates.find_one({"id": application["candidate_id"]}, {"_id": 0})
            if not candidate:
                candidate = await db.candidate_bank.find_one({"id": application["candidate_id"]}, {"_id": 0})
            if candidate:
                resume_url = candidate.get("resume_url")
    
    if not resume_url:
        raise HTTPException(status_code=404, detail="Resume not found for this application")
    
    # Extract filename from URL
    original_filename = resume_url.split("/")[-1]
    
    # Check both possible upload locations
    from config import ROOT_DIR
    primary_dir = ROOT_DIR / "uploads"
    primary_path = primary_dir / original_filename
    secondary_path = UPLOAD_DIR / original_filename
    
    if primary_path.exists():
        file_path = primary_path
    elif secondary_path.exists():
        file_path = secondary_path
    else:
        raise HTTPException(status_code=404, detail="Resume file not found")
    
    # Generate proper download filename
    candidate_name = application.get("candidate_name", "Unknown_Candidate")
    name_parts = candidate_name.strip().split()
    
    if len(name_parts) >= 2:
        first_name = name_parts[0]
        last_name = name_parts[-1]
    elif len(name_parts) == 1:
        first_name = name_parts[0]
        last_name = "Unknown"
    else:
        first_name = "Unknown"
        last_name = "Candidate"
    
    first_name = re.sub(r'[^a-zA-Z0-9]', '', first_name)
    last_name = re.sub(r'[^a-zA-Z0-9]', '', last_name)
    
    file_ext = file_path.suffix
    download_filename = f"{first_name}_{last_name}_VHC{file_ext}"
    
    return FileResponse(
        file_path,
        filename=download_filename,
        media_type="application/octet-stream"
    )


# ============== APPLICATION CRUD ==============

@applications_router.post("/applications", response_model=ApplicationResponse)
async def create_application(app_data: ApplicationCreate, current_user: dict = Depends(require_role(["candidate"]))):
    """Create a new application (candidate applies for a job)"""
    # Check if job exists
    job = await db.jobs.find_one({"id": app_data.job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check if already applied
    existing = await db.applications.find_one({
        "job_id": app_data.job_id,
        "candidate_id": current_user["id"]
    })
    if existing:
        raise HTTPException(status_code=400, detail="Already applied to this job")
    
    # Get candidate's data from candidate_bank if exists
    candidate_bank = await db.candidate_bank.find_one(
        {"$or": [{"linked_user_id": current_user["id"]}, {"email": current_user["email"]}]},
        {"_id": 0}
    )
    
    app_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Get company name
    company = await db.companies.find_one({"id": job.get("company_id")}, {"name": 1, "_id": 0})
    company_name = company.get("name") if company else job.get("company_name", "Unknown")
    
    app_doc = {
        "id": app_id,
        "job_id": app_data.job_id,
        "candidate_id": current_user["id"],
        "candidate_name": current_user["name"],
        "candidate_email": current_user["email"],
        "job_title": job.get("title"),
        "company_name": company_name,
        "cover_letter": app_data.cover_letter,
        "status": "active",
        "stage": "applied",
        "source": "self",
        "notes": [],
        "edit_history": [],
        "created_at": now,
        "updated_at": now
    }
    
    # Include candidate bank data if available
    if candidate_bank:
        app_doc["current_salary"] = candidate_bank.get("current_salary")
        app_doc["expected_salary"] = candidate_bank.get("expected_salary")
        app_doc["notice_period"] = candidate_bank.get("notice_period")
        app_doc["location"] = candidate_bank.get("location")
        app_doc["experience_years"] = candidate_bank.get("experience_years")
        app_doc["skills"] = candidate_bank.get("skills", [])
        app_doc["resume_url"] = candidate_bank.get("resume_url")
        app_doc["current_employer"] = candidate_bank.get("current_employer")
        app_doc["designation"] = candidate_bank.get("designation")
        app_doc["industry"] = candidate_bank.get("industry")
        app_doc["education"] = candidate_bank.get("education")
        app_doc["ug_course"] = candidate_bank.get("ug_course")
        app_doc["headline"] = candidate_bank.get("headline")
        app_doc["candidate_phone"] = candidate_bank.get("phone")
    
    await db.applications.insert_one(app_doc)
    
    # Increment applicant count
    await db.jobs.update_one({"id": app_data.job_id}, {"$inc": {"applicant_count": 1}})
    
    # Notify job poster about new application
    if job.get("posted_by"):
        try:
            await create_notification(
                user_id=job["posted_by"],
                notification_type="new_application",
                title="New Application",
                message=f"{current_user['name']} applied for {job.get('title', 'a job')}",
                link=f"/employer/jobs/{app_data.job_id}/applicants",
                metadata={"job_id": app_data.job_id, "application_id": app_id},
            )
        except Exception:
            pass  # Don't fail application on notification error
    # Notify assigned recruiters
    for rec_id in job.get("assigned_recruiters", []):
        try:
            await create_notification(
                user_id=rec_id,
                notification_type="new_application",
                title="New Application",
                message=f"{current_user['name']} applied for {job.get('title', 'a job')}",
                link="/recruiter/pipeline",
                metadata={"job_id": app_data.job_id, "application_id": app_id},
            )
        except Exception:
            pass
    
    # Data Governance: Add to candidate's application history if they exist in candidate_bank
    if candidate_bank:
        await add_application_to_history(candidate_bank["id"], {
            "id": app_id,
            "job_id": app_data.job_id,
            "job_title": job.get("title"),
            "company_name": company_name,
            "source": "self",
            "created_at": now,
            "stage": "applied"
        })
    
    return ApplicationResponse(**app_doc)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Timeline Filter — "show only movements in window"
# ─────────────────────────────────────────────────────────────────────────────
_WINDOW_DAYS = {"week": 7, "month": 30, "quarter": 90, "year": 365}


def _build_pipeline_window_filter(window: Optional[str],
                                  window_from: Optional[str],
                                  window_to: Optional[str]) -> Optional[dict]:
    """Translate a window selection into a Mongo filter that keeps applications
    whose stage_history has at least one transition inside the window.

    Returns None for 'all' / unset → no filter applied.
    """
    if not window or window == "all":
        return None

    now = datetime.now(timezone.utc)

    if window == "custom":
        try:
            start = datetime.fromisoformat(window_from) if window_from else (now - timedelta(days=30))
            end   = datetime.fromisoformat(window_to)   if window_to   else now
        except ValueError:
            # bad input → fall back to "month"
            start = now - timedelta(days=30)
            end = now
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        # Make end inclusive: extend to 23:59:59 if it's a date-only input
        if end.hour == 0 and end.minute == 0 and end.second == 0:
            end = end + timedelta(days=1) - timedelta(microseconds=1)
    else:
        days = _WINDOW_DAYS.get(window, 30)
        start = now - timedelta(days=days)
        end   = now

    start_iso = start.isoformat()
    end_iso   = end.isoformat()

    # stage_history is an array of {stage, moved_by, moved_by_name, timestamp}.
    # An $elemMatch ensures BOTH bounds apply to the SAME entry, not different ones.
    # We also accept `updated_at` as a fallback because some older application
    # rows were created before stage_history was populated on insert.
    return {
        "$or": [
            {"stage_history": {"$elemMatch": {"timestamp": {"$gte": start_iso, "$lte": end_iso}}}},
            {"$and": [
                {"updated_at": {"$gte": start_iso, "$lte": end_iso}},
                {"$or": [
                    {"stage_history": {"$exists": False}},
                    {"stage_history": {"$size": 0}},
                ]},
            ]},
        ],
    }


@applications_router.get("/applications/pipeline-stats")
async def get_pipeline_stage_stats(
    job_id: Optional[str] = None,
    window: Optional[str] = Query(None, description="week/month/quarter/year/all/custom"),
    window_from: Optional[str] = None,
    window_to: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Stage-count widgets for the pipeline page. Counts honor the same
    timeline window as the main /applications list so the numbers tie."""
    base_query: Dict[str, Any] = {}
    if current_user["role"] == "candidate":
        base_query["candidate_id"] = current_user["id"]
    elif current_user["role"] == "employer":
        jobs = await db.jobs.find({"posted_by": current_user["id"]}, {"id": 1, "_id": 0}).to_list(1000)
        base_query["job_id"] = {"$in": [j["id"] for j in jobs]}
    if job_id:
        base_query["job_id"] = job_id

    win_filter = _build_pipeline_window_filter(window, window_from, window_to)
    if win_filter:
        base_query = {"$and": [base_query, win_filter]} if base_query else win_filter

    # Apply the standard pipeline display filter (hide extension clutter)
    from services.pipeline_events import pipeline_display_filter
    base_query = {"$and": [base_query, pipeline_display_filter()]} if base_query else pipeline_display_filter()

    pipeline = [
        {"$match": base_query},
        {"$group": {"_id": "$stage", "n": {"$sum": 1}}},
    ]
    rows = await db.applications.aggregate(pipeline).to_list(50)
    counts = {r["_id"]: r["n"] for r in rows if r.get("_id")}
    total = sum(counts.values())
    return {
        "window": window or "all",
        "window_from": window_from,
        "window_to": window_to,
        "total": total,
        "by_stage": counts,
    }


@applications_router.get("/applications", response_model=List[ApplicationResponse])
async def get_applications(
    job_id: Optional[str] = None,
    stage: Optional[str] = None,
    page: int = 1,
    limit: int = 200,
    window: Optional[str] = Query(
        None,
        description="Activity window for pipeline movement: 'week' (7d), 'month' (30d), 'quarter' (90d), 'year' (365d), 'all', or 'custom'. With 'custom', supply window_from/window_to as ISO dates.",
    ),
    window_from: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD) — start of custom window"),
    window_to: Optional[str]   = Query(None, description="ISO date (YYYY-MM-DD) — end of custom window"),
    current_user: dict = Depends(get_current_user),
):
    """Get applications with role-based filtering and pagination.

    Pipeline timeline filter (v5.5.10+):
      Pass `window` to restrict results to applications whose stage CHANGED
      inside the window. This mirrors what a recruiter expects from "This Week"
      etc — actual recent movement, not just stale records that happen to live
      in the system. Uses `stage_history.timestamp` (every transition is
      appended there). The same window powers the stage-count widgets on the
      pipeline page so the numbers tie.
    """
    try:
        query = {}
        
        if current_user["role"] == "candidate":
            query["candidate_id"] = current_user["id"]
        elif current_user["role"] == "employer":
            jobs = await db.jobs.find({"posted_by": current_user["id"]}, {"id": 1, "_id": 0}).to_list(1000)
            job_ids = [j["id"] for j in jobs]
            query["job_id"] = {"$in": job_ids}
        
        if job_id:
            query["job_id"] = job_id
        if stage:
            query["stage"] = stage

        # ── Pipeline timeline window: filter to applications that MOVED in the window ──
        win_filter = _build_pipeline_window_filter(window, window_from, window_to)
        if win_filter:
            query = {"$and": [query, win_filter]} if query else win_filter

        # Apply pipeline display filter (hide extension clutter + stale rejections)
        # Only when no explicit stage filter is set (preserve exact-stage queries).
        if not stage:
            from services.pipeline_events import pipeline_display_filter
            _f = pipeline_display_filter()
            query = {"$and": [query, _f]} if query else _f

        _limit = max(1, min(limit, 500))
        _skip = (max(1, page) - 1) * _limit
        applications = await db.applications.find(query, {"_id": 0}).skip(_skip).limit(_limit).to_list(_limit)

        # Enrich with candidate_bank fields so the pipeline card/detail dialog
        # shows the real CTC / experience / location / employer rather than the
        # empty strings the raw application row was seeded with at capture time.
        candidate_ids = list({a.get("candidate_id") for a in applications if a.get("candidate_id")})
        candidates_map = {}
        if candidate_ids:
            cands = await db.candidate_bank.find(
                {"id": {"$in": candidate_ids}},
                {"_id": 0, "id": 1, "location": 1, "current_employer": 1, "designation": 1,
                 "industry": 1, "education": 1, "ug_course": 1, "headline": 1,
                 "expected_salary": 1, "current_salary": 1, "experience_years": 1,
                 "notice_period": 1, "phone": 1, "name": 1, "email": 1}
            ).to_list(len(candidate_ids))
            candidates_map = {c["id"]: c for c in cands}
        for a in applications:
            cb = candidates_map.get(a.get("candidate_id"), {})
            if not cb:
                continue
            # Prefer existing application value; fall back to candidate_bank
            for fld in ("candidate_name", "candidate_email", "candidate_phone"):
                bank_fld = {"candidate_name": "name", "candidate_email": "email", "candidate_phone": "phone"}[fld]
                if not a.get(fld):
                    a[fld] = cb.get(bank_fld)
            for fld in ("current_salary", "expected_salary", "notice_period",
                        "experience_years", "location", "headline",
                        "current_employer", "designation", "industry"):
                if a.get(fld) in (None, "", 0):
                    a[fld] = cb.get(fld)
            # Education in candidate_bank is a list of dicts — flatten to a string
            if not a.get("education"):
                edu = cb.get("education")
                if isinstance(edu, list) and edu:
                    parts = []
                    for e in edu[:2]:
                        if isinstance(e, dict):
                            deg = e.get("degree") or ""
                            inst = e.get("institution") or ""
                            parts.append(f"{deg} · {inst}" if deg and inst else (deg or inst))
                    a["education"] = "; ".join(p for p in parts if p) or None
                elif isinstance(edu, str):
                    a["education"] = edu

        # Strip revenue fields for non-admin/employer roles
        is_revenue_role = current_user.get("role") in ("admin", "employer")
        results = []
        for a in applications:
            if not is_revenue_role:
                for key in ("forecast_revenue", "forecast_slab", "forecast_percentage",
                            "offered_ctc", "expected_ctc"):
                    a.pop(key, None)
            try:
                results.append(ApplicationResponse(**a))
            except Exception:
                # Skip malformed application documents rather than 500 the entire response
                continue
        return results
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Applications] Error fetching applications: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch applications. Please try again.")


@applications_router.get("/applications/pending-approval")
async def get_pending_employer_approval(
    job_id: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Get all candidates pending employer approval (at 'shortlisted' stage).
    Employer sees candidates shortlisted by their team recruiters.
    """
    query = {"stage": "shortlisted"}
    
    if job_id:
        query["job_id"] = job_id
    
    # Employer sees only their team's jobs
    if current_user["role"] == "employer":
        team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
        if team:
            team_jobs = await db.jobs.find(
                {"$or": [
                    {"team_id": team["id"]},
                    {"posted_by": current_user["id"]},
                    {"assigned_recruiter_id": {"$in": team.get("recruiter_ids", [])}},
                ]},
                {"_id": 0, "id": 1}
            ).to_list(1000)
            job_ids = [j["id"] for j in team_jobs]
            query["job_id"] = {"$in": job_ids}
        else:
            query["job_id"] = {"$in": []}
    
    applications = await db.applications.find(query, {"_id": 0}).sort("updated_at", -1).to_list(500)
    
    # Batch-fetch job info in one query instead of N individual find_ones
    job_ids = list({a.get("job_id") for a in applications if a.get("job_id")})
    jobs_map = {}
    if job_ids:
        jobs = await db.jobs.find(
            {"id": {"$in": job_ids}},
            {"_id": 0, "id": 1, "title": 1, "job_public_id": 1, "company_name": 1}
        ).to_list(len(job_ids))
        jobs_map = {j["id"]: j for j in jobs}
    
    for app in applications:
        job = jobs_map.get(app.get("job_id"), {})
        if job:
            app["job_title"] = job.get("title")
            app["job_public_id"] = job.get("job_public_id")
            app["company_name"] = job.get("company_name")
    
    return {"pending_count": len(applications), "applications": applications}



@applications_router.get("/applications/{app_id}", response_model=ApplicationResponse)
async def get_application(app_id: str, current_user: dict = Depends(get_current_user)):
    """Get single application. Revenue fields stripped for recruiters."""
    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if current_user.get("role") not in ("admin", "employer"):
        for key in ("forecast_revenue", "forecast_slab", "forecast_percentage",
                    "offered_ctc", "expected_ctc"):
            application.pop(key, None)
    return ApplicationResponse(**application)


@applications_router.put("/applications/{app_id}", response_model=ApplicationResponse)
async def update_application(app_id: str, update_data: ApplicationUpdate, current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))):
    """Update application with stage tracking and revenue enforcement."""
    # Get current application for history tracking
    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}

    # ── Stage transition enforcement ──
    new_stage = update_dict.get("stage")
    if new_stage:
        from services.pipeline_events import validate_stage_transition, log_pipeline_event
        current_stage = application.get("stage", "applied")

        is_valid, error_msg = validate_stage_transition(current_stage, new_stage)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.applications.update_one({"id": app_id}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Data Governance: Update candidate history if stage changed
    if "stage" in update_dict and application.get("candidate_id"):
        new_stage = update_dict["stage"]
        previous_stage = application.get("stage", "applied")
        outcome = None
        if new_stage in ["joined", "hired", "rejected", "dropped"]:
            outcome = new_stage
        await update_application_in_history(
            application["candidate_id"],
            app_id,
            new_stage,
            outcome
        )
        # Log pipeline event
        from services.pipeline_events import log_pipeline_event
        await log_pipeline_event(
            candidate_id=application.get("candidate_id", ""),
            mandate_id=application.get("job_id", ""),
            application_id=app_id,
            previous_stage=previous_stage,
            new_stage=new_stage,
            source="pipeline",
            user_id=current_user.get("id", ""),
            user_name=current_user.get("name", current_user.get("email", "")),
        )
        # Sync pipeline → tracker (Rule B)
        from services.tracker_sync import sync_pipeline_to_tracker
        await sync_pipeline_to_tracker(
            application_id=app_id,
            new_stage=new_stage,
            user_id=current_user.get("id", ""),
            user_name=current_user.get("name", current_user.get("email", "")),
        )

        # LTR auto-capture — server-side, fire-and-forget. Translates the
        # stage transition into a labeled action against the user's most
        # recent search_session (within the last hour). If no recent session
        # exists, this silently no-ops. See services/ltr_telemetry.py.
        try:
            from services.ltr_telemetry import STAGE_TO_LTR_ACTION, auto_log_action
            ltr_action = STAGE_TO_LTR_ACTION.get(new_stage)
            if ltr_action:
                asyncio.create_task(auto_log_action(
                    user=current_user,
                    candidate_id=application.get("candidate_id", ""),
                    action=ltr_action,
                    extra={"app_id": app_id, "stage": new_stage, "source": "pipeline_stage_change"},
                ))
        except Exception as _e:
            logger.debug(f"[applications] LTR auto-log skipped: {_e}")

        # Phase 55.7 — auto-draft a bill on `hired` / `joined`. Best-effort;
        # never blocks the stage change. Idempotent via line_items.application_id.
        if new_stage in ("hired", "joined"):
            try:
                from services.bill_auto_draft import maybe_auto_draft_bill
                merged_app = {**application, **update_dict, "id": app_id}
                await maybe_auto_draft_bill(app_id, merged_app, current_user)
            except Exception as _e:
                # Never break stage transitions because of billing side-effects.
                logger.warning("[applications] auto-draft bill failed for %s: %s", app_id, _e)
    
    updated_application = await db.applications.find_one({"id": app_id}, {"_id": 0})

    # Log activity for stage change
    if "stage" in update_dict and application.get("candidate_id"):
        previous_stage = application.get("stage", "applied")
        new_stg = update_dict["stage"]
        await log_activity(
            candidate_id=application["candidate_id"], action=ACTION_STAGE_CHANGED,
            description=f"Stage changed from {previous_stage} to {new_stg} for {application.get('job_title', 'a job')}",
            performed_by=current_user.get("id"), performed_by_name=current_user.get("name"),
            performed_by_role=current_user.get("role"),
            candidate_name=application.get("candidate_name"),
            details={"from_stage": previous_stage, "to_stage": new_stg, "job_id": application.get("job_id"), "application_id": app_id},
        )

    # Notify candidate about stage change
    if "stage" in update_dict and application.get("candidate_id"):
        stage_label = update_dict["stage"].replace("_", " ").title()
        try:
            await create_notification(
                user_id=application["candidate_id"],
                notification_type="status_change",
                title="Application Update",
                message=f"Your application for {application.get('job_title', 'a job')} is now: {stage_label}",
                link="/candidate/applications",
                metadata={"application_id": app_id, "stage": update_dict["stage"]},
            )
        except Exception:
            pass

    # Phase 54.11 — active cache invalidation: any change that affects
    # the pipeline view (stage move, note, revenue, deletion etc.) must
    # purge the cached snapshot so admins see the change instantly
    # instead of waiting up to 60s for natural TTL expiry.
    _bust_pipeline_cache()

    return ApplicationResponse(**updated_application)


@applications_router.post("/applications/{app_id}/employer-approval")
async def employer_approve_candidate(
    app_id: str,
    req: CandidateApprovalRequest,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Employer approves or rejects a candidate shortlisted by a recruiter.
    
    Flow: Recruiter Shortlists → Employer Approves/Rejects → Moves Forward
    - approve: stage moves from 'shortlisted' to 'employer_approved'
    - reject: stage moves to 'employer_rejected'
    """
    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    current_stage = application.get("stage", "applied")
    if current_stage != "shortlisted":
        raise HTTPException(
            status_code=400,
            detail=f"Can only approve/reject candidates at 'shortlisted' stage. Current stage: {current_stage}"
        )
    
    if req.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")
    
    now = datetime.now(timezone.utc).isoformat()
    new_stage = "employer_approved" if req.action == "approve" else "employer_rejected"
    
    update_fields = {
        "stage": new_stage,
        "employer_approval": req.action + "d",  # "approved" or "rejected"
        "employer_approval_by": current_user["id"],
        "employer_approval_by_name": current_user["name"],
        "employer_approval_at": now,
        "employer_approval_reason": req.reason,
        "updated_at": now,
    }
    
    await db.applications.update_one({"id": app_id}, {"$set": update_fields})
    
    # Log pipeline event
    from services.pipeline_events import log_pipeline_event
    await log_pipeline_event(
        candidate_id=application.get("candidate_id", ""),
        mandate_id=application.get("job_id", ""),
        application_id=app_id,
        previous_stage=current_stage,
        new_stage=new_stage,
        source="employer_approval",
        user_id=current_user.get("id", ""),
        user_name=current_user.get("name", ""),
    )
    
    # Sync to tracker
    from services.tracker_sync import sync_pipeline_to_tracker
    await sync_pipeline_to_tracker(
        application_id=app_id,
        new_stage=new_stage,
        user_id=current_user.get("id", ""),
        user_name=current_user.get("name", ""),
    )
    
    # Update governance history
    if application.get("candidate_id"):
        outcome = "employer_rejected" if req.action == "reject" else None
        await update_application_in_history(
            application["candidate_id"], app_id, new_stage, outcome
        )
    
    logger.info(f"Employer {current_user['name']} {req.action}d candidate in application {app_id}")
    
    # Log activity
    action_type = ACTION_APPROVAL if req.action == "approve" else ACTION_REJECTED
    await log_activity(
        candidate_id=application.get("candidate_id", ""), action=action_type,
        description=f"Employer {req.action}d candidate for {application.get('job_title', 'a job')}",
        performed_by=current_user.get("id"), performed_by_name=current_user.get("name"),
        performed_by_role=current_user.get("role"),
        candidate_name=application.get("candidate_name"),
        details={"action": req.action, "reason": req.reason, "application_id": app_id},
    )

    updated = await db.applications.find_one({"id": app_id}, {"_id": 0})
    return {
        "success": True,
        "message": f"Candidate {req.action}d successfully",
        "application": {k: v for k, v in updated.items() if k != "_id"},
    }




@applications_router.delete("/applications/{app_id}")
async def delete_application(
    app_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Remove candidate from pipeline (Admin only).
    
    Soft delete: Sets status to 'removed' and preserves data for audit.
    This removes the candidate from the job pipeline but:
    - Does NOT delete the candidate from the data bank
    - Does NOT delete the candidate's user account
    - Preserves audit trail
    
    Use cases:
    - Duplicate application cleanup
    - Candidate requested removal
    - Data quality corrections
    """
    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Soft delete - mark as removed
    await db.applications.update_one(
        {"id": app_id},
        {"$set": {
            "stage": "removed",
            "status": "removed",
            "removed_at": now,
            "removed_by": current_user["id"],
            "removed_by_name": current_user.get("name"),
            "updated_at": now
        }}
    )
    
    # Update candidate history if exists
    if application.get("candidate_id"):
        await update_application_in_history(
            application["candidate_id"],
            app_id,
            "removed",
            "removed"
        )
    
    # Audit log
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "entity_type": "application",
        "entity_id": app_id,
        "action": "removed_from_pipeline",
        "changed_by": current_user["id"],
        "changed_by_name": current_user.get("name"),
        "changed_by_role": current_user["role"],
        "timestamp": now,
        "details": {
            "candidate_name": application.get("candidate_name"),
            "candidate_email": application.get("candidate_email"),
            "job_id": application.get("job_id"),
            "previous_stage": application.get("stage")
        }
    })

    _bust_pipeline_cache()  # Phase 54.11

    return {
        "message": "Candidate removed from pipeline successfully",
        "application_id": app_id,
        "candidate_name": application.get("candidate_name")
    }


def _bust_pipeline_cache():
    """Phase 54.11 — fire-and-forget pipeline cache invalidation. Used
    by every write endpoint that affects the pipeline view."""
    try:
        from services.cache import cache
        cache.invalidate_pipeline_cache()
    except Exception:
        pass


@applications_router.post("/applications/{app_id}/notes")
async def add_note(app_id: str, note_data: NoteCreate, current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))):
    """Add note to application"""
    note = {
        "id": str(uuid.uuid4()),
        "content": note_data.content,
        "author_id": current_user["id"],
        "author_name": current_user["name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.applications.update_one(
        {"id": app_id},
        {"$push": {"notes": note}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Log activity for note
    app = await db.applications.find_one({"id": app_id}, {"_id": 0, "candidate_id": 1, "candidate_name": 1, "job_title": 1})
    if app:
        await log_activity(
            candidate_id=app.get("candidate_id", ""), action=ACTION_NOTE_ADDED,
            description=f"Note added on application for {app.get('job_title', 'a job')}",
            performed_by=current_user.get("id"), performed_by_name=current_user.get("name"),
            performed_by_role=current_user.get("role"),
            candidate_name=app.get("candidate_name"),
            details={"application_id": app_id, "note_preview": note_data.content[:100]},
        )

    _bust_pipeline_cache()  # Phase 54.11
    return {"message": "Note added successfully", "note": note}


@applications_router.put("/applications/{app_id}/details")
async def update_application_details(
    app_id: str, 
    update_data: ApplicationDetailUpdate, 
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Controlled editing of applicant details (salary, notice period, skills, experience summary).
    
    Data Precedence: Candidate self-edit > Employer edit > Recruiter edit > Resume parsing
    - Manual edits override parsed data
    - Resume parsing will NEVER overwrite manual edits (manually_edited flag)
    
    All edits are logged with full audit trail.
    """
    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    now = datetime.now(timezone.utc).isoformat()
    update_dict = {}
    audit_entries = []
    
    editable_fields = {
        "current_salary": update_data.current_salary,
        "notice_period": update_data.notice_period,
        "skills": update_data.skills,
        "experience_summary": update_data.experience_summary
    }
    
    for field, new_value in editable_fields.items():
        if new_value is not None:
            old_value = application.get(field)
            
            if old_value != new_value:
                update_dict[field] = new_value
                
                audit_entry = {
                    "field": field,
                    "old_value": old_value,
                    "new_value": new_value,
                    "updated_by_id": current_user["id"],
                    "updated_by_name": current_user["name"],
                    "updated_by_role": current_user["role"],
                    "timestamp": now
                }
                audit_entries.append(audit_entry)
    
    if not update_dict:
        return {"message": "No changes detected", "application_id": app_id}
    
    # Set metadata
    update_dict["updated_at"] = now
    update_dict["manually_edited"] = True
    update_dict["last_edited_by"] = {
        "name": current_user["name"],
        "role": current_user["role"],
        "user_id": current_user["id"],
        "timestamp": now
    }
    
    # Update application with audit trail
    result = await db.applications.update_one(
        {"id": app_id},
        {
            "$set": update_dict,
            "$push": {"edit_history": {"$each": audit_entries}}
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Also update candidate_bank if the candidate exists there
    if application.get("candidate_id"):
        candidate_update = {}
        audit_fields = []
        if "current_salary" in update_dict:
            candidate_update["current_salary"] = update_dict["current_salary"]
            audit_fields.append("current_salary")
        if "notice_period" in update_dict:
            candidate_update["notice_period"] = update_dict["notice_period"]
            audit_fields.append("notice_period")
        if "skills" in update_dict:
            candidate_update["skills"] = update_dict["skills"]
        if "experience_summary" in update_dict:
            candidate_update["summary"] = update_dict["experience_summary"]
        
        if candidate_update:
            candidate_update["updated_at"] = now
            candidate_update["manually_edited"] = True
            candidate_update["last_profile_updated_at"] = now
            candidate_update["last_updated_by"] = current_user["id"]
            await db.candidate_bank.update_one(
                {"id": application["candidate_id"]},
                {"$set": candidate_update}
            )
            
            # Data Governance: Add audit entries for mandatory field changes
            if audit_fields:
                candidate = await db.candidate_bank.find_one({"id": application["candidate_id"]}, {"_id": 0})
                if candidate:
                    for field in audit_fields:
                        old_entry = next((e for e in audit_entries if e["field"] == field), None)
                        if old_entry:
                            profile_audit = create_profile_audit_entry(
                                field, old_entry["old_value"], old_entry["new_value"],
                                current_user["id"], current_user["name"], current_user["role"],
                                "application_edit"
                            )
                            await db.candidate_bank.update_one(
                                {"id": application["candidate_id"]},
                                {"$push": {"profile_update_audit": profile_audit}}
                            )
    
    updated_application = await db.applications.find_one({"id": app_id}, {"_id": 0})

    _bust_pipeline_cache()  # Phase 54.11
    return {
        "message": "Application details updated successfully",
        "application_id": app_id,
        "changes": [
            {"field": e["field"], "old_value": e["old_value"], "new_value": e["new_value"]}
            for e in audit_entries
        ],
        "updated_by": {
            "name": current_user["name"],
            "role": current_user["role"]
        },
        "application": ApplicationResponse(**updated_application)
    }


@applications_router.get("/applications/{app_id}/edit-history")
async def get_application_edit_history(
    app_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Get the full edit history (audit trail) for an application."""
    application = await db.applications.find_one({"id": app_id}, {"_id": 0, "edit_history": 1, "last_edited_by": 1})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    return {
        "application_id": app_id,
        "edit_history": application.get("edit_history", []),
        "last_edited_by": application.get("last_edited_by")
    }


# ============== JOB APPLICANTS (Per-Job Review Screen) ==============

@applications_router.get("/jobs/{job_id}/applicants")
async def get_job_applicants(
    job_id: str, 
    stage: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Get all applicants for a specific job with enriched data for review.
    Returns candidate details, match scores, must-have indicators, salary, and notice period.
    """
    # Verify job exists and user has access
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # For employers, verify they own the job or it belongs to one of their teams
    if current_user["role"] == "employer":
        is_owner = job.get("posted_by") == current_user["id"]
        is_team_job = False
        if not is_owner:
            team_ids_cursor = db.teams.find({"employer_id": current_user["id"]}, {"_id": 0, "id": 1})
            team_ids = [t["id"] async for t in team_ids_cursor]
            is_team_job = job.get("team_id") in team_ids if team_ids else False
        if not is_owner and not is_team_job:
            raise HTTPException(status_code=403, detail="Not authorized to view applicants for this job")
    
    # Build query
    query = {"job_id": job_id}
    if stage:
        query["stage"] = stage
    else:
        # Apply pipeline display filter (hide extension clutter + stale rejections)
        from services.pipeline_events import pipeline_display_filter
        query = {"$and": [query, pipeline_display_filter()]}

    # Get all applications for this job
    applications = await db.applications.find(query, {"_id": 0}).to_list(1000)
    
    # Parse job requirements for must-have matching
    job_requirements = []
    if job.get("requirements"):
        job_requirements = [r.strip().lower() for r in job.get("requirements", "").split(",") if r.strip()]
    
    enriched_applicants = []
    
    for app in applications:
        # Get additional candidate data from candidate_bank if available
        candidate_data = await db.candidate_bank.find_one(
            {"$or": [
                {"id": app.get("candidate_id")},
                {"email": app.get("candidate_email")}
            ]},
            {"_id": 0}
        )
        
        # Calculate match score based on skills overlap
        app_skills = app.get("skills") or (candidate_data.get("skills") if candidate_data else []) or []
        app_skills_lower = [s.lower() for s in app_skills]
        
        # Calculate must-haves met
        must_haves_met = []
        matched_requirements = 0
        for req in job_requirements:
            is_met = any(req in skill or skill in req for skill in app_skills_lower)
            must_haves_met.append({"requirement": req, "met": is_met})
            if is_met:
                matched_requirements += 1
        
        # Calculate match score (percentage of requirements met)
        match_score = int((matched_requirements / len(job_requirements) * 100)) if job_requirements else 0
        
        # Get career stability from candidate_bank or calculate
        career_stability = None
        if candidate_data and candidate_data.get("experience"):
            career_stability = calculate_career_stability(candidate_data.get("experience", []))
        
        # Build enriched response
        enriched = {
            "id": app.get("id"),
            "job_id": app.get("job_id"),
            "candidate_id": app.get("candidate_id"),
            "candidate_name": app.get("candidate_name") or (candidate_data.get("name") if candidate_data else None),
            "candidate_email": app.get("candidate_email") or (candidate_data.get("email") if candidate_data else None),
            "candidate_phone": app.get("candidate_phone") or (candidate_data.get("phone") if candidate_data else None),
            "headline": app.get("headline") or (candidate_data.get("headline") if candidate_data else None),
            "summary": candidate_data.get("summary") if candidate_data else None,
            "experience_summary": app.get("experience_summary") or (candidate_data.get("summary") if candidate_data else None),
            "skills": app_skills,
            "experience_years": app.get("experience_years") or (candidate_data.get("experience_years") if candidate_data else None),
            "location": app.get("location") or (candidate_data.get("location") if candidate_data else None),
            "current_salary": app.get("current_salary") or (candidate_data.get("current_salary") if candidate_data else None),
            "notice_period": app.get("notice_period") or (candidate_data.get("notice_period") if candidate_data else None),
            "resume_url": app.get("resume_url") or (candidate_data.get("resume_url") if candidate_data else None),
            "r2_metadata": app.get("r2_metadata") or (candidate_data.get("r2_metadata") if candidate_data else None),
            "cover_letter": app.get("cover_letter"),
            "stage": app.get("stage", "sourced"),
            "match_score": match_score,
            "must_haves_met": must_haves_met,
            "career_stability": career_stability,
            "applied_at": app.get("applied_at") or app.get("created_at"),
            "updated_at": app.get("updated_at"),
            "notes": app.get("notes", []),
            "edit_history": app.get("edit_history", []),
            "last_edited_by": app.get("last_edited_by"),
            "manually_edited": app.get("manually_edited", False),
            "current_employer": app.get("current_employer") or (candidate_data.get("current_employer") if candidate_data else None),
            "designation": app.get("designation") or (candidate_data.get("designation") if candidate_data else None),
            "industry": app.get("industry") or (candidate_data.get("industry") if candidate_data else None),
            "education": app.get("education") or (candidate_data.get("education") if candidate_data else None),
            "ug_course": app.get("ug_course") or (candidate_data.get("ug_course") if candidate_data else None),
            "expected_salary": app.get("expected_salary") or (candidate_data.get("expected_salary") if candidate_data else None),
        }
        
        enriched_applicants.append(enriched)
    
    # Sort by match score (highest first), then by applied date
    enriched_applicants.sort(key=lambda x: (-(x.get("match_score") or 0), x.get("applied_at") or ""))
    
    return {
        "job": {
            "id": job.get("id"),
            "title": job.get("title"),
            "location": job.get("location"),
            "job_type": job.get("job_type"),
            "salary_min": job.get("salary_min"),
            "salary_max": job.get("salary_max"),
            "requirements": job.get("requirements"),
            "applicant_count": len(applications)
        },
        "applicants": enriched_applicants,
        "stage_counts": {
            "sourced": sum(1 for a in applications if a.get("stage") == "sourced"),
            "submitted_to_client": sum(1 for a in applications if a.get("stage") == "submitted_to_client"),
            "shortlisted": sum(1 for a in applications if a.get("stage") == "shortlisted"),
            "interview": sum(1 for a in applications if a.get("stage") == "interview"),
            "offered": sum(1 for a in applications if a.get("stage") == "offered"),
            "hired": sum(1 for a in applications if a.get("stage") == "hired"),
            "joined": sum(1 for a in applications if a.get("stage") == "joined"),
            "rejected": sum(1 for a in applications if a.get("stage") == "rejected"),
            "on_hold": sum(1 for a in applications if a.get("stage") == "on_hold"),
        }
    }


# ============== CANDIDATE MANAGEMENT (Admin/Recruiter) ==============

@applications_router.get("/candidates", response_model=List[CandidateProfile])
async def get_candidates(current_user: dict = Depends(require_role(["admin", "recruiter", "employer"]))):
    """Get all candidate profiles"""
    profiles = await db.candidate_profiles.find({}, {"_id": 0}).to_list(1000)
    return [CandidateProfile(**p) for p in profiles]


@applications_router.get("/candidates/{candidate_id}", response_model=CandidateProfile)
async def get_candidate(candidate_id: str, current_user: dict = Depends(require_role(["admin", "recruiter", "employer"]))):
    """Get single candidate profile"""
    profile = await db.candidate_profiles.find_one({"user_id": candidate_id}, {"_id": 0})
    if not profile:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return CandidateProfile(**profile)


# ============== AI MATCHING ENGINE ==============

@applications_router.post("/ai/parse-resume")
async def ai_parse_resume(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Parse resume using AI and optionally add to candidate data bank"""
    if not file.filename.lower().endswith(('.pdf', '.doc', '.docx', '.txt')):
        raise HTTPException(status_code=400, detail="Only PDF, DOC, DOCX, TXT files allowed")
    
    # Save file temporarily
    file_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix
    temp_path = UPLOAD_DIR / f"temp_{file_id}{file_ext}"
    
    async with aiofiles.open(temp_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    # Extract text
    if file_ext.lower() == '.pdf':
        resume_text = extract_text_from_pdf(temp_path)
    else:
        async with aiofiles.open(temp_path, 'r', errors='ignore') as f:
            resume_text = await f.read()
    
    if not resume_text.strip():
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Could not extract text from file")
    
    # Parse with AI
    result = await parse_resume_with_ai(resume_text)

    if not result["success"]:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=result.get("error", "Parsing failed"))

    # Generate fingerprint
    fingerprint = generate_resume_fingerprint(resume_text)
    result["data"]["resume_fingerprint"] = fingerprint

    temp_path.unlink(missing_ok=True)

    return {"success": True, "parsed_data": result["data"]}


@applications_router.post("/ai/parse-jd")
async def ai_parse_job_description(
    jd_text: str = Form(None),
    file: UploadFile = File(None),
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Parse job description using AI"""
    text_to_parse = jd_text
    
    if file:
        file_ext = Path(file.filename).suffix
        temp_path = UPLOAD_DIR / f"temp_jd_{uuid.uuid4()}{file_ext}"
        
        async with aiofiles.open(temp_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        if file_ext.lower() == '.pdf':
            text_to_parse = extract_text_from_pdf(temp_path)
        else:
            async with aiofiles.open(temp_path, 'r', errors='ignore') as f:
                text_to_parse = await f.read()
        
        temp_path.unlink(missing_ok=True)
    
    if not text_to_parse or not text_to_parse.strip():
        raise HTTPException(status_code=400, detail="No job description text provided")

    result = await parse_job_description_with_ai(text_to_parse)

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Parsing failed"))

    return {"success": True, "parsed_data": result["data"]}


@applications_router.post("/matching/find-candidates", response_model=List[MatchResult])
async def find_matching_candidates(
    match_req: MatchRequest,
    request: Request,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Find candidates matching job requirements.

    Two modes controlled by `match_mode` / `quick_match`:
      * **quick** (default) — zero LLM calls; keyword + semantic scoring. ~1-3 s.
      * **full_ai** — launches a background job that uses LLM per candidate.
        Returns an empty list with a header `X-Match-Job-Id` for polling.

    Rate limited: 10 requests per minute per user.
    """
    import time
    from fastapi.responses import JSONResponse

    # FAST PATH: Check cache BEFORE rate limiter (avoids external Redis call)
    cache_key = _match_cache_key(match_req)
    if cache_key in _match_cache:
        cached_results, cached_at = _match_cache[cache_key]
        if time.time() - cached_at < _MATCH_CACHE_TTL:
            return JSONResponse(content=cached_results)

    # Thundering herd prevention: if another request is computing the same key, wait
    if cache_key not in _match_locks:
        _match_locks[cache_key] = asyncio.Lock()
    lock = _match_locks[cache_key]

    if lock.locked():
        async with lock:
            if cache_key in _match_cache:
                cached_results, cached_at = _match_cache[cache_key]
                if time.time() - cached_at < _MATCH_CACHE_TTL:
                    return JSONResponse(content=cached_results)

    await lock.acquire()

    # Rate limit only for actual computation (not cache hits)
    from services.rate_limiter import rate_limiter
    rate_limiter.check_rate_limit(request, "ai_match")

    # Limit concurrent matching operations to prevent DB connection storms
    try:
        await asyncio.wait_for(_MATCH_SEMAPHORE.acquire(), timeout=15.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Server busy. Please retry in a few seconds.")

    # Resolve mode: match_mode takes precedence over quick_match
    if match_req.match_mode == "full_ai":
        use_quick = False
    elif match_req.match_mode == "quick":
        use_quick = True
    elif match_req.quick_match is not None:
        use_quick = match_req.quick_match
    else:
        use_quick = True  # default to quick for performance

    start_time = time.time()

    # ---- Resolve job data (FAST — no LLM) ----
    job = None
    if match_req.job_id:
        job = await db.jobs.find_one({"id": match_req.job_id}, {"_id": 0})
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

    # Fast JD parsing — never calls LLM
    job_data = parse_job_requirements_fast(
        job_doc=job,
        jd_text=match_req.jd_text,
    )
    if not job_data.get("required_skills") and not job_data.get("key_requirements_summary"):
        raise HTTPException(status_code=400, detail="Could not extract job requirements. Provide a job_id or jd_text.")

    logger.info(f"[MATCH] JD parsed (fast) in {time.time() - start_time:.2f}s — skills={len(job_data.get('required_skills', []))}")

    # ---- STAGE 1: Database pre-filtering (same for both modes) ----
    stage1_start = time.time()
    required_skills = job_data.get("required_skills") or []
    preferred_skills = job_data.get("preferred_skills") or []
    all_skills = required_skills + preferred_skills

    # Merge keyword into the search if provided
    if match_req.keyword:
        keyword_terms = [k.strip() for k in match_req.keyword.split(",") if k.strip()]
        all_skills = list(set(all_skills + keyword_terms))

    min_exp = job_data.get("experience_min") or match_req.min_experience
    max_exp = job_data.get("experience_max") or match_req.max_experience
    location = match_req.must_have_location or job_data.get("location")

    MAX_CANDIDATES = 100
    pre_filtered = []

    # Try Atlas Search first
    if all_skills:
        try:
            search_query = " ".join(all_skills[:10])
            atlas_pipeline = [
                {"$search": {
                    "index": "candidate_search",
                    "compound": {
                        "should": [
                            {"text": {"query": search_query, "path": "skills", "fuzzy": {"maxEdits": 1}, "score": {"boost": {"value": 3}}}},
                            {"text": {"query": search_query, "path": "summary", "fuzzy": {"maxEdits": 2}, "score": {"boost": {"value": 2}}}},
                            {"text": {"query": search_query, "path": "headline", "fuzzy": {"maxEdits": 1}, "score": {"boost": {"value": 2}}}},
                            {"text": {"query": search_query, "path": ["designation", "current_employer", "industry"], "fuzzy": {"maxEdits": 1}, "score": {"boost": {"value": 1.5}}}},
                            {"text": {"query": search_query, "path": "raw_profile_text", "fuzzy": {"maxEdits": 2}, "score": {"boost": {"value": 1}}}},
                        ],
                        "minimumShouldMatch": 1,
                    },
                }},
                {"$addFields": {"search_score": {"$meta": "searchScore"}}},
            ]
            exp_match = {}
            if min_exp is not None:
                exp_match["experience_years"] = {"$gte": min_exp}
            if max_exp is not None:
                exp_match.setdefault("experience_years", {})["$lte"] = max_exp + 2
            if exp_match:
                atlas_pipeline.append({"$match": exp_match})
            if location and match_req.must_have_location:
                atlas_pipeline.append({"$match": {"location": {"$regex": location, "$options": "i"}}})
            atlas_pipeline += [
                {"$sort": {"search_score": -1}},
                {"$limit": MAX_CANDIDATES},
                {"$project": {"_id": 0, "id": 1, "name": 1, "email": 1, "skills": 1,
                              "experience_years": 1, "education": 1, "location": 1,
                              "summary": 1, "headline": 1, "designation": 1,
                              "it_skills": 1, "source": 1, "created_by": 1,
                              "search_score": 1, "embedding": 1,
                              "phone": 1, "current_employer": 1, "current_salary": 1,
                              "expected_salary": 1, "notice_period": 1, "industry": 1}},
            ]
            pre_filtered = await db.candidate_bank.aggregate(atlas_pipeline, allowDiskUse=True).to_list(MAX_CANDIDATES)
            logger.info(f"[MATCH] Atlas Search: {len(pre_filtered)} candidates in {time.time() - stage1_start:.2f}s")
        except Exception as e:
            logger.warning(f"[MATCH] Atlas Search failed, using fallback: {e}")
            pre_filtered = []

    # Fallback: optimized query — only searches indexed/small fields (NOT raw_profile_text)
    if not pre_filtered:
        pipeline = []
        match_cond = {}
        if min_exp is not None or max_exp is not None:
            ef = {}
            if min_exp is not None:
                ef["$gte"] = min_exp
            if max_exp is not None:
                ef["$lte"] = max_exp + 2
            if ef:
                match_cond["experience_years"] = ef
        if location and match_req.must_have_location:
            match_cond["location"] = {"$regex": location, "$options": "i"}
        if match_cond:
            pipeline.append({"$match": match_cond})
        if all_skills:
            # Only search skills array and designation — NOT raw_profile_text (too slow on 75K+ docs)
            skills_pattern = "|".join(all_skills[:8])
            pipeline.append({"$match": {"$or": [
                {"skills": {"$regex": skills_pattern, "$options": "i"}},
                {"designation": {"$regex": skills_pattern, "$options": "i"}},
                {"headline": {"$regex": skills_pattern, "$options": "i"}},
            ]}})
        pipeline += [
            {"$addFields": {"skill_match_count": {"$size": {"$ifNull": [{"$setIntersection": [
                {"$map": {"input": {"$ifNull": ["$skills", []]}, "as": "s", "in": {"$toLower": "$$s"}}},
                [s.lower() for s in all_skills] if all_skills else [],
            ]}, []]}}}},
            {"$sort": {"skill_match_count": -1, "experience_years": -1}},
            {"$limit": MAX_CANDIDATES},
            {"$project": {"_id": 0, "id": 1, "name": 1, "email": 1, "skills": 1,
                          "experience_years": 1, "education": 1, "location": 1,
                          "summary": 1, "headline": 1, "designation": 1,
                          "it_skills": 1, "source": 1, "created_by": 1,
                          "skill_match_count": 1, "embedding": 1,
                          "phone": 1, "current_employer": 1, "current_salary": 1,
                          "expected_salary": 1, "notice_period": 1, "industry": 1}},
        ]
        try:
            pre_filtered = await db.candidate_bank.aggregate(pipeline, allowDiskUse=True).to_list(MAX_CANDIDATES)
        except Exception as e:
            logger.warning(f"[MATCH] Aggregation fallback failed: {e}")
            simple_q = {}
            if min_exp is not None:
                simple_q["experience_years"] = {"$gte": min_exp}
            pre_filtered = await db.candidate_bank.find(
                simple_q, {"_id": 0, "id": 1, "name": 1, "email": 1, "skills": 1,
                            "experience_years": 1, "education": 1, "location": 1,
                            "summary": 1, "headline": 1, "designation": 1,
                            "it_skills": 1, "source": 1, "created_by": 1, "embedding": 1,
                            "phone": 1, "current_employer": 1, "current_salary": 1,
                            "expected_salary": 1, "notice_period": 1, "industry": 1}
            ).sort("experience_years", -1).limit(MAX_CANDIDATES).to_list(MAX_CANDIDATES)

    stage1_time = time.time() - stage1_start
    logger.info(f"[MATCH] Stage 1 done: {len(pre_filtered)} candidates in {stage1_time:.2f}s")

    if not pre_filtered:
        return []

    # ---- Apply must-have hard filters ----
    must_have = {}
    if match_req.must_have_location:
        must_have["location"] = match_req.must_have_location
    if match_req.must_have_qualification:
        must_have["required_qualification"] = match_req.must_have_qualification
    if match_req.must_have_skills:
        must_have["mandatory_skills"] = match_req.must_have_skills
    if match_req.min_experience is not None:
        must_have["min_experience"] = match_req.min_experience
    if match_req.max_experience is not None:
        must_have["max_experience"] = match_req.max_experience

    # Batch fetch creator roles (skip for quick match to minimize DB hits)
    creator_roles = {}
    if not use_quick:
        creator_ids = list({c.get("created_by") for c in pre_filtered if c.get("created_by")})
        if creator_ids:
            creators = await db.users.find({"id": {"$in": creator_ids}}, {"_id": 0, "id": 1, "role": 1}).to_list(len(creator_ids))
            creator_roles = {c["id"]: c.get("role") for c in creators}

    filtered_candidates = []
    filtered_out_results = []
    for cand in pre_filtered:
        if must_have:
            fr = apply_must_have_filters(cand, must_have)
            if not fr["passed"]:
                filtered_out_results.append(MatchResult(
                    candidate_id=cand["id"], candidate_name=cand["name"],
                    candidate_email=cand.get("email") or "", score=0, filtered_out=True,
                    filter_reason=fr["reason"], explanation=f"Excluded: {fr['reason']}",
                    source=cand.get("source", "unknown"),
                    source_role=creator_roles.get(cand.get("created_by")),
                    phone=cand.get("phone"),
                    designation=cand.get("designation"),
                    headline=cand.get("headline"),
                    current_employer=cand.get("current_employer"),
                    location=cand.get("location"),
                    experience_years=cand.get("experience_years"),
                    current_salary=cand.get("current_salary"),
                    expected_salary=cand.get("expected_salary"),
                    notice_period=cand.get("notice_period"),
                    industry=cand.get("industry"),
                    education=cand.get("education"),
                    skills=cand.get("skills") or [],
                ))
                continue
        filtered_candidates.append(cand)

    # ---- Generate job embedding for semantic search (skip in quick mode for speed) ----
    job_embedding = None
    if match_req.semantic_search and not use_quick:
        try:
            job_text = f"{job_data.get('title', '')} | Skills: {', '.join(all_skills[:15])}"
            job_embedding = await embedding_service.generate_embedding(job_text)
        except Exception as e:
            logger.warning(f"[MATCH] Job embedding failed: {e}")

    # ============== FULL AI MODE — background job ==============
    if not use_quick:
        match_job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Store pending job
        await db.match_jobs.insert_one({
            "id": match_job_id,
            "status": "processing",
            "progress": 0,
            "total_candidates": len(filtered_candidates),
            "scored_candidates": 0,
            "searched_by": current_user["id"],
            "job_id": match_req.job_id,
            "results": None,
            "error": None,
            "created_at": now,
        })

        async def _run_full_ai_matching():
            """Background coroutine — runs LLM scoring and stores results."""
            try:
                # Parse JD with LLM for richer data
                enriched_job_data = job_data
                if match_req.job_id and job:
                    jd_result = await parse_job_description_with_ai(
                        (job.get("description", "") + " " + job.get("requirements", "")).strip()
                    )
                    if jd_result["success"]:
                        enriched_job_data = jd_result["data"]
                elif match_req.jd_text:
                    jd_result = await parse_job_description_with_ai(match_req.jd_text)
                    if jd_result["success"]:
                        enriched_job_data = jd_result["data"]

                MAX_CONCURRENT = 5
                AI_TIMEOUT = 30
                sem = asyncio.Semaphore(MAX_CONCURRENT)
                scored = 0

                async def _score_one(c):
                    nonlocal scored
                    async with sem:
                        try:
                            mr = await asyncio.wait_for(
                                calculate_candidate_job_match(c, enriched_job_data, None),
                                timeout=AI_TIMEOUT,
                            )
                        except Exception:
                            mr = calculate_fast_match_score(c, enriched_job_data,
                                                           job_embedding, c.get("embedding"))
                        scored += 1
                        # Update progress periodically
                        if scored % 10 == 0 or scored == len(filtered_candidates):
                            await db.match_jobs.update_one(
                                {"id": match_job_id},
                                {"$set": {"scored_candidates": scored,
                                          "progress": int(scored / len(filtered_candidates) * 100)}},
                            )
                        sem_score = None
                        if job_embedding and c.get("embedding"):
                            sem_score = embedding_service.cosine_similarity(job_embedding, c["embedding"]) * 100
                        ai_score = mr.get("score", 0)
                        combined = int(ai_score * 0.7 + sem_score * 0.3) if sem_score else ai_score
                        expl = mr.get("explanation", "")
                        if sem_score:
                            expl += f" | Semantic: {sem_score:.0f}%"
                        return MatchResult(
                            candidate_id=c["id"], candidate_name=c["name"],
                            candidate_email=c["email"], score=combined,
                            skill_match_score=mr.get("skill_match_score"),
                            experience_match_score=mr.get("experience_match_score"),
                            semantic_score=round(sem_score, 1) if sem_score else None,
                            matched_skills=mr.get("matched_skills", []),
                            missing_skills=mr.get("missing_skills", []),
                            strengths=mr.get("strengths", []),
                            gaps=mr.get("gaps", []),
                            explanation=expl,
                            source=c.get("source", "unknown"),
                            source_role=creator_roles.get(c.get("created_by")),
                            phone=c.get("phone"),
                            designation=c.get("designation"),
                            headline=c.get("headline"),
                            current_employer=c.get("current_employer"),
                            location=c.get("location"),
                            experience_years=c.get("experience_years"),
                            current_salary=c.get("current_salary"),
                            expected_salary=c.get("expected_salary"),
                            notice_period=c.get("notice_period"),
                            industry=c.get("industry"),
                            education=c.get("education"),
                            skills=c.get("skills") or [],
                        )

                results = await asyncio.gather(*[_score_one(c) for c in filtered_candidates])
                all_results = list(results) + filtered_out_results
                all_results.sort(key=lambda x: (not x.filtered_out, x.score), reverse=True)

                await db.match_jobs.update_one(
                    {"id": match_job_id},
                    {"$set": {
                        "status": "completed",
                        "progress": 100,
                        "scored_candidates": len(filtered_candidates),
                        "results": [r.model_dump() for r in all_results[:match_req.limit]],
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )
            except Exception as exc:
                logger.error(f"[MATCH BG] Full AI job {match_job_id} failed: {exc}")
                await db.match_jobs.update_one(
                    {"id": match_job_id},
                    {"$set": {"status": "failed", "error": str(exc)}},
                )

        # Fire-and-forget background task
        asyncio.create_task(_run_full_ai_matching())

        _MATCH_SEMAPHORE.release()
        if lock.locked():
            lock.release()
        # Return immediate response with job_id in a header-like field
        return [MatchResult(
            candidate_id="__background_job__",
            candidate_name="Background AI Match Started",
            candidate_email=match_job_id,
            score=0,
            explanation=f"Full AI matching started as background job. Poll GET /api/matching/jobs/{match_job_id}/status for results.",
        )]

    # ============== QUICK MATCH MODE — zero LLM calls ==============
    stage2_start = time.time()
    quick_results = []
    for cand in filtered_candidates:
        fs = calculate_fast_match_score(
            cand, job_data,
            job_embedding=job_embedding,
            candidate_embedding=cand.get("embedding"),
        )
        quick_results.append(MatchResult(
            candidate_id=cand["id"], candidate_name=cand["name"],
            candidate_email=cand.get("email") or "",
            score=fs["score"],
            skill_match_score=fs.get("skill_match_score"),
            experience_match_score=fs.get("experience_match_score"),
            ctc_fit_score=fs.get("ctc_fit_score"),
            location_fit_score=fs.get("location_fit_score"),
            notice_fit_score=fs.get("notice_fit_score"),
            stability_score=fs.get("stability_score"),
            tfidf_score=fs.get("tfidf_score"),
            semantic_score=fs.get("semantic_score"),
            is_maybe=fs.get("is_maybe"),
            data_completeness=fs.get("data_completeness"),
            matched_skills=fs.get("matched_skills", []),
            missing_skills=fs.get("missing_skills", []),
            explanation=fs["explanation"],
            source=cand.get("source", "unknown"),
            source_role=creator_roles.get(cand.get("created_by")),
            phone=cand.get("phone"),
            designation=cand.get("designation"),
            headline=cand.get("headline"),
            current_employer=cand.get("current_employer"),
            location=cand.get("location"),
            experience_years=cand.get("experience_years"),
            current_salary=cand.get("current_salary"),
            expected_salary=cand.get("expected_salary"),
            notice_period=cand.get("notice_period"),
            industry=cand.get("industry"),
            education=cand.get("education"),
            skills=cand.get("skills") or [],
        ))

    results = quick_results + filtered_out_results
    results.sort(key=lambda x: (not x.filtered_out, x.score), reverse=True)
    results = results[:match_req.limit]

    total_time = time.time() - start_time
    logger.info(f"[MATCH] Quick match done: {len(quick_results)} scored in {time.time() - stage2_start:.2f}s, total={total_time:.2f}s")

    # Store match history for Match History feature
    history_id = str(uuid.uuid4())
    top_results = [r.model_dump() for r in results if not r.filtered_out][:20]
    await db.match_results.insert_one({
        "id": history_id,
        "job_id": match_req.job_id,
        "jd_text": (match_req.jd_text or "")[:500],
        "searched_by": current_user["id"],
        "searched_by_name": current_user.get("name", ""),
        "searched_by_role": current_user["role"],
        "total_candidates_in_db": await db.candidate_bank.count_documents({}),
        "pre_filtered_count": len(pre_filtered),
        "ai_scored_count": len(filtered_candidates),
        "matched_count": len([r for r in results if r.score >= 50 and not r.filtered_out]),
        "mode": "quick",
        "job_title": job.get("title", "") if job else "Custom JD",
        "top_results": top_results,
        "filters": {
            "location": match_req.must_have_location,
            "skills": match_req.must_have_skills,
            "min_exp": match_req.min_experience,
            "max_exp": match_req.max_experience,
        },
        "stage1_time_seconds": round(stage1_time, 2),
        "total_time_seconds": round(total_time, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    _MATCH_SEMAPHORE.release()
    # Cache results as serialized dicts for fast JSONResponse return
    if len(_match_cache) > 100:
        _match_cache.clear()
    _match_cache[cache_key] = ([r.model_dump() for r in results], time.time())
    if lock.locked():
        lock.release()
    return results


@applications_router.get("/matching/jobs/{match_job_id}/status")
async def get_match_job_status(
    match_job_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Poll the status of a background Full AI matching job.
    Returns progress, status, and results when completed.
    """
    job = await db.match_jobs.find_one({"id": match_job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Match job not found")

    response = {
        "job_id": job["id"],
        "status": job.get("status", "pending"),
        "progress": job.get("progress", 0),
        "total_candidates": job.get("total_candidates", 0),
        "scored_candidates": job.get("scored_candidates", 0),
        "error": job.get("error"),
    }
    if job.get("status") == "completed" and job.get("results"):
        response["results"] = job["results"]
    return response


@applications_router.get("/matching/history")
async def get_match_history(
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Get past match search history for the current user.
    Admin sees all, employer/recruiter see their own.
    """
    query = {}
    if current_user["role"] in ("employer", "recruiter"):
        query["searched_by"] = current_user["id"]

    docs = await db.match_results.find(
        query,
        {"_id": 0, "id": 1, "job_id": 1, "job_title": 1, "jd_text": 1,
         "searched_by_name": 1, "searched_by_role": 1, "mode": 1,
         "matched_count": 1, "ai_scored_count": 1, "total_time_seconds": 1,
         "filters": 1, "timestamp": 1}
    ).sort("timestamp", -1).limit(100).to_list(100)

    return docs


@applications_router.get("/matching/history/{history_id}")
async def get_match_history_detail(
    history_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Get full results of a past match search.
    """
    doc = await db.match_results.find_one({"id": history_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Match history not found")

    # Access control
    if current_user["role"] in ("employer", "recruiter"):
        if doc.get("searched_by") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")

    return doc


@applications_router.post("/matching/shortlist")
async def shortlist_candidate_from_screening(
    req: ShortlistRequest,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Add a candidate from AI screening to a job's pipeline as a shortlisted applicant.
    Creates an application record with stage='shortlisted' and source='ai_screening'.
    """
    # Validate job exists
    job = await db.jobs.find_one({"id": req.job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Validate candidate exists in candidate bank
    candidate = await db.candidate_bank.find_one({"id": req.candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found in candidate bank")

    # Check if already applied/shortlisted for this job
    existing = await db.applications.find_one({
        "job_id": req.job_id,
        "$or": [
            {"candidate_id": req.candidate_id},
            {"candidate_email": (candidate.get("email") or "").lower()},
        ],
    })
    if existing:
        raise HTTPException(status_code=400, detail=f"Candidate already in pipeline for this job (stage: {existing.get('stage', 'unknown')})")

    # Get company name
    company = await db.companies.find_one({"id": job.get("company_id")}, {"name": 1, "_id": 0})
    company_name = company.get("name") if company else job.get("company_name", "Unknown")

    app_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    app_doc = {
        "id": app_id,
        "job_id": req.job_id,
        "candidate_id": req.candidate_id,
        "candidate_name": candidate.get("name", ""),
        "candidate_email": candidate.get("email", ""),
        "job_title": job.get("title"),
        "company_name": company_name,
        "cover_letter": None,
        "status": "active",
        "stage": "shortlisted",
        "source": "ai_screening",
        "shortlisted_by": current_user["id"],
        "shortlisted_by_name": current_user.get("name", ""),
        "shortlisted_by_role": current_user["role"],
        "notes": [{"text": req.notes, "by": current_user["name"], "at": now}] if req.notes else [],
        "edit_history": [],
        "current_salary": candidate.get("current_salary"),
        "expected_salary": candidate.get("expected_salary"),
        "notice_period": candidate.get("notice_period"),
        "location": candidate.get("location"),
        "experience_years": candidate.get("experience_years"),
        "skills": candidate.get("skills", []),
        "resume_url": candidate.get("resume_url"),
        "current_employer": candidate.get("current_employer"),
        "designation": candidate.get("designation"),
        "industry": candidate.get("industry"),
        "education": candidate.get("education"),
        "ug_course": candidate.get("ug_course"),
        "headline": candidate.get("headline"),
        "candidate_phone": candidate.get("phone"),
        "created_at": now,
        "updated_at": now,
    }

    await db.applications.insert_one(app_doc)

    # Increment applicant count on job
    await db.jobs.update_one({"id": req.job_id}, {"$inc": {"applicant_count": 1}})

    # Add to candidate's application history
    try:
        await add_application_to_history(req.candidate_id, {
            "id": app_id,
            "job_id": req.job_id,
            "job_title": job.get("title"),
            "company_name": company_name,
            "source": "ai_screening",
            "stage": "shortlisted",
            "applied_at": now,
        })
    except Exception:
        pass

    # Log activity for shortlist
    await log_activity(
        candidate_id=req.candidate_id, action=ACTION_SHORTLISTED,
        description=f"Shortlisted for {job.get('title', 'a job')} at {company_name}",
        performed_by=current_user.get("id"), performed_by_name=current_user.get("name"),
        performed_by_role=current_user.get("role"),
        candidate_name=candidate.get("name"),
        details={"job_id": req.job_id, "application_id": app_id, "source": "ai_screening"},
    )

    # LTR auto-capture — explicit shortlist is the strongest positive signal.
    try:
        from services.ltr_telemetry import auto_log_action
        asyncio.create_task(auto_log_action(
            user=current_user,
            candidate_id=req.candidate_id,
            action="shortlist",
            extra={"app_id": app_id, "job_id": req.job_id, "source": "matching_shortlist"},
        ))
    except Exception as _e:
        logger.debug(f"[applications] LTR auto-log skipped on shortlist: {_e}")

    return {
        "message": "Candidate shortlisted successfully",
        "application_id": app_id,
        "candidate_name": candidate.get("name"),
        "job_title": job.get("title"),
        "stage": "shortlisted",
    }


@applications_router.get("/matching/jobs-for-candidate", response_model=List[JobMatchForCandidate])
async def get_matching_jobs_for_candidate(
    current_user: dict = Depends(require_role(["candidate"]))
):
    """Get matching jobs for current candidate based on their profile"""
    
    # Get candidate from data bank
    candidate = await db.candidate_bank.find_one(
        {"linked_user_id": current_user["id"]},
        {"_id": 0}
    )
    
    if not candidate:
        # Fallback to candidate_profiles
        profile = await db.candidate_profiles.find_one(
            {"user_id": current_user["id"]},
            {"_id": 0}
        )
        if not profile:
            return []
        candidate = profile
    
    # Get active jobs
    jobs = await db.jobs.find({"status": "active"}, {"_id": 0}).to_list(100)
    
    results = []
    for job in jobs:
        # Parse job requirements
        jd_text = f"{job.get('title', '')} {job.get('description', '')} {job.get('requirements', '')}"
        jd_result = await parse_job_description_with_ai(jd_text)

        if not jd_result["success"]:
            continue

        job_data = jd_result["data"]
        match_result = await calculate_candidate_job_match(candidate, job_data)
        
        if match_result.get("score", 0) >= 30:  # Only show relevant matches
            results.append(JobMatchForCandidate(
                job_id=job["id"],
                job_title=job["title"],
                company_name=job.get("company_name"),
                location=job.get("location", ""),
                score=match_result.get("score", 0),
                explanation=match_result.get("explanation", ""),
                matched_skills=match_result.get("matched_skills", [])
            ))
    
    # Sort by score
    results.sort(key=lambda x: x.score, reverse=True)
    
    return results[:20]  # Return top 20 matches



# ── Link Candidate to Job ──────────────────────────────────────────────

@applications_router.post("/applications/link-candidate")
async def link_candidate_to_job(
    data: LinkCandidateRequest,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Link an existing candidate from the bank to a job as an application."""
    # Verify candidate exists
    candidate = await db.candidate_bank.find_one({"id": data.candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Verify job exists
    job = await db.jobs.find_one({"id": data.job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check if already linked (e.g. extension auto-captured this candidate earlier)
    existing = await db.applications.find_one(
        {"candidate_id": data.candidate_id, "job_id": data.job_id},
        {"_id": 0}
    )
    if existing:
        # Upgrade the existing row so it becomes visible in the pipeline.
        # The pipeline_display_filter() hides rows with source=extension_capture;
        # the user explicitly clicked "Add as Applicant", so this candidate is
        # no longer a silent auto-capture — mark it as a manual link.
        now_ts = datetime.now(timezone.utc).isoformat()
        upgrade = {
            "source": "candidate_bank",
            "manually_added_at": now_ts,
            "manually_added_by": current_user.get("id"),
            "updated_at": now_ts,
        }
        # If the previous stage was beyond 'sourced' (e.g. already interviewed),
        # leave it where it is; we only want to surface it in the board.
        if existing.get("stage") in (None, "", "sourced"):
            upgrade["stage"] = "sourced"
        await db.applications.update_one({"id": existing["id"]}, {"$set": upgrade})
        existing.update(upgrade)
        return {
            "message": "Candidate surfaced to pipeline",
            "application_id": existing["id"],
            "application": existing,
        }

    now = datetime.now(timezone.utc).isoformat()
    application_id = str(uuid.uuid4())

    application = {
        "id": application_id,
        "job_id": data.job_id,
        "candidate_id": data.candidate_id,
        "candidate_name": candidate.get("name", ""),
        "candidate_email": candidate.get("email", ""),
        "candidate_phone": candidate.get("phone", ""),
        "stage": "sourced",
        "status": "active",
        "source": "candidate_bank",
        "expected_salary": data.expected_salary,
        "created_by": current_user["id"],
        "created_at": now,
        "updated_at": now,
        "stage_history": [{
            "stage": "sourced",
            "moved_by": current_user["id"],
            "moved_by_name": current_user.get("name", ""),
            "timestamp": now,
        }],
    }

    await db.applications.insert_one(application)
    application.pop("_id", None)

    return {"message": "Candidate linked to job", "application_id": application_id, "application": application}
