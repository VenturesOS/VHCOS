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
    """Save an AI-parsed CV profile to the candidate bank."""
    
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
    
    # Build visibility
    visibility = {"employer_ids": [], "recruiter_ids": [], "team_ids": []}
    if current_user["role"] == "employer":
        visibility["employer_ids"].append(current_user["id"])
    elif current_user["role"] == "recruiter":
        visibility["recruiter_ids"].append(current_user["id"])
        if current_user.get("company_id"):
            visibility["employer_ids"].append(current_user["company_id"])
    elif current_user["role"] == "admin":
        visibility["employer_ids"].append(current_user["id"])
    
    doc = {
        "id": candidate_id,
        "name": name.strip(),
        "first_name": name.strip().split()[0] if name.strip() else None,
        "last_name": name.strip().split()[-1] if name.strip() and len(name.strip().split()) > 1 else None,
        "email": (profile.get("email") or "").lower().strip() or None,
        "phone": profile.get("phone"),
        "current_company": profile.get("current_company"),
        "current_designation": profile.get("current_designation"),
        "current_industry": profile.get("current_industry"),
        "total_experience_years": profile.get("total_experience_years"),
        "headline": profile.get("headline"),
        "profile_summary": profile.get("profile_summary"),
        "location": profile.get("location"),
        "preferred_locations": profile.get("preferred_locations", []),
        "date_of_birth": profile.get("date_of_birth"),
        "gender": profile.get("gender"),
        "key_skills": profile.get("key_skills", []),
        "it_skills": profile.get("it_skills", []),
        "work_experience": profile.get("work_experience", []),
        "education": profile.get("education", []),
        "certifications": profile.get("certifications", []),
        "projects": profile.get("projects", []),
        "languages": profile.get("languages", []),
        "online_profiles": profile.get("online_profiles", []),
        "source": "cv_upload",
        "source_details": {
            "upload_method": "cv_upload",
            "filename": data.get("filename", "unknown"),
            "captured_by": current_user["id"],
            "captured_by_email": current_user.get("email"),
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
