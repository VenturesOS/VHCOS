"""
VHC Talent OS — Health Monitor Service
Runs health checks against all system components and stores results.
"""
import time
import psutil
import logging
from datetime import datetime, timezone, timedelta
from config import db, client

logger = logging.getLogger(__name__)

SERVICES = [
    {"name": "mongodb", "priority": "HIGH"},
    {"name": "api_server", "priority": "HIGH"},
    {"name": "background_workers", "priority": "MEDIUM"},
    {"name": "queue_system", "priority": "MEDIUM"},
    {"name": "system_resources", "priority": "LOW"},
    {"name": "automation_pipeline", "priority": "MEDIUM"},
    {"name": "ai_services", "priority": "MEDIUM"},
    {"name": "data_sync", "priority": "LOW"},
    {"name": "naukri_capture", "priority": "MEDIUM"},
    {"name": "security", "priority": "HIGH"},
    {"name": "virus_scanner", "priority": "MEDIUM"},
]


async def check_mongodb():
    start = time.time()
    try:
        await client.admin.command("ping")
        latency = round((time.time() - start) * 1000, 1)
        status = "healthy" if latency < 500 else "warning" if latency < 2000 else "critical"
        return {"status": status, "metrics": {"latency_ms": latency}, "error_details": None}
    except Exception as e:
        return {"status": "critical", "metrics": {"latency_ms": -1}, "error_details": str(e)}


async def check_api_server():
    start = time.time()
    try:
        count = await db.users.count_documents({})
        latency = round((time.time() - start) * 1000, 1)
        status = "healthy" if latency < 1000 else "warning"
        return {"status": status, "metrics": {"latency_ms": latency, "user_count": count}, "error_details": None}
    except Exception as e:
        return {"status": "critical", "metrics": {}, "error_details": str(e)}


async def check_background_workers():
    try:
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(minutes=30)).isoformat()
        # Only check "processing" jobs that haven't updated — "active" is a normal steady state
        stuck = await db.jobs.count_documents({"status": "processing", "updated_at": {"$lt": cutoff}})
        recent_errors = await db.system_errors.count_documents({
            "source": "backend", "created_at": {"$gte": (now - timedelta(hours=1)).isoformat()}
        })
        status = "healthy" if stuck == 0 and recent_errors < 10 else "warning" if recent_errors < 30 else "critical"
        return {"status": status, "metrics": {"stuck_jobs": stuck, "recent_errors_1h": recent_errors}, "error_details": None}
    except Exception as e:
        return {"status": "warning", "metrics": {}, "error_details": str(e)}


async def check_queue_system():
    try:
        pending = await db.job_queue.count_documents({"status": "pending"}) if "job_queue" in await db.list_collection_names() else 0
        failed = await db.job_queue.count_documents({"status": "failed"}) if "job_queue" in await db.list_collection_names() else 0
        status = "healthy" if pending < 50 and failed < 10 else "warning" if pending < 200 else "critical"
        return {"status": status, "metrics": {"pending": pending, "failed": failed}, "error_details": None}
    except Exception as e:
        return {"status": "warning", "metrics": {"pending": 0, "failed": 0}, "error_details": str(e)}


async def check_system_resources():
    try:
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.5)
        disk = psutil.disk_usage("/")
        status = "healthy"
        if mem.percent > 95 or cpu > 95 or disk.percent > 95:
            status = "critical"
        elif mem.percent > 85 or cpu > 85 or disk.percent > 90:
            status = "warning"
        return {
            "status": status,
            "metrics": {
                "memory_percent": round(mem.percent, 1),
                "memory_used_mb": round(mem.used / 1048576),
                "memory_total_mb": round(mem.total / 1048576),
                "cpu_percent": round(cpu, 1),
                "disk_percent": round(disk.percent, 1),
            },
            "error_details": None,
        }
    except Exception as e:
        return {"status": "warning", "metrics": {}, "error_details": str(e)}


