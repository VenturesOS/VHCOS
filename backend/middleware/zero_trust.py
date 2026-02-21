"""
VHC Talent OS — Cloudflare Zero Trust Access Middleware
Validates Cf-Access-Jwt-Assertion header on admin routes.

Supports two modes:
  - ENFORCE (CF_ACCESS_ENFORCE=true): Blocks requests without valid CF token (production)
  - AUDIT (default): Logs events but allows through with JWT auth fallback (rollout/preview)

When CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD are configured, Zero Trust is ACTIVE.
"""
import os
import logging
import jwt
import httpx
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)

_raw_domain = os.environ.get("CF_ACCESS_TEAM_DOMAIN", "")
# Handle both formats: "vhc-admin" or "vhc-admin.cloudflareaccess.com"
CF_TEAM_DOMAIN = _raw_domain.replace(".cloudflareaccess.com", "").strip()
CF_AUD = os.environ.get("CF_ACCESS_AUD", "").strip()
CF_ENFORCE = os.environ.get("CF_ACCESS_ENFORCE", "true").lower() == "true"
ZERO_TRUST_ENABLED = bool(CF_TEAM_DOMAIN and CF_AUD)

_certs_cache = {"keys": None}

if ZERO_TRUST_ENABLED:
    logger.warning(f"[ZERO_TRUST] ACTIVE | Team: {CF_TEAM_DOMAIN} | Enforce: {CF_ENFORCE}")
else:
    logger.info("[ZERO_TRUST] Not configured — admin routes use JWT auth only")


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


def _get_client_ip(request: Request) -> str:
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    if "," in ip:
        ip = ip.split(",")[0].strip()
    return ip


async def require_zero_trust(request: Request):
    """
    FastAPI dependency that enforces Cloudflare Zero Trust on admin routes.

    - Not configured → pass through
    - Configured + ENFORCE mode → block without valid CF token
    - Configured + AUDIT mode → log event but allow (JWT auth still required)
    """
    if not ZERO_TRUST_ENABLED:
        return None

    from services.security_service import log_security_event

    cf_token = request.headers.get("Cf-Access-Jwt-Assertion", "")

    if not cf_token:
        ip = _get_client_ip(request)
        await log_security_event(
            "zero_trust_missing_token", ip, "HIGH",
            f"Admin access without CF Access token: {request.url.path}",
            {"path": request.url.path, "enforce": CF_ENFORCE}
        )
        if CF_ENFORCE:
            raise HTTPException(status_code=403, detail="Access denied. Cloudflare Access required.")
        # Audit mode: logged but not blocked (JWT auth still required downstream)
        return None

    # Token present — validate it
    claims = await verify_cf_access_token(cf_token)
    if not claims:
        ip = _get_client_ip(request)
        await log_security_event(
            "zero_trust_invalid_token", ip, "CRITICAL",
            f"Invalid CF Access token on: {request.url.path}",
            {"path": request.url.path, "enforce": CF_ENFORCE}
        )
        if CF_ENFORCE:
            raise HTTPException(status_code=403, detail="Invalid Cloudflare Access token.")
        return None

    # Valid token — log successful access
    await log_security_event(
        "zero_trust_access_granted",
        _get_client_ip(request),
        "INFO",
        f"CF Access verified for {request.url.path}",
        {"path": request.url.path, "email": claims.get("email", "unknown")}
    )
    return claims
