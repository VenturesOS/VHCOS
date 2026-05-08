"""
Health check and diagnostics endpoints.
Extracted from server.py for modularity.
"""
import os
import logging
from fastapi import APIRouter
from config import db, db_name, client, R2_ENABLED, r2_client, R2_BUCKET_NAME
import config as config_module

logger = logging.getLogger(__name__)

health_router = APIRouter(tags=["Health"])

# Reference to _route_imports_failed — set from server.py after import
_route_imports_failed: list = []


def set_route_import_failures(failures: list):
    global _route_imports_failed
    _route_imports_failed = failures


@health_router.get("/api/health")
@health_router.get("/health")
async def health_check():
    """E-06: Deep health check with actual MongoDB/Redis ping."""
    checks = {}

    # MongoDB ping
    try:
        from config import db
        result = await db.command("ping")
        checks["mongodb"] = "ok" if result.get("ok") == 1.0 else "degraded"
    except Exception as e:
        checks["mongodb"] = f"error: {e}"

    # Redis ping
    try:
        from services.redis_client import get_redis
        r = get_redis()
        if r:
            r.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "not_configured"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    status = "healthy" if checks.get("mongodb") == "ok" else "degraded"
    return {
        "status": status,
        "service": "VHC Talent OS",
        "checks": checks,
        "import_failures": len(_route_imports_failed),
    }


@health_router.get("/api/health/diagnostics")
async def health_diagnostics():
    """Production diagnostics — shows masked credentials and config sources."""
    key = os.environ.get("OPENAI_API_KEY", "")
    override_key = ""
    try:
        from mongo_production_override import OPENAI_API_KEY as _ok
        override_key = _ok or ""
    except Exception:
        pass
    return {
        "env_openai_key": f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "(empty/short)",
        "override_openai_key": f"{override_key[:8]}...{override_key[-4:]}" if len(override_key) > 12 else "(empty/short)",
        "keys_match": key == override_key if key and override_key else None,
        "mongo_override_active": getattr(config_module, '_override_active', 'unknown'),
        "db_name": db_name,
        "import_failures": len(_route_imports_failed),
    }


