"""
Application lifecycle management — startup/shutdown tasks.
Extracted from server.py for modularity.
"""
import os
import logging
import asyncio
from config import db, db_name, client, R2_ENABLED, r2_client, R2_BUCKET_NAME

logger = logging.getLogger(__name__)


async def run_critical_init():
    """
    Synchronous DB initialization — MUST complete before the server accepts requests.
    This eliminates the 1-2 second window where requests fail with 503/500.
    If MongoDB is unreachable after retries, the worker CRASHES so Gunicorn restarts it.
    """
    import config as _cfg

    # --- Initialize MongoDB client ---
    try:
        _cfg.initialize_db()
        logging.warning("[CRITICAL INIT] MongoDB client created successfully")
    except Exception as e:
        logging.critical(f"[CRITICAL INIT] FATAL: MongoDB client creation failed: {e}")
        raise  # Crash the worker — no point serving requests without DB

    # --- Initialize services that depend on DB ---
    try:
        _cfg.init_services()
    except Exception as e:
        logging.warning(f"[CRITICAL INIT] init_services failed: {e}")

    # --- Verify DB connectivity with retries ---
    last_error = None
    for attempt in range(3):
        try:
            await client.admin.command("ping")
            user_count = await db.users.count_documents({})
            logging.warning(f"[CRITICAL INIT] MongoDB OK | users={user_count} | db={db_name}")
            return  # Success
        except Exception as e:
            last_error = e
            logging.warning(f"[CRITICAL INIT] MongoDB ping attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                await asyncio.sleep(2)

    # All retries exhausted — crash the worker so Gunicorn restarts it
    logging.critical("[CRITICAL INIT] FATAL: MongoDB unreachable after 3 attempts. Crashing worker.")
    raise RuntimeError(f"MongoDB unreachable after 3 ping attempts: {last_error}")


async def run_deferred_init(app):
    """
    Background tasks that can run AFTER the server is already accepting requests.
    DB is guaranteed to be initialized before this runs.
    """
    import config as _cfg

    # --- Environment report ---
    try:
        from utils.environment import log_environment_banner
        log_environment_banner()
    except Exception as e:
        logging.warning(f"[ENV] Environment report skipped: {e}")

    # --- MongoDB diagnostics ---
    def _mask(uri: str) -> str:
        if not uri:
            return "(empty)"
        if "://" in uri and "@" in uri:
            scheme_end = uri.index("://") + 3
            at_pos = uri.index("@")
            return uri[:scheme_end] + "***:***@" + uri[at_pos + 1:]
        return uri[:30] + "..."

    mongo_url_env = os.environ.get('MONGO_URL', '')
    db_name_env = os.environ.get('DB_NAME', '')

    logging.warning("=" * 60)
    logging.warning("  MONGO CONNECTION DIAGNOSTICS")
    logging.warning(f"  ACTUAL URI    = {_mask(_cfg.mongodb_uri)}")
    logging.warning(f"  ENV MONGO_URL = {_mask(mongo_url_env)}")
    logging.warning(f"  DB_NAME (used)= {db_name}")
    logging.warning(f"  DB_NAME (env) = {db_name_env or '(not set)'}")
    logging.warning("=" * 60)

    # --- Notification indexes (fast unread count queries) ---
    try:
        await db.notifications.create_index([("user_id", 1), ("is_read", 1)])
        await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
        logging.info("Notification DB indexes initialized")
    except Exception as e:
        logging.warning(f"Notification index init failed: {e}")

    # --- Core collection indexes (performance-critical) ---
    async def _safe_index(collection, keys, **kwargs):
        """Create index, skip if already exists with different name."""
        try:
            await collection.create_index(keys, **kwargs)
        except Exception:
            pass  # Index exists (possibly under different name)

    try:
        # candidate_bank — 94 queries, most queried collection
        await _safe_index(db.candidate_bank, "email")
        await _safe_index(db.candidate_bank, "phone")
        await _safe_index(db.candidate_bank, "id", unique=True)
        await _safe_index(db.candidate_bank, [("company_id", 1), ("created_at", -1)])
        await _safe_index(db.candidate_bank, [("source", 1), ("created_at", -1)])
        await _safe_index(db.candidate_bank, [("created_at", -1)])
        await _safe_index(db.candidate_bank, [("mandate_id", 1)])
        await _safe_index(db.candidate_bank, "naukri_id")
        await _safe_index(db.candidate_bank, "naukri_profile_id")

        # badge_audit — Phase 56.3 (rolling 30-day TTL via `expires_at`)
        await _safe_index(db.badge_audit, "id", unique=True)
        await _safe_index(db.badge_audit, [("ts", -1)])
        await _safe_index(db.badge_audit, [("user_email", 1), ("ts", -1)])
        await _safe_index(db.badge_audit, "expires_at", expireAfterSeconds=0)

        # badge_feedback — user-reported wrong-match flags (Badge Phase A,
        # 2026-06-15). 180-day TTL, separate from auto-labelled badge_audit.
        await _safe_index(db.badge_feedback, "id", unique=True)
        await _safe_index(db.badge_feedback, [("ts", -1)])
        await _safe_index(db.badge_feedback, [("kind", 1), ("ts", -1)])
        await _safe_index(db.badge_feedback, [("badge_candidate_id", 1), ("ts", -1)])
        await _safe_index(db.badge_feedback, "expires_at", expireAfterSeconds=0)

        # enrichment_cache — Search Phase 2 (2026-06-15). Long-lived cache
        # for LLM-derived inferences (company → industry); _id is the
        # cache key so no extra index needed beyond the default.
        # (no TTL — these answers don't expire)

        # search_sessions — Phase 56.5 LTR telemetry (180-day TTL)
        await _safe_index(db.search_sessions, "id", unique=True)
        await _safe_index(db.search_sessions, [("ts", -1)])
        await _safe_index(db.search_sessions, [("user_email", 1), ("ts", -1)])
        await _safe_index(db.search_sessions, "expires_at", expireAfterSeconds=0)

        # extension_capture_jobs — async capture poll-state (Phase 57:
        # 7-day TTL via `expires_at`; was unbounded growth + no sweep index)
        await _safe_index(db.extension_capture_jobs, "expires_at", expireAfterSeconds=0)
        await _safe_index(db.extension_capture_jobs, [("status", 1), ("updated_at", 1)])

        # candidate_embeddings — cluster-bounded vector fallback (Phase 57
        # perf rewrite) routes every similar/search query through cluster_id
        await _safe_index(db.candidate_embeddings, "cluster_id")

        # users — 82 queries
        await _safe_index(db.users, "email", unique=True)
        await _safe_index(db.users, "id", unique=True)
        await _safe_index(db.users, [("role", 1), ("company_id", 1)])

        # jobs — 79 queries
        await _safe_index(db.jobs, "id", unique=True)
        await _safe_index(db.jobs, [("company_id", 1), ("status", 1)])
        await _safe_index(db.jobs, [("posted_by", 1), ("created_at", -1)])
        await _safe_index(db.jobs, "status")

        # teams — 60 queries
        await _safe_index(db.teams, "id", unique=True)
        await _safe_index(db.teams, "company_id")

        # applications — 47 queries
        await _safe_index(db.applications, "id", unique=True)
        await _safe_index(db.applications, [("job_id", 1), ("status", 1)])
        await _safe_index(db.applications, [("candidate_id", 1), ("created_at", -1)])
        await _safe_index(db.applications, "job_id")
        await _safe_index(db.applications, [("job_id", 1), ("stage", 1), ("updated_at", -1)])

        # companies — 44 queries
        await _safe_index(db.companies, "id", unique=True)
        await _safe_index(db.companies, "name")

        # LLM enrichment cache — content-hash deduplication
        await _safe_index(db.llm_enrichment_cache, "text_hash", unique=True)
        await _safe_index(db.llm_enrichment_cache, "created_at")

        # Refresh tokens (M-03) — single-use rotation
        await _safe_index(db.refresh_tokens, "token_hash", unique=True)
        await _safe_index(db.refresh_tokens, "user_id")
        await _safe_index(db.refresh_tokens, "expires_at")

        # Login attempts (brute-force lockout)
        await _safe_index(db.login_attempts, "email", unique=True)

        # Additional compound indexes from audit (PERF-3)
        await _safe_index(db.jobs, [("status", 1), ("career_page_status", 1)])
        await _safe_index(db.users, [("role", 1), ("is_active", 1)])

        logging.warning("[DB Indexes] Core collection indexes initialized successfully")
    except Exception as e:
        logging.warning(f"[DB Indexes] Core index init failed: {e}")

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
        # Phase 56: analytics page-view tracking
        await db.analytics_pageviews.create_index("ts")
        await db.analytics_pageviews.create_index("user_id")
        await db.analytics_pageviews.create_index("route")
        await db.analytics_pageviews.create_index([("ts", -1), ("event_type", 1)])
        from services.maintenance_bot import start_bot
        start_bot()
        logging.info("Maintenance bot started")
    except Exception as e:
        logging.warning(f"Maintenance bot init failed: {e}")

    # --- Blog scheduler ---
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from services.blog_scheduler import auto_publish_blog, get_schedule_config, auto_generate_pipeline

        scheduler = AsyncIOScheduler()

        async def run_employer_publish():
            config = await get_schedule_config()
            if config.get("employer", {}).get("enabled"):
                await auto_publish_blog("employer")

        async def run_candidate_publish():
            config = await get_schedule_config()
            if config.get("candidate", {}).get("enabled"):
                await auto_publish_blog("candidate")

        async def run_auto_generate():
            """Refill draft queue if below minimum thresholds."""
            config = await get_schedule_config()
            if config.get("auto_generate", {}).get("enabled", True):
                await auto_generate_pipeline()

        scheduler.add_job(run_employer_publish, 'cron', day_of_week='mon,wed,fri', hour=3, minute=30, id='employer_blog')
        scheduler.add_job(run_candidate_publish, 'cron', day_of_week='tue,thu', hour=4, minute=30, id='candidate_blog')
        scheduler.add_job(run_auto_generate, 'cron', hour=2, minute=0, id='auto_generate_blogs')
        scheduler.start()
        app.state.blog_scheduler = scheduler
        logging.info("[BlogScheduler] Auto-publish + auto-generate scheduler started")
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

    # --- Recruiter performance reports (Daily + Weekly Excel to team leaders) ---
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from services.reports_service import generate_and_send_daily_reports, generate_and_send_weekly_reports
        from services.team_digest_service import run_daily_digest
        from config import db as _db

        async def _run_daily():
            await generate_and_send_daily_reports(_db)

        async def _run_weekly():
            await generate_and_send_weekly_reports(_db)

        async def _run_team_digest():
            await run_daily_digest(_db)

        reports_scheduler = AsyncIOScheduler()
        # Team digest at 18:29 IST = 12:59 UTC — 1 min before email reports
        reports_scheduler.add_job(_run_team_digest, 'cron', hour=12, minute=59, id='daily_team_digest')
        # 18:30 IST = 13:00 UTC (APScheduler default timezone is UTC)
        reports_scheduler.add_job(_run_daily, 'cron', hour=13, minute=0, id='daily_recruiter_report')
        # 09:00 IST Monday = 03:30 UTC Monday
        reports_scheduler.add_job(_run_weekly, 'cron', day_of_week='mon', hour=3, minute=30, id='weekly_recruiter_report')
        reports_scheduler.start()
        app.state.reports_scheduler = reports_scheduler
        # Use WARNING level so it surfaces in gunicorn logs alongside other schedulers
        logging.warning("[ReportsScheduler] Team digest (18:29 IST) + Daily (18:30 IST) + Weekly (Mon 09:00 IST) jobs started")
        for j in reports_scheduler.get_jobs():
            logging.warning(f"[ReportsScheduler] Job: {j.id} | next_run={j.next_run_time}")
    except Exception as e:
        logging.warning(f"[ReportsScheduler] Failed to start: {e}")

    # --- Batch API enrichment scheduler (DISABLED — using spaCy + Haiku instead) ---
    # To re-enable: uncomment the block below
    # try:
    #     from services.batch_enrichment import submit_batch, poll_and_process_batches
    #     batch_scheduler = AsyncIOScheduler()
    #     batch_scheduler.add_job(lambda: submit_batch(), 'interval', minutes=30, id='batch_submit')
    #     batch_scheduler.add_job(lambda: poll_and_process_batches(), 'interval', minutes=5, id='batch_poll')
    #     batch_scheduler.start()
    #     app.state.batch_scheduler = batch_scheduler
    # except Exception as e:
    #     logging.warning(f"[BatchScheduler] Failed: {e}")

    # --- R2 validation ---
    if R2_ENABLED:
        try:
            r2_client.head_bucket(Bucket=R2_BUCKET_NAME)
            logging.info(f"Cloudflare R2 connected. Bucket: {R2_BUCKET_NAME}")
        except Exception as e:
            logging.warning(f"Cloudflare R2 connectivity check failed: {e}")
            logging.warning("R2 may still work for object operations")
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

    # --- Activity log indexes ---
    try:
        from services.activity_log_service import ensure_activity_indexes
        await ensure_activity_indexes()
    except Exception as e:
        logging.warning(f"Activity log index init failed: {e}")

    # --- E-04: Preload spaCy model at startup to avoid first-request latency ---
    try:
        from services.spacy_extractor import _get_nlp
        _get_nlp()
        logging.info("[Startup] spaCy model preloaded")
    except Exception as e:
        logging.warning(f"[Startup] spaCy preload failed (non-critical): {e}")

    # --- Temp file cleanup scheduler (PERF-6) ---
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        import time as _time
        from pathlib import Path as _Path

        def _cleanup_temp_files():
            upload_dir = _Path(__file__).parent.parent / "uploads"
            if not upload_dir.exists():
                return
            cutoff = _time.time() - 86400  # 24 hours
            cleaned = 0
            for f in upload_dir.glob("temp_*"):
                try:
                    if f.stat().st_mtime < cutoff:
                        f.unlink()
                        cleaned += 1
                except Exception:
                    pass
            if cleaned:
                logging.info(f"[TempCleanup] Deleted {cleaned} temp files older than 24h")

        temp_scheduler = AsyncIOScheduler()
        temp_scheduler.add_job(_cleanup_temp_files, 'cron', hour=1, minute=0, id='temp_file_cleanup')
        temp_scheduler.start()
        app.state.temp_cleanup_scheduler = temp_scheduler
        logging.info("[TempCleanup] Nightly temp file cleanup scheduler started")
    except Exception as e:
        logging.warning(f"[TempCleanup] Failed to start: {e}")

    # --- Background scheduler ---
    try:
        from services.scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        logging.error(f"Scheduler startup failed: {e}", exc_info=True)

    logging.info("[DEFERRED INIT] All background services initialized")


async def shutdown_scheduler():
    """Gracefully stop the scheduler."""
    from services.scheduler import stop_scheduler
    stop_scheduler()


async def shutdown_db(app_client):
    """Close database connection."""
    if app_client:
        app_client.close()
