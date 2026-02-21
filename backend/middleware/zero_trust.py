"""
VHC Talent OS — Cloudflare Zero Trust Access Middleware
Validates Cf-Access-Jwt-Assertion header on admin routes.
When CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD are configured, admin routes
require a valid Cloudflare Access JWT. Otherwise, it's bypassed gracefully.
"""
import os
import logging
import jwt
import httpx
from functools import lru_cache
from fastapi import Request, HTTPException, Depends

logger = logging.getLogger(__name__)

CF_TEAM_DOMAIN = os.environ.get("CF_ACCESS_TEAM_DOMAIN", "")
CF_AUD = os.environ.get("CF_ACCESS_AUD", "")
ZERO_TRUST_ENABLED = bool(CF_TEAM_DOMAIN and CF_AUD)

_certs_cache = {"keys": None}


async def _fetch_cf_certs():
    """Fetch Cloudflare Access public keys for JWT verification."""
    if _certs_cache["keys"]:
        return _certs_cache["keys"]
    try:
        url = f"https://{CF_TEAM_DOMAIN}.cloudflareaccess.com/cdn-cgi/access/certs"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=5)
            data = resp.json()
            _certs_cache["keys"] = data.get("public_certs", [])
            return _certs_cache["keys"]
    except Exception as e:
        logger.error(f"[ZERO_TRUST] Failed to fetch CF certs: {e}")
        return []


async def verify_cf_access_token(token: str) -> dict:
    """Verify a Cloudflare Access JWT and return its claims."""
    certs = await _fetch_cf_certs()
    if not certs:
        return {}

    for cert in certs:
        try:
            decoded = jwt.decode(
                token,
                key=cert["cert"],
                audience=CF_AUD,
                algorithms=["RS256"],
            )
            return decoded
        except jwt.InvalidTokenError:
            continue
    return {}


async def require_zero_trust(request: Request):
    """
    FastAPI dependency that enforces Cloudflare Zero Trust on admin routes.
    When not configured, passes through silently.
    """
    if not ZERO_TRUST_ENABLED:
        return None

    cf_token = request.headers.get("Cf-Access-Jwt-Assertion", "")
    if not cf_token:
        # Log the attempt
        from services.security_service import log_security_event
        ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
        if "," in ip:
            ip = ip.split(",")[0].strip()
        await log_security_event(
            "zero_trust_missing_token", ip, "HIGH",
            f"Admin access attempt without CF Access token: {request.url.path}",
            {"path": request.url.path}
        )
        raise HTTPException(status_code=403, detail="Access denied. Cloudflare Access required.")

    claims = await verify_cf_access_token(cf_token)
    if not claims:
        from services.security_service import log_security_event
        ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
        if "," in ip:
            ip = ip.split(",")[0].strip()
        await log_security_event(
            "zero_trust_invalid_token", ip, "CRITICAL",
            f"Invalid CF Access token on: {request.url.path}",
            {"path": request.url.path}
        )
        raise HTTPException(status_code=403, detail="Invalid Cloudflare Access token.")

    return claims
