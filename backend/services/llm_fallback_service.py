"""
LLM Fallback Service — Multi-tier resilience for candidate extraction.

Fallback Chain (Option-A architecture, 2026-05-05):
1. RunPod vLLM (Qwen 14B AWQ on L4) — Primary (self-hosted, ~₹0 marginal cost)
2. Emergent LLM Key → Claude Haiku 4.5 — Last-resort fallback (only when
   RunPod pod is UNREACHABLE; "strict-Qwen" policy blocks fallback when the
   pod is up but Qwen still couldn't parse).

Anthropic Direct API (4-key rotation) was REMOVED in Phase 51 to consolidate
billing through the Emergent Universal Key and eliminate the recurring
"credit balance too low" outage.
"""
import os
import json
import asyncio
import logging
import httpx
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Configuration
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
# Anthropic Direct API removed in Phase 51 (Option-A architecture, 2026-05-05).
# Kept as `None` to preserve any downstream `if ANTHROPIC_API_KEY:` guards.
ANTHROPIC_API_KEY = None
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
RUNPOD_VLLM_URL = os.environ.get("RUNPOD_VLLM_URL")
RUNPOD_MODEL_NAME = os.environ.get("RUNPOD_MODEL_NAME", "Qwen/Qwen2.5-14B-Instruct-AWQ")
# Explicit API key — override if set; otherwise auto-derive from URL below
RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY") or os.environ.get("VLLM_API_KEY") or os.environ.get("RUNPOD_VLLM_API_KEY")

# Auto-derive API key from URL when not set explicitly.
# RunPod pod template uses VLLM_API_KEY=sk-$RUNPOD_POD_ID and the URL format is
# https://{POD_ID}-{PORT}.proxy.runpod.net, so we can extract POD_ID from the hostname.
if not RUNPOD_API_KEY and RUNPOD_VLLM_URL:
    try:
        from urllib.parse import urlparse
        host = urlparse(RUNPOD_VLLM_URL).hostname or ""
        # e.g. "wmq1x0p6ixg7kb-8000.proxy.runpod.net" -> pod_id "wmq1x0p6ixg7kb"
        if host.endswith(".proxy.runpod.net"):
            first_seg = host.split(".")[0]  # "wmq1x0p6ixg7kb-8000"
            if "-" in first_seg:
                pod_id = first_seg.rsplit("-", 1)[0]
                if pod_id:
                    RUNPOD_API_KEY = f"sk-{pod_id}"
                    # Use logger defined below — defer the log
                    import logging as _logging
                    _logging.getLogger(__name__).info(
                        f"[RunPod] Auto-derived API key from URL (pod_id={pod_id})"
                    )
    except Exception:
        pass


def _extract_json_from_response(response_text: str) -> str:
    """Extract and repair JSON from LLM response (handles markdown, trailing commas, missing commas, etc.)."""
    import re
    from json_repair import repair_json
    
    clean = response_text.strip()
    
    # Remove markdown code blocks
    if clean.startswith('```'):
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', clean, re.DOTALL)
        if match:
            clean = match.group(1)
        else:
            clean = clean.replace('```json', '').replace('```', '').strip()
    
    # Extract just the JSON object if there's extra text before/after
    match = re.search(r'\{.*\}', clean, re.DOTALL)
    if match:
        clean = match.group(0)
    
    # v5.4.1: Use json_repair library as PRIMARY repair method
    # This handles missing commas, trailing commas, unquoted keys, etc.
    try:
        repaired = repair_json(clean, return_objects=False)
        if repaired and repaired.startswith('{'):
            return repaired
    except Exception as e:
        logger.debug(f"[JSON-Repair] Library failed, falling back to regex: {e}")
    
    # Fallback: manual regex repairs for edge cases
    # 1. Remove trailing commas before } or ]
    clean = re.sub(r',\s*([}\]])', r'\1', clean)
    # 2. Remove comments (// style)
    clean = re.sub(r'//[^\n]*', '', clean)
    # 3. Remove control characters
    clean = re.sub(r'[\x00-\x1f\x7f]', ' ', clean)
    # 4. Fix unquoted keys (common: key: "value" instead of "key": "value")
    clean = re.sub(r'(?<=\{|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r' "\1":', clean)
    # 5. Fix missing commas between fields: }"field" or ]"field" or ""  "field"
    clean = re.sub(r'"\s*\n\s*"', '",\n"', clean)
    clean = re.sub(r'"\s+"(?=[a-zA-Z_])', '", "', clean)
    clean = re.sub(r'(\})\s*(")', r'\1, \2', clean)
    clean = re.sub(r'(\])\s*(")', r'\1, \2', clean)
    clean = re.sub(r'(null|true|false|\d)\s*\n\s*"', r'\1,\n"', clean)
    # 6. Fix single quotes used as string delimiters
    clean = re.sub(r"(?<![a-zA-Z])'([^']*)'(?=\s*[:,}\]])", r'"\1"', clean)
    
    return clean


async def _try_groq(system_prompt: str, user_prompt: str, temperature: float = 0, max_tokens: int = 2000) -> Optional[Dict]:
    """
    Attempt extraction using Groq API.
    
    Returns:
        dict: Parsed JSON response
        None: If Groq fails (rate limit, timeout, etc.)
    """
    if not groq_client:
        logger.warning("[Fallback] Groq client not configured — skipping")
        return None
    
    try:
        logger.info("[Fallback] Attempting Groq extraction...")
        
        completion = await groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=30.0  # 30 second timeout
        )
        
        result = completion.choices[0].message.content.strip()
        
        # Log token usage
        tokens_used = completion.usage.total_tokens
        logger.info(f"[Fallback][Groq] ✅ Success | tokens: {tokens_used}")
        
        # Parse JSON
        clean_result = _extract_json_from_response(result)
        data = json.loads(clean_result)
        
        return data
        
    except Exception as e:
        error_msg = str(e)
        
        # Detect specific error types
        if "429" in error_msg or "rate_limit" in error_msg.lower():
            logger.warning("[Fallback][Groq] ⚠️ Rate limit exceeded — falling back")
        elif "503" in error_msg or "service unavailable" in error_msg.lower():
            logger.warning("[Fallback][Groq] ⚠️ Service unavailable — falling back")
        elif "timeout" in error_msg.lower():
            logger.warning("[Fallback][Groq] ⚠️ Timeout — falling back")
        else:
            logger.warning(f"[Fallback][Groq] ❌ Error: {error_msg}")
        
        return None


