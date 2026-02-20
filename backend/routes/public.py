"""
VHC Talent OS - Public Routes (No Authentication Required)
Handles public job listings, resume parsing, and job applications.
"""
import uuid
import re
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel, EmailStr
import aiofiles
import fitz  # PyMuPDF

# Import configuration
from config import db, R2_ENABLED, UPLOAD_DIR

# Import services
from services import upload_to_r2, generate_r2_key

# Create logger
logger = logging.getLogger(__name__)

# Create router for public endpoints
public_router = APIRouter(prefix="/api/public", tags=["Public"])


# Rate limiting storage (in-memory for Phase-1, use Redis in production)
rate_limit_store = {}


def check_rate_limit(identifier: str, limit: int = 10, window: int = 60) -> bool:
    """
    Simple rate limiter. Returns True if allowed, False if rate limited.
    identifier: IP or unique key
    limit: max requests per window
    window: time window in seconds
    """
    now = time.time()
    key = f"rate:{identifier}"
    
    if key not in rate_limit_store:
        rate_limit_store[key] = []
    
    # Clean old entries
    rate_limit_store[key] = [t for t in rate_limit_store[key] if now - t < window]
    
    if len(rate_limit_store[key]) >= limit:
        return False
    
    rate_limit_store[key].append(now)
    return True


class PublicApplicationCreate(BaseModel):
    """Public job application without login"""
    job_id: str
    email: EmailStr
    name: str
    phone: Optional[str] = None
    cover_letter: Optional[str] = None
    # Honeypot field - should be empty
    website: Optional[str] = None
    # Turnstile token for bot protection
    turnstile_token: Optional[str] = None


def calculate_career_stability(experience: List[Dict]) -> Dict:
    """
    Calculate career stability based on job tenure.
    Returns: {score: 'green'|'yellow'|'red', quick_changes: int, tooltip: str}
    
    Rules:
    - Green: 0-1 quick changes (≤1 year tenure)
    - Yellow: 2-3 quick changes
    - Red: More than 3 quick changes
    """
    if not experience:
        return {"score": "green", "quick_changes": 0, "tooltip": "No work history available"}
    
    quick_changes = 0
    
    for job in experience:
        duration = job.get("duration", "").lower()
        
        # Parse duration to check if ≤1 year
        is_quick = False
        if "month" in duration:
            # Extract months
            months_match = re.search(r'(\d+)\s*month', duration)
            if months_match:
                months = int(months_match.group(1))
                if months <= 12:
                    is_quick = True
        elif "year" in duration:
            years_match = re.search(r'(\d+)\s*year', duration)
            if years_match:
                years = int(years_match.group(1))
                if years < 1:
                    is_quick = True
        elif any(term in duration for term in ["present", "current", "ongoing"]):
            # Current job, don't count
            pass
        else:
            # Unknown format, assume not quick
            pass
        
        if is_quick:
            quick_changes += 1
    
    if quick_changes <= 1:
        return {
            "score": "green",
            "quick_changes": quick_changes,
            "tooltip": f"Stable career history ({quick_changes} short tenure)"
        }
    elif quick_changes <= 3:
        return {
            "score": "yellow",
            "quick_changes": quick_changes,
            "tooltip": f"Moderate job changes ({quick_changes} short tenures)"
        }
    else:
        return {
            "score": "red",
            "quick_changes": quick_changes,
            "tooltip": f"Frequent job changes ({quick_changes} short tenures)"
        }


@public_router.get("/jobs")
async def get_public_jobs(
    search: Optional[str] = None,
    location: Optional[str] = None,
    job_type: Optional[str] = None,
    limit: int = 50
):
    """
    Get active job listings (PUBLIC - NO AUTH REQUIRED).
    For careers page on public website.
    
    VISIBILITY RULES:
    - Only jobs with career_page_status = "live" are visible
    - Only jobs with shareable_link_enabled = true are visible
    
    CLIENT PRIVACY: Returns public_company_alias instead of real company name.
    """
    query = {
        "status": "active",
        "career_page_status": "live",
        "shareable_link_enabled": True
    }
    
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"department": {"$regex": search, "$options": "i"}}
        ]
    
    if location:
        query["location"] = {"$regex": location, "$options": "i"}
    
    if job_type:
        query["job_type"] = job_type
    
    jobs = await db.jobs.find(query, {"_id": 0}).limit(limit).to_list(limit)
    
    # CLIENT PRIVACY: Sanitize response for public view
    sanitized_jobs = []
    for job in jobs:
        sanitized_jobs.append({
            "id": job.get("id"),
            "job_public_id": job.get("job_public_id"),
            "title": job.get("title"),
            "description": job.get("description"),
            "requirements": job.get("requirements"),
            "location": job.get("location"),
            "job_type": job.get("job_type"),
            "department": job.get("department"),
            "salary_min": job.get("salary_min"),
            "salary_max": job.get("salary_max"),
            "skills": job.get("skills", []),
            "experience_min": job.get("experience_min"),
            "experience_max": job.get("experience_max"),
            "company_name": job.get("public_company_alias") or "Confidential Client",
            "created_at": job.get("created_at")
        })
    
    return sanitized_jobs


