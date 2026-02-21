"""
VHC Talent OS — Maintenance Routes
Endpoints for maintenance report download, bot status, and manual triggers.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from utils import require_role
from services.maintenance_report_generator import generate_maintenance_report
from services.maintenance_bot import get_bot_status, run_maintenance_cycle
from services.health_monitor import run_all_checks, compute_health_score
from services.reliability_layer import get_reliability_summary, is_safe_mode, is_stress_mode
from datetime import datetime, timezone, timedelta
from config import db

maintenance_router = APIRouter(prefix="/api/system-health", tags=["maintenance"])

LIMIT = 1000
DAYS = 7


@maintenance_router.get("/maintenance-report/download")
async def download_maintenance_report(user=Depends(require_role("admin"))):
    """Generate and download the combined maintenance PDF report."""
    pdf_bytes = await generate_maintenance_report()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="VHC_Maintenance_Report_{ts}.pdf"'},
    )


@maintenance_router.get("/maintenance-status")
async def maintenance_status(user=Depends(require_role("admin"))):
    """Get current bot status, health score, and reliability state."""
    bot = get_bot_status()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    latest_checks = {}
    async for doc in db.system_health_checks.find({"timestamp": {"$gte": cutoff}}, {"_id": 0}).sort("timestamp", -1):
        sn = doc["service_name"]
        if sn not in latest_checks:
            latest_checks[sn] = doc
        if len(latest_checks) >= 10:
            break

    score = compute_health_score(list(latest_checks.values())) if latest_checks else 100
    fixes_24h = await db.maintenance_fixes.count_documents({"start_time": {"$gte": cutoff}})
    rel_summary = await get_reliability_summary(days=1)

    return {
        "bot": bot,
        "health_score": score,
        "services": list(latest_checks.values()),
        "fixes_24h": fixes_24h,
        "reliability_events_24h": rel_summary,
        "safe_mode": is_safe_mode(),
        "stress_mode": is_stress_mode(),
    }


@maintenance_router.post("/maintenance-run")
async def manual_maintenance_run(user=Depends(require_role("admin"))):
    """Manually trigger a maintenance cycle."""
    result = await run_maintenance_cycle()
    return {"status": "ok", **result}