async def _try_emergent_openai(system_prompt: str, user_prompt: str, temperature: float = 0, max_tokens: int = 2000) -> Optional[Dict]:
    """
    Attempt extraction using Emergent LLM Key → OpenAI GPT-4o.
    
    Returns:
        dict: Parsed JSON response
        None: If Emergent LLM fails
    """
    if not EMERGENT_LLM_KEY:
        logger.warning("[Fallback] EMERGENT_LLM_KEY not configured — skipping")
        return None
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        
        logger.info("[Fallback] Attempting Emergent LLM (OpenAI GPT-4o) extraction...")
        
        # Initialize chat
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id="fallback-extraction",
            system_message=system_prompt
        ).with_model("openai", "gpt-4o")
        
        # Send message
        user_message = UserMessage(text=user_prompt)
        response = await chat.send_message(user_message)
        
        logger.info("[Fallback][Emergent] ✅ Success")
        
        # Parse JSON
        clean_result = _extract_json_from_response(response)
        data = json.loads(clean_result)
        
        return data
        
    except Exception as e:
        logger.error(f"[Fallback][Emergent] ❌ Error: {e}")
        return None


async def _call_emergent_llm_haiku(system_prompt: str, user_prompt: str, temperature: float = 0) -> Optional[Dict]:
    """
    Call Claude Haiku 4.5 via Emergent LLM Key for candidate extraction.
    
    Returns:
        dict: {"content": response_text} on success
        None: If call fails
    """
    if not EMERGENT_LLM_KEY:
        logger.warning("[Haiku] EMERGENT_LLM_KEY not configured — skipping")
        return None
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        
        logger.info("[Haiku] Calling Claude Haiku 4.5 via Emergent LLM Key...")
        
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id="haiku-extraction",
            system_message=system_prompt
        ).with_model("anthropic", "claude-haiku-4-5-20251001")
        
        user_message = UserMessage(text=user_prompt)
        response = await chat.send_message(user_message)
        
        logger.info("[Haiku] Claude Haiku 4.5 response received")
        return {"content": response}
        
    except Exception as e:
        logger.error(f"[Haiku] Claude Haiku 4.5 error: {e}")
        return None


async def _call_runpod_vllm(system_prompt: str, user_prompt: str, temperature: float = 0, retry: bool = True, disable_guided: bool = False, text_mode: bool = False) -> Optional[Dict]:
    """
    Call Qwen 14B via RunPod vLLM with guided JSON generation.
    Uses response_format to force valid JSON output.
    Auto-retries once on failure with truncated prompt.
    """
    if not RUNPOD_VLLM_URL:
        logger.warning("[RunPod] RUNPOD_VLLM_URL not configured — skipping")
        return None
    
    try:
        url = f"{RUNPOD_VLLM_URL.rstrip('/')}/v1/chat/completions"

        # Strict JSON schema for vLLM's guided_json — eliminates malformed JSON
        # and forces Qwen-14B to emit every field (nullable where optional).
        # See https://docs.vllm.ai/en/stable/features/structured_outputs.html
        profile_schema = {
            "type": "object",
            "properties": {
                "name": {"type": ["string", "null"]},
                "email": {"type": ["string", "null"]},
                "phone": {"type": ["string", "null"]},
                "location": {"type": ["string", "null"]},
                "experience_years": {"type": ["number", "null"]},
                "current_employer": {"type": ["string", "null"]},
                "current_designation": {"type": ["string", "null"]},
                "current_ctc": {"type": ["number", "null"]},
                "expected_ctc": {"type": ["number", "null"]},
                "notice_period": {"type": ["string", "null"]},
                "notice_period_days": {"type": ["number", "null"]},
                "profile_summary": {"type": ["string", "null"]},
                "headline": {"type": ["string", "null"]},
                "key_skills": {"type": "array", "items": {"type": "string"}},
                "work_experience": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "company": {"type": ["string", "null"]},
                            "designation": {"type": ["string", "null"]},
                            "from_date": {"type": ["string", "null"]},
                            "to_date": {"type": ["string", "null"]},
                            "is_current": {"type": "boolean"},
                            "duration": {"type": ["string", "null"]},
                            "description": {"type": ["string", "null"]},
                        },
                    },
                },
                "education": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "degree": {"type": ["string", "null"]},
                            "institution": {"type": ["string", "null"]},
                            "specialization": {"type": ["string", "null"]},
                            "year_of_passing": {"type": ["string", "null"]},
                            "score": {"type": ["string", "null"]},
                        },
                    },
                },
                "certifications": {"type": "array", "items": {"type": "string"}},
                "languages": {"type": "array", "items": {"type": "string"}},
                "projects": {"type": "array", "items": {"type": "object"}},
                "online_profiles": {"type": "array", "items": {"type": "object"}},
                "preferred_locations": {"type": "array", "items": {"type": "string"}},
                "highest_qualification": {"type": ["string", "null"]},
                "current_department": {"type": ["string", "null"]},
                "current_industry": {"type": ["string", "null"]},
            },
            "required": ["name", "experience_years", "current_ctc", "expected_ctc",
                         "notice_period", "location", "current_employer",
                         "current_designation", "work_experience", "education"],
        }

        payload = {
            "model": RUNPOD_MODEL_NAME,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature,
            # Profiles with 3+ work entries, rich education, and full JD text
            # can easily exceed 6k tokens — that was the #1 cause of "JSON
            # decode error" mid-string truncations. 12k covers 99% of the
            # observed cut-off cases (max observed ~10k chars ≈ 3.3k tokens).
            "max_tokens": 16000,  # v5.4.1: Increased from 12000 for long profiles
        }
        # Prefer `response_format=json_object` as the universal structured-output
        # mode — works on every vLLM build since 0.5.x. `guided_json` with xgrammar
        # crashes on schemas containing union types (`["string","null"]`), which
        # is unavoidable for optional fields. Enable by setting VLLM_GUIDED_JSON=1
        # only after confirming xgrammar+outlines parity on your pod.
        _use_guided = os.environ.get("VLLM_GUIDED_JSON", "0") == "1"
        if text_mode:
            # Plain text completion — used by AI summary generator. Don't force
            # JSON or Qwen returns useless fragments like "[1]" / "[6]".
            pass
        elif not disable_guided and _use_guided:
            payload["guided_json"] = profile_schema
            payload["guided_decoding_backend"] = "xgrammar"
        else:
            payload["response_format"] = {"type": "json_object"}
        
        logger.info(f"[RunPod] Calling Qwen 14B (mode={'text' if text_mode else 'json'})...")
        
        headers = {"Content-Type": "application/json"}
        if RUNPOD_API_KEY:
            headers["Authorization"] = f"Bearer {RUNPOD_API_KEY}"

        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
            finish_reason = choice.get("finish_reason", "")
            
            # vLLM reports finish_reason="length" when the response was cut
            # at max_tokens mid-JSON. Detecting it here lets us auto-retry with
            # a larger budget instead of failing over to Anthropic/Emergent.
            if finish_reason == "length" and retry and not text_mode:
                logger.warning(
                    f"[RunPod] finish_reason=length at {payload['max_tokens']} tokens — "
                    f"retrying with 20000 tokens"
                )
                payload["max_tokens"] = 20000
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                choice = data["choices"][0]
                content = choice["message"]["content"]
                finish_reason = choice.get("finish_reason", "")
            
            logger.info(
                f"[RunPod] Qwen 14B response received "
                f"({len(content)} chars, finish={finish_reason})"
            )
            return {"content": content}
    
    except httpx.TimeoutException:
        logger.error("[RunPod] Request timed out (180s)")
        # Retry with shorter prompt on timeout
        if retry:
            logger.info("[RunPod] Retrying with truncated prompt...")
            short_prompt = f"Extract complete profile:\n\n{user_prompt.split(chr(10), 2)[-1][:40000]}"
            return await _call_runpod_vllm(system_prompt, short_prompt, temperature, retry=False)
        return None
    except httpx.HTTPStatusError as e:
        error_text = e.response.text[:300]
        logger.error(f"[RunPod] HTTP error {e.response.status_code}: {error_text}")
        # Retry with shorter prompt if context too long
        if e.response.status_code == 400 and "context length" in error_text.lower() and retry:
            logger.info("[RunPod] Context too long, retrying with truncated prompt...")
            short_prompt = f"Extract complete profile:\n\n{user_prompt.split(chr(10), 2)[-1][:40000]}"
            return await _call_runpod_vllm(system_prompt, short_prompt, temperature, retry=False)
        # Graceful degradation: some older vLLM builds reject guided_json.
        # Retry once without structured-output constraints.
        low = error_text.lower()
        if e.response.status_code == 400 and ("guided_json" in low or "guided_decoding" in low or "xgrammar" in low or "guided decoding" in low) and retry:
            logger.warning("[RunPod] guided_json unsupported / conflicting on this pod — retrying without schema enforcement")
            return await _call_runpod_vllm(system_prompt, user_prompt, temperature, retry=False, disable_guided=True)
        # RunPod pods occasionally 502/503/504 during cold-start / auto-scale.
        # A short backoff + retry keeps these on the Qwen track instead of
        # leaking to the paid Anthropic/Emergent fallbacks.
        if e.response.status_code in (429, 500, 502, 503, 504) and retry:
            logger.warning(f"[RunPod] Transient {e.response.status_code} — backoff 5s + retry")
            await asyncio.sleep(5)
            return await _call_runpod_vllm(system_prompt, user_prompt, temperature, retry=False, disable_guided=disable_guided, text_mode=text_mode)
        return None
    except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError, httpx.ReadTimeout) as e:
        # Network-layer failures are the #1 reason profiles leak from Qwen to
        # Anthropic/Emergent on this deploy (693 cases / 4d in prod). The pod
        # is usually just re-spawning — one backoff + retry recovers most.
        logger.error(f"[RunPod] Network error: {type(e).__name__}: {str(e)[:200]}")
        if retry:
            logger.info("[RunPod] Network-error backoff 5s + retry")
            await asyncio.sleep(5)
            return await _call_runpod_vllm(system_prompt, user_prompt, temperature, retry=False, disable_guided=disable_guided, text_mode=text_mode)
        return None
    except Exception as e:
        logger.error(f"[RunPod] Error: {e}")
        return None


