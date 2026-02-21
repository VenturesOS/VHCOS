"""
VHC Talent OS — Maintenance Routes
Endpoints for maintenance report download, bot status, and manual triggers.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from utils import require_role
from services.maintenance_report_generator import generate_maintenance_report
from services.maintenance_bot import get_bot_status, run_maintenance_cycle, run_diagnostic_self_test
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


@maintenance_router.post("/diagnostic-test")
async def run_diagnostic(user=Depends(require_role("admin"))):
    """Manually trigger the diagnostic self-test."""
    result = await run_diagnostic_self_test()
    return {"status": "ok", **result}


@maintenance_router.get("/failed-captures")
async def get_failed_captures(
    page: int = 1,
    limit: int = 20,
    recovered: Optional[str] = None,
    user=Depends(require_role("admin")),
):
    """Get failed Naukri capture logs for admin review."""
    from typing import Optional as Opt
    query = {"status": "failed"}
    if recovered == "true":
        query["is_recovered"] = True
    elif recovered == "false":
        query["is_recovered"] = False

    skip = (page - 1) * limit
    total = await db.naukri_capture_logs.count_documents(query)
    logs = await db.naukri_capture_logs.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)

    # Stats
    total_failed = await db.naukri_capture_logs.count_documents({"status": "failed"})
    unrecovered = await db.naukri_capture_logs.count_documents({"status": "failed", "is_recovered": False})

    return {
        "logs": logs,
        "total": total,
        "page": page,
        "limit": limit,
        "stats": {"total_failed": total_failed, "unrecovered": unrecovered},
    }


@maintenance_router.post("/failed-captures/{capture_id}/recover")
async def mark_capture_recovered(capture_id: str, user=Depends(require_role("admin"))):
    """Mark a failed capture as recovered (manually added to candidate bank)."""
    result = await db.naukri_capture_logs.update_one(
        {"id": capture_id, "status": "failed"},
        {"$set": {"is_recovered": True, "recovered_at": datetime.now(timezone.utc).isoformat(), "recovered_by": user.get("id", "")}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Capture log not found or already recovered")
    return {"status": "ok", "message": "Marked as recovered"}


@maintenance_router.get("/live-status")
async def live_status(user=Depends(require_role("admin"))):
    """Returns current services, score history (24h), and latest incidents."""
    now = datetime.now(timezone.utc)
    cutoff_24h = (now - timedelta(hours=24)).isoformat()

    # 1. Latest check per service
    latest_services = {}
    async for doc in db.system_health_checks.find(
        {"timestamp": {"$gte": cutoff_24h}}, {"_id": 0}
    ).sort("timestamp", -1):
        sn = doc["service_name"]
        if sn not in latest_services:
            latest_services[sn] = doc
        if len(latest_services) >= 10:
            break

    # 2. Failure counts per service (last 24h)
    failure_counts = {}
    async for doc in db.system_health_checks.find(
        {"timestamp": {"$gte": cutoff_24h}, "status": {"$in": ["warning", "critical"]}},
        {"service_name": 1, "_id": 0},
    ):
        sn = doc["service_name"]
        failure_counts[sn] = failure_counts.get(sn, 0) + 1

    for sn, svc in latest_services.items():
        svc["failure_count_24h"] = failure_counts.get(sn, 0)

    # 3. Health score history — one point per cycle for last 24h
    score_history = []
    all_checks = await db.system_health_checks.find(
        {"timestamp": {"$gte": cutoff_24h}}, {"_id": 0}
    ).sort("timestamp", 1).to_list(5000)

    # Group by timestamp (each cycle shares the same timestamp)
    from collections import defaultdict
    buckets = defaultdict(list)
    for c in all_checks:
        buckets[c["timestamp"]].append(c)

    for ts in sorted(buckets.keys()):
        checks = buckets[ts]
        score = compute_health_score(checks)
        score_history.append({"timestamp": ts, "score": score})

    # 4. Latest 5 incidents (critical/warning checks)
    incidents = await db.system_health_checks.find(
        {"status": {"$in": ["warning", "critical"]}, "timestamp": {"$gte": cutoff_24h}},
        {"_id": 0},
    ).sort("timestamp", -1).limit(5).to_list(5)

    # 5. Current score
    current_score = compute_health_score(list(latest_services.values())) if latest_services else 100

    return {
        "services": list(latest_services.values()),
        "score_history": score_history,
        "current_score": current_score,
        "incidents": incidents,
    }
