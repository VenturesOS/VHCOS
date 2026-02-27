"""
VHC Talent OS — Centralized Environment Resolver
Single source of truth for environment detection across the entire application.
All modules MUST use this instead of checking env variables directly.
"""
import os
import logging

logger = logging.getLogger(__name__)

# ── Resolve once at import time ──

_frontend_url = os.environ.get("REACT_APP_BACKEND_URL", "") or os.environ.get("FRONTEND_URL", "")
_cors_origins = os.environ.get("CORS_ORIGINS", "")
_mongo_url = os.environ.get("MONGO_URL", "")
_db_name = os.environ.get("DB_NAME", "vhc_talent_os")

PRODUCTION_DOMAINS = ("ventureshrd.com", "www.ventureshrd.com")


def _detect_environment() -> str:
    """Detect environment reliably.
    Priority: explicit APP_ENV > production DB cluster > preview pod > domain heuristics.
    The MongoDB cluster is the authoritative source of truth for data identity:
    if connected to the production Atlas cluster, data IS production regardless
    of where the code is running (preview pod, local, etc.).
    """
    explicit = os.environ.get("APP_ENV", "").lower()
    if explicit in ("production", "preview", "local", "staging"):
        return explicit

    # Check if connected to production Atlas cluster — authoritative for data identity.
    # This MUST run before the preview-pod check: a preview pod connected to production
    # data should report "production" so the warning banner does not appear.
    try:
        mongo_uri = os.environ.get("MONGODB_URI") or os.environ.get("MONGODB_URL") or os.environ.get("MONGO_URL") or ""
        # Also check the Python override file (survives platform .env overwrites).
        # config.py uses this same file to connect, so env detection must match.
        if "cluster0.vuhdiod.mongodb.net" not in mongo_uri:
            try:
                from mongo_production_override import MONGO_URL as _ov_url
                if _ov_url and "cluster0.vuhdiod.mongodb.net" in _ov_url:
                    mongo_uri = _ov_url
            except ImportError:
                pass
        if "cluster0.vuhdiod.mongodb.net" in mongo_uri:
            return "production"
    except Exception:
        pass

    # Emergent preview pod with non-production DB
    app_url = os.environ.get("APP_URL", "").lower()
    if "preview" in app_url or "emergent" in app_url:
        return "preview"

    cors = _cors_origins.lower()
    frontend = _frontend_url.lower()
    if "localhost" in cors or "127.0.0.1" in cors:
        return "local"

    if any(d in cors for d in PRODUCTION_DOMAINS) or any(d in frontend for d in PRODUCTION_DOMAINS):
        return "production"

    return "unknown"


ENV_NAME: str = _detect_environment()
IS_PRODUCTION: bool = ENV_NAME == "production"
IS_PREVIEW: bool = ENV_NAME == "preview"
IS_LOCAL: bool = ENV_NAME == "local"
DB_NAME: str = _db_name
MONGO_HOST: str = _mongo_url.split("@")[-1].split("/")[0].split("?")[0] if "@" in _mongo_url else "unknown"


def get_environment_info() -> dict:
    """Return a dict summarising the current environment — safe for logging (no secrets)."""
    return {
        "environment": ENV_NAME,
        "is_production": IS_PRODUCTION,
        "database": DB_NAME,
        "mongo_cluster": MONGO_HOST,
    }


def log_environment_banner():
    """Log a clear environment banner once at startup."""
    info = get_environment_info()
    banner = (
        f"\n{'='*60}\n"
        f"  VHC TALENT OS — ENVIRONMENT REPORT\n"
        f"  ENV          = {info['environment']}\n"
        f"  DB           = {info['database']}\n"
        f"  MONGO_CLUSTER= {info['mongo_cluster']}\n"
        f"  IS_PRODUCTION= {info['is_production']}\n"
        f"{'='*60}"
    )
    logging.warning(banner)


def normalize_email(email: str) -> str:
    """Canonical email normalisation — lowercase + strip whitespace."""
    if not email:
        return ""
    return email.strip().lower()
