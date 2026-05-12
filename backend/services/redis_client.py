"""
VHC Talent OS — Centralized Redis Client (M-08 + Local Redis support, Feb 2026)

Single Redis singleton shared by rate_limiter, cache service, etc.

Backend selection priority (first match wins):
1. REDIS_URL  -> local / self-hosted Redis via redis-py
                 (e.g. redis://localhost:6379, rediss://host:6380/0)
2. UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN -> Upstash REST (legacy)
3. None      -> caching disabled, callers fall back to in-memory paths.

Both clients expose the subset of commands the app uses
(get/setex/delete/scan/zadd/zcard/zremrangebyscore/expire/ping) with the
same call signatures, so downstream code is unchanged.
"""
import os
import logging

logger = logging.getLogger(__name__)

_redis_client = None
_checked = False
_backend = None  # "local" | "upstash" | None


def _init_local(url: str):
    """Connect to a self-hosted Redis via redis-py. decode_responses=True
    keeps return types as str to match upstash-redis behaviour."""
    import redis as redis_py  # noqa: WPS433  (lazy import — keeps startup cheap)

    client = redis_py.Redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=3,
        health_check_interval=30,
    )
    client.ping()
    return client


def _init_upstash(url: str, token: str):
    from upstash_redis import Redis  # noqa: WPS433
    client = Redis(url=url, token=token)
    client.ping()
    return client


def get_redis():
    """Get or create the shared Redis singleton. Returns None if unavailable."""
    global _redis_client, _checked, _backend
    if _checked:
        return _redis_client

    _checked = True

    local_url = (os.environ.get("REDIS_URL") or "").strip()
    upstash_url = (os.environ.get("UPSTASH_REDIS_REST_URL") or "").strip()
    upstash_token = (os.environ.get("UPSTASH_REDIS_REST_TOKEN") or "").strip()

    if local_url:
        try:
            _redis_client = _init_local(local_url)
            _backend = "local"
            logger.info(f"[Redis] Local backend connected ({local_url.split('@')[-1]})")
            return _redis_client
        except Exception as e:
            logger.warning(f"[Redis] Local backend init failed: {e}")

    if upstash_url and upstash_token:
        try:
            _redis_client = _init_upstash(upstash_url, upstash_token)
            _backend = "upstash"
            logger.info("[Redis] Upstash backend connected")
            return _redis_client
        except Exception as e:
            logger.warning(f"[Redis] Upstash init failed: {e}")

    logger.warning("[Redis] No backend configured — caching disabled")
    return None


def get_backend() -> str:
    """Returns the active backend name for diagnostics: 'local' | 'upstash' | 'none'."""
    if not _checked:
        get_redis()
    return _backend or "none"
