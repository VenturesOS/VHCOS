"""
VHC Talent OS - Authentication Utilities
JWT token handling, password hashing, and role-based access control.

M-03: Refresh token rotation — access tokens are short-lived (30 min),
refresh tokens are long-lived (7 days) and single-use (rotated on each refresh).
"""
import secrets
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import bcrypt

from config import JWT_SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, db

security = HTTPBearer()

REFRESH_TOKEN_EXPIRE_DAYS = 7

# ── In-process user cache (per-worker, 30s TTL) ─────────────────────────
# Every authenticated request hits db.users.find_one(). At ~5k auth-checks
# per hour that's a serious hot path — Mongo Atlas latency + document load
# for what is effectively immutable data. A 30s in-memory cache turns 5k
# lookups/hr into ~200 (one per unique user per 30s) with zero external
# deps. Cache is invalidated on logout by bumping token_version.
_USER_CACHE_TTL_SECONDS = 30
_user_cache: dict[str, Tuple[dict, float]] = {}


def _cache_get_user(user_id: str) -> Optional[dict]:
    """Return the cached user dict if present and fresh, else None."""
    entry = _user_cache.get(user_id)
    if not entry:
        return None
    user, ts = entry
    if time.time() - ts > _USER_CACHE_TTL_SECONDS:
        _user_cache.pop(user_id, None)
        return None
    return user


def _cache_put_user(user: dict) -> None:
    """Store a fresh user snapshot in the cache."""
    uid = user.get("id")
    if uid:
        _user_cache[uid] = (user, time.time())


def invalidate_user_cache(user_id: str) -> None:
    """Drop a user from the cache — call this on logout / role change / deactivation."""
    _user_cache.pop(user_id, None)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def create_access_token(data: dict) -> str:
    """Create a JWT access token with expiration and token_version."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token() -> str:
    """Create a cryptographically random refresh token (opaque, not JWT)."""
    return secrets.token_urlsafe(48)


async def store_refresh_token(user_id: str, refresh_token: str, token_version: int = 0):
    """Store a hashed refresh token in the database (single-use rotation)."""
    import hashlib
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    await db.refresh_tokens.insert_one({
        "user_id": user_id,
        "token_hash": token_hash,
        "token_version": token_version,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def validate_refresh_token(refresh_token: str) -> dict:
    """
    Validate a refresh token: check hash exists, not expired, then delete it (single-use).
    Returns the user dict if valid.
    """
    import hashlib
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    record = await db.refresh_tokens.find_one({"token_hash": token_hash})
    if not record:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Check expiry
    expires = datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires:
        await db.refresh_tokens.delete_one({"token_hash": token_hash})
        raise HTTPException(status_code=401, detail="Refresh token expired — please log in again")

    # Single-use: delete this token immediately (will be replaced with a new one)
    await db.refresh_tokens.delete_one({"token_hash": token_hash})

    # Fetch user and validate token_version
    user = await db.users.find_one({"id": record["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # SEC-04: block refresh attempts by deactivated/offboarded users.
    # Also purge any remaining refresh tokens so the extension can't keep retrying.
    if not user.get("is_active", True):
        await db.refresh_tokens.delete_many({"user_id": record["user_id"]})
        raise HTTPException(status_code=401, detail="Account deactivated")

    user_ver = user.get("token_version", 0)
    if record.get("token_version", 0) < user_ver:
        # Token version mismatch — all refresh tokens for this user are invalidated
        await db.refresh_tokens.delete_many({"user_id": record["user_id"]})
        raise HTTPException(status_code=401, detail="Session invalidated — please log in again")

    return user


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Extract and validate the current user from JWT token."""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        # Reject refresh tokens used as access tokens
        if payload.get("type") == "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Try the 30s in-process cache first — this dominates the hot path.
        user = _cache_get_user(user_id)
        if user is None:
            user = await db.users.find_one({"id": user_id}, {"_id": 0})
            if user is None:
                raise HTTPException(status_code=401, detail="User not found")
            _cache_put_user(user)

        # Reject deactivated users (SEC-04: block deactivated/offboarded accounts)
        if not user.get("is_active", True):
            invalidate_user_cache(user_id)
            raise HTTPException(status_code=401, detail="Account deactivated")
        # Validate token_version (CRIT-3: token revocation)
        token_ver = payload.get("tv", 0)
        user_ver = user.get("token_version", 0)
        if token_ver < user_ver:
            invalidate_user_cache(user_id)
            raise HTTPException(status_code=401, detail="Token revoked — please log in again")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Service starting up — please retry in a moment")


async def get_current_user_from_token(request, token_param=None):
    """
    Extract user from either Authorization header or ?token= query param.
    Used by download endpoints that open in a new browser tab.
    """
    raw_token = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        raw_token = auth_header[7:]
    elif token_param:
        raw_token = token_param

    if not raw_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(raw_token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = _cache_get_user(user_id)
        if user is None:
            user = await db.users.find_one({"id": user_id}, {"_id": 0})
            if user is None:
                raise HTTPException(status_code=401, detail="User not found")
            _cache_put_user(user)
        # SEC-04: block deactivated accounts on download endpoints too
        if not user.get("is_active", True):
            invalidate_user_cache(user_id)
            raise HTTPException(status_code=401, detail="Account deactivated")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_role(allowed_roles: List[str]):
    """
    Dependency factory for role-based access control.
    Usage: @api_router.get("/endpoint", dependencies=[Depends(require_role(["admin", "employer"]))])
    """
    async def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return role_checker
