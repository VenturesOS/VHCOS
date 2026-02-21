"""
VHC Talent OS — Maintenance Bot
Background worker that runs health checks every 5 minutes,
triggers auto-healing, and manages the reliability layer.
"""
import logging
import asyncio
from datetime import datetime, timezone
from services.health_monitor import run_all_checks, compute_health_score
from services.auto_healer import attempt_fix
from services.reliability_layer import (
    set_stress_mode, activate_safe_mode, deactivate_safe_mode, is_safe_mode,
    process_buffered_requests,
)

logger = logging.getLogger(__name__)

_bot_running = False
_last_run = None
_last_score = None


def get_bot_status():
    return {
        "running": _bot_running,
        "last_run": _last_run,
        "last_health_score": _last_score,
    }


async def run_maintenance_cycle():
    """Single maintenance cycle: check → heal → manage reliability."""
    global _last_run, _last_score

    results = await run_all_checks()
    score = compute_health_score(results)
    _last_score = score
    _last_run = datetime.now(timezone.utc).isoformat()

    critical = [r for r in results if r["status"] == "critical"]
    warnings = [r for r in results if r["status"] == "warning"]

    # Stress mode: pause LOW tasks if score drops below 50
    await set_stress_mode(score < 50)

    # Safe mode: activate if multiple critical services
    if len(critical) >= 3 and not is_safe_mode():
        await activate_safe_mode(f"Health score {score}, {len(critical)} critical services")
    elif len(critical) < 2 and is_safe_mode():
        await deactivate_safe_mode()

    # Auto-heal critical and warning services
    for check in critical + warnings:
        issue = check.get("error_details") or f"{check['service_name']} status: {check['status']}"
        try:
            await attempt_fix(check["service_name"], issue)
        except Exception as e:
            logger.error(f"[BOT] Auto-heal failed for {check['service_name']}: {e}")

    # Drain buffered requests if system is healthy
    if score >= 70:
        try:
            await process_buffered_requests(limit=20)
        except Exception:
            pass

    logger.info(f"[MAINTENANCE BOT] Cycle complete — Score: {score}, Critical: {len(critical)}, Warnings: {len(warnings)}")
    return {"score": score, "critical": len(critical), "warnings": len(warnings)}


async def _bot_loop():
    """Continuous background loop. Runs every 5 minutes."""
    global _bot_running
    _bot_running = True
    logger.info("[MAINTENANCE BOT] Started background loop (5-min interval)")
    while _bot_running:
        try:
            await run_maintenance_cycle()
        except Exception as e:
            logger.error(f"[MAINTENANCE BOT] Cycle error: {e}")
        await asyncio.sleep(300)  # 5 minutes


def start_bot():
    """Launch the bot as a non-blocking background task."""
    global _bot_running
    if _bot_running:
        return
    loop = asyncio.get_event_loop()
    loop.create_task(_bot_loop())
    logger.info("[MAINTENANCE BOT] Background task created")


def stop_bot():
    global _bot_running
    _bot_running = False
    logger.info("[MAINTENANCE BOT] Stopped")
