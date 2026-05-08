"""
VHC Talent OS — Centralized Redis Client (M-08)
Single Upstash Redis connection shared by rate_limiter and cache service.
"""
import os
import logging

logger = logging.getLogger(__name__)

_redis_client = None
_checked = False


def get_redis():
    """Get or create the shared Redis singleton. Returns None if unavailable."""
    global _redis_client, _checked
    if not _checked:
        _checked = True
        try:
            from upstash_redis import Redis
            url = os.environ.get("UPSTASH_REDIS_REST_URL")
            token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
            if url and token:
                _redis_client = Redis(url=url, token=token)
                _redis_client.ping()
                logger.info("[Redis] Upstash connected (shared client)")
            else:
                logger.warning("[Redis] Credentials not configured — Redis disabled")
        except Exception as e:
            logger.warning(f"[Redis] Connection failed: {e} — Redis disabled")
            _redis_client = None
    return _redis_client
