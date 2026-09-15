"""
EC2-side HTTP client for the RunPod BGE sidecar — with circuit breaker.

When the sidecar is unreachable (pod stopped, network blip), we fall
back to the legacy *local* sentence-transformers code path if available
— so the system degrades gracefully instead of hard-failing.

## Circuit breaker (Phase 55.10 / Feb 2026)

States: CLOSED → OPEN → HALF_OPEN → CLOSED|OPEN

  • CLOSED   = normal. Every call hits the sidecar.
                Three consecutive failures trip → OPEN.
  • OPEN     = sidecar known down. All calls fail-fast in <1ms.
                After `BGE_BREAKER_OPEN_SECS` (default 300s), the next
                call moves the state to HALF_OPEN.
  • HALF_OPEN = a single probe call goes through.
                Success → CLOSED, reset counters.
                Failure → OPEN, reset cooldown timer.

This means the FIRST request after a RunPod death will be slow (one
10-second timeout). Every subsequent request for the next 5 minutes
is instant fallback. After 5 minutes, ONE probe call tests recovery
— if it fails, slow path skipped again for another 5 min.

## Env vars

  BGE_SIDECAR_URL              — base URL of the sidecar (required to enable)
  BGE_SIDECAR_TIMEOUT          — read timeout in seconds (default 8)
  BGE_SIDECAR_CONNECT_TIMEOUT  — connect timeout in seconds (default 2)
  BGE_BREAKER_THRESHOLD        — consecutive failures to trip (default 3)
  BGE_BREAKER_OPEN_SECS        — how long to stay OPEN (default 300)

Set BGE_SIDECAR_URL='' to disable remote entirely and always use local.

## Connection pooling

Calls share a `requests.Session` with a pooled `HTTPAdapter`
(`pool_maxsize=32`, `max_retries=0`). Keep-alive avoids TCP+TLS handshake
per call and `max_retries=0` keeps failures visible to the breaker.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import List, Optional

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

SIDECAR_URL = os.environ.get("BGE_SIDECAR_URL", "").rstrip("/")
SIDECAR_TIMEOUT_SECS = float(os.environ.get("BGE_SIDECAR_TIMEOUT", "8"))
SIDECAR_CONNECT_TIMEOUT_SECS = float(os.environ.get("BGE_SIDECAR_CONNECT_TIMEOUT", "2"))
EMBED_DIM = 384
MAX_BATCH_SIZE = 64

# Shared session with a pooled HTTPAdapter. `pool_maxsize` sets the number of
# keep-alive sockets we hold per host; anything above this queues, which is
# fine because callers always run under `asyncio.to_thread` and the breaker
# short-circuits when the sidecar is unhealthy. `max_retries=0` keeps failures
# visible to the breaker instead of masked by transparent retries.
_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=4, pool_maxsize=32, max_retries=0)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)
_REQUEST_TIMEOUT = (SIDECAR_CONNECT_TIMEOUT_SECS, SIDECAR_TIMEOUT_SECS)

# ── Circuit breaker config ───────────────────────────────────────────
_BREAKER_THRESHOLD = int(os.environ.get("BGE_BREAKER_THRESHOLD", "3"))
_BREAKER_OPEN_SECS = float(os.environ.get("BGE_BREAKER_OPEN_SECS", "300"))

_STATE_CLOSED = "closed"
_STATE_OPEN = "open"
_STATE_HALF_OPEN = "half_open"

_lock = threading.Lock()
_state: str = _STATE_CLOSED
_consecutive_failures: int = 0
_opened_at: float = 0.0
_total_failures: int = 0
_total_successes: int = 0
_total_short_circuited: int = 0  # calls that fast-failed in OPEN
_last_failure_msg: Optional[str] = None


def _transition(new_state: str) -> None:
    """Must be called with _lock held."""
    global _state, _opened_at
    if _state == new_state:
        return
    if new_state == _STATE_OPEN:
        _opened_at = time.time()
        logger.warning(
            "[EmbedClient] CIRCUIT OPEN — sidecar deemed down. "
            "Skipping remote calls for %.0fs.", _BREAKER_OPEN_SECS,
        )
    elif new_state == _STATE_HALF_OPEN:
        logger.info("[EmbedClient] CIRCUIT HALF_OPEN — probing sidecar recovery")
    elif new_state == _STATE_CLOSED:
        logger.info("[EmbedClient] CIRCUIT CLOSED — sidecar recovered, resuming normal traffic")
    _state = new_state


def _on_success() -> None:
    global _consecutive_failures, _total_successes
    with _lock:
        _consecutive_failures = 0
        _total_successes += 1
        if _state != _STATE_CLOSED:
            _transition(_STATE_CLOSED)


def _on_failure(msg: str) -> None:
    global _consecutive_failures, _total_failures, _last_failure_msg
    with _lock:
        _consecutive_failures += 1
        _total_failures += 1
        _last_failure_msg = msg[:200]
        if _state == _STATE_HALF_OPEN:
            # Probe failed — go straight back to OPEN
            _transition(_STATE_OPEN)
        elif _state == _STATE_CLOSED and _consecutive_failures >= _BREAKER_THRESHOLD:
            _transition(_STATE_OPEN)


def _should_attempt() -> bool:
    """Return True if we should make a real HTTP call (and reserve a probe
    slot if applicable). Must be cheap — runs on the hot path."""
    global _total_short_circuited
    with _lock:
        if _state == _STATE_CLOSED:
            return True
        if _state == _STATE_OPEN:
            if time.time() - _opened_at >= _BREAKER_OPEN_SECS:
                # Cooldown elapsed — promote to HALF_OPEN and let THIS call probe
                _transition(_STATE_HALF_OPEN)
                return True
            _total_short_circuited += 1
            return False
        # HALF_OPEN: only one probe in flight at a time. Subsequent concurrent
        # callers fail-fast until the probe resolves.
        _total_short_circuited += 1
        return False


def is_remote_enabled() -> bool:
    return bool(SIDECAR_URL)


def breaker_state() -> dict:
    """Snapshot of breaker state for admin UI / diagnostics."""
    with _lock:
        remaining = 0.0
        if _state == _STATE_OPEN:
            remaining = max(0.0, _BREAKER_OPEN_SECS - (time.time() - _opened_at))
        return {
            "enabled": bool(SIDECAR_URL),
            "state": _state,
            "consecutive_failures": _consecutive_failures,
            "threshold": _BREAKER_THRESHOLD,
            "open_for_seconds": _BREAKER_OPEN_SECS,
            "seconds_until_half_open": round(remaining, 1) if remaining else 0,
            "total_successes": _total_successes,
            "total_failures": _total_failures,
            "total_short_circuited": _total_short_circuited,
            "last_failure_msg": _last_failure_msg,
        }


def reset_breaker() -> None:
    """Manual reset — for admin "force retry" button or tests."""
    global _consecutive_failures
    with _lock:
        _consecutive_failures = 0
        _transition(_STATE_CLOSED)


def embed_remote(texts: List[str]) -> Optional[List[Optional[List[float]]]]:
    """POST /embed to the sidecar. Returns list of vectors (None for empty inputs)
    or None if the sidecar is unreachable / disabled / circuit-open.
    Caller falls back to local embedding on None."""
    if not SIDECAR_URL or not texts:
        return None
    if not _should_attempt():
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
        r = _session.post(
            f"{SIDECAR_URL}/embed",
            json={"texts": texts, "normalize": True},
            timeout=_REQUEST_TIMEOUT,
        )
        if r.status_code == 503:
            logger.warning("[EmbedClient] sidecar 503 — model not warm yet")
            _on_failure("HTTP 503 — model not warm")
            return None
        r.raise_for_status()
        data = r.json()
        _on_success()
        return data.get("embeddings")
    except (requests.RequestException, ValueError) as e:
        # Only log the first 2 failures in detail; once breaker opens, the
        # subsequent _should_attempt() short-circuits make this path silent.
        with _lock:
            cur_failures = _consecutive_failures
        if cur_failures < _BREAKER_THRESHOLD:
            logger.warning("[EmbedClient] sidecar call failed: %s — falling back", str(e))
        _on_failure(str(e))
        return None


def rerank_remote(query: str, documents: List[str], top_k: Optional[int] = None) -> Optional[List[dict]]:
    """POST /rerank to the sidecar. Returns list of {index, score} dicts
    sorted by score desc, or None if the sidecar is unreachable / disabled.

    Caller can fall back to bi-encoder cosine ordering on None.
    """
    if not SIDECAR_URL or not documents or not query:
        return None
    if not _should_attempt():
        return None
    try:
        r = _session.post(
            f"{SIDECAR_URL}/rerank",
            json={"query": query, "documents": documents, "top_k": top_k},
            timeout=_REQUEST_TIMEOUT,
        )
        if r.status_code == 503:
            logger.warning("[EmbedClient] rerank 503 — model not warm yet")
            _on_failure("HTTP 503 — model not warm (rerank)")
            return None
        r.raise_for_status()
        _on_success()
        return r.json().get("results")
    except (requests.RequestException, ValueError) as e:
        with _lock:
            cur_failures = _consecutive_failures
        if cur_failures < _BREAKER_THRESHOLD:
            logger.warning("[EmbedClient] rerank call failed: %s", str(e))
        _on_failure(str(e))
        return None


def health_check() -> dict:
    """Cheap probe to surface in admin status pages.
    Does NOT go through the breaker — admins want raw state."""
    if not SIDECAR_URL:
        return {"enabled": False, "reason": "BGE_SIDECAR_URL unset"}
    try:
        r = _session.get(f"{SIDECAR_URL}/health", timeout=(SIDECAR_CONNECT_TIMEOUT_SECS, 5.0))
        r.raise_for_status()
        return {
            "enabled": True,
            "ok": True,
            "breaker": breaker_state(),
            **r.json(),
        }
    except Exception as e:
        return {
            "enabled": True,
            "ok": False,
            "error": str(e),
            "breaker": breaker_state(),
        }


# ── Backwards-compat shims (other modules may have imported these) ───
def _should_skip_remote() -> bool:
    """Legacy alias for callers from the old basic-cooldown era."""
    return not _should_attempt()


def _mark_remote_failed() -> None:
    _on_failure("manual mark_remote_failed")


def _mark_remote_healthy() -> None:
    _on_success()
