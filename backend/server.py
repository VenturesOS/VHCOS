"""
VHC Talent OS — Main Application Entry Point
Handles app creation, middleware setup, route registration, and lifecycle events.
Business logic lives in services/, routes are thin controllers in routes/.
"""
from fastapi import FastAPI, HTTPException, Request
from starlette.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
import logging
import asyncio
import httpx

# Import configuration from config.py
from config import (
    ROOT_DIR,
    db,
    db_name,
    client,
    r2_client,
    R2_ENABLED,
    R2_BUCKET_NAME,
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    UPLOAD_DIR,
    PARENT_UPLOAD_DIR
)

# Import models from models/ (barrel export validates all model imports)
from models import (
    # Auth models
    UserBase, UserCreate, UserLogin, UserResponse, UserUpdate,
    AdminUserCreate, AdminPasswordReset, PasswordReset, TokenResponse,
    # Job models
    JobBase, JobCreate, JobResponse, JobUpdate, JobStateTransition,
    CareerPageStatusUpdate, JDParseRequest, JDParseResponse, MandateAssignment,
    ShareableLinkUpdate, MandateShareableLinkUpdate,
    # Candidate models
    CandidateProfile, CandidateProfileUpdate,
    # Application models
    ApplicationBase, ApplicationCreate, ApplicationResponse,
    ApplicationUpdate, ApplicationDetailUpdate, AuditLogEntry, NoteCreate,
    ApplicantReviewResponse, CandidateApprovalRequest,
    ShortlistRequest, LinkCandidateRequest,
    # Company models
    CompanyBase, CompanyCreate, CompanyResponse, CompanyUpdate,
    # Team models
    TeamCreate, TeamUpdate, TeamResponse,
    # Referral models
    ReferralCreate, ReferralResponse, ReferralStatusUpdate,
    # Message models
    MessageBase, MessageCreate, MessageResponse,
    # Candidate Bank models
    CandidateBankRecord, CandidateBankUpdate, CandidateBankAuditLogEntry,
    BatchUploadCandidate, BatchSaveRequest,
    # Matching models
    MatchRequest, MatchResult, JobMatchForCandidate,
    # Alert models
    JobAlertPreferences, JobAlertCreate, WhatsAppOptIn, NotificationLogEntry,
    # Commercial models
    CommercialCreate, CommercialUpdate, CommercialResponse,
    RevenueEntry, RevenueUpdate
)

# Import utilities from utils/
from utils import (
    # Auth utilities
    hash_password, verify_password, create_access_token,
    get_current_user, require_role, security,
    # Governance utilities
    validate_mandatory_candidate_fields, create_profile_audit_entry,
    update_candidate_freshness, add_application_to_history,
    update_application_in_history
)

# Import R2 storage services
try:
    from services import (
        upload_to_r2,
        get_r2_signed_url,
        get_file_from_r2,
        generate_r2_key
    )
except Exception as e:
    logging.warning(f"[IMPORT] Services import failed: {e}")
    async def upload_to_r2(*a, **kw): return None
    async def get_r2_signed_url(*a, **kw): return None
    async def get_file_from_r2(*a, **kw): return None
    def generate_r2_key(*a, **kw): return ""

# ============== ROUTE IMPORTS ==============
# Wrapped in safe loader so server starts even if some routes fail
_route_imports_failed = []

_ALLOWED_ROUTE_PREFIXES = ("routes.",)

def _safe_import(module_path, attr_name):
    """Import a router safely; return None on failure so the server can still start."""
    if not any(module_path.startswith(p) for p in _ALLOWED_ROUTE_PREFIXES):
        logging.error(f"[IMPORT BLOCKED] {module_path} not in allowed prefixes")
        return None
    try:
        mod = __import__(module_path, fromlist=[attr_name])
        return getattr(mod, attr_name)
    except Exception as e:
        _route_imports_failed.append(f"{module_path}.{attr_name}: {e}")
        logging.error(f"[IMPORT FAIL] {module_path}.{attr_name}: {e}")
        return None

# Core routes
try:
    from routes import auth_router, public_router, files_router, admin_router, jobs_router, candidates_router, applications_router, settings_router, background_jobs_router, teams_router, referrals_router, commercials_router, analytics_router, revenue_router, employer_router, linkedin_router