async def _log_extraction_event(db, candidate_name: str, source: str, success: bool, fallback_chain: list, elapsed_ms: int):
    """Log extraction event to MongoDB for daily reporting.
    Silently swallows event-loop-mismatch errors when called from background tasks
    running on a different loop than the global db client.
    Also silently skips when called from a standalone script that has not
    called `initialize_db()` — the log is non-critical.
    """
    try:
        if db is None:
            from config import db as _db
            db = _db
        await db.extraction_tracking.insert_one({
            "candidate_name": candidate_name,
            "source": source,
            "success": success,
            "fallback_chain": fallback_chain,
            "elapsed_ms": elapsed_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        })
    except RuntimeError as e:
        # "attached to a different loop" — happens in background tasks; non-fatal
        # "Database not initialized yet" — happens when called from scripts
        msg = str(e)
        if "different loop" in msg or "not initialized" in msg.lower():
            return
        logger.error(f"[Tracking] RuntimeError: {e}")
    except Exception as e:
        logger.error(f"[Tracking] Failed to log: {e}")


async def extract_with_fallback(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0,
    max_tokens: int = 2000,
    context: str = "unknown"
) -> Dict:
    """
    Multi-tier LLM extraction with automatic fallback.
    
    Args:
        system_prompt: LLM system prompt
        user_prompt: User message
        temperature: LLM temperature (0-1)
        max_tokens: Max response tokens
        context: Context label for logging (e.g., "CV Upload", "Extension Capture")
    
    Returns:
        dict: {
            "success": True,
            "data": {...},
            "source": "groq" | "emergent_llm" | "raw_fallback"
        }
        OR
        dict: {
            "success": False,
            "error": "...",
            "raw_text": "..." (if fallback to raw)
        }
    """
    
    # Tier 1: Try Groq
    result = await _try_groq(system_prompt, user_prompt, temperature, max_tokens)
    if result:
        logger.info(f"[Fallback][{context}] ✅ Success via Groq")
        return {
            "success": True,
            "data": result,
            "source": "groq"
        }
    
    # Tier 2: Try Emergent LLM (OpenAI GPT-4o)
    logger.warning(f"[Fallback][{context}] Groq failed — trying Emergent LLM...")
    result = await _try_emergent_openai(system_prompt, user_prompt, temperature, max_tokens)
    if result:
        logger.info(f"[Fallback][{context}] ✅ Success via Emergent LLM")
        return {
            "success": True,
            "data": result,
            "source": "emergent_llm"
        }
    
    # Tier 3: All LLMs failed — return raw text for manual review
    logger.error(f"[Fallback][{context}] ❌ All LLM providers failed — saving raw text")
    return {
        "success": False,
        "error": "All LLM providers failed (Groq rate limited, Emergent LLM unavailable)",
        "raw_text": user_prompt[:5000],  # Save first 5000 chars for manual review
        "source": "raw_fallback"
    }


async def extract_phone_and_work_experience_fallback(raw_text: str, candidate_name: str = None) -> dict:
    """
    Extract phone number and work experience using fallback chain.
    
    Returns:
        dict: {
            "phone": str or None,
            "work_experience": [...],
            "error": str (if failed),
            "source": "groq" | "emergent_llm" | "raw_fallback"
        }
    """
    
    system_prompt = """You are an expert at extracting structured data from resumes and job profiles.
Your task is to extract ONLY the candidate's work experience history and phone number.

Return ONLY a valid JSON object with this EXACT structure (no markdown, no code blocks):
{
    "phone": "phone number if found, null otherwise",
    "work_experience": [
        {
            "company": "company name",
            "designation": "job title/role",
            "from_date": "start date (Month Year or just Year)",
            "to_date": "end date or Present/Current",
            "is_current": true or false,
            "description": "brief 1-2 sentence description of responsibilities"
        }
    ]
}

CRITICAL RULES:
1. DO NOT extract education as work experience
2. DO NOT use GPA, CGPA, grades, or percentages as job titles
3. DO NOT use universities, colleges, or schools as company names
4. ONLY extract actual employment/work history
5. If phone has country code, include it
6. Return ONLY the JSON object, no explanations or markdown
7. Work experience should be in reverse chronological order (most recent first)
"""

    user_prompt = f"""Extract work experience and phone number from this candidate profile:

Candidate Name: {candidate_name or 'Unknown'}

Profile Text:
{raw_text[:24000]}

Remember: Return ONLY the JSON object, no markdown formatting."""

    result = await extract_with_fallback(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0,
        max_tokens=3500,
        context=f"Phone/Work-Exp: {candidate_name or 'Unknown'}"
    )
    
    if result["success"]:
        data = result["data"]
        data["source"] = result["source"]
        return data
    else:
        return {
            "phone": None,
            "work_experience": [],
            "error": result["error"],
            "source": result["source"]
        }


