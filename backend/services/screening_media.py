"""
screening_media.py — inbound WhatsApp media: documents, images, voice
=====================================================================

Graph API two-step fetch (media id → signed url → bytes), storage via
the platform's upload_to_r2 (which itself falls back to local disk when
R2_ENABLED=0), and optional voice-note transcription through the Groq
audio endpoint (same key as the LLM adapter).

  AGENT_STT=1        enable voice-note transcription
  AGENT_STT_MODEL    default whisper-large-v3
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com"


def _token() -> Optional[str]:
    return os.environ.get("WHATSAPP_ACCESS_TOKEN")


async def download_media(media_id: str) -> Optional[Dict[str, Any]]:
    """Return {bytes, mime, filename} or None."""
    token = _token()
    if not token:
        logger.error("[AshaMedia] WHATSAPP_ACCESS_TOKEN missing")
        return None
    version = os.environ.get("WHATSAPP_API_VERSION", "v25.0")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            meta = await client.get(f"{GRAPH_BASE}/{version}/{media_id}",
                                    headers={"Authorization": f"Bearer {token}"})
            if meta.status_code != 200:
                logger.error("[AshaMedia] meta HTTP %s", meta.status_code)
                return None
            info = meta.json()
            blob = await client.get(info["url"], headers={"Authorization": f"Bearer {token}"})
            if blob.status_code != 200:
                logger.error("[AshaMedia] blob HTTP %s", blob.status_code)
                return None
            return {"bytes": blob.content,
                    "mime": info.get("mime_type", "application/octet-stream"),
                    "size": info.get("file_size")}
    except Exception as e:
        logger.error("[AshaMedia] download failed: %s", e)
        return None


_EXT = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png",
        "application/msword": "doc", "audio/ogg": "ogg", "audio/mpeg": "mp3",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx"}


_uploader = None  # tests inject; production lazy-imports r2_storage


async def store_candidate_doc(db, candidate_id: str, doc_key: str,
                              media: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Persist a received document onto the candidate record."""
    global _uploader
    if _uploader is None:
        from services.r2_storage import upload_to_r2  # platform util, local fallback built in
        _uploader = upload_to_r2
    upload_to_r2 = _uploader
    from models.neural_schema import utcnow
    ext = _EXT.get(media["mime"], "bin")
    key = f"agent_docs/{candidate_id}/{doc_key}_{int(utcnow().timestamp())}.{ext}"
    try:
        res = await upload_to_r2(media["bytes"], key, media["mime"])
    except Exception as e:
        logger.error("[AshaMedia] store failed: %s", e)
        return None
    entry = {"kind": doc_key, "r2_key": key, "mime": media["mime"],
             "size": media.get("size"), "received_at": utcnow(),
             "storage": res if isinstance(res, dict) else {}}
    await db.candidate_bank.update_one(
        {"id": candidate_id},
        {"$push": {"agent_documents": entry},
         "$set": {"needs_reparse": doc_key == "updated_cv", "updated_at": utcnow()}})
    return entry


async def transcribe_voice(media: Dict[str, Any]) -> Optional[str]:
    """Groq Whisper transcription; None when AGENT_STT is off/unavailable."""
    if os.environ.get("AGENT_STT", "0") != "1":
        return None
    key = os.environ.get("AGENT_LLM_API_KEY") or os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    base = os.environ.get("AGENT_LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    model = os.environ.get("AGENT_STT_MODEL", "whisper-large-v3")
    ext = _EXT.get(media["mime"], "ogg")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{base}/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                files={"file": (f"note.{ext}", media["bytes"], media["mime"])},
                data={"model": model, "language": "hi", "response_format": "text"},
            )
        if r.status_code != 200:
            logger.warning("[AshaSTT] HTTP %s", r.status_code)
            return None
        text = r.text.strip()
        return text or None
    except Exception as e:
        logger.warning("[AshaSTT] %s", e)
        return None


def voice_unavailable_text(language: str) -> str:
    return ("Voice note mila 🙏 — filhaal kripya text mein reply karein."
            if language in ("hi", "hinglish")
            else "Got your voice note 🙏 — for now, please reply in text.")
