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
    Validates MongoDB connectivity on startup. Non-blocking: logs warning if unavailable.
    Motor will auto-reconnect on subsequent requests.
    """
    for attempt in range(3):
        try:
            await client.admin.command("ping")
            # Log connection target for deployment verification (WARNING level for visibility)
            mongo_url_env = os.environ.get('MONGO_URL', '')
            mongodb_uri_env = os.environ.get('MONGODB_URI', '')
            active_uri = mongo_url_env or mongodb_uri_env
            is_atlas = 'mongodb+srv' in active_uri or 'mongodb.net' in active_uri
            host_preview = active_uri[:60] if active_uri else 'EMPTY'
            logging.warning(f"MongoDB connected: {'ATLAS' if is_atlas else 'LOCAL'} | DB: {db_name} | Host: {host_preview}...")
            logging.warning(f"  MONGO_URL set: {bool(mongo_url_env)} | MONGODB_URI set: {bool(mongodb_uri_env)} | Match: {mongo_url_env == mongodb_uri_env if mongo_url_env and mongodb_uri_env else 'N/A'}")
            if not is_atlas:
                logging.warning("CRITICAL: Connected to LOCAL MongoDB, NOT Atlas! Check MONGO_URL in .env")
            # Verify user count as sanity check
            user_count = await db.users.count_documents({})
            logging.warning(f"  DB sanity: users collection has {user_count} documents")
            return
        except Exception as e:
            logging.warning(f"MongoDB connection attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                await asyncio.sleep(5)
    logging.warning("MongoDB not available at startup. Motor will auto-reconnect on first request.")


@app.on_event("startup")
async def init_compliance_indexes():
    try:
        from services.compliance_service import ensure_compliance_indexes
        await ensure_compliance_indexes()
        logging.info("Compliance DB indexes initialized")
    except Exception as e:
        logging.warning(f"Compliance index init failed: {e}")


@app.on_event("startup")
async def init_maintenance_bot():
    try:
        # Create indexes for maintenance collections
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
        # Start bot background loop
        from services.maintenance_bot import start_bot
        start_bot()
        logging.info("Maintenance bot started")
    except Exception as e:
        logging.warning(f"Maintenance bot init failed: {e}")


@app.on_event("startup")
async def start_blog_scheduler():
    """Start the APScheduler background jobs for blog auto-publishing."""
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

        # Employer: Mon, Wed, Fri at 03:30 UTC (9:00 AM IST)
        scheduler.add_job(run_employer_publish, 'cron', day_of_week='mon,wed,fri', hour=3, minute=30, id='employer_blog')
        # Candidate: Tue, Thu at 04:30 UTC (10:00 AM IST)
        scheduler.add_job(run_candidate_publish, 'cron', day_of_week='tue,thu', hour=4, minute=30, id='candidate_blog')

        scheduler.start()
        app.state.blog_scheduler = scheduler
        logging.info("[BlogScheduler] Auto-publish scheduler started (Employer: Mon/Wed/Fri 9AM IST, Candidate: Tue/Thu 10AM IST)")
    except Exception as e:
        logging.warning(f"[BlogScheduler] Failed to start scheduler: {e}")

@app.on_event("startup")
async def validate_r2_connection():
    """
    Validates Cloudflare R2 connectivity on application startup.
    Non-blocking: Falls back to local storage if R2 is not available.
    """
    if R2_ENABLED:
        try:
            # List buckets to verify connectivity
            r2_client.list_buckets()
            logging.info("Cloudflare R2 successfully connected and operational")
            logging.info(f"R2 Bucket: {R2_BUCKET_NAME}")
        except Exception as e:
            logging.warning(f"Cloudflare R2 connectivity check failed: {e}")
            logging.warning("R2 may still work - some operations may succeed despite list_buckets failure")
    else:
        logging.info("Cloudflare R2 not configured - using local storage")

@app.on_event("startup")
async def normalize_existing_emails():
    """One-time: ensure all stored emails are lowercase + trimmed for consistency."""
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


@app.on_event("startup")
async def seed_canonical_users():
    """
    Seeds all canonical users on startup. Idempotent — skips existing emails.
    This ensures the LIVE DB always has the full user set regardless of which
    Atlas cluster is backing it.
    """
    CANONICAL_USERS = [
        {"id": "eb962d6f-ad6f-454a-bd7b-edc68f8b4ff7", "email": "admin@vhc.in", "name": "System Admin", "role": "admin", "password": "$2b$12$ZtGVQr6p.odISa05QSX4ZOGbol0ekJsSxbGahfxz86MngEYoIdmsy", "phone": None, "company_id": None, "is_active": True, "requires_password_reset": False, "created_at": "2026-01-18T08:01:29.570417+00:00"},
        {"id": "cf36890a-b8fa-47e2-abf3-d4600f04c831", "email": "ajit@vhc.in", "name": "Ajit Yadav", "role": "employer", "password": "$2b$12$dfrxtnSOfX0FYNfOK4ITyO5OaIsXh1BHsOQpi.hu044mI6BdKwb1m", "phone": "", "company_id": "", "is_active": True, "requires_password_reset": False, "created_at": "2026-01-24T11:12:03.591922+00:00"},
        {"id": "f2a32556-f910-453a-8a2d-961211a17c46", "email": "maneet@vhc.in", "name": "Maneet Siwach", "role": "employer", "password": "$2b$12$T/HoymVbxL594waHsMd9T.TSJaDaErcPAyk18scejB1.sej/7.x3K", "phone": "", "company_id": "", "is_active": True, "requires_password_reset": False, "created_at": "2026-01-24T11:12:28.421906+00:00"},
        {"id": "8dc5f7b9-be24-4e65-81d7-7af78fd07c18", "email": "bikash@vhc.in", "name": "Bikash Das", "role": "employer", "password": "$2b$12$lusoc9qdSgZ4pA5X1N2NPuMwITAkhXFhjRuGyK3hMHiQZz7C.bdvW", "phone": "", "company_id": "", "is_active": True, "requires_password_reset": False, "created_at": "2026-01-24T11:12:50.979012+00:00"},
        {"id": "e9e33bd0-db62-4db2-86ea-495a6230e222", "email": "avinash@vhc.in", "name": "Avinash D", "role": "employer", "password": "$2b$12$.OpYhQeiSoZDxvv8dKx8kOwoYcxxsXHEMkfL3YbQ0i33oPVR1t6zO", "phone": "", "company_id": "", "is_active": True, "requires_password_reset": False, "created_at": "2026-01-24T11:13:23.080204+00:00"},
        {"id": "06b70e35-bb06-41b9-a5f1-d9111112ae78", "email": "yamini@vhc.in", "name": "Yamini gupta", "role": "recruiter", "password": "$2b$12$TltmwBE9zX/2EnrfFBWE9.u14NZw0RKKUC0c68Ku2qnQzusHRPzFO", "phone": "", "company_id": "", "is_active": True, "requires_password_reset": False, "created_at": "2026-01-27T06:31:07.218244+00:00"},
        {"id": "839f5e28-f97e-4e0d-ae18-091e0636fa60", "email": "jatin@vhc.in", "name": "Jatin Yadav", "role": "recruiter", "password": "$2b$12$FqyCMbLAqndTOH8GdI6w7el./csjxH/uunI2Pfdf2cjtDB7gc7YoG", "phone": "", "company_id": "", "is_active": True, "requires_password_reset": False, "created_at": "2026-01-28T04:47:27.495354+00:00"},
        {"id": "3bee4bf4-02cb-4b81-8e40-7d8224f1fc94", "email": "yatharth@vhc.in", "name": "Yatharth rao", "role": "candidate", "password": "$2b$12$0AckEwRnz4gIEAnOuL3vxeemKfP.Swvj9lklolBeOk8Pm4tRVQz.y", "phone": None, "company_id": None, "is_active": False, "requires_password_reset": False, "created_at": "2026-02-08T12:12:07.205594+00:00"},
        {"id": "a792bb92-84dc-4fd3-be03-ec1940296dfc", "email": "admin@ventureshrd.com", "name": "System Admin", "role": "admin", "password": "$2b$12$XBS4GQKWbdntQiCpJJtzHuum60trpcvQuZRSxD8RKGWTH3/3/tquu", "phone": None, "company_id": None, "is_active": True, "requires_password_reset": False, "created_at": "2026-02-12T17:35:37.397223+00:00"},
        {"id": "f412d7aa-c3f1-436f-aaea-91600905f486", "email": "siddharth@vhc.in", "name": "Siddharth Rao", "role": "admin", "password": "$2b$12$okpacLfjsOC9WIPxGZ0uZuFYRpns/cKJGauIpRXYAzlNcr9.HWBR2", "phone": "9810557485", "company_id": "", "is_active": True, "requires_password_reset": False, "created_at": "2026-02-16T05:03:36.884013+00:00"},
        {"id": "a39a318f-a107-4a5b-b6ff-03232a4d2289", "email": "rohit@vhc.in", "name": "Rohit Yadav", "role": "employer", "password": "$2b$12$fRYVuQ1uLgh7Tb2vxMkDSO4lS19xv0CwiMRW4EePCPeV3Ns0dwROe", "phone": "", "company_id": "", "is_active": True, "requires_password_reset": True, "created_at": "2026-02-16T08:08:13.909837+00:00"},
        {"id": "10f2023f-1404-4ae6-afea-884384e020fd", "email": "manorma@vhc.in", "name": "Manorma yadav", "role": "employer", "password": "$2b$12$JUkE1doXQs9txyHaubcuy.Fh1IDj8bPsI0.tpKJtjyoEr4F5JxePW", "phone": "", "company_id": "", "is_active": True, "requires_password_reset": False, "created_at": "2026-02-16T08:08:57.878577+00:00"},
        {"id": "a8f2f035-8d4b-4c90-ae53-ef64a0fd7c0c", "email": "rohitjakhmola28@yahoo.com", "name": "ROHIT JAKHMOLA", "role": "candidate", "password": "$2b$12$vI7BxZzUE2UEdOs.3T0ft.EKXz0CpB3hMA2Voiku2crI/k52/IjpO", "phone": None, "company_id": None, "is_active": True, "requires_password_reset": True, "created_at": "2026-02-16T12:07:09.594698+00:00"},
        {"id": "67ac3ae1-5b14-4a1c-aedf-0cbbbb58e629", "email": "yatharthrao9@gmail.com", "name": "Nehul Singhania", "role": "candidate", "password": "$2b$12$eYUSvOjtfWAJnIzSOqG9X.FIwiKUj12wglU9WOdmvjey3ObXIPZKq", "phone": None, "company_id": None, "is_active": True, "requires_password_reset": True, "created_at": "2026-02-16T12:41:50.545989+00:00"},
        {"id": "57eec150-0f3f-4922-9dfc-b4dbbcf1d28f", "email": "durainaidu1@gmail.com", "name": "G.DURAI", "role": "candidate", "password": "$2b$12$rW/kR1mhfYl7AF4.2x1ELOuHkJMchr1i8NlCtNZxHH05Kzjq323wu", "phone": "9940719536", "company_id": None, "is_active": True, "requires_password_reset": False, "created_at": "2026-02-17T14:15:57.033202+00:00"},
        {"id": "218de586-9494-4b42-a2ed-6dabc411ce2c", "email": "khatrianandd@gmail.com", "name": "Anand  Khatri", "role": "candidate", "password": "$2b$12$X2DBwgMdAWAV/dTzrki24uPC3GEfUqadmGzlUme4LtHMbbrvyW2I.", "phone": "6377361515", "company_id": None, "is_active": True, "requires_password_reset": False, "created_at": "2026-02-19T07:41:24.740221+00:00"},
        {"id": "0ce74b21-6950-402a-a91f-846586ee4a21", "email": "bhumika@vhc.in", "name": "Bhumika Anand", "role": "recruiter", "password": "$2b$12$4XtD.DbBIZccrGnv7vKbKu5QlDRq399CNtQljvTABLl2TwgtLjkTG", "phone": "8800555880", "company_id": "", "is_active": True, "requires_password_reset": False, "created_at": "2026-02-20T05:00:11.904178+00:00"},
        {"id": "6be69a8a-e0ba-46fd-9a1b-f403edd54d3f", "email": "employer@vhc.in", "name": "Demo Employer", "role": "employer", "password": "$2b$12$./lJf/SWtP8m01Yg1r/EgubWOECAVabgBYShCqbEVsgawBweQgCG6", "phone": None, "company_id": None, "is_active": True, "requires_password_reset": False, "created_at": "2026-02-20T11:27:46.843891+00:00"},
        {"id": "68c2a939-e10b-4442-bc9e-2f9e757d9729", "email": "test_turnstile_bypass_61c488d7@example.com", "name": "Turnstile Bypass Test", "role": "candidate", "password": "$2b$12$OMVjeqLVJS9Gdh9nFEqbNe/h38ut0VLgMq2YRFnM4I2.JFutJ12IC", "phone": None, "company_id": None, "is_active": True, "requires_password_reset": False, "created_at": "2026-02-21T13:24:55.554289+00:00"},
    ]

    try:
        existing_emails = set()
        async for doc in db.users.find({}, {"email": 1, "_id": 0}):
            existing_emails.add(doc.get("email", "").strip().lower())

        inserted = 0
        for user in CANONICAL_USERS:
            if user["email"].strip().lower() not in existing_emails:
                await db.users.insert_one(user)
                inserted += 1
                logging.info(f"[USER_SEED] Inserted missing user: {user['email']}")

        total = await db.users.count_documents({})
        if inserted:
            logging.warning(f"[USER_SEED] Seeded {inserted} missing users. Total now: {total}")
        else:
            logging.info(f"[USER_SEED] All {total} canonical users already present")
    except Exception as e:
        logging.warning(f"[USER_SEED] Skipped (DB not available): {e}")

@app.on_event("startup")
async def ensure_pillar_pages_index():
    """Create unique index on pillar_pages.slug."""
    try:
        await db.pillar_pages.create_index("slug", unique=True)
        logging.info("pillar_pages.slug unique index ensured")
    except Exception as e:
        logging.warning(f"pillar_pages index creation skipped: {e}")

@app.on_event("startup")
async def ensure_blog_digests_index():
    """Create indexes on blog_digests and seo collections."""
    try:
        await db.blog_digests.create_index("week_key", unique=True)
        await db.blog_digests.create_index([("generated_at", -1)])
        await db.seo_snapshots.create_index([("snapshot_date", -1)])
        await db.seo_alerts.create_index("status")
        await db.seo_alerts.create_index("severity")
        logging.info("blog_digests + seo indexes ensured")
    except Exception as e:
        logging.warning(f"Index creation skipped: {e}")

@app.on_event("startup")
async def start_background_scheduler():
    """Start APScheduler for background jobs."""
    from services.scheduler import start_scheduler
    try:
        start_scheduler()
    except Exception as e:
        logging.error(f"Scheduler startup failed: {e}", exc_info=True)

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
    response = await call_next(request)
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