async def check_automation_pipeline():
    try:
        now = datetime.now(timezone.utc)
        h24 = (now - timedelta(hours=24)).isoformat()
        total_apps = await db.applications.count_documents({"applied_at": {"$gte": h24}})
        failed_pipeline = await db.system_errors.count_documents({
            "source": "backend", "error_type": {"$regex": "pipeline|automation", "$options": "i"},
            "created_at": {"$gte": h24},
        })
        if total_apps == 0:
            status = "healthy"
            rate = 100.0
        else:
            rate = round(((total_apps - failed_pipeline) / total_apps) * 100, 1)
            status = "healthy" if rate > 95 else "warning" if rate > 80 else "critical"
        return {"status": status, "metrics": {"success_rate": rate, "total_24h": total_apps, "failures_24h": failed_pipeline}, "error_details": None}
    except Exception as e:
        return {"status": "warning", "metrics": {}, "error_details": str(e)}


async def check_ai_services():
    try:
        now = datetime.now(timezone.utc)
        h1 = (now - timedelta(hours=1)).isoformat()
        ai_errors = await db.system_errors.count_documents({
            "created_at": {"$gte": h1},
            "$or": [
                {"error_type": {"$regex": "openai|ai|llm|gpt", "$options": "i"}},
                {"message": {"$regex": "openai|timeout|rate.limit", "$options": "i"}},
            ],
        })
        status = "healthy" if ai_errors == 0 else "warning" if ai_errors < 5 else "critical"
        return {"status": status, "metrics": {"ai_errors_1h": ai_errors}, "error_details": None}
    except Exception as e:
        return {"status": "warning", "metrics": {}, "error_details": str(e)}


async def check_data_sync():
    try:
        now = datetime.now(timezone.utc)
        h24 = (now - timedelta(hours=24)).isoformat()
        sync_errors = await db.system_errors.count_documents({
            "created_at": {"$gte": h24},
            "$or": [
                {"error_type": {"$regex": "^(sync_fail|data_drift|data_sync_error)$", "$options": "i"}},
                {"message": {"$regex": "sync.*(fail|error|timeout)|data.*inconsistenc|data.*drift", "$options": "i"}},
            ],
        })
        status = "healthy" if sync_errors < 5 else "warning" if sync_errors < 20 else "critical"
        return {"status": status, "metrics": {"sync_errors_24h": sync_errors}, "error_details": None}
    except Exception as e:
        return {"status": "warning", "metrics": {}, "error_details": str(e)}


async def check_naukri_capture():
    try:
        now = datetime.now(timezone.utc)
        h24 = (now - timedelta(hours=24)).isoformat()
        total = await db.naukri_capture_logs.count_documents({"timestamp": {"$gte": h24}})
        failed = await db.naukri_capture_logs.count_documents({"timestamp": {"$gte": h24}, "status": "failed"})
        # FIX (Phase 52, 2026-05-07 maintenance review): the "unrecovered"
        # query previously had no time bound, so EVERY historical failed
        # capture from months ago that had `is_recovered=false` (or missing)
        # counted as "unrecovered". Result: 252 false-alarm auto-fix events
        # in the 7-day report ("15 unrecovered failed captures, no specific
        # fix available") even though the same report's "Failed Captures"
        # section showed 0 actual unrecovered captures in the period.
        # Bound the unrecovered count to the 24h window AND match $ne True
        # so docs that lack the field at all aren't auto-counted as failures.
        unrecovered = await db.naukri_capture_logs.count_documents({
            "timestamp": {"$gte": h24},
            "status": "failed",
            "is_recovered": {"$ne": True},
        })
        rate = round(((total - failed) / max(total, 1)) * 100, 1) if total > 0 else 100.0
        status = "healthy" if rate >= 95 and unrecovered < 5 else "warning" if rate >= 80 and unrecovered < 20 else "critical"
        return {
            "status": status,
            "metrics": {"total_24h": total, "failed_24h": failed, "success_rate": rate, "unrecovered": unrecovered},
            "error_details": f"{unrecovered} unrecovered failed captures (24h)" if unrecovered > 0 else None,
        }
    except Exception as e:
        return {"status": "warning", "metrics": {}, "error_details": str(e)}


