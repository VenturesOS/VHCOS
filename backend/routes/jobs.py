"""
VHC Talent OS - Jobs Routes
Handles all job-related operations including CRUD, career page control,
shareable links, JD parsing, and mandate assignments.
"""
import uuid
import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel, Field
import os
import aiofiles
import fitz  # PyMuPDF for PDF text extraction

# Import configuration
from config import db, UPLOAD_DIR

# Import models
from models import (
    JobCreate, JobResponse, JobUpdate, JobStateTransition
)

# Import utilities
from utils import get_current_user, require_role

# Import cache service
from services.cache import cache


# Create router for jobs endpoints
jobs_router = APIRouter(prefix="/api", tags=["Jobs"])


# ============== HELPER FUNCTIONS ==============

async def generate_job_public_id() -> str:
    """
    Generate a unique job public ID in format: VHC/YYYY/NNNN
    - Prefix: VHC
    - Year: Current calendar year
    - Sequence: 4-digit number, resets every year
    """
    current_year = datetime.now(timezone.utc).year
    
    # Use atomic findAndModify to get next sequence number
    counter = await db.job_sequences.find_one_and_update(
        {"year": current_year},
        {"$inc": {"sequence": 1}},
        upsert=True,
        return_document=True
    )
    
    sequence = counter.get("sequence", 1)
    
    # Format: VHC/YYYY/NNNN
    job_public_id = f"VHC/{current_year}/{sequence:04d}"
    
    return job_public_id


# ============== PYDANTIC MODELS (Local to this module) ==============

class CareerPageStatusUpdate(BaseModel):
    """Model for updating career page status"""
    new_status: str = Field(..., pattern="^(live|removed)$")
    reason: Optional[str] = None


class ShareableLinkUpdate(BaseModel):
    """Model for toggling shareable link status"""
    enabled: bool


class MandateShareableLinkUpdate(BaseModel):
    """Model for toggling mandate-level shareable link status"""
    enabled: bool


# ============== JOB CRUD ==============

@jobs_router.post("/jobs", response_model=JobResponse)
async def create_job(job_data: JobCreate, current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))):
    """
    Create a new job with approval workflow:
    - Admin/Employer: Job goes directly to 'active' status
    - Recruiter: Job goes to 'pending_approval' status, needs Employer/Admin approval
    """
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Generate unique job public ID (VHC/YYYY/NNNN format)
    job_public_id = await generate_job_public_id()
    
    # Determine company_id
    company_id = job_data.company_id or current_user.get("company_id", "default")
    company_name = None
    
    if company_id and company_id != "default":
        company = await db.companies.find_one({"id": company_id}, {"_id": 0})
        if company:
            company_name = company.get("name")
            # Verify employer is assigned to this company if not admin
            if current_user["role"] == "employer":
                if company.get("assigned_employer_id") and company.get("assigned_employer_id") != current_user["id"]:
                    raise HTTPException(status_code=403, detail="You are not assigned to this company")
    
    # Determine initial status based on role
    if current_user["role"] == "recruiter":
        initial_status = "pending_approval"
    else:
        initial_status = "active"
    
    # Validate public_company_alias for active jobs (mandatory for public visibility)
    if initial_status == "active" and not job_data.public_company_alias:
        # Default alias if not provided
        job_data_dict = job_data.model_dump()
        job_data_dict["public_company_alias"] = "Confidential Client"
    else:
        job_data_dict = job_data.model_dump()
    
    # Find team for this employer/recruiter
    team_id = None
    if current_user["role"] == "recruiter":
        # Find team where this recruiter is assigned
        team = await db.teams.find_one({"recruiter_ids": current_user["id"], "status": "active"}, {"_id": 0})
        if team:
            team_id = team["id"]
    elif current_user["role"] == "employer":
        # Find team for this employer
        team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
        if team:
            team_id = team["id"]
    
    job_doc = {
        "id": job_id,
        "job_public_id": job_public_id,  # Structured Job ID
        **job_data_dict,
        "company_id": company_id,
        "company_name": company_name,
        "posted_by": current_user["id"],
        "posted_by_role": current_user["role"],
        "status": initial_status,
        "team_id": team_id,
        "applicant_count": 0,
        # Career Page Status: NEVER auto-posted, always starts as not_posted
        "career_page_status": "not_posted",
        "career_page_history": [],
        # Shareable link: disabled by default
        "shareable_link_enabled": False,
        "approval_history": [{
            "status": initial_status,
            "changed_by": current_user["id"],
            "changed_by_name": current_user["name"],
            "changed_by_role": current_user["role"],
            "timestamp": now,
            "reason": "Job created"
        }],
        "created_at": now,
        "updated_at": now
    }
    
    await db.jobs.insert_one(job_doc)
    
    logging.info(f"Job {job_public_id} ({job_id}) created by {current_user['name']} ({current_user['role']}) with status {initial_status}")
    
    return JobResponse(**job_doc)


