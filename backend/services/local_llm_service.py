"""
Local LLM Service - Routes admin@vhc.in to local Gemma 4 via Cloudflare Tunnel
"""
import os
import httpx
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Local LLM endpoint (via Cloudflare Tunnel)
LOCAL_LLM_URL = os.environ.get("LOCAL_LLM_URL", "https://initially-achievements-banner-laboratories.trycloudflare.com/v1/chat/completions")
LOCAL_LLM_MODEL = os.environ.get("LOCAL_LLM_MODEL", "gemma-4-e4b")

async def local_llm_chat_completion(
    system_prompt: str,
    user_prompt: str,
    model: str = LOCAL_LLM_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 3000,
    timeout: int = 300  # Increased to 5 minutes for CPU inference
) -> Optional[dict]:
    """
    Call local LLM via Cloudflare Tunnel.
    Compatible with OpenAI chat completion API format.
    """
    try:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        logger.warning(f"[Local LLM] Calling {LOCAL_LLM_URL} with {len(user_prompt)} chars")
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                LOCAL_LLM_URL,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.warning(f"[Local LLM] ✅ Success - {len(content)} chars returned")
                return {
                    "content": content,
                    "model": model,
                    "source": "local_llm_gemma4"
                }
            else:
                logger.error(f"[Local LLM] ❌ HTTP {response.status_code}: {response.text[:200]}")
                return None
                
    except httpx.TimeoutException:
        logger.error(f"[Local LLM] ⏱️ Timeout after {timeout}s")
        return None
    except Exception as e:
        logger.error(f"[Local LLM] ❌ Error: {e}")
        return None


async def extract_full_profile_local(raw_text: str, candidate_name: str = None) -> dict:
    """
    Full profile extraction using local Gemma 4.
    Uses optimized prompt for better Gemma 4 compatibility.
    """
    system_prompt = """You are an expert recruitment data extractor. Extract candidate information EXACTLY as it appears.

CRITICAL RULES:
1. Experience calculation: Count ALL jobs from EARLIEST start date to TODAY
   - Example: Job 1 (2018-2021) + Job 2 (2021-2023) + Job 3 (2023-Present) = 5-7 years total
   - ALWAYS sum up ALL work periods, don't just take one number
2. Email: ONLY extract candidate's personal email (IGNORE @naukri.com, @gmail.com from recruiters)
3. CTC: Convert Lakhs/Crores to RUPEES (1 Lakh = 100000, 1 Crore = 10000000)
4. Phone: Extract 10-digit mobile number (ignore recruiter numbers)
5. Work descriptions: Copy FULL job descriptions with ALL details

Return ONLY valid JSON (no markdown, no explanation):
{
  "name": "string",
  "email": "string or null",
  "phone": "string or null",
  "location": "string or null",
  "experience_years": number,
  "current_employer": "string or null",
  "current_designation": "string or null",
  "current_ctc": number or null,
  "expected_ctc": number or null,
  "notice_period": "string or null",
  "notice_period_days": number or null,
  "key_skills": ["skill1", "skill2"],
  "work_experience": [
    {
      "company": "string",
      "designation": "string",
      "from_date": "MMM YYYY",
      "to_date": "MMM YYYY or Present",
      "is_current": true/false,
      "duration": "e.g. 2y 3m",
      "description": "FULL detailed description"
    }
  ],
  "education": [
    {
      "degree": "string",
      "institution": "string",
      "specialization": "string or null",
      "year_of_passing": "string or null"
    }
  ],
  "certifications": ["cert1", "cert2"],
  "languages": ["language1", "language2"],
  "projects": [{"name": "string", "description": "string"}],
  "online_profiles": [{"platform": "string", "url": "string"}],
  "preferred_locations": ["city1", "city2"],
  "highest_qualification": "string or null",
  "headline": "string or null",
  "profile_summary": "string or null",
  "current_department": "string or null",
  "current_industry": "string or null"
}"""

    user_prompt = f"""Extract ALL data from this candidate profile.

Candidate: {candidate_name or 'Unknown'}

IMPORTANT:
- Calculate experience_years by adding ALL job durations
- Extract FULL work experience descriptions (don't summarize)
- Ignore recruiter emails/phones

Profile Text:
{raw_text[:8000]}

Return ONLY the JSON object."""

    result = await local_llm_chat_completion(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.0,
        max_tokens=3000,
        timeout=300  # 5 minutes for CPU inference
    )
    
    if result:
        try:
            # Parse JSON from response
            content = result["content"].strip()
            
            # Remove markdown code blocks if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            
            parsed = json.loads(content)
            parsed["ai_enrichment_source"] = "local_llm_gemma4"
            return parsed
            
        except json.JSONDecodeError as e:
            logger.error(f"[Local LLM] JSON parse error: {e}")
            logger.error(f"[Local LLM] Raw response: {result['content'][:500]}")
            return {}
    
    return {}
