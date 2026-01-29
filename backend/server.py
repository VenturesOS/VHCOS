from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, status, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
import os
import logging
import hashlib
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt
import aiofiles
import fitz  # PyMuPDF for PDF text extraction

# Import configuration from config.py
from config import (
    ROOT_DIR,
    db,
    db_name,
    client,
    r2_client,
    R2_ENABLED,
    R2_BUCKET_NAME,
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    UPLOAD_DIR,
    PARENT_UPLOAD_DIR
)

# Import models from models/
from models import (
    # Auth models
    UserBase, UserCreate, UserLogin, UserResponse, UserUpdate,
    AdminUserCreate, AdminPasswordReset, PasswordReset, TokenResponse,
    # Job models
    JobBase, JobCreate, JobResponse, JobUpdate, JobStateTransition,
    CareerPageStatusUpdate, JDParseRequest, JDParseResponse, MandateAssignment,
    # Candidate models
    CandidateProfile, CandidateProfileUpdate,
    # Application models
    ApplicationBase, ApplicationCreate, ApplicationResponse,
    ApplicationUpdate, ApplicationDetailUpdate, AuditLogEntry, NoteCreate,
    # Company models
    CompanyBase, CompanyCreate, CompanyResponse, CompanyUpdate,
    # Team models
    TeamCreate, TeamUpdate, TeamResponse,
    # Referral models
    ReferralCreate, ReferralResponse, ReferralStatusUpdate,
    # Message models
    MessageBase, MessageCreate, MessageResponse,
    # Candidate Bank models
    CandidateBankRecord, CandidateBankUpdate, CandidateBankAuditLogEntry,
    BatchUploadCandidate, BatchSaveRequest,
    # Matching models
    MatchRequest, MatchResult, JobMatchForCandidate,
    # Alert models
    JobAlertPreferences, JobAlertCreate, WhatsAppOptIn, NotificationLogEntry,
    # Commercial models
    CommercialCreate, CommercialUpdate, CommercialResponse,
    RevenueEntry, RevenueUpdate
)

# Import utilities from utils/
from utils import (
    # Auth utilities
    hash_password, verify_password, create_access_token,
    get_current_user, require_role, security,
    # Governance utilities
    validate_mandatory_candidate_fields, create_profile_audit_entry,
    update_candidate_freshness, add_application_to_history,
    update_application_in_history
)

# Import R2 storage services
from services import (
    upload_to_r2,
    get_r2_signed_url,
    get_file_from_r2,
    generate_r2_key
)

# Import route modules
from routes import auth_router, public_router, files_router, admin_router, jobs_router, candidates_router, applications_router

# Import boto3 for type hints (r2_client operations)
import boto3
from botocore.config import Config


# Create the main app
app = FastAPI(title="VHC Talent OS API")

# Include auth routes (extracted to routes/auth.py)
app.include_router(auth_router)

# Include public routes (extracted to routes/public.py)
app.include_router(public_router)

# Include file serving routes (extracted to routes/files.py)
app.include_router(files_router)

# Include admin routes (extracted to routes/admin.py)
app.include_router(admin_router)

# Include jobs routes (extracted to routes/jobs.py)
app.include_router(jobs_router)

# Include candidate bank routes (extracted to routes/candidates.py)
app.include_router(candidates_router)

# Include applications & AI matching routes (extracted to routes/applications.py)
app.include_router(applications_router)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Note: Auth routes extracted to routes/auth.py and included via app.include_router()

# Note: USER MANAGEMENT (ADMIN) routes have been extracted to routes/admin.py
# Endpoints: /api/users, /api/users/{user_id}, /api/admin/users, /api/admin/pipeline, etc.

# Note: JOB ROUTES have been extracted to routes/jobs.py
# Endpoints: /api/jobs, /api/jobs/{job_id}, /api/jobs/{job_id}/transition,
#            /api/jobs/{job_id}/career-page-status, /api/jobs/{job_id}/shareable-link,
#            /api/career-page/jobs, /api/jobs/parse-jd, /api/jobs/{job_id}/assign-recruiters, etc.

# ============== CV DOWNLOAD ENDPOINT ==============

@api_router.get("/applications/{app_id}/resume")
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
    # Primary location: /app/uploads (used by public apply)
    primary_dir = Path("/app/uploads")
    primary_path = primary_dir / original_filename
    
    # Secondary location: /app/backend/uploads (used by internal uploads)
    secondary_path = UPLOAD_DIR / original_filename
    
    if primary_path.exists():
        file_path = primary_path
    elif secondary_path.exists():
        file_path = secondary_path
    else:
        raise HTTPException(status_code=404, detail="Resume file not found")
    
    # Generate proper download filename: Firstname_Lastname_VHC.ext
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
    
    # Clean names (remove special characters, replace spaces with underscore)
    import re
    first_name = re.sub(r'[^a-zA-Z0-9]', '', first_name)
    last_name = re.sub(r'[^a-zA-Z0-9]', '', last_name)
    
    # Get file extension
    file_ext = file_path.suffix
    
    # Create download filename
    download_filename = f"{first_name}_{last_name}_VHC{file_ext}"
    
    return FileResponse(
        file_path,
        filename=download_filename,
        media_type="application/octet-stream"
    )


# Note: Resume download endpoints extracted to routes/candidates.py
# Endpoints: /api/candidates/{candidate_id}/resume, /api/candidate-bank/{candidate_id}/download-resume

# ============== COMPANY ROUTES ==============

@api_router.post("/companies", response_model=CompanyResponse)
async def create_company(company_data: CompanyCreate, current_user: dict = Depends(require_role(["admin", "employer"]))):
    company_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    company_doc = {
        "id": company_id,
        **company_data.model_dump(),
        "created_by": current_user["id"],
        "created_at": now
    }
    
    await db.companies.insert_one(company_doc)
    
    # Link employer to company
    if current_user["role"] == "employer":
        await db.users.update_one({"id": current_user["id"]}, {"$set": {"company_id": company_id}})
    
    return CompanyResponse(**company_doc)

@api_router.get("/companies", response_model=List[CompanyResponse])
async def get_companies(current_user: dict = Depends(get_current_user)):
    companies = await db.companies.find({}, {"_id": 0}).to_list(1000)
    return [CompanyResponse(**c) for c in companies]

@api_router.get("/companies/{company_id}", response_model=CompanyResponse)
async def get_company(company_id: str, current_user: dict = Depends(get_current_user)):
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanyResponse(**company)


# ============== CANDIDATE PROFILE ROUTES ==============

@api_router.get("/profile", response_model=CandidateProfile)
async def get_profile(current_user: dict = Depends(require_role(["candidate"]))):
    profile = await db.candidate_profiles.find_one({"user_id": current_user["id"]}, {"_id": 0})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return CandidateProfile(**profile)

@api_router.put("/profile", response_model=CandidateProfile)
async def update_profile(update_data: CandidateProfileUpdate, current_user: dict = Depends(require_role(["candidate"]))):
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.candidate_profiles.update_one(
        {"user_id": current_user["id"]},
        {"$set": update_dict}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    profile = await db.candidate_profiles.find_one({"user_id": current_user["id"]}, {"_id": 0})
    return CandidateProfile(**profile)

@api_router.post("/profile/resume")
async def upload_resume(file: UploadFile = File(...), current_user: dict = Depends(require_role(["candidate"]))):
    if not file.filename.lower().endswith(('.pdf', '.doc', '.docx')):
        raise HTTPException(status_code=400, detail="Only PDF and DOC files allowed")
    
    file_ext = Path(file.filename).suffix
    filename = f"{current_user['id']}_resume{file_ext}"
    file_path = UPLOAD_DIR / filename
    
    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    resume_url = f"/api/uploads/{filename}"
    
    await db.candidate_profiles.update_one(
        {"user_id": current_user["id"]},
        {"$set": {"resume_url": resume_url, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {"message": "Resume uploaded successfully", "resume_url": resume_url}

# ============== APPLICATION ROUTES ==============

@api_router.post("/applications", response_model=ApplicationResponse)
async def create_application(app_data: ApplicationCreate, current_user: dict = Depends(require_role(["candidate"]))):
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

@api_router.get("/applications", response_model=List[ApplicationResponse])
async def get_applications(job_id: Optional[str] = None, stage: Optional[str] = None, current_user: dict = Depends(get_current_user)):
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

@api_router.get("/applications/{app_id}", response_model=ApplicationResponse)
async def get_application(app_id: str, current_user: dict = Depends(get_current_user)):
    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return ApplicationResponse(**application)

@api_router.put("/applications/{app_id}", response_model=ApplicationResponse)
async def update_application(app_id: str, update_data: ApplicationUpdate, current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))):
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

@api_router.post("/applications/{app_id}/notes")
async def add_note(app_id: str, note_data: NoteCreate, current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))):
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


@api_router.put("/applications/{app_id}/details")
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
    # Get current application
    application = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    now = datetime.now(timezone.utc).isoformat()
    update_dict = {}
    audit_entries = []
    
    # Process each field that can be edited
    editable_fields = {
        "current_salary": update_data.current_salary,
        "notice_period": update_data.notice_period,
        "skills": update_data.skills,
        "experience_summary": update_data.experience_summary
    }
    
    for field, new_value in editable_fields.items():
        if new_value is not None:
            old_value = application.get(field)
            
            # Only log if value actually changed
            if old_value != new_value:
                update_dict[field] = new_value
                
                # Create audit entry
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
    update_dict["manually_edited"] = True  # Flag to prevent parsing overwrites
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
            candidate_update["last_profile_updated_at"] = now  # Data Governance: freshness update
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
    
    # Fetch updated application
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


@api_router.get("/applications/{app_id}/edit-history")
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
    experience_summary: Optional[str] = None  # Editable summary text
    skills: Optional[List[str]] = None
    experience_years: Optional[int] = None
    location: Optional[str] = None
    current_salary: Optional[int] = None  # INR
    notice_period: Optional[str] = None
    resume_url: Optional[str] = None
    cover_letter: Optional[str] = None
    stage: str = "applied"
    match_score: Optional[int] = None  # 0-100 percentage
    must_haves_met: Optional[List[Dict]] = None  # [{requirement: str, met: bool}]
    career_stability: Optional[Dict] = None  # {score: green/yellow/red, quick_changes: int}
    applied_at: Optional[str] = None
    updated_at: Optional[str] = None
    notes: List[Dict] = []
    edit_history: List[Dict] = []  # Audit trail
    last_edited_by: Optional[Dict] = None  # {name, role, timestamp}
    manually_edited: bool = False  # Flag indicating manual edits exist

@api_router.get("/jobs/{job_id}/applicants")
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

@api_router.get("/candidates", response_model=List[CandidateProfile])
async def get_candidates(current_user: dict = Depends(require_role(["admin", "recruiter", "employer"]))):
    profiles = await db.candidate_profiles.find({}, {"_id": 0}).to_list(1000)
    return [CandidateProfile(**p) for p in profiles]

@api_router.get("/candidates/{candidate_id}", response_model=CandidateProfile)
async def get_candidate(candidate_id: str, current_user: dict = Depends(require_role(["admin", "recruiter", "employer"]))):
    profile = await db.candidate_profiles.find_one({"user_id": candidate_id}, {"_id": 0})
    if not profile:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return CandidateProfile(**profile)

# ============== MESSAGE ROUTES ==============

@api_router.post("/messages", response_model=MessageResponse)
async def send_message(msg_data: MessageCreate, current_user: dict = Depends(get_current_user)):
    # Check recipient exists
    recipient = await db.users.find_one({"id": msg_data.recipient_id}, {"_id": 0})
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    
    msg_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    msg_doc = {
        "id": msg_id,
        "sender_id": current_user["id"],
        "sender_name": current_user["name"],
        "recipient_id": msg_data.recipient_id,
        "recipient_name": recipient["name"],
        "subject": msg_data.subject,
        "content": msg_data.content,
        "is_read": False,
        "created_at": now
    }
    
    await db.messages.insert_one(msg_doc)
    return MessageResponse(**msg_doc)