@public_router.get("/jobs/{job_id}")
async def get_public_job_detail(job_id: str):
    """
    Get single job detail (PUBLIC - NO AUTH REQUIRED).
    Supports lookup by internal ID or job_public_id (VHC/YYYY/NNNN).
    
    VISIBILITY RULES:
    - Only jobs with career_page_status = "live" are visible
    - Only jobs with shareable_link_enabled = true are visible
    
    CLIENT PRIVACY: Returns public_company_alias instead of real company name.
    """
    # Support lookup by either internal ID or job_public_id
    job = await db.jobs.find_one({
        "$or": [
            {"id": job_id},
            {"job_public_id": job_id}
        ],
        "status": "active",
        "career_page_status": "live",
        "shareable_link_enabled": True
    }, {"_id": 0})
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # CLIENT PRIVACY: Return only public-safe fields
    return {
        "id": job.get("id"),
        "job_public_id": job.get("job_public_id"),
        "title": job.get("title"),
        "description": job.get("description"),
        "requirements": job.get("requirements"),
        "location": job.get("location"),
        "job_type": job.get("job_type"),
        "department": job.get("department"),
        "salary_min": job.get("salary_min"),
        "salary_max": job.get("salary_max"),
        "skills": job.get("skills", []),
        "experience_min": job.get("experience_min"),
        "experience_max": job.get("experience_max"),
        "company_name": job.get("public_company_alias") or "Confidential Client",
        "created_at": job.get("created_at")
    }


@public_router.get("/mandate/{job_id}")
async def get_mandate_job_detail(job_id: str, token: str):
    """
    Get single job detail via mandate shareable link (PUBLIC - NO AUTH REQUIRED).
    Supports lookup by internal ID or job_public_id (VHC/YYYY/NNNN).
    
    SECURITY: Requires valid mandate_share_token to access.
    This endpoint BYPASSES career page visibility requirements.
    
    Use case: Sharing jobs that are not on the public career page,
    such as assigned mandates or confidential searches.
    """
    if not token:
        raise HTTPException(status_code=400, detail="Share token is required")
    
    # Support lookup by either internal ID or job_public_id
    job = await db.jobs.find_one({
        "$or": [
            {"id": job_id},
            {"job_public_id": job_id}
        ],
        "status": "active",
        "mandate_shareable_link_enabled": True,
        "mandate_share_token": token
    }, {"_id": 0})
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or link is invalid/expired")
    
    # Return public-safe fields (same as career page job detail)
    return {
        "id": job.get("id"),
        "job_public_id": job.get("job_public_id"),
        "title": job.get("title"),
        "description": job.get("description"),
        "requirements": job.get("requirements"),
        "location": job.get("location"),
        "job_type": job.get("job_type"),
        "department": job.get("department"),
        "salary_min": job.get("salary_min"),
        "salary_max": job.get("salary_max"),
        "skills": job.get("skills", []),
        "experience_min": job.get("experience_min"),
        "experience_max": job.get("experience_max"),
        "company_name": job.get("public_company_alias") or "Confidential Client",
        "created_at": job.get("created_at"),
        "is_mandate_link": True  # Flag to differentiate from career page links
    }


