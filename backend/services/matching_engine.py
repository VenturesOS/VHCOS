"""
AI Matching Engine Service for VHC Talent OS
Uses GPT-5.2 via Emergent LLM (primary) or direct OpenAI API (fallback).
Includes fast (non-LLM) scoring for high-concurrency scenarios.

FIXED:
- Single canonical parse_resume_with_ai() implementation
- normalize_candidate() applied to every parse result
- calculate_fast_match_score() reads both canonical + alias field names
- calculate_candidate_job_match() reads both canonical + alias field names
- AWS-portable: falls back to direct OpenAI when emergentintegrations unavailable
"""
import os
import re
import json
import hashlib
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone
import uuid
import logging

# Try to import Emergent LLM library; fall back to direct OpenAI API via llm_service.py
_USE_EMERGENT = False
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    _emergent_key = os.environ.get("EMERGENT_LLM_KEY")
    if _emergent_key:
        _USE_EMERGENT = True
        logging.info("[MATCHING] Using Emergent LLM (emergentintegrations library)")
    else:
        logging.info("[MATCHING] EMERGENT_LLM_KEY not set — falling back to direct OpenAI API")
except ImportError:
    logging.info("[MATCHING] emergentintegrations not installed — using direct OpenAI API fallback")

from services.schema_normalizer import (
    normalize_candidate,
    extract_json_from_llm_response,
    get_skills,
    get_all_skill_tokens,
    get_summary,
    get_experience_years,
    get_experience_list,
    get_designation,
    get_employer,
    get_industry,
)

# Pre-import text extraction libraries at module load (avoids thread import-lock deadlocks)
import io as _io
import tempfile as _tempfile
import subprocess as _subprocess
from pathlib import Path as _Path

_fitz = None
try:
    import fitz as _fitz
except ImportError:
    pass

_docx2txt = None
try:
    import docx2txt as _docx2txt
except ImportError:
    pass

_docx = None
try:
    import docx as _docx
except ImportError:
    pass

_pypdf = None
try:
    # pypdf is the maintained successor to PyPDF2 (same API at the points we
    # use). Falling back to PyPDF2 if pypdf isn't installed yet on EC2.
    import pypdf as _pypdf
except ImportError:
    try:
        import PyPDF2 as _pypdf  # type: ignore
    except ImportError:
        pass

# pdfplumber: table-aware fallback when fitz/pypdf yield too little text
# (often the case for resumes where contact info / experience hides in
# tables, multi-column layouts, or text-as-image-fragments).
_pdfplumber = None
try:
    import pdfplumber as _pdfplumber
except ImportError:
    pass

_pytesseract = None
_convert_from_bytes = None
try:
    import pytesseract as _pytesseract
    from pdf2image import convert_from_bytes as _convert_from_bytes
except ImportError:
    pass

logger = logging.getLogger(__name__)

EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")


async def _llm_chat(system_msg: str, user_msg: str, max_tokens: int = 1500) -> str:
    """
    Unified LLM chat — NOW USING GROQ for cost optimization.
    
    Phase 55.14: routes directly through llm_service.chat_completion, which
    itself uses NVIDIA Nemotron → Nemotron Super 120B (primary) → Emergent Claude Haiku 4.5
    (fallback). The old Groq-first path was removed with services/groq_ai_service.
    """
    from services.llm_service import chat_completion
    return await chat_completion(
        system_prompt=system_msg,
        user_prompt=user_msg,
        json_mode=True,
        temperature=0.3,
        timeout=120.0,
        max_tokens=max_tokens,
        priority="high",
    )


def get_chat_client(system_msg: str = "You are an expert recruiter AI that extracts structured data from text."):
    """Get Emergent Chat client for GPT-5.2 (legacy — use _llm_chat for new code)."""
    if not _USE_EMERGENT:
        raise RuntimeError("emergentintegrations not available — use _llm_chat() instead")
    return LlmChat(
        api_key=EMERGENT_KEY,
        session_id=str(uuid.uuid4()),
        system_message=system_msg,
    )


# ---------------------------------------------------------------------------
# CANONICAL RESUME PARSER — single implementation
# routes/candidates.py imports this; do NOT re-implement there.
# ---------------------------------------------------------------------------

