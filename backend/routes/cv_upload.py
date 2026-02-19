"""
CV Upload → AI-Parsed Candidate Profile
"""
import uuid
import os
import json as json_module
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from config import db
from utils import require_role

logger = logging.getLogger(__name__)
cv_upload_router = APIRouter(prefix="/api", tags=["CV Upload"])


@cv_upload_router.post("/cv-upload/parse")
async def parse_cv(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Upload a CV (PDF/DOCX), extract text, parse with AI, return structured profile."""
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ('pdf', 'docx', 'doc'):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")
    
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")
    
    # Extract text from file
    raw_text = ""
    if ext == 'pdf':
        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            for page in doc:
                raw_text += page.get_text()
            doc.close()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to read PDF: {str(e)}")
    elif ext in ('docx', 'doc'):
        try:
            import io
            from docx import Document
            doc = Document(io.BytesIO(content))
            raw_text = "\n".join([p.text for p in doc.paragraphs])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to read DOCX: {str(e)}")
    
    if len(raw_text.strip()) < 50:
        raise HTTPException(status_code=400, detail="Could not extract enough text from the file")
    
    # Parse with AI
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="AI service not configured")
    
    raw_text_truncated = raw_text[:12000]
    
    prompt = f"""You are a resume/CV parsing expert. Extract structured candidate data from this resume.

Return a JSON object with these fields (use null for missing data):

{{
  "name": "Full name",
  "email": "email address or null",
  "phone": "phone number or null",
  "current_company": "current employer or null",
  "current_designation": "current job title or null",
  "current_industry": "industry sector or null",
  "total_experience_years": number or null,
  "headline": "professional headline or null",
  "profile_summary": "summary/objective text or null",
  "location": "current city or null",
  "preferred_locations": ["city1", "city2"],
  "date_of_birth": "DOB or null",
  "gender": "Male/Female/Other or null",
  "key_skills": ["skill1", "skill2"],
  "it_skills": [{{"name": "skill", "version": "ver", "experience_years": num}}],
  "work_experience": [{{"company": "name", "designation": "title", "from_date": "date", "to_date": "date or null", "is_current": boolean, "description": "description"}}],
  "education": [{{"degree": "degree", "institution": "college/university", "year_of_passing": "year", "specialization": "field"}}],
  "certifications": [{{"name": "cert name"}}],
  "projects": [{{"title": "project", "description": "desc"}}],
  "languages": [{{"language": "name", "proficiency": "level"}}],
  "online_profiles": [{{"platform": "LinkedIn/GitHub", "url": "url"}}]
}}

IMPORTANT:
- Convert experience to decimal (5 years 6 months = 5.5)
- Extract ALL work experiences, education, skills
- Return ONLY valid JSON

Resume text:
{raw_text_truncated}"""

    try:
        from services.llm_service import chat_completion
        content = await chat_completion(
            system_prompt="You are a precise resume parser. Extract structured candidate data from resumes. Return only valid JSON.",
            user_prompt=prompt,
            temperature=0.1,
            json_mode=True,
            timeout=30.0,
        )
        
        profile_data = json_module.loads(content)
        
        logger.info(f"[CV Parse] Extracted: {profile_data.get('name')}")
        return {"success": True, "profile_data": profile_data, "filename": file.filename}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CV Parse] Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to parse CV")


@cv_upload_router.post("/cv-upload/save")
async def save_cv_profile(
    data: dict,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Save an AI-parsed CV profile to the candidate bank.
    Maps to the UNIFIED candidate schema (identical to extension capture).
    Missing fields remain null — never fabricated or inferred.
    """
    
    profile = data.get("profile", {})
    name = profile.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    
    # Check for duplicate by name + source
    import re
    name_regex = re.compile(f"^{re.escape(name.strip())}$", re.IGNORECASE)
    existing = await db.candidate_bank.find_one(
        {"name": name_regex, "source": "cv_upload"}, {"_id": 0}
    )
    
    # Also check by email
    if not existing and profile.get("email"):
        existing = await db.candidate_bank.find_one(
            {"email": profile["email"].lower().strip()}, {"_id": 0}
        )
    
    now = datetime.now(timezone.utc).isoformat()
    candidate_id = existing["id"] if existing else str(uuid.uuid4())
    action = "updated" if existing else "created"
    
    # Build visibility (reuse extension pattern)
    from routes.extension import build_team_visibility, normalize_phone
    visibility_data = await build_team_visibility(current_user)
    visibility = visibility_data.get("visibility", {"employer_ids": [], "recruiter_ids": []})
    
    # Parse name parts
    name_parts = name.strip().split()
    first_name = name_parts[0] if name_parts else None
    last_name = name_parts[-1] if len(name_parts) > 1 else None
    middle_name = " ".join(name_parts[1:-1]) if len(name_parts) > 2 else None
    
    # Extract work experience
    work_exp = profile.get("work_experience") or []
    
    # Determine current employment from experience
    current_from_exp = {}
    for exp in work_exp:
        if isinstance(exp, dict) and exp.get("is_current"):
            current_from_exp = exp
            break
    
    # Extract education
    education = profile.get("education") or []
    highest_qual = None
    highest_degree = None
    if education:
        first_edu = education[0] if isinstance(education[0], dict) else {}
        highest_qual = first_edu.get("degree")
        highest_degree = first_edu.get("specialization") or first_edu.get("degree")
    
    # Extract certifications — normalize to [{name: ...}] format
    raw_certs = profile.get("certifications") or []
    certs_list = []
    certs_detailed = []
    for c in raw_certs:
        if isinstance(c, dict):
            cert_name = c.get("name") or c.get("title") or ""
            if cert_name:
                certs_list.append(cert_name)
                certs_detailed.append(c)
        elif isinstance(c, str) and c:
            certs_list.append(c)
            certs_detailed.append({"name": c})
    
    # Extract online profiles for linkedin/github
    online_profiles = profile.get("online_profiles") or []
    linkedin_url = None
    github_url = None
    for op in online_profiles:
        if isinstance(op, dict):
            platform = (op.get("platform") or "").lower()
            url = op.get("url") or ""
            if "linkedin" in platform and url:
                linkedin_url = url
            elif "github" in platform and url:
                github_url = url
    
    phone = profile.get("phone")
    email = (profile.get("email") or "").lower().strip() or None
    
    # Build UNIFIED candidate document — matching extension schema exactly
    doc = {
        "id": candidate_id,
        
        # === BASIC INFO ===
        "name": name.strip(),
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "photo_url": None,
        
        # === CONTACT ===
        "email": email,
        "alternate_email": None,
        "phone": phone,
        "phone_normalized": normalize_phone(phone) if phone else None,
        "alternate_phone": None,
        
        # === PROFESSIONAL IDENTITY ===
        "headline": profile.get("headline"),
        "resume_headline": profile.get("headline"),
        "summary": profile.get("profile_summary"),
        
        # === CURRENT EMPLOYMENT ===
        "current_employer": profile.get("current_company") or current_from_exp.get("company"),
        "designation": profile.get("current_designation") or current_from_exp.get("designation"),
        "department": None,
        "industry": profile.get("current_industry"),
        "role_category": None,
        "employment_status": None,
        
        # === EXPERIENCE ===
        "experience_years": int(profile.get("total_experience_years") or 0) if profile.get("total_experience_years") else None,
        "experience_months": None,
        "experience_display": f"{profile.get('total_experience_years')} years" if profile.get("total_experience_years") else None,
        "experience": work_exp,
        
        # === EDUCATION ===
        "highest_qualification": highest_qual,
        "highest_degree": highest_degree,
        "education": education,
        
        # === SKILLS ===
        "skills": profile.get("key_skills") or [],
        "skills_display": ", ".join(profile.get("key_skills") or []),
        "it_skills": profile.get("it_skills") or [],
        "soft_skills": [],
        "tools": [],
        
        # === CERTIFICATIONS ===
        "certifications": certs_list,
        "certifications_detailed": certs_detailed,
        
        # === PROJECTS ===
        "projects": profile.get("projects") or [],
        
        # === LANGUAGES ===
        "languages": profile.get("languages") or [],
        
        # === ONLINE PROFILES ===
        "online_profiles": online_profiles,
        "linkedin_url": linkedin_url,
        "github_url": github_url,
        "portfolio_url": None,
        
        # === PERSONAL DETAILS ===
        "date_of_birth": profile.get("date_of_birth"),
        "age": None,
        "gender": profile.get("gender"),
        "marital_status": None,
        "nationality": None,
        "has_passport": False,
        "passport_number": None,
        "passport_expiry": None,
        
        # Address
        "permanent_address": None,
        "permanent_city": None,
        "permanent_state": None,
        "permanent_country": None,
        "permanent_pincode": None,
        "current_address": None,
        "current_city": None,
        "current_state": None,
        "current_country": None,
        "current_pincode": None,
        
        # Category
        "category": None,
        "differently_abled": False,
        "disability_type": None,
        
        # Work Permit
        "work_permit_usa": None,
        "work_permit_other": None,
        
        # === CAREER PREFERENCES ===
        "current_salary": None,
        "current_salary_currency": "INR",
        "current_salary_breakdown": None,
        "expected_salary": None,
        "expected_salary_currency": "INR",
        "expected_salary_min": None,
        "expected_salary_max": None,
        
        "notice_period": None,
        "notice_period_days": None,
        "is_serving_notice": False,
        "last_working_day": None,
        "notice_negotiable": False,
        
        "location": profile.get("location"),
        "preferred_locations": profile.get("preferred_locations") or [],
        "willing_to_relocate": False,
        "relocation_preferences": [],
        
        "preferred_job_type": [],
        "preferred_employment_type": [],
        "preferred_shift": [],
        "work_from_home": False,
        "remote_work_preference": None,
        
        "preferred_industry": [],
        "preferred_functional_area": [],
        "preferred_role": [],
        "preferred_role_category": [],
        
        "preferred_company_type": [],
        "preferred_company_size": None,
        "companies_to_avoid": [],
        
        # === ADDITIONAL ===
        "accomplishments": None,
        "about_me": None,
        "additional_info": None,
        
        # === RESUME ===
        "has_resume": True,
        "resume_title": data.get("filename"),
        "resume_format": None,
        
        # === SOURCE TRACKING ===
        "source": "cv_upload",
        "source_details": {
            "upload_method": "cv_upload",
            "filename": data.get("filename", "unknown"),
            "captured_by": current_user["id"],
            "captured_by_name": current_user.get("name", current_user.get("email")),
            "captured_by_email": current_user.get("email"),
            "captured_at": now,
        },
        "visibility": visibility,
        "created_by": current_user["id"],
        "updated_at": now,
    }
    
    if existing:
        await db.candidate_bank.update_one({"id": candidate_id}, {"$set": doc})
    else:
        doc["created_at"] = now
        await db.candidate_bank.insert_one(doc)
    
    # Remove _id before returning
    doc.pop("_id", None)
    
    return {"success": True, "action": action, "candidate_id": candidate_id, "profile": doc}
