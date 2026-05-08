"""
CV Upload → AI-Parsed Candidate Profile
"""
import uuid
import os
import re
import json as json_module
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from config import db
from utils import require_role

logger = logging.getLogger(__name__)
cv_upload_router = APIRouter(prefix="/api", tags=["CV Upload"])

# ── Admin-only test accounts for cost-optimized extraction ──────────────────
_COST_OPT_EMAILS = {"admin@vhc.in"}


def _regex_extract_profile(text: str) -> dict:
    """Extract structured CV fields using regex patterns. Works well for Naukri-formatted text."""
    profile = {}

    # Name — first non-empty line that looks like a name (2-4 capitalized words)
    for line in text.split("\n"):
        line = line.strip()
        if line and 2 <= len(line.split()) <= 5 and not any(c in line for c in "@./:"):
            words = line.split()
            if all(w[0].isupper() for w in words if w.isalpha()):
                profile["name"] = line
                break

    # Email
    emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', text)
    if emails:
        profile["email"] = emails[0].lower()

    # Phone
    phones = re.findall(r'(?:\+91[\s-]?)?(?:\d[\s-]?){10}', text)
    if phones:
        profile["phone"] = re.sub(r'[\s-]', '', phones[0])

    # Experience years
    exp_match = re.search(r'(\d+)\s*(?:years?|yrs?)[\s.]*(\d+)?\s*(?:months?|mos?)?', text, re.IGNORECASE)
    if exp_match:
        years = int(exp_match.group(1))
        months = int(exp_match.group(2)) if exp_match.group(2) else 0
        profile["total_experience_years"] = round(years + months / 12, 1)

    # Location — common patterns
    loc_match = re.search(r'(?:Location|City|Address)\s*[:\-]\s*(.+)', text, re.IGNORECASE)
    if loc_match:
        profile["location"] = loc_match.group(1).strip().split('\n')[0].strip()

    # Current company
    comp_match = re.search(r'(?:Current\s*(?:Company|Employer|Organization)|Working\s*(?:at|with))\s*[:\-]\s*(.+)', text, re.IGNORECASE)
    if comp_match:
        profile["current_company"] = comp_match.group(1).strip().split('\n')[0].strip()

    # Current designation
    desig_match = re.search(r'(?:Current\s*(?:Designation|Role|Title|Position)|Designation)\s*[:\-]\s*(.+)', text, re.IGNORECASE)
    if desig_match:
        profile["current_designation"] = desig_match.group(1).strip().split('\n')[0].strip()

    # Skills — Multiple strategies for Naukri-format CVs
    skills = []
    
    # Strategy 1: Look for explicit "Key Skills" or "Skills" section
    skills_match = re.search(r'(?:Key\s*Skills?|Technical\s*Skills?|Core\s*Competenc)\s*[:\-]\s*(.+?)(?:\n\n|\n[A-Z][a-z])', text, re.IGNORECASE | re.DOTALL)
    if skills_match:
        raw = skills_match.group(1)
        skills = [s.strip() for s in re.split(r'[,|•·\n]', raw) if s.strip() and len(s.strip()) > 2 and len(s.strip()) < 50]
    
    # Strategy 2: Naukri table format — short lines (2-5 words) at the start, before long paragraphs
    if len(skills) < 3:
        candidate_name = profile.get("name", "").lower()
        early_lines = text.split('\n')[:60]
        for line in early_lines:
            line = line.strip()
            if 3 < len(line) < 50 and 1 <= len(line.split()) <= 5:
                # Skip if it looks like a name, email, phone, date, or section header
                if any(c in line for c in '@./:'):
                    continue
                if re.match(r'^(Personal|Education|Experience|Summary|Objective|Address|Profile|IT\s*Skills|Career|CORE\s*COMP|Core\s*Comp)', line, re.IGNORECASE):
                    continue
                if re.match(r'^\d{2}[\-/]', line):  # dates
                    continue
                if re.match(r'^\+?\d[\d\s\-]{8,}$', line):  # phone
                    continue
                if candidate_name and line.lower().strip() == candidate_name.strip():
                    continue
                # Looks like a skill/competency
                if any(c.isalpha() for c in line):
                    skills.append(line)
    
    if skills:
        # Deduplicate while preserving order
        seen = set()
        unique_skills = []
        for s in skills:
            key = s.lower().strip()
            if key not in seen:
                seen.add(key)
                unique_skills.append(s)
        profile["key_skills"] = unique_skills[:20]

    return profile