@jobs_router.post("/jobs/{job_id}/transition", response_model=JobResponse)
async def transition_job_status(
    job_id: str, 
    transition: JobStateTransition, 
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Transition job status with audit logging.
    Valid transitions:
    - draft -> pending_approval, active (admin only)
    - pending_approval -> active, draft (rejected back to draft)
    - active -> on_hold, closed
    - on_hold -> active, closed
    - closed -> archived (admin only)
    - archived -> (no transitions, final state)
    """
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    current_status = job.get("status", "active")
    new_status = transition.new_status
    
    # Define valid transitions
    valid_transitions = {
        "draft": ["pending_approval", "active"],
        "pending_approval": ["active", "draft", "on_hold"],
        "active": ["on_hold", "closed"],
        "on_hold": ["active", "closed"],
        "closed": ["archived"],
        "archived": []  # No transitions from archived
    }
    
    # Admin can do any transition except from archived
    if current_user["role"] != "admin":
        if new_status not in valid_transitions.get(current_status, []):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid transition from {current_status} to {new_status}"
            )
        # Employer can only approve their team's jobs
        if current_user["role"] == "employer":
            team = await db.teams.find_one({"employer_id": current_user["id"]}, {"_id": 0})
            if team and job.get("team_id") != team["id"]:
                # Check if job was posted by a recruiter in their team
                if job.get("posted_by") not in team.get("recruiter_ids", []):
                    raise HTTPException(status_code=403, detail="You can only approve jobs from your team")
    else:
        # Admin can't transition from archived
        if current_status == "archived":
            raise HTTPException(status_code=400, detail="Cannot transition from archived state")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Create audit entry
    audit_entry = {
        "from_status": current_status,
        "to_status": new_status,
        "changed_by": current_user["id"],
        "changed_by_name": current_user["name"],
        "changed_by_role": current_user["role"],
        "timestamp": now,
        "reason": transition.reason or f"Status changed from {current_status} to {new_status}"
    }
    
    # Update job
    await db.jobs.update_one(
        {"id": job_id},
        {
            "$set": {"status": new_status, "updated_at": now},
            "$push": {"approval_history": audit_entry}
        }
    )
    
    logging.info(f"Job {job_id} transitioned from {current_status} to {new_status} by {current_user['name']}")
    
    updated_job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return JobResponse(**updated_job)


@jobs_router.get("/jobs/pending-approval", response_model=List[JobResponse])
async def get_pending_approval_jobs(current_user: dict = Depends(require_role(["admin", "employer"]))):
    """Get jobs pending approval (for Admin and Employers)"""
    query = {"status": "pending_approval"}
    
    if current_user["role"] == "employer":
        # Get jobs from recruiters in this employer's team
        team = await db.teams.find_one({"employer_id": current_user["id"]}, {"_id": 0})
        if team:
            query["$or"] = [
                {"team_id": team["id"]},
                {"posted_by": {"$in": team.get("recruiter_ids", [])}}
            ]
        else:
            # No team, return empty
            return []
    
    jobs = await db.jobs.find(query, {"_id": 0}).to_list(1000)
    return [JobResponse(**j) for j in jobs]


@jobs_router.get("/jobs", response_model=List[JobResponse])
async def get_jobs(status: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    
    if current_user["role"] == "employer":
        # Employer sees jobs from their team
        team = await db.teams.find_one({"employer_id": current_user["id"]}, {"_id": 0})
        if team:
            query["$or"] = [
                {"posted_by": current_user["id"]},
                {"team_id": team["id"]}
            ]
        else:
            query["posted_by"] = current_user["id"]
    elif current_user["role"] == "recruiter":
        # Recruiter sees ONLY mandates explicitly assigned to them OR jobs they posted
        # This enforces employer-led mandate allocation - recruiters can only work on assigned mandates
        query["$or"] = [
            {"posted_by": current_user["id"]},  # Jobs they created
            {"assigned_recruiters": current_user["id"]}  # Mandates explicitly assigned by employer
        ]
    elif current_user["role"] == "candidate":
        query["status"] = "active"
    # Admin sees all jobs
    
    if status:
        query["status"] = status
    
    jobs = await db.jobs.find(query, {"_id": 0}).to_list(1000)
    return [JobResponse(**j) for j in jobs]


@jobs_router.get("/jobs/browse", response_model=List[JobResponse])
async def browse_jobs(search: Optional[str] = None, location: Optional[str] = None, job_type: Optional[str] = None):
    """Public job browsing - only shows ACTIVE jobs with masked company names (cached)"""
    
    # Build cache key from filters
    cache_key = f"jobs_browse:{search or ''}:{location or ''}:{job_type or ''}"
    
    # Try cache first
    cached_result = cache.get(cache_key)
    if cached_result:
        logging.debug(f"Cache HIT for job browse: {cache_key}")
        return [JobResponse(**j) for j in cached_result]
    
    query = {"status": "active"}
    
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}}
        ]
    if location:
        query["location"] = {"$regex": location, "$options": "i"}
    if job_type:
        query["job_type"] = job_type
    
    jobs = await db.jobs.find(query, {"_id": 0}).to_list(100)
    
    # Cache results for 3 minutes
    cache.set(cache_key, jobs, ttl=180)
    
    return [JobResponse(**j) for j in jobs]


@jobs_router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, current_user: dict = Depends(get_current_user)):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**job)


@jobs_router.put("/jobs/{job_id}", response_model=JobResponse)
async def update_job(job_id: str, update_data: JobUpdate, current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))):
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    result = await db.jobs.update_one({"id": job_id}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return JobResponse(**job)


@jobs_router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, current_user: dict = Depends(require_role(["admin", "employer"]))):
    result = await db.jobs.delete_one({"id": job_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"message": "Job deleted successfully"}


# ============== CAREER PAGE PUBLISHING CONTROL ==============

@jobs_router.post("/jobs/{job_id}/career-page-status")
async def update_career_page_status(
    job_id: str,
    update: CareerPageStatusUpdate,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Update job's career page status with full audit logging.
    
    IMPORTANT: Career page publishing is NEVER automatic.
    System must ALWAYS ask: "Do you want to post this job on the career page?"
    Default option = NO
    
    Access Control:
    - Admin: Can turn ON/OFF career page status for any job
    - Employer: Can turn ON/OFF for jobs under their companies
    - Recruiter: Can turn ON/OFF ONLY for jobs they personally created AND only after employer approval
    - Candidate: NO control
    
    Rules:
    - Job must be in 'active' status to be posted on career page
    - Removing from career page does NOT delete the job internally
    - Full audit log maintained for all status changes
    """
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Access control checks
    if current_user["role"] == "recruiter":
        # Recruiter can only control jobs they personally created
        if job.get("posted_by") != current_user["id"]:
            raise HTTPException(
                status_code=403, 
                detail="Recruiters can only control career page status for jobs they personally created"
            )
        # Recruiter can only post after employer approval (status must be 'active')
        if job.get("status") != "active":
            raise HTTPException(
                status_code=400,
                detail="Job must be approved (active status) before posting to career page"
            )
    
    elif current_user["role"] == "employer":
        # Employer can control jobs under their companies
        team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
        if team:
            company_ids = team.get("company_ids", [])
            recruiter_ids = team.get("recruiter_ids", [])
            
            can_control = (
                job.get("posted_by") == current_user["id"] or
                job.get("company_id") in company_ids or
                job.get("posted_by") in recruiter_ids
            )
            
            if not can_control:
                raise HTTPException(
                    status_code=403,
                    detail="Employers can only control career page status for jobs under their companies"
                )
        else:
            # No team assigned, only own jobs
            if job.get("posted_by") != current_user["id"]:
                raise HTTPException(status_code=403, detail="Access denied")
    
    # Admin has full access - no additional checks needed
    
    # Validation: Can only post active jobs to career page
    if update.new_status == "live" and job.get("status") != "active":
        raise HTTPException(
            status_code=400,
            detail="Only active/approved jobs can be posted on the career page"
        )
    
    now = datetime.now(timezone.utc).isoformat()
    current_status = job.get("career_page_status", "not_posted")
    
    # Create audit log entry
    audit_entry = {
        "from_status": current_status,
        "to_status": update.new_status,
        "changed_by": current_user["id"],
        "changed_by_name": current_user.get("name", "Unknown"),
        "changed_by_role": current_user["role"],
        "reason": update.reason,
        "timestamp": now
    }
    
    # Update job
    await db.jobs.update_one(
        {"id": job_id},
        {
            "$set": {
                "career_page_status": update.new_status,
                "updated_at": now
            },
            "$push": {"career_page_history": audit_entry}
        }
    )
    
    # Create global audit log
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "entity_type": "job",
        "entity_id": job_id,
        "action": f"career_page_{update.new_status}",
        "old_value": current_status,
        "new_value": update.new_status,
        "changed_by": current_user["id"],
        "changed_by_name": current_user.get("name"),
        "changed_by_role": current_user["role"],
        "reason": update.reason,
        "timestamp": now
    })
    
    updated_job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    
    return {
        "success": True,
        "message": f"Job {'posted to' if update.new_status == 'live' else 'removed from'} career page",
        "job_id": job_id,
        "career_page_status": update.new_status,
        "audit_entry": audit_entry
    }


