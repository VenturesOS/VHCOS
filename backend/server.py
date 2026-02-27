from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, status, Form, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
import os
import logging
import hashlib
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt
import aiofiles
import fitz  # PyMuPDF for PDF text extraction

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

# Import models from models/
from models import (
    # Auth models
    UserBase, UserCreate, UserLogin, UserResponse, UserUpdate,
    AdminUserCreate, AdminPasswordReset, PasswordReset, TokenResponse,
    # Job models
    JobBase, JobCreate, JobResponse, JobUpdate, JobStateTransition,
    CareerPageStatusUpdate, JDParseRequest, JDParseResponse, MandateAssignment,
    # Candidate models
    CandidateProfile, CandidateProfileUpdate,
    # Application models
    ApplicationBase, ApplicationCreate, ApplicationResponse,
    ApplicationUpdate, ApplicationDetailUpdate, AuditLogEntry, NoteCreate,
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
from services import (
    upload_to_r2,
    get_r2_signed_url,
    get_file_from_r2,
    generate_r2_key
)

# Import route modules
from routes import auth_router, public_router, files_router, admin_router, jobs_router, candidates_router, applications_router, settings_router, background_jobs_router, teams_router, referrals_router, commercials_router, analytics_router, revenue_router, employer_router, linkedin_router
from routes.bulk_import import bulk_import_router
from routes.bug_reports import bug_reports_router
from routes.system_errors import system_errors_router, log_system_error
from routes.extension import extension_router
from routes.profile import profile_router
from routes.cv_upload import cv_upload_router
from routes.ai_search import ai_search_router
from routes.contact import router as contact_router
from routes.blog import router as blog_router
from routes.seo import router as seo_router
from routes.pillar_pages import router as pillar_pages_router
from routes.blog_digest import router as blog_digest_router
from routes.seo_dashboard import router as seo_dashboard_router
from routes.tracker import router as tracker_router
from routes.compliance_routes import compliance_router
from routes.maintenance_routes import maintenance_router
from routes.attendance import router as attendance_router
from routes.attendance_analytics import router as attendance_analytics_router

# Import boto3 for type hints (r2_client operations)
import boto3
from botocore.config import Config


# Create the main app
app = FastAPI(title="VHC Talent OS API")


@app.get("/health")
async def health_check():
    return {"status": "ok"}


# Include auth routes (extracted to routes/auth.py)
app.include_router(auth_router)

# Include public routes (extracted to routes/public.py)
app.include_router(public_router)

# Include file serving routes (extracted to routes/files.py)
app.include_router(files_router)

# Include admin routes (extracted to routes/admin.py)
app.include_router(admin_router)

# Include jobs routes (extracted to routes/jobs.py)
app.include_router(jobs_router)

# Include candidate bank routes (extracted to routes/candidates.py)
app.include_router(candidates_router)

# Include applications & AI matching routes (extracted to routes/applications.py)
app.include_router(applications_router)

# Include settings & alerts routes (extracted to routes/settings.py)
app.include_router(settings_router)

# Include background jobs & embeddings routes
app.include_router(background_jobs_router)

# Include bulk import routes (Admin only - for controlled data seeding)
app.include_router(bulk_import_router)

# Include extracted business-logic routes
app.include_router(teams_router)
app.include_router(referrals_router)
app.include_router(commercials_router)
app.include_router(bug_reports_router)
app.include_router(system_errors_router)
app.include_router(profile_router)
app.include_router(cv_upload_router)
app.include_router(ai_search_router)
app.include_router(extension_router)
app.include_router(analytics_router)
app.include_router(contact_router)
app.include_router(blog_router)
app.include_router(seo_router)
app.include_router(pillar_pages_router)
app.include_router(blog_digest_router)
app.include_router(seo_dashboard_router)
app.include_router(revenue_router)
app.include_router(employer_router)
app.include_router(linkedin_router)
app.include_router(tracker_router)
app.include_router(compliance_router)
app.include_router(maintenance_router)
app.include_router(attendance_router)
app.include_router(attendance_analytics_router)

# ============== RATE LIMITING MIDDLEWARE ==============
from middleware.rate_limiter import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# ============== ZERO TRUST MIDDLEWARE ==============
from middleware.zero_trust import ZeroTrustMiddleware
app.add_middleware(ZeroTrustMiddleware)

# All employer/admin business endpoints extracted to routes/employer_routes.py
# Endpoints: /api/employers/{id}/companies, /api/employer/my-team, /api/employer/companies,
#            /api/employer/pipeline, /api/companies/{id}/assign-employer,
#            /api/companies/{id} (PUT), /api/admin/hierarchy,
#            /api/analytics/admin, /api/analytics/employer,
#            /api/companies/{id}/pipeline

# ============== SEED ADMIN ==============

@app.on_event("startup")
async def log_environment_report():
    """Log environment details once at startup for deployment auditing."""
    try:
        from utils.environment import log_environment_banner
        log_environment_banner()
    except Exception as e:
        logging.warning(f"[ENV] Environment report skipped: {e}")


@app.on_event("startup")
async def validate_mongodb_connection():
    """
    Validates MongoDB connectivity and logs full connection diagnostics.
    """
    def _mask(uri: str) -> str:
        """Mask credentials in URI for safe logging."""
        if not uri:
            return "(empty)"
        if "://" in uri and "@" in uri:
            scheme_end = uri.index("://") + 3
            at_pos = uri.index("@")
            return uri[:scheme_end] + "***:***@" + uri[at_pos + 1:]
        return uri[:30] + "..."

    mongo_url_env = os.environ.get('MONGO_URL', '')
    mongodb_uri_env = os.environ.get('MONGODB_URI', '')
    db_name_env = os.environ.get('DB_NAME', '')

    from config import mongodb_uri as _actual_uri
    logging.warning("=" * 60)
    logging.warning("  MONGO CONNECTION DIAGNOSTICS")
    logging.warning(f"  ACTUAL URI    = {_mask(_actual_uri)}")
    logging.warning(f"  ENV MONGO_URL = {_mask(mongo_url_env)}")
    logging.warning(f"  DB_NAME (used)= {db_name}")
    logging.warning(f"  DB_NAME (env) = {db_name_env or '(not set)'}")
    logging.warning("=" * 60)

    for attempt in range(3):
        try:
            await client.admin.command("ping")
            user_count = await db.users.count_documents({})
            logging.warning(f"  MongoDB OK | users={user_count} | db={db_name}")
            if user_count < 19:
                logging.warning(f"  WARNING: Expected 19 users but found {user_count}. Likely connected to WRONG database!")
            return
        except Exception as e:
            logging.warning(f"  MongoDB attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                await asyncio.sleep(5)
    logging.warning("  MongoDB not available at startup. Motor will auto-reconnect on first request.")


@app.on_event("startup")
async def deferred_db_init():
    """
    Run all heavy DB operations (indexes, bots, schedulers) in the BACKGROUND
    so the server binds to port 8001 immediately and passes health checks.
    Previously these were 12+ separate startup events that could take 60s+ total.
    """
    async def _run_deferred():
        await asyncio.sleep(2)  # Let the server fully bind first

        # --- Compliance indexes ---
        try:
            from services.compliance_service import ensure_compliance_indexes
            await ensure_compliance_indexes()
            logging.info("Compliance DB indexes initialized")
        except Exception as e:
            logging.warning(f"Compliance index init failed: {e}")

        # --- Attendance indexes ---
        try:
            await db.attendance_records.create_index([("user_id", 1), ("date", 1)], unique=True)
            await db.attendance_records.create_index("date")
            await db.attendance_records.create_index("status")
            await db.leave_requests.create_index([("user_id", 1), ("start_date", 1)])
            await db.leave_requests.create_index("status")
            await db.leave_balances.create_index([("user_id", 1), ("year", 1)], unique=True)
            await db.holidays.create_index("date", unique=True)
            await db.notification_events.create_index([("recipient_id", 1), ("created_at", -1)])
            await db.notification_events.create_index("event_type")
            await db.notification_delivery_logs.create_index([("event_id", 1), ("channel", 1)])
            await db.cron_job_locks.create_index("job_name", unique=True)
            await db.cron_job_logs.create_index([("job_name", 1), ("executed_at", -1)])
            await db.attendance_health_scores.create_index("user_id", unique=True)
            logging.info("Attendance DB indexes initialized")
        except Exception as e:
            logging.warning(f"Attendance index init failed: {e}")

        # --- Maintenance bot indexes + start ---
        try:
            await db.system_health_checks.create_index("timestamp")
            await db.system_health_checks.create_index("service_name")
            await db.maintenance_fixes.create_index("start_time")
            await db.maintenance_fixes.create_index("service_name")
            await db.reliability_events.create_index("timestamp")
            await db.reliability_events.create_index("event_type")
            await db.reliability_buffer.create_index("status")
            await db.naukri_capture_logs.create_index("timestamp")
            await db.naukri_capture_logs.create_index("status")
            await db.naukri_capture_logs.create_index([("status", 1), ("is_recovered", 1)])
            await db.security_events.create_index("timestamp")
            await db.security_events.create_index("event_type")
            await db.security_events.create_index("severity")
            from services.maintenance_bot import start_bot
            start_bot()
            logging.info("Maintenance bot started")
        except Exception as e:
            logging.warning(f"Maintenance bot init failed: {e}")

        # --- Blog scheduler ---
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from services.blog_scheduler import auto_publish_blog, get_schedule_config

            scheduler = AsyncIOScheduler()

            async def run_employer_publish():
                config = await get_schedule_config()
                if config.get("employer", {}).get("enabled"):
                    await auto_publish_blog("employer")

            async def run_candidate_publish():
                config = await get_schedule_config()
                if config.get("candidate", {}).get("enabled"):
                    await auto_publish_blog("candidate")

            scheduler.add_job(run_employer_publish, 'cron', day_of_week='mon,wed,fri', hour=3, minute=30, id='employer_blog')
            scheduler.add_job(run_candidate_publish, 'cron', day_of_week='tue,thu', hour=4, minute=30, id='candidate_blog')
            scheduler.start()
            app.state.blog_scheduler = scheduler
            logging.info("[BlogScheduler] Auto-publish scheduler started")
        except Exception as e:
            logging.warning(f"[BlogScheduler] Failed to start scheduler: {e}")

        # --- Attendance scheduler ---
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from services.attendance_cron_service import run_attendance_reminders, run_auto_absent_marking

            scheduler = AsyncIOScheduler()
            scheduler.add_job(run_attendance_reminders, 'cron', hour=4, minute=30, id='attendance_reminder')
            scheduler.add_job(run_auto_absent_marking, 'cron', hour=13, minute=0, id='auto_absent')
            scheduler.start()
            app.state.attendance_scheduler = scheduler
            logging.info("[AttendanceScheduler] Cron jobs started")
        except Exception as e:
            logging.warning(f"[AttendanceScheduler] Failed to start: {e}")

        # --- R2 validation ---
        if R2_ENABLED:
            try:
                r2_client.list_buckets()
                logging.info("Cloudflare R2 successfully connected")
            except Exception as e:
                logging.warning(f"Cloudflare R2 connectivity check failed: {e}")
                logging.warning("R2 may still work - some operations may succeed despite list_buckets failure")
        else:
            logging.info("Cloudflare R2 not configured - using local storage")

        # --- Email normalization ---
        try:
            cursor = db.users.find({"email": {"$regex": "[A-Z\\s]"}}, {"_id": 1, "email": 1})
            count = 0
            async for doc in cursor:
                normalised = doc["email"].strip().lower()
                if normalised != doc["email"]:
                    await db.users.update_one({"_id": doc["_id"]}, {"$set": {"email": normalised}})
                    count += 1
            if count:
                logging.warning(f"[EMAIL_NORM] Normalised {count} existing user emails to lowercase")
        except Exception as e:
            logging.warning(f"[EMAIL_NORM] Skipped: {e}")

        # --- Pillar pages index ---
        try:
            await db.pillar_pages.create_index("slug", unique=True)
        except Exception as e:
            logging.warning(f"pillar_pages index creation skipped: {e}")

        # --- Blog digests + SEO indexes ---
        try:
            await db.blog_digests.create_index("week_key", unique=True)
            await db.blog_digests.create_index([("generated_at", -1)])
            await db.seo_snapshots.create_index([("snapshot_date", -1)])
            await db.seo_alerts.create_index("status")
            await db.seo_alerts.create_index("severity")
            logging.info("blog_digests + seo indexes ensured")
        except Exception as e:
            logging.warning(f"Index creation skipped: {e}")

        # --- Background scheduler ---
        try:
            from services.scheduler import start_scheduler
            start_scheduler()
        except Exception as e:
            logging.error(f"Scheduler startup failed: {e}", exc_info=True)

        logging.info("[DEFERRED INIT] All background services initialized")

    # Fire and forget — server can start accepting requests immediately
    asyncio.create_task(_run_deferred())

@app.on_event("shutdown")
async def stop_background_scheduler():
    """Gracefully stop the scheduler."""
    from services.scheduler import stop_scheduler
    stop_scheduler()


# Auto-capture unhandled exceptions and log to system_errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback as tb
    # Skip HTTP exceptions (they're intentional)
    if isinstance(exc, HTTPException):
        raise exc

    error_msg = str(exc)
    stack = tb.format_exception(type(exc), exc, exc.__traceback__)
    stack_str = "".join(stack)

    # Extract user from token if present
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


# CORS: combine hardcoded production origins with env overrides
_hardcoded_origins = [
    "https://ventureshrd.com",
    "https://www.ventureshrd.com",
]
_env_origins = [o.strip() for o in os.environ.get('CORS_ORIGINS', '').split(',') if o.strip()]

# If wildcard is specified, use it directly (Starlette reflects actual origin with credentials)
if "*" in _env_origins:
    _all_origins = ["*"]
else:
    _all_origins = list(set(_hardcoded_origins + _env_origins))

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# SEO & Security Headers Middleware
@app.middleware("http")
async def seo_security_headers(request: Request, call_next):
    try:
        response = await call_next(request)
    except RuntimeError:
        from starlette.responses import JSONResponse as _JSONResp
        return _JSONResp(status_code=500, content={"detail": "Internal server error"})
    # HTTPS enforcement headers
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Prevent Cloudflare / browser from caching API responses
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["CDN-Cache-Control"] = "no-store"
        response.headers["Cloudflare-CDN-Cache-Control"] = "no-store"

    return response

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
