"""
VHC Talent OS - Applications & AI Matching Routes
Handles all application lifecycle operations including CRUD, stage transitions,
AI screening, candidate-job matching, and audit history.
"""
import uuid
import logging
import re
import asyncio
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
import aiofiles

# Concurrency limiter for matching endpoint
_MATCH_SEMAPHORE = asyncio.Semaphore(20)  # Max 20 concurrent match operations

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

# Create router for applications endpoints
applications_router = APIRouter(prefix="/api", tags=["Applications"])

logger = logging.getLogger(__name__)


# ============== HELPER FUNCTIONS ==============

def extract_text_from_pdf(file_path: Path) -> str:
    """Extract text from PDF file"""
    import fitz
    try:
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return ""


def calculate_career_stability(experience: List[dict]) -> Dict[str, Any]:
    """Calculate career stability score based on job history"""
    if not experience:
        return {"score": "yellow", "quick_changes": 0, "avg_tenure_months": 0}
    
    quick_changes = 0  # Jobs with tenure < 12 months
    total_tenure = 0
    
    for job in experience:
        # Estimate tenure from dates if available
        start = job.get("start_date")
        end = job.get("end_date", "present")
        
        # If we can't calculate, assume average tenure
        tenure_months = 24  # Default assumption
        
        if start:
            # Simple calculation (could be improved)
            if isinstance(start, str) and "20" in start:
                try:
                    start_year = int(start.split("/")[-1] if "/" in start else start[:4])
                    if end == "present":
                        end_year = datetime.now().year
                    else:
                        end_year = int(end.split("/")[-1] if "/" in end else end[:4])
                    tenure_months = (end_year - start_year) * 12
                except (ValueError, IndexError, TypeError):
                    pass
        
        total_tenure += tenure_months
        if tenure_months < 12:
            quick_changes += 1
    
    avg_tenure = total_tenure / len(experience) if experience else 0
    
    # Score determination
    if quick_changes == 0 and avg_tenure >= 24:
        score = "green"
    elif quick_changes <= 1 and avg_tenure >= 12:
        score = "yellow"
    else:
        score = "red"
    
    return {
        "score": score,
        "quick_changes": quick_changes,
        "avg_tenure_months": round(avg_tenure)
    }


# ============== PYDANTIC MODELS ==============

class ApplicantReviewResponse(BaseModel):
    """Enhanced applicant data for review screen"""
    model_config = ConfigDict(extra="ignore")
    id: str
    job_id: str
    candidate_id: str
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_phone: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    experience_summary: Optional[str] = None
    skills: Optional[List[str]] = None
    experience_years: Optional[int] = None
    location: Optional[str] = None
    current_salary: Optional[int] = None
    notice_period: Optional[str] = None
    resume_url: Optional[str] = None
    cover_letter: Optional[str] = None
    stage: str = "applied"
    match_score: Optional[int] = None
    must_haves_met: Optional[List[Dict]] = None
    career_stability: Optional[Dict] = None
    applied_at: Optional[str] = None
    updated_at: Optional[str] = None
    notes: List[Dict] = []
    edit_history: List[Dict] = []
    last_edited_by: Optional[Dict] = None
    manually_edited: bool = False


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
    primary_dir = Path("/app/uploads")
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
        app_doc["notice_period"] = candidate_bank.get("notice_period")
        app_doc["location"] = candidate_bank.get("location")
        app_doc["experience_years"] = candidate_bank.get("experience_years")
        app_doc["skills"] = candidate_bank.get("skills", [])
        app_doc["resume_url"] = candidate_bank.get("resume_url")
    
    await db.applications.insert_one(app_doc)
    
    # Increment applicant count
    await db.jobs.update_one({"id": app_data.job_id}, {"$inc": {"applicant_count": 1}})
    
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


