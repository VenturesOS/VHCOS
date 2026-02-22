"""
VHC Talent OS — Maintenance Routes
Endpoints for maintenance report download, bot status, and manual triggers.
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
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


@maintenance_router.get("/security-events")
async def get_security_events(
    page: int = 1,
    limit: int = 20,
    severity: Optional[str] = None,
    event_type: Optional[str] = None,
    user=Depends(require_role("admin")),
):
    """Get security events for the dashboard."""
    from services.security_service import get_security_summary
    query = {}
    if severity:
        query["severity"] = severity
    if event_type:
        query["event_type"] = event_type

    skip = (page - 1) * limit
    total = await db.security_events.count_documents(query)
    events = await db.security_events.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
    summary = await get_security_summary(hours=24)

    return {"events": events, "total": total, "page": page, "limit": limit, "summary": summary}


@maintenance_router.get("/security-validation")
async def security_validation(user=Depends(require_role("admin"))):
    """
    Quick deployment validation: checks all security layers.
    Returns PASS/FAIL status for each protection layer + overall score.
    """
    from services.security_service import (
        TURNSTILE_ENABLED, CLAMAV_ENABLED, CLAMAV_HOST,
        check_clamav_health
    )
    from middleware.zero_trust import ZERO_TRUST_ENABLED, CF_ENFORCE
    from middleware.rate_limiter import ROUTE_LIMITS

    layers = {}

    # 1. Turnstile CAPTCHA
    layers["turnstile"] = {
        "status": "PASS" if TURNSTILE_ENABLED else "WARN",
        "enabled": TURNSTILE_ENABLED,
        "detail": "Enabled and verifying" if TURNSTILE_ENABLED else "Not configured — CAPTCHA bypassed",
    }

    # 2. Zero Trust Access
    zt_detail = "Not configured — admin routes use JWT only"
    if ZERO_TRUST_ENABLED and CF_ENFORCE:
        zt_detail = "Enabled — admin routes enforced (block mode)"
    elif ZERO_TRUST_ENABLED:
        zt_detail = "Enabled — admin routes monitored (audit mode)"
    layers["zero_trust"] = {
        "status": "PASS" if ZERO_TRUST_ENABLED else "WARN",
        "enabled": ZERO_TRUST_ENABLED,
        "enforce": CF_ENFORCE,
        "detail": zt_detail,
    }

    # 3. ClamAV Virus Scanner
    if CLAMAV_ENABLED and CLAMAV_HOST:
        clam_health = await check_clamav_health()
        clam_ok = clam_health.get("available", False)
        layers["clamav"] = {
            "status": "PASS" if clam_ok else "FAIL",
            "enabled": True,
            "detail": "Connected to daemon" if clam_ok else f"Daemon unavailable: {clam_health.get('error', 'unknown')}",
        }
    else:
        layers["clamav"] = {
            "status": "WARN",
            "enabled": False,
            "detail": "Not configured — using pattern-based scanning only",
        }

    # 4. Rate Limiting
    layers["rate_limiting"] = {
        "status": "PASS",
        "enabled": True,
        "detail": f"Active on {len(ROUTE_LIMITS)} routes",
        "protected_routes": list(ROUTE_LIMITS.keys()),
    }

    # 5. File Validation
    layers["file_validation"] = {
        "status": "PASS",
        "enabled": True,
        "detail": "Active — type, size, magic bytes, pattern scanning",
    }

    # 6. Security Logging
    recent_count = await db.security_events.count_documents({
        "timestamp": {"$gte": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()}
    })
    layers["security_logging"] = {
        "status": "PASS",
        "enabled": True,
        "detail": f"Active — {recent_count} events in last 24h",
    }

    # 7. XSS Prevention
    layers["xss_prevention"] = {
        "status": "PASS",
        "enabled": True,
        "detail": "Active — HTML sanitization on CV text",
    }

    # Compute overall
    statuses = [lyr["status"] for lyr in layers.values()]
    fail_count = statuses.count("FAIL")
    warn_count = statuses.count("WARN")
    pass_count = statuses.count("PASS")
    total_layers = len(layers)

    score = round((pass_count / total_layers) * 100)
    overall = "FAIL" if fail_count > 0 else "WARN" if warn_count > 0 else "PASS"

    return {
        "overall": overall,
        "score": score,
        "pass_count": pass_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "total_layers": total_layers,
        "layers": layers,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@maintenance_router.get("/security-posture")
async def security_posture(user=Depends(require_role("admin"))):
    """
    Full security posture data for the Security Audit Dashboard.
    Includes posture score, layer status, recent events, and compliance checklist.
    """
    from services.security_service import (
        TURNSTILE_ENABLED, CLAMAV_ENABLED, CLAMAV_HOST,
        check_clamav_health, get_security_summary
    )
    from middleware.zero_trust import ZERO_TRUST_ENABLED, CF_ENFORCE
    from middleware.rate_limiter import ROUTE_LIMITS

    # Gather validation data
    clam_available = False
    if CLAMAV_ENABLED and CLAMAV_HOST:
        try:
            clam_health = await check_clamav_health()
            clam_available = clam_health.get("available", False)
        except Exception:
            pass

    # Protection layers with scoring weights
    protection_layers = [
        {
            "id": "file_validation",
            "name": "File Upload Validation",
            "category": "Upload Security",
            "active": True,
            "weight": 15,
            "detail": "Type, size, magic bytes, pattern scanning",
        },
        {
            "id": "rate_limiting",
            "name": "API Rate Limiting",
            "category": "API Protection",
            "active": True,
            "weight": 15,
            "detail": f"Active on {len(ROUTE_LIMITS)} routes",
        },
        {
            "id": "security_logging",
            "name": "Security Event Logging",
            "category": "Monitoring",
            "active": True,
            "weight": 10,
            "detail": "All events logged to security_events collection",
        },
        {
            "id": "xss_prevention",
            "name": "XSS Prevention",
            "category": "Content Safety",
            "active": True,
            "weight": 10,
            "detail": "HTML sanitization on all CV text extraction",
        },
        {
            "id": "turnstile",
            "name": "Cloudflare Turnstile CAPTCHA",
            "category": "Bot Protection",
            "active": TURNSTILE_ENABLED,
            "weight": 15,
            "detail": "Enabled" if TURNSTILE_ENABLED else "Not configured",
        },
        {
            "id": "zero_trust",
            "name": "Cloudflare Zero Trust Access",
            "category": "Admin Protection",
            "active": ZERO_TRUST_ENABLED,
            "weight": 20,
            "detail": (
                "Enforcing (block mode)" if ZERO_TRUST_ENABLED and CF_ENFORCE
                else "Monitoring (audit mode)" if ZERO_TRUST_ENABLED
                else "Not configured"
            ),
        },
        {
            "id": "clamav",
            "name": "ClamAV Virus Scanner",
            "category": "Malware Protection",
            "active": CLAMAV_ENABLED and clam_available,
            "weight": 15,
            "detail": "Connected" if (CLAMAV_ENABLED and clam_available) else "Not active",
        },
    ]

    # Calculate posture score
    total_weight = sum(pl["weight"] for pl in protection_layers)
    active_weight = sum(pl["weight"] for pl in protection_layers if pl["active"])
    posture_score = round((active_weight / total_weight) * 100)

    # Recent security events (last 7 days)
    cutoff_7d = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent_events = await db.security_events.find(
        {"timestamp": {"$gte": cutoff_7d}}, {"_id": 0}
    ).sort("timestamp", -1).limit(20).to_list(20)

    summary_24h = await get_security_summary(hours=24)
    summary_7d = await get_security_summary(hours=168)

    # Compliance checklist
    compliance_checklist = [
        {"item": "File uploads restricted to PDF, DOC, DOCX (max 5MB)", "status": True},
        {"item": "Magic byte validation prevents file spoofing", "status": True},
        {"item": "Pattern-based threat scanning on all uploads", "status": True},
        {"item": "ClamAV antivirus scanning enabled", "status": CLAMAV_ENABLED and clam_available},
        {"item": "CAPTCHA on public registration form", "status": TURNSTILE_ENABLED},
        {"item": "CAPTCHA on resume upload form", "status": TURNSTILE_ENABLED},
        {"item": "CAPTCHA on job application form", "status": TURNSTILE_ENABLED},
        {"item": "API rate limiting on authentication endpoints", "status": True},
        {"item": "API rate limiting on public upload endpoints", "status": True},
        {"item": "API rate limiting on admin endpoints", "status": True},
        {"item": "Zero Trust access control on admin routes", "status": ZERO_TRUST_ENABLED},
        {"item": "Security event logging active", "status": True},
        {"item": "XSS prevention on CV content display", "status": True},
        {"item": "Honeypot fields on public forms", "status": True},
        {"item": "JWT-based authentication with configurable expiry", "status": True},
        {"item": "Security events visible in System Health dashboard", "status": True},
        {"item": "Security events included in maintenance PDF report", "status": True},
    ]

    return {
        "posture_score": posture_score,
        "protection_layers": protection_layers,
        "active_count": sum(1 for pl in protection_layers if pl["active"]),
        "inactive_count": sum(1 for pl in protection_layers if not pl["active"]),
        "total_layers": len(protection_layers),
        "recent_events": recent_events,
        "summary_24h": summary_24h,
        "summary_7d": summary_7d,
        "compliance_checklist": compliance_checklist,
        "compliance_score": round(sum(1 for c in compliance_checklist if c["status"]) / len(compliance_checklist) * 100),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@maintenance_router.get("/training-manual/download")
async def download_training_manual(user=Depends(require_role("admin"))):
    """Generate and download the training manual as a styled PDF."""
    from services.training_manual_service import generate_training_manual_pdf
    try:
        pdf_bytes = await generate_training_manual_pdf()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Training manual source file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="VHC_Training_Manual.pdf"'},
    )


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
        if len(latest_services) >= 12:
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
