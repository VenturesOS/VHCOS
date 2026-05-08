"""
VHC Talent OS — Compliance Routes
Endpoints for compliance dashboard, audit logs, consent actions, cookie consent.
All dashboard endpoints are admin-protected.
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from typing import Optional
from datetime import datetime, timezone
from config import db
from utils import get_current_user, require_role
from services.compliance_service import (
    log_consent_audit,
    get_consent_health,
    get_data_risk_alerts,
    CONSENT_VERSION,
)

compliance_router = APIRouter(prefix="/api/compliance", tags=["compliance"])

# NOTE: Compliance indexes are created in services/lifecycle.py run_deferred_init()
# Do NOT add a router-level startup event — it fires before DB is initialized.


@compliance_router.get("/dashboard-stats")
async def compliance_dashboard_stats(user=Depends(require_role("admin"))):
    health = await get_consent_health()
    alerts = await get_data_risk_alerts()
    total_audit = await db.consent_audit_logs.count_documents({})
    pending_gov = await db.data_governance_requests.count_documents({"status": "pending"})
    return {
        "consent_health": health,
        "data_risk_alerts": alerts,
        "total_audit_entries": total_audit,
        "pending_governance_requests": pending_gov,
        "consent_version": CONSENT_VERSION,
    }


@compliance_router.get("/audit-logs")
async def get_audit_logs(
    action: Optional[str] = None,
    source: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    user=Depends(require_role("admin")),
):
    query = {}
    if action:
        query["action"] = action
    if source:
        query["source"] = source
    if from_date or to_date:
        date_filter = {}
        if from_date:
            date_filter["$gte"] = from_date
        if to_date:
            date_filter["$lte"] = to_date
        query["timestamp"] = date_filter

    skip = (page - 1) * limit
    total = await db.consent_audit_logs.count_documents(query)
    logs = await db.consent_audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
    return {"logs": logs, "total": total, "page": page, "limit": limit}


@compliance_router.get("/governance-requests")
async def get_governance_requests(
    status: Optional[str] = None,
    request_type: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    user=Depends(require_role("admin")),
):
    query = {}
    if status:
        query["status"] = status
    if request_type:
        query["request_type"] = request_type

    skip = (page - 1) * limit
    total = await db.data_governance_requests.count_documents(query)
    requests = await db.data_governance_requests.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"requests": requests, "total": total, "page": page, "limit": limit}


@compliance_router.post("/cookie-consent")
async def log_cookie_consent(request: Request):
    """Public endpoint — logs cookie consent from any visitor."""
    body = await request.json()
    client_ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    entry = {
        "preferences": body.get("preferences", {}),
        "action": body.get("action", "unknown"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ip_address": client_ip,
        "user_agent": request.headers.get("User-Agent", ""),
        "consent_version": CONSENT_VERSION,
    }
    await db.cookie_consent_logs.insert_one(entry)
    return {"status": "ok"}


@compliance_router.get("/consent-version")
async def get_consent_version():
    """Public endpoint — returns current consent version for frontend forms."""
    return {"consent_version": CONSENT_VERSION}
