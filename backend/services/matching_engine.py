"""
AI Matching Engine Service for VHC Talent OS
Uses GPT-5.2 via Emergent LLM for resume/JD parsing and matching
"""
import os
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
    Returns structured candidate data.
    """
    try:
        chat = get_chat_client("You are an expert resume parser. Extract structured data from resumes accurately.")
        
        prompt = f"""Parse the following resume and extract structured data. Return ONLY valid JSON with this exact structure:
{{
    "name": "full name",
    "email": "email if found or null",
    "phone": "phone if found or null",
    "headline": "professional title/headline",
    "summary": "brief professional summary (2-3 sentences)",
    "skills": ["skill1", "skill2", ...],
    "experience_years": number or 0,
    "experience": [
        {{
            "title": "job title",
            "company": "company name",
            "duration": "duration string",
            "description": "brief description"
        }}
    ],
    "education": [
        {{
            "degree": "degree name",
            "institution": "school/university",
            "year": "graduation year or null"
        }}
    ],
    "location": "city, state/country if found or null",
    "certifications": ["cert1", "cert2", ...]
}}

Resume text:
{resume_text[:8000]}"""  # Limit to 8000 chars
        
        logger.info(f"[RESUME PARSE] Sending prompt to GPT-5.2, length: {len(prompt)}")
        
        response = await chat.send_message(
            message=UserMessage(text=prompt)
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
            message=UserMessage(text=prompt)
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
        
        logger.info(f"[MATCH CALC] Sending prompt to GPT-5.2")
        
        response = await chat.send_message(
            message=UserMessage(text=prompt)
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
