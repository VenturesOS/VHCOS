"""
AI Matching Engine Service for VHC Talent OS
Uses GPT-5.2 via Emergent LLM for resume/JD parsing and matching.
Includes fast (non-LLM) scoring for high-concurrency scenarios.

FIXED:
- Single canonical parse_resume_with_ai() implementation
- normalize_candidate() applied to every parse result
- calculate_fast_match_score() reads both canonical + alias field names
- calculate_candidate_job_match() reads both canonical + alias field names
"""
import os
import re
import json
import hashlib
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone
import uuid
from emergentintegrations.llm.chat import LlmChat, UserMessage
import logging

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

logger = logging.getLogger(__name__)

EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")


def get_chat_client(system_msg: str = "You are an expert recruiter AI that extracts structured data from text."):
    """Get Emergent Chat client for GPT-5.2"""
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
        chat = get_chat_client(
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

        response = await chat.send_message(UserMessage(text=prompt))

        response_text = (response or "").strip()
        if not response_text:
            logger.error("[RESUME PARSE] LLM returned empty response")
            return {"success": False, "error": "LLM returned empty response"}

        logger.info(f"[RESUME PARSE] Raw response (first 500): {response_text[:500]}")

        json_str = extract_json_from_llm_response(response_text)
        logger.info(f"[RESUME PARSE] Extracted JSON (first 300): {json_str[:300]}")

        parsed = json.loads(json_str)

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
        chat = get_chat_client(
            "You are an expert job description parser. Extract structured requirements accurately."
        )

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

        response = await chat.send_message(UserMessage(text=prompt))

        response_text = (response or "").strip()
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

        chat = get_chat_client(
            "You are an expert recruiter AI that evaluates candidate-job fit."
        )

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

        logger.info("[MATCH CALC] Sending prompt to GPT-5.2")

        response = await chat.send_message(UserMessage(text=prompt))

        response_text = (response or "").strip()
        if not response_text:
            logger.error("[MATCH CALC] LLM returned empty response")
            return {
                "score": 0,
                "matched": False,
                "error": "LLM returned empty response",
                "explanation": "Unable to calculate match — no AI response",
            }

        json_str = extract_json_from_llm_response(response_text)
        match_result = json.loads(json_str)
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
        req_text  = job_doc.get("requirements", "") or ""
        desc_text = job_doc.get("description", "")  or ""
        combined  = f"{req_text} {desc_text}".strip()

        if req_text:
            result["required_skills"] = [s.strip() for s in req_text.split(",") if s.strip()]

        result["experience_min"]          = job_doc.get("experience_min") or job_doc.get("min_experience")
        result["experience_max"]          = job_doc.get("experience_max") or job_doc.get("max_experience")
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

    return result


def calculate_fast_match_score(
    candidate_data: Dict,
    job_data: Dict,
    job_embedding: Optional[List[float]] = None,
    candidate_embedding: Optional[List[float]] = None,
) -> Dict:
    """
    Calculate match score WITHOUT an LLM call.
    FIXED: reads both canonical (key_skills, profile_summary, total_experience_years)
           and alias (skills, summary, experience_years) field names via
           schema_normalizer helpers.
    """
    # Use normalizer helpers — transparent to schema variant
    candidate_skill_tokens = get_all_skill_tokens(candidate_data)
    summary_text = get_summary(candidate_data)
    designation  = get_designation(candidate_data)

    text_fields = " ".join(filter(None, [
        summary_text,
        designation,
        candidate_data.get("headline", ""),
    ])).lower()

    cand_exp = get_experience_years(candidate_data)

    job_skills_required = [s.lower() for s in (job_data.get("required_skills") or [])]
    job_skills_preferred = [s.lower() for s in (job_data.get("preferred_skills") or [])]
    all_job_skills = list(dict.fromkeys(job_skills_required + job_skills_preferred))

    # Fuzzy skill matching (substring check in tokens + text fields)
    matched_skills = []
    for js in all_job_skills:
        matched = any(js in cs or cs in js for cs in candidate_skill_tokens)
        if not matched:
            matched = js in text_fields
        if matched:
            matched_skills.append(js)
    matched_skills = list(dict.fromkeys(matched_skills))
    missing_skills = [s for s in job_skills_required if s not in matched_skills][:5]

    skill_score = (
        (len(matched_skills) / max(len(all_job_skills), 1)) * 100
        if all_job_skills else 50.0
    )

    # Experience score
    min_exp = job_data.get("experience_min")
    max_exp = job_data.get("experience_max")
    exp_score = 70.0
    if min_exp is not None:
        min_exp_f = float(min_exp)
        if cand_exp >= min_exp_f:
            exp_score = 90.0
            if max_exp is not None and cand_exp > float(max_exp) + 3:
                exp_score = 60.0
        else:
            diff = min_exp_f - cand_exp
            exp_score = max(0.0, 70.0 - diff * 15)

    # Semantic score
    semantic_score = None
    if job_embedding and candidate_embedding:
        try:
            from services.embeddings import embedding_service
            semantic_score = (
                embedding_service.cosine_similarity(job_embedding, candidate_embedding) * 100
            )
        except Exception:
            pass

    # Weighted total
    if semantic_score is not None:
        total_score = int(skill_score * 0.40 + exp_score * 0.25 + semantic_score * 0.25 + 10)
    else:
        total_score = int(skill_score * 0.50 + exp_score * 0.30 + 20)

    explanation = (
        f"Quick match: {len(matched_skills)}/{len(all_job_skills)} skills matched, "
        f"{cand_exp:.1f} yrs exp"
    )
    if semantic_score is not None:
        explanation += f", {semantic_score:.0f}% semantic similarity"

    def _fmt(s):
        return s.title() if len(s) > 3 else s.upper()

    return {
        "score": min(total_score, 100),
        "skill_match_score": int(min(skill_score, 100)),
        "experience_match_score": int(min(exp_score, 100)),
        "semantic_score": round(semantic_score, 1) if semantic_score is not None else None,
        "matched_skills": [_fmt(s) for s in matched_skills[:10]],
        "missing_skills": [_fmt(s) for s in missing_skills],
        "explanation": explanation,
    }


# ---------------------------------------------------------------------------
# Text extraction helper (used by job_queue handlers)
# ---------------------------------------------------------------------------

def extract_text_from_file(content: bytes, filename: str) -> str:
    """
    Extract plain text from PDF/DOC/DOCX file bytes.
    Returns empty string on failure.
    """
    import io
    from pathlib import Path

    ext = Path(filename).suffix.lower()
    text = ""

    try:
        if ext == ".pdf":
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(content)) as pdf:
                    text = "\n".join(
                        page.extract_text() or "" for page in pdf.pages
                    )
            except ImportError:
                try:
                    import PyPDF2
                    reader = PyPDF2.PdfReader(io.BytesIO(content))
                    text = "\n".join(
                        page.extract_text() or "" for page in reader.pages
                    )
                except Exception:
                    pass

        elif ext in (".doc", ".docx"):
            try:
                import docx
                doc = docx.Document(io.BytesIO(content))
                text = "\n".join(para.text for para in doc.paragraphs)
            except Exception:
                pass

    except Exception as e:
        logger.warning(f"Text extraction failed for {filename}: {e}")

    return text.strip()