@health_router.get("/api/health/aws-readiness")
async def aws_readiness_check():
    """One-click AWS deployment readiness check.
    Validates every external dependency and config requirement.
    Returns pass/fail per service with actionable messages.
    """
    checks = {}
    all_pass = True

    # 1. MongoDB
    try:
        await client.admin.command("ping")
        user_count = await db.users.count_documents({})
        checks["mongodb"] = {"status": "pass", "detail": f"Connected. {user_count} users in '{db_name}'."}
    except RuntimeError:
        try:
            from config import mongodb_uri, _client_opts, initialize_db
            initialize_db()
            await client.admin.command("ping")
            user_count = await db.users.count_documents({})
            checks["mongodb"] = {"status": "pass", "detail": f"Connected (late init). {user_count} users in '{db_name}'."}
        except Exception as e2:
            checks["mongodb"] = {"status": "FAIL", "detail": f"DB proxy not initialized and direct connect failed: {str(e2)[:200]}"}
            all_pass = False
    except Exception as e:
        checks["mongodb"] = {"status": "FAIL", "detail": str(e)[:200]}
        all_pass = False

    # 2. Cloudflare R2 Storage
    if R2_ENABLED:
        try:
            r2_client.head_bucket(Bucket=R2_BUCKET_NAME)
            checks["r2_storage"] = {"status": "pass", "detail": f"Connected. Bucket: {R2_BUCKET_NAME}"}
        except Exception as e:
            checks["r2_storage"] = {"status": "FAIL", "detail": f"Bucket check failed: {str(e)[:200]}"}
            all_pass = False
    else:
        r2_vars = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"]
        missing = [v for v in r2_vars if not os.environ.get(v)]
        checks["r2_storage"] = {"status": "FAIL", "detail": f"Not configured. Missing env vars: {', '.join(missing)}"}
        all_pass = False

    # 3. OpenAI API Key
    oai_key = os.environ.get("OPENAI_API_KEY", "")
    if oai_key and len(oai_key) > 20:
        checks["openai"] = {"status": "pass", "detail": f"Key set ({oai_key[:8]}...{oai_key[-4:]}, len={len(oai_key)})"}
    else:
        checks["openai"] = {"status": "FAIL", "detail": "OPENAI_API_KEY missing or too short. AI features will not work."}
        all_pass = False

    # 4. Emergent LLM (optional)
    emergent_key = os.environ.get("EMERGENT_LLM_KEY", "")
    try:
        from emergentintegrations.llm.chat import LlmChat
        if emergent_key:
            checks["emergent_llm"] = {"status": "pass", "detail": "Library installed + key set. Using Emergent LLM."}
        else:
            checks["emergent_llm"] = {"status": "skip", "detail": "Library installed but key not set. Using OpenAI fallback."}
    except ImportError:
        if emergent_key:
            checks["emergent_llm"] = {"status": "warn", "detail": "Key set but library not installed. Using OpenAI fallback."}
        else:
            checks["emergent_llm"] = {"status": "skip", "detail": "Not installed. Using direct OpenAI API (this is fine)."}

    # 5. Resend Email
    resend_key = os.environ.get("RESEND_API_KEY", "")
    if resend_key and resend_key != "re_placeholder_key" and len(resend_key) > 10:
        checks["email_resend"] = {"status": "pass", "detail": f"Key set ({resend_key[:6]}...). Sender: {os.environ.get('SENDER_EMAIL', '(not set)')}"}
    else:
        checks["email_resend"] = {"status": "FAIL", "detail": "RESEND_API_KEY missing or placeholder. Emails will not send."}
        all_pass = False

    # 6. Turnstile CAPTCHA
    ts_key = os.environ.get("TURNSTILE_SECRET_KEY", "")
    if ts_key and ts_key.lower() not in ("disabled", "false", "none", "skip", ""):
        checks["turnstile"] = {"status": "pass", "detail": "Enabled. Ensure your domain is registered on Cloudflare Turnstile."}
    elif ts_key.lower() in ("disabled", "false", "none", "skip"):
        checks["turnstile"] = {"status": "warn", "detail": "Explicitly DISABLED. Public apply endpoints have no CAPTCHA protection."}
    else:
        checks["turnstile"] = {"status": "warn", "detail": "Not configured. CAPTCHA is OFF — set TURNSTILE_SECRET_KEY to enable."}

    # 7. JWT Secret
    jwt_key = os.environ.get("JWT_SECRET_KEY", "")
    if jwt_key and jwt_key != "vhc-secret-key-CHANGE-IN-PRODUCTION" and len(jwt_key) > 16:
        checks["jwt_secret"] = {"status": "pass", "detail": "Custom secret set."}
    else:
        checks["jwt_secret"] = {"status": "FAIL", "detail": "Using default/weak JWT secret. Set JWT_SECRET_KEY to a strong random value."}
        all_pass = False

    # 8. SITE_URL
    site_url = os.environ.get("SITE_URL", "")
    if site_url:
        checks["site_url"] = {"status": "pass", "detail": f"Set to: {site_url}"}
    else:
        checks["site_url"] = {"status": "warn", "detail": "Not set. Defaulting to https://ventureshrd.com. Set SITE_URL for custom domains."}

    # 9. CORS
    cors = os.environ.get("CORS_ORIGINS", "")
    if cors:
        checks["cors"] = {"status": "pass", "detail": f"Origins: {cors[:100]}"}
    else:
        checks["cors"] = {"status": "warn", "detail": "CORS_ORIGINS not set. Only hardcoded origins will be allowed."}

    # 10. Route imports
    checks["route_imports"] = {
        "status": "pass" if not _route_imports_failed else "FAIL",
        "detail": f"{len(_route_imports_failed)} failures" + (f": {_route_imports_failed[:3]}" if _route_imports_failed else ""),
    }
    if _route_imports_failed:
        all_pass = False

    # 11. Redis/Upstash (optional)
    redis_url = os.environ.get("UPSTASH_REDIS_REST_URL", "")
    if redis_url:
        checks["redis_cache"] = {"status": "pass", "detail": "Upstash Redis configured."}
    else:
        checks["redis_cache"] = {"status": "skip", "detail": "Not configured. Using in-memory cache (fine for single-worker)."}

    passed = sum(1 for c in checks.values() if c["status"] == "pass")
    failed = sum(1 for c in checks.values() if c["status"] == "FAIL")
    warned = sum(1 for c in checks.values() if c["status"] == "warn")
    skipped = sum(1 for c in checks.values() if c["status"] == "skip")

    return {
        "ready": all_pass,
        "summary": f"{passed} pass, {failed} fail, {warned} warn, {skipped} skip",
        "checks": checks,
    }