@public_router.post("/parse-resume")
async def public_parse_resume(
    request: Request,
    resume: UploadFile = File(...),
    website: Optional[str] = Form(None),  # Honeypot
):
    """
    Parse resume and return extracted data for review (NO LOGIN REQUIRED).
    Step 1 of two-step apply flow.
    """
    # Get client IP for rate limiting
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    
    # Rate limit: 10 parses per minute per IP
    if not check_rate_limit(f"parse:{client_ip}", limit=10, window=60):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    
    # Honeypot check
    if website:
        logger.warning(f"[BOT] Honeypot triggered from {client_ip}")
        return {"success": True, "parsed_data": {}}
    
    # Save resume file temporarily
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    filename = f"temp_{timestamp}_{resume.filename}"
    upload_dir = Path("/app/uploads")
    upload_dir.mkdir(exist_ok=True)
    
    file_path = upload_dir / filename
    async with aiofiles.open(file_path, 'wb') as f:
        content = await resume.read()
        await f.write(content)
    
    # Extract resume text
    resume_text = ""
    try:
        if filename.lower().endswith('.pdf'):
            doc = fitz.open(str(file_path))
            for page in doc:
                resume_text += page.get_text()
            doc.close()
        elif filename.lower().endswith('.txt'):
            async with aiofiles.open(file_path, 'r', errors='ignore') as f:
                resume_text = await f.read()
    except Exception as e:
        logger.error(f"[PARSE] Resume text extraction failed: {e}")
    
    # Parse resume with AI
    parsed_data = {}
    try:
        from services.matching_engine import parse_resume_with_ai
        result = await parse_resume_with_ai(resume_text[:8000])
        if result.get("success"):
            parsed_data = result.get("data", {})
    except Exception as e:
        logger.error(f"[PARSE] AI parsing failed: {e}")
    
    # Calculate career stability
    career_stability = calculate_career_stability(parsed_data.get("experience", []))
    
    return {
        "success": True,
        "parsed_data": {
            "name": parsed_data.get("name"),
            "email": parsed_data.get("email"),
            "phone": parsed_data.get("phone"),
            "headline": parsed_data.get("headline"),
            "summary": parsed_data.get("summary"),
            "skills": parsed_data.get("skills", []),
            "experience_years": parsed_data.get("experience_years", 0),
            "experience": parsed_data.get("experience", []),
            "education": parsed_data.get("education", []),
            "location": parsed_data.get("location"),
            "certifications": parsed_data.get("certifications", [])
        },
        "career_stability": career_stability,
        "resume_filename": filename,
        "resume_url": f"/api/uploads/{filename}"
    }