async def parse_resume_with_ai(resume_text: str) -> Dict:
    """
    Parse resume text using GPT-5.2 to extract structured data.

    Returns {"success": True, "data": <normalized_candidate_dict>}
        or  {"success": False, "error": "<message>"}

    Output is always normalized via normalize_candidate() so that
    BOTH canonical field names (key_skills, profile_summary, work_experience,
    total_experience_years) AND their aliases (skills, summary, experience,
    experience_years) are present with identical values.
    """
    response_text = ""
    try:
        system_msg = (
            "You are an expert resume parser. Extract structured data from resumes "
            "with maximum detail and accuracy. Never fabricate data — only extract "
            "what is present. Return only valid JSON, no markdown, no commentary."
        )

        prompt = f"""Parse the following resume and extract structured data.
Return ONLY valid JSON with this EXACT structure — no extra keys, no omissions.
Use null for any field not found in the resume.

{{
    "name": "full name or null",
    "email": "email or null",
    "phone": "phone or null",
    "headline": "professional title/headline or null",
    "profile_summary": "professional summary 2-3 sentences or null",
    "current_company": "current or most recent employer or null",
    "current_designation": "current or most recent job title or null",
    "current_industry": "industry if determinable or null",
    "total_experience_years": <number or null>,
    "location": "city, state/country or null",
    "date_of_birth": "DOB if found or null",
    "gender": "gender if found or null",
    "key_skills": ["skill1", "skill2"],
    "it_skills": [{{"name": "tool/tech", "version": "ver or null", "experience": "yrs or null"}}],
    "work_experience": [
        {{
            "designation": "job title",
            "company": "company name",
            "from_date": "MMM YYYY or null",
            "to_date": "MMM YYYY or null",
            "is_current": true,
            "description": "responsibilities/achievements"
        }}
    ],
    "education": [
        {{
            "degree": "degree name",
            "specialization": "field of study or null",
            "institution": "university/college",
            "year_of_passing": "year or null"
        }}
    ],
    "certifications": ["certification name 1"],
    "projects": [{{"title": "name", "description": "brief description"}}],
    "languages": [{{"language": "name", "proficiency": "level or null"}}],
    "online_profiles": [{{"platform": "LinkedIn/GitHub/etc", "url": "URL"}}],
    "preferred_locations": ["location1"]
}}

Resume text:
{resume_text[:8000]}"""

        logger.info(f"[RESUME PARSE] Sending prompt, length: {len(prompt)}")

        response_text = await _llm_chat(system_msg, prompt)
        response_text = (response_text or "").strip()
        if not response_text:
            logger.error("[RESUME PARSE] LLM returned empty response")
            return {"success": False, "error": "LLM returned empty response"}

        logger.info(f"[RESUME PARSE] Raw response (first 500): {response_text[:500]}")

        json_str = extract_json_from_llm_response(response_text)
        logger.info(f"[RESUME PARSE] Extracted JSON (first 300): {json_str[:300]}")

        # Try strict json.loads first; fall back to json_repair on truncation /
        # malformed output. This prevents recurring "[RESUME PARSE] JSON parse
        # error: Expecting ',' delimiter" storms (May-05 incident: same
        # candidate retried >5 times → contributed to Anthropic credit drain
        # and OOM cascade). json_repair already handles LLM/Haiku truncation
        # in llm_fallback_service.py — we extend the same defence here.
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as je:
            try:
                from json_repair import repair_json
                repaired = repair_json(json_str, return_objects=True)
                if isinstance(repaired, dict) and repaired:
                    logger.warning(
                        f"[RESUME PARSE] Recovered via json_repair "
                        f"(strict failed: {je})"
                    )
                    parsed = repaired
                else:
                    raise je
            except ImportError:
                logger.error("[RESUME PARSE] json_repair not installed")
                raise je

        # Apply canonical normalization — resolves ALL field name variants
        normalized = normalize_candidate(parsed)

        logger.info(
            f"[RESUME PARSE] Success. "
            f"skills={len(normalized.get('key_skills', []))}, "
            f"exp_years={normalized.get('total_experience_years')}"
        )
        return {"success": True, "data": normalized}

    except json.JSONDecodeError as e:
        logger.error(
            f"[RESUME PARSE] JSON parse error: {e}. "
            f"Response was: {response_text[:500]}"
        )
        return {"success": False, "error": f"Failed to parse AI response: {str(e)}"}
    except Exception as e:
        logger.error(f"[RESUME PARSE] Error: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# JD Parser
# ---------------------------------------------------------------------------

async def parse_job_description_with_ai(jd_text: str) -> Dict:
    """
    Parse job description using GPT-5.2 to extract structured requirements.
    """
    response_text = ""
    try:
        system_msg = "You are an expert job description parser. Extract structured requirements accurately."

        prompt = f"""Parse the following job description and extract structured requirements.
Return ONLY valid JSON with this exact structure:

{{
    "title": "job title",
    "department": "department if mentioned or null",
    "location": "location requirement or null",
    "job_type": "full-time/part-time/contract/remote",
    "experience_min": <minimum years as number or 0>,
    "experience_max": <maximum years as number or null>,
    "required_skills": ["must have skill1", "must have skill2"],
    "preferred_skills": ["nice to have skill1"],
    "required_qualifications": ["degree requirement", "certification"],
    "responsibilities": ["responsibility1", "responsibility2"],
    "salary_min": <minimum salary as number or null>,
    "salary_max": <maximum salary as number or null>,
    "key_requirements_summary": "2-3 sentence summary of key requirements"
}}

Job Description:
{jd_text[:8000]}"""

        logger.info(f"[JD PARSE] Sending prompt, length: {len(prompt)}")

        response_text = await _llm_chat(system_msg, prompt)
        response_text = (response_text or "").strip()
        if not response_text:
            logger.error("[JD PARSE] LLM returned empty response")
            return {"success": False, "error": "LLM returned empty response"}

        logger.info(f"[JD PARSE] Raw response (first 500): {response_text[:500]}")

        json_str = extract_json_from_llm_response(response_text)
        parsed = json.loads(json_str)

        logger.info(f"[JD PARSE] Success. Keys: {list(parsed.keys())}")
        return {"success": True, "data": parsed}

    except json.JSONDecodeError as e:
        logger.error(f"[JD PARSE] JSON parse error: {e}")
        return {"success": False, "error": f"Failed to parse AI response: {str(e)}"}
    except Exception as e:
        logger.error(f"[JD PARSE] Error: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# AI Match Scorer
# ---------------------------------------------------------------------------

async def calculate_candidate_job_match(
    candidate_data: Dict,
    job_data: Dict,
    must_have_filters: Optional[Dict] = None,
) -> Dict:
    """
    Calculate match score between candidate and job using AI.
    Returns match score (0-100) and explanation.

    FIXED: reads both canonical and alias field names via schema_normalizer helpers.
    """
    response_text = ""
    try:
        # Hard filters first
        if must_have_filters:
            filter_result = apply_must_have_filters(candidate_data, must_have_filters)
            if not filter_result["passed"]:
                return {
                    "score": 0,
                    "matched": False,
                    "filtered_out": True,
                    "filter_reason": filter_result["reason"],
                    "explanation": f"Candidate excluded: {filter_result['reason']}",
                }

        system_msg = "You are an expert recruiter AI that evaluates candidate-job fit."

        # Use normalizer helpers — works regardless of which schema the doc uses
        candidate_skills   = get_skills(candidate_data)
        candidate_exp      = get_experience_years(candidate_data)
        candidate_summary  = get_summary(candidate_data)
        candidate_edu      = candidate_data.get("education", [])
        candidate_location = candidate_data.get("location", "Not specified")

        prompt = f"""Analyze the match between this candidate and job. Return ONLY valid JSON.

CANDIDATE:
- Skills: {candidate_skills}
- Experience Years: {candidate_exp}
- Education: {candidate_edu}
- Location: {candidate_location}
- Summary: {candidate_summary[:500] if candidate_summary else "Not provided"}

JOB REQUIREMENTS:
- Required Skills: {job_data.get("required_skills", [])}
- Experience Required: {job_data.get("experience_min", 0)}-{job_data.get("experience_max", "any")} years
- Required Qualifications: {job_data.get("required_qualifications", [])}
- Location: {job_data.get("location", "Any")}

Return JSON:
{{
    "score": <number 0-100>,
    "skill_match_score": <number 0-100>,
    "experience_match_score": <number 0-100>,
    "education_match_score": <number 0-100>,
    "matched_skills": ["skill1", "skill2"],
    "missing_skills": ["skill1", "skill2"],
    "strengths": ["strength1", "strength2"],
    "gaps": ["gap1", "gap2"],
    "recommendation": "brief recommendation",
    "explanation": "2-3 sentence explanation of the match"
}}"""

        logger.info("[MATCH CALC] Sending prompt to LLM")

        response_text = await _llm_chat(system_msg, prompt)
        response_text = (response_text or "").strip()
        if not response_text:
            logger.error("[MATCH CALC] LLM returned empty response")
            return {
                "score": 0,
                "matched": False,
                "error": "LLM returned empty response",
                "explanation": "Unable to calculate match — no AI response",
            }

        json_str = extract_json_from_llm_response(response_text)
        # Match-calc parser uses the same json_repair fallback as the
        # resume parser at line ~219 (Phase 51) and the resume-upload path
        # below. Without this, LLM truncation on long candidate profiles
        # causes "Expecting ',' delimiter" 500s on /api/applications +
        # /api/candidate-bank/upload (Phase 52 maintenance review fix).
        try:
            match_result = json.loads(json_str)
        except json.JSONDecodeError as je:
            try:
                from json_repair import repair_json
                repaired = repair_json(json_str, return_objects=True)
                if isinstance(repaired, dict) and repaired:
                    logger.warning(
                        f"[MATCH CALC] Recovered via json_repair "
                        f"(strict failed: {je})"
                    )
                    match_result = repaired
                else:
                    raise je
            except ImportError:
                raise je
        match_result["matched"]     = match_result.get("score", 0) >= 50
        match_result["filtered_out"] = False

        logger.info(f"[MATCH CALC] Score: {match_result.get('score')}")
        return match_result

    except json.JSONDecodeError as e:
        logger.error(f"[MATCH CALC] JSON parse error: {e}")
        return {
            "score": 0,
            "matched": False,
            "error": f"JSON parse error: {str(e)}",
            "explanation": "Unable to calculate match",
        }
    except Exception as e:
        logger.error(f"[MATCH CALC] Error: {type(e).__name__}: {e}")
        return {
            "score": 0,
            "matched": False,
            "error": str(e),
            "explanation": "Unable to calculate match",
        }


# ---------------------------------------------------------------------------
# Hard filters
# ---------------------------------------------------------------------------

def apply_must_have_filters(candidate_data: Dict, filters: Dict) -> Dict:
    """Apply hard filters. Returns {"passed": bool, "reason": str|None}."""

    # Location
    if filters.get("location"):
        loc = (candidate_data.get("location") or "").lower()
        if filters["location"].lower() not in loc:
            return {"passed": False, "reason": f"Location mismatch: requires {filters['location']}"}

    # Experience — use normalizer helper
    cand_exp = get_experience_years(candidate_data)
    if filters.get("min_experience") is not None:
        if cand_exp < float(filters["min_experience"]):
            return {"passed": False, "reason": f"Insufficient experience: requires {filters['min_experience']}+ years"}
    if filters.get("max_experience") is not None:
        if cand_exp > float(filters["max_experience"]):
            return {"passed": False, "reason": f"Over-experienced: max {filters['max_experience']} years"}

    # Mandatory skills — use normalizer helper
    if filters.get("mandatory_skills"):
        candidate_skills = get_all_skill_tokens(candidate_data)
        for skill in filters["mandatory_skills"]:
            skill_lower = skill.lower()
            found = any(skill_lower in cs or cs in skill_lower for cs in candidate_skills)
            if not found:
                return {"passed": False, "reason": f"Missing mandatory skill: {skill}"}

    # Qualification
    if filters.get("required_qualification"):
        edu_text = " ".join([
            f"{e.get('degree', '')} {e.get('institution', '')}"
            for e in (candidate_data.get("education") or [])
        ]).lower()
        if filters["required_qualification"].lower() not in edu_text:
            return {"passed": False, "reason": f"Missing qualification: {filters['required_qualification']}"}

    return {"passed": True, "reason": None}


# ---------------------------------------------------------------------------
# Resume fingerprint
# ---------------------------------------------------------------------------

def generate_resume_fingerprint(resume_text: str) -> str:
    """Generate a fingerprint hash for resume deduplication."""
    normalized = " ".join(resume_text.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

async def find_similar_candidate(
    db,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    resume_fingerprint: Optional[str] = None,
    name: Optional[str] = None,
    skills: Optional[List[str]] = None,
) -> Optional[Dict]:
    """
    Find duplicate candidate using multiple criteria.
    Priority: email > phone > resume fingerprint.
    """
    if email:
        existing = await db.candidate_bank.find_one(
            {"email": email.strip().lower()}, {"_id": 0}
        )
        if existing:
            return {"found": True, "candidate": existing, "match_type": "email"}

    if phone:
        normalized_phone = "".join(filter(str.isdigit, phone))
        if len(normalized_phone) >= 10:
            existing = await db.candidate_bank.find_one(
                {"phone_normalized": normalized_phone[-10:]}, {"_id": 0}
            )
            if existing:
                return {"found": True, "candidate": existing, "match_type": "phone"}

    if resume_fingerprint:
        existing = await db.candidate_bank.find_one(
            {"resume_fingerprints": resume_fingerprint}, {"_id": 0}
        )
        if existing:
            return {"found": True, "candidate": existing, "match_type": "resume_fingerprint"}

    return {"found": False, "candidate": None, "match_type": None}


# ---------------------------------------------------------------------------
# Fast (non-LLM) scoring
# ---------------------------------------------------------------------------

def parse_job_requirements_fast(
    job_doc: Optional[Dict] = None,
    jd_text: Optional[str] = None,
) -> Dict:
    """
    Extract structured job requirements WITHOUT an LLM call.
    Returns a structure compatible with the LLM-parsed format.
    """
    result = {
        "title": "",
        "required_skills": [],
        "preferred_skills": [],
        "experience_min": None,
        "experience_max": None,
        "location": None,
        "required_qualifications": [],
        "key_requirements_summary": "",
    }

    if job_doc:
        result["title"]    = job_doc.get("title", "")
        result["location"] = job_doc.get("location")

        # Prioritize structured skills array if available
        structured_skills = job_doc.get("skills") or job_doc.get("key_skills") or []
        if isinstance(structured_skills, list) and structured_skills:
            result["required_skills"] = [s.strip() for s in structured_skills if s.strip()]
        else:
            # Fall back to parsing requirements text
            req_text  = job_doc.get("requirements", "") or ""
            # Handle bullet-point, newline, and comma formats
            import re as _re
            lines = _re.split(r'[•\n\r;]+', req_text)
            parsed_reqs = [l.strip().strip(',').strip() for l in lines if l.strip() and len(l.strip()) > 2]
            # Filter out long sentences — skills should be < 60 chars
            result["required_skills"] = [r for r in parsed_reqs if len(r) < 60][:20]

        desc_text = job_doc.get("description", "")  or ""
        combined  = f"{job_doc.get('requirements', '')} {desc_text}".strip()

        result["experience_min"]          = job_doc.get("experience_min") or job_doc.get("min_experience")
        result["experience_max"]          = job_doc.get("experience_max") or job_doc.get("max_experience")
        result["salary_min"]              = job_doc.get("salary_min") or job_doc.get("ctc_min")
        result["salary_max"]              = job_doc.get("salary_max") or job_doc.get("ctc_max")
        result["key_requirements_summary"] = combined[:300]

    if jd_text and not result["required_skills"]:
        text_lower = jd_text.lower()
        result["key_requirements_summary"] = jd_text[:300]

        exp_patterns = [
            r"(\d+)\+?\s*(?:to|-)\s*(\d+)\s*years?",
            r"(\d+)\+?\s*years?\s*(?:of)?\s*experience",
            r"minimum\s*(\d+)\s*years?",
        ]
        for pat in exp_patterns:
            m = re.search(pat, text_lower)
            if m:
                groups = m.groups()
                result["experience_min"] = int(groups[0])
                if len(groups) > 1 and groups[1]:
                    result["experience_max"] = int(groups[1])
                break

        _SKILL_KEYWORDS = {
            "python", "java", "javascript", "typescript", "react", "angular", "vue",
            "node", "nodejs", "django", "flask", "fastapi", "spring", "sql", "nosql",
            "mongodb", "postgresql", "mysql", "redis", "docker", "kubernetes", "aws",
            "azure", "gcp", "git", "ci/cd", "agile", "scrum", "machine learning",
            "deep learning", "data science", "nlp", "computer vision", "tensorflow",
            "pytorch", "pandas", "numpy", "excel", "powerpoint", "communication",
            "leadership", "management", "sales", "marketing", "finance", "accounting",
            "hr", "recruitment", "devops", "sre", "html", "css", "sass", "graphql",
            "rest", "api", "microservices", "cloud", "linux", "c++", "c#", ".net",
            "golang", "rust", "swift", "kotlin", "flutter", "react native", "figma",
            "photoshop", "illustrator", "ui/ux", "product management", "jira",
            "confluence", "slack", "tableau", "power bi", "spark", "hadoop",
            "airflow", "kafka", "rabbitmq", "elasticsearch", "terraform", "ansible",
        }
        found_skills = []
        for skill in _SKILL_KEYWORDS:
            if skill in text_lower:
                found_skills.append(skill.title() if len(skill) > 3 else skill.upper())
        result["required_skills"] = found_skills[:20]

    # Alias for compatibility with routes that expect "skills"
    result["skills"] = result["required_skills"]
    result["summary"] = result.get("key_requirements_summary", "")
    result["responsibilities"] = []
    result["requirements"] = result["required_skills"]

    return result


# ---------------------------------------------------------------------------
# Skill synonym map — 300+ bidirectional entries
# ---------------------------------------------------------------------------
_SKILL_SYNONYMS_RAW = {
    # Programming languages
    "js": "javascript", "ts": "typescript", "py": "python", "c#": "csharp",
    "c++": "cpp", "golang": "go", "rb": "ruby",
    # Frontend
    "react.js": "react", "reactjs": "react", "react native": "react-native",
    "vue.js": "vue", "vuejs": "vue", "angular.js": "angular", "angularjs": "angular",
    "next.js": "nextjs", "nextjs": "next.js", "nuxt.js": "nuxtjs",
    "svelte.js": "svelte", "jquery": "j query",
    # Backend
    "node.js": "nodejs", "nodejs": "node", "express.js": "express", "expressjs": "express",
    "django rest framework": "drf", "drf": "django rest framework",
    "spring boot": "spring", "asp.net": "aspnet", ".net": "dotnet", "dotnet": ".net",
    "ruby on rails": "rails", "ror": "ruby on rails",
    "fastapi": "fast api", "flask": "flask python",
    # Cloud & DevOps
    "aws": "amazon web services", "amazon web services": "aws",
    "gcp": "google cloud", "google cloud platform": "gcp", "google cloud": "gcp",
    "k8s": "kubernetes", "kubernetes": "k8s",
    "ci/cd": "cicd", "cicd": "ci cd", "ci cd": "ci/cd",
    "devops": "dev ops", "sre": "site reliability",
    "tf": "terraform", "terraform": "tf",
    "iac": "infrastructure as code", "cloudformation": "cf",
    # Databases
    "postgres": "postgresql", "postgresql": "postgres",
    "mongo": "mongodb", "mongodb": "mongo",
    "ms sql": "mssql", "mssql": "sql server", "sql server": "mssql",
    "dynamodb": "dynamo db", "cassandra": "apache cassandra",
    "elasticsearch": "elastic search", "es": "elasticsearch",
    # Data & AI
    "ml": "machine learning", "machine learning": "ml",
    "ai": "artificial intelligence", "artificial intelligence": "ai",
    "dl": "deep learning", "deep learning": "dl",
    "nlp": "natural language processing", "natural language processing": "nlp",
    "cv": "computer vision", "computer vision": "cv",
    "sklearn": "scikit-learn", "scikit-learn": "sklearn", "scikit learn": "sklearn",
    "pyspark": "spark", "apache spark": "spark",
    "apache kafka": "kafka", "apache airflow": "airflow",
    "bi": "business intelligence", "business intelligence": "bi",
    "etl": "extract transform load", "data pipeline": "etl",
    "powerbi": "power bi", "power bi": "powerbi",
    "data visualization": "data viz",
    # Sales & Marketing
    "b2b": "business to business", "b2c": "business to consumer",
    "crm": "customer relationship management", "salesforce crm": "salesforce",
    "seo": "search engine optimization", "sem": "search engine marketing",
    "smm": "social media marketing", "digital marketing": "online marketing",
    "google ads": "google adwords", "ppc": "pay per click",
    "lead generation": "lead gen", "business development": "bd",
    "key account management": "kam", "channel sales": "channel partner sales",
    "distribution sales": "distributor sales", "dealer management": "dealer network",
    "territory management": "area management", "area sales": "territory sales",
    "fmcg sales": "fmcg", "institutional sales": "corporate sales",
    # HR & Management
    "hr": "human resources", "human resources": "hr",
    "pm": "project management", "project management": "pm",
    "pmp": "project management professional",
    "talent acquisition": "recruitment", "recruitment": "hiring",
    "onboarding": "employee onboarding",
    "l&d": "learning and development", "training": "l&d",
    # Finance & Accounting
    "ca": "chartered accountant", "chartered accountant": "ca",
    "cma": "cost management accountant", "cfa": "chartered financial analyst",
    "gst": "goods and services tax", "tds": "tax deducted at source",
    "accounts payable": "ap", "accounts receivable": "ar",
    "erp": "enterprise resource planning", "sap": "sap erp",
    "tally": "tally erp", "quickbooks": "quick books",
    "mis": "management information system", "p&l": "profit and loss",
    "budgeting": "financial planning",
    # Office & Tools
    "ms excel": "excel", "excel": "ms excel", "advanced excel": "excel",
    "ms word": "word", "ms powerpoint": "powerpoint",
    "google sheets": "g sheets", "ms office": "microsoft office",
    "jira": "atlassian jira", "confluence": "atlassian confluence",
    # Design
    "ui/ux": "ui ux", "ux design": "ui/ux", "ui design": "ui/ux",
    "figma": "figma design", "adobe xd": "xd",
    "photoshop": "adobe photoshop", "illustrator": "adobe illustrator",
    # QA
    "qa": "quality assurance", "quality assurance": "qa",
    "sdet": "qa automation", "selenium": "selenium webdriver",
    "manual testing": "manual qa", "automation testing": "test automation",
    # Other
    "rpa": "robotic process automation", "robotic process automation": "rpa",
    "rest api": "rest", "restful": "rest", "rest": "restful api",
    "graphql": "graph ql",
    "agile": "agile methodology", "scrum": "scrum master",
    "kanban": "lean kanban",
}

# Build bidirectional lookup
_SKILL_SYNONYMS = {}
for k, v in _SKILL_SYNONYMS_RAW.items():
    _SKILL_SYNONYMS[k.lower()] = v.lower()
    _SKILL_SYNONYMS[v.lower()] = k.lower()

# ---------------------------------------------------------------------------
# Skill category groups — partial credit for related skills
# ---------------------------------------------------------------------------
_SKILL_CATEGORIES = {
    "frontend": {"react", "angular", "vue", "svelte", "html", "css", "sass", "tailwind",
                 "bootstrap", "jquery", "nextjs", "nuxtjs", "gatsby", "remix"},
    "backend": {"nodejs", "django", "flask", "fastapi", "spring", "express", "rails",
                "laravel", "php", ".net", "aspnet", "nestjs"},
    "programming": {"python", "java", "javascript", "typescript", "c++", "c#", "go",
                    "rust", "ruby", "kotlin", "swift", "scala", "php", "r"},
    "cloud": {"aws", "azure", "gcp", "heroku", "digitalocean", "cloudflare"},
    "database": {"mysql", "postgresql", "mongodb", "redis", "cassandra", "dynamodb",
                 "mssql", "oracle", "sqlite", "elasticsearch", "firebase"},
    "devops": {"docker", "kubernetes", "terraform", "ansible", "jenkins", "github actions",
               "gitlab ci", "circleci", "prometheus", "grafana", "nginx"},
    "data_science": {"machine learning", "deep learning", "nlp", "computer vision",
                     "tensorflow", "pytorch", "pandas", "numpy", "scikit-learn",
                     "data analysis", "statistics", "r", "spark"},
    "sales": {"b2b sales", "b2c sales", "channel sales", "distribution sales",
              "territory management", "dealer management", "key account management",
              "business development", "lead generation", "fmcg sales", "institutional sales"},
    "marketing": {"digital marketing", "seo", "sem", "social media marketing",
                  "content marketing", "email marketing", "google ads", "facebook ads",
                  "brand management", "market research"},
    "finance": {"accounting", "taxation", "gst", "tds", "audit", "budgeting",
                "financial analysis", "mis", "erp", "sap", "tally"},
    "design": {"figma", "photoshop", "illustrator", "ui/ux", "sketch",
               "adobe xd", "canva", "invision"},
}


def _get_skill_category(skill: str) -> str:
    s = skill.lower().strip()
    for cat, members in _SKILL_CATEGORIES.items():
        if s in members or any(s in m or m in s for m in members):
            return cat
    return "other"


# ---------------------------------------------------------------------------
# Location matching — Indian city/state proximity
# ---------------------------------------------------------------------------
_CITY_STATE_MAP = {
    "mumbai": "maharashtra", "pune": "maharashtra", "nagpur": "maharashtra", "nashik": "maharashtra",
    "delhi": "delhi ncr", "new delhi": "delhi ncr", "noida": "delhi ncr", "gurgaon": "delhi ncr",
    "gurugram": "delhi ncr", "faridabad": "delhi ncr", "ghaziabad": "delhi ncr",
    "bangalore": "karnataka", "bengaluru": "karnataka", "mysore": "karnataka",
    "hyderabad": "telangana", "secunderabad": "telangana",
    "chennai": "tamil nadu", "coimbatore": "tamil nadu", "madurai": "tamil nadu",
    "kolkata": "west bengal", "howrah": "west bengal",
    "ahmedabad": "gujarat", "surat": "gujarat", "vadodara": "gujarat", "rajkot": "gujarat",
    "jaipur": "rajasthan", "udaipur": "rajasthan", "jodhpur": "rajasthan",
    "lucknow": "uttar pradesh", "kanpur": "uttar pradesh", "agra": "uttar pradesh",
    "chandigarh": "punjab", "ludhiana": "punjab", "amritsar": "punjab",
    "bhopal": "madhya pradesh", "indore": "madhya pradesh",
    "patna": "bihar", "ranchi": "jharkhand",
    "kochi": "kerala", "thiruvananthapuram": "kerala",
    "bhubaneswar": "odisha", "visakhapatnam": "andhra pradesh", "vijayawada": "andhra pradesh",
    "dehradun": "uttarakhand", "srinagar": "jammu & kashmir",
    "goa": "goa", "panaji": "goa", "raipur": "chhattisgarh",
    "remote": "remote", "pan india": "remote", "work from home": "remote", "wfh": "remote",
}

_METRO_CITIES = {"mumbai", "delhi", "bangalore", "bengaluru", "hyderabad", "chennai",
                 "kolkata", "pune", "ahmedabad", "gurgaon", "gurugram", "noida"}


def _calc_location_fit(candidate_data: Dict, job_data: Dict) -> float:
    """Score 0-100 for location alignment."""
    cand_loc = (candidate_data.get("location") or candidate_data.get("current_location") or "").lower().strip()
    job_loc = (job_data.get("location") or "").lower().strip()

    if not cand_loc or not job_loc:
        return 55.0  # Unknown — slightly below neutral

    if "remote" in job_loc or "remote" in cand_loc or "pan india" in job_loc:
        return 90.0

    # Exact city match
    if cand_loc == job_loc or cand_loc in job_loc or job_loc in cand_loc:
        return 95.0

    # Same state/region
    cand_state = _CITY_STATE_MAP.get(cand_loc, cand_loc)
    job_state = _CITY_STATE_MAP.get(job_loc, job_loc)
    if cand_state == job_state:
        return 80.0

    # Both metro cities — more flexible relocation
    if cand_loc in _METRO_CITIES and job_loc in _METRO_CITIES:
        return 55.0

    return 35.0  # Different region


# ---------------------------------------------------------------------------
# TF-IDF text similarity (free, no API)
# ---------------------------------------------------------------------------
def _calc_ctc_fit(candidate_data: Dict, job_data: Dict) -> float:
    """Score 0-100 for CTC/salary alignment."""
    cand_ctc = candidate_data.get("current_salary") or candidate_data.get("current_ctc")
    if cand_ctc is not None:
        try:
            cand_ctc = float(cand_ctc)
        except (ValueError, TypeError):
            cand_ctc = None

    sal_min = job_data.get("salary_min") or job_data.get("ctc_min")
    sal_max = job_data.get("salary_max") or job_data.get("ctc_max")
    if sal_min is not None:
        try:
            sal_min = float(sal_min)
        except (ValueError, TypeError):
            sal_min = None
    if sal_max is not None:
        try:
            sal_max = float(sal_max)
        except (ValueError, TypeError):
            sal_max = None

    if cand_ctc is None or (sal_min is None and sal_max is None):
        return 55.0  # Unknown — slightly below neutral

    if sal_min and sal_max:
        if sal_min <= cand_ctc <= sal_max:
            return 95.0
        elif cand_ctc < sal_min:
            # Under budget — still good
            return 80.0
        else:
            # Over budget
            overshoot_pct = ((cand_ctc - sal_max) / sal_max) * 100 if sal_max > 0 else 50
            if overshoot_pct <= 10:
                return 70.0
            elif overshoot_pct <= 25:
                return 50.0
            elif overshoot_pct <= 50:
                return 30.0
            return 15.0
    elif sal_max:
        if cand_ctc <= sal_max:
            return 90.0
        overshoot_pct = ((cand_ctc - sal_max) / sal_max) * 100 if sal_max > 0 else 50
        return max(15.0, 80.0 - overshoot_pct)
    elif sal_min:
        if cand_ctc >= sal_min:
            return 90.0
        return 50.0

    return 55.0


def _calc_notice_fit(candidate_data: Dict) -> float:
    """Score 0-100 for notice period desirability."""
    np_val = candidate_data.get("notice_period") or candidate_data.get("notice_period_days")
    if not np_val:
        return 55.0  # Unknown

    np_str = str(np_val).lower().strip()

    # Immediate / serving notice
    if any(k in np_str for k in ["immediate", "0", "serving", "buyout"]):
        return 95.0

    # Extract days
    days = None
    m = re.search(r'(\d+)\s*day', np_str)
    if m:
        days = int(m.group(1))
    else:
        m = re.search(r'(\d+)\s*month', np_str)
        if m:
            days = int(m.group(1)) * 30
        else:
            m = re.search(r'(\d+)\s*week', np_str)
            if m:
                days = int(m.group(1)) * 7
            else:
                try:
                    days = int(float(np_str))
                except (ValueError, TypeError):
                    pass

    if days is None:
        return 55.0

    if days <= 15:
        return 95.0
    elif days <= 30:
        return 85.0
    elif days <= 60:
        return 65.0
    elif days <= 90:
        return 45.0
    else:
        return 25.0


def _calc_stability(candidate_data: Dict) -> float:
    """Score 0-100 for job stability based on work history."""
    work_exp = candidate_data.get("work_experience") or candidate_data.get("experience") or []
    if not work_exp or not isinstance(work_exp, list):
        return 60.0  # Unknown — neutral

    num_jobs = len(work_exp)
    total_exp = get_experience_years(candidate_data)

    if num_jobs <= 1:
        return 90.0  # Single employer — very stable

    if total_exp <= 0:
        return 60.0

    avg_tenure = total_exp / num_jobs

    if avg_tenure >= 4:
        return 95.0
    elif avg_tenure >= 2.5:
        return 85.0
    elif avg_tenure >= 1.5:
        return 70.0
    elif avg_tenure >= 1.0:
        return 50.0
    else:
        return 25.0  # Frequent job hopper


def _tfidf_similarity(text_a: str, text_b: str) -> float:
    """Simple TF-IDF cosine similarity between two texts. Returns 0-100."""
    if not text_a or not text_b:
        return 0.0

    import math
    stop_words = {"the","a","an","is","are","was","were","be","been","being","have","has",
                  "had","do","does","did","will","would","shall","should","may","might",
                  "can","could","and","but","or","nor","not","so","yet","both","either",
                  "neither","each","every","all","any","few","more","most","other","some",
                  "such","no","only","own","same","than","too","very","in","on","at","to",
                  "for","of","with","by","from","as","into","through","during","before",
                  "after","above","below","between","out","off","over","under","again",
                  "further","then","once","here","there","when","where","why","how","what",
                  "which","who","whom","this","that","these","those","i","me","my","we",
                  "our","you","your","he","him","his","she","her","it","its","they","them"}

    def tokenize(text):
        return [w for w in re.findall(r'\b[a-z]{2,}\b', text.lower()) if w not in stop_words]

    tokens_a = tokenize(text_a)
    tokens_b = tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0

    all_tokens = set(tokens_a) | set(tokens_b)
    freq_a = {t: tokens_a.count(t) for t in set(tokens_a)}
    freq_b = {t: tokens_b.count(t) for t in set(tokens_b)}

    dot = sum(freq_a.get(t, 0) * freq_b.get(t, 0) for t in all_tokens)
    mag_a = math.sqrt(sum(v**2 for v in freq_a.values()))
    mag_b = math.sqrt(sum(v**2 for v in freq_b.values()))

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return min((dot / (mag_a * mag_b)) * 100, 100.0)


# ---------------------------------------------------------------------------
# Data completeness score — identify "maybe" candidates
# ---------------------------------------------------------------------------
def _data_completeness(candidate_data: Dict) -> Tuple[float, list]:
    """Return (completeness %, list of missing fields)."""
    fields = {
        "name": bool(candidate_data.get("name")),
        "email": bool(candidate_data.get("email")),
        "phone": bool(candidate_data.get("phone")),
        "skills": bool(candidate_data.get("skills") or candidate_data.get("key_skills")),
        "experience": bool(get_experience_years(candidate_data) > 0),
        "ctc": bool(candidate_data.get("current_salary") or candidate_data.get("current_ctc")),
        "notice_period": bool(candidate_data.get("notice_period")),
        "location": bool(candidate_data.get("location") or candidate_data.get("current_location")),
        "designation": bool(candidate_data.get("current_designation") or candidate_data.get("designation")),
        "employer": bool(candidate_data.get("current_employer")),
    }
    filled = sum(1 for v in fields.values() if v)
    missing = [k for k, v in fields.items() if not v]
    return (filled / len(fields)) * 100, missing


def _resolve_skill_synonyms(skill: str) -> set:
    """Return a set of all synonym forms for a skill."""
    s = skill.lower().strip()
    synonyms = {s}
    if s in _SKILL_SYNONYMS:
        synonyms.add(_SKILL_SYNONYMS[s])
    return synonyms


def _skill_matches(job_skill: str, candidate_tokens: set, text_fields: str) -> bool:
    """Check if a job skill matches any candidate token using synonyms + fuzzy."""
    variants = _resolve_skill_synonyms(job_skill)
    for v in variants:
        if v in candidate_tokens:
            return True
        if any(v in ct or ct in v for ct in candidate_tokens if len(ct) > 2):
            return True
        if v in text_fields:
            return True
    return False


def _skill_category_match(job_skill: str, candidate_tokens: set) -> bool:
    """Partial credit: candidate has a skill in the same category as the job skill."""
    cat = _get_skill_category(job_skill)
    if cat == "other":
        return False
    category_skills = _SKILL_CATEGORIES.get(cat, set())
    return any(cs in category_skills or any(cs in ms or ms in cs for ms in category_skills)
               for cs in candidate_tokens if len(cs) > 2)


def calculate_fast_match_score(
    candidate_data: Dict,
    job_data: Dict,
    job_embedding: Optional[List[float]] = None,
    candidate_embedding: Optional[List[float]] = None,
) -> Dict:
    """
    Multi-dimensional match score WITHOUT an LLM call.
    Dimensions: Skills (35%), Experience (15%), CTC (12%), Location (10%),
    Notice (8%), Stability (8%), Text Similarity (12%).
    Returns 'maybe' flag when data is incomplete.
    """
    candidate_skill_tokens = get_all_skill_tokens(candidate_data)
    summary_text = get_summary(candidate_data)
    designation  = get_designation(candidate_data)

    text_fields = " ".join(filter(None, [
        summary_text, designation,
        candidate_data.get("headline", ""),
        " ".join(candidate_data.get("certifications") or []),
    ])).lower()

    cand_exp = get_experience_years(candidate_data)

    job_skills_required = [s.lower().strip() for s in (job_data.get("required_skills") or []) if s.strip()]
    job_skills_preferred = [s.lower().strip() for s in (job_data.get("preferred_skills") or []) if s.strip()]
    all_job_skills = list(dict.fromkeys(job_skills_required + job_skills_preferred))

    # --- Skill matching: exact + synonym + category ---
    matched_skills = []
    partial_skills = []
    for js in all_job_skills:
        if _skill_matches(js, candidate_skill_tokens, text_fields):
            matched_skills.append(js)
        elif _skill_category_match(js, candidate_skill_tokens):
            partial_skills.append(js)
    matched_skills = list(dict.fromkeys(matched_skills))
    missing_skills = [s for s in job_skills_required if s not in matched_skills][:5]

    skill_score = 50.0
    if all_job_skills:
        full_match_ratio = len(matched_skills) / len(all_job_skills)
        partial_ratio = len(partial_skills) / len(all_job_skills)
        skill_score = min((full_match_ratio * 100 + partial_ratio * 30), 100.0)

    # --- Experience score ---
    min_exp = job_data.get("experience_min")
    max_exp = job_data.get("experience_max")
    exp_score = 60.0
    if min_exp is not None:
        min_exp_f = float(min_exp)
        max_exp_f = float(max_exp) if max_exp else min_exp_f + 10
        if min_exp_f <= cand_exp <= max_exp_f:
            exp_score = 95.0
        elif cand_exp >= min_exp_f:
            overshoot = cand_exp - max_exp_f
            exp_score = max(50.0, 90.0 - overshoot * 5)
        else:
            diff = min_exp_f - cand_exp
            exp_score = max(10.0, 70.0 - diff * 15)

    # --- CTC fit ---
    ctc_score = _calc_ctc_fit(candidate_data, job_data)

    # --- Location fit ---
    location_score = _calc_location_fit(candidate_data, job_data)

    # --- Notice period fit ---
    notice_score = _calc_notice_fit(candidate_data)

    # --- Stability score ---
    stability_score = _calc_stability(candidate_data)

    # --- TF-IDF text similarity (free semantic matching) ---
    job_text = " ".join(filter(None, [
        job_data.get("title", ""),
        job_data.get("key_requirements_summary", ""),
        " ".join(job_data.get("required_skills") or []),
    ]))
    cand_text = " ".join(filter(None, [
        summary_text, designation, text_fields,
    ]))
    tfidf_score = _tfidf_similarity(job_text, cand_text)

    # --- Data completeness → maybe flag ---
    completeness, missing_fields = _data_completeness(candidate_data)
    is_maybe = completeness < 60

    # --- Weighted total ---
    total_score = int(
        skill_score * 0.35
        + exp_score * 0.15
        + ctc_score * 0.12
        + location_score * 0.10
        + notice_score * 0.08
        + stability_score * 0.08
        + tfidf_score * 0.12
    )

    # --- Build explanation ---
    parts = [f"{len(matched_skills)}/{len(all_job_skills)} skills"]
    if partial_skills:
        parts.append(f"+{len(partial_skills)} related")
    parts.append(f"{cand_exp:.1f}yr exp")

    cand_loc = (candidate_data.get("location") or candidate_data.get("current_location") or "").strip()
    job_loc = (job_data.get("location") or "").strip()
    if location_score >= 90:
        parts.append("loc match")
    elif location_score < 50 and cand_loc and job_loc:
        parts.append(f"loc mismatch ({cand_loc})")

    if ctc_score >= 85:
        parts.append("within budget")
    elif ctc_score < 50:
        parts.append("CTC over budget")

    if notice_score >= 85:
        parts.append("quick joiner")
    elif notice_score < 50:
        parts.append("long notice")

    if stability_score < 50:
        parts.append("frequent hops")

    if is_maybe:
        parts.append(f"incomplete({', '.join(missing_fields[:3])})")

    def _fmt(s):
        return s.title() if len(s) > 3 else s.upper()

    return {
        "score": max(0, min(total_score, 100)),
        "skill_match_score": int(min(skill_score, 100)),
        "experience_match_score": int(min(exp_score, 100)),
        "ctc_fit_score": int(min(ctc_score, 100)),
        "location_fit_score": int(min(location_score, 100)),
        "notice_fit_score": int(min(notice_score, 100)),
        "stability_score": int(min(stability_score, 100)),
        "tfidf_score": round(tfidf_score, 1),
        "semantic_score": round(tfidf_score, 1),  # Alias for backward compat
        "matched_skills": [_fmt(s) for s in matched_skills[:10]],
        "partial_skills": [_fmt(s) for s in partial_skills[:5]],
        "missing_skills": [_fmt(s) for s in missing_skills],
        "explanation": " | ".join(parts),
        "is_maybe": is_maybe,
        "data_completeness": round(completeness, 0),
        "missing_data_fields": missing_fields,
    }


# ---------------------------------------------------------------------------
# Text extraction helper (used by job_queue handlers)
# ---------------------------------------------------------------------------

def extract_text_from_file(content: bytes, filename: str) -> str:
    """
    Extract plain text from PDF/DOC/DOCX file bytes.
    Uses PyMuPDF (fitz) as primary PDF extractor, antiword for .doc, docx2txt for .docx.
    Falls back to OCR (Tesseract) for image-based/scanned PDFs.
    All library imports are at module level to prevent thread import-lock deadlocks.
    """
    ext = _Path(filename).suffix.lower()
    text = ""

    try:
        if ext == ".pdf":
            # Primary: PyMuPDF (fitz)
            if _fitz:
                try:
                    doc = _fitz.open(stream=content, filetype="pdf")
                    text = "\n".join(page.get_text() for page in doc)
                    doc.close()
                except Exception as e1:
                    logger.warning(f"fitz extraction failed for {filename}: {e1}")

            # Fallback: pypdf
            if not text or len(text.strip()) < 30:
                if _pypdf:
                    try:
                        reader = _pypdf.PdfReader(_io.BytesIO(content))
                        text = "\n".join(
                            page.extract_text() or "" for page in reader.pages
                        )
                    except Exception:
                        pass

            # Phase 54.7 — Table-aware fallback (pdfplumber)
            # Triggered when standard text extractors yield a tiny amount
            # of text (< 500 chars). This catches resumes where contact
            # info / experience / education is laid out inside tables or
            # multi-column boxes that fitz / pypdf collapse into noise.
            # Output preserves table row structure so the downstream LLM
            # parser sees clean "Header | Value" rows.
            if (not text or len(text.strip()) < 500) and _pdfplumber:
                try:
                    pre_len = len(text.strip()) if text else 0
                    parts: list[str] = []
                    with _pdfplumber.open(_io.BytesIO(content)) as pdf:
                        # cap at first 6 pages — beyond that resumes are
                        # almost always cover letters / appendices.
                        for page in pdf.pages[:6]:
                            page_text = page.extract_text(
                                x_tolerance=2, y_tolerance=2,
                            ) or ""
                            parts.append(page_text)
                            for table in (page.extract_tables() or []):
                                for row in table:
                                    cells = [str(c).strip() for c in row if c]
                                    if cells:
                                        parts.append(" | ".join(cells))
                    pp_text = "\n".join(p for p in parts if p and p.strip())
                    if len(pp_text.strip()) > pre_len:
                        logger.info(
                            f"[pdfplumber] table-aware fallback used for "
                            f"{filename}: {pre_len} -> {len(pp_text.strip())} chars"
                        )
                        text = pp_text
                except Exception as e:
                    logger.warning(
                        f"[pdfplumber] table-aware fallback failed for "
                        f"{filename}: {e}"
                    )

            # OCR fallback for image-based/scanned PDFs
            if not text or len(text.strip()) < 30:
                logger.info(f"[OCR] Text extraction got {len(text.strip())} chars for {filename} — trying OCR")
                if _convert_from_bytes and _pytesseract:
                    try:
                        images = _convert_from_bytes(content, dpi=200, first_page=1, last_page=5)
                        ocr_text = ""
                        for i, img in enumerate(images):
                            page_text = _pytesseract.image_to_string(img, lang='eng')
                            ocr_text += page_text + "\n"
                        if ocr_text.strip():
                            text = ocr_text.strip()
                            logger.info(f"[OCR] Success — extracted {len(text)} chars from {filename}")
                    except Exception as ocr_err:
                        logger.warning(f"[OCR] Failed for {filename}: {ocr_err}")

        elif ext == ".doc":
            # Old Word binary format — needs antiword
            tmp_path = None
            try:
                with _tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                result = _subprocess.run(
                    ["antiword", tmp_path],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0 and result.stdout.strip():
                    text = result.stdout
                else:
                    raise ValueError(f"antiword returned code {result.returncode}")
            except FileNotFoundError:
                logger.warning(f"antiword not installed — cannot extract .doc file {filename}")
                if _docx2txt:
                    try:
                        text = _docx2txt.process(_io.BytesIO(content))
                    except Exception:
                        pass
            except Exception as e1:
                logger.warning(f"antiword failed for {filename}: {e1}")
                if _docx2txt:
                    try:
                        text = _docx2txt.process(_io.BytesIO(content))
                    except Exception:
                        pass
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

        elif ext == ".docx":
            # Modern Word format — docx2txt first (handles paragraphs + tables)
            if _docx2txt:
                try:
                    text = _docx2txt.process(_io.BytesIO(content)) or ""
                except Exception as e1:
                    logger.warning(f"docx2txt failed for {filename}: {e1}")

            # Fallback: python-docx with explicit table extraction
            if not text or len(text.strip()) < 30:
                if _docx:
                    try:
                        doc = _docx.Document(_io.BytesIO(content))
                        parts = [p.text for p in doc.paragraphs if p.text.strip()]
                        for table in doc.tables:
                            for row in table.rows:
                                for cell in row.cells:
                                    if cell.text.strip():
                                        parts.append(cell.text.strip())
                        text = "\n".join(parts)
                    except Exception as e2:
                        logger.warning(f"python-docx fallback failed for {filename}: {e2}")

    except Exception as e:
        logger.warning(f"Text extraction failed for {filename}: {e}")

    return text.strip()
