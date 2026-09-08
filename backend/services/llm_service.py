"""Shared completion interface: Nemotron → Nemotron Super 120B → Emergent Haiku."""
import asyncio
import os
from services.llm_fallback_service import call_llm_chain


def get_model() -> str:
    return os.environ["NEMOTRON_MODEL"]


async def chat_completion(system_prompt: str, user_prompt: str, model: str = None,
                          temperature: float = 0.7, max_tokens: int = None,
                          json_mode: bool = False, timeout: float = 270.0,
                          return_usage: bool = False, priority: str = "normal"):
    result = await asyncio.wait_for(call_llm_chain(
        system_prompt, user_prompt, temperature, max_tokens or 16000, json_mode=json_mode,
    ), timeout=timeout)
    if result.get("error"):
        raise RuntimeError(result["error"])
    if return_usage:
        return {"content": result["content"], "usage": result.get("usage", {}),
                "model": result.get("model"), "source": result["source"]}
    return result["content"]