@public_router.post("/apply")
async def public_apply(
    request: Request,
    job_id: str = Form(...),
    email: str = Form(...),
    name: str = Form(...),
    phone: Optional[str] = Form(None),
    cover_letter: Optional[str] = Form(None),
    current_salary: Optional[int] = Form(None),  # INR - from review step
    notice_period: Optional[str] = Form(None),  # e.g., "30 days", "2 weeks", "immediate"
    skills: Optional[str] = Form(None),  # Comma-separated, edited by candidate
    experience_years: Optional[int] = Form(None),  # Candidate-corrected value
    location: Optional[str] = Form(None),  # Candidate-corrected value
    headline: Optional[str] = Form(None),  # Candidate-corrected value
    resume: UploadFile = File(None),  # Optional if resume_filename provided from parse step
    resume_filename: Optional[str] = Form(None),  # From /public/parse-resume step
    website: Optional[str] = Form(None),  # Honeypot
    turnstile_token: Optional[str] = Form(None),
    consent_given: Optional[str] = Form(None),  # Must be "true" for consent
    mandate_token: Optional[str] = Form(None)  # Optional: for mandate shareable links
):
    """
    Public job application (NO LOGIN REQUIRED).
    Supports two-step apply flow:
    - Step 1: Candidate uploads resume via /public/parse-resume, gets parsed data
    - Step 2: Candidate reviews/edits data, adds salary & notice period, then submits here
    
    CONSENT REQUIRED: consent_given must be "true" to process application.
    
    Can also accept direct resume upload for single-step apply.
    """
    # Get client IP for rate limiting and consent tracking
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    
    # Rate limit: 5 applications per minute per IP
    if not check_rate_limit(f"apply:{client_ip}", limit=5, window=60):
        raise HTTPException(status_code=429, detail="Too many applications. Please try again later.")
    
    # CONSENT VALIDATION (MANDATORY)
    if consent_given != "true":
        raise HTTPException(
            status_code=400, 
            detail="Consent is required to submit your application. Please agree to the data processing terms."
        )
    
    # Honeypot check - if website field is filled, it's a bot
    if website:
        logger.warning(f"[BOT] Honeypot triggered from {client_ip}")
        # Return success to not tip off bots, but don't process
        return {"success": True, "message": "Application submitted successfully", "application_id": str(uuid.uuid4())}
    
    # Verify job exists AND is publicly accessible
    # Support two access paths:
    # 1. Career page link: career_page_status = "live" AND shareable_link_enabled = True
    # 2. Mandate link: mandate_shareable_link_enabled = True AND valid mandate_token
    
    job = None
    application_source = "career_page"
    
    if mandate_token:
        # Mandate link access - bypasses career page requirement
        job = await db.jobs.find_one({
            "$or": [{"id": job_id}, {"job_public_id": job_id}],
            "status": "active",
            "mandate_shareable_link_enabled": True,
            "mandate_share_token": mandate_token
        }, {"_id": 0})
        if job:
            application_source = "mandate_link"
    
    if not job:
        # Try career page access
        job = await db.jobs.find_one({
            "$or": [{"id": job_id}, {"job_public_id": job_id}],
            "status": "active",
            "career_page_status": "live",
            "shareable_link_enabled": True
        }, {"_id": 0})
        application_source = "career_page"
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or no longer accepting applications")
    
    # Use internal job ID for application
    internal_job_id = job.get("id")
    
    # Validate email
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        raise HTTPException(status_code=400, detail="Invalid email address")
    
    # Store consent metadata
    consent_metadata = {
        "consent_given": True,
        "consent_timestamp": datetime.now(timezone.utc).isoformat(),
        "consent_ip_address": client_ip,
        "consent_policy_version": "v1.0_2026",
        "consent_text": "I consent to Ventures HRD collecting and processing my personal data including resume, contact details, and professional information for recruitment purposes under the Digital Personal Data Protection Act, 2023. I understand I can withdraw consent at any time."
    }
    
    # Handle resume - either from parse step or new upload
    upload_dir = Path("/app/uploads")
    upload_dir.mkdir(exist_ok=True)
    filename = None
    resume_text = ""
    parsed_data = {}
    r2_metadata = None  # R2 storage metadata (populated if R2 upload succeeds)
    
    if resume_filename:
        # Two-step flow: resume was already parsed, use the existing file
        file_path = upload_dir / resume_filename
        if not file_path.exists():
            raise HTTPException(status_code=400, detail="Resume file not found. Please re-upload your resume.")
        filename = resume_filename
        
        # Use candidate-provided data from review step (already corrected by candidate)
        parsed_data = {
            "name": name,
            "email": email,
            "phone": phone,
            "headline": headline,
            "skills": [s.strip() for s in skills.split(",")] if skills else [],
            "experience_years": experience_years or 0,
            "location": location
        }
        
        # Extract resume text for storage
        try:
            if filename.lower().endswith('.pdf'):
                doc = fitz.open(str(file_path))
                for page in doc:
                    resume_text += page.get_text()
                doc.close()
            elif filename.lower().endswith('.txt'):
                async with aiofiles.open(file_path, 'r', errors='ignore') as f:
                    resume_text = await f.read()
        except Exception as e:
            logger.error(f"[PUBLIC APPLY] Resume text extraction failed: {e}")
    elif resume:
        # Single-step flow: new resume upload, parse it now
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        safe_email = email.replace('@', '_at_').replace('.', '_')
        filename = f"public_{safe_email}_{timestamp}_{resume.filename}"
        
        # Read file content once
        content = await resume.read()
        
        # Save locally first (needed for text extraction)
        file_path = upload_dir / filename
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        
        # Upload to R2 if enabled (async, for permanent storage)
        r2_metadata = None
        if R2_ENABLED:
            try:
                r2_key = generate_r2_key("applications", resume.filename)
                r2_result = await upload_to_r2(content, r2_key, resume.content_type or "application/octet-stream")
                if r2_result.get("storage") == "r2":
                    r2_metadata = {
                        "storage": "r2",
                        "r2_key": r2_key,
                        "original_filename": resume.filename,
                        "filename": filename,
                        "content_type": resume.content_type,
                        "uploaded_at": datetime.now(timezone.utc).isoformat(),
                        "uploaded_by_role": "public"
                    }
                    logging.info(f"[R2] Resume uploaded to R2: {r2_key}")
            except Exception as e:
                logging.error(f"[R2] Upload failed, using local storage: {e}")
        
        # Extract resume text
        try:
            if filename.lower().endswith('.pdf'):
                doc = fitz.open(str(file_path))
                for page in doc:
                    resume_text += page.get_text()
                doc.close()
            elif filename.lower().endswith('.txt'):
                async with aiofiles.open(file_path, 'r', errors='ignore') as f:
                    resume_text = await f.read()
        except Exception as e:
            logger.error(f"[PUBLIC APPLY] Resume text extraction failed: {e}")
        
        # Parse resume with AI
        try:
            from services.matching_engine import parse_resume_with_ai
            result = await parse_resume_with_ai(resume_text[:8000])
            if result.get("success"):
                parsed_data = result.get("data", {})
        except Exception as e:
            logger.error(f"[PUBLIC APPLY] AI parsing failed: {e}")
    else:
        raise HTTPException(status_code=400, detail="Resume is required. Please upload a resume file.")
    
    # Check if candidate already exists in data bank
    existing_candidate = await db.candidate_bank.find_one({
        "$or": [
            {"email": email},
            {"phone": phone} if phone else {"email": email}
        ]
    }, {"_id": 0})
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Prepare skills list (from candidate-edited or parsed data)
    final_skills = parsed_data.get("skills", [])
    if skills and isinstance(skills, str):
        final_skills = [s.strip() for s in skills.split(",") if s.strip()]
    
    if existing_candidate:
        candidate_id = existing_candidate["id"]
        # Update with new data
        update_data = {
            "skills": final_skills or existing_candidate.get("skills", []),
            "experience_years": experience_years if experience_years is not None else existing_candidate.get("experience_years", 0),
            "current_salary": current_salary,
            "notice_period": notice_period,
            "updated_at": now
        }
        if location:
            update_data["location"] = location
        if headline:
            update_data["headline"] = headline
        if filename:
            update_data["resume_url"] = f"/api/uploads/{filename}"
        # Add R2 metadata if available
        if r2_metadata:
            update_data["r2_metadata"] = r2_metadata
        
        await db.candidate_bank.update_one(
            {"id": candidate_id},
            {"$set": update_data}
        )
    else:
        # Create new candidate in data bank
        candidate_id = str(uuid.uuid4())
        candidate_doc = {
            "id": candidate_id,
            "name": parsed_data.get("name") or name,
            "email": email,
            "phone": parsed_data.get("phone") or phone,
            "headline": headline or parsed_data.get("headline"),
            "summary": parsed_data.get("summary"),
            "skills": final_skills,
            "experience_years": experience_years if experience_years is not None else parsed_data.get("experience_years", 0),
            "experience": parsed_data.get("experience", []),
            "education": parsed_data.get("education", []),
            "location": location or parsed_data.get("location"),
            "current_salary": current_salary,  # INR
            "notice_period": notice_period,
            "source": "public_application",
            "source_job_id": job_id,
            "resume_url": f"/api/uploads/{filename}" if filename else None,
            "resume_text": resume_text[:5000],
            "is_active": True,
            "linked_user_id": None,  # Not linked to any user account
            "r2_metadata": r2_metadata,  # R2 storage metadata (None if local storage)
            "created_at": now,
            "updated_at": now
        }
        await db.candidate_bank.insert_one(candidate_doc)
    
    # Create application with salary and notice period
    application_id = str(uuid.uuid4())
    application_doc = {
        "id": application_id,
        "job_id": internal_job_id,
        "job_public_id": job.get("job_public_id"),
        "candidate_id": candidate_id,
        # IMPORTANT: User-provided form data takes priority over AI-parsed data
        "candidate_name": name or parsed_data.get("name"),
        "candidate_email": email,
        "candidate_phone": phone or parsed_data.get("phone"),
        "resume_url": f"/api/uploads/{filename}" if filename else None,
        "r2_metadata": r2_metadata,  # R2 storage metadata (None if local storage)
        "cover_letter": cover_letter,
        "current_salary": current_salary,  # INR
        "notice_period": notice_period,
        "skills": final_skills,
        "experience_years": experience_years if experience_years is not None else parsed_data.get("experience_years", 0),
        "location": location or parsed_data.get("location"),
        "headline": headline or parsed_data.get("headline"),
        "stage": "applied",
        "source": "public_website",
        "application_channel": application_source,  # "career_page" or "mandate_link"
        "notes": [],
        # Consent tracking metadata
        "consent": consent_metadata,
        "applied_at": now,
        "updated_at": now
    }
    await db.applications.insert_one(application_doc)
    
    # Update job applicant count
    await db.jobs.update_one({"id": internal_job_id}, {"$inc": {"applicant_count": 1}})
    
    logger.info(f"[PUBLIC APPLY] New application from {email} for job {job.get('job_public_id')} ({internal_job_id})")
    
    return {
        "success": True,
        "message": "Application submitted successfully! We'll review your profile and get back to you.",
        "redirect_to": "/application-success"
    }


