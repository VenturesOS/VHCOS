"""
screening_llm.py — Asha's LLM adapter (phrasing + extraction fallback)
======================================================================

Two narrow jobs, nothing else:
  phrase(block, name, language)      -> the outgoing question text
  extract(kind, question, reply, ctx)-> {"value": ..., "confident": bool}

Deterministic-first design: the engine tries rule parsers BEFORE calling
extract(), and phrase() falls back to the block's own template. With
AGENT_LLM=0 (or no key) the agent is fully functional and repeatable —
that is also how the test suite runs.

Provider: OpenAI-compatible chat endpoint (Groq by default) via httpx.
  AGENT_LLM            "1"|"0"          (default 1)
  AGENT_LLM_BASE_URL   default https://api.groq.com/openai/v1
  AGENT_LLM_MODEL      default llama-3.3-70b-versatile
  GROQ_API_KEY / AGENT_LLM_API_KEY
Swapping to the platform's llm_service fallback chain later means
reimplementing _chat() only.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return os.environ.get("AGENT_LLM", "1") == "1" and bool(_api_key())


def _api_key() -> Optional[str]:
    return os.environ.get("AGENT_LLM_API_KEY") or os.environ.get("GROQ_API_KEY")


def _base_url() -> str:
    return os.environ.get("AGENT_LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")


def _model() -> str:
    return os.environ.get("AGENT_LLM_MODEL", "llama-3.3-70b-versatile")


async def _chat(system: str, user: str, max_tokens: int = 300, temperature: float = 0.3) -> Optional[str]:
    if not _enabled():
        return None
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.post(
                f"{_base_url()}/chat/completions",
                headers={"Authorization": f"Bearer {_api_key()}"},
                json={
                    "model": _model(),
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
        if r.status_code != 200:
            logger.warning("[AshaLLM] HTTP %s — falling back to template", r.status_code)
            return None
        return (r.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:
        logger.warning("[AshaLLM] %s — falling back to template", e)
        return None


_LANG_NAME = {"en": "English", "hi": "Hindi (Devanagari ok)", "hinglish": "Hinglish (Hindi in Roman script)"}


async def phrase(block: Dict[str, Any], name: str, language: str) -> str:
    """Natural one-message phrasing of the block's question. Template on
    any failure — the meaning always comes from the template."""
    template = (block.get("hi") if language in ("hi", "hinglish") else block.get("en")) or block.get("en", "")
    template = template.replace("{name}", name or "ji")
    out = await _chat(
        system=(
            "You are Asha, a warm, professional recruitment assistant for Ventures HRD Centre (India). "
            f"Rewrite the given screening question naturally in {_LANG_NAME.get(language, 'English')} "
            "as ONE short WhatsApp message. Keep the exact same meaning, keep any examples in "
            "brackets, at most one emoji, no extra questions, no preamble. Output only the message."
        ),
        user=template,
        max_tokens=160,
        temperature=0.4,
    )
    if not out or len(out) > 500:
        return template
    return out


_JSON_RE = re.compile(r"\{.*\}", re.S)

_EXTRACT_SPECS = {
    "yesno":  '{"value": "yes"|"no"|"unclear", "confident": true|false}',
    "number": '{"value": <number or null>, "confident": true|false}',
    "salary": '{"value": <annual amount in lakhs (LPA) as number, or null>, "confident": true|false}',
    "notice": '{"value": <notice period in DAYS as integer, or null>, "confident": true|false}',
    "location": '{"value": "there"|"willing"|"not_willing"|"unclear", "confident": true|false}',
    "text":   '{"value": "<short cleaned answer>", "confident": true|false}',
}


async def extract(kind: str, question: str, reply: str, ctx: str = "") -> Optional[Dict[str, Any]]:
    """LLM extraction fallback (engine's rule parsers run first). Returns
    None when the LLM is off/unavailable — the engine then handles it."""
    spec = _EXTRACT_SPECS.get(kind, _EXTRACT_SPECS["text"])
    out = await _chat(
        system=(
            "You extract structured answers from Indian recruitment screening replies "
            "(English/Hindi/Hinglish; 'lakh'≈LPA, 'mahina'=month, 'din'=day, 'haan'=yes, 'nahi'=no). "
            f"Respond with ONLY this JSON, nothing else: {spec} "
            "Set confident=false if the reply does not clearly answer the question."
        ),
        user=f"Question: {question}\n{('Context: ' + ctx) if ctx else ''}\nReply: {reply}",
        max_tokens=80,
        temperature=0,
    )
    if not out:
        return None
    m = _JSON_RE.search(out)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        if "value" in data:
            return {"value": data.get("value"), "confident": bool(data.get("confident"))}
    except Exception:
        pass
    return None
