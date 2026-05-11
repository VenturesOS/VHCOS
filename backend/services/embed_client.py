"""
EC2-side HTTP client for the RunPod BGE sidecar.

When the sidecar is unreachable (pod stopped, network blip), we fall
back to the legacy *local* sentence-transformers code path if available
— so the system degrades gracefully instead of hard-failing.

Set the env var `BGE_SIDECAR_URL` to enable remote embeddings:
    BGE_SIDECAR_URL=https://<POD-ID>-8001.proxy.runpod.net

If unset → falls back to local embeddings (current behavior).
"""
from __future__ import annotations

import logging
import os
import time
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

SIDECAR_URL = os.environ.get("BGE_SIDECAR_URL", "").rstrip("/")
SIDECAR_TIMEOUT_SECS = float(os.environ.get("BGE_SIDECAR_TIMEOUT", "10"))
EMBED_DIM = 384
MAX_BATCH_SIZE = 64

# Module-level health flag — set to False after a failed call so subsequent
# calls in the same minute go straight to local fallback without retrying
# the network. Reset every minute by `_should_skip_remote()`.
_REMOTE_FAILED_AT: float = 0.0
_REMOTE_COOLDOWN_SECS = 60.0


def _should_skip_remote() -> bool:
    """Skip remote call for 60 s after a known failure to avoid hammering
    a down sidecar."""
    if _REMOTE_FAILED_AT == 0.0:
        return False
    if time.time() - _REMOTE_FAILED_AT > _REMOTE_COOLDOWN_SECS:
        return False
    return True


def _mark_remote_failed() -> None:
    global _REMOTE_FAILED_AT
    _REMOTE_FAILED_AT = time.time()


def _mark_remote_healthy() -> None:
    global _REMOTE_FAILED_AT
    _REMOTE_FAILED_AT = 0.0


def is_remote_enabled() -> bool:
    return bool(SIDECAR_URL)


def embed_remote(texts: List[str]) -> Optional[List[Optional[List[float]]]]:
    """POST /embed to the sidecar. Returns list of vectors (None for empty inputs)
    or None if the sidecar is unreachable / disabled. Caller can fall back."""
    if not SIDECAR_URL or _should_skip_remote() or not texts:
        return None

    # Chunk large batches
    if len(texts) > MAX_BATCH_SIZE:
        out: List[Optional[List[float]]] = []
        for i in range(0, len(texts), MAX_BATCH_SIZE):
            piece = embed_remote(texts[i:i + MAX_BATCH_SIZE])
            if piece is None:
                return None
            out.extend(piece)
        return out

    try:
        r = requests.post(
            f"{SIDECAR_URL}/embed",
            json={"texts": texts, "normalize": True},
            timeout=SIDECAR_TIMEOUT_SECS,
        )
        if r.status_code == 503:
            # Model not loaded yet on the sidecar — treat as a soft fail.
            logger.warning("[EmbedClient] sidecar 503 — model not warm yet")
            _mark_remote_failed()
            return None
        r.raise_for_status()
        data = r.json()
        _mark_remote_healthy()
        return data.get("embeddings")
    except (requests.RequestException, ValueError) as e:
        logger.warning(f"[EmbedClient] sidecar call failed: {e!s} — falling back")
        _mark_remote_failed()
        return None


def health_check() -> dict:
    """Cheap probe to surface in admin status pages."""
    if not SIDECAR_URL:
        return {"enabled": False, "reason": "BGE_SIDECAR_URL unset"}
    try:
        r = requests.get(f"{SIDECAR_URL}/health", timeout=5)
        r.raise_for_status()
        return {"enabled": True, "ok": True, **r.json()}
    except Exception as e:
        return {"enabled": True, "ok": False, "error": str(e)}
