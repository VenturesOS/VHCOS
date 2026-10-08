"""Provider adapters for Nemotron Super 120B → Nemotron 550B → Mistral Nemotron."""
import asyncio
import logging
import os
import random

import httpx

logger = logging.getLogger(__name__)
PROVIDER_TIMEOUT = 90.0
# Mistral Nemotron on NVIDIA NIM is intermittent: warm calls return in ~1s, cold
# calls hang. A short budget lets us use it when it is healthy without stalling
# the chain when it is not — it sits last, so a cold call just ends the chain.
MISTRAL_TIMEOUT = 15.0


class ProviderError(RuntimeError):
    """Sanitized failure suitable for storing with an extraction attempt."""


async def _nvidia(model_key, system_prompt, user_prompt, temperature, max_tokens, text_mode,
                  budget=None):
    key = os.environ.get("NEMOTRON_API_KEY")
    base_url = os.environ.get("NEMOTRON_BASE_URL")
    model = os.environ.get(model_key)
    if not key or not base_url or not model:
        raise ProviderError("not_configured")
    if budget is None:
        budget = PROVIDER_TIMEOUT
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
    elif model.startswith("mistralai/"):
        # Mistral Nemotron hosted on NVIDIA NIM accepts the vanilla payload.
        pass
    else:
        raise ProviderError("unsupported_model_configuration")
    try:
        # The wall-clock budget covers ALL retries, not the per-attempt timeout.
        async with asyncio.timeout(budget):
            async with httpx.AsyncClient(timeout=httpx.Timeout(budget, connect=10.0)) as client:
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


async def call_nvidia_mistral(system_prompt, user_prompt, temperature=0, text_mode=False, max_tokens=16000):
    return await _nvidia("NVIDIA_MISTRAL_MODEL", system_prompt, user_prompt, temperature, max_tokens, text_mode,
                         budget=MISTRAL_TIMEOUT)
