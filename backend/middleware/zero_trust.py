"""
VHC Talent OS — Cloudflare Zero Trust Access Middleware
Validates Cf-Access-Jwt-Assertion header on ALL /api/admin/* routes.

Supports two modes:
  - ENFORCE (CF_ACCESS_ENFORCE=true): Blocks requests without valid CF token (production)
  - AUDIT (CF_ACCESS_ENFORCE=false): Logs events but allows through (rollout/preview)

When CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD are configured, Zero Trust is ACTIVE.
"""
import os
import logging
import jwt
import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from fastapi import Request

logger = logging.getLogger(__name__)

_raw_domain = os.environ.get("CF_ACCESS_TEAM_DOMAIN", "")
# Handle both formats: "vhc-admin" or "vhc-admin.cloudflareaccess.com"
CF_TEAM_DOMAIN = _raw_domain.replace(".cloudflareaccess.com", "").strip()
CF_AUD = os.environ.get("CF_ACCESS_AUD", "").strip()
CF_ENFORCE = os.environ.get("CF_ACCESS_ENFORCE", "true").lower() == "true"
ZERO_TRUST_ENABLED = bool(CF_TEAM_DOMAIN and CF_AUD)

# Protected path prefixes
PROTECTED_PATHS = ["/api/admin/", "/api/admin"]

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


def _is_admin_path(path: str) -> bool:
    """Check if the request path is a protected admin route."""
    return any(path.startswith(p) for p in PROTECTED_PATHS)


class ZeroTrustMiddleware(BaseHTTPMiddleware):
    """HTTP middleware that enforces Cloudflare Zero Trust on all /api/admin/* routes."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip if not configured or not an admin path
        if not ZERO_TRUST_ENABLED or not _is_admin_path(path):
            try:
                return await call_next(request)
            except RuntimeError:
                return JSONResponse(status_code=500, content={"detail": "Internal server error"})

        from services.security_service import log_security_event

        cf_token = request.headers.get("Cf-Access-Jwt-Assertion", "")

        if not cf_token:
            ip = _get_client_ip(request)
            await log_security_event(
                "zero_trust_missing_token", ip, "HIGH",
                f"Admin access without CF Access token: {path}",
                {"path": path, "enforce": CF_ENFORCE}
            )
            if CF_ENFORCE:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Access denied. Cloudflare Access required."}
                )
            try:
                return await call_next(request)
            except RuntimeError:
                return JSONResponse(status_code=500, content={"detail": "Internal server error"})

        # Token present — validate it
        claims = await verify_cf_access_token(cf_token)
        if not claims:
            ip = _get_client_ip(request)
            await log_security_event(
                "zero_trust_invalid_token", ip, "CRITICAL",
                f"Invalid CF Access token on: {path}",
                {"path": path, "enforce": CF_ENFORCE}
            )
            if CF_ENFORCE:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Invalid Cloudflare Access token."}
                )
            try:
                return await call_next(request)
            except RuntimeError:
                return JSONResponse(status_code=500, content={"detail": "Internal server error"})

        # Valid token — log access
        await log_security_event(
            "zero_trust_access_granted", _get_client_ip(request), "INFO",
            f"CF Access verified for {path}",
            {"path": path, "email": claims.get("email", "unknown")}
        )
        try:
            return await call_next(request)
        except RuntimeError:
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Legacy dependency (no-op since middleware handles enforcement)
async def require_zero_trust(request: Request):
    return None
