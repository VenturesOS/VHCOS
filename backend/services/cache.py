"""
Redis Caching Service using Upstash
Provides caching for search results, job parsing, and match scores.

No functional changes from original — included in the release package
so the fixed services (embeddings, chunked_upload) can import it
without version confusion.
"""
import os
import json
import hashlib
import logging
from typing import Optional, Any, List
from datetime import datetime
from functools import wraps

logger = logging.getLogger(__name__)

_redis_client = None


def get_redis_client():
    """Get Redis client from centralized service (M-08)."""
    global _redis_client
    if _redis_client is None:
        from services.redis_client import get_redis
        _redis_client = get_redis()
    return _redis_client


def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate a consistent cache key from arguments using SHA-256."""
    key_data  = f"{prefix}:{json.dumps(args, sort_keys=True)}:{json.dumps(kwargs, sort_keys=True)}"
    hash_key  = hashlib.sha256(key_data.encode()).hexdigest()[:16]
    return f"{prefix}:{hash_key}"


class CacheService:
    """High-level caching service with typed methods."""

    TTL_SEARCH_RESULTS      = 600    # 10 minutes
    TTL_JOB_PARSING         = 3600   # 1 hour
    TTL_MATCH_SCORES        = 1800   # 30 minutes
    TTL_CANDIDATE_EMBEDDINGS = 86400  # 24 hours
    TTL_STATS               = 120    # 2 minutes
    TTL_JOB_BROWSE          = 600    # 10 minutes
    TTL_CAREER_PAGE         = 600    # 10 minutes

    def __init__(self):
        self.redis   = get_redis_client()
        self.enabled = self.redis is not None

    def _serialize(self, data: Any) -> str:
        if isinstance(data, (dict, list)):
            return json.dumps(data, default=str)
        return str(data)

    def _deserialize(self, data: str) -> Any:
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return data

    # ── Basic Operations ──────────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        if not self.enabled:
            return None
        try:
            data = self.redis.get(key)
            if data:
                logger.debug(f"Cache HIT: {key}")
                return self._deserialize(data)
            logger.debug(f"Cache MISS: {key}")
            return None
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        if not self.enabled:
            return False
        try:
            self.redis.setex(key, ttl, self._serialize(value))
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
            return False

    def delete(self, key: str) -> bool:
        if not self.enabled:
            return False
        try:
            self.redis.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache delete error: {e}")
            return False

    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern using cursor-based SCAN (H-04)."""
        if not self.enabled:
            return 0
        try:
            deleted = 0
            cursor = 0
            while True:
                cursor, keys = self.redis.scan(cursor, match=pattern, count=100)
                for key in keys:
                    self.redis.delete(key)
                    deleted += 1
                if cursor == 0:
                    break
            if deleted:
                logger.info(f"Deleted {deleted} cache keys matching: {pattern}")
            return deleted
        except Exception as e:
            logger.warning(f"Cache delete pattern error: {e}")
            return 0

    # ── Search Results ────────────────────────────────────────────────────

    def get_search_results(self, search_query: str, filters: dict, page: int, limit: int) -> Optional[dict]:
        key = generate_cache_key("search", search_query, page=page, limit=limit, **filters)
        return self.get(key)

    def set_search_results(self, search_query: str, filters: dict, page: int, limit: int, results: dict) -> bool:
        key = generate_cache_key("search", search_query, page=page, limit=limit, **filters)
        return self.set(key, results, self.TTL_SEARCH_RESULTS)

    def invalidate_search_cache(self) -> int:
        return self.delete_pattern("search:*")

    # ── Job Parsing Cache ─────────────────────────────────────────────────

    def get_parsed_job(self, job_id: str) -> Optional[dict]:
        return self.get(f"job_parsed:{job_id}")

    def set_parsed_job(self, job_id: str, parsed_data: dict) -> bool:
        return self.set(f"job_parsed:{job_id}", parsed_data, self.TTL_JOB_PARSING)

    def invalidate_job_cache(self, job_id: str) -> bool:
        return self.delete(f"job_parsed:{job_id}")

    # ── Match Scores Cache ────────────────────────────────────────────────

    def get_match_scores(self, job_id: str, quick_match: bool = True) -> Optional[List[dict]]:
        key = f"match:{job_id}:{'quick' if quick_match else 'ai'}"
        return self.get(key)

    def set_match_scores(self, job_id: str, scores: List[dict], quick_match: bool = True) -> bool:
        key = f"match:{job_id}:{'quick' if quick_match else 'ai'}"
        return self.set(key, scores, self.TTL_MATCH_SCORES)

    def invalidate_match_cache(self, job_id: str = None) -> int:
        if job_id:
            self.delete(f"match:{job_id}:quick")
            self.delete(f"match:{job_id}:ai")
            return 2
        return self.delete_pattern("match:*")

    # ── Candidate Embeddings Cache ────────────────────────────────────────

    def get_candidate_embedding(self, candidate_id: str) -> Optional[List[float]]:
        return self.get(f"emb_cand:{candidate_id}")

    def set_candidate_embedding(self, candidate_id: str, embedding: List[float]) -> bool:
        return self.set(f"emb_cand:{candidate_id}", embedding, self.TTL_CANDIDATE_EMBEDDINGS)

    # ── Stats Cache ───────────────────────────────────────────────────────

    def get_dashboard_stats(self, user_id: str, role: str) -> Optional[dict]:
        return self.get(f"stats:{role}:{user_id}")

    def set_dashboard_stats(self, user_id: str, role: str, stats: dict) -> bool:
        return self.set(f"stats:{role}:{user_id}", stats, self.TTL_STATS)


# Global cache instance
cache = CacheService()


# ── Decorator for automatic caching ──────────────────────────────────────

def cached(prefix: str, ttl: int = 300, key_args: List[str] = None):
    """
    Decorator to cache async function results.

    Usage:
        @cached("search", ttl=300, key_args=["search_query", "page"])
        async def search_candidates(search_query: str, page: int):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not cache.enabled:
                return await func(*args, **kwargs)

            if key_args:
                key_data = {k: kwargs.get(k) for k in key_args if k in kwargs}
            else:
                key_data = kwargs

            cache_key     = generate_cache_key(prefix, **key_data)
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result

            result = await func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result

        return wrapper
    return decorator
