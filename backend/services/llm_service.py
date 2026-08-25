"""
Centralized LLM Service — routes through RunPod Qwen 2.5-14B serverless,
with Emergent LLM (Claude Haiku 4.5) as the last-resort fallback.

Phase 55.14 rewrite (2026-08): previously routed Groq → OpenRouter → Claude →
OpenAI. All four legacy paths are removed. The `chat_completion` and
`get_model` signatures are preserved so the ~10 existing call sites
(matching_engine, blog_*, ai_search, extension_service, resume, cv_upload)
keep working without individual refactors.

For direct RunPod calls with guided-JSON schema (profile extraction), use
`services.llm_fallback_service._call_runpod_vllm` directly.
"""
import logging
import os

from services.llm_fallback_service import _call_runpod_vllm, _call_emergent_llm_haiku

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_LABEL = os.environ.get("RUNPOD_QWEN_MODEL", "Qwen/Qwen2.5-14B-Instruct-AWQ")


def get_model() -> str:
    """Kept for backward compat — some blog code logs the model name."""
    return _DEFAULT_MODEL_LABEL


async def chat_completion(
    system_prompt: str,
    user_prompt: str,
    model: str = None,           # kept for signature compat; ignored
    temperature: float = 0.7,
    max_tokens: int = None,       # kept for signature compat; ignored
    json_mode: bool = False,
    timeout: float = 120.0,       # kept for signature compat; RunPod client uses 180s
    return_usage: bool = False,
    priority: str = "normal",     # kept for signature compat; ignored
):
    """Route: RunPod Qwen (primary) → Emergent Claude Haiku 4.5 (fallback).

    Returns content string by default.
    If return_usage=True, returns {"content": str, "usage": dict, "model": str}.
    """
    # ── 1. RunPod Qwen 2.5-14B (serverless) ──
    try:
        result = await _call_runpod_vllm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            # Always disable the profile-specific guided_json schema — this
            # is a generic chat entry point, callers have their own schemas.
            disable_guided=True,
            text_mode=not json_mode,
        )
        if result and result.get("content"):
            content = result["content"]
            if return_usage:
                return {"content": content, "usage": {}, "model": _DEFAULT_MODEL_LABEL}
            return content
    except Exception as e:
        logger.warning(f"[LLM] RunPod Qwen failed: {e} — falling back to Emergent Claude Haiku")

    # ── 2. Emergent Claude Haiku 4.5 (last resort) ──
    try:
        result = await _call_emergent_llm_haiku(system_prompt, user_prompt)
        if result and result.get("content"):
            content = result["content"]
            if return_usage:
                return {"content": content, "usage": {}, "model": "claude-haiku-4-5"}
            return content
    except Exception as e:
        logger.error(f"[LLM] Emergent Claude Haiku also failed: {e}")
        raise RuntimeError(f"Both RunPod Qwen and Emergent Claude failed: {e}")

    raise RuntimeError("All LLM providers returned empty content")