@public_router.post("/upload-resume")
async def public_upload_resume(
    request: Request,
    email: str = Form(...),
    name: str = Form(...),
    phone: Optional[str] = Form(None),
    resume: UploadFile = File(...),
    website: Optional[str] = Form(None),  # Honeypot
):
    """
    Public resume upload to candidate data bank (NO LOGIN REQUIRED).
    For candidates who want to be in the talent pool without applying to specific job.
    """
    # Get client IP for rate limiting
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    
    # Rate limit: 3 uploads per hour per IP
    if not check_rate_limit(f"upload:{client_ip}", limit=3, window=3600):
        raise HTTPException(status_code=429, detail="Too many uploads. Please try again later.")
    
    # Honeypot check
    if website:
        logger.warning(f"[BOT] Honeypot triggered from {client_ip}")
        return {"success": True, "message": "Resume uploaded successfully"}
    
    # Save and process similar to apply
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    safe_email = email.replace('@', '_at_').replace('.', '_')
    filename = f"pool_{safe_email}_{timestamp}_{resume.filename}"
    upload_dir = Path("/app/uploads")
    upload_dir.mkdir(exist_ok=True)
    
    file_path = upload_dir / filename
    async with aiofiles.open(file_path, 'wb') as f:
        content = await resume.read()
        await f.write(content)
    
    # Extract and parse
    resume_text = ""
    try:
        if filename.lower().endswith('.pdf'):
            doc = fitz.open(str(file_path))
            for page in doc:
                resume_text += page.get_text()
            doc.close()
        elif filename.lower().endswith('.txt'):
            async with aiofiles.open(file_path, 'r', errors='ignore') as f:
                resume_text = await f.read()
    except Exception as e:
        logger.error(f"Resume extraction failed: {e}")
    
    parsed_data = {}
    try:
        from services.matching_engine import parse_resume_with_ai
        result = await parse_resume_with_ai(resume_text[:8000])
        if result.get("success"):
            parsed_data = result.get("data", {})
    except Exception as e:
        logger.error(f"AI parsing failed: {e}")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Check existing
    existing = await db.candidate_bank.find_one({"email": email}, {"_id": 0})
    if existing:
        candidate_id = existing["id"]
        await db.candidate_bank.update_one(
            {"id": candidate_id},
            {"$set": {
                "name": parsed_data.get("name") or name,
                "skills": parsed_data.get("skills", existing.get("skills", [])),
                "experience_years": parsed_data.get("experience_years", existing.get("experience_years", 0)),
                "resume_url": f"/api/uploads/{filename}",
                "updated_at": now
            }}
        )
    else:
        candidate_id = str(uuid.uuid4())
        candidate_doc = {
            "id": candidate_id,
            "name": parsed_data.get("name") or name,
            "email": email,
            "phone": parsed_data.get("phone") or phone,
            "headline": parsed_data.get("headline"),
            "summary": parsed_data.get("summary"),
            "skills": parsed_data.get("skills", []),
            "experience_years": parsed_data.get("experience_years", 0),
            "experience": parsed_data.get("experience", []),
            "education": parsed_data.get("education", []),
            "location": parsed_data.get("location"),
            "source": "talent_pool_upload",
            "resume_url": f"/api/uploads/{filename}",
            "resume_text": resume_text[:5000],
            "is_active": True,
            "linked_user_id": None,
            "created_at": now,
            "updated_at": now
        }
        await db.candidate_bank.insert_one(candidate_doc)
    
    return {
        "success": True,
        "message": "Resume uploaded to our talent pool! We'll reach out when matching opportunities arise.",
        "candidate_id": candidate_id,
        "parsed_skills": parsed_data.get("skills", [])[:5]
    }