CTC_MAX_SANE = 50_000_000  # ₹5 Cr — annual CTC above this is treated as corrupt/irrelevant
CTC_MIN_SANE = 50_000      # ₹50K — annual CTC below this is treated as noise


def sanitize_ctc(val) -> Optional[int]:
    """Validate a CTC number. Returns None if out of sane range (₹50K – ₹5Cr/year).
    Prevents corrupt LLM/regex outputs from polluting the candidate DB.
    """
    if val is None:
        return None
    try:
        n = int(float(val))
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if n < CTC_MIN_SANE:
        return None
    if n > CTC_MAX_SANE:
        return None
    return n


def _regex_backfill_critical(result: dict, raw_text: str) -> dict:
    """
    Post-LLM regex safety net: Backfill CTC, notice period, education, location
    from raw text when LLM missed them. Ensures consistency regardless of LLM quality.

    Defensive: any internal error (bad regex, unexpected input) must NOT bubble up —
    the LLM result is always more valuable than a regex backfill side-effect.
    """
    try:
        return _regex_backfill_critical_impl(result, raw_text)
    except Exception as e:
        logger.error(f"[Regex Backfill] Non-fatal error — returning LLM result as-is: {e}")
        return result


def _regex_backfill_critical_impl(result: dict, raw_text: str) -> dict:
    import re

    # ── CTC (current) ──
    if not result.get('current_ctc'):
        ctc_patterns = [
            re.compile(r'₹\s*([\d.]+)\s*(Lacs?|LPA|Lac)\s*\(expects', re.IGNORECASE),
            re.compile(r'₹\s*([\d.]+)\s*(Lacs?|LPA|Lac)(?!\s*\))', re.IGNORECASE),
            re.compile(r'(?:Current\s+)?CTC[:\s]+₹?\s*([\d.]+)\s*(Lacs?|LPA|Lac|Cr|Crore)', re.IGNORECASE),
            re.compile(r'([\d.]+)\s*(Lacs?|LPA)\s*(?:per\s+annum|p\.?a\.?|annual)?', re.IGNORECASE),
        ]
        for pat in ctc_patterns:
            m = pat.search(raw_text)
            if m:
                val = float(m.group(1))
                unit = m.group(2).lower()
                if unit in ('cr', 'crore'):
                    candidate = int(val * 10000000)
                else:
                    candidate = int(val * 100000)
                clean = sanitize_ctc(candidate)
                if clean is not None:
                    result['current_ctc'] = clean
                    logger.info(f"[Regex Backfill] CTC: {clean}")
                else:
                    logger.warning(f"[Regex Backfill] CTC rejected (out of sane range): raw={candidate} from '{m.group(0)}'")
                break

    # ── CTC (expected) ──
    if not result.get('expected_ctc'):
        m = re.search(r'expects?[:\s]*₹?\s*([\d.]+)\s*(Lacs?|LPA|Lac|Cr|Crore)', raw_text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            unit = m.group(2).lower()
            if unit in ('cr', 'crore'):
                candidate = int(val * 10000000)
            else:
                candidate = int(val * 100000)
            clean = sanitize_ctc(candidate)
            if clean is not None:
                result['expected_ctc'] = clean
                logger.info(f"[Regex Backfill] Expected CTC: {clean}")
            else:
                logger.warning(f"[Regex Backfill] Expected CTC rejected (out of sane range): raw={candidate}")

    # Also sanitize any LLM-provided CTC that slipped through
    for _k in ('current_ctc', 'expected_ctc'):
        if result.get(_k) is not None:
            _clean = sanitize_ctc(result[_k])
            if _clean != result[_k]:
                logger.warning(f"[CTC-Sanitize] {_k} rejected: {result[_k]} -> None")
                result[_k] = _clean

    # ── Notice Period ──
    if not result.get('notice_period'):
        notice_patterns = [
            re.compile(r'Notice\s*(?:Period)?[:\s]+(\d{1,2})\s*Months?', re.IGNORECASE),
            re.compile(r'(\d{1,2})\s*Months?\s*(?:Notice|notice)', re.IGNORECASE),
            re.compile(r'(Immediate(?:ly)?|Serving\s+Notice)', re.IGNORECASE),
        ]
        for pat in notice_patterns:
            m = pat.search(raw_text)
            if m:
                txt = m.group(1)
                if txt.lower().startswith('immedia'):
                    result['notice_period'] = 'Immediate'
                    result['notice_period_days'] = 0
                elif txt.lower().startswith('serving'):
                    result['notice_period'] = 'Serving Notice'
                    result['notice_period_days'] = 0
                else:
                    months = int(txt)
                    result['notice_period'] = f"{months} Month{'s' if months != 1 else ''}"
                    result['notice_period_days'] = months * 30
                logger.info(f"[Regex Backfill] Notice: {result['notice_period']}")
                break

    # ── Location ──
    if not result.get('location'):
        loc_patterns = [
            re.compile(r'(?:Lacs?|LPA|Cr)\)?\.?\s*([A-Z][a-z]+(?:[,\s]+[A-Z][a-z]+){0,2})\s*Current'),
            re.compile(r'Current\s+Location[:\s]+([A-Za-z][A-Za-z\s,]+?)(?:\s*[\|\n•]|\s+Notice|\s+CTC)', re.IGNORECASE),
            re.compile(r'Location[:\s]+([A-Za-z][A-Za-z\s,]+?)(?:\s*[\|\n•]|\s*$)', re.IGNORECASE),
        ]
        for pat in loc_patterns:
            m = pat.search(raw_text)
            if m:
                loc = m.group(1).strip().rstrip(',')
                if len(loc) > 2 and loc.lower() not in ('the', 'and', 'for', 'not'):
                    result['location'] = loc
                    logger.info(f"[Regex Backfill] Location: {result['location']}")
                    break

    # ── Education (if empty or missing) ──
    edu = result.get('education', [])
    if not edu:
        degree_patterns = [
            re.compile(r'(B\.?Tech|B\.?E\.?|M\.?Tech|M\.?E\.?|MBA|MCA|BCA|B\.?Sc|M\.?Sc|BBA|B\.?Com|M\.?Com|Ph\.?D|Diploma)', re.IGNORECASE),
        ]
        for pat in degree_patterns:
            matches = pat.findall(raw_text)
            if matches:
                for deg in set(matches[:3]):
                    result.setdefault('education', []).append({
                        "degree": deg,
                        "institution": "Not Available",
                        "year_of_passing": "",
                        "specialization": None,
                        "score": None
                    })
                logger.info(f"[Regex Backfill] Education: {len(result.get('education', []))} degrees found")
                break

    # ── Highest Qualification ──
    if not result.get('highest_qualification') and result.get('education'):
        priority = ['Ph.D', 'M.Tech', 'M.E.', 'MBA', 'M.Sc', 'M.Com', 'MCA', 'B.Tech', 'B.E.', 'B.Sc', 'BBA', 'B.Com', 'BCA', 'Diploma']
        for p in priority:
            for edu_item in result.get('education', []):
                if p.lower() in (edu_item.get('degree', '') or '').lower():
                    result['highest_qualification'] = edu_item.get('degree', p)
                    break
            if result.get('highest_qualification'):
                break

    return result



def _parse_work_date(date_str):
    """Parse Naukri-style work-experience dates into (year, month).
    Handles: 'Jun 2022', "Jun '22", 'June 2020', '2020', 'Present', 'Current', 'Till Date', etc.
    Returns (year:int, month:int) or None if cannot parse. Month defaults to 6 (mid-year) if absent.
    """
    import re
    from datetime import datetime
    if not date_str or not isinstance(date_str, str):
        return None
    s = date_str.strip()
    if not s:
        return None
    # Present / Current / Till Date → now
    if re.search(r'\b(present|current|till\s*date|now|ongoing)\b', s, re.IGNORECASE):
        now = datetime.utcnow()
        return (now.year, now.month)
    months = {
        'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
        'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
        'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9,
        'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12,
    }
    # "Jun 2022" / "Jun '22" / "June 2020" / "06/2022" / "06-2022" / "2022"
    m = re.search(r"([A-Za-z]{3,9})[\s,'`]+(\d{2,4})", s)
    if m:
        mo = months.get(m.group(1).lower())
        if mo:
            yr = int(m.group(2))
            if yr < 100:
                yr += 2000 if yr < 70 else 1900
            return (yr, mo)
    m = re.search(r"(\d{1,2})[/\-\.](\d{2,4})", s)
    if m:
        mo = int(m.group(1))
        yr = int(m.group(2))
        if yr < 100:
            yr += 2000 if yr < 70 else 1900
        if 1 <= mo <= 12:
            return (yr, mo)
    # Year only
    m = re.search(r"\b(19|20)(\d{2})\b", s)
    if m:
        return (int(m.group(1) + m.group(2)), 6)
    return None


def _compute_duration(from_date: str, to_date: str, is_current: bool = False) -> Optional[str]:
    """Compute 'Xy Ym' from date range. Returns None if unable to compute."""
    from datetime import datetime
    f = _parse_work_date(from_date)
    if not f:
        return None
    if is_current or not to_date or not str(to_date).strip():
        now = datetime.utcnow()
        t = (now.year, now.month)
    else:
        t = _parse_work_date(to_date)
        if not t:
            now = datetime.utcnow()
            t = (now.year, now.month)
    total_from = f[0] * 12 + f[1]
    total_to = t[0] * 12 + t[1]
    diff = max(0, total_to - total_from)
    years = diff // 12
    months = diff % 12
    return f"{years}y {months}m"


def _fix_work_experience_durations(result: dict) -> dict:
    """Post-process work_experience list: compute duration from from_date/to_date
    whenever duration is missing, empty, or the '0y 0m' placeholder produced by LLMs.
    """
    work = result.get("work_experience")
    if not isinstance(work, list):
        return result
    fixed_count = 0
    for exp in work:
        if not isinstance(exp, dict):
            continue
        dur = (exp.get("duration") or "").strip().lower()
        needs_fix = (
            not dur
            or dur in ("0y 0m", "0 y 0 m", "0 years 0 months", "0y0m")
            or dur.startswith("0y 0m")
        )
        if needs_fix:
            computed = _compute_duration(
                exp.get("from_date"),
                exp.get("to_date"),
                bool(exp.get("is_current")),
            )
            if computed and computed != "0y 0m":
                exp["duration"] = computed
                fixed_count += 1
    if fixed_count:
        logger.info(f"[DurationFix] Recomputed {fixed_count} work_experience durations")
    return result


def _fix_experience_from_raw_text(result: dict, raw_text: str) -> dict:
    """
    Post-processing: Extract experience_years from raw text using regex
    and override the LLM's value. LLMs often use standard math division
    (months/12) instead of our custom formula (months/100).
    
    Formula: Years + (Months / 100)
    "7y 3m" = 7.03, "2y 5m" = 2.05, "0y 8m" = 0.08
    """
    import re
    
    patterns = [
        # "5y 8m", "5Y 8M", "5y8m"
        r'(\d{1,2})\s*[yY]\s*(\d{1,2})\s*[mM]',
        # "5 years 8 months", "5 year 3 month"
        r'(\d{1,2})\s*(?:years?)\s*(\d{1,2})\s*(?:months?)',
        # "5 Yrs 8 Mos"
        r'(\d{1,2})\s*(?:yrs?)\s*(\d{1,2})\s*(?:mos?)',
        # "5 Years, 8 Months" (with comma)
        r'(\d{1,2})\s*(?:years?|yrs?)\s*[,.\s]+\s*(\d{1,2})\s*(?:months?|mos?)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            years = int(match.group(1))
            months = int(match.group(2))
            correct_exp = round(years + (months / 100), 2)
            llm_exp = result.get("experience_years")
            if llm_exp != correct_exp:
                logger.info(f"[ExpFix] Corrected experience: {llm_exp} -> {correct_exp} (from '{match.group(0)}')")
                result["experience_years"] = correct_exp
                result["_experience_corrected"] = True
            return result
    
    # Year-only patterns (no months mentioned)
    year_only_patterns = [
        # "Experience : 8 Years" or "Total Experience: 8 Years" (header format)
        r'(?:Total\s*)?Experience\s*[:\-]\s*(\d{1,2})\s*(?:years?|yrs?)',
        # Naukri header: "8 Years | Current CTC" or "8 Years₹" 
        r'(\d{1,2})\s*(?:years?|yrs?)\s*(?:[|\u20b9₹•,])',
    ]
    
    for pattern in year_only_patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            years = int(match.group(1))
            if years > 0:
                correct_exp = float(years)
                llm_exp = result.get("experience_years")
                # Only override if LLM value seems wrong (e.g., defaulted to 1)
                if llm_exp is None or (llm_exp <= 1 and years > 1):
                    logger.info(f"[ExpFix] Corrected experience (year-only): {llm_exp} -> {correct_exp} (from '{match.group(0)}')")
                    result["experience_years"] = correct_exp
                    result["_experience_corrected"] = True
                return result
    
    return result


# ══════════════════════════════════════════════════════════════════════════
# Pod-reachability gate — enforces strict Qwen-only policy
# ══════════════════════════════════════════════════════════════════════════
# User requirement (2026-05-01): when the RunPod vLLM pod IS reachable, the
# pipeline must NOT fall back to Anthropic / Emergent even if Qwen emits
# malformed JSON that our 3 retries can't recover. Only when the pod is
# genuinely down (DNS, connect refused, 5xx health) may the Anthropic /
# Emergent fallback trigger. This makes Qwen-share approach ~100% when the
# pod is healthy and cleanly isolates "pod outage" from "bad profile text".

_RUNPOD_PING_STATE: Dict[str, float] = {"ok_until": 0.0, "fail_until": 0.0, "last_result": True}
_RUNPOD_PING_OK_TTL = 60.0    # trust "reachable" for 60s
_RUNPOD_PING_FAIL_TTL = 10.0  # recheck "unreachable" every 10s
_RUNPOD_PING_TIMEOUT = 4.0    # seconds — fast fail for pod health check


async def is_runpod_reachable() -> bool:
    """Lightweight health probe for the RunPod vLLM pod with TTL cache.

    Returns True when the pod responds to `/v1/models` with any <500 HTTP
    status within 4s. Any network error (ConnectError, ReadTimeout, DNS
    failure, RemoteProtocolError) or 5xx is treated as unreachable.
    """
    import time as _t

    now = _t.time()
    if now < _RUNPOD_PING_STATE["ok_until"]:
        return True
    if now < _RUNPOD_PING_STATE["fail_until"]:
        return False

    if not RUNPOD_VLLM_URL:
        _RUNPOD_PING_STATE.update({
            "ok_until": 0.0,
            "fail_until": now + _RUNPOD_PING_FAIL_TTL,
            "last_result": False,
        })
        return False

    url = f"{RUNPOD_VLLM_URL.rstrip('/')}/v1/models"
    headers = {}
    if RUNPOD_API_KEY:
        headers["Authorization"] = f"Bearer {RUNPOD_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=_RUNPOD_PING_TIMEOUT) as c:
            r = await c.get(url, headers=headers)
            if r.status_code < 500:
                _RUNPOD_PING_STATE.update({
                    "ok_until": now + _RUNPOD_PING_OK_TTL,
                    "fail_until": 0.0,
                    "last_result": True,
                })
                return True
            logger.warning(f"[RunPod-ping] health HTTP {r.status_code} — treating as unreachable")
    except (httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout,
            httpx.RemoteProtocolError, httpx.ConnectTimeout) as e:
        logger.warning(f"[RunPod-ping] network: {type(e).__name__}: {str(e)[:120]} — pod unreachable")
    except Exception as e:
        logger.warning(f"[RunPod-ping] unexpected: {type(e).__name__}: {str(e)[:120]} — pod unreachable")

    _RUNPOD_PING_STATE.update({
        "ok_until": 0.0,
        "fail_until": now + _RUNPOD_PING_FAIL_TTL,
        "last_result": False,
    })
    return False


def invalidate_runpod_ping_cache() -> None:
    """Force the next extraction to re-probe the pod."""
    _RUNPOD_PING_STATE.update({"ok_until": 0.0, "fail_until": 0.0})




async def extract_full_profile_fallback(raw_text: str, candidate_name: str = None) -> dict:
    """
    PRIMARY: Extract full candidate profile using Claude Haiku 4.5 (via Emergent LLM Key).
    Uses the detailed prompt with all extraction rules for high-quality results.
    """
    logger.info(f"[Haiku-Primary] Starting extraction for {candidate_name or 'Unknown'}")
    
    system_prompt = """You are an expert data-extraction agent for recruitment profiles (Naukri, LinkedIn, Monster, resume text).

============================================================
CRITICAL — STRUCTURAL ANCHOR (Naukri Top Card)
============================================================
Naukri profiles are structured. The FIRST 800–1500 characters of the text contain a "Top Card" with the canonical values for Experience, Current CTC, Expected CTC, Current Location, Notice Period, Current Employer, Current Designation, and Highest Degree. THESE ARE SOURCE-OF-TRUTH values. You MUST extract them if they are present in the header region.

Common Naukri top-card patterns and how to map them:
  • "22y"                           →  experience_years = 22.00
  • "10y 3m"                        →  experience_years = 10.03   (years + months/100, NOT months/12)
  • "5y"                            →  experience_years = 5.00
  • "₹60 Lacs (expects: ₹80 Lacs)"  →  current_ctc = 6000000   expected_ctc = 8000000
  • "₹60 Lacs"                      →  current_ctc = 6000000
  • "60 LPA"                        →  current_ctc = 6000000
  • "18.5 Lakhs"                    →  current_ctc = 1850000
  • "Indore"                        →  location = "Indore"
  • "Current: Head Mfg at Mahindra" →  current_designation = "Head Mfg", current_employer = "Mahindra"
  • "3 Months" / "60 days" / "Immediate" → notice_period = that string, notice_period_days = 90 / 60 / 0

IF THE TOP CARD SHOWS A VALUE, YOU MUST RETURN IT. Leaving it null when it is visible in the header is a CRITICAL FAILURE. Only use null when the field is genuinely absent.
Return expected_ctc SEPARATELY from current_ctc — never merge them.

============================================================
OUTPUT — return ONLY valid JSON (no markdown, no commentary):
============================================================
{
    "name": "full name",
    "email": "email address",
    "phone": "phone number",
    "location": "current location/city (from top card)",
    "experience_years": total years as decimal number (from top card),
    "current_employer": "current company name (from top card)",
    "current_designation": "current job title (from top card)",
    "current_ctc": CTC in RUPEES (convert lakhs → rupees, see examples above),
    "expected_ctc": expected CTC in RUPEES (never reuse current_ctc for this),
    "notice_period": "exact label e.g. 'Immediate', '15 Days', '30 Days', '2 Months', '3 Months'",
    "notice_period_days": notice period in days (Immediate=0, 15 Days=15, 1 Month=30, 2 Months=60, 3 Months=90),
    "profile_summary": "2-3 sentence professional summary",
    "headline": "professional headline or null",
    "key_skills": ["skill1", "skill2"],
    "work_experience": [
        {
            "company": "company name",
            "designation": "job title",
            "from_date": "start date (e.g., Jun 2022, Jan 2018, 2015)",
            "to_date": "end date or 'Present'",
            "is_current": true/false,
            "duration": "e.g. 2y 3m — compute from from_date to to_date (or today if Present). NEVER return '0y 0m' unless the role is less than 1 month old.",
            "description": "full role description"
        }
    ],
    "education": [
        {
            "degree": "degree name (e.g., B.Tech, MBA, M.Sc, B.E., Bachelor, Master, Ph.D)",
            "institution": "college/university name (or 'Not Available' if not found)",
            "specialization": "specialization or null",
            "year_of_passing": "graduation year (e.g., 2015, 2020, or 'Not Available' if not found)",
            "score": "GPA/percentage if available (or null if not found)"
        }
    ],
    "certifications": ["cert1"],
    "languages": ["lang1"],
    "projects": [{"name": "string", "description": "string"}],
    "online_profiles": [{"platform": "string", "url": "string"}],
    "preferred_locations": ["city1"],
    "highest_qualification": "string or null",
    "current_department": "string or null",
    "current_industry": "string or null"
}

============================================================
EXTRACTION ORDER (follow strictly):
============================================================
STEP 1 — Scan the FIRST 1500 characters (the Top Card). Extract: experience_years, current_ctc, expected_ctc, location, notice_period, current_employer, current_designation. If any of these values are visible in the header, you MUST populate them.
STEP 2 — Scan the rest of the profile for work_experience, education, skills, certifications, projects.
STEP 3 — Cross-check: if top-card current_employer/current_designation was found, ensure the first item of work_experience matches.

CTC CONVERSION RULES (CRITICAL):
- "Lacs" / "Lakhs" / "L" → multiply by 100000. "60 Lacs" = 6000000.
- "LPA" = Lakhs Per Annum. "60 LPA" = 6000000.
- "Cr" / "Crore" → multiply by 10000000. "1.2 Cr" = 12000000.
- If only a raw number is given (e.g. "600000"), return it as-is.
- Cap sanity: reject values > 500000000 (₹50 Cr) — those are data entry errors.

NOTICE PERIOD MAPPING:
- "Immediate" / "Immediately" / "0 days" / "Available to join" → notice_period_days = 0
- "15 days" / "15 Days or less" / "2 weeks" → 15
- "30 days" / "1 month" → 30
- "60 days" / "2 months" → 60
- "90 days" / "3 months" → 90
- ">3 months" / "90+ days" → 120

EXPERIENCE RULES:
- Use this SPECIAL formula: experience_years = Years + (Months / 100). This is NOT math — each month adds 0.01, NOT 0.083:
  * "7y 3m" = 7.03    (NOT 7.25)
  * "22y" = 22.00
  * "10+ years" = 10.00
- ALWAYS return experience_years as a decimal number (float).
- If the top card shows experience (common in Naukri), USE THAT VALUE directly.

EDUCATION RULES:
- Look for degrees (B.Tech, B.E., MBA, M.Tech, M.Sc, Bachelor, Master, BBA, MCA, Ph.D).
- Look for institutions: college, university, institute, IIT, NIT, IIM.
- If top card shows "Ph.D/Doctorate Indian Institute of Management, Kolkata", extract degree="Ph.D", institution="Indian Institute of Management, Kolkata".
- If you find ONLY a degree but no institution, still return it with institution="Not Available".
- Never return education where ALL fields are "Not Available" — return [] instead.

GENERAL RULES:
- DO NOT mix education with work experience.
- Extract ALL skills mentioned anywhere (Key Skills, IT Skills, Technical Skills).
- For each work_experience item, write a 2-3 sentence description.
- Return ONLY the JSON. No markdown fences, no explanations.
"""

    user_prompt = f"Extract complete profile:\n\n{raw_text[:50000]}"

    import time
    start_time = time.time()
    fallback_chain = []

    # Runtime skip flag — set RUNPOD_SKIP=1 to bypass RunPod (e.g., when pod is known down)
    runpod_skip = os.environ.get("RUNPOD_SKIP", "").lower() in ("1", "true", "yes")

    # LAYER 1: RunPod vLLM (Qwen 14B) — self-hosted
    if RUNPOD_VLLM_URL and not runpod_skip:
        fallback_chain.append("runpod_qwen14b")
        llm_response = await _call_runpod_vllm(system_prompt, user_prompt)
        if llm_response:
            content = _extract_json_from_response(llm_response["content"])
            try:
                result = json.loads(content)
                result = _fix_experience_from_raw_text(result, raw_text)
                result = _fix_work_experience_durations(result)
                result = _regex_backfill_critical(result, raw_text)
                result["_extraction_source"] = "runpod_qwen14b"
                result["source"] = "runpod_qwen14b"
                elapsed = int((time.time() - start_time) * 1000)
                logger.info(f"[Layer1-RunPod] SUCCESS for {candidate_name} ({elapsed}ms)")
                await _log_extraction_event(None, candidate_name, "runpod_qwen14b", True, fallback_chain, elapsed)
                return result
            except json.JSONDecodeError as e:
                logger.error(f"[Layer1-RunPod] JSON decode error: {e} (content length: {len(content)})")
                # Use json_repair library as nuclear fallback
                try:
                    from json_repair import repair_json
                    repaired = repair_json(content, return_objects=True)
                    # Accept any dict with meaningful content (name, experience_years, or current_employer)
                    if isinstance(repaired, dict) and (
                        repaired.get("name") or repaired.get("experience_years") is not None
                        or repaired.get("current_employer") or repaired.get("key_skills")
                    ):
                        result = repaired
                        result = _fix_experience_from_raw_text(result, raw_text)
                        result = _fix_work_experience_durations(result)
                        result = _regex_backfill_critical(result, raw_text)
                        result["_extraction_source"] = "runpod_qwen14b"
                        result["source"] = "runpod_qwen14b"
                        elapsed = int((time.time() - start_time) * 1000)
                        logger.info(f"[Layer1-RunPod] SUCCESS (json_repair) for {candidate_name} ({elapsed}ms)")
                        await _log_extraction_event(None, candidate_name, "runpod_qwen14b", True, fallback_chain, elapsed)
                        return result
                    else:
                        logger.warning(f"[Layer1-RunPod] json_repair returned empty/invalid dict for {candidate_name} — will attempt temp=0.1 retry")
                except Exception as repair_err:
                    logger.error(f"[Layer1-RunPod] json_repair also failed: {repair_err}")

                # ── Final retry at temperature=0.1 with truncated prompt ──
                # Qwen occasionally emits malformed JSON mid-stream at temp=0 due to
                # greedy sampling. A tiny temperature burst + shorter context resolves ~90%
                # of these cases without escalating to the paid Anthropic fallback.
                try:
                    short_prompt = f"Extract complete profile in ONE valid JSON (no commentary):\n\n{user_prompt.split(chr(10), 2)[-1][:20000]}"
                    retry_response = await _call_runpod_vllm(system_prompt, short_prompt, temperature=0.1, retry=False, disable_guided=True)
                    if retry_response:
                        retry_content = _extract_json_from_response(retry_response["content"])
                        try:
                            result = json.loads(retry_content)
                        except json.JSONDecodeError:
                            from json_repair import repair_json
                            result = repair_json(retry_content, return_objects=True)
                        if isinstance(result, dict) and (
                            result.get("name") or result.get("experience_years") is not None
                            or result.get("current_employer") or result.get("key_skills")
                        ):
                            result = _fix_experience_from_raw_text(result, raw_text)
                            result = _fix_work_experience_durations(result)
                            result = _regex_backfill_critical(result, raw_text)
                            result["_extraction_source"] = "runpod_qwen14b_retry"
                            result["source"] = "runpod_qwen14b_retry"
                            elapsed = int((time.time() - start_time) * 1000)
                            logger.info(f"[Layer1-RunPod] SUCCESS (temp=0.1 retry) for {candidate_name} ({elapsed}ms)")
                            await _log_extraction_event(None, candidate_name, "runpod_qwen14b_retry", True, fallback_chain, elapsed)
                            return result
                except Exception as retry_err:
                    logger.error(f"[Layer1-RunPod] Temp-retry also failed: {retry_err}")

                # ── Third retry: text_mode (no response_format), shortest prompt ──
                # Some vLLM 0.6+ builds garble JSON even at temp=0.1 when the
                # prompt includes structured-output hints. Drop all constraints
                # and let Qwen free-form, then json_repair whatever comes out.
                try:
                    bare_prompt = f"Extract profile fields as JSON only:\n{user_prompt.split(chr(10), 2)[-1][:15000]}"
                    r3 = await _call_runpod_vllm(system_prompt, bare_prompt, temperature=0.2, retry=False, disable_guided=True, text_mode=True)
                    if r3:
                        from json_repair import repair_json
                        result = repair_json(_extract_json_from_response(r3["content"]), return_objects=True)
                        if isinstance(result, dict) and (
                            result.get("name") or result.get("experience_years") is not None
                            or result.get("current_employer") or result.get("key_skills")
                        ):
                            result = _fix_experience_from_raw_text(result, raw_text)
                            result = _fix_work_experience_durations(result)
                            result = _regex_backfill_critical(result, raw_text)
                            result["_extraction_source"] = "runpod_qwen14b_bare"
                            result["source"] = "runpod_qwen14b_bare"
                            elapsed = int((time.time() - start_time) * 1000)
                            logger.info(f"[Layer1-RunPod] SUCCESS (bare-text retry) for {candidate_name} ({elapsed}ms)")
                            await _log_extraction_event(None, candidate_name, "runpod_qwen14b_bare", True, fallback_chain, elapsed)
                            return result
                except Exception as bare_err:
                    logger.error(f"[Layer1-RunPod] Bare-text retry also failed: {bare_err}")
                fallback_chain.append("runpod_json_fail")
        else:
            fallback_chain.append("runpod_call_fail")
        logger.warning(f"[Layer1-RunPod] Failed for {candidate_name}, checking pod reachability before fallback...")

    # ══════════════════════════════════════════════════════════════════════
    # STRICT QWEN-ONLY POLICY (requested 2026-05-01)
    # ══════════════════════════════════════════════════════════════════════
    # If the pod is reachable, skip Anthropic/Emergent entirely. The
    # candidate will be tagged `qwen_reachable_unrecovered` so you can see
    # in the report exactly which profiles Qwen couldn't parse even when
    # the pod was healthy — typically truncated raw_text_for_enrichment or
    # genuinely corrupt DOM captures. These are safe to retry later.
    if RUNPOD_VLLM_URL:
        pod_up = await is_runpod_reachable()
        if pod_up:
            elapsed = int((time.time() - start_time) * 1000)
            fallback_chain.append("strict_qwen_no_fallback")
            logger.error(
                f"[Extraction] STRICT-QWEN: pod is REACHABLE but Qwen couldn't "
                f"parse {candidate_name} after 3 retries. "
                f"Refusing to fall back to paid LLMs. Tag=qwen_reachable_unrecovered"
            )
            await _log_extraction_event(
                None, candidate_name, "qwen_reachable_unrecovered",
                False, fallback_chain, elapsed,
            )
            return {
                "error": "Qwen failed but pod is reachable — strict Qwen-only policy blocks Anthropic/Emergent fallback",
                "source": "qwen_reachable_unrecovered",
                "_extraction_source": "qwen_reachable_unrecovered",
                "_fallback_chain": fallback_chain,
            }
        logger.warning(f"[Extraction] pod UNREACHABLE — allowing Anthropic/Emergent fallback for {candidate_name}")
        fallback_chain.append("pod_unreachable")

    # LAYER 2: Emergent LLM Key → Claude Haiku 4.5 (last-resort fallback)
    # NOTE (Option-A architecture, 2026-05-05):
    # Anthropic Direct API (with 4-key rotation) was REMOVED in Phase 51 to
    # eliminate dual billing + the recurring "credit balance too low" outage.
    # The Emergent Universal Key bills through one channel and still uses
    # Claude Haiku 4.5 under the hood — same quality, simpler ops.
    fallback_chain.append("emergent_haiku")
    llm_response = await _call_emergent_llm_haiku(system_prompt, user_prompt)
    if llm_response:
        content = _extract_json_from_response(llm_response["content"])
        try:
            result = json.loads(content)
            result = _fix_experience_from_raw_text(result, raw_text)
            result = _fix_work_experience_durations(result)
            result["_extraction_source"] = "emergent_haiku_4_5"
            result["source"] = "emergent_haiku_4_5"
            elapsed = int((time.time() - start_time) * 1000)
            logger.info(f"[Layer2-Emergent] SUCCESS for {candidate_name} ({elapsed}ms)")
            await _log_extraction_event(None, candidate_name, "emergent_haiku_4_5", True, fallback_chain, elapsed)
            return result
        except json.JSONDecodeError as e:
            logger.error(f"[Layer2-Emergent] JSON decode error: {e}")
            try:
                from json_repair import repair_json
                repaired = repair_json(content, return_objects=True)
                if isinstance(repaired, dict) and repaired.get("name"):
                    result = repaired
                    result = _fix_experience_from_raw_text(result, raw_text)
                    result = _fix_work_experience_durations(result)
                    result = _regex_backfill_critical(result, raw_text)
                    result["_extraction_source"] = "emergent_haiku_4_5"
                    result["source"] = "emergent_haiku_4_5"
                    elapsed = int((time.time() - start_time) * 1000)
                    logger.info(f"[Layer2-Emergent] SUCCESS (json_repair) for {candidate_name} ({elapsed}ms)")
                    await _log_extraction_event(None, candidate_name, "emergent_haiku_4_5", True, fallback_chain, elapsed)
                    return result
            except Exception:
                pass
            fallback_chain.append("emergent_json_fail")
    else:
        fallback_chain.append("emergent_call_fail")

    elapsed = int((time.time() - start_time) * 1000)
    logger.error(f"[Extraction] BOTH LAYERS FAILED for {candidate_name} (Qwen + Emergent)")
    await _log_extraction_event(None, candidate_name, "all_failed", False, fallback_chain, elapsed)
    # Return a tagged error result — the caller uses `error` to skip
    # enrichment. We tag `_extraction_source="all_failed"` explicitly so no
    # candidate ever lands in the DB with `ai_enrichment_source=None` (which
    # makes them impossible to re-queue for retry).
    return {
        "error": "All LLM providers failed",
        "source": "all_failed",
        "_extraction_source": "all_failed",
        "_fallback_chain": fallback_chain,
    }
