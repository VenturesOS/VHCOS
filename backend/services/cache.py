"""
Redis Caching Service using Upstash
Provides caching for search results, job parsing, and match scores.
"""
import os
import json
import hashlib
import logging
from typing import Optional, Any, List
from datetime import datetime
from functools import wraps

logger = logging.getLogger(__name__)

# Initialize Upstash Redis client
_redis_client = None

def get_redis_client():
    """Get or create Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        try:
            from upstash_redis import Redis
            url = os.environ.get("UPSTASH_REDIS_REST_URL")
            token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
            
            if url and token:
                _redis_client = Redis(url=url, token=token)
                # Test connection
                _redis_client.ping()
                logger.info("✅ Redis cache connected successfully")
            else:
                logger.warning("⚠️ Redis credentials not configured, caching disabled")
                _redis_client = None
        except Exception as e:
            logger.warning(f"⚠️ Redis connection failed: {e}, caching disabled")
            _redis_client = None
    return _redis_client


def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate a consistent cache key from arguments."""
    key_data = f"{prefix}:{json.dumps(args, sort_keys=True)}:{json.dumps(kwargs, sort_keys=True)}"
    hash_key = hashlib.md5(key_data.encode()).hexdigest()[:16]
    return f"{prefix}:{hash_key}"


class CacheService:
    """High-level caching service with typed methods."""
    
    # Cache TTL settings (in seconds)
    TTL_SEARCH_RESULTS = 300  # 5 minutes - search results change frequently
    TTL_JOB_PARSING = 3600    # 1 hour - job descriptions rarely change
    TTL_MATCH_SCORES = 1800   # 30 minutes - match scores for job-candidate pairs
    TTL_CANDIDATE_EMBEDDINGS = 86400  # 24 hours - embeddings are stable
    TTL_STATS = 60            # 1 minute - dashboard stats
    
    def __init__(self):
        self.redis = get_redis_client()
        self.enabled = self.redis is not None
    
    def _serialize(self, data: Any) -> str:
        """Serialize data for storage."""
        if isinstance(data, (dict, list)):
            return json.dumps(data, default=str)
        return str(data)
    
    def _deserialize(self, data: str) -> Any:
        """Deserialize data from storage."""
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return data
    
    # ============== Basic Operations ==============
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
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
        """Set value in cache with TTL."""
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
        """Delete key from cache."""
        if not self.enabled:
            return False
        try:
            self.redis.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache delete error: {e}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        if not self.enabled:
            return 0
        try:
            # Upstash doesn't support SCAN, so we use KEYS (use cautiously in production)
            keys = self.redis.keys(pattern)
            if keys:
                for key in keys:
                    self.redis.delete(key)
                logger.info(f"Deleted {len(keys)} cache keys matching: {pattern}")
                return len(keys)
            return 0
        except Exception as e:
            logger.warning(f"Cache delete pattern error: {e}")
            return 0
    
    # ============== Search Results Caching ==============
    
    def get_search_results(self, search_query: str, filters: dict, page: int, limit: int) -> Optional[dict]:
        """Get cached search results."""
        key = generate_cache_key("search", search_query, page=page, limit=limit, **filters)
        return self.get(key)
    
    def set_search_results(self, search_query: str, filters: dict, page: int, limit: int, results: dict) -> bool:
        """Cache search results."""
        key = generate_cache_key("search", search_query, page=page, limit=limit, **filters)
        return self.set(key, results, self.TTL_SEARCH_RESULTS)
    
    def invalidate_search_cache(self) -> int:
        """Invalidate all search caches (call when candidates are added/modified)."""
        return self.delete_pattern("search:*")
    
    # ============== Job Parsing Cache ==============
    
    def get_parsed_job(self, job_id: str) -> Optional[dict]:
        """Get cached parsed job description."""
        key = f"job_parsed:{job_id}"
        return self.get(key)
    
    def set_parsed_job(self, job_id: str, parsed_data: dict) -> bool:
        """Cache parsed job description."""
        key = f"job_parsed:{job_id}"
        return self.set(key, parsed_data, self.TTL_JOB_PARSING)
    
    def invalidate_job_cache(self, job_id: str) -> bool:
        """Invalidate cache for specific job."""
        return self.delete(f"job_parsed:{job_id}")
    
    # ============== Match Scores Cache ==============
    
    def get_match_scores(self, job_id: str, quick_match: bool = True) -> Optional[List[dict]]:
        """Get cached match scores for a job."""
        key = f"match:{job_id}:{'quick' if quick_match else 'ai'}"
        return self.get(key)
    
    def set_match_scores(self, job_id: str, scores: List[dict], quick_match: bool = True) -> bool:
        """Cache match scores for a job."""
        key = f"match:{job_id}:{'quick' if quick_match else 'ai'}"
        return self.set(key, scores, self.TTL_MATCH_SCORES)
    
    def invalidate_match_cache(self, job_id: str = None) -> int:
        """Invalidate match caches (all or specific job)."""
        if job_id:
            self.delete(f"match:{job_id}:quick")
            self.delete(f"match:{job_id}:ai")
            return 2
        return self.delete_pattern("match:*")
    
    # ============== Candidate Embeddings Cache ==============
    
    def get_candidate_embedding(self, candidate_id: str) -> Optional[List[float]]:
        """Get cached candidate embedding vector."""
        key = f"emb:{candidate_id}"
        return self.get(key)
    
    def set_candidate_embedding(self, candidate_id: str, embedding: List[float]) -> bool:
        """Cache candidate embedding vector."""
        key = f"emb:{candidate_id}"
        return self.set(key, embedding, self.TTL_CANDIDATE_EMBEDDINGS)
    
    # ============== Stats Cache ==============
    
    def get_dashboard_stats(self, user_id: str, role: str) -> Optional[dict]:
        """Get cached dashboard stats."""
        key = f"stats:{role}:{user_id}"
        return self.get(key)
    
    def set_dashboard_stats(self, user_id: str, role: str, stats: dict) -> bool:
        """Cache dashboard stats."""
        key = f"stats:{role}:{user_id}"
        return self.set(key, stats, self.TTL_STATS)


# Global cache instance
cache = CacheService()


# ============== Decorator for automatic caching ==============

def cached(prefix: str, ttl: int = 300, key_args: List[str] = None):
    """
    Decorator to cache function results.
    
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
            
            # Generate cache key from specified arguments
            if key_args:
                key_data = {k: kwargs.get(k) for k in key_args if k in kwargs}
            else:
                key_data = kwargs
            
            cache_key = generate_cache_key(prefix, **key_data)
            
            # Try to get from cache
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result
        
        return wrapper
    return decorator