@health_router.get("/api/health/incident-analysis")
async def incident_analysis():
    """
    Deep diagnostics for investigating downtime/performance incidents.
    Shows MongoDB connection pool stats, recent capture activity, error patterns.
    
    Use this to diagnose why the system was down or slow.
    """
    from datetime import datetime, timezone, timedelta
    import psutil
    
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": {},
        "mongodb": {},
        "recent_activity": {},
        "error_patterns": {},
    }
    
    # System metrics
    try:
        result["system"] = {
            "cpu_percent": psutil.cpu_percent(interval=0.5),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_available_mb": round(psutil.virtual_memory().available / 1024 / 1024),
            "disk_percent": psutil.disk_usage('/').percent,
        }
    except Exception as e:
        result["system"]["error"] = str(e)
    
    # MongoDB connection pool stats
    try:
        # Get server status for connection info
        server_status = await client.admin.command("serverStatus")
        connections = server_status.get("connections", {})
        result["mongodb"]["connections"] = {
            "current": connections.get("current", "N/A"),
            "available": connections.get("available", "N/A"),
            "total_created": connections.get("totalCreated", "N/A"),
        }
        
        # Pool configuration from config
        from config import _client_opts
        result["mongodb"]["pool_config"] = {
            "maxPoolSize": _client_opts.get("maxPoolSize"),
            "minPoolSize": _client_opts.get("minPoolSize"),
            "serverSelectionTimeoutMS": _client_opts.get("serverSelectionTimeoutMS"),
            "connectTimeoutMS": _client_opts.get("connectTimeoutMS"),
        }
    except Exception as e:
        result["mongodb"]["error"] = str(e)
    
    # Recent capture activity (last 24 hours)
    try:
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(hours=24)
        
        # Count captures by status
        pipeline = [
            {"$match": {"timestamp": {"$gte": yesterday.isoformat()}}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        capture_stats = await db.naukri_capture_logs.aggregate(pipeline).to_list(20)
        result["recent_activity"]["captures_24h"] = {s["_id"]: s["count"] for s in capture_stats}
        
        # Captures per hour (last 6 hours)
        hourly_pipeline = [
            {"$match": {"timestamp": {"$gte": (now - timedelta(hours=6)).isoformat()}}},
            {"$group": {
                "_id": {"$substr": ["$timestamp", 0, 13]},  # Group by hour
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": -1}},
            {"$limit": 6},
        ]
        hourly_stats = await db.naukri_capture_logs.aggregate(hourly_pipeline).to_list(10)
        result["recent_activity"]["captures_hourly"] = {s["_id"]: s["count"] for s in hourly_stats}
        
        # Total extension captures today
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        result["recent_activity"]["extension_captures_today"] = await db.candidate_bank.count_documents({
            "source": {"$regex": "_extension$"},
            "created_at": {"$gte": today_start.isoformat()}
        })
        
        # Attendance check-ins today (IST = UTC+5:30)
        ist_offset = timedelta(hours=5, minutes=30)
        ist_now = now + ist_offset
        ist_today = ist_now.strftime("%Y-%m-%d")
        result["recent_activity"]["attendance_checkins_today"] = await db.attendance_records.count_documents({
            "date": ist_today, "check_in": {"$ne": None}
        })
        
    except Exception as e:
        result["recent_activity"]["error"] = str(e)
    
    # Error patterns (last 24 hours)
    try:
        error_pipeline = [
            {"$match": {
                "timestamp": {"$gte": yesterday.isoformat()},
                "status": "failed"
            }},
            {"$group": {"_id": "$failure_reason", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]
        error_stats = await db.naukri_capture_logs.aggregate(error_pipeline).to_list(10)
        result["error_patterns"]["capture_failures"] = [
            {"reason": s["_id"][:100] if s["_id"] else "unknown", "count": s["count"]} 
            for s in error_stats
        ]
    except Exception as e:
        result["error_patterns"]["error"] = str(e)
    
    return result
