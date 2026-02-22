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
    - Emergent preview pods have 'preview_endpoint' in env.
    - Production (ventureshrd.com) has neither of these signals.
    """
    # Explicit override always wins
    explicit = os.environ.get("APP_ENV", "").lower()
    if explicit in ("production", "preview", "local", "staging"):
        return explicit

    # Emergent preview pod detection
    if os.environ.get("preview_endpoint") or "emergent" in os.environ.get("HOSTNAME", "").lower():
        return "preview"

    # Localhost detection
    cors = _cors_origins.lower()
    if "localhost" in cors or "127.0.0.1" in cors:
        return "local"

    # If production domains are the only CORS origins, it's production
    if any(d in cors for d in PRODUCTION_DOMAINS):
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
