"""Provider adapters for Nemotron Ultra → Nemotron Super → Emergent Haiku."""
import asyncio
import logging
import os
import random
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)
HAIKU_MODEL = "claude-haiku-4-5-20251001"
PROVIDER_TIMEOUT = 90.0


class ProviderError(RuntimeError):
    """Sanitized failure suitable for storing with an extraction attempt."""


async def _nvidia(model_key, system_prompt, user_prompt, temperature, max_tokens, text_mode):
    key = os.environ.get("NEMOTRON_API_KEY")
    base_url = os.environ.get("NEMOTRON_BASE_URL")
    model = os.environ.get(model_key)
    if not key or not base_url or not model:
        raise ProviderError("not_configured")
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt},
                     {"role": "user", "content": user_prompt}],
        "temperature": temperature, "max_tokens": max_tokens, "stream": False,
    }
    if model.startswith("nvidia/nemotron-3"):
        # Hosted Nemotron does not support response_format. Validate JSON locally.
        payload["chat_template_kwargs"] = {"enable_thinking": False}
        payload["reasoning_effort"] = "none"
        if model_key == "NVIDIA_FALLBACK_MODEL":
            payload["temperature"] = 1.0
            payload["top_p"] = 0.95
    else:
        raise ProviderError("unsupported_model_configuration")
    try:
        # The wall-clock budget covers ALL retries, not 90 seconds per attempt.
        async with asyncio.timeout(PROVIDER_TIMEOUT):
            async with httpx.AsyncClient(timeout=httpx.Timeout(PROVIDER_TIMEOUT, connect=10.0)) as client:
                for attempt in range(3):
                    try:
                        response = await client.post(
                            f"{base_url.rstrip('/')}/chat/completions", json=payload,
                            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                        )
                    except httpx.NetworkError:
                        if attempt == 2:
                            raise
                        await asyncio.sleep(0.5 * (2 ** attempt) + random.uniform(0, 0.2))
                        continue
                    if response.status_code in (502, 503, 504) and attempt < 2:
                        await asyncio.sleep(0.5 * (2 ** attempt) + random.uniform(0, 0.2))
                        continue
                    # Permanent failures and throttling advance to the next provider.
                    response.raise_for_status()
                    data = response.json()
                    break
        choice = data["choices"][0]
        content = choice["message"].get("content")
        if choice.get("finish_reason") == "length":
            raise ProviderError("truncated_output")
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("empty_content")
        return {"content": content, "model": model, "usage": data.get("usage", {}),
                "finish_reason": choice.get("finish_reason")}
    except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
        raise ProviderError("timeout") from exc
    except httpx.HTTPStatusError as exc:
        raise ProviderError(f"http_{exc.response.status_code}") from exc
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(type(exc).__name__) from exc


async def call_nemotron(system_prompt, user_prompt, temperature=0, text_mode=False, max_tokens=16000):
    return await _nvidia("NEMOTRON_MODEL", system_prompt, user_prompt, temperature, max_tokens, text_mode)


async def call_nvidia_fallback(system_prompt, user_prompt, temperature=0, text_mode=False, max_tokens=16000):
    return await _nvidia("NVIDIA_FALLBACK_MODEL", system_prompt, user_prompt, temperature, max_tokens, text_mode)


async def call_haiku(system_prompt, user_prompt, temperature=0, text_mode=False, max_tokens=16000):
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise ProviderError("not_configured")
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    chat = LlmChat(api_key=key, session_id=f"extraction-{uuid4()}", system_message=system_prompt)
    chat = chat.with_model("anthropic", HAIKU_MODEL).with_params(
        temperature=temperature, max_tokens=max_tokens,
    )
    try:
        # Background structured job, not an interactive streamed chat response.
        response = await asyncio.wait_for(chat.send_message(UserMessage(text=user_prompt)), PROVIDER_TIMEOUT)
        if not isinstance(response, str) or not response.strip():
            raise ProviderError("empty_content")
        return {"content": response, "model": HAIKU_MODEL, "usage": {}}
    except asyncio.TimeoutError as exc:
        raise ProviderError("timeout") from exc
    except ProviderError:
        raise
    except Exception as exc:
        # Do not persist SDK exception text: it can include credentials or input.
        status = getattr(exc, "status_code", None)
        raise ProviderError(f"http_{status}" if status else type(exc).__name__) from exc