@jobs_router.get("/jobs/{job_id}/career-page-history")
async def get_career_page_history(
    job_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Get career page status change history for a job"""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0, "career_page_history": 1, "career_page_status": 1})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "job_id": job_id,
        "current_status": job.get("career_page_status", "not_posted"),
        "history": job.get("career_page_history", [])
    }


@jobs_router.put("/jobs/{job_id}/shareable-link")
async def update_shareable_link(
    job_id: str,
    update: ShareableLinkUpdate,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Enable or disable shareable link for a job.
    
    Rules:
    - Shareable link can only be enabled for jobs with career_page_status = "live"
    - Admin has full access
    - Employer can control jobs under their companies
    - Recruiter can only control jobs they personally created
    """
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Access control (same as career page status)
    if current_user["role"] == "recruiter":
        if job.get("posted_by") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    elif current_user["role"] == "employer":
        team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
        if team:
            company_ids = team.get("company_ids", [])
            recruiter_ids = team.get("recruiter_ids", [])
            can_control = (
                job.get("posted_by") == current_user["id"] or
                job.get("company_id") in company_ids or
                job.get("posted_by") in recruiter_ids
            )
            if not can_control:
                raise HTTPException(status_code=403, detail="Access denied")
        elif job.get("posted_by") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Validation: Can only enable shareable link for live jobs
    if update.enabled and job.get("career_page_status") != "live":
        raise HTTPException(
            status_code=400,
            detail="Shareable link can only be enabled for jobs that are live on the career page"
        )
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.jobs.update_one(
        {"id": job_id},
        {
            "$set": {
                "shareable_link_enabled": update.enabled,
                "updated_at": now
            }
        }
    )
    
    # Audit log
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "entity_type": "job",
        "entity_id": job_id,
        "action": f"shareable_link_{'enabled' if update.enabled else 'disabled'}",
        "old_value": job.get("shareable_link_enabled", False),
        "new_value": update.enabled,
        "changed_by": current_user["id"],
        "changed_by_name": current_user.get("name"),
        "changed_by_role": current_user["role"],
        "timestamp": now
    })
    
    return {
        "success": True,
        "message": f"Shareable link {'enabled' if update.enabled else 'disabled'}",
        "job_id": job_id,
        "job_public_id": job.get("job_public_id"),
        "shareable_link_enabled": update.enabled
    }


