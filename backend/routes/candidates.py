"""
VHC Talent OS - Candidate Bank Routes
Handles all candidate data bank operations including CRUD, visibility rules,
data governance enforcement, resume management, and audit history.
"""
import uuid
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
import aiofiles

# Import configuration
from config import db, UPLOAD_DIR, R2_ENABLED

# Import models
from models import (
    CandidateBankRecord, CandidateBankUpdate, BatchSaveRequest
)

# Import utilities
from utils import get_current_user, require_role
from utils.governance import (
    find_similar_candidate, should_update_field, create_audit_log,
    create_profile_audit_entry, generate_resume_fingerprint, normalize_phone
)

# Import R2 storage helpers
from services.r2_storage import generate_r2_key, upload_to_r2, get_r2_download_url

# Create router for candidate bank endpoints
candidates_router = APIRouter(prefix="/api", tags=["Candidate Bank"])

logger = logging.getLogger(__name__)


# ============== HELPER FUNCTIONS ==============

def extract_text_from_pdf(file_path: Path) -> str:
    """Extract text from PDF using PyMuPDF"""
    import fitz
    try:
        doc = fitz.open(str(file_path))
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return ""


async def parse_resume_with_ai(resume_text: str) -> dict:
    """Parse resume text using AI"""
    import os
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        import json
        
        parse_prompt = f"""Parse this resume and extract structured data.
Return JSON with these fields:
- name: Full name
- email: Email address
- phone: Phone number
- skills: Array of skills
- experience_years: Years of experience (number)
- summary: Brief summary
- headline: Professional headline
- location: Location
- experience: Array of work experiences
- education: Array of education

Resume text:
{resume_text[:6000]}

Return ONLY valid JSON."""

        chat_client = LlmChat(
            api_key=os.environ.get("EMERGENT_LLM_KEY"),
            session_id=str(uuid.uuid4()),
            system_message="You are a resume parser. Extract data accurately."
        )
        
        response = await chat_client.send_message(UserMessage(text=parse_prompt))
        
        # Parse JSON response
        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        
        parsed = json.loads(response_text)
        return {"success": True, "data": parsed}
        
    except Exception as e:
        logger.error(f"Resume parsing error: {e}")
        return {"success": False, "error": str(e)}


# ============== CANDIDATE VISIBILITY HELPERS ==============

async def check_candidate_visibility(candidate_id: str, current_user: dict) -> bool:
    """
    Unified visibility check for candidate data bank.
    Returns True if user has access, False otherwise.
    
    Rules:
    - Admin: Full access
    - Employer: Candidates parsed by self, team recruiters, or applied to employer's jobs
    - Recruiter: Candidates parsed by self, or applied to their ASSIGNED mandates
    - Candidate: NO access
    """
    if current_user["role"] == "admin":
        return True
    
    if current_user["role"] == "candidate":
        return False
    
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0, "created_by": 1, "visibility": 1})
    if not candidate:
        return False
    
    if current_user["role"] == "employer":
        # Check if employer created this candidate
        if candidate.get("created_by") == current_user["id"]:
            return True
        
        # Check if a team member created this candidate
        team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
        if team and candidate.get("created_by") in team.get("recruiter_ids", []):
            return True
        
        # Check if candidate applied to employer's jobs
        team_recruiter_ids = team.get("recruiter_ids", []) if team else []
        employer_jobs = await db.jobs.find(
            {"$or": [
                {"posted_by": current_user["id"]},
                {"posted_by": {"$in": team_recruiter_ids}},
                {"company_id": {"$in": team.get("company_ids", []) if team else []}}
            ]},
            {"id": 1, "_id": 0}
        ).to_list(1000)
        employer_job_ids = [j["id"] for j in employer_jobs]
        
        application = await db.applications.find_one({
            "candidate_id": candidate_id,
            "job_id": {"$in": employer_job_ids}
        })
        if application:
            return True
        
        # Check legacy visibility field
        if current_user["id"] in candidate.get("visibility", {}).get("employer_ids", []):
            return True
        
        return False
    
    elif current_user["role"] == "recruiter":
        # Check if recruiter created this candidate
        if candidate.get("created_by") == current_user["id"]:
            return True
        
        # Check if candidate applied to recruiter's ASSIGNED mandates
        # CRITICAL: Use assigned_recruiters for mandate allocation compliance
        recruiter_jobs = await db.jobs.find(
            {"$or": [
                {"posted_by": current_user["id"]},
                {"assigned_recruiters": current_user["id"]}  # Aligned with mandate allocation
            ]},
            {"id": 1, "_id": 0}
        ).to_list(1000)
        recruiter_job_ids = [j["id"] for j in recruiter_jobs]
        
        application = await db.applications.find_one({
            "candidate_id": candidate_id,
            "job_id": {"$in": recruiter_job_ids}
        })
        if application:
            return True
        
        # Check legacy visibility field
        if current_user["id"] in candidate.get("visibility", {}).get("recruiter_ids", []):
            return True
        
        return False
    
    return False