async def check_security():
    try:
        now = datetime.now(timezone.utc)
        h24 = (now - timedelta(hours=24)).isoformat()
        total = await db.security_events.count_documents({"timestamp": {"$gte": h24}})
        critical = await db.security_events.count_documents({"timestamp": {"$gte": h24}, "severity": "CRITICAL"})
        high = await db.security_events.count_documents({"timestamp": {"$gte": h24}, "severity": "HIGH"})
        status = "healthy" if critical == 0 and high < 3 else "warning" if critical < 3 and high < 10 else "critical"
        return {
            "status": status,
            "metrics": {"events_24h": total, "critical_24h": critical, "high_24h": high},
            "error_details": f"{critical} critical, {high} high security events" if critical + high > 0 else None,
        }
    except Exception as e:
        return {"status": "healthy", "metrics": {}, "error_details": str(e)}


async def check_virus_scanner():
    """Check ClamAV virus scanner availability."""
    try:
        from services.security_service import check_clamav_health, CLAMAV_ENABLED
        if not CLAMAV_ENABLED:
            return {
                "status": "healthy",
                "metrics": {"enabled": False, "mode": "pattern_scan_only"},
                "error_details": "ClamAV disabled — using pattern-based scanning"
            }
        health = await check_clamav_health()
        if health["available"]:
            return {"status": "healthy", "metrics": {"enabled": True, "daemon": "connected"}, "error_details": None}
        else:
            return {
                "status": "warning",
                "metrics": {"enabled": True, "daemon": "unavailable"},
                "error_details": health.get("error", "ClamAV daemon not reachable")
            }
    except Exception as e:
        return {"status": "warning", "metrics": {"enabled": False}, "error_details": str(e)}


CHECK_MAP = {
    "mongodb": check_mongodb,
    "api_server": check_api_server,
    "background_workers": check_background_workers,
    "queue_system": check_queue_system,
    "system_resources": check_system_resources,
    "automation_pipeline": check_automation_pipeline,
    "ai_services": check_ai_services,
    "data_sync": check_data_sync,
    "naukri_capture": check_naukri_capture,
    "security": check_security,
    "virus_scanner": check_virus_scanner,
}


async def run_all_checks():
    """Run all health checks and store results. Returns list of check results."""
    results = []
    now = datetime.now(timezone.utc).isoformat()
    for svc in SERVICES:
        name = svc["name"]
        fn = CHECK_MAP.get(name)
        if not fn:
            continue
        try:
            result = await fn()
        except Exception as e:
            result = {"status": "critical", "metrics": {}, "error_details": str(e)}
        doc = {
            "service_name": name,
            "priority": svc["priority"],
            "status": result["status"],
            "timestamp": now,
            "metrics": result.get("metrics", {}),
            "error_details": result.get("error_details"),
        }
        results.append(doc)
    if results:
        await db.system_health_checks.insert_many(results)
    return results


def compute_health_score(results):
    """Compute 0-100 health score from check results. Penalizes inactive security layers."""
    if not results:
        return 100
    weights = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    status_scores = {"healthy": 1.0, "warning": 0.5, "critical": 0.0}
    total_weight = sum(weights.get(r.get("priority", "LOW"), 1) for r in results)
    weighted_sum = sum(
        weights.get(r.get("priority", "LOW"), 1) * status_scores.get(r["status"], 0)
        for r in results
    )
    base_score = round((weighted_sum / max(total_weight, 1)) * 100)

    # Security layer penalties: check if optional security services are inactive
    try:
        from services.security_service import TURNSTILE_ENABLED, CLAMAV_ENABLED
        from middleware.zero_trust import ZERO_TRUST_ENABLED
        penalty = 0
        if not TURNSTILE_ENABLED:
            penalty += 2
        if not ZERO_TRUST_ENABLED:
            penalty += 3
        if not CLAMAV_ENABLED:
            penalty += 2
        base_score = max(0, base_score - penalty)
    except Exception:
        pass

    return base_score
