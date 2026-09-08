"""Candidate extraction: NVIDIA Nemotron Super 120B → NVIDIA Nemotron Ultra 550B → NVIDIA Mistral Nemotron → Emergent Haiku.

Every entry point uses the same ordered chain. Super leads because it handles
more captures cleanly in production; Ultra follows for the harder profiles.
No retired inference service, health probe, configuration flag, or provider-
specific gate can block fallback.
"""
import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from services.llm_providers import (
    call_nemotron as _call_nemotron,
    call_nvidia_fallback as _call_nvidia_fallback,
    call_nvidia_mistral as _call_nvidia_mistral,
    call_haiku as _call_emergent_llm_haiku,
    ProviderError,
)
from services.profile_extraction_helpers import (
    PROFILE_SYSTEM_PROMPT, _extract_json_from_response, sanitize_ctc,
    _regex_backfill_critical, _regex_backfill_critical_impl,
    _parse_work_date, _compute_duration, _fix_work_experience_durations,
    _fix_experience_from_raw_text, CTC_MAX_SANE, CTC_MIN_SANE,
)

logger = logging.getLogger(__name__)
APPROVED_SOURCES = (
    "nvidia_nemotron_super_120b",
    "nvidia_nemotron_550b",
    "nvidia_mistral_nemotron",
    "emergent_haiku_4_5",
)


class ExtractedProfile(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = Field(min_length=1)
    key_skills: list[str] | None = None
    work_experience: list[dict] | None = None
    education: list[dict] | None = None
    experience_years: float | None = None
    current_employer: str | None = None


def _valid_profile(data):
    profile = ExtractedProfile.model_validate(data)
    return bool(profile.name.strip() and (profile.key_skills or profile.work_experience
                or profile.current_employer or profile.experience_years is not None))


async def call_llm_chain(system_prompt, user_prompt, temperature=0, max_tokens=16000,
                         json_mode=False, validator=None):
    """One bounded attempt per provider, including parse/quality failure fallback."""
    chain, errors = [], []
    providers = zip(APPROVED_SOURCES, (_call_nvidia_fallback, _call_nemotron, _call_nvidia_mistral, _call_emergent_llm_haiku))
    for source, call in providers:
        chain.append(source)
        try:
            response = await call(system_prompt, user_prompt, temperature=temperature,
                                  max_tokens=max_tokens, text_mode=not json_mode)
            if not response or not isinstance(response.get("content"), str) or not response["content"].strip():
                raise ProviderError("empty_content")
            if response.get("finish_reason") == "length":
                raise ProviderError("truncated_output")
            if json_mode:
                parsed = json.loads(_extract_json_from_response(response["content"]))
                if not isinstance(parsed, dict) or not parsed:
                    raise ProviderError("invalid_json_object")
                if validator and not validator(parsed):
                    raise ProviderError("quality_check_failed")
                response["parsed"] = parsed
                response["content"] = json.dumps(parsed)
            return {**response, "source": source, "_fallback_chain": chain,
                    "_fallback_errors": errors}
        except Exception as exc:
            reason = str(exc) if isinstance(exc, ProviderError) else (
                "schema_validation_failed" if isinstance(exc, ValidationError) else type(exc).__name__)
            errors.append({"source": source, "reason": reason})
            logger.warning("[LLMChain] %s failed (%s); trying next approved provider", source, reason)
    return {"error": "All LLM providers failed", "source": "all_failed",
            "_fallback_chain": chain, "_fallback_errors": errors}


async def _log_extraction_event(db, candidate_name, source, success, fallback_chain, elapsed_ms):
    try:
        if db is None:
            from config import db
        await db.extraction_tracking.insert_one({
            "candidate_name": candidate_name, "source": source, "success": success,
            "fallback_chain": fallback_chain, "elapsed_ms": elapsed_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        })
    except Exception:
        logger.debug("Extraction tracking unavailable in this event loop")


async def extract_full_profile_fallback(raw_text: str, candidate_name: str = None) -> dict:
    started = time.monotonic()
    response = await call_llm_chain(PROFILE_SYSTEM_PROMPT,
        f"Extract complete profile:\n\n{raw_text[:50000]}", json_mode=True, validator=_valid_profile)
    if response.get("error"):
        result = {**response, "_extraction_source": "all_failed"}
    else:
        result = response["parsed"]
        result = _fix_experience_from_raw_text(result, raw_text)
        result = _fix_work_experience_durations(result)
        result = _regex_backfill_critical(result, raw_text)
        result.update(source=response["source"], _extraction_source=response["source"],
                      _fallback_chain=response["_fallback_chain"],
                      _fallback_errors=response["_fallback_errors"])
    await _log_extraction_event(None, candidate_name, result["source"], not result.get("error"),
                                result["_fallback_chain"], int((time.monotonic() - started) * 1000))
    return result


async def extract_with_fallback(system_prompt: str, user_prompt: str, temperature=0,
                                max_tokens=2000, context="unknown") -> Dict:
    result = await call_llm_chain(system_prompt, user_prompt, temperature, max_tokens, json_mode=True)
    if result.get("error"):
        return {**result, "success": False}
    return {"success": True, "data": result["parsed"], "source": result["source"],
            "_fallback_chain": result["_fallback_chain"]}


async def extract_phone_and_work_experience_fallback(raw_text: str, candidate_name: str = None) -> dict:
    result = await extract_with_fallback(
        'Extract only the candidate phone and employment history as JSON with keys "phone" '
        'and "work_experience" (array of company, designation, from_date, to_date, is_current, description). '
        'Do not include education as employment. Use null or [] for unknown values.',
        f"Candidate: {candidate_name or 'Unknown'}\n{raw_text[:24000]}", max_tokens=3500,
    )
    if result["success"]:
        return {**result["data"], "source": result["source"]}
    return {"phone": None, "work_experience": [], "error": result["error"], "source": result["source"]}