async def get_accessible_candidate_ids(current_user: dict) -> list:
    """
    Get list of candidate IDs accessible to the current user.
    Used for list queries.
    """
    if current_user["role"] == "admin":
        return None  # None means no filter (full access)
    
    if current_user["role"] == "candidate":
        return []  # Empty list means no access
    
    accessible_ids = set()
    
    if current_user["role"] == "employer":
        # Get employer's team
        team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
        team_recruiter_ids = team.get("recruiter_ids", []) if team else []
        
        # Get jobs under employer's mandates
        employer_jobs = await db.jobs.find(
            {"$or": [
                {"posted_by": current_user["id"]},
                {"posted_by": {"$in": team_recruiter_ids}},
                {"company_id": {"$in": team.get("company_ids", []) if team else []}}
            ]},
            {"id": 1, "_id": 0}
        ).to_list(1000)
        employer_job_ids = [j["id"] for j in employer_jobs]
        
        # Get candidate IDs who applied to employer's jobs
        applications = await db.applications.find(
            {"job_id": {"$in": employer_job_ids}},
            {"candidate_id": 1, "_id": 0}
        ).to_list(10000)
        accessible_ids.update([a.get("candidate_id") for a in applications if a.get("candidate_id")])
        
        # Add candidates created by employer or team
        created_candidates = await db.candidate_bank.find(
            {"$or": [
                {"created_by": current_user["id"]},
                {"created_by": {"$in": team_recruiter_ids}},
                {"visibility.employer_ids": current_user["id"]}
            ]},
            {"id": 1, "_id": 0}
        ).to_list(10000)
        accessible_ids.update([c["id"] for c in created_candidates])
        
    elif current_user["role"] == "recruiter":
        # Get recruiter's ASSIGNED mandates (aligned with mandate allocation)
        recruiter_jobs = await db.jobs.find(
            {"$or": [
                {"posted_by": current_user["id"]},
                {"assigned_recruiters": current_user["id"]}  # Aligned with mandate allocation
            ]},
            {"id": 1, "_id": 0}
        ).to_list(1000)
        recruiter_job_ids = [j["id"] for j in recruiter_jobs]
        
        # Get candidate IDs who applied to recruiter's jobs
        applications = await db.applications.find(
            {"job_id": {"$in": recruiter_job_ids}},
            {"candidate_id": 1, "_id": 0}
        ).to_list(10000)
        accessible_ids.update([a.get("candidate_id") for a in applications if a.get("candidate_id")])
        
        # Add candidates created by recruiter
        created_candidates = await db.candidate_bank.find(
            {"$or": [
                {"created_by": current_user["id"]},
                {"visibility.recruiter_ids": current_user["id"]}
            ]},
            {"id": 1, "_id": 0}
        ).to_list(10000)
        accessible_ids.update([c["id"] for c in created_candidates])
    
    return list(accessible_ids)


# ============== RESUME DOWNLOAD ==============