except Exception as e:
    logging.error(f"[IMPORT FAIL] Core routes: {e}")
    auth_router = public_router = files_router = admin_router = jobs_router = None
    candidates_router = applications_router = settings_router = background_jobs_router = None
    teams_router = referrals_router = commercials_router = analytics_router = None
    revenue_router = employer_router = linkedin_router = None

bulk_import_router = _safe_import("routes.bulk_import", "bulk_import_router")
bug_reports_router = _safe_import("routes.bug_reports", "bug_reports_router")

try:
    from routes.system_errors import system_errors_router, log_system_error
except Exception as e:
    logging.error(f"[IMPORT FAIL] system_errors: {e}")
    system_errors_router = None
    async def log_system_error(*a, **kw): pass

extension_router = _safe_import("routes.extension", "extension_router")
profile_router = _safe_import("routes.profile", "profile_router")
cv_upload_router = _safe_import("routes.cv_upload", "cv_upload_router")
ai_search_router = _safe_import("routes.ai_search", "ai_search_router")
sourcing_router = _safe_import("routes.sourcing_search", "sourcing_router")
contact_router = _safe_import("routes.contact", "router")
blog_router = _safe_import("routes.blog", "router")
seo_router = _safe_import("routes.seo", "router")
pillar_pages_router = _safe_import("routes.pillar_pages", "router")
blog_digest_router = _safe_import("routes.blog_digest", "router")
seo_dashboard_router = _safe_import("routes.seo_dashboard", "router")
tracker_router = _safe_import("routes.tracker", "router")
compliance_router = _safe_import("routes.compliance_routes", "compliance_router")
maintenance_router = _safe_import("routes.maintenance_routes", "maintenance_router")
attendance_router = _safe_import("routes.attendance", "router")
attendance_analytics_router = _safe_import("routes.attendance_analytics", "router")
resume_router = _safe_import("routes.resume", "resume_router")
account_manager_router = _safe_import("routes.account_manager", "account_manager_router")
finance_router = _safe_import("routes.finance", "finance_router")
notification_router = _safe_import("routes.notifications", "notification_router")
activity_router = _safe_import("routes.activity_log", "activity_router")
activity_monitor_router = _safe_import("routes.activity_monitor", "router")
extraction_report_router = _safe_import("routes.extraction_report", "router")
extraction_trace_router = _safe_import("routes.extraction_trace", "router")
admin_monitoring_router = _safe_import("routes.admin_monitoring", "router")
extension_updates_router = _safe_import("routes.extension_updates", "router")
reports_router = _safe_import("routes.reports", "router")
talent_graph_router = _safe_import("routes.talent_graph", "router")

# Health router
from routes.health import health_router, set_route_import_failures

# Import boto3 for type hints (r2_client operations)
try:
    import boto3
    from botocore.config import Config
except ImportError:
    boto3 = None
    Config = None
    logging.warning("[IMPORT] boto3 not available — R2 storage disabled")


# ============== LIFESPAN (Global HTTPX Client + DB Init) ==============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: creates shared resources at startup, cleans up on shutdown."""
    # ── Startup ──
    # 1. Global httpx.AsyncClient — reused across all LLM calls (no per-request overhead)
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10, read=90, write=30, pool=10),
        limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
    )
    logging.info("[Lifespan] Global httpx.AsyncClient created")

    # 2. Critical DB initialization (blocks until MongoDB connected)
    from services.lifecycle import run_critical_init, run_deferred_init
    await run_critical_init()

    # 3. Non-critical tasks (indexes, schedulers) run in background
    asyncio.create_task(run_deferred_init(app))

    # 4. API metrics
    from middleware.api_metrics import start_metrics_flusher, ensure_metrics_indexes
    start_metrics_flusher()
    await ensure_metrics_indexes()

    # 5. RunPod auto-sync daemon (no-op if RUNPOD_API_KEY not set)
    from services.runpod_sync_service import runpod_sync_loop
    asyncio.create_task(runpod_sync_loop())

    # 6. Talent Graph indexes — safe to run on every boot
    try:
        from services.talent_graph_service import ensure_embeddings_indexes
        from config import db as _tg_db
        await ensure_embeddings_indexes(_tg_db)
    except Exception as _e:
        logging.warning(f"[Lifespan] Talent Graph index init skipped: {_e}")

    yield  # ── App is running ──

    # ── Shutdown ──
    await app.state.http_client.aclose()
    logging.info("[Lifespan] Global httpx.AsyncClient closed")

    from services.lifecycle import shutdown_scheduler, shutdown_db
    await shutdown_scheduler()
    await shutdown_db(client)