@applications_router.get("/applications", response_model=List[ApplicationResponse])
async def get_applications(job_id: Optional[str] = None, stage: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Get applications with role-based filtering"""
    query = {}
    
    if current_user["role"] == "candidate":
        query["candidate_id"] = current_user["id"]
    elif current_user["role"] == "employer":
        # Get employer's jobs
        jobs = await db.jobs.find({"posted_by": current_user["id"]}, {"id": 1, "_id": 0}).to_list(1000)
        job_ids = [j["id"] for j in jobs]
        query["job_id"] = {"$in": job_ids}
    
    if job_id:
        query["job_id"] = job_id
    if stage:
        query["stage"] = stage
    
    applications = await db.applications.find(query, {"_id": 0}).to_list(1000)
    return [ApplicationResponse(**a) for a in applications]


@applications_router.get("/applications/{app_id}", response_model=ApplicationResponse)
async def get_application(app_id: str, current_user: dict = Depends(get_current_user)):
    """Get single application"""
    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return ApplicationResponse(**application)


@applications_router.put("/applications/{app_id}", response_model=ApplicationResponse)
async def update_application(app_id: str, update_data: ApplicationUpdate, current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))):
    """Update application with stage tracking"""
    # Get current application for history tracking
    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.applications.update_one({"id": app_id}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Data Governance: Update candidate history if stage changed
    if "stage" in update_dict and application.get("candidate_id"):
        new_stage = update_dict["stage"]
        outcome = None
        if new_stage in ["hired", "rejected", "dropped"]:
            outcome = new_stage
        await update_application_in_history(
            application["candidate_id"],
            app_id,
            new_stage,
            outcome
        )
    
    updated_application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    return ApplicationResponse(**updated_application)


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
    
    return {
        "message": "Candidate removed from pipeline successfully",
        "application_id": app_id,
        "candidate_name": application.get("candidate_name")
    }


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
    
    # For employers, verify they own the job
    if current_user["role"] == "employer" and job.get("posted_by") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to view applicants for this job")
    
    # Build query
    query = {"job_id": job_id}
    if stage:
        query["stage"] = stage
    
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
            "stage": app.get("stage", "applied"),
            "match_score": match_score,
            "must_haves_met": must_haves_met,
            "career_stability": career_stability,
            "applied_at": app.get("applied_at") or app.get("created_at"),
            "updated_at": app.get("updated_at"),
            "notes": app.get("notes", []),
            "edit_history": app.get("edit_history", []),
            "last_edited_by": app.get("last_edited_by"),
            "manually_edited": app.get("manually_edited", False)
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
            "applied": sum(1 for a in applications if a.get("stage") == "applied"),
            "shortlisted": sum(1 for a in applications if a.get("stage") == "shortlisted"),
            "interview": sum(1 for a in applications if a.get("stage") == "interview"),
            "offered": sum(1 for a in applications if a.get("stage") == "offered"),
            "hired": sum(1 for a in applications if a.get("stage") == "hired"),
            "rejected": sum(1 for a in applications if a.get("stage") == "rejected"),
            "on_hold": sum(1 for a in applications if a.get("stage") == "on_hold"),
            "over_budget": sum(1 for a in applications if a.get("stage") == "over_budget"),
            "not_qualified": sum(1 for a in applications if a.get("stage") == "not_qualified")
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
    from services.rate_limiter import rate_limiter
    rate_limiter.check_rate_limit(request, "ai_match")

    import time

    # Limit concurrent matching operations to prevent resource exhaustion
    try:
        await asyncio.wait_for(_MATCH_SEMAPHORE.acquire(), timeout=15.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Server busy. Please retry in a few seconds.")

    try:
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
                            {"text": {"query": search_query, "path": "summary", "fuzzy": {"maxEdits": 2}, "score": {"boost": {"value": 1.5}}}},
                            {"text": {"query": search_query, "path": ["designation", "current_employer"], "fuzzy": {"maxEdits": 1}}},
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
                              "summary": 1, "source": 1, "created_by": 1,
                              "search_score": 1, "embedding": 1}},
            ]
            pre_filtered = await db.candidate_bank.aggregate(atlas_pipeline).to_list(MAX_CANDIDATES)
            logger.info(f"[MATCH] Atlas Search: {len(pre_filtered)} candidates in {time.time() - stage1_start:.2f}s")
        except Exception as e:
            logger.warning(f"[MATCH] Atlas Search failed, using fallback: {e}")
            pre_filtered = []

    # Fallback: regex-based query
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
            pipeline.append({"$match": {"$or": [
                {"skills": {"$regex": "|".join(all_skills[:5]), "$options": "i"}},
                {"summary": {"$regex": "|".join(all_skills[:3]), "$options": "i"}},
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
                          "summary": 1, "source": 1, "created_by": 1,
                          "skill_match_count": 1, "embedding": 1}},
        ]
        try:
            pre_filtered = await db.candidate_bank.aggregate(pipeline).to_list(MAX_CANDIDATES)
        except Exception as e:
            logger.warning(f"[MATCH] Aggregation fallback failed: {e}")
            simple_q = {}
            if min_exp is not None:
                simple_q["experience_years"] = {"$gte": min_exp}
            pre_filtered = await db.candidate_bank.find(
                simple_q, {"_id": 0, "id": 1, "name": 1, "email": 1, "skills": 1,
                            "experience_years": 1, "education": 1, "location": 1,
                            "summary": 1, "source": 1, "created_by": 1, "embedding": 1}
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

    # Batch fetch creator roles
    creator_ids = list({c.get("created_by") for c in pre_filtered if c.get("created_by")})
    creator_roles = {}
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
                    candidate_email=cand["email"], score=0, filtered_out=True,
                    filter_reason=fr["reason"], explanation=f"Excluded: {fr['reason']}",
                    source=cand.get("source", "unknown"),
                    source_role=creator_roles.get(cand.get("created_by")),
                ))
                continue
        filtered_candidates.append(cand)

    # ---- Generate job embedding for semantic search ----
    job_embedding = None
    if match_req.semantic_search:
        try:
            job_text = f"{job_data.get('title', '')} | Skills: {', '.join(all_skills[:15])}"
            job_embedding = await embedding_service.generate_embedding(job_text)
        except Exception as e:
            logger.warning(f"[MATCH] Job embedding failed: {e}")

    # ============== FULL AI MODE — background job ==============
    if not use_quick:
        import asyncio

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

        # Return immediate response with job_id in a header-like field
        # We return empty results list + include a special entry for the frontend
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
            candidate_email=cand["email"],
            score=fs["score"],
            skill_match_score=fs.get("skill_match_score"),
            experience_match_score=fs.get("experience_match_score"),
            semantic_score=fs.get("semantic_score"),
            matched_skills=fs.get("matched_skills", []),
            missing_skills=fs.get("missing_skills", []),
            explanation=fs["explanation"],
            source=cand.get("source", "unknown"),
            source_role=creator_roles.get(cand.get("created_by")),
        ))

    results = quick_results + filtered_out_results
    results.sort(key=lambda x: (not x.filtered_out, x.score), reverse=True)
    results = results[:match_req.limit]

    total_time = time.time() - start_time
    logger.info(f"[MATCH] Quick match done: {len(quick_results)} scored in {time.time() - stage2_start:.2f}s, total={total_time:.2f}s")

    # Analytics
    if match_req.job_id:
        await db.match_results.insert_one({
            "id": str(uuid.uuid4()),
            "job_id": match_req.job_id,
            "searched_by": current_user["id"],
            "searched_by_role": current_user["role"],
            "total_candidates_in_db": await db.candidate_bank.count_documents({}),
            "pre_filtered_count": len(pre_filtered),
            "ai_scored_count": len(filtered_candidates),
            "matched_count": len([r for r in results if r.score >= 50 and not r.filtered_out]),
            "mode": "quick",
            "stage1_time_seconds": round(stage1_time, 2),
            "total_time_seconds": round(total_time, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

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
