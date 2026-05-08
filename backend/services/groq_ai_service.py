"""
Groq-powered AI services for high-priority features.
Direct Groq integration for CV parsing, batch enrichment, and JD parsing.

Cost: $0.59/M input + $0.79/M output (vs Claude Haiku $0.25/M + $1.25/M = cheaper output)
Speed: <2 seconds
Quality: Excellent with structured prompts
"""
import os
import logging
import httpx
from typing import Dict, List

logger = logging.getLogger(__name__)

# Groq API configuration
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


async def groq_chat_completion(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0,
    max_tokens: int = 2048,
    json_mode: bool = True,
) -> str:
    """
    3-layer AI call: RunPod (free) → Groq → Emergent LLM fallback.
    
    Optimized for resume parsing, JD parsing, batch enrichment.
    Returns plain text response (caller handles JSON parsing).
    """
    # ── Layer 1: RunPod vLLM (free, self-hosted) ──
    RUNPOD_URL = os.environ.get("RUNPOD_VLLM_URL")
    RUNPOD_MODEL = os.environ.get("RUNPOD_MODEL_NAME", "Qwen/Qwen2.5-14B-Instruct-AWQ")
    
    if RUNPOD_URL:
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            if json_mode and "JSON" not in system_prompt:
                messages[0]["content"] = f"{system_prompt}\n\nYou MUST return ONLY valid JSON. No markdown, no explanations, just the JSON object."
            
            payload = {
                "model": RUNPOD_MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": min(max_tokens, 4000),
            }
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{RUNPOD_URL.rstrip('/')}/v1/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                logger.info(
                    f"[RunPod-CV] Success | tokens: in={usage.get('prompt_tokens', 0)} out={usage.get('completion_tokens', 0)}"
                )
                return content
                
        except Exception as e:
            logger.warning(f"[RunPod-CV] Failed ({type(e).__name__}: {e}), falling back to Groq...")

    # ── Layer 2: Groq API ──
    if GROQ_API_KEY:
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            payload = {
                "model": GROQ_MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            
            if json_mode and "JSON" not in system_prompt:
                messages[0]["content"] = f"{system_prompt}\n\nYou MUST return ONLY valid JSON. No markdown, no explanations, just the JSON object."
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    GROQ_API_URL,
                    headers={
                        "Authorization": f"Bearer {GROQ_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                
                logger.info(
                    f"[Groq] Success | model={GROQ_MODEL} | "
                    f"tokens: in={usage.get('prompt_tokens', 0)} out={usage.get('completion_tokens', 0)}"
                )
                
                return content
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 or "rate_limit" in e.response.text.lower():
                logger.warning("[Groq] Rate limit exceeded — falling back to Emergent LLM")
            else:
                logger.error(f"[Groq] HTTP error {e.response.status_code}: {e.response.text}")
                
        except Exception as e:
            logger.error(f"[Groq] Error: {type(e).__name__}: {e}")
    
    # ── Layer 3: Emergent LLM ──
    logger.info("[Groq] Attempting fallback to Emergent LLM (OpenAI GPT-4o)...")
    
    from dotenv import load_dotenv
    load_dotenv()
    
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    
    EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
    
    if not EMERGENT_LLM_KEY:
        raise ValueError("All 3 layers failed: RunPod unavailable, Groq failed, EMERGENT_LLM_KEY not configured")
    
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id="groq-fallback",
        system_message=system_prompt
    ).with_model("openai", "gpt-4o")
    
    user_message = UserMessage(text=user_prompt)
    response = await chat.send_message(user_message)
    
    logger.info("[Emergent] Success via Emergent LLM fallback")
    
    return response


# ============================================================================
# Resume Parser (Groq-optimized prompt)
# ============================================================================

async def parse_resume_with_groq(resume_text: str) -> Dict:
    """
    Parse resume using Groq Llama 3.3 70B.
    Optimized prompt for maximum extraction accuracy.
    
    Returns: {"success": True, "data": {...}} or {"success": False, "error": "..."}
    """
    try:
        system_prompt = """You are an expert resume parser. Extract ALL information from resumes with 100% accuracy.

CRITICAL RULES:
- Extract ONLY what is explicitly stated
- NEVER fabricate or infer data
- Use null for missing fields
- Return ONLY valid JSON, no markdown, no explanations
- Dates: Use "MMM YYYY" format (e.g., "Jan 2020")
- Experience: Calculate total years as decimal (e.g., 5.5 years)
- Skills: Extract ALL mentioned skills, tools, and technologies"""

        user_prompt = f"""Parse this resume and extract structured data.

Return ONLY valid JSON with this EXACT structure:

{{
    "name": "full name or null",
    "email": "email address or null",
    "phone": "phone number or null",
    "headline": "professional title/headline or null",
    "profile_summary": "2-3 sentence professional summary or null",
    "current_company": "current or most recent employer or null",
    "current_designation": "current or most recent job title or null",
    "current_industry": "industry if stated or null",
    "total_experience_years": <number or null>,
    "location": "city, state or null",
    "key_skills": ["skill1", "skill2", "skill3"],
    "work_experience": [
        {{
            "designation": "job title",
            "company": "company name",
            "from_date": "MMM YYYY or null",
            "to_date": "MMM YYYY or Present",
            "is_current": true,
            "description": "responsibilities and achievements"
        }}
    ],
    "education": [
        {{
            "degree": "degree name",
            "specialization": "field of study or null",
            "institution": "university/college",
            "year_of_passing": "YYYY or null"
        }}
    ],
    "certifications": ["cert1", "cert2"],
    "projects": [{{"title": "project name", "description": "brief description"}}],
    "languages": [{{"language": "name", "proficiency": "level or null"}}],
    "online_profiles": [{{"platform": "LinkedIn/GitHub/etc", "url": "URL"}}],
    "preferred_locations": ["city1", "city2"]
}}

Resume text:
{resume_text[:8000]}

IMPORTANT: Return ONLY the JSON object, nothing else."""

        response_text = await groq_chat_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0,
            max_tokens=2048,
            json_mode=True
        )
        
        # Extract JSON from response (handles markdown wrapping)
        import json
        from services.schema_normalizer import extract_json_from_llm_response, normalize_candidate
        
        json_str = extract_json_from_llm_response(response_text)
        parsed = json.loads(json_str)
        
        # Normalize field names for compatibility
        normalized = normalize_candidate(parsed)
        
        logger.info(
            f"[Groq Resume Parse] ✅ Success | "
            f"skills={len(normalized.get('key_skills', []))}, "
            f"exp_years={normalized.get('total_experience_years')}"
        )
        
        return {"success": True, "data": normalized}
        
    except json.JSONDecodeError as e:
        logger.error(f"[Groq Resume Parse] JSON error: {e}")
        return {"success": False, "error": f"Failed to parse AI response: {str(e)}"}
    except Exception as e:
        logger.error(f"[Groq Resume Parse] Error: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# Job Description Parser (Groq-optimized)
# ============================================================================

async def parse_job_description_with_groq(jd_text: str) -> Dict:
    """
    Parse job description using Groq Llama 3.3 70B.
    
    Returns: {"success": True, "data": {...}} or {"success": False, "error": "..."}
    """
    try:
        system_prompt = """You are an expert job description parser. Extract structured requirements with maximum accuracy.

RULES:
- Extract ONLY what is explicitly stated
- Use null for missing/unclear information
- Return ONLY valid JSON, no markdown
- Salary: Extract if mentioned, null otherwise
- Skills: Distinguish required vs preferred"""

        user_prompt = f"""Parse this job description and extract structured requirements.

Return ONLY valid JSON with this EXACT structure:

{{
    "title": "job title",
    "department": "department or null",
    "location": "location requirement or null",
    "job_type": "full-time/part-time/contract/remote",
    "experience_min": <minimum years as number or 0>,
    "experience_max": <maximum years as number or null>,
    "required_skills": ["must-have skill1", "must-have skill2"],
    "preferred_skills": ["nice-to-have skill1", "nice-to-have skill2"],
    "required_qualifications": ["degree requirement", "certification"],
    "responsibilities": ["responsibility1", "responsibility2"],
    "salary_min": <minimum salary as number or null>,
    "salary_max": <maximum salary as number or null>,
    "key_requirements_summary": "2-3 sentence summary of critical requirements"
}}

Job Description:
{jd_text[:8000]}

Return ONLY the JSON object."""

        response_text = await groq_chat_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0,
            max_tokens=1500,
            json_mode=True
        )
        
        import json
        from services.schema_normalizer import extract_json_from_llm_response
        
        json_str = extract_json_from_llm_response(response_text)
        parsed = json.loads(json_str)
        
        logger.info(f"[Groq JD Parse] ✅ Success | keys: {list(parsed.keys())}")
        
        return {"success": True, "data": parsed}
        
    except json.JSONDecodeError as e:
        logger.error(f"[Groq JD Parse] JSON error: {e}")
        return {"success": False, "error": f"Failed to parse AI response: {str(e)}"}
    except Exception as e:
        logger.error(f"[Groq JD Parse] Error: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# Batch Enrichment Helper
# ============================================================================

async def groq_extract_candidate_profile(raw_text: str, candidate_name: str) -> Dict:
    """
    Extract candidate profile data using Groq (for batch enrichment).
    Same interface as bedrock_service.extract_full_profile but uses Groq.
    
    Returns structured candidate data dict.
    """
    from services.groq_service import extract_full_profile_groq
    
    # Reuse the existing groq_service.py implementation
    # which has the full candidate extraction prompt
    result = await extract_full_profile_groq(raw_text=raw_text, candidate_name=candidate_name)
    
    if result.get('error'):
        logger.error(f"[Groq Batch] Extraction failed for {candidate_name}: {result['error']}")
        return {}
    
    return result