async def _check_dedup(text: str) -> dict:
    """Check if a candidate with the same email/phone already exists. Returns existing profile or empty dict."""
    emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', text)
    phones = re.findall(r'(?:\+91[\s-]?)?(?:\d[\s-]?){10}', text)

    query_conditions = []
    if emails:
        query_conditions.append({"email": {"$regex": re.escape(emails[0]), "$options": "i"}})
    if phones:
        clean_phone = re.sub(r'[\s-]', '', phones[0])[-10:]  # last 10 digits
        query_conditions.append({"phone": {"$regex": clean_phone}})

    if not query_conditions:
        return {}

    existing = await db.candidates.find_one(
        {"$or": query_conditions},
        {"_id": 0, "name": 1, "email": 1, "phone": 1, "key_skills": 1,
         "total_experience_years": 1, "location": 1, "current_company": 1,
         "current_designation": 1, "current_industry": 1, "headline": 1,
         "profile_summary": 1, "preferred_locations": 1, "date_of_birth": 1,
         "gender": 1, "it_skills": 1, "work_experience": 1, "education": 1,
         "certifications": 1, "projects": 1, "languages": 1, "online_profiles": 1}
    )
    return existing or {}


@cv_upload_router.post("/cv-upload/parse", status_code=202)
async def parse_cv(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Upload a CV (PDF/DOCX). Returns a task_id immediately (202). Poll GET /cv-upload/parse/{task_id} for result."""
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ('pdf', 'docx', 'doc'):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")
    
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    # Security: validate file content (magic bytes + threat scan)
    from services.security_service import validate_upload as _sec_validate
    logger.info(f"[CV Parse] Security check for {file.filename}...")
    sec_check = await _sec_validate(content, file.filename, current_user.get("email", "internal"))
    if not sec_check["valid"]:
        raise HTTPException(status_code=400, detail=sec_check["reason"])
    
    # Create async task and process in background
    from services.async_tasks import create_task, fire_and_forget
    task_id = await create_task("cv_parse", current_user["id"], {"filename": file.filename})
    fire_and_forget(_do_parse_cv(task_id, content, file.filename))
    
    return {"task_id": task_id, "status": "processing", "message": "CV parsing started. Poll GET /cv-upload/parse/{task_id} for result."}


async def _do_parse_cv(task_id: str, content: bytes, filename: str):
    """Background worker: extract text + AI parse, then update task record."""
    from services.async_tasks import complete_task, fail_task
    try:
        import asyncio
        from services.matching_engine import extract_text_from_file

        logger.info(f"[CV Parse BG] Extracting text from {filename}...")
        loop = asyncio.get_event_loop()
        raw_text = await loop.run_in_executor(None, extract_text_from_file, content, filename)

        if not raw_text or len(raw_text.strip()) < 50:
            await fail_task(task_id, "Could not extract enough text from the file. It may be image-based, empty, or password-protected.")
            return

        raw_text_truncated = raw_text[:6000]
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            await fail_task(task_id, "AI service not configured")
            return

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

        from services.llm_service import chat_completion
        ai_content = await chat_completion(
            system_prompt="You are a precise resume parser. Extract structured candidate data from resumes. Return only valid JSON.",
            user_prompt=prompt,
            temperature=0.1,
            json_mode=True,
            timeout=90.0,
        )
        
        # Resilient JSON extraction: strip markdown code fences if present
        cleaned = ai_content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        
        profile_data = json_module.loads(cleaned)
        logger.info(f"[CV Parse BG] Extracted: {profile_data.get('name')}")
        await complete_task(task_id, {"success": True, "profile_data": profile_data, "filename": filename})
        
    except json_module.JSONDecodeError as je:
        logger.error(f"[CV Parse BG] JSON decode failed: {je}")
        await fail_task(task_id, "AI returned invalid JSON. Please retry or try a different file format.")
    except ValueError as e:
        logger.error(f"[CV Parse BG] Configuration error: {e}")
        await fail_task(task_id, "AI service temporarily unavailable. Please try again later.")
    except RuntimeError as e:
        logger.error(f"[CV Parse BG] LLM service error: {e}")
        await fail_task(task_id, "AI service is busy. Please try again in a few moments.")
    except Exception as e:
        logger.error(f"[CV Parse BG] Unexpected error ({type(e).__name__}): {e}")
        await fail_task(task_id, f"Failed to parse CV: {str(e)[:200]}")


@cv_upload_router.get("/cv-upload/parse/{task_id}")
async def get_parse_status(
    task_id: str,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Poll for CV parsing task status. Auto-fails stale tasks (>3 min stuck in processing)."""
    from services.async_tasks import get_task, fail_task
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["created_by"] != current_user["id"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    # Auto-fail stale tasks — if processing for > 3 minutes, the worker likely died
    if task["status"] == "processing" and task.get("updated_at"):
        from datetime import datetime, timezone
        try:
            updated = datetime.fromisoformat(task["updated_at"].replace("Z", "+00:00"))
            age_seconds = (datetime.now(timezone.utc) - updated).total_seconds()
            if age_seconds > 180:
                await fail_task(task_id, "CV parsing timed out on the server. The worker may have restarted. Please retry.")
                task["status"] = "failed"
                task["error"] = "CV parsing timed out on the server. The worker may have restarted. Please retry."
        except (ValueError, TypeError):
            pass

    return task


@cv_upload_router.post("/cv-upload/save")
async def save_cv_profile(
    data: dict,
    current_user: dict = Depends(require_role(["admin", "employer", "recruiter"]))
):
    """Save an AI-parsed CV profile to the candidate bank.

    Uses **non-destructive merge** logic when updating an existing candidate:
      1. Retain existing metadata (CTC, notice period, etc.) — never null-overwrite.
      2. Elaborate: merge richer work-experience / education / skills from CV.
      3. Append contacts: if CV has *different* phone/email, save as alternate.
    """

    profile = data.get("profile", {})
    name = profile.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    # --- duplicate lookup (any source, not just cv_upload) ---
    import re
    name_regex = re.compile(f"^{re.escape(name.strip())}$", re.IGNORECASE)
    existing = await db.candidate_bank.find_one(
        {"name": name_regex}, {"_id": 0}
    )
    if not existing and profile.get("email"):
        existing = await db.candidate_bank.find_one(
            {"email": profile["email"].lower().strip()}, {"_id": 0}
        )
    if not existing and profile.get("phone"):
        from services.extension_service import normalize_phone
        norm = normalize_phone(profile["phone"])
        if norm:
            existing = await db.candidate_bank.find_one(
                {"phone_normalized": norm}, {"_id": 0}
            )

    now = datetime.now(timezone.utc).isoformat()
    candidate_id = existing["id"] if existing else str(uuid.uuid4())
    action = "updated" if existing else "created"

    # --- parse CV fields ---
    cv_doc = _build_cv_document(profile, data, current_user, candidate_id, now)

    if existing:
        merged = _merge_cv_into_existing(existing, cv_doc, profile)
        merged["updated_at"] = now
        # Track the CV upload event
        merged.setdefault("source_history", existing.get("source_history", []))
        merged["source_history"].append({
            "source": "cv_upload",
            "filename": data.get("filename", "unknown"),
            "uploaded_by": current_user.get("email"),
            "uploaded_at": now,
        })
        merged["has_resume"] = True
        merged["resume_title"] = data.get("filename") or existing.get("resume_title")
        await db.candidate_bank.update_one({"id": candidate_id}, {"$set": merged})
        # re-read for response
        final = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    else:
        # Set visibility for new candidates
        from services.extension_service import build_team_visibility
        visibility_data = await build_team_visibility(current_user)
        cv_doc["visibility"] = visibility_data.get("visibility", {"employer_ids": [], "recruiter_ids": []})
        cv_doc["created_at"] = now
        await db.candidate_bank.insert_one(cv_doc)
        final = cv_doc
        final.pop("_id", None)

    # Log activity
    from services.activity_log_service import log_activity, ACTION_CV_UPLOADED, ACTION_UPDATED
    await log_activity(
        candidate_id=candidate_id,
        action=ACTION_CV_UPLOADED if action == "created" else ACTION_UPDATED,
        description=f"CV uploaded ({data.get('filename', 'unknown')})" if action == "created" else f"CV re-uploaded ({data.get('filename', 'unknown')}), profile merged",
        performed_by=current_user.get("id"), performed_by_name=current_user.get("name"),
        performed_by_role=current_user.get("role"),
        candidate_name=name,
        details={"filename": data.get("filename"), "action": action},
    )

    return {"success": True, "action": action, "candidate_id": candidate_id, "profile": final}


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS: build & merge
# ──────────────────────────────────────────────────────────────────────────────

def _build_cv_document(profile, data, current_user, candidate_id, now):
    """Build a fresh candidate document from a parsed CV (used for new candidates)."""
    from routes.extension import normalize_phone
    import asyncio

    name = profile["name"].strip()
    name_parts = name.split()
    first_name = name_parts[0] if name_parts else None
    last_name = name_parts[-1] if len(name_parts) > 1 else None
    middle_name = " ".join(name_parts[1:-1]) if len(name_parts) > 2 else None

    work_exp = profile.get("work_experience") or []
    current_from_exp = next((e for e in work_exp if isinstance(e, dict) and e.get("is_current")), {})

    education = profile.get("education") or []
    first_edu = education[0] if education and isinstance(education[0], dict) else {}
    highest_qual = first_edu.get("degree")
    highest_degree = first_edu.get("specialization") or first_edu.get("degree")

    raw_certs = profile.get("certifications") or []
    certs_list, certs_detailed = [], []
    for c in raw_certs:
        if isinstance(c, dict):
            n = c.get("name") or c.get("title") or ""
            if n:
                certs_list.append(n)
                certs_detailed.append(c)
        elif isinstance(c, str) and c:
            certs_list.append(c)
            certs_detailed.append({"name": c})

    online_profiles = profile.get("online_profiles") or []
    linkedin_url = github_url = None
    for op in online_profiles:
        if isinstance(op, dict):
            p = (op.get("platform") or "").lower()
            u = op.get("url") or ""
            if "linkedin" in p and u:
                linkedin_url = u
            elif "github" in p and u:
                github_url = u

    phone = profile.get("phone")
    email = (profile.get("email") or "").lower().strip() or None

    return {
        "id": candidate_id,
        "name": name, "first_name": first_name, "middle_name": middle_name, "last_name": last_name,
        "photo_url": None,
        "email": email, "alternate_email": None,
        "phone": phone, "phone_normalized": normalize_phone(phone) if phone else None, "alternate_phone": None,
        "headline": profile.get("headline"), "resume_headline": profile.get("headline"),
        "summary": profile.get("profile_summary"),
        "current_employer": profile.get("current_company") or current_from_exp.get("company"),
        "designation": profile.get("current_designation") or current_from_exp.get("designation"),
        "department": None, "industry": profile.get("current_industry"),
        "role_category": None, "employment_status": None,
        "experience_years": float(profile["total_experience_years"]) if profile.get("total_experience_years") else None,
        "experience_months": None,
        "experience_display": f"{profile['total_experience_years']} years" if profile.get("total_experience_years") else None,
        "experience": work_exp,
        "highest_qualification": highest_qual, "highest_degree": highest_degree, "education": education,
        "skills": profile.get("key_skills") or [],
        "skills_display": ", ".join(profile.get("key_skills") or []),
        "it_skills": profile.get("it_skills") or [], "soft_skills": [], "tools": [],
        "certifications": certs_list, "certifications_detailed": certs_detailed,
        "projects": profile.get("projects") or [],
        "languages": profile.get("languages") or [],
        "online_profiles": online_profiles, "linkedin_url": linkedin_url, "github_url": github_url, "portfolio_url": None,
        "date_of_birth": profile.get("date_of_birth"), "age": None, "gender": profile.get("gender"),
        "marital_status": None, "nationality": None,
        "has_passport": False, "passport_number": None, "passport_expiry": None,
        "permanent_address": None, "permanent_city": None, "permanent_state": None,
        "permanent_country": None, "permanent_pincode": None,
        "current_address": None, "current_city": None, "current_state": None,
        "current_country": None, "current_pincode": None,
        "category": None, "differently_abled": False, "disability_type": None,
        "work_permit_usa": None, "work_permit_other": None,
        "current_salary": None, "current_salary_currency": "INR", "current_salary_breakdown": None,
        "expected_salary": None, "expected_salary_currency": "INR",
        "expected_salary_min": None, "expected_salary_max": None,
        "notice_period": None, "notice_period_days": None,
        "is_serving_notice": False, "last_working_day": None, "notice_negotiable": False,
        "location": profile.get("location"),
        "preferred_locations": profile.get("preferred_locations") or [],
        "willing_to_relocate": False, "relocation_preferences": [],
        "preferred_job_type": [], "preferred_employment_type": [], "preferred_shift": [],
        "work_from_home": False, "remote_work_preference": None,
        "preferred_industry": [], "preferred_functional_area": [],
        "preferred_role": [], "preferred_role_category": [],
        "preferred_company_type": [], "preferred_company_size": None, "companies_to_avoid": [],
        "accomplishments": None, "about_me": None, "additional_info": None,
        "has_resume": True, "resume_title": data.get("filename"), "resume_format": None,
        "source": "cv_upload",
        "source_details": {
            "upload_method": "cv_upload",
            "filename": data.get("filename", "unknown"),
            "captured_by": current_user["id"],
            "captured_by_name": current_user.get("name", current_user.get("email")),
            "captured_by_email": current_user.get("email"),
            "captured_at": datetime.now(timezone.utc).isoformat(),
        },
        "created_by": current_user["id"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _merge_cv_into_existing(existing: dict, cv_doc: dict, profile: dict) -> dict:
    """Non-destructive merge: CV data enriches existing record without null overwrites.

    Rules:
      1. PROTECTED metadata fields (CTC, notice, salary, etc.) are NEVER overwritten
         if they already have a value — regardless of what the CV says.
      2. Elaboration fields (work experience, education, skills, summary) are merged:
         the richer/longer version wins, arrays are union-merged.
      3. Contact fields: if the CV brings a *different* phone/email, it becomes
         the alternate; the original stays primary.
    """
    from routes.extension import normalize_phone
    update: dict = {}

    # ── 1. PROTECTED scalar fields: keep existing if populated ──
    PROTECTED_FIELDS = [
        "current_salary", "current_salary_currency", "current_salary_breakdown",
        "expected_salary", "expected_salary_currency", "expected_salary_min", "expected_salary_max",
        "notice_period", "notice_period_days", "is_serving_notice", "last_working_day", "notice_negotiable",
        "naukri_profile_id", "naukri_profile_url",
        "preferred_job_type", "preferred_employment_type", "preferred_shift",
        "work_from_home", "remote_work_preference",
        "preferred_industry", "preferred_functional_area", "preferred_role", "preferred_role_category",
        "preferred_company_type", "preferred_company_size", "companies_to_avoid",
        "willing_to_relocate", "relocation_preferences",
        "has_passport", "passport_number", "passport_expiry",
        "work_permit_usa", "work_permit_other",
        "category", "differently_abled", "disability_type",
        "marital_status", "nationality",
        "photo_url", "response_rate",
    ]
    # These fields stay untouched from the existing record.
    for field in PROTECTED_FIELDS:
        if _has_value(existing.get(field)):
            update[field] = existing[field]

    # ── 2. FILL-IF-EMPTY scalar fields: CV fills gaps only ──
    FILL_FIELDS = [
        "headline", "resume_headline", "industry", "role_category",
        "department", "employment_status",
        "date_of_birth", "age", "gender",
        "permanent_address", "permanent_city", "permanent_state", "permanent_country", "permanent_pincode",
        "current_address", "current_city", "current_state", "current_country", "current_pincode",
        "accomplishments", "about_me", "additional_info",
        "linkedin_url", "github_url", "portfolio_url",
    ]
    for field in FILL_FIELDS:
        cv_val = cv_doc.get(field)
        ex_val = existing.get(field)
        if _has_value(cv_val) and not _has_value(ex_val):
            update[field] = cv_val

    # ── 3. ELABORATE text fields: prefer longer/richer version ──
    for field in ["summary", "headline", "resume_headline"]:
        cv_val = cv_doc.get(field) or ""
        ex_val = existing.get(field) or ""
        if len(str(cv_val)) > len(str(ex_val)):
            update[field] = cv_val

    # ── 4. CONTACT merging: append as alternates ──
    cv_email = cv_doc.get("email")
    cv_phone = cv_doc.get("phone")
    ex_email = existing.get("email")
    ex_phone = existing.get("phone")

    # Email
    if cv_email and ex_email:
        if cv_email.lower().strip() != ex_email.lower().strip():
            # Different email — store as alternate (keep original primary)
            ex_alt_email = existing.get("alternate_email")
            if not ex_alt_email:
                update["alternate_email"] = cv_email
            elif ex_alt_email.lower().strip() != cv_email.lower().strip():
                update["alternate_email"] = cv_email  # update alternate to latest CV email
    elif cv_email and not ex_email:
        update["email"] = cv_email

    # Phone
    if cv_phone and ex_phone:
        cv_norm = normalize_phone(cv_phone)
        ex_norm = normalize_phone(ex_phone)
        if cv_norm != ex_norm:
            ex_alt_phone = existing.get("alternate_phone")
            if not ex_alt_phone:
                update["alternate_phone"] = cv_phone
            elif normalize_phone(ex_alt_phone) != cv_norm:
                update["alternate_phone"] = cv_phone
    elif cv_phone and not ex_phone:
        update["phone"] = cv_phone
        update["phone_normalized"] = normalize_phone(cv_phone)

    # ── 5. NAME: prefer CV if it looks more complete ──
    cv_name = cv_doc.get("name") or ""
    ex_name = existing.get("name") or ""
    if cv_name and len(cv_name.split()) > len(ex_name.split()):
        update["name"] = cv_name
        parts = cv_name.split()
        update["first_name"] = parts[0]
        update["last_name"] = parts[-1] if len(parts) > 1 else None
        update["middle_name"] = " ".join(parts[1:-1]) if len(parts) > 2 else None

    # ── 6. CURRENT EMPLOYMENT: fill gaps, don't overwrite ──
    for field in ["current_employer", "designation"]:
        cv_val = cv_doc.get(field)
        ex_val = existing.get(field)
        if _has_value(cv_val) and not _has_value(ex_val):
            update[field] = cv_val

    # ── 7. EXPERIENCE YEARS: fill if missing ──
    cv_exp = cv_doc.get("experience_years")
    ex_exp = existing.get("experience_years")
    if cv_exp and not ex_exp:
        update["experience_years"] = cv_exp
        update["experience_display"] = f"{cv_exp} years"

    # ── 8. LOCATION: fill if missing ──
    if _has_value(cv_doc.get("location")) and not _has_value(existing.get("location")):
        update["location"] = cv_doc["location"]

    # ── 9. ARRAY merging — union dedup for elaboration fields ──
    # Work experience: merge by company+designation key
    update["experience"] = _merge_work_experience(
        existing.get("experience") or [], cv_doc.get("experience") or []
    )

    # Education: merge by degree+institution key
    update["education"] = _merge_by_keys(
        existing.get("education") or [], cv_doc.get("education") or [],
        keys=["degree", "institution"]
    )

    # Skills: union
    update["skills"] = _merge_string_lists(
        existing.get("skills") or [], cv_doc.get("skills") or []
    )
    update["skills_display"] = ", ".join(update["skills"])

    # IT Skills: merge by name
    update["it_skills"] = _merge_by_keys(
        existing.get("it_skills") or [], cv_doc.get("it_skills") or [],
        keys=["name"]
    )

    # Certifications: union strings
    update["certifications"] = _merge_string_lists(
        existing.get("certifications") or [], cv_doc.get("certifications") or []
    )
    update["certifications_detailed"] = _merge_by_keys(
        existing.get("certifications_detailed") or [], cv_doc.get("certifications_detailed") or [],
        keys=["name"]
    )

    # Projects: merge by title
    update["projects"] = _merge_by_keys(
        existing.get("projects") or [], cv_doc.get("projects") or [],
        keys=["title"]
    )

    # Languages: merge by language name
    update["languages"] = _merge_by_keys(
        existing.get("languages") or [], cv_doc.get("languages") or [],
        keys=["language"]
    )

    # Online profiles: merge by platform
    update["online_profiles"] = _merge_by_keys(
        existing.get("online_profiles") or [], cv_doc.get("online_profiles") or [],
        keys=["platform"]
    )

    # Preferred locations: union
    update["preferred_locations"] = _merge_string_lists(
        existing.get("preferred_locations") or [], cv_doc.get("preferred_locations") or []
    )

    # ── 10. Preserve source & visibility from original ──
    if existing.get("source"):
        update["source"] = existing["source"]  # keep original source (e.g. "naukri_extension")
    if existing.get("visibility"):
        update["visibility"] = existing["visibility"]
    if existing.get("created_by"):
        update["created_by"] = existing["created_by"]

    return update


def _has_value(val) -> bool:
    """Return True if val is non-null, non-empty, non-zero meaningful data."""
    if val is None:
        return False
    if isinstance(val, str) and not val.strip():
        return False
    if isinstance(val, (list, dict)) and not val:
        return False
    return True


def _merge_string_lists(existing: list, new: list) -> list:
    """Union-merge two lists of strings, case-insensitive dedup."""
    seen = set()
    result = []
    for item in existing + new:
        if isinstance(item, str):
            key = item.strip().lower()
            if key and key not in seen:
                seen.add(key)
                result.append(item.strip())
    return result


def _merge_by_keys(existing: list, new: list, keys: list) -> list:
    """Merge two lists of dicts, deduplicating by a composite key.
    If a match is found, prefer the entry with more data (longer JSON repr).
    """
    def make_key(d):
        return "|".join((str(d.get(k) or "")).strip().lower() for k in keys)

    merged = {}
    for item in existing:
        if isinstance(item, dict):
            k = make_key(item)
            if k and k not in merged:
                merged[k] = item

    for item in new:
        if isinstance(item, dict):
            k = make_key(item)
            if not k:
                continue
            if k in merged:
                # prefer the entry with more detail (longer serialized form)
                import json as _j
                if len(_j.dumps(item, default=str)) > len(_j.dumps(merged[k], default=str)):
                    merged[k] = item
            else:
                merged[k] = item

    return list(merged.values())


def _merge_work_experience(existing: list, new: list) -> list:
    """Merge work experience entries, matching by company+designation.
    Prefer the CV version if it has a longer description (richer detail).
    """
    def make_key(exp):
        company = (exp.get("company") or "").strip().lower()
        desig = (exp.get("designation") or "").strip().lower()
        return f"{company}|{desig}"

    merged = {}
    order = []

    for exp in existing:
        if isinstance(exp, dict):
            k = make_key(exp)
            if k not in merged:
                order.append(k)
            merged[k] = exp

    for exp in new:
        if isinstance(exp, dict):
            k = make_key(exp)
            if k in merged:
                # Prefer whichever has a longer description (CV usually wins)
                old_desc = len(str(merged[k].get("description") or ""))
                new_desc = len(str(exp.get("description") or ""))
                if new_desc > old_desc:
                    merged[k] = exp
            else:
                order.append(k)
                merged[k] = exp

    return [merged[k] for k in order if k in merged]
