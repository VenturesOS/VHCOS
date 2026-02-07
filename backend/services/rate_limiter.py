"""
Rate Limiting Middleware for VHC Talent OS
Implements token bucket rate limiting using Redis.
"""
import os
import time
import logging
from typing import Optional, Dict
from fastapi import Request, HTTPException
from functools import wraps

logger = logging.getLogger(__name__)

# Rate limit configuration
RATE_LIMITS = {
    "auth": {"requests": 30, "window": 60},       # 30 requests per minute for auth
    "search": {"requests": 100, "window": 60},    # 100 requests per minute for search
    "ai_match": {"requests": 60, "window": 60},   # 60 requests per minute for AI matching
    "api": {"requests": 300, "window": 60},       # 300 requests per minute general API
    "upload": {"requests": 10, "window": 60},     # 10 uploads per minute
}


class RateLimiter:
    """Token bucket rate limiter using Redis."""
    
    def __init__(self):
        self._redis = None
        self._enabled = False
        self._local_cache: Dict[str, tuple] = {}  # Fallback for when Redis unavailable
    
    def _get_redis(self):
        """Lazy load Redis client."""
        if self._redis is None:
            try:
                from upstash_redis import Redis
                url = os.environ.get("UPSTASH_REDIS_REST_URL")
                token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
                if url and token:
                    self._redis = Redis(url=url, token=token)
                    self._enabled = True
            except Exception as e:
                logger.warning(f"Rate limiter Redis unavailable: {e}")
                self._enabled = False
        return self._redis
    
    def _get_client_id(self, request: Request) -> str:
        """Get unique client identifier from request."""
        # Try to get user ID from auth header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            # Use token hash as client ID for authenticated users
            import hashlib
            token_hash = hashlib.md5(auth_header.encode()).hexdigest()[:12]
            return f"user:{token_hash}"
        
        # Fall back to IP address
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"
        return f"ip:{request.client.host if request.client else 'unknown'}"
    
    def check_rate_limit(self, request: Request, limit_type: str = "api") -> bool:
        """
        Check if request is within rate limit.
        Returns True if allowed, raises HTTPException if rate limited.
        """
        config = RATE_LIMITS.get(limit_type, RATE_LIMITS["api"])
        max_requests = config["requests"]
        window_seconds = config["window"]
        
        client_id = self._get_client_id(request)
        key = f"ratelimit:{limit_type}:{client_id}"
        
        redis = self._get_redis()
        
        if redis and self._enabled:
            try:
                # Use Redis for distributed rate limiting
                current_time = int(time.time())
                window_start = current_time - window_seconds
                
                # Use sorted set for sliding window
                pipe_key = f"{key}:requests"
                
                # Remove old entries
                redis.zremrangebyscore(pipe_key, 0, window_start)
                
                # Count current requests
                current_count = redis.zcard(pipe_key)
                
                if current_count >= max_requests:
                    # Get TTL for retry-after header
                    oldest = redis.zrange(pipe_key, 0, 0, withscores=True)
                    retry_after = window_seconds
                    if oldest:
                        retry_after = int(oldest[0][1]) + window_seconds - current_time
                    
                    logger.warning(f"Rate limit exceeded for {client_id} on {limit_type}")
                    raise HTTPException(
                        status_code=429,
                        detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                        headers={"Retry-After": str(retry_after)}
                    )
                
                # Add current request
                redis.zadd(pipe_key, {str(current_time): current_time})
                redis.expire(pipe_key, window_seconds + 10)
                
                return True
                
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"Rate limit check failed: {e}, allowing request")
                return True
        else:
            # Fallback to local in-memory rate limiting
            return self._check_local_rate_limit(key, max_requests, window_seconds)
    
    def _check_local_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Local fallback rate limiting when Redis unavailable."""
        current_time = time.time()
        
        if key in self._local_cache:
            requests, window_start = self._local_cache[key]
            
            # Reset window if expired
            if current_time - window_start > window_seconds:
                self._local_cache[key] = (1, current_time)
                return True
            
            # Check if over limit
            if requests >= max_requests:
                retry_after = int(window_start + window_seconds - current_time)
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)}
                )
            
            # Increment
            self._local_cache[key] = (requests + 1, window_start)
        else:
            self._local_cache[key] = (1, current_time)
        
        # Cleanup old entries periodically
        if len(self._local_cache) > 10000:
            cutoff = current_time - 120
            self._local_cache = {
                k: v for k, v in self._local_cache.items() 
                if v[1] > cutoff
            }
        
        return True
    
    def get_remaining(self, request: Request, limit_type: str = "api") -> Dict:
        """Get remaining rate limit info for response headers."""
        config = RATE_LIMITS.get(limit_type, RATE_LIMITS["api"])
        client_id = self._get_client_id(request)
        key = f"ratelimit:{limit_type}:{client_id}:requests"
        
        redis = self._get_redis()
        if redis and self._enabled:
            try:
                current_count = redis.zcard(key) or 0
                remaining = max(0, config["requests"] - current_count)
                return {
                    "X-RateLimit-Limit": str(config["requests"]),
                    "X-RateLimit-Remaining": str(remaining),
                    "X-RateLimit-Reset": str(config["window"])
                }
            except Exception:
                pass
        
        return {
            "X-RateLimit-Limit": str(config["requests"]),
            "X-RateLimit-Remaining": "unknown",
            "X-RateLimit-Reset": str(config["window"])
        }


# Global rate limiter instance
rate_limiter = RateLimiter()


def rate_limit(limit_type: str = "api"):
    """Decorator for rate limiting endpoints."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Find request in args/kwargs
            request = kwargs.get("request")
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            
            if request:
                rate_limiter.check_rate_limit(request, limit_type)
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator
