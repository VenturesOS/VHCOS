"""
AI Matching Engine Service for VHC Talent OS
Uses GPT-5.2 via Emergent LLM for resume/JD parsing and matching.
Includes fast (non-LLM) scoring for high-concurrency scenarios.
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

logger = logging.getLogger(__name__)

# Initialize Emergent LLM
EMERGENT_KEY = os.environ.get('EMERGENT_LLM_KEY')

def get_chat_client(system_msg: str = "You are an expert recruiter AI that extracts structured data from text."):
    """Get Emergent Chat client for GPT-5.2"""
    return LlmChat(
        api_key=EMERGENT_KEY,
        session_id=str(uuid.uuid4()),
        system_message=system_msg
    )

async def parse_resume_with_ai(resume_text: str) -> Dict:
    """
    Parse resume text using GPT-5.2 to extract structured data.
    Returns structured candidate data matching the unified profile schema.
    """
    try:
        chat = get_chat_client("You are an expert resume parser. Extract structured data from resumes with maximum detail and accuracy. Never fabricate data — only extract what is present.")
        
        prompt = f"""Parse the following resume and extract structured data. Return ONLY valid JSON with this exact structure.
IMPORTANT: Only include data explicitly found in the resume. Use null for missing fields. Never infer or fabricate.

{{
    "name": "full name",
    "email": "email or null",
    "phone": "phone or null",
    "headline": "professional title/headline",
    "profile_summary": "professional summary (2-3 sentences from resume objective/summary section)",
    "current_company": "current or most recent employer or null",
    "current_designation": "current or most recent job title or null",
    "current_industry": "industry if determinable or null",
    "total_experience_years": number or null,
    "location": "city, state/country or null",
    "date_of_birth": "DOB if found or null",
    "gender": "gender if found or null",
    "key_skills": ["skill1", "skill2", ...],
    "it_skills": [{{"name": "tool/tech name", "version": "version or null", "experience": "years or null"}}],
    "work_experience": [
        {{
            "designation": "job title",
            "company": "company name",
            "from_date": "start date (MMM YYYY) or null",
            "to_date": "end date (MMM YYYY) or null",
            "is_current": true/false,
            "description": "responsibilities/achievements summary"
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
    "certifications": ["certification name 1", "certification name 2"],
    "projects": [{{"title": "project name", "description": "brief description"}}],
    "languages": [{{"language": "language name", "proficiency": "level or null"}}],
    "online_profiles": [{{"platform": "LinkedIn/GitHub/etc", "url": "URL"}}],
    "preferred_locations": ["location1", "location2"]
}}

Resume text:
{resume_text[:8000]}"""
        
        logger.info(f"[RESUME PARSE] Sending prompt to GPT-5.2, length: {len(prompt)}")
        
        response = await chat.send_message(
            user_message=UserMessage(text=prompt)
        )
        
        logger.info(f"[RESUME PARSE] Raw LLM response: {response[:500] if response else 'EMPTY'}")
        
        # Extract JSON from response - response is the text directly
        response_text = response.strip() if response else ""
        
        if not response_text:
            logger.error("[RESUME PARSE] LLM returned empty response!")
            return {"success": False, "error": "LLM returned empty response"}
        
        # Try to find JSON in response
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0]
        else:
            json_str = response_text
        
        logger.info(f"[RESUME PARSE] Extracted JSON string: {json_str[:300] if json_str else 'EMPTY'}")
        
        parsed = json.loads(json_str.strip())
        
        # Backwards-compat: map old field names if present
        if "summary" in parsed and "profile_summary" not in parsed:
            parsed["profile_summary"] = parsed.pop("summary")
        if "skills" in parsed and "key_skills" not in parsed:
            parsed["key_skills"] = parsed.pop("skills")
        if "experience" in parsed and "work_experience" not in parsed:
            raw_exp = parsed.pop("experience")
            mapped_exp = []
            for e in (raw_exp or []):
                if isinstance(e, dict):
                    mapped_exp.append({
                        "designation": e.get("title") or e.get("designation"),
                        "company": e.get("company"),
                        "from_date": e.get("from_date") or e.get("start_date"),
                        "to_date": e.get("to_date") or e.get("end_date"),
                        "is_current": e.get("is_current", False),
                        "description": e.get("description") or e.get("duration"),
                    })
            parsed["work_experience"] = mapped_exp
        
        logger.info(f"[RESUME PARSE] Successfully parsed JSON with keys: {list(parsed.keys())}")
        return {"success": True, "data": parsed}
        
    except json.JSONDecodeError as e:
        logger.error(f"[RESUME PARSE] JSON parse error: {e}, response was: {response_text[:500] if response_text else 'EMPTY'}")
        return {"success": False, "error": f"Failed to parse AI response: {str(e)}"}
    except Exception as e:
        logger.error(f"[RESUME PARSE] Error: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}


async def parse_job_description_with_ai(jd_text: str) -> Dict:
    """
    Parse job description using GPT-5.2 to extract structured requirements.
    """
    try:
        chat = get_chat_client("You are an expert job description parser. Extract structured requirements accurately.")
        
        prompt = f"""Parse the following job description and extract structured requirements. Return ONLY valid JSON with this exact structure:
{{
    "title": "job title",
    "department": "department if mentioned or null",
    "location": "location requirement or null",
    "job_type": "full-time/part-time/contract/remote",
    "experience_min": minimum years as number or 0,
    "experience_max": maximum years as number or null,
    "required_skills": ["must have skill1", "must have skill2", ...],
    "preferred_skills": ["nice to have skill1", ...],
    "required_qualifications": ["degree requirement", "certification", ...],
    "responsibilities": ["responsibility1", "responsibility2", ...],
    "salary_min": minimum salary as number or null,
    "salary_max": maximum salary as number or null,
    "key_requirements_summary": "2-3 sentence summary of key requirements"
}}

Job Description:
{jd_text[:8000]}"""
        
        logger.info(f"[JD PARSE] Sending prompt to GPT-5.2, length: {len(prompt)}")
        
        response = await chat.send_message(
            user_message=UserMessage(text=prompt)
        )
        
        logger.info(f"[JD PARSE] Raw LLM response: {response[:500] if response else 'EMPTY'}")
        
        # Response is the text directly
        response_text = response.strip() if response else ""
        
        if not response_text:
            logger.error("[JD PARSE] LLM returned empty response!")
            return {"success": False, "error": "LLM returned empty response"}
        
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0]
        else:
            json_str = response_text
        
        logger.info(f"[JD PARSE] Extracted JSON string: {json_str[:300] if json_str else 'EMPTY'}")
        
        parsed = json.loads(json_str.strip())
        logger.info(f"[JD PARSE] Successfully parsed JSON with keys: {list(parsed.keys())}")
        return {"success": True, "data": parsed}
        
    except json.JSONDecodeError as e:
        logger.error(f"[JD PARSE] JSON parse error: {e}")
        return {"success": False, "error": f"Failed to parse AI response: {str(e)}"}
    except Exception as e:
        logger.error(f"[JD PARSE] Error: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}


async def calculate_candidate_job_match(
    candidate_data: Dict,
    job_data: Dict,
    must_have_filters: Optional[Dict] = None
) -> Dict:
    """
    Calculate match score between candidate and job using AI.
    Returns match score (0-100) and explanation.
    """
    try:
        # First apply must-have filters (hard filters)
        if must_have_filters:
            filter_result = apply_must_have_filters(candidate_data, must_have_filters)
            if not filter_result["passed"]:
                return {
                    "score": 0,
                    "matched": False,
                    "filtered_out": True,
                    "filter_reason": filter_result["reason"],
                    "explanation": f"Candidate excluded: {filter_result['reason']}"
                }
        
        chat = get_chat_client("You are an expert recruiter AI that evaluates candidate-job fit.")
        
        prompt = f"""Analyze the match between this candidate and job. Return ONLY valid JSON:

CANDIDATE:
- Skills: {candidate_data.get('skills', [])}
- Experience Years: {candidate_data.get('experience_years', 0)}
- Education: {candidate_data.get('education', [])}
- Location: {candidate_data.get('location', 'Not specified')}
- Summary: {candidate_data.get('summary', 'Not provided')}

JOB REQUIREMENTS:
- Required Skills: {job_data.get('required_skills', [])}
- Experience Required: {job_data.get('experience_min', 0)}-{job_data.get('experience_max', 'any')} years
- Required Qualifications: {job_data.get('required_qualifications', [])}
- Location: {job_data.get('location', 'Any')}

Return JSON:
{{
    "score": number from 0-100,
    "skill_match_score": number from 0-100,
    "experience_match_score": number from 0-100,
    "education_match_score": number from 0-100,
    "matched_skills": ["skill1", "skill2"],
    "missing_skills": ["skill1", "skill2"],
    "strengths": ["strength1", "strength2"],
    "gaps": ["gap1", "gap2"],
    "recommendation": "brief recommendation",
    "explanation": "2-3 sentence explanation of the match"
}}"""
        
        logger.info("[MATCH CALC] Sending prompt to GPT-5.2")
        
        response = await chat.send_message(
            user_message=UserMessage(text=prompt)
        )
        
        logger.info(f"[MATCH CALC] Raw LLM response: {response[:500] if response else 'EMPTY'}")
        
        # Response is the text directly
        response_text = response.strip() if response else ""
        
        if not response_text:
            logger.error("[MATCH CALC] LLM returned empty response!")
            return {
                "score": 0,
                "matched": False,
                "error": "LLM returned empty response",
                "explanation": "Unable to calculate match - no AI response"
            }
        
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0]
        else:
            json_str = response_text
        
        logger.info(f"[MATCH CALC] Extracted JSON string: {json_str[:300] if json_str else 'EMPTY'}")
        
        match_result = json.loads(json_str.strip())
        match_result["matched"] = match_result.get("score", 0) >= 50
        match_result["filtered_out"] = False
        
        logger.info(f"[MATCH CALC] Successfully calculated match score: {match_result.get('score')}")
        return match_result
        
    except json.JSONDecodeError as e:
        logger.error(f"[MATCH CALC] JSON parse error: {e}")
        return {
            "score": 0,
            "matched": False,
            "error": f"JSON parse error: {str(e)}",
            "explanation": "Unable to calculate match"
        }
    except Exception as e:
        logger.error(f"[MATCH CALC] Error: {type(e).__name__}: {e}")
        return {
            "score": 0,
            "matched": False,
            "error": str(e),
            "explanation": "Unable to calculate match"
        }


def apply_must_have_filters(candidate_data: Dict, filters: Dict) -> Dict:
    """
    Apply hard filters to candidate. Returns pass/fail with reason.
    """
    # Location filter
    if filters.get("location"):
        candidate_location = (candidate_data.get("location") or "").lower()
        required_location = filters["location"].lower()
        if required_location and required_location not in candidate_location:
            return {"passed": False, "reason": f"Location mismatch: requires {filters['location']}"}
    
    # Experience filter
    if filters.get("min_experience") is not None:
        candidate_exp = candidate_data.get("experience_years", 0)
        if candidate_exp < filters["min_experience"]:
            return {"passed": False, "reason": f"Insufficient experience: requires {filters['min_experience']}+ years"}
    
    if filters.get("max_experience") is not None:
        candidate_exp = candidate_data.get("experience_years", 0)
        if candidate_exp > filters["max_experience"]:
            return {"passed": False, "reason": f"Over-experienced: max {filters['max_experience']} years"}
    
    # Mandatory skills filter
    if filters.get("mandatory_skills"):
        candidate_skills = [s.lower() for s in candidate_data.get("skills", [])]
        for skill in filters["mandatory_skills"]:
            skill_found = any(skill.lower() in cs for cs in candidate_skills)
            if not skill_found:
                return {"passed": False, "reason": f"Missing mandatory skill: {skill}"}
    
    # Qualification filter
    if filters.get("required_qualification"):
        candidate_edu = " ".join([
            f"{e.get('degree', '')} {e.get('institution', '')}"
            for e in candidate_data.get("education", [])
        ]).lower()
        if filters["required_qualification"].lower() not in candidate_edu:
            return {"passed": False, "reason": f"Missing qualification: {filters['required_qualification']}"}
    
    return {"passed": True, "reason": None}


def generate_resume_fingerprint(resume_text: str) -> str:
    """Generate a fingerprint hash for resume deduplication"""
    # Normalize text
    normalized = " ".join(resume_text.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


async def find_similar_candidate(
    db, 
    email: Optional[str] = None,
    phone: Optional[str] = None,
    resume_fingerprint: Optional[str] = None,
    name: Optional[str] = None,
    skills: Optional[List[str]] = None
) -> Optional[Dict]:
    """
    Find duplicate candidate using multiple criteria.
    Priority: email > phone > resume fingerprint > AI similarity
    """
    # Check by email (primary)
    if email:
        existing = await db.candidate_bank.find_one({"email": email.lower()}, {"_id": 0})
        if existing:
            return {"found": True, "candidate": existing, "match_type": "email"}
    
    # Check by phone
    if phone:
        normalized_phone = "".join(filter(str.isdigit, phone))
        if len(normalized_phone) >= 10:
            existing = await db.candidate_bank.find_one(
                {"phone_normalized": normalized_phone[-10:]}, 
                {"_id": 0}
            )
            if existing:
                return {"found": True, "candidate": existing, "match_type": "phone"}
    
    # Check by resume fingerprint
    if resume_fingerprint:
        existing = await db.candidate_bank.find_one(
            {"resume_fingerprints": resume_fingerprint},
            {"_id": 0}
        )
        if existing:
            return {"found": True, "candidate": existing, "match_type": "resume_fingerprint"}
    
    return {"found": False, "candidate": None, "match_type": None}


# ============== FAST (NON-LLM) SCORING FUNCTIONS ==============

def parse_job_requirements_fast(job_doc: Optional[Dict] = None, jd_text: Optional[str] = None) -> Dict:
    """
    Extract structured job requirements WITHOUT an LLM call.
    Uses the existing job document fields or basic text extraction.
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

    # If we have a structured job document, use its fields directly
    if job_doc:
        result["title"] = job_doc.get("title", "")
        result["location"] = job_doc.get("location")

        # Extract skills from requirements/description fields
        req_text = job_doc.get("requirements", "") or ""
        desc_text = job_doc.get("description", "") or ""
        combined = f"{req_text} {desc_text}".strip()

        # Skills from comma-separated requirements field
        if req_text:
            result["required_skills"] = [s.strip() for s in req_text.split(",") if s.strip()]

        # Experience from job fields
        result["experience_min"] = job_doc.get("experience_min") or job_doc.get("min_experience")
        result["experience_max"] = job_doc.get("experience_max") or job_doc.get("max_experience")
        result["key_requirements_summary"] = combined[:300]

    # If raw JD text provided, do basic keyword extraction
    if jd_text and not result["required_skills"]:
        text_lower = jd_text.lower()
        result["key_requirements_summary"] = jd_text[:300]

        # Extract experience requirements
        exp_patterns = [
            r'(\d+)\+?\s*(?:to|-)\s*(\d+)\s*years?',
            r'(\d+)\+?\s*years?\s*(?:of)?\s*experience',
            r'minimum\s*(\d+)\s*years?',
        ]
        for pat in exp_patterns:
            m = re.search(pat, text_lower)
            if m:
                groups = m.groups()
                result["experience_min"] = int(groups[0])
                if len(groups) > 1 and groups[1]:
                    result["experience_max"] = int(groups[1])
                break

        # Extract skills by looking for common tech/business keywords
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

        # Check for skills in text
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
    Calculate a match score between candidate and job WITHOUT an LLM call.
    Searches skills array, it_skills, summary, headline, and designation.
    """
    candidate_skills = [s.lower() for s in (candidate_data.get("skills") or [])]

    # Also extract skill names from it_skills objects
    for it_skill in (candidate_data.get("it_skills") or []):
        if isinstance(it_skill, dict) and it_skill.get("name"):
            candidate_skills.append(it_skill["name"].lower())
        elif isinstance(it_skill, str):
            candidate_skills.append(it_skill.lower())
    candidate_skills = list(set(candidate_skills))

    # Build a text blob from summary/headline/designation for text-based matching
    text_fields = " ".join(filter(None, [
        candidate_data.get("summary", ""),
        candidate_data.get("headline", ""),
        candidate_data.get("designation", ""),
    ])).lower()

    job_skills_required = [s.lower() for s in (job_data.get("required_skills") or [])]
    job_skills_preferred = [s.lower() for s in (job_data.get("preferred_skills") or [])]
    all_job_skills = list(set(job_skills_required + job_skills_preferred))

    # --- Skill matching (fuzzy: substring check in skills + text fields) ---
    matched_skills = []
    for js in all_job_skills:
        # Check in skills array
        for cs in candidate_skills:
            if js in cs or cs in js:
                matched_skills.append(js)
                break
        else:
            # Check in text fields (summary, headline, designation)
            if js in text_fields:
                matched_skills.append(js)
    matched_skills = list(set(matched_skills))
    missing_skills = [s for s in job_skills_required if s not in matched_skills][:5]

    skill_score = (len(matched_skills) / max(len(all_job_skills), 1)) * 100 if all_job_skills else 50

    # --- Experience matching ---
    min_exp = job_data.get("experience_min")
    max_exp = job_data.get("experience_max")
    cand_exp = candidate_data.get("experience_years") or 0
    exp_score = 70  # default
    if min_exp is not None:
        if cand_exp >= min_exp:
            exp_score = 90
            if max_exp is not None and cand_exp > max_exp + 3:
                exp_score = 60  # over-experienced
        else:
            diff = min_exp - cand_exp
            exp_score = max(0, 70 - diff * 15)

    # --- Semantic score ---
    semantic_score = None
    if job_embedding and candidate_embedding:
        try:
            from services.embeddings import embedding_service
            semantic_score = embedding_service.cosine_similarity(job_embedding, candidate_embedding) * 100
        except Exception:
            pass

    # --- Weighted total ---
    if semantic_score is not None:
        total_score = int(skill_score * 0.40 + exp_score * 0.25 + semantic_score * 0.25 + 10)
    else:
        total_score = int(skill_score * 0.50 + exp_score * 0.30 + 20)

    explanation = f"Quick match: {len(matched_skills)}/{len(all_job_skills)} skills matched, {cand_exp} yrs exp"
    if semantic_score is not None:
        explanation += f", {semantic_score:.0f}% semantic similarity"

    return {
        "score": min(total_score, 100),
        "skill_match_score": int(min(skill_score, 100)),
        "experience_match_score": int(min(exp_score, 100)),
        "semantic_score": round(semantic_score, 1) if semantic_score else None,
        "matched_skills": [s.title() if len(s) > 3 else s.upper() for s in matched_skills[:10]],
        "missing_skills": [s.title() if len(s) > 3 else s.upper() for s in missing_skills],
        "explanation": explanation,
    }