@candidates_router.get("/candidates/{candidate_id}/resume")
async def download_candidate_resume(
    candidate_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Download resume directly from candidate bank.
    Same naming convention: Firstname_Lastname_VHC.ext
    
    Access Control:
    - Admin: Full access
    - Employer/Recruiter: Must have visibility to the candidate
    
    Resume must be downloadable even if candidate is NOT in any pipeline.
    """
    # Get candidate from candidate bank
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not candidate:
        # Try candidates collection
        candidate = await db.candidates.find_one({"id": candidate_id}, {"_id": 0})
    
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    # Access control check (same as candidate bank visibility)
    if current_user["role"] == "employer":
        has_access = False
        if candidate.get("created_by") == current_user["id"]:
            has_access = True
        if not has_access:
            team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
            if team and candidate.get("created_by") in team.get("recruiter_ids", []):
                has_access = True
        if not has_access and current_user["id"] in candidate.get("visibility", {}).get("employer_ids", []):
            has_access = True
        # Check if candidate has an application to employer's jobs
        if not has_access:
            team = await db.teams.find_one({"employer_id": current_user["id"], "status": "active"}, {"_id": 0})
            team_recruiter_ids = team.get("recruiter_ids", []) if team else []
            employer_jobs = await db.jobs.find(
                {"$or": [
                    {"posted_by": current_user["id"]},
                    {"posted_by": {"$in": team_recruiter_ids}}
                ]},
                {"id": 1, "_id": 0}
            ).to_list(1000)
            employer_job_ids = [j["id"] for j in employer_jobs]
            application = await db.applications.find_one({
                "candidate_id": candidate_id,
                "job_id": {"$in": employer_job_ids}
            })
            if application:
                has_access = True
        if not has_access:
            raise HTTPException(status_code=403, detail="Access denied to this candidate's resume")
            
    elif current_user["role"] == "recruiter":
        has_access = False
        if candidate.get("created_by") == current_user["id"]:
            has_access = True
        if not has_access and current_user["id"] in candidate.get("visibility", {}).get("recruiter_ids", []):
            has_access = True
        # Check if candidate has an application to recruiter's jobs
        if not has_access:
            team = await db.teams.find_one({"recruiter_ids": current_user["id"], "status": "active"}, {"_id": 0})
            recruiter_jobs = await db.jobs.find(
                {"$or": [
                    {"posted_by": current_user["id"]},
                    {"team_id": team["id"]} if team else {"team_id": "__never_match__"}
                ]},
                {"id": 1, "_id": 0}
            ).to_list(1000)
            recruiter_job_ids = [j["id"] for j in recruiter_jobs]
            application = await db.applications.find_one({
                "candidate_id": candidate_id,
                "job_id": {"$in": recruiter_job_ids}
            })
            if application:
                has_access = True
        if not has_access:
            raise HTTPException(status_code=403, detail="Access denied to this candidate's resume")
    
    # Check for R2 storage first
    resume_versions = candidate.get("resume_versions", [])
    active_resume_id = candidate.get("active_resume_id")
    
    # Find active resume version with R2 metadata
    r2_metadata = None
    for version in resume_versions:
        if version.get("id") == active_resume_id and version.get("r2_metadata"):
            r2_metadata = version.get("r2_metadata")
            break
    
    if r2_metadata and r2_metadata.get("storage") == "r2":
        # Generate signed URL for R2 download
        r2_key = r2_metadata.get("r2_key")
        if r2_key:
            try:
                signed_url = await get_r2_download_url(r2_key)
                if signed_url:
                    from fastapi.responses import RedirectResponse
                    return RedirectResponse(url=signed_url, status_code=302)
            except Exception as e:
                logger.error(f"R2 download URL generation failed: {e}")
                # Fall through to local file
    
    # Get resume URL for local file
    resume_url = candidate.get("resume_url")
    if not resume_url:
        raise HTTPException(status_code=404, detail="Resume not found for this candidate")
    
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
    
    # Generate download filename
    candidate_name = candidate.get("name", "Unknown_Candidate")
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


@candidates_router.get("/candidate-bank/{candidate_id}/download-resume")
async def download_candidate_bank_resume(
    candidate_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Download resume from Candidate Data Bank view.
    Alias for /candidates/{candidate_id}/resume with same access control.
    """
    return await download_candidate_resume(candidate_id, current_user)


# ============== CANDIDATE BANK CRUD ==============

@candidates_router.get("/candidate-bank", response_model=List[CandidateBankRecord])
async def get_candidate_bank(
    search: Optional[str] = None,
    skills: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Get candidates from data bank based on STRICT role visibility.
    
    Access Control (Data Governance):
    - Admin: Full access to all candidates from all sources
    - Employer: Only candidates parsed by self, parsed by assigned team members, 
                or applied via job postings under employer's mandates
    - Recruiter: Only candidates parsed by self, or applied via jobs of their assigned mandates
    - Candidate: NO access (returns empty list)
    """
    
    # Use unified helper for candidate visibility
    accessible_ids = await get_accessible_candidate_ids(current_user)
    
    # Candidate has ZERO access to internal Candidate Data Bank
    if accessible_ids is not None and len(accessible_ids) == 0:
        return []
    
    query = {}
    
    # Apply visibility filter (None means full access for admin)
    if accessible_ids is not None:
        query["id"] = {"$in": accessible_ids}
    
    # Search filter
    if search:
        search_condition = {
            "$or": [
                {"name": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}},
                {"skills": {"$regex": search, "$options": "i"}}
            ]
        }
        if "id" in query:
            query = {"$and": [{"id": query["id"]}, search_condition]}
        else:
            query.update(search_condition)
    
    # Skills filter
    if skills:
        skill_list = [s.strip() for s in skills.split(",")]
        skill_condition = {"skills": {"$in": skill_list}}
        if "$and" in query:
            query["$and"].append(skill_condition)
        else:
            query["skills"] = {"$in": skill_list}
    
    candidates = await db.candidate_bank.find(query, {"_id": 0}).to_list(500)
    return [CandidateBankRecord(**c) for c in candidates]


@candidates_router.get("/candidate-bank/{candidate_id}")
async def get_candidate_bank_record(
    candidate_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get single candidate from data bank with STRICT visibility check.
    
    Access Control (Data Governance):
    - Admin: Full access
    - Employer: Only if candidate was parsed by self, team member, or applied to employer's jobs
    - Recruiter: Only if candidate was parsed by self or applied to recruiter's ASSIGNED mandates
    - Candidate: NO access
    """
    
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    # Use unified visibility helper
    has_access = await check_candidate_visibility(candidate_id, current_user)
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied to this candidate")
    
    return candidate


@candidates_router.put("/candidate-bank/{candidate_id}")
async def update_candidate_bank_record(
    candidate_id: str,
    update_data: CandidateBankUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update candidate in data bank with priority rules and audit"""
    
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    # Determine source based on role and ownership
    if current_user["role"] == "candidate" and candidate.get("linked_user_id") == current_user["id"]:
        source = "candidate"
    else:
        source = current_user["role"]
    
    update_dict = {}
    for field, value in update_data.model_dump().items():
        if value is not None:
            if await should_update_field(candidate_id, field, source, db):
                old_val = candidate.get(field)
                if old_val != value:
                    update_dict[field] = value
                    await create_audit_log(candidate_id, field, old_val, value, current_user, f"{source}_update")
    
    if update_dict:
        update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
        update_dict["last_updated_by"] = current_user["id"]
        
        await db.candidate_bank.update_one(
            {"id": candidate_id},
            {"$set": update_dict}
        )
    
    return {"message": "Candidate updated", "fields_updated": list(update_dict.keys())}


# ============== CANDIDATE BANK ADD ==============

@candidates_router.post("/candidate-bank/add")
async def add_to_candidate_bank(
    file: UploadFile = File(...),
    email: str = Form(None),
    name: str = Form(None),
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Add candidate to data bank from resume upload with deduplication"""
    
    # Parse resume
    if not file.filename.lower().endswith(('.pdf', '.doc', '.docx', '.txt')):
        raise HTTPException(status_code=400, detail="Only PDF, DOC, DOCX, TXT files allowed")
    
    file_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix
    file_path = UPLOAD_DIR / f"resume_{file_id}{file_ext}"
    
    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    # Upload to R2 if enabled
    r2_metadata = None
    if R2_ENABLED:
        try:
            r2_key = generate_r2_key("candidate-bank", file.filename)
            r2_result = await upload_to_r2(content, r2_key, file.content_type or "application/octet-stream")
            if r2_result.get("storage") == "r2":
                r2_metadata = {
                    "storage": "r2",
                    "r2_key": r2_key,
                    "original_filename": file.filename,
                    "content_type": file.content_type,
                    "uploaded_at": datetime.now(timezone.utc).isoformat(),
                    "uploaded_by": current_user["id"],
                    "uploaded_by_role": current_user["role"]
                }
                logging.info(f"[R2] Candidate bank resume uploaded to R2: {r2_key}")
        except Exception as e:
            logging.error(f"[R2] Candidate bank upload failed, using local storage: {e}")
    
    # Extract and parse
    if file_ext.lower() == '.pdf':
        resume_text = extract_text_from_pdf(file_path)
    else:
        async with aiofiles.open(file_path, 'r', errors='ignore') as f:
            resume_text = await f.read()
    
    fingerprint = generate_resume_fingerprint(resume_text)
    
    parse_result = await parse_resume_with_ai(resume_text)
    if not parse_result["success"]:
        raise HTTPException(status_code=500, detail="Failed to parse resume")
    
    parsed_data = parse_result["data"]
    candidate_email = email or parsed_data.get("email")
    candidate_name = name or parsed_data.get("name")
    
    if not candidate_email:
        raise HTTPException(status_code=400, detail="Could not determine candidate email")
    
    # Check for duplicates
    dup_check = await find_similar_candidate(
        db,
        email=candidate_email,
        phone=parsed_data.get("phone"),
        resume_fingerprint=fingerprint
    )
    
    now = datetime.now(timezone.utc).isoformat()
    resume_version = {
        "id": file_id,
        "filename": file.filename,
        "path": str(file_path),
        "fingerprint": fingerprint,
        "uploaded_at": now,
        "uploaded_by": current_user["id"],
        "is_active": True,
        "r2_metadata": r2_metadata  # R2 storage info (None if local only)
    }
    
    if dup_check["found"]:
        # Update existing candidate
        existing = dup_check["candidate"]
        
        # Mark old resumes as inactive
        await db.candidate_bank.update_one(
            {"id": existing["id"]},
            {"$set": {"resume_versions.$[].is_active": False}}
        )
        
        # Add new resume version
        await db.candidate_bank.update_one(
            {"id": existing["id"]},
            {
                "$push": {"resume_versions": resume_version},
                "$addToSet": {"resume_fingerprints": fingerprint},
                "$set": {
                    "active_resume_id": file_id,
                    "resume_url": f"/api/uploads/resume_{file_id}{file_ext}",
                    "updated_at": now,
                    "last_updated_by": current_user["id"],
                    "last_profile_updated_at": now
                }
            }
        )
        
        return {
            "action": "updated",
            "candidate_id": existing["id"],
            "match_type": dup_check.get("match_type", "unknown"),
            "message": f"Existing candidate updated: {existing.get('name')}"
        }
    
    # Create new candidate
    candidate_id = str(uuid.uuid4())
    
    candidate_doc = {
        "id": candidate_id,
        "email": candidate_email.lower().strip(),
        "name": candidate_name or "Unknown",
        "phone": parsed_data.get("phone"),
        "phone_normalized": normalize_phone(parsed_data.get("phone", "")),
        "headline": parsed_data.get("headline"),
        "summary": parsed_data.get("summary"),
        "skills": parsed_data.get("skills", []),
        "experience_years": parsed_data.get("experience_years"),
        "experience": parsed_data.get("experience", []),
        "education": parsed_data.get("education", []),
        "location": parsed_data.get("location"),
        "certifications": [],
        "active_resume_id": file_id,
        "resume_versions": [resume_version],
        "resume_fingerprints": [fingerprint],
        "resume_url": f"/api/uploads/resume_{file_id}{file_ext}",
        "current_salary": None,  # Data Governance: mandatory field, needs to be filled
        "notice_period": None,   # Data Governance: mandatory field, needs to be filled
        "source": current_user["role"],
        "linked_user_id": None,
        "visibility": {
            f"{current_user['role']}_ids": [current_user["id"]]
        },
        "match_cache": [],
        "created_at": now,
        "updated_at": now,
        "created_by": current_user["id"],
        "last_updated_by": current_user["id"],
        # Data Governance: Profile Freshness metadata
        "last_profile_updated_at": now,
        "last_application_date": None,
        "application_history": [],
        "profile_update_audit": []
    }
    
    await db.candidate_bank.insert_one(candidate_doc)
    
    return {
        "action": "created",
        "candidate_id": candidate_id,
        "message": "New candidate added to data bank"
    }


# ============== BATCH CV UPLOAD ==============

@candidates_router.post("/candidate-bank/batch-parse")
async def batch_parse_resumes(
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Parse up to 10 CVs and return preview data. No save - just parsing.
    Returns parsed data for each file for user preview/edit before save.
    """
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files allowed per batch")
    
    if len(files) == 0:
        raise HTTPException(status_code=400, detail="No files uploaded")
    
    results = []
    
    for file in files:
        temp_id = str(uuid.uuid4())
        
        try:
            # Validate file type
            if not file.filename.lower().endswith(('.pdf', '.doc', '.docx')):
                results.append({
                    "temp_id": temp_id,
                    "filename": file.filename,
                    "success": False,
                    "error": "Only PDF, DOC, DOCX files allowed"
                })
                continue
            
            # Save file temporarily
            file_id = str(uuid.uuid4())
            file_ext = Path(file.filename).suffix
            file_path = UPLOAD_DIR / f"resume_{file_id}{file_ext}"
            
            async with aiofiles.open(file_path, 'wb') as f:
                content = await file.read()
                await f.write(content)
            
            # Upload to R2 if enabled
            r2_metadata = None
            if R2_ENABLED:
                try:
                    r2_key = generate_r2_key("candidate-bank/batch", file.filename)
                    r2_result = await upload_to_r2(content, r2_key, file.content_type or "application/octet-stream")
                    if r2_result.get("storage") == "r2":
                        r2_metadata = {
                            "storage": "r2",
                            "r2_key": r2_key,
                            "original_filename": file.filename,
                            "content_type": file.content_type,
                            "uploaded_at": datetime.now(timezone.utc).isoformat(),
                            "uploaded_by": current_user["id"],
                            "uploaded_by_role": current_user["role"]
                        }
                        logging.info(f"[R2] Batch resume uploaded to R2: {r2_key}")
                except Exception as e:
                    logging.error(f"[R2] Batch upload failed, using local storage: {e}")
            
            # Extract text
            if file_ext.lower() == '.pdf':
                resume_text = extract_text_from_pdf(file_path)
            else:
                async with aiofiles.open(file_path, 'r', errors='ignore') as f:
                    resume_text = await f.read()
            
            # Generate fingerprint for dedup
            fingerprint = generate_resume_fingerprint(resume_text)
            
            # Parse with AI
            parse_result = await parse_resume_with_ai(resume_text[:8000])
            
            if not parse_result["success"]:
                results.append({
                    "temp_id": temp_id,
                    "filename": file.filename,
                    "success": False,
                    "error": "Failed to parse resume"
                })
                continue
            
            parsed_data = parse_result["data"]
            
            # Check for duplicates
            dup_check = await find_similar_candidate(
                db,
                email=parsed_data.get("email"),
                phone=parsed_data.get("phone"),
                resume_fingerprint=fingerprint
            )
            
            results.append({
                "temp_id": temp_id,
                "filename": file.filename,
                "file_id": file_id,
                "fingerprint": fingerprint,
                "r2_metadata": r2_metadata,  # R2 storage info (None if local only)
                "success": True,
                "parsed_data": {
                    "name": parsed_data.get("name", "Unknown"),
                    "email": parsed_data.get("email", ""),
                    "phone": parsed_data.get("phone", ""),
                    "skills": parsed_data.get("skills", []),
                    "experience_summary": parsed_data.get("summary", ""),
                    "experience_years": parsed_data.get("experience_years", 0),
                    "location": parsed_data.get("location", ""),
                    "headline": parsed_data.get("headline", ""),
                    "experience": parsed_data.get("experience", []),
                    "education": parsed_data.get("education", [])
                },
                "duplicate_check": {
                    "is_duplicate": dup_check["found"],
                    "match_type": dup_check.get("match_type"),
                    "existing_candidate": {
                        "id": dup_check["candidate"]["id"],
                        "name": dup_check["candidate"].get("name"),
                        "email": dup_check["candidate"].get("email"),
                        "created_at": dup_check["candidate"].get("created_at"),
                        "current_salary": dup_check["candidate"].get("current_salary"),
                        "notice_period": dup_check["candidate"].get("notice_period")
                    } if dup_check["found"] else None
                }
            })
            
        except Exception as e:
            logger.error(f"Error parsing file {file.filename}: {str(e)}")
            results.append({
                "temp_id": temp_id,
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })
    
    return {
        "total": len(files),
        "parsed": len([r for r in results if r.get("success")]),
        "failed": len([r for r in results if not r.get("success")]),
        "results": results
    }


@candidates_router.post("/candidate-bank/batch-save")
async def batch_save_candidates(
    request: BatchSaveRequest,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Save multiple candidates to data bank after user review/edit.
    ATOMIC: All succeed or all fail. Validates salary & notice period as mandatory.
    """
    candidates = request.candidates
    
    if len(candidates) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 candidates per batch")
    
    if len(candidates) == 0:
        raise HTTPException(status_code=400, detail="No candidates to save")
    
    # VALIDATION PHASE - Check all candidates first (Data Governance enforcement)
    validation_errors = []
    
    for idx, candidate in enumerate(candidates):
        errors = []
        
        if not candidate.email or not candidate.email.strip():
            errors.append("Email is required")
        if not candidate.name or not candidate.name.strip():
            errors.append("Name is required")
        # Data Governance: Mandatory fields enforcement
        if not candidate.current_salary or candidate.current_salary <= 0:
            errors.append("Current salary (INR) is mandatory and must be positive")
        if not candidate.notice_period or not candidate.notice_period.strip():
            errors.append("Notice period is mandatory")
        if not candidate.location or not candidate.location.strip():
            errors.append("Location is mandatory")
        if candidate.experience_years is None:
            errors.append("Experience (years) is mandatory")
        
        if errors:
            validation_errors.append({
                "temp_id": candidate.temp_id,
                "index": idx,
                "name": candidate.name,
                "errors": errors
            })
    
    # If any validation errors, FAIL ALL (atomic behavior)
    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validation failed. No candidates were saved.",
                "errors": validation_errors
            }
        )
    
    # SAVE PHASE - All validated, now save
    now = datetime.now(timezone.utc).isoformat()
    saved = []
    
    for candidate in candidates:
        try:
            # Check for duplicate again (in case of race condition)
            dup_check = await find_similar_candidate(
                db,
                email=candidate.email,
                phone=candidate.phone,
                resume_fingerprint=candidate.fingerprint
            )
            
            file_path = None
            for f in UPLOAD_DIR.iterdir():
                if candidate.file_id in f.name:
                    file_path = f
                    break
            
            resume_version = {
                "id": candidate.file_id,
                "fingerprint": candidate.fingerprint,
                "uploaded_at": now,
                "uploaded_by": current_user["id"],
                "is_active": True,
                "r2_metadata": candidate.r2_metadata  # R2 storage info
            }
            
            if dup_check["found"]:
                # Update existing candidate
                existing = dup_check["candidate"]
                
                update_data = {
                    "resume_versions": existing.get("resume_versions", []) + [resume_version],
                    "active_resume_id": candidate.file_id,
                    "updated_at": now,
                    "last_updated_by": current_user["id"],
                    "current_salary": candidate.current_salary,
                    "notice_period": candidate.notice_period,
                    "resume_url": f"/api/uploads/resume_{candidate.file_id}{Path(file_path).suffix if file_path else '.pdf'}"
                }
                
                # Update fields with audit logging
                source = current_user["role"]
                
                if candidate.name and candidate.name != existing.get("name"):
                    if await should_update_field(existing["id"], "name", source, db):
                        await create_audit_log(existing["id"], "name", existing.get("name"), candidate.name, current_user, "batch_upload")
                        update_data["name"] = candidate.name
                
                if candidate.skills and candidate.skills != existing.get("skills"):
                    if await should_update_field(existing["id"], "skills", source, db):
                        await create_audit_log(existing["id"], "skills", existing.get("skills"), candidate.skills, current_user, "batch_upload")
                        update_data["skills"] = candidate.skills
                
                if candidate.experience_summary and candidate.experience_summary != existing.get("summary"):
                    if await should_update_field(existing["id"], "summary", source, db):
                        await create_audit_log(existing["id"], "summary", existing.get("summary"), candidate.experience_summary, current_user, "batch_upload")
                        update_data["summary"] = candidate.experience_summary
                
                # Add fingerprint if new
                if candidate.fingerprint not in existing.get("resume_fingerprints", []):
                    update_data["resume_fingerprints"] = existing.get("resume_fingerprints", []) + [candidate.fingerprint]
                
                await db.candidate_bank.update_one({"id": existing["id"]}, {"$set": update_data})
                
                saved.append({
                    "temp_id": candidate.temp_id,
                    "action": "updated",
                    "candidate_id": existing["id"],
                    "name": candidate.name
                })
            
            else:
                # Create new candidate
                candidate_id = str(uuid.uuid4())
                
                candidate_doc = {
                    "id": candidate_id,
                    "email": candidate.email.lower().strip(),
                    "name": candidate.name.strip(),
                    "phone": candidate.phone,
                    "phone_normalized": normalize_phone(candidate.phone or ""),
                    "headline": None,
                    "summary": candidate.experience_summary,
                    "skills": candidate.skills,
                    "experience_years": candidate.experience_years,  # Data Governance: mandatory
                    "experience": [],
                    "education": [],
                    "location": candidate.location,  # Data Governance: mandatory
                    "certifications": [],
                    "active_resume_id": candidate.file_id,
                    "resume_versions": [resume_version],
                    "resume_fingerprints": [candidate.fingerprint],
                    "resume_url": f"/api/uploads/resume_{candidate.file_id}{Path(file_path).suffix if file_path else '.pdf'}",
                    "current_salary": candidate.current_salary,
                    "notice_period": candidate.notice_period,
                    "source": current_user["role"],
                    "linked_user_id": None,
                    "visibility": {
                        f"{current_user['role']}_ids": [current_user["id"]]
                    },
                    "match_cache": [],
                    "created_at": now,
                    "updated_at": now,
                    "created_by": current_user["id"],
                    "last_updated_by": current_user["id"],
                    # Data Governance: Profile Freshness metadata
                    "last_profile_updated_at": now,
                    "last_application_date": None,
                    "application_history": [],
                    "profile_update_audit": []
                }
                
                await db.candidate_bank.insert_one(candidate_doc)
                
                saved.append({
                    "temp_id": candidate.temp_id,
                    "action": "created",
                    "candidate_id": candidate_id,
                    "name": candidate.name
                })
        
        except Exception as e:
            logger.error(f"Error saving candidate {candidate.temp_id}: {str(e)}")
            # Atomic failure - rollback and fail all
            raise HTTPException(
                status_code=500,
                detail={
                    "message": f"Failed to save candidate {candidate.name}. No candidates were saved.",
                    "error": str(e)
                }
            )
    
    return {
        "success": True,
        "message": f"Successfully saved {len(saved)} candidates",
        "saved": saved
    }


# ============== UPDATE CANDIDATE MANDATORY FIELDS ==============

@candidates_router.put("/candidate-bank/{candidate_id}/salary-notice")
async def update_candidate_mandatory_fields(
    candidate_id: str,
    current_salary: int = None,
    notice_period: str = None,
    location: str = None,
    experience_years: int = None,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Update candidate's mandatory fields in the Candidate Data Bank.
    Data Governance: salary, notice_period, location, experience_years
    Used to ensure mandatory fields are set before linking to jobs.
    All changes are audit-logged.
    """
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    now = datetime.now(timezone.utc).isoformat()
    update_data = {"updated_at": now}
    audit_entries = []
    
    # Track which fields are being updated
    fields_updated = []
    
    if current_salary is not None:
        if current_salary <= 0:
            raise HTTPException(status_code=400, detail="Salary must be positive")
        
        old_val = candidate.get("current_salary")
        if old_val != current_salary:
            audit_entries.append(create_profile_audit_entry(
                "current_salary", old_val, current_salary,
                current_user["id"], current_user["name"], current_user["role"],
                "manual_update"
            ))
            await create_audit_log(
                candidate_id, "current_salary", old_val, current_salary, 
                current_user, "manual_update"
            )
        update_data["current_salary"] = current_salary
        fields_updated.append("current_salary")
    
    if notice_period is not None:
        if not notice_period.strip():
            raise HTTPException(status_code=400, detail="Notice period cannot be empty")
        
        old_val = candidate.get("notice_period")
        if old_val != notice_period.strip():
            audit_entries.append(create_profile_audit_entry(
                "notice_period", old_val, notice_period.strip(),
                current_user["id"], current_user["name"], current_user["role"],
                "manual_update"
            ))
            await create_audit_log(
                candidate_id, "notice_period", old_val, notice_period.strip(),
                current_user, "manual_update"
            )
        update_data["notice_period"] = notice_period.strip()
        fields_updated.append("notice_period")
    
    if location is not None:
        if not location.strip():
            raise HTTPException(status_code=400, detail="Location cannot be empty")
        
        old_val = candidate.get("location")
        if old_val != location.strip():
            audit_entries.append(create_profile_audit_entry(
                "location", old_val, location.strip(),
                current_user["id"], current_user["name"], current_user["role"],
                "manual_update"
            ))
            await create_audit_log(
                candidate_id, "location", old_val, location.strip(),
                current_user, "manual_update"
            )
        update_data["location"] = location.strip()
        fields_updated.append("location")
    
    if experience_years is not None:
        if experience_years < 0:
            raise HTTPException(status_code=400, detail="Experience years cannot be negative")
        
        old_val = candidate.get("experience_years")
        if old_val != experience_years:
            audit_entries.append(create_profile_audit_entry(
                "experience_years", old_val, experience_years,
                current_user["id"], current_user["name"], current_user["role"],
                "manual_update"
            ))
            await create_audit_log(
                candidate_id, "experience_years", old_val, experience_years,
                current_user, "manual_update"
            )
        update_data["experience_years"] = experience_years
        fields_updated.append("experience_years")
    
    # Update freshness metadata
    update_data["last_profile_updated_at"] = now
    update_data["last_updated_by"] = current_user["id"]
    
    # Perform update with audit log appended
    update_ops = {"$set": update_data}
    if audit_entries:
        update_ops["$push"] = {"profile_update_audit": {"$each": audit_entries}}
    
    await db.candidate_bank.update_one({"id": candidate_id}, update_ops)
    
    return {
        "success": True,
        "message": "Candidate updated successfully",
        "candidate_id": candidate_id,
        "fields_updated": fields_updated
    }


# ============== CANDIDATE AUDIT & HISTORY ==============

@candidates_router.get("/candidate-bank/{candidate_id}/audit-log")
async def get_candidate_audit_log(
    candidate_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Get audit trail for candidate with proper visibility check"""
    
    # Check candidate visibility using unified helper
    has_access = await check_candidate_visibility(candidate_id, current_user)
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied to this candidate")
    
    logs = await db.audit_logs.find(
        {"candidate_id": candidate_id},
        {"_id": 0}
    ).sort("timestamp", -1).to_list(100)
    
    return logs


@candidates_router.get("/candidate-bank/{candidate_id}/history")
async def get_candidate_activity_history(
    candidate_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Data Governance: Get candidate's complete activity history.
    Internal-only endpoint for Admin, Employer, Recruiter.
    Shows all applications, stage changes, and outcomes across all jobs.
    """
    # Check candidate visibility using unified helper
    has_access = await check_candidate_visibility(candidate_id, current_user)
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied to this candidate")
    
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    # Get all applications for this candidate
    applications = await db.applications.find(
        {"candidate_id": candidate_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    # Enrich with job and company details
    enriched_applications = []
    for app in applications:
        job = await db.jobs.find_one({"id": app.get("job_id")}, {"title": 1, "company_id": 1, "location": 1, "_id": 0})
        company_name = "Unknown"
        if job and job.get("company_id"):
            company = await db.companies.find_one({"id": job.get("company_id")}, {"name": 1, "_id": 0})
            company_name = company.get("name") if company else app.get("company_name", "Unknown")
        
        enriched_applications.append({
            "application_id": app.get("id"),
            "job_id": app.get("job_id"),
            "job_title": job.get("title") if job else app.get("job_title", "Unknown"),
            "company_name": company_name,
            "job_location": job.get("location") if job else None,
            "stage": app.get("stage", "applied"),
            "source": app.get("source", "self"),
            "applied_at": app.get("created_at"),
            "last_updated": app.get("updated_at"),
            "current_salary_at_application": app.get("current_salary"),
            "notice_period_at_application": app.get("notice_period"),
            "has_notes": len(app.get("notes", [])) > 0,
            "edit_count": len(app.get("edit_history", []))
        })
    
    # Get stored application history from candidate record
    stored_history = candidate.get("application_history", [])
    
    # Profile freshness data
    freshness = {
        "last_profile_updated_at": candidate.get("last_profile_updated_at"),
        "last_application_date": candidate.get("last_application_date"),
        "profile_created_at": candidate.get("created_at"),
        "total_applications": len(applications)
    }
    
    # Profile audit trail for mandatory fields
    profile_audit = candidate.get("profile_update_audit", [])[-20:]  # Last 20 entries
    
    return {
        "candidate_id": candidate_id,
        "candidate_name": candidate.get("name"),
        "candidate_email": candidate.get("email"),
        "applications": enriched_applications,
        "stored_history": stored_history,
        "freshness": freshness,
        "profile_audit": profile_audit,
        "summary": {
            "total_applications": len(applications),
            "stages": {
                "applied": sum(1 for a in applications if a.get("stage") == "applied"),
                "shortlisted": sum(1 for a in applications if a.get("stage") == "shortlisted"),
                "interview": sum(1 for a in applications if a.get("stage") == "interview"),
                "offered": sum(1 for a in applications if a.get("stage") == "offered"),
                "hired": sum(1 for a in applications if a.get("stage") == "hired"),
                "rejected": sum(1 for a in applications if a.get("stage") == "rejected"),
            }
        }
    }


@candidates_router.get("/candidate-bank/{candidate_id}/resume-history")
async def get_candidate_resume_history(
    candidate_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Get resume version history for candidate with proper visibility check"""
    
    # Check candidate visibility using unified helper
    has_access = await check_candidate_visibility(candidate_id, current_user)
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied to this candidate")
    
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    return {
        "active_resume_id": candidate.get("active_resume_id"),
        "resume_versions": candidate.get("resume_versions", [])
    }


# ============== LINK CANDIDATE TO JOB ==============

class LinkCandidateRequest(BaseModel):
    """Request to link a candidate to a job as an applicant"""
    candidate_id: str
    job_id: str


@candidates_router.post("/applications/link-candidate")
async def link_candidate_to_job(
    request: LinkCandidateRequest,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """
    Create an application record linking a Candidate Data Bank record to a job.
    Does NOT duplicate the candidate - just creates an application.
    Inherits salary & notice period from Candidate Data Bank.
    """
    # Validate candidate exists
    candidate = await db.candidate_bank.find_one({"id": request.candidate_id}, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found in data bank")
    
    # Validate job exists
    job = await db.jobs.find_one({"id": request.job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check if application already exists
    existing_app = await db.applications.find_one({
        "candidate_id": request.candidate_id,
        "job_id": request.job_id
    })
    if existing_app:
        raise HTTPException(
            status_code=400,
            detail="Application already exists for this candidate-job combination"
        )
    
    # Data Governance: Ensure mandatory fields are present
    if not candidate.get("current_salary"):
        raise HTTPException(
            status_code=400,
            detail="Candidate salary is required. Please update the candidate's salary first."
        )
    if not candidate.get("notice_period"):
        raise HTTPException(
            status_code=400,
            detail="Candidate notice period is required. Please update first."
        )
    
    # Create application
    now = datetime.now(timezone.utc).isoformat()
    application_id = str(uuid.uuid4())
    
    application_doc = {
        "id": application_id,
        "candidate_id": request.candidate_id,
        "job_id": request.job_id,
        "email": candidate.get("email"),
        "name": candidate.get("name"),
        "phone": candidate.get("phone"),
        "resume_url": candidate.get("resume_url"),
        "current_salary": candidate.get("current_salary"),
        "notice_period": candidate.get("notice_period"),
        "skills": candidate.get("skills", []),
        "experience_years": candidate.get("experience_years"),
        "location": candidate.get("location"),
        "stage": "applied",
        "source": current_user["role"],
        "source_role": current_user["role"],
        "created_by": current_user["id"],
        "created_at": now,
        "updated_at": now,
        "notes": [],
        "edit_history": []
    }
    
    await db.applications.insert_one(application_doc)
    
    # Update job applicant count
    await db.jobs.update_one(
        {"id": request.job_id},
        {"$inc": {"applicant_count": 1}}
    )
    
    # Update candidate's application history
    await db.candidate_bank.update_one(
        {"id": request.candidate_id},
        {
            "$set": {"last_application_date": now},
            "$push": {
                "application_history": {
                    "job_id": request.job_id,
                    "job_title": job.get("title"),
                    "applied_at": now,
                    "source": current_user["role"]
                }
            }
        }
    )
    
    logging.info(f"Candidate {candidate.get('name')} linked to job {job.get('title')} by {current_user['name']} ({current_user['role']})")
    
    return {
        "success": True,
        "message": "Candidate linked to job successfully",
        "application_id": application_id,
        "candidate_name": candidate.get("name"),
        "job_title": job.get("title")
    }