@jobs_router.put("/jobs/{job_id}/mandate-shareable-link")
async def update_mandate_shareable_link(
    job_id: str,
    update: MandateShareableLinkUpdate,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Enable or disable mandate-level shareable link for a job.
    
    This allows sharing job links INDEPENDENT of career page visibility.
    Useful for:
    - Assigned mandates to recruiters
    - Confidential searches
    - Jobs not intended for public career page
    
    Rules:
    - Only Admin and Employer can enable mandate shareable links
    - Job must be in 'active' status
    - Generates a secure token for the shareable link
    """
    import secrets
    
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Access control
    if current_user["role"] == "employer":
        team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
        if team:
            company_ids = team.get("company_ids", [])
            recruiter_ids = team.get("recruiter_ids", [])
            can_control = (
                job.get("posted_by") == current_user["id"] or
                job.get("company_id") in company_ids or
                job.get("posted_by") in recruiter_ids
            )
            if not can_control:
                raise HTTPException(status_code=403, detail="Access denied")
        elif job.get("posted_by") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Validation: Job must be active
    if job.get("status") != "active":
        raise HTTPException(
            status_code=400,
            detail="Mandate shareable link can only be enabled for active jobs"
        )
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Generate secure token if enabling
    mandate_share_token = job.get("mandate_share_token")
    if update.enabled and not mandate_share_token:
        mandate_share_token = secrets.token_urlsafe(24)
    
    await db.jobs.update_one(
        {"id": job_id},
        {
            "$set": {
                "mandate_shareable_link_enabled": update.enabled,
                "mandate_share_token": mandate_share_token if update.enabled else None,
                "updated_at": now
            }
        }
    )
    
    # Audit log
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "entity_type": "job",
        "entity_id": job_id,
        "action": f"mandate_shareable_link_{'enabled' if update.enabled else 'disabled'}",
        "old_value": job.get("mandate_shareable_link_enabled", False),
        "new_value": update.enabled,
        "changed_by": current_user["id"],
        "changed_by_name": current_user.get("name"),
        "changed_by_role": current_user["role"],
        "timestamp": now
    })
    
    return {
        "success": True,
        "message": f"Mandate shareable link {'enabled' if update.enabled else 'disabled'}",
        "job_id": job_id,
        "job_public_id": job.get("job_public_id"),
        "mandate_shareable_link_enabled": update.enabled,
        "mandate_share_token": mandate_share_token if update.enabled else None
    }


@jobs_router.get("/career-page/jobs")
async def get_career_page_jobs():
    """
    Public endpoint: Get all jobs that are live on the career page.
    Used by the public career page to display available positions.
    Results are cached for 5 minutes.
    """
    cache_key = "career_page_jobs"
    
    # Try cache first
    cached_result = cache.get(cache_key)
    if cached_result:
        logging.debug("Cache HIT for career page jobs")
        return cached_result
    
    jobs = await db.jobs.find(
        {
            "career_page_status": "live",
            "status": "active",
            "shareable_link_enabled": True
        },
        {
            "_id": 0,
            "id": 1,
            "job_public_id": 1,
            "title": 1,
            "description": 1,
            "requirements": 1,
            "location": 1,
            "job_type": 1,
            "salary_min": 1,
            "salary_max": 1,
            "department": 1,
            "skills": 1,
            "experience_min": 1,
            "experience_max": 1,
            "public_company_alias": 1,
            "company_name": 1,
            "created_at": 1
        }
    ).to_list(100)
    
    # Use public company alias if available, otherwise company name
    for job in jobs:
        job["display_company"] = job.get("public_company_alias") or job.get("company_name") or "Confidential"
    
    # Cache results for 5 minutes
    cache.set(cache_key, jobs, ttl=300)
    
    return jobs


# ============== JD PARSING ==============

@jobs_router.post("/jobs/extract-jd-text")
async def extract_jd_text_from_file(
    jd_file: UploadFile = File(...),
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Extract text from uploaded JD file (PDF, DOC, DOCX).
    Returns raw text for preview before parsing.
    """
    if not jd_file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    file_ext = jd_file.filename.split(".")[-1].lower()
    if file_ext not in ["pdf", "doc", "docx", "txt"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file format '{file_ext}'. Use PDF, DOC, DOCX, or TXT"
        )
    
    # Save file temporarily
    file_path = UPLOAD_DIR / f"jd_{uuid.uuid4()}.{file_ext}"
    try:
        async with aiofiles.open(file_path, "wb") as f:
            content = await jd_file.read()
            await f.write(content)
        
        raw_text = ""
        extraction_method = ""
        
        # Extract text based on file type
        if file_ext == "pdf":
            try:
                doc = fitz.open(str(file_path))
                for page in doc:
                    raw_text += page.get_text()
                doc.close()
                extraction_method = "pdf_fitz"
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to extract text from PDF: {str(e)}")
                
        elif file_ext == "txt":
            try:
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    raw_text = await f.read()
                extraction_method = "txt_read"
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to read text file: {str(e)}")
                
        elif file_ext in ["doc", "docx"]:
            try:
                from docx import Document
                doc = Document(str(file_path))
                raw_text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
                extraction_method = "docx_python"
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to extract text from DOC/DOCX: {str(e)}")
        
        if not raw_text.strip():
            raise HTTPException(status_code=400, detail="No text could be extracted from the file. The file may be empty or contain only images.")
        
        # Log extraction for audit
        logging.info(f"JD text extracted by {current_user['name']} ({current_user['role']}) - method: {extraction_method}, chars: {len(raw_text)}")
        
        return {
            "success": True,
            "extracted_text": raw_text.strip(),
            "filename": jd_file.filename,
            "file_type": file_ext,
            "char_count": len(raw_text),
            "extraction_method": extraction_method,
            "extracted_by": current_user["id"],
            "extracted_by_role": current_user["role"],
            "extracted_at": datetime.now(timezone.utc).isoformat()
        }
        
    finally:
        # Clean up temp file
        if file_path.exists():
            file_path.unlink(missing_ok=True)


@jobs_router.post("/jobs/parse-jd")
async def parse_job_description(
    jd_text: Optional[str] = Form(None),
    jd_file: Optional[UploadFile] = File(None),
    input_type: Optional[str] = Form("paste"),  # "paste" or "upload"
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Parse a job description (text or file) using AI.
    Returns structured job fields for form pre-fill.
    """
    raw_text = ""
    
    if jd_file:
        # Save and extract text from file
        file_ext = jd_file.filename.split(".")[-1].lower()
        if file_ext not in ["pdf", "doc", "docx", "txt"]:
            raise HTTPException(status_code=400, detail="Unsupported file format. Use PDF, DOC, DOCX, or TXT")
        
        # Save file temporarily
        file_path = UPLOAD_DIR / f"jd_{uuid.uuid4()}.{file_ext}"
        try:
            async with aiofiles.open(file_path, "wb") as f:
                content = await jd_file.read()
                await f.write(content)
            
            # Extract text based on file type
            if file_ext == "pdf":
                try:
                    doc = fitz.open(str(file_path))
                    for page in doc:
                        raw_text += page.get_text()
                    doc.close()
                except Exception as pdf_err:
                    logging.error(f"PDF extraction error: {pdf_err}")
                    raise HTTPException(status_code=400, detail=f"Failed to extract text from PDF: {str(pdf_err)}")
                    
            elif file_ext == "txt":
                try:
                    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                        raw_text = await f.read()
                except Exception as txt_err:
                    logging.error(f"TXT read error: {txt_err}")
                    raise HTTPException(status_code=400, detail=f"Failed to read text file: {str(txt_err)}")
                    
            else:
                # For DOC/DOCX, use python-docx
                try:
                    from docx import Document
                    doc = Document(str(file_path))
                    raw_text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
                except Exception as docx_err:
                    logging.error(f"DOCX extraction error: {docx_err}")
                    raise HTTPException(status_code=400, detail=f"Failed to extract text from DOC/DOCX: {str(docx_err)}")
            
            # Validate extracted text
            if not raw_text or not raw_text.strip():
                raise HTTPException(status_code=400, detail="No text could be extracted from the file. The file may be empty or contain only images.")
                
        finally:
            # Clean up temp file
            if file_path.exists():
                file_path.unlink(missing_ok=True)
    
    elif jd_text:
        raw_text = jd_text
    else:
        raise HTTPException(status_code=400, detail="Provide either jd_text or jd_file")
    
    # Log JD parsing usage for audit
    logging.info(f"JD Parsing requested by {current_user['name']} ({current_user['role']}) - input_type: {input_type}, chars: {len(raw_text)}")
    
    # Parse using AI (using GPT-5.2 via Emergent)
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        import json
        
        parse_prompt = f"""Parse the following job description and extract structured information.
Return a JSON object with these fields:
- title: Job title
- skills: Array of required skills
- experience_years: Estimated years of experience required (number)
- location: Job location
- job_level: One of "junior", "mid", "senior", "leadership" based on requirements
- salary_min: Minimum salary if mentioned (number, in INR)
- salary_max: Maximum salary if mentioned (number, in INR)
- summary: 2-3 sentence summary of the role
- responsibilities: Array of key responsibilities
- requirements: Array of key requirements

Job Description:
{raw_text[:4000]}

Return ONLY valid JSON, no markdown or explanation."""

        # Initialize LlmChat client
        chat_client = LlmChat(
            api_key=os.environ.get("EMERGENT_LLM_KEY"),
            session_id=str(uuid.uuid4()),
            system_message="You are an expert job description parser. Extract structured data accurately."
        )
        
        response = await chat_client.send_message(UserMessage(text=parse_prompt))
        
        # Parse JSON response
        try:
            # Clean response (remove markdown if present)
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            
            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            parsed = {}
        
        return {
            "success": True,
            "title": parsed.get("title"),
            "skills": parsed.get("skills", []),
            "experience_years": parsed.get("experience_years"),
            "experience_min": parsed.get("experience_years"),
            "experience_max": parsed.get("experience_years"),
            "location": parsed.get("location"),
            "job_level": parsed.get("job_level"),
            "salary_min": parsed.get("salary_min"),
            "salary_max": parsed.get("salary_max"),
            "summary": parsed.get("summary"),
            "responsibilities": parsed.get("responsibilities", []),
            "requirements": parsed.get("requirements", []),
            "raw_text": raw_text[:2000],
            # Audit metadata
            "input_type": input_type,
            "parsed_by": current_user["id"],
            "parsed_by_name": current_user.get("name"),
            "parsed_by_role": current_user["role"],
            "parsed_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logging.error(f"JD parsing error: {e}")
        # Return basic extraction if AI fails
        return {
            "success": False,
            "title": None,
            "skills": [],
            "experience_years": None,
            "experience_min": None,
            "experience_max": None,
            "location": None,
            "job_level": None,
            "salary_min": None,
            "salary_max": None,
            "summary": None,
            "responsibilities": [],
            "requirements": [],
            "raw_text": raw_text[:2000],
            "input_type": input_type,
            "parsed_by": current_user["id"],
            "parsed_by_name": current_user.get("name"),
            "parsed_by_role": current_user["role"],
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "parse_error": str(e)
        }


# ============== MANDATE ASSIGNMENT ==============

@jobs_router.get("/employer/team-recruiters")
async def get_team_recruiters(current_user: dict = Depends(require_role(["admin", "employer"]))):
    """
    Get list of recruiters in employer's team for mandate assignment.
    Returns recruiter details including their current mandate workload.
    """
    if current_user["role"] == "employer":
        team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
        if not team:
            return {"recruiters": [], "team": None}
        
        recruiter_ids = team.get("recruiter_ids", [])
    else:
        # Admin can see all recruiters
        all_recruiters = await db.users.find(
            {"role": "recruiter", "is_active": True},
            {"_id": 0, "password": 0}
        ).to_list(1000)
        
        result = []
        for rec in all_recruiters:
            active_mandates = await db.jobs.count_documents({
                "assigned_recruiters": rec["id"],
                "status": {"$in": ["active", "pending_approval"]}
            })
            result.append({
                "id": rec["id"],
                "name": rec.get("name"),
                "email": rec.get("email"),
                "phone": rec.get("phone"),
                "active_mandates_count": active_mandates
            })
        
        return {"recruiters": result, "team": None}
    
    # Get recruiter details with mandate counts
    recruiters = await db.users.find(
        {"id": {"$in": recruiter_ids}, "is_active": True},
        {"_id": 0, "password": 0}
    ).to_list(100)
    
    result = []
    for rec in recruiters:
        active_mandates = await db.jobs.count_documents({
            "assigned_recruiters": rec["id"],
            "status": {"$in": ["active", "pending_approval"]}
        })
        result.append({
            "id": rec["id"],
            "name": rec.get("name"),
            "email": rec.get("email"),
            "phone": rec.get("phone"),
            "active_mandates_count": active_mandates
        })
    
    return {
        "recruiters": result,
        "team": {
            "id": team.get("id"),
            "name": team.get("name")
        }
    }


@jobs_router.post("/jobs/{job_id}/assign-recruiters")
async def assign_recruiters_to_mandate(
    job_id: str,
    recruiter_ids: List[str],
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Assign recruiters to a job mandate (Employer-led allocation).
    
    Rules:
    - Only Employer or Admin can assign
    - Recruiters cannot self-assign
    - Only active/approved jobs can have recruiters assigned
    - Recruiters must be in employer's team
    """
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Validate job status - only active or pending_approval jobs can be assigned
    if job.get("status") not in ["active", "pending_approval"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot assign recruiters to jobs with status '{job.get('status')}'. Job must be Active or Pending Approval."
        )
    
    # Employer access control
    if current_user["role"] == "employer":
        # Check if employer owns this job (via team or direct posting)
        team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
        
        can_assign = (
            job.get("posted_by") == current_user["id"] or
            (team and job.get("team_id") == team.get("id")) or
            (team and job.get("posted_by") in team.get("recruiter_ids", []))
        )
        
        if not can_assign:
            raise HTTPException(status_code=403, detail="You can only assign recruiters to mandates under your team")
        
        # Validate recruiters are in employer's team
        if team:
            team_recruiter_ids = team.get("recruiter_ids", [])
            for rec_id in recruiter_ids:
                if rec_id not in team_recruiter_ids:
                    recruiter = await db.users.find_one({"id": rec_id}, {"name": 1, "_id": 0})
                    rec_name = recruiter.get("name", rec_id) if recruiter else rec_id
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Recruiter '{rec_name}' is not in your team"
                    )
    
    # Validate all recruiter IDs exist and are active recruiters
    for rec_id in recruiter_ids:
        recruiter = await db.users.find_one({"id": rec_id, "role": "recruiter", "is_active": True}, {"_id": 0})
        if not recruiter:
            raise HTTPException(status_code=400, detail=f"Recruiter {rec_id} not found or inactive")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Get recruiter details for assignment
    recruiter_details = []
    for rec_id in recruiter_ids:
        rec = await db.users.find_one({"id": rec_id}, {"name": 1, "email": 1, "_id": 0})
        if rec:
            recruiter_details.append({
                "id": rec_id,
                "name": rec.get("name", "Unknown"),
                "email": rec.get("email")
            })
    
    # Get previous assignment state for audit
    previous_assignments = job.get("assigned_recruiters", [])
    
    # Create audit entry
    assignment_audit = {
        "action": "recruiters_assigned",
        "previous_recruiters": previous_assignments,
        "new_recruiters": recruiter_ids,
        "assigned_by_id": current_user["id"],
        "assigned_by_name": current_user["name"],
        "assigned_by_role": current_user["role"],
        "timestamp": now
    }
    
    await db.jobs.update_one(
        {"id": job_id},
        {
            "$set": {
                "assigned_recruiters": recruiter_ids,
                "updated_at": now
            },
            "$push": {"assignment_history": assignment_audit}
        }
    )
    
    logging.info(f"Mandate {job.get('job_public_id', job_id)} assigned to recruiters {[r['name'] for r in recruiter_details]} by {current_user['name']} ({current_user['role']})")
    
    return {
        "success": True,
        "message": "Recruiters assigned successfully",
        "job_id": job_id,
        "job_public_id": job.get("job_public_id"),
        "job_title": job.get("title"),
        "assigned_recruiters": recruiter_details,
        "assigned_by": current_user["name"],
        "assigned_at": now
    }


@jobs_router.delete("/jobs/{job_id}/assign-recruiters/{recruiter_id}")
async def remove_recruiter_from_mandate(
    job_id: str,
    recruiter_id: str,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Remove a single recruiter from a mandate.
    """
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Employer access control
    if current_user["role"] == "employer":
        team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
        can_assign = (
            job.get("posted_by") == current_user["id"] or
            (team and job.get("team_id") == team.get("id"))
        )
        if not can_assign:
            raise HTTPException(status_code=403, detail="Access denied")
    
    current_assignments = job.get("assigned_recruiters", [])
    if recruiter_id not in current_assignments:
        raise HTTPException(status_code=400, detail="Recruiter is not assigned to this mandate")
    
    new_assignments = [r for r in current_assignments if r != recruiter_id]
    now = datetime.now(timezone.utc).isoformat()
    
    # Get recruiter name for audit
    recruiter = await db.users.find_one({"id": recruiter_id}, {"name": 1, "_id": 0})
    recruiter_name = recruiter.get("name", "Unknown") if recruiter else "Unknown"
    
    assignment_audit = {
        "action": "recruiter_removed",
        "removed_recruiter_id": recruiter_id,
        "removed_recruiter_name": recruiter_name,
        "removed_by_id": current_user["id"],
        "removed_by_name": current_user["name"],
        "removed_by_role": current_user["role"],
        "timestamp": now
    }
    
    await db.jobs.update_one(
        {"id": job_id},
        {
            "$set": {
                "assigned_recruiters": new_assignments,
                "updated_at": now
            },
            "$push": {"assignment_history": assignment_audit}
        }
    )
    
    logging.info(f"Recruiter {recruiter_name} removed from mandate {job_id} by {current_user['name']}")
    
    return {
        "success": True,
        "message": f"Recruiter {recruiter_name} removed from mandate",
        "job_id": job_id,
        "remaining_recruiters": new_assignments
    }


@jobs_router.get("/jobs/{job_id}/assignments")
async def get_job_assignments(
    job_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Get recruiter assignments for a job with full details."""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # For recruiter, check if they are assigned
    if current_user["role"] == "recruiter":
        if current_user["id"] not in job.get("assigned_recruiters", []):
            raise HTTPException(status_code=403, detail="Not assigned to this job")
    
    # Get recruiter details
    assigned_details = []
    for rec_id in job.get("assigned_recruiters", []):
        recruiter = await db.users.find_one({"id": rec_id}, {"_id": 0, "password": 0})
        if recruiter:
            # Get active mandates count for this recruiter
            active_mandates = await db.jobs.count_documents({
                "assigned_recruiters": rec_id,
                "status": {"$in": ["active", "pending_approval"]}
            })
            assigned_details.append({
                "id": recruiter.get("id"),
                "name": recruiter.get("name"),
                "email": recruiter.get("email"),
                "phone": recruiter.get("phone"),
                "active_mandates_count": active_mandates
            })
    
    return {
        "job_id": job_id,
        "job_public_id": job.get("job_public_id"),
        "job_title": job.get("title"),
        "job_status": job.get("status"),
        "team_id": job.get("team_id"),
        "assigned_recruiters": assigned_details,
        "assignment_history": job.get("assignment_history", [])
    }


# ============== JOB NOTIFICATIONS ==============
# Import the notification helper function from server.py (if needed in future)
# For now, we define stub endpoints that will call the background task

@jobs_router.post("/jobs/with-notifications", response_model=JobResponse)
async def create_job_with_notifications(
    job_data: JobCreate,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Create a new job and trigger notifications to matching candidates.
    This is an alternative endpoint that includes notification triggering.
    """
    now = datetime.now(timezone.utc).isoformat()
    job_id = str(uuid.uuid4())
    
    # Get company_id for employers
    company_id = None
    if current_user["role"] == "employer":
        company_id = current_user.get("company_id")
    
    job_doc = {
        "id": job_id,
        **job_data.model_dump(),
        "company_id": company_id,
        "posted_by": current_user["id"],
        "status": "active",
        "applicant_count": 0,
        "created_at": now
    }
    
    await db.jobs.insert_one(job_doc)
    
    # Note: Notification triggering would be done via services/notification_service.py
    # For now, we just log the intent
    logging.info(f"Job {job_id} created with notification trigger by {current_user['name']}")
    
    return JobResponse(**job_doc)


@jobs_router.post("/jobs/{job_id}/notify-candidates")
async def manually_trigger_notifications(
    job_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Manually trigger notifications for a job.
    Useful for re-notifying or notifying after job update.
    """
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Note: Notification triggering would be done via services/notification_service.py
    logging.info(f"Manual notification trigger for job {job_id} by {current_user['name']}")
    
    return {"message": "Notification task started", "job_id": job_id}
