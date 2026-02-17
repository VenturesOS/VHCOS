"""
APScheduler — Background job scheduler for VHC Talent OS.
Runs the weekly blog digest every Monday at 09:00 IST.
"""
import asyncio
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()
_started = False


def _run_digest_sync():
    """Synchronous wrapper to run the async digest generator."""
    from services.blog_digest import generate_weekly_digest
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.ensure_future(generate_weekly_digest())
            # Can't await in sync context when loop is running; use run_coroutine_threadsafe
            import concurrent.futures
            future = asyncio.run_coroutine_threadsafe(generate_weekly_digest(), loop)
            result = future.result(timeout=120)
        else:
            result = asyncio.run(generate_weekly_digest())
        logger.info(f"[Scheduler] Digest job completed: {result.get('status')}")
    except Exception as e:
        logger.error(f"[Scheduler] Digest job failed: {e}", exc_info=True)


def start_scheduler():
    """Start the APScheduler. Safe to call multiple times — only starts once."""
    global _started
    if _started:
        logger.info("[Scheduler] Already running, skipping")
        return

    # Weekly digest: Monday 09:00 IST (03:30 UTC)
    scheduler.add_job(
        _run_digest_sync,
        CronTrigger(day_of_week="mon", hour=9, minute=0, timezone="Asia/Kolkata"),
        id="weekly_blog_digest",
        name="Weekly Blog Digest",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    _started = True

    jobs = scheduler.get_jobs()
    for job in jobs:
        logger.info(f"[Scheduler] Registered job: {job.name} | next_run={job.next_run_time}")


def stop_scheduler():
    """Gracefully shutdown the scheduler."""
    global _started
    if _started:
        scheduler.shutdown(wait=False)
        _started = False
        logger.info("[Scheduler] Stopped")
