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
        cutoff = (now - timedelta(minutes=10)).isoformat()
        stuck = await db.jobs.count_documents({"status": "active", "updated_at": {"$lt": cutoff}})
        recent_errors = await db.system_errors.count_documents({
            "source": "backend", "created_at": {"$gte": (now - timedelta(hours=1)).isoformat()}
        })
        status = "healthy" if stuck == 0 and recent_errors < 5 else "warning" if recent_errors < 20 else "critical"
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
        if mem.percent > 90 or cpu > 90 or disk.percent > 90:
            status = "critical"
        elif mem.percent > 75 or cpu > 75 or disk.percent > 80:
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
        rate = round(((total_apps - failed_pipeline) / max(total_apps, 1)) * 100, 1)
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
                {"error_type": {"$regex": "sync|drift|mismatch", "$options": "i"}},
                {"message": {"$regex": "sync|email.send|notification", "$options": "i"}},
            ],
        })
        status = "healthy" if sync_errors < 3 else "warning" if sync_errors < 10 else "critical"
        return {"status": status, "metrics": {"sync_errors_24h": sync_errors}, "error_details": None}
    except Exception as e:
        return {"status": "warning", "metrics": {}, "error_details": str(e)}


async def check_naukri_capture():
    try:
        now = datetime.now(timezone.utc)
        h24 = (now - timedelta(hours=24)).isoformat()
        total = await db.naukri_capture_logs.count_documents({"timestamp": {"$gte": h24}})
        failed = await db.naukri_capture_logs.count_documents({"timestamp": {"$gte": h24}, "status": "failed"})
        unrecovered = await db.naukri_capture_logs.count_documents({"status": "failed", "is_recovered": False})
        rate = round(((total - failed) / max(total, 1)) * 100, 1) if total > 0 else 100.0
        status = "healthy" if rate >= 95 and unrecovered < 5 else "warning" if rate >= 80 and unrecovered < 20 else "critical"
        return {
            "status": status,
            "metrics": {"total_24h": total, "failed_24h": failed, "success_rate": rate, "unrecovered": unrecovered},
            "error_details": f"{unrecovered} unrecovered failed captures" if unrecovered > 0 else None,
        }
    except Exception as e:
        return {"status": "warning", "metrics": {}, "error_details": str(e)}


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
    """Compute 0-100 health score from check results."""
    if not results:
        return 100
    weights = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    status_scores = {"healthy": 1.0, "warning": 0.5, "critical": 0.0}
    total_weight = sum(weights.get(r.get("priority", "LOW"), 1) for r in results)
    weighted_sum = sum(
        weights.get(r.get("priority", "LOW"), 1) * status_scores.get(r["status"], 0)
        for r in results
    )
    return round((weighted_sum / max(total_weight, 1)) * 100)