# ============== CREATE APP ==============

app = FastAPI(title="VHC Talent OS API", lifespan=lifespan)


# ============== REGISTER ROUTERS ==============

# Pass import failures to health router
set_route_import_failures(_route_imports_failed)

_all_routers = [
    health_router,
    auth_router, public_router, files_router, admin_router, jobs_router,
    candidates_router, applications_router, settings_router, background_jobs_router,
    bulk_import_router, teams_router, referrals_router, commercials_router,
    bug_reports_router, system_errors_router, profile_router, cv_upload_router,
    ai_search_router, extension_router, analytics_router, contact_router,
    blog_router, seo_router, pillar_pages_router, blog_digest_router,
    seo_dashboard_router, revenue_router, employer_router, linkedin_router,
    tracker_router, compliance_router, maintenance_router, attendance_router,
    attendance_analytics_router, resume_router, account_manager_router,
    notification_router, activity_router, finance_router,
    activity_monitor_router,
    extraction_report_router,
    extraction_trace_router,
    admin_monitoring_router,
    extension_updates_router,
    reports_router,
    talent_graph_router,
    sourcing_router,
]

for _r in _all_routers:
    if _r is not None:
        app.include_router(_r)

if _route_imports_failed:
    logging.error(f"[STARTUP] {len(_route_imports_failed)} route(s) failed to import:")
    for f in _route_imports_failed:
        logging.error(f"  - {f}")


# ============== MIDDLEWARE ==============

# Phase 54.13 — Gzip compression. Drops the admin/pipeline JSON from
# 2.5 MB → ~380 KB on the wire (85% smaller, 80% faster transfer over
# typical office connections). Threshold 500 bytes avoids overhead on
# small responses.
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=500)

from middleware.correlation import CorrelationIdMiddleware
app.add_middleware(CorrelationIdMiddleware)

from middleware.rate_limiter import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

from middleware.zero_trust import ZeroTrustMiddleware
app.add_middleware(ZeroTrustMiddleware)

from middleware.api_metrics import APIMetricsMiddleware
app.add_middleware(APIMetricsMiddleware)


# ============== GLOBAL EXCEPTION HANDLER ==============

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback as tb
    if isinstance(exc, HTTPException):
        raise exc

    error_msg = str(exc)
    stack = tb.format_exception(type(exc), exc, exc.__traceback__)
    stack_str = "".join(stack)

    user_id = None
    user_role = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from utils import verify_token
            payload = verify_token(auth_header.split(" ")[1])
            user_id = payload.get("sub")
            user_role = payload.get("role")
        except Exception:
            pass

    try:
        await log_system_error(
            source="backend",
            error_type=type(exc).__name__,
            message=error_msg,
            stack_trace=stack_str,
            endpoint=str(request.url.path),
            method=request.method,
            status_code=500,
            user_id=user_id,
            user_role=user_role,
        )
    except Exception:
        pass

    logging.error(f"Unhandled exception on {request.method} {request.url.path}: {error_msg}")
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ============== CORS ==============

_hardcoded_origins = [
    "https://ventureshrd.com",
    "https://www.ventureshrd.com",
]
_site_url = os.environ.get("SITE_URL", "").strip().rstrip("/")
if _site_url and _site_url not in _hardcoded_origins:
    _hardcoded_origins.append(_site_url)
_env_origins = [o.strip() for o in os.environ.get('CORS_ORIGINS', '').split(',') if o.strip()]

# SEC-4: Never allow wildcard with credentials — enumerate origins explicitly
_env_origins = [o for o in _env_origins if o != "*"]
_all_origins = list(set(_hardcoded_origins + _env_origins))

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== SECURITY HEADERS ==============

@app.middleware("http")
async def seo_security_headers(request: Request, call_next):
    try:
        response = await call_next(request)
    except RuntimeError:
        from starlette.responses import JSONResponse as _JSONResp
        return _JSONResp(status_code=500, content={"detail": "Internal server error"})
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # M-09: Content-Security-Policy to prevent stored XSS
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob: https://*.r2.dev https://*.cloudflare.com; "
        "connect-src 'self' https://api.ventureshrd.com https://*.upstash.io; "
        "frame-src https://challenges.cloudflare.com; "
        "frame-ancestors 'none';"
    )

    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["CDN-Cache-Control"] = "no-store"
        response.headers["Cloudflare-CDN-Cache-Control"] = "no-store"

    return response


# ============== LOGGING ==============

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