@api_router.get("/messages", response_model=List[MessageResponse])
async def get_messages(sent: bool = False, current_user: dict = Depends(get_current_user)):
    if sent:
        query = {"sender_id": current_user["id"]}
    else:
        query = {"recipient_id": current_user["id"]}
    
    messages = await db.messages.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [MessageResponse(**m) for m in messages]

@api_router.put("/messages/{msg_id}/read")
async def mark_message_read(msg_id: str, current_user: dict = Depends(get_current_user)):
    result = await db.messages.update_one(
        {"id": msg_id, "recipient_id": current_user["id"]},
        {"$set": {"is_read": True}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"message": "Marked as read"}

# ============== DASHBOARD STATS ==============

@api_router.get("/stats/admin")
async def get_admin_stats(current_user: dict = Depends(require_role(["admin"]))):
    total_users = await db.users.count_documents({})
    total_jobs = await db.jobs.count_documents({})
    total_applications = await db.applications.count_documents({})
    total_companies = await db.companies.count_documents({})
    
    users_by_role = await db.users.aggregate([
        {"$group": {"_id": "$role", "count": {"$sum": 1}}}
    ]).to_list(10)
    
    recent_applications = await db.applications.find({}, {"_id": 0}).sort("created_at", -1).to_list(5)
    
    return {
        "total_users": total_users,
        "total_jobs": total_jobs,
        "total_applications": total_applications,
        "total_companies": total_companies,
        "users_by_role": {item["_id"]: item["count"] for item in users_by_role},
        "recent_applications": recent_applications
    }

@api_router.get("/stats/recruiter")
async def get_recruiter_stats(current_user: dict = Depends(require_role(["recruiter"]))):
    total_jobs = await db.jobs.count_documents({})
    total_candidates = await db.candidate_profiles.count_documents({})
    
    pipeline_stats = await db.applications.aggregate([
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}}
    ]).to_list(10)
    
    return {
        "total_jobs": total_jobs,
        "total_candidates": total_candidates,
        "pipeline_stats": {item["_id"]: item["count"] for item in pipeline_stats}
    }

@api_router.get("/stats/employer")
async def get_employer_stats(current_user: dict = Depends(require_role(["employer"]))):
    my_jobs = await db.jobs.count_documents({"posted_by": current_user["id"]})
    
    jobs = await db.jobs.find({"posted_by": current_user["id"]}, {"id": 1, "_id": 0}).to_list(1000)
    job_ids = [j["id"] for j in jobs]
    
    total_applicants = await db.applications.count_documents({"job_id": {"$in": job_ids}})
    
    stage_stats = await db.applications.aggregate([
        {"$match": {"job_id": {"$in": job_ids}}},
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}}
    ]).to_list(10)
    
    return {
        "my_jobs": my_jobs,
        "total_applicants": total_applicants,
        "stage_stats": {item["_id"]: item["count"] for item in stage_stats}
    }

@api_router.get("/stats/candidate")
async def get_candidate_stats(current_user: dict = Depends(require_role(["candidate"]))):
    my_applications = await db.applications.count_documents({"candidate_id": current_user["id"]})
    active_jobs = await db.jobs.count_documents({"status": "active"})
    
    app_stages = await db.applications.aggregate([
        {"$match": {"candidate_id": current_user["id"]}},
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}}
    ]).to_list(10)
    
    unread_messages = await db.messages.count_documents({
        "recipient_id": current_user["id"],
        "is_read": False
    })
    
    return {
        "my_applications": my_applications,
        "active_jobs": active_jobs,
        "application_stages": {item["_id"]: item["count"] for item in app_stages},
        "unread_messages": unread_messages
    }

# ============== AI MATCHING ENGINE ==============

from services.matching_engine import (
    parse_resume_with_ai,
    parse_job_description_with_ai,
    calculate_candidate_job_match,
    apply_must_have_filters,
    generate_resume_fingerprint,
    find_similar_candidate
)

def extract_text_from_pdf(file_path: Path) -> str:
    """Extract text from PDF file"""
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

def normalize_phone(phone: str) -> str:
    """Normalize phone number for deduplication"""
    if not phone:
        return ""
    return "".join(filter(str.isdigit, phone))[-10:]

