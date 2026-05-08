"""
Centralized LLM Service — Groq-first routing for cost optimization.

Order: Groq (Llama 3.3 70B) → OpenRouter Free → Claude (Emergent) fallback
All AI features route through chat_completion().

COST OPTIMIZATION:
- Groq: $0.59/M input + $0.79/M output (fast, deterministic)
- OpenRouter Free: $0 (rate-limited, may fail)
- Claude Haiku: $0.25/M input + $1.25/M output (fallback only)
"""
import os
import logging
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
# PRIMARY: Groq (fast, cheap, reliable)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# FALLBACK 1: OpenRouter Free
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_FREE_MODEL = os.environ.get("OPENROUTER_FREE_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
OPENROUTER_FALLBACK_MODEL = os.environ.get("OPENROUTER_FALLBACK_MODEL", "qwen/qwen3.6-plus-preview:free")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# FALLBACK 2: Claude (Emergent LLM Key)
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")

# FALLBACK 3: OpenAI (last resort)
OPENAI_API_KEY_RAW = os.environ.get("OPENAI_API_KEY")
DEFAULT_MODEL = os.environ.get("LLM_DEFAULT_MODEL", "gpt-4o-mini")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


def get_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        try:
            from mongo_production_override import OPENAI_API_KEY
            key = OPENAI_API_KEY
            if key:
                os.environ["OPENAI_API_KEY"] = key
        except (ImportError, AttributeError):
            pass
    if not key:
        raise ValueError("OPENAI_API_KEY not configured")
    return key


def get_model() -> str:
    return DEFAULT_MODEL


# ── Groq (PRIMARY) ──────────────────────────────────────────────────────────

async def _call_groq(messages: list, temperature: float = 0, max_tokens: int = 2000) -> dict:
    """Call Groq Llama 3.3 70B - Primary LLM for all features."""
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not configured")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            
            return {
                "content": content,
                "usage": {
                    "input": usage.get("prompt_tokens", 0),
                    "output": usage.get("completion_tokens", 0),
                },
                "model": GROQ_MODEL,
                "provider": "groq"
            }
    except Exception as e:
        logger.warning(f"[Groq] Failed: {e}")
        raise


# ── OpenRouter (FREE tier, FALLBACK 1) ──────────────────────────────────────

async def _call_openrouter(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    json_mode: bool = False,
    timeout: float = 90.0,
) -> str:
    """Call OpenRouter free model, with fallback to secondary free model. Raises on failure."""
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not set")

    models_to_try = [OPENROUTER_FREE_MODEL, OPENROUTER_FALLBACK_MODEL]
    last_error = None

    for model in models_to_try:
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.environ.get("SITE_URL", "https://ventureshrd.com"),
            "X-Title": "VHC Talent OS",
        }

        try:
            from config import get_http_client
            shared = get_http_client()
            if shared:
                resp = await shared.post(OPENROUTER_API_URL, headers=headers, json=body)
            else:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(OPENROUTER_API_URL, headers=headers, json=body)

            if resp.status_code == 429:
                last_error = f"{model} rate limited"
                logger.warning(f"[LLM] OpenRouter {model} rate limited, trying next...")
                continue
            if resp.status_code != 200:
                last_error = f"{model} error {resp.status_code}"
                logger.warning(f"[LLM] OpenRouter {model} returned {resp.status_code}, trying next...")
                continue

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content or not content.strip():
                last_error = f"{model} returned empty"
                continue

            model_used = data.get("model", model)
            logger.info(f"[LLM] OpenRouter success via {model_used}")
            return content
        except Exception as e:
            last_error = f"{model}: {e}"
            logger.warning(f"[LLM] OpenRouter {model} failed: {e}")
            continue

    raise RuntimeError(f"All OpenRouter models failed: {last_error}")


# ── Claude via Emergent ─────────────────────────────────────────────────────

async def _call_claude(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    timeout: float = 120.0,
) -> str:
    """Call Claude Haiku 4.5 via Emergent integrations."""
    if not EMERGENT_LLM_KEY:
        raise ValueError("EMERGENT_LLM_KEY not set")

    import uuid
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"llm-{uuid.uuid4().hex[:8]}",
        system_message=system_prompt,
    ).with_model("anthropic", "claude-haiku-4-5")

    content = await chat.send_message(UserMessage(text=user_prompt))
    if not content or not content.strip():
        raise RuntimeError("Claude returned empty content")

    logger.info("[LLM] Claude Haiku 4.5 (Emergent) success")
    return content


# ── Direct OpenAI ───────────────────────────────────────────────────────────

