"""
Centralized LLM Service — Single entry point for all OpenAI chat completion calls.
Model-agnostic: configurable via env vars. All AI features route through here.
"""
import os
import logging
import httpx

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("LLM_DEFAULT_MODEL", "gpt-4o-mini")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


def get_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    source = "env"
    # Belt-and-suspenders: if env var is missing/empty, read directly from override file
    if not key:
        try:
            from mongo_production_override import OPENAI_API_KEY
            key = OPENAI_API_KEY
            source = "override_file"
            if key:
                os.environ["OPENAI_API_KEY"] = key
        except (ImportError, AttributeError):
            pass
    if not key:
        raise ValueError("OPENAI_API_KEY not configured — set it in .env or environment")
    # Log masked key on first call for production diagnostics
    logger.info(f"[LLM] API key loaded from {source}: {key[:8]}...{key[-4:]} (len={len(key)})")
    return key


def get_model() -> str:
    return DEFAULT_MODEL


async def chat_completion(
    system_prompt: str,
    user_prompt: str,
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = None,
    json_mode: bool = False,
    timeout: float = 120.0,
    return_usage: bool = False,
):
    """Call OpenAI chat completion API.

    Returns content string by default.
    If return_usage=True, returns {"content": str, "usage": dict, "model": str}.
    """
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

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(2):
            try:
                resp = await client.post(
                    OPENAI_API_URL,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=body,
                )
                break
            except httpx.ReadTimeout:
                if attempt == 0:
                    logger.warning(f"[LLM] ReadTimeout on attempt 1, retrying...")
                    continue
                raise RuntimeError("LLM API timeout after 2 attempts")

    if resp.status_code != 200:
        logger.error(f"[LLM] Error {resp.status_code}: {resp.text[:300]}")
        raise RuntimeError(f"LLM API error: {resp.status_code}")

    data = resp.json()
    content = data["choices"][0]["message"]["content"]

    if return_usage:
        return {
            "content": content,
            "usage": data.get("usage", {}),
            "model": data.get("model", model),
        }
    return content