async def create_audit_log(
    candidate_id: str,
    field: str,
    old_val: Any,
    new_val: Any,
    user: dict,
    source: str
):
    """Create audit trail entry for candidate data changes"""
    log_entry = {
        "id": str(uuid.uuid4()),
        "candidate_id": candidate_id,
        "field_changed": field,
        "old_value": str(old_val) if old_val else None,
        "new_value": str(new_val) if new_val else None,
        "updated_by_role": user["role"],
        "updated_by_id": user["id"],
        "updated_by_name": user["name"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source
    }
    await db.audit_logs.insert_one(log_entry)

# Data update priority: candidate > employer > recruiter > parsing
UPDATE_PRIORITY = {
    "candidate": 4,
    "employer": 3,
    "recruiter": 2,
    "admin": 5,
    "parsing": 1
}

async def should_update_field(
    candidate_id: str,
    field: str,
    new_source: str,
    db
) -> bool:
    """Check if update should proceed based on priority rules"""
    # Get last update source for this field
    last_log = await db.audit_logs.find_one(
        {"candidate_id": candidate_id, "field_changed": field},
        sort=[("timestamp", -1)]
    )
    
    if not last_log:
        return True
    
    last_source_role = last_log.get("updated_by_role", "parsing")
    last_priority = UPDATE_PRIORITY.get(last_source_role, 1)
    new_priority = UPDATE_PRIORITY.get(new_source, 1)
    
    return new_priority >= last_priority

@api_router.post("/ai/parse-resume")
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

@api_router.post("/ai/parse-jd")
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

@api_router.post("/matching/find-candidates", response_model=List[MatchResult])
async def find_matching_candidates(
    match_req: MatchRequest,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Find candidates matching job requirements with AI scoring"""
    
    # Get job requirements
    job_data = None
    if match_req.job_id:
        job = await db.jobs.find_one({"id": match_req.job_id}, {"_id": 0})
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        # Parse existing job description
        jd_result = await parse_job_description_with_ai(job.get("description", "") + " " + job.get("requirements", ""))
        if jd_result["success"]:
            job_data = jd_result["data"]
    elif match_req.jd_text:
        jd_result = await parse_job_description_with_ai(match_req.jd_text)
        if jd_result["success"]:
            job_data = jd_result["data"]
    
    if not job_data:
        raise HTTPException(status_code=400, detail="Could not parse job requirements")
    
    # Build must-have filters
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
    
    # CRITICAL: AI Screening searches ENTIRE candidate database
    # This is a SYSTEM-LEVEL INTELLIGENCE function, not UI-level visibility filter
    # DATA VISIBILITY ≠ AI SEARCH SCOPE
    # Results are READ-ONLY, CONTEXTUAL VISIBILITY - no edit/ownership rights granted
    query = {}  # No role-based filtering for AI screening input
    
    candidates = await db.candidate_bank.find(query, {"_id": 0}).to_list(1000)
    
    results = []
    for candidate in candidates:
        match_result = await calculate_candidate_job_match(candidate, job_data, must_have if must_have else None)
        
        # Determine candidate source for display
        source = candidate.get("source", "unknown")
        created_by_role = None
        if candidate.get("created_by"):
            creator = await db.users.find_one({"id": candidate["created_by"]}, {"role": 1, "_id": 0})
            if creator:
                created_by_role = creator.get("role")
        
        results.append(MatchResult(
            candidate_id=candidate["id"],
            candidate_name=candidate["name"],
            candidate_email=candidate["email"],
            score=match_result.get("score", 0),
            skill_match_score=match_result.get("skill_match_score"),
            experience_match_score=match_result.get("experience_match_score"),
            matched_skills=match_result.get("matched_skills", []),
            missing_skills=match_result.get("missing_skills", []),
            strengths=match_result.get("strengths", []),
            gaps=match_result.get("gaps", []),
            explanation=match_result.get("explanation", ""),
            filtered_out=match_result.get("filtered_out", False),
            filter_reason=match_result.get("filter_reason"),
            source=source,
            source_role=created_by_role
        ))
    
    # Sort by score descending, filtered_out last
    results.sort(key=lambda x: (not x.filtered_out, x.score), reverse=True)
    
    # Store match results for analytics
    if match_req.job_id:
        await db.match_results.insert_one({
            "id": str(uuid.uuid4()),
            "job_id": match_req.job_id,
            "searched_by": current_user["id"],
            "searched_by_role": current_user["role"],
            "total_candidates": len(candidates),
            "matched_count": len([r for r in results if r.score >= 50 and not r.filtered_out]),
            "filters_applied": must_have,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    return results

@api_router.get("/matching/jobs-for-candidate", response_model=List[JobMatchForCandidate])
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


# Note: CANDIDATE DATA BANK routes have been extracted to routes/candidates.py
# Endpoints: /api/candidate-bank, /api/candidate-bank/{candidate_id},
#            /api/candidate-bank/add, /api/candidate-bank/batch-parse,
#            /api/candidate-bank/batch-save, /api/candidates/{candidate_id}/resume,
#            /api/candidate-bank/{candidate_id}/download-resume,
#            /api/candidate-bank/{candidate_id}/salary-notice,
#            /api/candidate-bank/{candidate_id}/audit-log,
#            /api/candidate-bank/{candidate_id}/history,
#            /api/candidate-bank/{candidate_id}/resume-history,
#            /api/applications/link-candidate

# ============== JOB ALERTS & NOTIFICATIONS ==============

from services.notification_service import (
    notify_candidate_of_job_match,
    process_job_notifications,
    trigger_job_notifications_background,
    send_alert_confirmation_email,
    get_candidate_notification_preferences
)
from services.whatsapp_service import validate_phone_number, is_whatsapp_enabled

@api_router.get("/alerts/preferences", response_model=JobAlertPreferences)
async def get_alert_preferences(current_user: dict = Depends(require_role(["candidate"]))):
    """Get candidate's job alert preferences"""
    prefs = await db.job_alerts.find_one({"candidate_id": current_user["id"]}, {"_id": 0})
    
    if not prefs:
        # Get candidate profile to populate default skills
        profile = await db.candidate_profiles.find_one({"user_id": current_user["id"]}, {"_id": 0})
        default_skills = profile.get("skills", []) if profile else []
        
        # Also check candidate_bank for skills
        if not default_skills:
            bank_record = await db.candidate_bank.find_one(
                {"$or": [{"linked_user_id": current_user["id"]}, {"email": current_user["email"]}]},
                {"_id": 0}
            )
            if bank_record:
                default_skills = bank_record.get("skills", [])
        
        # Create default preferences
        now = datetime.now(timezone.utc).isoformat()
        prefs = {
            "id": str(uuid.uuid4()),
            "candidate_id": current_user["id"],
            "candidate_email": current_user["email"],
            "is_active": False,  # Not active until explicitly enabled
            "email_enabled": True,
            "skills": default_skills[:10],  # Limit to 10 skills
            "location_preference": None,
            "experience_min": None,
            "experience_max": None,
            "job_types": [],
            "frequency": "instant",
            "whatsapp_opt_in": False,
            "whatsapp_number": None,
            "whatsapp_opt_in_timestamp": None,
            "notification_channels": ["email"],
            "created_at": now,
            "updated_at": now
        }
        await db.job_alerts.insert_one(prefs)
    
    return JobAlertPreferences(**prefs)


@api_router.post("/alerts/preferences", response_model=JobAlertPreferences)
async def create_or_update_alert_preferences(
    prefs_data: JobAlertCreate,
    current_user: dict = Depends(require_role(["candidate"]))
):
    """Create or update job alert preferences (opt-in to alerts)"""
    now = datetime.now(timezone.utc).isoformat()
    
    existing = await db.job_alerts.find_one({"candidate_id": current_user["id"]}, {"_id": 0})
    
    update_dict = {k: v for k, v in prefs_data.model_dump().items() if v is not None}
    update_dict["updated_at"] = now
    update_dict["is_active"] = True  # Activating alerts
    
    if existing:
        await db.job_alerts.update_one(
            {"candidate_id": current_user["id"]},
            {"$set": update_dict}
        )
        prefs = await db.job_alerts.find_one({"candidate_id": current_user["id"]}, {"_id": 0})
    else:
        # Get default skills from profile
        profile = await db.candidate_profiles.find_one({"user_id": current_user["id"]}, {"_id": 0})
        default_skills = profile.get("skills", []) if profile else []
        
        prefs = {
            "id": str(uuid.uuid4()),
            "candidate_id": current_user["id"],
            "candidate_email": current_user["email"],
            "is_active": True,
            "email_enabled": update_dict.get("email_enabled", True),
            "skills": update_dict.get("skills", default_skills[:10]),
            "location_preference": update_dict.get("location_preference"),
            "experience_min": update_dict.get("experience_min"),
            "experience_max": update_dict.get("experience_max"),
            "job_types": update_dict.get("job_types", []),
            "frequency": update_dict.get("frequency", "instant"),
            "whatsapp_opt_in": False,
            "whatsapp_number": None,
            "whatsapp_opt_in_timestamp": None,
            "notification_channels": ["email"],
            "created_at": now,
            "updated_at": now
        }
        await db.job_alerts.insert_one(prefs)
    
    # Send confirmation email
    asyncio.create_task(send_alert_confirmation_email(
        db=db,
        candidate_email=current_user["email"],
        candidate_name=current_user.get("name", "Candidate"),
        preferences=prefs
    ))
    
    return JobAlertPreferences(**prefs)


@api_router.put("/alerts/preferences", response_model=JobAlertPreferences)
async def update_alert_preferences(
    prefs_data: JobAlertCreate,
    current_user: dict = Depends(require_role(["candidate"]))
):
    """Update existing job alert preferences"""
    existing = await db.job_alerts.find_one({"candidate_id": current_user["id"]})
    if not existing:
        raise HTTPException(status_code=404, detail="Alert preferences not found. Create them first.")
    
    update_dict = {k: v for k, v in prefs_data.model_dump().items() if v is not None}
    update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.job_alerts.update_one(
        {"candidate_id": current_user["id"]},
        {"$set": update_dict}
    )
    
    prefs = await db.job_alerts.find_one({"candidate_id": current_user["id"]}, {"_id": 0})
    return JobAlertPreferences(**prefs)


@api_router.delete("/alerts/preferences")
async def delete_alert_preferences(current_user: dict = Depends(require_role(["candidate"]))):
    """Unsubscribe from all job alerts (soft delete - sets is_active to false)"""
    result = await db.job_alerts.update_one(
        {"candidate_id": current_user["id"]},
        {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Alert preferences not found")
    
    return {"message": "Successfully unsubscribed from job alerts"}


@api_router.post("/alerts/pause")
async def pause_alerts(current_user: dict = Depends(require_role(["candidate"]))):
    """Temporarily pause job alerts"""
    await db.job_alerts.update_one(
        {"candidate_id": current_user["id"]},
        {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"message": "Job alerts paused"}


@api_router.post("/alerts/resume")
async def resume_alerts(current_user: dict = Depends(require_role(["candidate"]))):
    """Resume paused job alerts"""
    await db.job_alerts.update_one(
        {"candidate_id": current_user["id"]},
        {"$set": {"is_active": True, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"message": "Job alerts resumed"}


# ============== WHATSAPP OPT-IN/OUT ==============

@api_router.post("/alerts/whatsapp/opt-in", response_model=JobAlertPreferences)
async def whatsapp_opt_in(
    opt_in_data: WhatsAppOptIn,
    current_user: dict = Depends(require_role(["candidate"]))
):
    """
    Opt-in to WhatsApp notifications.
    REQUIRES explicit consent and valid phone number.
    """
    if not is_whatsapp_enabled():
        raise HTTPException(
            status_code=400, 
            detail="WhatsApp notifications are not configured on this system"
        )
    
    # Validate phone number
    validated_phone = validate_phone_number(opt_in_data.whatsapp_number)
    if not validated_phone:
        raise HTTPException(status_code=400, detail="Invalid phone number format. Use E.164 format (e.g., +919876543210)")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Ensure alert preferences exist
    existing = await db.job_alerts.find_one({"candidate_id": current_user["id"]})
    if not existing:
        # Create default preferences first
        prefs = {
            "id": str(uuid.uuid4()),
            "candidate_id": current_user["id"],
            "candidate_email": current_user["email"],
            "is_active": True,
            "email_enabled": True,
            "skills": [],
            "location_preference": None,
            "experience_min": None,
            "experience_max": None,
            "job_types": [],
            "frequency": "instant",
            "whatsapp_opt_in": True,
            "whatsapp_number": validated_phone,
            "whatsapp_opt_in_timestamp": now,
            "notification_channels": ["email", "whatsapp"],
            "created_at": now,
            "updated_at": now
        }
        await db.job_alerts.insert_one(prefs)
    else:
        # Update existing with WhatsApp opt-in
        update_data = {
            "whatsapp_opt_in": True,
            "whatsapp_number": validated_phone,
            "whatsapp_opt_in_timestamp": now,
            "notification_channels": list(set(existing.get("notification_channels", []) + ["whatsapp"])),
            "updated_at": now
        }
        await db.job_alerts.update_one(
            {"candidate_id": current_user["id"]},
            {"$set": update_data}
        )
    
    prefs = await db.job_alerts.find_one({"candidate_id": current_user["id"]}, {"_id": 0})
    return JobAlertPreferences(**prefs)


@api_router.post("/alerts/whatsapp/opt-out")
async def whatsapp_opt_out(current_user: dict = Depends(require_role(["candidate"]))):
    """
    Opt-out of WhatsApp notifications.
    Email notifications remain unaffected.
    """
    now = datetime.now(timezone.utc).isoformat()
    
    existing = await db.job_alerts.find_one({"candidate_id": current_user["id"]})
    if existing:
        channels = existing.get("notification_channels", ["email"])
        if "whatsapp" in channels:
            channels.remove("whatsapp")
        
        await db.job_alerts.update_one(
            {"candidate_id": current_user["id"]},
            {"$set": {
                "whatsapp_opt_in": False,
                "notification_channels": channels,
                "updated_at": now
            }}
        )
    
    return {"message": "Successfully opted out of WhatsApp notifications"}


@api_router.put("/alerts/whatsapp/number")
async def update_whatsapp_number(
    opt_in_data: WhatsAppOptIn,
    current_user: dict = Depends(require_role(["candidate"]))
):
    """Update WhatsApp phone number (must already be opted in)"""
    existing = await db.job_alerts.find_one({"candidate_id": current_user["id"]})
    if not existing or not existing.get("whatsapp_opt_in"):
        raise HTTPException(status_code=400, detail="Please opt-in to WhatsApp first")
    
    validated_phone = validate_phone_number(opt_in_data.whatsapp_number)
    if not validated_phone:
        raise HTTPException(status_code=400, detail="Invalid phone number format")
    
    await db.job_alerts.update_one(
        {"candidate_id": current_user["id"]},
        {"$set": {
            "whatsapp_number": validated_phone,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"message": "WhatsApp number updated", "number": validated_phone}


# ============== NOTIFICATION HISTORY ==============

@api_router.get("/notifications/history")
async def get_notification_history(
    limit: int = 20,
    current_user: dict = Depends(require_role(["candidate"]))
):
    """Get notification history for current candidate"""
    notifications = await db.notification_logs.find(
        {"recipient_id": current_user["id"]},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    return notifications


@api_router.get("/admin/notifications/stats")
async def get_notification_stats(current_user: dict = Depends(require_role(["admin"]))):
    """Get notification statistics (admin only)"""
    # Total notifications sent
    total_sent = await db.notification_logs.count_documents({"status": "sent"})
    total_failed = await db.notification_logs.count_documents({"status": "failed"})
    total_skipped = await db.notification_logs.count_documents({"status": "skipped"})
    
    # By channel
    email_sent = await db.notification_logs.count_documents({"channel": "email", "status": "sent"})
    whatsapp_sent = await db.notification_logs.count_documents({"channel": "whatsapp", "status": "sent"})
    
    # Active alert subscribers
    active_subscribers = await db.job_alerts.count_documents({"is_active": True})
    whatsapp_opted_in = await db.job_alerts.count_documents({"whatsapp_opt_in": True})
    
    return {
        "total_sent": total_sent,
        "total_failed": total_failed,
        "total_skipped": total_skipped,
        "email_sent": email_sent,
        "whatsapp_sent": whatsapp_sent,
        "active_subscribers": active_subscribers,
        "whatsapp_opted_in": whatsapp_opted_in
    }


# ============== TRIGGER NOTIFICATIONS ON JOB EVENTS ==============

import asyncio

# Note: Job notification routes have been extracted to routes/jobs.py
# Endpoints: /api/jobs/with-notifications, /api/jobs/{job_id}/notify-candidates

# Note: PUBLIC API routes have been extracted to routes/public.py
# Endpoints: /api/public/jobs, /api/public/jobs/{job_id}, /api/public/parse-resume,
#            /api/public/apply, /api/public/upload-resume

# ============== SETTINGS ==============

@api_router.get("/settings")
async def get_settings(current_user: dict = Depends(require_role(["admin"]))):
    settings = await db.settings.find_one({"type": "global"}, {"_id": 0})
    if not settings:
        settings = {
            "type": "global",
            "ai_parsing_enabled": True,
            "email_notifications": True,
            "max_applications_per_job": 100,
            "resume_size_limit_mb": 5
        }
        await db.settings.insert_one(settings)
    return settings

@api_router.put("/settings")
async def update_settings(settings_data: dict, current_user: dict = Depends(require_role(["admin"]))):
    await db.settings.update_one(
        {"type": "global"},
        {"$set": settings_data},
        upsert=True
    )
    return {"message": "Settings updated successfully"}

# ============== PHASE-A: TEAM MANAGEMENT ==============

@api_router.post("/teams", response_model=TeamResponse)
async def create_team(team_data: TeamCreate, current_user: dict = Depends(require_role(["admin"]))):
    """
    Create a new Team (Admin only).
    
    A Team links:
    - One Employer (team owner/manager)
    - Multiple Recruiters (team members)
    - Multiple Companies (client companies the team manages)
    """
    # Validate employer exists and has correct role
    employer = await db.users.find_one({"id": team_data.employer_id, "role": "employer"}, {"_id": 0})
    if not employer:
        raise HTTPException(status_code=404, detail="Employer not found")
    
    # Validate all recruiters exist and have correct role
    recruiter_names = []
    for recruiter_id in team_data.recruiter_ids:
        recruiter = await db.users.find_one({"id": recruiter_id, "role": "recruiter"}, {"_id": 0})
        if not recruiter:
            raise HTTPException(status_code=400, detail=f"Recruiter {recruiter_id} not found")
        recruiter_names.append(recruiter.get("name", "Unknown"))
    
    # Validate all companies exist
    company_names = []
    for company_id in team_data.company_ids:
        company = await db.companies.find_one({"id": company_id}, {"_id": 0})
        if not company:
            raise HTTPException(status_code=400, detail=f"Company {company_id} not found")
        company_names.append(company.get("name", "Unknown"))
    
    team_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    team_doc = {
        "id": team_id,
        "name": team_data.name,
        "employer_id": team_data.employer_id,
        "employer_name": employer.get("name"),
        "recruiter_ids": team_data.recruiter_ids,
        "recruiter_names": recruiter_names,
        "company_ids": team_data.company_ids,
        "company_names": company_names,
        "status": "active",
        "active_jobs_count": 0,
        "created_at": now,
        "updated_at": now,
        "created_by": current_user["id"],
        "audit_log": [{
            "action": "created",
            "by_id": current_user["id"],
            "by_name": current_user["name"],
            "by_role": current_user["role"],
            "timestamp": now
        }]
    }
    
    await db.teams.insert_one(team_doc)
    
    # Update recruiters with team assignment
    for recruiter_id in team_data.recruiter_ids:
        await db.users.update_one(
            {"id": recruiter_id},
            {"$set": {"team_id": team_id, "updated_at": now}}
        )
    
    # Update companies with employer assignment
    for company_id in team_data.company_ids:
        await db.companies.update_one(
            {"id": company_id},
            {"$set": {"assigned_employer_id": team_data.employer_id, "team_id": team_id, "updated_at": now}}
        )
    
    logging.info(f"Team '{team_data.name}' created by {current_user['name']}")
    
    return TeamResponse(**team_doc)


@api_router.get("/teams", response_model=List[TeamResponse])
async def get_teams(current_user: dict = Depends(require_role(["admin", "employer"]))):
    """
    Get all teams.
    - Admin: sees all teams
    - Employer: sees only their teams
    """
    query = {}
    if current_user["role"] == "employer":
        query["employer_id"] = current_user["id"]
    
    teams = await db.teams.find(query, {"_id": 0}).to_list(1000)
    
    # Enrich with active jobs count
    for team in teams:
        jobs_count = await db.jobs.count_documents({
            "team_id": team["id"],
            "status": {"$in": ["active", "pending_approval"]}
        })
        team["active_jobs_count"] = jobs_count
    
    return [TeamResponse(**t) for t in teams]


@api_router.get("/employer/my-team")
async def get_employer_team_with_metrics(current_user: dict = Depends(require_role(["employer"]))):
    """
    Get employer's team with detailed performance metrics.
    Shows: team members, mandates assigned, pipelines, revenue per stage, closed revenue.
    
    Internal endpoint for Employer portal "My Team" panel.
    """
    # Get employer's team
    team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
    
    if not team:
        return {
            "team": None,
            "members": [],
            "summary": {
                "total_members": 0,
                "total_mandates": 0,
                "total_pipeline": 0,
                "total_revenue_pipeline": 0,
                "total_revenue_closed": 0
            }
        }
    
    # Get team member details
    recruiter_ids = team.get("recruiter_ids", [])
    recruiters = await db.users.find(
        {"id": {"$in": recruiter_ids}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "is_active": 1, "created_at": 1}
    ).to_list(100)
    
    # Get jobs/mandates under employer's companies
    company_ids = team.get("company_ids", [])
    employer_jobs = await db.jobs.find(
        {"$or": [
            {"team_id": team["id"]},
            {"company_id": {"$in": company_ids}},
            {"posted_by": {"$in": recruiter_ids + [current_user["id"]]}}
        ]},
        {"_id": 0}
    ).to_list(1000)
    
    job_ids = [j["id"] for j in employer_jobs]
    
    # Get all applications for these jobs
    applications = await db.applications.find(
        {"job_id": {"$in": job_ids}},
        {"_id": 0}
    ).to_list(10000)
    
    # Get commercials for revenue calculation
    commercials = await db.commercials.find(
        {"company_id": {"$in": company_ids}},
        {"_id": 0}
    ).to_list(100)
    commercial_by_company = {c["company_id"]: c for c in commercials}
    
    # Calculate per-member metrics
    members_with_metrics = []
    
    for recruiter in recruiters:
        # Jobs assigned to this recruiter
        recruiter_jobs = [j for j in employer_jobs if 
                         j.get("posted_by") == recruiter["id"] or 
                         recruiter["id"] in j.get("assigned_recruiters", [])]
        recruiter_job_ids = [j["id"] for j in recruiter_jobs]
        
        # Applications for recruiter's jobs
        recruiter_apps = [a for a in applications if a["job_id"] in recruiter_job_ids]
        
        # Pipeline stages count
        stages = {
            "applied": 0, "shortlisted": 0, "interview": 0,
            "offered": 0, "hired": 0, "rejected": 0
        }
        for app in recruiter_apps:
            stage = app.get("stage", "applied")
            if stage in stages:
                stages[stage] += 1
        
        # Revenue calculation
        revenue_pipeline = 0
        revenue_closed = 0
        
        for app in recruiter_apps:
            job = next((j for j in recruiter_jobs if j["id"] == app["job_id"]), None)
            if job:
                company_id = job.get("company_id")
                commercial = commercial_by_company.get(company_id)
                offered_salary = app.get("offered_salary", 0) or app.get("current_salary", 0) or 0
                
                if commercial and offered_salary > 0:
                    fee_percent = commercial.get("fee_percentage", 0) or 8.33
                    revenue = (offered_salary * fee_percent) / 100
                    
                    if app.get("stage") == "hired":
                        revenue_closed += revenue
                    elif app.get("stage") in ["offered", "interview", "shortlisted"]:
                        revenue_pipeline += revenue
        
        members_with_metrics.append({
            "id": recruiter["id"],
            "name": recruiter["name"],
            "email": recruiter["email"],
            "is_active": recruiter.get("is_active", True),
            "joined_at": recruiter.get("created_at"),
            "mandates_assigned": len(recruiter_jobs),
            "mandates": [{"id": j["id"], "title": j["title"], "company_name": j.get("company_name")} for j in recruiter_jobs[:5]],
            "pipeline": stages,
            "total_pipeline_count": sum(stages.values()),
            "revenue_pipeline": round(revenue_pipeline, 2),
            "revenue_closed": round(revenue_closed, 2)
        })
    
    # Calculate team totals
    total_pipeline = sum(m["total_pipeline_count"] for m in members_with_metrics)
    total_revenue_pipeline = sum(m["revenue_pipeline"] for m in members_with_metrics)
    total_revenue_closed = sum(m["revenue_closed"] for m in members_with_metrics)
    
    return {
        "team": {
            "id": team["id"],
            "name": team["name"],
            "company_ids": company_ids,
            "company_names": team.get("company_names", [])
        },
        "members": members_with_metrics,
        "summary": {
            "total_members": len(members_with_metrics),
            "total_mandates": len(employer_jobs),
            "total_pipeline": total_pipeline,
            "total_revenue_pipeline": round(total_revenue_pipeline, 2),
            "total_revenue_closed": round(total_revenue_closed, 2)
        }
    }


@api_router.get("/employer/companies")
async def get_employer_companies_with_details(current_user: dict = Depends(require_role(["employer"]))):
    """
    Get employer's assigned companies with commercial details, mandates, and pipelines.
    
    Internal endpoint for Employer portal "Companies" panel.
    Returns companies assigned by Admin with:
    - Commercial details (read-only)
    - Active mandates
    - Pipeline data grouped by mandate
    """
    # Get employer's team to find assigned companies
    team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
    
    if not team:
        return {"companies": []}
    
    company_ids = team.get("company_ids", [])
    
    if not company_ids:
        return {"companies": []}
    
    # Get companies
    companies = await db.companies.find(
        {"id": {"$in": company_ids}},
        {"_id": 0}
    ).to_list(100)
    
    # Get commercials for each company
    commercials = await db.commercials.find(
        {"company_id": {"$in": company_ids}},
        {"_id": 0}
    ).to_list(100)
    commercial_by_company = {c["company_id"]: c for c in commercials}
    
    # Get jobs for each company
    all_jobs = await db.jobs.find(
        {"company_id": {"$in": company_ids}},
        {"_id": 0}
    ).to_list(1000)
    
    # Get applications for pipeline data
    job_ids = [j["id"] for j in all_jobs]
    applications = await db.applications.find(
        {"job_id": {"$in": job_ids}},
        {"_id": 0}
    ).to_list(10000)
    
    enriched_companies = []
    
    for company in companies:
        company_id = company["id"]
        commercial = commercial_by_company.get(company_id, {})
        company_jobs = [j for j in all_jobs if j.get("company_id") == company_id]
        company_job_ids = [j["id"] for j in company_jobs]
        company_apps = [a for a in applications if a["job_id"] in company_job_ids]
        
        # Group pipeline by mandate
        mandates_with_pipeline = []
        for job in company_jobs:
            job_apps = [a for a in company_apps if a["job_id"] == job["id"]]
            
            stages = {"applied": 0, "shortlisted": 0, "interview": 0, "offered": 0, "hired": 0, "rejected": 0}
            revenue_by_stage = {"applied": 0, "shortlisted": 0, "interview": 0, "offered": 0, "hired": 0}
            
            fee_percent = commercial.get("fee_percentage", 0) or 8.33
            
            for app in job_apps:
                stage = app.get("stage", "applied")
                if stage in stages:
                    stages[stage] += 1
                
                offered_salary = app.get("offered_salary", 0) or app.get("current_salary", 0) or 0
                if offered_salary > 0 and stage in revenue_by_stage:
                    revenue_by_stage[stage] += (offered_salary * fee_percent) / 100
            
            mandates_with_pipeline.append({
                "id": job["id"],
                "title": job["title"],
                "status": job.get("status", "active"),
                "location": job.get("location"),
                "posted_by": job.get("posted_by"),
                "created_at": job.get("created_at"),
                "pipeline_count": sum(stages.values()),
                "stages": stages,
                "revenue_by_stage": {k: round(v, 2) for k, v in revenue_by_stage.items()},
                "total_revenue_pipeline": round(sum(v for k, v in revenue_by_stage.items() if k != "hired"), 2),
                "total_revenue_closed": round(revenue_by_stage.get("hired", 0), 2)
            })
        
        # Calculate company totals
        total_pipeline = sum(m["pipeline_count"] for m in mandates_with_pipeline)
        total_revenue_closed = sum(m["total_revenue_closed"] for m in mandates_with_pipeline)
        
        enriched_companies.append({
            "id": company_id,
            "name": company["name"],
            "industry": company.get("industry"),
            "location": company.get("location"),
            "logo_url": company.get("logo_url"),
            # Commercial details (read-only for employer)
            "commercial": {
                "fee_percentage": commercial.get("fee_percentage"),
                "fee_structure": commercial.get("fee_structure"),
                "payment_terms": commercial.get("payment_terms"),
                "currency": commercial.get("currency", "INR"),
                "commercial_slabs": commercial.get("commercial_slabs", []),
                "is_active": commercial.get("is_active", True)
            },
            # Mandates
            "mandates": mandates_with_pipeline,
            "active_mandates_count": len([m for m in mandates_with_pipeline if m["status"] == "active"]),
            # Summary
            "total_pipeline": total_pipeline,
            "total_revenue_closed": round(total_revenue_closed, 2)
        })
    
    return {"companies": enriched_companies}


@api_router.get("/teams/{team_id}", response_model=TeamResponse)
async def get_team(team_id: str, current_user: dict = Depends(require_role(["admin", "employer"]))):
    """Get a specific team by ID."""
    team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Employer can only view their own teams
    if current_user["role"] == "employer" and team["employer_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get active jobs count
    jobs_count = await db.jobs.count_documents({
        "team_id": team_id,
        "status": {"$in": ["active", "pending_approval"]}
    })
    team["active_jobs_count"] = jobs_count
    
    return TeamResponse(**team)


@api_router.put("/teams/{team_id}", response_model=TeamResponse)
async def update_team(team_id: str, update_data: TeamUpdate, current_user: dict = Depends(require_role(["admin"]))):
    """
    Update a team (Admin only).
    Can update name, recruiters, companies, and status.
    """
    team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    now = datetime.now(timezone.utc).isoformat()
    update_dict = {"updated_at": now}
    audit_entries = []
    
    if update_data.name is not None:
        audit_entries.append({
            "action": "name_changed",
            "old_value": team.get("name"),
            "new_value": update_data.name,
            "by_id": current_user["id"],
            "by_name": current_user["name"],
            "by_role": current_user["role"],
            "timestamp": now
        })
        update_dict["name"] = update_data.name
    
    if update_data.status is not None:
        audit_entries.append({
            "action": "status_changed",
            "old_value": team.get("status"),
            "new_value": update_data.status,
            "by_id": current_user["id"],
            "by_name": current_user["name"],
            "by_role": current_user["role"],
            "timestamp": now
        })
        update_dict["status"] = update_data.status
    
    if update_data.recruiter_ids is not None:
        # Validate new recruiters
        recruiter_names = []
        for recruiter_id in update_data.recruiter_ids:
            recruiter = await db.users.find_one({"id": recruiter_id, "role": "recruiter"}, {"_id": 0})
            if not recruiter:
                raise HTTPException(status_code=400, detail=f"Recruiter {recruiter_id} not found")
            recruiter_names.append(recruiter.get("name", "Unknown"))
        
        # Remove old recruiters from team
        old_recruiter_ids = team.get("recruiter_ids", [])
        for old_id in old_recruiter_ids:
            if old_id not in update_data.recruiter_ids:
                await db.users.update_one(
                    {"id": old_id},
                    {"$unset": {"team_id": ""}}
                )
        
        # Add new recruiters to team
        for new_id in update_data.recruiter_ids:
            await db.users.update_one(
                {"id": new_id},
                {"$set": {"team_id": team_id, "updated_at": now}}
            )
        
        audit_entries.append({
            "action": "recruiters_changed",
            "old_value": old_recruiter_ids,
            "new_value": update_data.recruiter_ids,
            "by_id": current_user["id"],
            "by_name": current_user["name"],
            "by_role": current_user["role"],
            "timestamp": now
        })
        update_dict["recruiter_ids"] = update_data.recruiter_ids
        update_dict["recruiter_names"] = recruiter_names
    
    if update_data.company_ids is not None:
        # Validate new companies
        company_names = []
        for company_id in update_data.company_ids:
            company = await db.companies.find_one({"id": company_id}, {"_id": 0})
            if not company:
                raise HTTPException(status_code=400, detail=f"Company {company_id} not found")
            company_names.append(company.get("name", "Unknown"))
        
        # Update company assignments
        old_company_ids = team.get("company_ids", [])
        for old_id in old_company_ids:
            if old_id not in update_data.company_ids:
                await db.companies.update_one(
                    {"id": old_id},
                    {"$unset": {"assigned_employer_id": "", "team_id": ""}}
                )
        
        for new_id in update_data.company_ids:
            await db.companies.update_one(
                {"id": new_id},
                {"$set": {"assigned_employer_id": team["employer_id"], "team_id": team_id, "updated_at": now}}
            )
        
        audit_entries.append({
            "action": "companies_changed",
            "old_value": old_company_ids,
            "new_value": update_data.company_ids,
            "by_id": current_user["id"],
            "by_name": current_user["name"],
            "by_role": current_user["role"],
            "timestamp": now
        })
        update_dict["company_ids"] = update_data.company_ids
        update_dict["company_names"] = company_names
    
    await db.teams.update_one(
        {"id": team_id},
        {
            "$set": update_dict,
            "$push": {"audit_log": {"$each": audit_entries}}
        }
    )
    
    updated_team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    return TeamResponse(**updated_team)


@api_router.delete("/teams/{team_id}")
async def delete_team(team_id: str, current_user: dict = Depends(require_role(["admin"]))):
    """
    Soft delete a team (Admin only).
    Sets status to 'disabled' instead of actual deletion.
    """
    team = await db.teams.find_one({"id": team_id}, {"_id": 0})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.teams.update_one(
        {"id": team_id},
        {
            "$set": {"status": "disabled", "updated_at": now},
            "$push": {"audit_log": {
                "action": "disabled",
                "by_id": current_user["id"],
                "by_name": current_user["name"],
                "by_role": current_user["role"],
                "timestamp": now
            }}
        }
    )
    
    logging.info(f"Team {team_id} disabled by {current_user['name']}")
    
    return {"message": "Team disabled successfully"}


# ============== PHASE-A: REFERRAL MANAGEMENT ==============

@api_router.post("/referrals", response_model=ReferralResponse)
async def create_referral(referral_data: ReferralCreate, current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))):
    """
    Create a new candidate referral.
    
    Referral Lifecycle:
    1. submitted - Initial submission
    2. validated - Referral details verified
    3. linked - Linked to candidate bank record
    4. in_process - Candidate is being processed for the job
    5. outcome_reached - Hiring decision made
    6. closed - Referral process complete
    """
    # Validate job exists and is active
    job = await db.jobs.find_one({"id": referral_data.job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") != "active":
        raise HTTPException(status_code=400, detail="Can only refer candidates to active jobs")
    
    # Check for duplicate referral (same email + job)
    existing = await db.referrals.find_one({
        "job_id": referral_data.job_id,
        "candidate_email": referral_data.candidate_email.lower()
    })
    if existing:
        raise HTTPException(status_code=400, detail="This candidate has already been referred for this job")
    
    referral_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    referral_doc = {
        "id": referral_id,
        "job_id": referral_data.job_id,
        "job_title": job.get("title"),
        "referrer_id": current_user["id"],
        "referrer_name": current_user["name"],
        "candidate_name": referral_data.candidate_name,
        "candidate_email": referral_data.candidate_email.lower(),
        "candidate_phone": referral_data.candidate_phone,
        "resume_url": referral_data.resume_url,
        "note": referral_data.note,
        "status": "submitted",
        "linked_candidate_id": None,
        "linked_application_id": None,
        "status_history": [{
            "status": "submitted",
            "changed_by": current_user["id"],
            "changed_by_name": current_user["name"],
            "changed_by_role": current_user["role"],
            "timestamp": now,
            "reason": "Referral submitted"
        }],
        "created_at": now,
        "updated_at": now
    }
    
    await db.referrals.insert_one(referral_doc)
    
    logging.info(f"Referral {referral_id} created by {current_user['name']} for job {referral_data.job_id}")
    
    return ReferralResponse(**referral_doc)


@api_router.get("/referrals", response_model=List[ReferralResponse])
async def get_referrals(
    job_id: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Get referrals based on user role.
    - Admin: sees all referrals
    - Employer: sees referrals for their team's jobs
    - Recruiter: sees their own referrals
    """
    query = {}
    
    if current_user["role"] == "recruiter":
        query["referrer_id"] = current_user["id"]
    elif current_user["role"] == "employer":
        # Get jobs from employer's team
        team = await db.teams.find_one({"employer_id": current_user["id"]}, {"_id": 0})
        if team:
            team_jobs = await db.jobs.find({"team_id": team["id"]}, {"id": 1, "_id": 0}).to_list(1000)
            job_ids = [j["id"] for j in team_jobs]
            query["job_id"] = {"$in": job_ids}
        else:
            # No team, return empty
            return []
    
    if job_id:
        query["job_id"] = job_id
    if status:
        query["status"] = status
    
    referrals = await db.referrals.find(query, {"_id": 0}).to_list(1000)
    return [ReferralResponse(**r) for r in referrals]


@api_router.get("/referrals/{referral_id}", response_model=ReferralResponse)
async def get_referral(referral_id: str, current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))):
    """Get a specific referral by ID."""
    referral = await db.referrals.find_one({"id": referral_id}, {"_id": 0})
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found")
    
    # Access control for non-admin users
    if current_user["role"] == "recruiter":
        if referral["referrer_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    elif current_user["role"] == "employer":
        # Check if job belongs to employer's team
        job = await db.jobs.find_one({"id": referral["job_id"]}, {"_id": 0})
        if job:
            team = await db.teams.find_one({"employer_id": current_user["id"]}, {"_id": 0})
            if not team or job.get("team_id") != team["id"]:
                raise HTTPException(status_code=403, detail="Access denied")
        else:
            raise HTTPException(status_code=403, detail="Access denied")
    
    return ReferralResponse(**referral)


@api_router.post("/referrals/{referral_id}/transition", response_model=ReferralResponse)
async def transition_referral_status(
    referral_id: str,
    transition: ReferralStatusUpdate,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Transition referral status with audit logging.
    
    Valid transitions:
    - submitted -> validated, closed
    - validated -> linked, closed
    - linked -> in_process, closed
    - in_process -> outcome_reached, closed
    - outcome_reached -> closed
    - closed -> (no transitions, final state)
    """
    referral = await db.referrals.find_one({"id": referral_id}, {"_id": 0})
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found")
    
    current_status = referral.get("status", "submitted")
    new_status = transition.new_status
    
    # Define valid transitions
    valid_transitions = {
        "submitted": ["validated", "closed"],
        "validated": ["linked", "closed"],
        "linked": ["in_process", "closed"],
        "in_process": ["outcome_reached", "closed"],
        "outcome_reached": ["closed"],
        "closed": []  # Final state
    }
    
    if new_status not in valid_transitions.get(current_status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition from {current_status} to {new_status}"
        )
    
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
    
    await db.referrals.update_one(
        {"id": referral_id},
        {
            "$set": {"status": new_status, "updated_at": now},
            "$push": {"status_history": audit_entry}
        }
    )
    
    logging.info(f"Referral {referral_id} transitioned from {current_status} to {new_status} by {current_user['name']}")
    
    updated_referral = await db.referrals.find_one({"id": referral_id}, {"_id": 0})
    return ReferralResponse(**updated_referral)


@api_router.post("/referrals/{referral_id}/link-candidate")
async def link_referral_to_candidate(
    referral_id: str,
    candidate_id: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Link a referral to an existing candidate bank record, or create a new candidate.
    
    If candidate_id is provided: links to existing candidate
    If not provided: creates new candidate from referral data
    """
    referral = await db.referrals.find_one({"id": referral_id}, {"_id": 0})
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found")
    
    if referral.get("status") not in ["submitted", "validated"]:
        raise HTTPException(status_code=400, detail="Can only link referrals in submitted or validated status")
    
    now = datetime.now(timezone.utc).isoformat()
    
    if candidate_id:
        # Link to existing candidate
        candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
    else:
        # Create new candidate from referral data
        candidate_id = str(uuid.uuid4())
        candidate_doc = {
            "id": candidate_id,
            "email": referral["candidate_email"],
            "name": referral["candidate_name"],
            "phone": referral.get("candidate_phone"),
            "phone_normalized": referral.get("candidate_phone"),
            "skills": [],
            "experience_years": 0,
            "experience": [],
            "education": [],
            "resume_url": referral.get("resume_url"),
            "source": "referral",
            "source_referral_id": referral_id,
            "visibility": {
                f"{current_user['role']}_ids": [current_user["id"]]
            },
            "created_at": now,
            "updated_at": now,
            "created_by": current_user["id"]
        }
        await db.candidate_bank.insert_one(candidate_doc)
    
    # Update referral with link
    await db.referrals.update_one(
        {"id": referral_id},
        {
            "$set": {
                "status": "linked",
                "linked_candidate_id": candidate_id,
                "updated_at": now
            },
            "$push": {"status_history": {
                "from_status": referral["status"],
                "to_status": "linked",
                "changed_by": current_user["id"],
                "changed_by_name": current_user["name"],
                "changed_by_role": current_user["role"],
                "timestamp": now,
                "reason": f"Linked to candidate {candidate_id}"
            }}
        }
    )
    
    return {
        "message": "Referral linked to candidate successfully",
        "referral_id": referral_id,
        "candidate_id": candidate_id
    }


# ============== PHASE-A: COMPANY-EMPLOYER ASSIGNMENT ==============

@api_router.put("/companies/{company_id}/assign-employer")
async def assign_employer_to_company(
    company_id: str,
    employer_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Assign an employer to manage a company (Admin only).
    """
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    employer = await db.users.find_one({"id": employer_id, "role": "employer"}, {"_id": 0})
    if not employer:
        raise HTTPException(status_code=404, detail="Employer not found")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.companies.update_one(
        {"id": company_id},
        {"$set": {
            "assigned_employer_id": employer_id,
            "assigned_employer_name": employer.get("name"),
            "updated_at": now
        }}
    )
    
    return {
        "message": "Employer assigned to company successfully",
        "company_id": company_id,
        "employer_id": employer_id,
        "employer_name": employer.get("name")
    }


@api_router.put("/companies/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: str,
    update_data: CompanyUpdate,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Update company details.
    - Admin: can update any company
    - Employer: can only update companies assigned to them
    """
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Access control for employers
    if current_user["role"] == "employer":
        if company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="You are not assigned to this company")
    
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.companies.update_one({"id": company_id}, {"$set": update_dict})
    
    updated_company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    return CompanyResponse(**updated_company)


# ============== PHASE-A: ADMIN HIERARCHY OVERVIEW ==============

@api_router.get("/admin/hierarchy")
async def get_admin_hierarchy(current_user: dict = Depends(require_role(["admin"]))):
    """
    Get complete hierarchy overview for Admin.
    Shows: Employers -> Teams -> Recruiters -> Companies
    """
    # Get all employers
    employers = await db.users.find({"role": "employer", "is_active": True}, {"_id": 0, "password": 0}).to_list(1000)
    
    hierarchy = []
    
    for employer in employers:
        employer_data = {
            "employer_id": employer["id"],
            "employer_name": employer["name"],
            "employer_email": employer["email"],
            "teams": []
        }
        
        # Get teams for this employer
        teams = await db.teams.find({"employer_id": employer["id"], "status": "active"}, {"_id": 0}).to_list(100)
        
        for team in teams:
            # Get active jobs count
            jobs_count = await db.jobs.count_documents({
                "team_id": team["id"],
                "status": {"$in": ["active", "pending_approval"]}
            })
            
            team_data = {
                "team_id": team["id"],
                "team_name": team["name"],
                "active_jobs_count": jobs_count,
                "recruiters": [],
                "companies": []
            }
            
            # Get recruiters in this team
            for recruiter_id in team.get("recruiter_ids", []):
                recruiter = await db.users.find_one({"id": recruiter_id}, {"_id": 0, "password": 0})
                if recruiter:
                    team_data["recruiters"].append({
                        "id": recruiter["id"],
                        "name": recruiter["name"],
                        "email": recruiter["email"]
                    })
            
            # Get companies in this team
            for company_id in team.get("company_ids", []):
                company = await db.companies.find_one({"id": company_id}, {"_id": 0})
                if company:
                    team_data["companies"].append({
                        "id": company["id"],
                        "name": company["name"],
                        "industry": company.get("industry")
                    })
            
            employer_data["teams"].append(team_data)
        
        hierarchy.append(employer_data)
    
    # Get unassigned recruiters
    unassigned_recruiters = await db.users.find(
        {"role": "recruiter", "is_active": True, "team_id": {"$exists": False}},
        {"_id": 0, "password": 0}
    ).to_list(1000)
    
    # Get unassigned companies
    unassigned_companies = await db.companies.find(
        {"assigned_employer_id": {"$exists": False}},
        {"_id": 0}
    ).to_list(1000)
    
    return {
        "hierarchy": hierarchy,
        "unassigned_recruiters": [{"id": r["id"], "name": r["name"], "email": r["email"]} for r in unassigned_recruiters],
        "unassigned_companies": [{"id": c["id"], "name": c["name"]} for c in unassigned_companies],
        "summary": {
            "total_employers": len(employers),
            "total_teams": sum(len(e["teams"]) for e in hierarchy),
            "total_unassigned_recruiters": len(unassigned_recruiters),
            "total_unassigned_companies": len(unassigned_companies)
        }
    }


# ============== COMMERCIAL INTELLIGENCE ENGINE ==============

@api_router.post("/commercials", response_model=CommercialResponse)
async def create_commercial(
    commercial_data: CommercialCreate,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Create a commercial configuration for a company.
    - Admin: can create for any company
    - Employer: can only create for assigned companies
    """
    # Validate company exists
    company = await db.companies.find_one({"id": commercial_data.company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Employer can only manage assigned companies
    if current_user["role"] == "employer":
        if company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="You are not assigned to this company")
    
    # Validate commercial type fields
    if commercial_data.type == "percentage" and commercial_data.fee_percentage is None:
        raise HTTPException(status_code=400, detail="fee_percentage required for percentage type")
    if commercial_data.type == "fixed" and commercial_data.fixed_amount is None:
        raise HTTPException(status_code=400, detail="fixed_amount required for fixed type")
    if commercial_data.type == "level_based" and commercial_data.level_config is None:
        raise HTTPException(status_code=400, detail="level_config required for level_based type")
    
    commercial_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    commercial_doc = {
        "id": commercial_id,
        "company_id": commercial_data.company_id,
        "company_name": company.get("name"),
        "commercial_name": commercial_data.commercial_name,
        "type": commercial_data.type,
        "fee_percentage": commercial_data.fee_percentage,
        "fixed_amount": commercial_data.fixed_amount,
        "level_config": commercial_data.level_config,
        "salary_min": commercial_data.salary_min,
        "salary_max": commercial_data.salary_max,
        "job_level": commercial_data.job_level,
        "effective_from": commercial_data.effective_from,
        "effective_to": commercial_data.effective_to,
        "is_active": commercial_data.is_active,
        "created_at": now,
        "created_by": current_user["id"],
        "created_by_name": current_user["name"],
        "updated_at": now,
        "audit_log": [{
            "action": "created",
            "by_id": current_user["id"],
            "by_name": current_user["name"],
            "by_role": current_user["role"],
            "timestamp": now
        }]
    }
    
    await db.commercials.insert_one(commercial_doc)
    logging.info(f"Commercial '{commercial_data.commercial_name}' created for company {company.get('name')} by {current_user['name']}")
    
    return CommercialResponse(**commercial_doc)


@api_router.get("/commercials", response_model=List[CommercialResponse])
async def get_commercials(
    company_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Get commercials.
    - Admin: sees all commercials
    - Employer: sees only commercials for assigned companies
    """
    query = {}
    
    if current_user["role"] == "employer":
        # Get companies assigned to this employer
        assigned_companies = await db.companies.find(
            {"assigned_employer_id": current_user["id"]},
            {"id": 1, "_id": 0}
        ).to_list(1000)
        company_ids = [c["id"] for c in assigned_companies]
        query["company_id"] = {"$in": company_ids}
    
    if company_id:
        query["company_id"] = company_id
    if is_active is not None:
        query["is_active"] = is_active
    
    commercials = await db.commercials.find(query, {"_id": 0}).to_list(1000)
    return [CommercialResponse(**c) for c in commercials]


@api_router.get("/commercials/{commercial_id}", response_model=CommercialResponse)
async def get_commercial(
    commercial_id: str,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Get a specific commercial by ID."""
    commercial = await db.commercials.find_one({"id": commercial_id}, {"_id": 0})
    if not commercial:
        raise HTTPException(status_code=404, detail="Commercial not found")
    
    # Employer access control
    if current_user["role"] == "employer":
        company = await db.companies.find_one({"id": commercial["company_id"]}, {"_id": 0})
        if not company or company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    return CommercialResponse(**commercial)


@api_router.put("/commercials/{commercial_id}", response_model=CommercialResponse)
async def update_commercial(
    commercial_id: str,
    update_data: CommercialUpdate,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """Update a commercial configuration."""
    commercial = await db.commercials.find_one({"id": commercial_id}, {"_id": 0})
    if not commercial:
        raise HTTPException(status_code=404, detail="Commercial not found")
    
    # Employer access control
    if current_user["role"] == "employer":
        company = await db.companies.find_one({"id": commercial["company_id"]}, {"_id": 0})
        if not company or company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    now = datetime.now(timezone.utc).isoformat()
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    update_dict["updated_at"] = now
    
    # Create audit entry
    audit_entry = {
        "action": "updated",
        "changes": list(update_dict.keys()),
        "by_id": current_user["id"],
        "by_name": current_user["name"],
        "by_role": current_user["role"],
        "timestamp": now
    }
    
    await db.commercials.update_one(
        {"id": commercial_id},
        {
            "$set": update_dict,
            "$push": {"audit_log": audit_entry}
        }
    )
    
    updated = await db.commercials.find_one({"id": commercial_id}, {"_id": 0})
    return CommercialResponse(**updated)


@api_router.delete("/commercials/{commercial_id}")
async def delete_commercial(
    commercial_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Soft delete (deactivate) a commercial. Admin only."""
    commercial = await db.commercials.find_one({"id": commercial_id}, {"_id": 0})
    if not commercial:
        raise HTTPException(status_code=404, detail="Commercial not found")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.commercials.update_one(
        {"id": commercial_id},
        {
            "$set": {"is_active": False, "updated_at": now},
            "$push": {"audit_log": {
                "action": "deactivated",
                "by_id": current_user["id"],
                "by_name": current_user["name"],
                "by_role": current_user["role"],
                "timestamp": now
            }}
        }
    )
    
    return {"message": "Commercial deactivated successfully"}


# ============== REVENUE CALCULATION ENGINE ==============

def calculate_revenue(offered_salary: float, commercial: dict, job_level: Optional[str] = None) -> float:
    """Calculate revenue based on commercial type."""
    if commercial["type"] == "percentage":
        return offered_salary * (commercial["fee_percentage"] / 100)
    elif commercial["type"] == "fixed":
        return commercial["fixed_amount"]
    elif commercial["type"] == "level_based":
        level_config = commercial.get("level_config", {})
        level = job_level or "mid"  # Default to mid if not specified
        fee_pct = level_config.get(level, level_config.get("mid", 10.0))
        return offered_salary * (fee_pct / 100)
    return 0.0


async def get_applicable_commercial(company_id: str, salary: Optional[float] = None, job_level: Optional[str] = None) -> Optional[dict]:
    """Get the applicable commercial for a job/offer."""
    now = datetime.now(timezone.utc).isoformat()
    
    query = {
        "company_id": company_id,
        "is_active": True,
        "effective_from": {"$lte": now},
        "$or": [
            {"effective_to": None},
            {"effective_to": {"$gte": now}}
        ]
    }
    
    commercials = await db.commercials.find(query, {"_id": 0}).to_list(100)
    
    if not commercials:
        return None
    
    # If salary provided, try to find salary-range specific commercial
    if salary:
        for comm in commercials:
            if comm.get("salary_min") and comm.get("salary_max"):
                if comm["salary_min"] <= salary <= comm["salary_max"]:
                    return comm
    
    # If job level provided, try to find level-specific commercial
    if job_level:
        for comm in commercials:
            if comm.get("job_level") == job_level:
                return comm
            if comm["type"] == "level_based":
                return comm
    
    # Return first active commercial as default
    return commercials[0]


@api_router.post("/revenue/calculate")
async def calculate_application_revenue(
    application_id: str,
    offered_salary: float,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Calculate revenue for an application when offer is made.
    Creates/updates revenue entry in database.
    """
    application = await db.applications.find_one({"id": application_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Get job to find company
    job = await db.jobs.find_one({"id": application["job_id"]}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    company_id = job.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="Job has no company assigned")
    
    # Employer access control
    if current_user["role"] == "employer":
        company = await db.companies.find_one({"id": company_id}, {"_id": 0})
        if not company or company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Get applicable commercial
    commercial = await get_applicable_commercial(
        company_id,
        salary=offered_salary,
        job_level=job.get("job_level")
    )
    
    if not commercial:
        raise HTTPException(status_code=400, detail="No active commercial found for this company")
    
    # Calculate revenue
    calculated_revenue = calculate_revenue(
        offered_salary,
        commercial,
        job.get("job_level")
    )
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Check if revenue entry exists
    existing = await db.revenue.find_one({"application_id": application_id}, {"_id": 0})
    
    if existing:
        # Update existing
        await db.revenue.update_one(
            {"application_id": application_id},
            {
                "$set": {
                    "offered_salary": offered_salary,
                    "commercial_id": commercial["id"],
                    "commercial_type": commercial["type"],
                    "fee_percentage": commercial.get("fee_percentage"),
                    "fixed_amount": commercial.get("fixed_amount"),
                    "calculated_revenue": calculated_revenue,
                    "final_revenue": existing.get("manual_override") or calculated_revenue,
                    "stage": application.get("stage", "offered"),
                    "updated_at": now
                },
                "$push": {"audit_log": {
                    "action": "recalculated",
                    "offered_salary": offered_salary,
                    "calculated_revenue": calculated_revenue,
                    "by_id": current_user["id"],
                    "by_name": current_user["name"],
                    "timestamp": now
                }}
            }
        )
        revenue_id = existing["id"]
    else:
        # Create new
        revenue_id = str(uuid.uuid4())
        revenue_doc = {
            "id": revenue_id,
            "application_id": application_id,
            "job_id": application["job_id"],
            "job_title": job.get("title"),
            "candidate_id": application.get("candidate_id"),
            "candidate_name": application.get("candidate_name"),
            "company_id": company_id,
            "offered_salary": offered_salary,
            "commercial_id": commercial["id"],
            "commercial_name": commercial.get("commercial_name"),
            "commercial_type": commercial["type"],
            "fee_percentage": commercial.get("fee_percentage"),
            "fixed_amount": commercial.get("fixed_amount"),
            "calculated_revenue": calculated_revenue,
            "manual_override": None,
            "final_revenue": calculated_revenue,
            "stage": application.get("stage", "offered"),
            "is_closed": application.get("stage") == "hired",
            "created_at": now,
            "created_by": current_user["id"],
            "audit_log": [{
                "action": "created",
                "offered_salary": offered_salary,
                "calculated_revenue": calculated_revenue,
                "by_id": current_user["id"],
                "by_name": current_user["name"],
                "timestamp": now
            }]
        }
        await db.revenue.insert_one(revenue_doc)
    
    # Update application with offered salary
    await db.applications.update_one(
        {"id": application_id},
        {"$set": {"offered_salary": offered_salary, "updated_at": now}}
    )
    
    return {
        "revenue_id": revenue_id,
        "application_id": application_id,
        "offered_salary": offered_salary,
        "commercial_name": commercial.get("commercial_name"),
        "commercial_type": commercial["type"],
        "fee_percentage": commercial.get("fee_percentage"),
        "calculated_revenue": calculated_revenue,
        "final_revenue": calculated_revenue
    }


@api_router.put("/revenue/{revenue_id}/override")
async def override_revenue(
    revenue_id: str,
    manual_override: float,
    reason: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Admin-only: Manually override calculated revenue.
    """
    revenue = await db.revenue.find_one({"id": revenue_id}, {"_id": 0})
    if not revenue:
        raise HTTPException(status_code=404, detail="Revenue entry not found")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.revenue.update_one(
        {"id": revenue_id},
        {
            "$set": {
                "manual_override": manual_override,
                "final_revenue": manual_override,
                "updated_at": now
            },
            "$push": {"audit_log": {
                "action": "manual_override",
                "previous_revenue": revenue.get("final_revenue"),
                "new_revenue": manual_override,
                "reason": reason,
                "by_id": current_user["id"],
                "by_name": current_user["name"],
                "timestamp": now
            }}
        }
    )
    
    logging.info(f"Revenue {revenue_id} manually overridden to {manual_override} by {current_user['name']}: {reason}")
    
    return {"message": "Revenue overridden successfully", "final_revenue": manual_override}


@api_router.get("/revenue/pipeline")
async def get_revenue_pipeline(
    company_id: Optional[str] = None,
    employer_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Get revenue pipeline data.
    - Admin: sees all
    - Employer: sees only assigned companies
    """
    query = {}
    
    if current_user["role"] == "employer":
        # Get companies assigned to this employer
        assigned_companies = await db.companies.find(
            {"assigned_employer_id": current_user["id"]},
            {"id": 1, "_id": 0}
        ).to_list(1000)
        company_ids = [c["id"] for c in assigned_companies]
        query["company_id"] = {"$in": company_ids}
    elif company_id:
        query["company_id"] = company_id
    
    if date_from:
        query["created_at"] = {"$gte": date_from}
    if date_to:
        if "created_at" in query:
            query["created_at"]["$lte"] = date_to
        else:
            query["created_at"] = {"$lte": date_to}
    
    revenues = await db.revenue.find(query, {"_id": 0}).to_list(10000)
    
    # Calculate pipeline stats
    pipeline_by_stage = {}
    closed_revenue = 0
    total_pipeline = 0
    
    for rev in revenues:
        stage = rev.get("stage", "offered")
        amount = rev.get("final_revenue", 0)
        
        if stage not in pipeline_by_stage:
            pipeline_by_stage[stage] = {"count": 0, "revenue": 0}
        
        pipeline_by_stage[stage]["count"] += 1
        pipeline_by_stage[stage]["revenue"] += amount
        
        if rev.get("is_closed"):
            closed_revenue += amount
        else:
            total_pipeline += amount
    
    return {
        "pipeline_by_stage": pipeline_by_stage,
        "total_pipeline_revenue": total_pipeline,
        "closed_revenue": closed_revenue,
        "total_entries": len(revenues),
        "entries": revenues[:100]  # Limit detail response
    }


# ============== ADMIN ANALYTICS DASHBOARD ==============

@api_router.get("/analytics/admin")
async def get_admin_analytics(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    employer_id: Optional[str] = None,
    recruiter_id: Optional[str] = None,
    company_id: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin"]))
):
    """
    Admin analytics dashboard - Power BI style.
    Full visibility into all business metrics.
    """
    # Build date query
    date_query = {}
    if date_from:
        date_query["$gte"] = date_from
    if date_to:
        date_query["$lte"] = date_to
    
    # Get all jobs with filters
    jobs_query = {"status": {"$in": ["active", "on_hold", "closed"]}}
    if company_id:
        jobs_query["company_id"] = company_id
    
    jobs = await db.jobs.find(jobs_query, {"_id": 0}).to_list(10000)
    active_jobs = [j for j in jobs if j.get("status") == "active"]
    
    # Get all applications
    apps_query = {}
    if date_query:
        apps_query["created_at"] = date_query
    
    applications = await db.applications.find(apps_query, {"_id": 0}).to_list(100000)
    
    # Get revenue data
    revenue_query = {}
    if date_query:
        revenue_query["created_at"] = date_query
    if company_id:
        revenue_query["company_id"] = company_id
    
    revenues = await db.revenue.find(revenue_query, {"_id": 0}).to_list(10000)
    
    # Calculate KPIs
    total_pipeline_revenue = sum(r.get("final_revenue", 0) for r in revenues if not r.get("is_closed"))
    closed_revenue = sum(r.get("final_revenue", 0) for r in revenues if r.get("is_closed"))
    
    # Stage distribution
    stage_counts = {}
    for app in applications:
        stage = app.get("stage", "applied")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
    
    offered_count = stage_counts.get("offered", 0)
    hired_count = stage_counts.get("hired", 0)
    offer_to_join_ratio = (hired_count / offered_count * 100) if offered_count > 0 else 0
    
    # Calculate avg time to close
    hired_apps = [a for a in applications if a.get("stage") == "hired" and a.get("created_at")]
    if hired_apps:
        total_days = 0
        for app in hired_apps:
            try:
                created = datetime.fromisoformat(app["created_at"].replace("Z", "+00:00"))
                updated = datetime.fromisoformat(app.get("updated_at", app["created_at"]).replace("Z", "+00:00"))
                total_days += (updated - created).days
            except:
                pass
        avg_time_to_close = total_days / len(hired_apps) if hired_apps else 0
    else:
        avg_time_to_close = 0
    
    # Get counts
    active_employers = await db.users.count_documents({"role": "employer", "is_active": True})
    active_recruiters = await db.users.count_documents({"role": "recruiter", "is_active": True})
    
    # Revenue by company
    company_revenue = {}
    for rev in revenues:
        cid = rev.get("company_id")
        if cid:
            if cid not in company_revenue:
                company_revenue[cid] = {"name": "", "pipeline": 0, "closed": 0}
            company_revenue[cid]["pipeline"] += rev.get("final_revenue", 0) if not rev.get("is_closed") else 0
            company_revenue[cid]["closed"] += rev.get("final_revenue", 0) if rev.get("is_closed") else 0
    
    # Get company names
    for cid in company_revenue:
        company = await db.companies.find_one({"id": cid}, {"name": 1, "_id": 0})
        if company:
            company_revenue[cid]["name"] = company.get("name", "Unknown")
    
    # Recruiter performance
    recruiter_stats = {}
    for app in applications:
        # Get the recruiter who processed this application
        job = next((j for j in jobs if j["id"] == app.get("job_id")), None)
        if job:
            for rec_id in job.get("assigned_recruiter_ids", []):
                if rec_id not in recruiter_stats:
                    recruiter_stats[rec_id] = {"name": "", "applications": 0, "shortlisted": 0, "hired": 0, "revenue": 0}
                recruiter_stats[rec_id]["applications"] += 1
                if app.get("stage") in ["shortlisted", "interview", "offered", "hired"]:
                    recruiter_stats[rec_id]["shortlisted"] += 1
                if app.get("stage") == "hired":
                    recruiter_stats[rec_id]["hired"] += 1
    
    # Get recruiter names and add revenue
    for rec_id in recruiter_stats:
        user = await db.users.find_one({"id": rec_id}, {"name": 1, "_id": 0})
        if user:
            recruiter_stats[rec_id]["name"] = user.get("name", "Unknown")
        # Sum revenue for this recruiter's applications
        for rev in revenues:
            app = next((a for a in applications if a["id"] == rev.get("application_id")), None)
            if app:
                job = next((j for j in jobs if j["id"] == app.get("job_id")), None)
                if job and rec_id in job.get("assigned_recruiter_ids", []):
                    recruiter_stats[rec_id]["revenue"] += rev.get("final_revenue", 0)
    
    # Revenue funnel by stage
    revenue_funnel = {
        "offered": sum(r.get("final_revenue", 0) for r in revenues if r.get("stage") == "offered"),
        "hired": sum(r.get("final_revenue", 0) for r in revenues if r.get("stage") == "hired"),
    }
    
    return {
        "kpis": {
            "total_active_mandates": len(active_jobs),
            "total_pipeline_revenue": round(total_pipeline_revenue, 2),
            "closed_revenue": round(closed_revenue, 2),
            "avg_time_to_close_days": round(avg_time_to_close, 1),
            "offer_to_join_ratio": round(offer_to_join_ratio, 1),
            "active_employers": active_employers,
            "active_recruiters": active_recruiters,
        },
        "stage_distribution": stage_counts,
        "revenue_funnel": revenue_funnel,
        "company_revenue": list(company_revenue.values()),
        "recruiter_performance": list(recruiter_stats.values()),
    }


# ============== EMPLOYER ANALYTICS DASHBOARD ==============

@api_router.get("/analytics/employer")
async def get_employer_analytics(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Employer analytics dashboard.
    Scoped to assigned companies and teams only.
    """
    # Get companies assigned to this employer (or all for admin)
    if current_user["role"] == "employer":
        assigned_companies = await db.companies.find(
            {"assigned_employer_id": current_user["id"]},
            {"_id": 0}
        ).to_list(1000)
        company_ids = [c["id"] for c in assigned_companies]
    else:
        assigned_companies = await db.companies.find({}, {"_id": 0}).to_list(1000)
        company_ids = [c["id"] for c in assigned_companies]
    
    if not company_ids:
        return {
            "kpis": {
                "active_mandates": 0,
                "pipeline_revenue": 0,
                "closed_revenue": 0,
                "offers_pending": 0,
                "avg_fee_percentage": 0,
            },
            "team_performance": [],
            "company_revenue": [],
            "recruiter_contribution": [],
        }
    
    # Get jobs for these companies
    jobs = await db.jobs.find(
        {"company_id": {"$in": company_ids}},
        {"_id": 0}
    ).to_list(10000)
    
    active_jobs = [j for j in jobs if j.get("status") == "active"]
    job_ids = [j["id"] for j in jobs]
    
    # Get applications for these jobs
    applications = await db.applications.find(
        {"job_id": {"$in": job_ids}},
        {"_id": 0}
    ).to_list(100000)
    
    # Get revenue
    revenues = await db.revenue.find(
        {"company_id": {"$in": company_ids}},
        {"_id": 0}
    ).to_list(10000)
    
    pipeline_revenue = sum(r.get("final_revenue", 0) for r in revenues if not r.get("is_closed"))
    closed_revenue = sum(r.get("final_revenue", 0) for r in revenues if r.get("is_closed"))
    
    # Offers pending
    offers_pending = len([a for a in applications if a.get("stage") == "offered"])
    
    # Average fee percentage
    commercials = await db.commercials.find(
        {"company_id": {"$in": company_ids}, "is_active": True},
        {"_id": 0}
    ).to_list(1000)
    
    pct_fees = [c.get("fee_percentage", 0) for c in commercials if c.get("fee_percentage")]
    avg_fee = sum(pct_fees) / len(pct_fees) if pct_fees else 0
    
    # Company-wise revenue
    company_revenue = []
    for company in assigned_companies:
        comp_revs = [r for r in revenues if r.get("company_id") == company["id"]]
        company_revenue.append({
            "company_id": company["id"],
            "company_name": company.get("name"),
            "pipeline": sum(r.get("final_revenue", 0) for r in comp_revs if not r.get("is_closed")),
            "closed": sum(r.get("final_revenue", 0) for r in comp_revs if r.get("is_closed")),
            "mandates": len([j for j in jobs if j.get("company_id") == company["id"]]),
        })
    
    # Get teams for this employer
    teams = await db.teams.find(
        {"employer_id": current_user["id"]} if current_user["role"] == "employer" else {},
        {"_id": 0}
    ).to_list(100)
    
    team_performance = []
    for team in teams:
        team_jobs = [j for j in jobs if j.get("team_id") == team["id"]]
        team_job_ids = [j["id"] for j in team_jobs]
        team_apps = [a for a in applications if a.get("job_id") in team_job_ids]
        team_revs = [r for r in revenues if r.get("job_id") in team_job_ids]
        
        team_performance.append({
            "team_id": team["id"],
            "team_name": team.get("name"),
            "mandates": len(team_jobs),
            "applications": len(team_apps),
            "hired": len([a for a in team_apps if a.get("stage") == "hired"]),
            "pipeline_revenue": sum(r.get("final_revenue", 0) for r in team_revs if not r.get("is_closed")),
            "closed_revenue": sum(r.get("final_revenue", 0) for r in team_revs if r.get("is_closed")),
        })
    
    # Recruiter contribution
    recruiter_contribution = []
    recruiter_ids = set()
    for job in jobs:
        for rec_id in job.get("assigned_recruiter_ids", []):
            recruiter_ids.add(rec_id)
    
    for rec_id in recruiter_ids:
        rec_jobs = [j for j in jobs if rec_id in j.get("assigned_recruiter_ids", [])]
        rec_job_ids = [j["id"] for j in rec_jobs]
        rec_apps = [a for a in applications if a.get("job_id") in rec_job_ids]
        rec_revs = [r for r in revenues if r.get("job_id") in rec_job_ids]
        
        recruiter = await db.users.find_one({"id": rec_id}, {"name": 1, "_id": 0})
        
        recruiter_contribution.append({
            "recruiter_id": rec_id,
            "recruiter_name": recruiter.get("name", "Unknown") if recruiter else "Unknown",
            "mandates": len(rec_jobs),
            "applications": len(rec_apps),
            "hired": len([a for a in rec_apps if a.get("stage") == "hired"]),
            "revenue": sum(r.get("final_revenue", 0) for r in rec_revs),
        })
    
    return {
        "kpis": {
            "active_mandates": len(active_jobs),
            "pipeline_revenue": round(pipeline_revenue, 2),
            "closed_revenue": round(closed_revenue, 2),
            "offers_pending": offers_pending,
            "avg_fee_percentage": round(avg_fee, 2),
        },
        "team_performance": team_performance,
        "company_revenue": company_revenue,
        "recruiter_contribution": recruiter_contribution,
    }


# ============== COMPANY PIPELINE VIEW ==============

@api_router.get("/companies/{company_id}/pipeline")
async def get_company_pipeline(
    company_id: str,
    current_user: dict = Depends(require_role(["admin", "employer"]))
):
    """
    Get company profile with pipeline view.
    Shows mandates, revenue breakdown, and detailed pipeline.
    """
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Employer access control
    if current_user["role"] == "employer":
        if company.get("assigned_employer_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all jobs for this company
    jobs = await db.jobs.find({"company_id": company_id}, {"_id": 0}).to_list(10000)
    
    total_mandates = len(jobs)
    active_mandates = len([j for j in jobs if j.get("status") == "active"])
    closed_mandates = len([j for j in jobs if j.get("status") == "closed"])
    
    # Get revenue
    revenues = await db.revenue.find({"company_id": company_id}, {"_id": 0}).to_list(10000)
    total_revenue = sum(r.get("final_revenue", 0) for r in revenues)
    
    # Get commercials
    commercials = await db.commercials.find(
        {"company_id": company_id, "is_active": True},
        {"_id": 0}
    ).to_list(100)
    
    pct_fees = [c.get("fee_percentage", 0) for c in commercials if c.get("fee_percentage")]
    avg_commercial_pct = sum(pct_fees) / len(pct_fees) if pct_fees else 0
    
    # Build pipeline table
    pipeline = []
    for job in jobs:
        job_revenues = [r for r in revenues if r.get("job_id") == job["id"]]
        expected_revenue = sum(r.get("final_revenue", 0) for r in job_revenues if not r.get("is_closed"))
        closed_revenue = sum(r.get("final_revenue", 0) for r in job_revenues if r.get("is_closed"))
        
        # Get recruiters for this job
        recruiters = []
        for rec_id in job.get("assigned_recruiter_ids", []):
            rec = await db.users.find_one({"id": rec_id}, {"name": 1, "_id": 0})
            if rec:
                recruiters.append(rec.get("name", "Unknown"))
        
        # Get application count by stage
        apps = await db.applications.find({"job_id": job["id"]}, {"stage": 1, "_id": 0}).to_list(10000)
        stage_counts = {}
        for app in apps:
            stage = app.get("stage", "applied")
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
        
        pipeline.append({
            "job_id": job["id"],
            "job_title": job.get("title"),
            "job_level": job.get("job_level"),
            "status": job.get("status"),
            "recruiters": recruiters,
            "stage_counts": stage_counts,
            "expected_revenue": round(expected_revenue, 2),
            "closed_revenue": round(closed_revenue, 2),
        })
    
    return {
        "company": {
            "id": company["id"],
            "name": company.get("name"),
            "industry": company.get("industry"),
        },
        "summary": {
            "total_mandates": total_mandates,
            "active_mandates": active_mandates,
            "closed_mandates": closed_mandates,
            "total_revenue": round(total_revenue, 2),
            "avg_commercial_percentage": round(avg_commercial_pct, 2),
        },
        "commercials": [CommercialResponse(**c).model_dump() for c in commercials],
        "pipeline": pipeline,
    }


# Note: JD PARSING routes have been extracted to routes/jobs.py
# Endpoints: /api/jobs/extract-jd-text, /api/jobs/parse-jd

# Note: MANDATE ASSIGNMENT routes have been extracted to routes/jobs.py
# Endpoints: /api/employer/team-recruiters, /api/jobs/{job_id}/assign-recruiters, etc.

# Note: FILE SERVING routes have been extracted to routes/files.py
# Endpoints: /api/uploads/{filename}

# ============== SEED ADMIN ==============

@app.on_event("startup")
async def validate_mongodb_connection():
    """
    Validates MongoDB connectivity on application startup.
    CRITICAL: Application must fail loudly if database is not accessible.
    """
    try:
        # Ping MongoDB to verify connectivity
        await client.admin.command("ping")
        logging.info("MongoDB Atlas connected successfully")
        logging.info(f"Database: {db_name}")
    except Exception as e:
        logging.error(f"MongoDB connection failed: {str(e)}")
        logging.error("Application cannot start without database connection. Please check MONGODB_URI.")
        raise RuntimeError(f"MongoDB connection failed: {str(e)}")

@app.on_event("startup")
async def validate_r2_connection():
    """
    Validates Cloudflare R2 connectivity on application startup.
    Non-blocking: Falls back to local storage if R2 is not available.
    """
    if R2_ENABLED:
        try:
            # List buckets to verify connectivity
            r2_client.list_buckets()
            logging.info("Cloudflare R2 successfully connected and operational")
            logging.info(f"R2 Bucket: {R2_BUCKET_NAME}")
        except Exception as e:
            logging.warning(f"Cloudflare R2 connectivity check failed: {e}")
            logging.warning("R2 may still work - some operations may succeed despite list_buckets failure")
    else:
        logging.info("Cloudflare R2 not configured - using local storage")

@app.on_event("startup")
async def seed_admin():
    """
    Seeds admin user from environment variables on first run.
    Admin requires password reset on first login for security.
    Set ADMIN_EMAIL and ADMIN_PASSWORD in .env file.
    """
    admin_email = os.environ.get('ADMIN_EMAIL')
    admin_password = os.environ.get('ADMIN_PASSWORD')
    
    # Only seed if both credentials are provided in environment
    if not admin_email or not admin_password:
        logging.warning("ADMIN_EMAIL or ADMIN_PASSWORD not set - skipping admin seeding")
        return
    
    existing_admin = await db.users.find_one({"email": admin_email})
    if not existing_admin:
        admin_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        admin_doc = {
            "id": admin_id,
            "email": admin_email,
            "name": "System Admin",
            "role": "admin",
            "password": hash_password(admin_password),
            "phone": None,
            "company_id": None,
            "is_active": True,
            "requires_password_reset": True,  # Force password change on first login
            "created_at": now
        }
        
        await db.users.insert_one(admin_doc)
        logging.info(f"Admin user seeded (requires password reset): {admin_email}")
    
    # Cleanup: Remove any test users on startup
    test_result = await db.users.delete_many({"email": {"$regex": "@test\\.com$"}})
    if test_result.deleted_count > 0:
        logging.info(f"Cleaned up {test_result.deleted_count} test users")

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