async def _call_openai(
    system_prompt: str,
    user_prompt: str,
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = None,
    json_mode: bool = False,
    timeout: float = 120.0,
) -> str:
    """Direct OpenAI API call with retry."""
    api_key = get_api_key()
    model = model or DEFAULT_MODEL

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    if max_tokens:
        body["max_tokens"] = max_tokens
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    from config import get_http_client
    shared = get_http_client()
    use_shared = shared is not None

    async def _do_openai_request():
        _client = shared if use_shared else httpx.AsyncClient(timeout=timeout)
        try:
            resp = None
            for attempt in range(3):
                try:
                    resp = await _client.post(
                        OPENAI_API_URL,
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json=body,
                    )
                    if resp.status_code in (429, 500, 502, 503):
                        wait_time = (2 ** attempt) * 2
                        logger.warning(f"[LLM] OpenAI {resp.status_code} on attempt {attempt+1}, waiting {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue
                    break
                except httpx.ReadTimeout:
                    if attempt < 2:
                        logger.warning(f"[LLM] OpenAI ReadTimeout on attempt {attempt+1}, retrying...")
                        await asyncio.sleep(2)
                        continue
                    raise RuntimeError("OpenAI API timeout after 3 attempts")
            return resp
        finally:
            if not use_shared:
                await _client.aclose()

    resp = await _do_openai_request()

    if resp is None or resp.status_code != 200:
        status = resp.status_code if resp else "no response"
        raise RuntimeError(f"OpenAI API error: {status}")

    data = resp.json()
    return data["choices"][0]["message"]["content"]


# ── Waterfall: OpenRouter → Claude → OpenAI ─────────────────────────────────

async def chat_completion(
    system_prompt: str,
    user_prompt: str,
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = None,
    json_mode: bool = False,
    timeout: float = 120.0,
    return_usage: bool = False,
    priority: str = "normal",
):
    """Waterfall LLM call: OpenRouter Free -> Claude (via Emergent) -> Direct OpenAI.

    Anthropic Direct API was REMOVED in Phase 51 (Option-A architecture,
    2026-05-05) — see comment block below.

    M-05: `priority="high"` skips free models and goes straight to Claude/OpenAI.
    Use for user-facing sync operations (matching, JD parsing) where quality matters.
    Use `priority="normal"` for background tasks where cost matters.

    Returns content string by default.
    If return_usage=True, returns {"content": str, "usage": dict, "model": str}.
    """
    errors = []

    # ── 0. Anthropic Direct API REMOVED (Option-A, 2026-05-05) ──
    # Phase 51: removed `anthropic` SDK + 4-key rotation to consolidate
    # billing under the Emergent Universal Key. The "Claude via Emergent"
    # path below still uses Claude Haiku 4.5 — same model, simpler ops,
    # one bill. The "credit balance too low" outage that contributed to
    # the May-05 OOM cascade can no longer occur from this code path.

    # ── 1. OpenRouter Free (skip for high-priority sync operations) ──
    if OPENROUTER_API_KEY and priority != "high":
        try:
            content = await _call_openrouter(
                system_prompt, user_prompt,
                temperature=temperature, json_mode=json_mode, timeout=min(timeout, 90),
            )
            if return_usage:
                return {"content": content, "usage": {}, "model": OPENROUTER_FREE_MODEL}
            return content
        except Exception as e:
            errors.append(f"OpenRouter: {e}")
            logger.warning(f"[LLM] OpenRouter failed: {e} — falling back to Claude")

    # ── 2. Claude via Emergent ──
    if EMERGENT_LLM_KEY:
        try:
            content = await _call_claude(
                system_prompt, user_prompt,
                temperature=temperature, timeout=timeout,
            )
            if return_usage:
                return {"content": content, "usage": {}, "model": "claude-haiku-4-5"}
            return content
        except Exception as e:
            errors.append(f"Claude: {e}")
            logger.warning(f"[LLM] Claude failed: {e} — falling back to OpenAI")

    # ── 3. Direct OpenAI (final fallback) ──
    try:
        content = await _call_openai(
            system_prompt, user_prompt,
            model=model, temperature=temperature,
            max_tokens=max_tokens, json_mode=json_mode, timeout=timeout,
        )
        if return_usage:
            return {"content": content, "usage": {}, "model": model or DEFAULT_MODEL}
        return content
    except Exception as e:
        errors.append(f"OpenAI: {e}")
        logger.error(f"[LLM] ALL providers failed: {errors}")
        raise RuntimeError(f"All LLM providers failed: {'; '.join(errors)}")
