"""
VHC Talent OS — Compliance Service
Handles consent audit logging, compliance alerts, and dashboard data.
"""
import uuid
from datetime import datetime, timezone, timedelta
from config import db

CONSENT_VERSION = "v1.0_2026"


async def log_consent_audit(
    candidate_id: str,
    action: str,
    source: str,
    ip_address: str = "unknown",
    user_agent: str = "",
    consent_version: str = CONSENT_VERSION,
    metadata: dict = None,
):
    """Log a consent action to the audit trail."""
    entry = {
        "id": str(uuid.uuid4()),
        "candidate_id": candidate_id,
        "action": action,
        "consent_version": consent_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ip_address": ip_address,
        "user_agent": user_agent,
        "source": source,
        "metadata": metadata or {},
    }
    await db.consent_audit_logs.insert_one(entry)
    return entry["id"]


async def log_compliance_alert(severity: str, alert_type: str, title: str, description: str, metadata: dict = None):
    """Create a compliance alert."""
    entry = {
        "id": str(uuid.uuid4()),
        "severity": severity,
        "alert_type": alert_type,
        "title": title,
        "description": description,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resolved_at": None,
        "metadata": metadata or {},
    }
    await db.compliance_alerts.insert_one(entry)
    return entry["id"]


async def get_consent_health():
    """Get consent health overview for dashboard."""
    total_profiles = await db.candidate_bank.count_documents({})
    with_consent = await db.candidate_bank.count_documents({"consent.accepted": True})
    with_current = await db.candidate_bank.count_documents({"consent.consent_version": CONSENT_VERSION})
    missing = total_profiles - with_consent
    compliance_pct = round((with_consent / total_profiles) * 100, 1) if total_profiles > 0 else 0

    total_apps = await db.applications.count_documents({})
    apps_with_consent = await db.applications.count_documents({"consent_metadata.consent_given": True})

    return {
        "total_profiles": total_profiles,
        "consent_recorded": with_consent,
        "current_version_consent": with_current,
        "missing_consent": missing,
        "compliance_percentage": compliance_pct,
        "total_applications": total_apps,
        "applications_with_consent": apps_with_consent,
    }


async def get_data_risk_alerts():
    """Compute data risk alerts dynamically."""
    alerts = []
    now = datetime.now(timezone.utc)

    # Profiles without consent
    missing_count = await db.candidate_bank.count_documents({
        "$or": [{"consent": {"$exists": False}}, {"consent.accepted": {"$ne": True}}]
    })
    if missing_count > 0:
        sev = "CRITICAL" if missing_count > 100 else "HIGH" if missing_count > 20 else "MEDIUM"
        alerts.append({
            "severity": sev, "type": "missing_consent",
            "title": f"{missing_count} profiles without consent",
            "description": "Candidate profiles in the bank lack explicit DPDP consent.",
            "count": missing_count,
        })

    # Outdated consent version
    outdated = await db.candidate_bank.count_documents({
        "consent.accepted": True,
        "consent.consent_version": {"$ne": CONSENT_VERSION, "$exists": True},
    })
    if outdated > 0:
        alerts.append({
            "severity": "MEDIUM", "type": "outdated_consent",
            "title": f"{outdated} profiles with outdated consent version",
            "description": f"These profiles have consent but not the current version ({CONSENT_VERSION}).",
            "count": outdated,
        })

    # Applications without consent metadata
    apps_no_consent = await db.applications.count_documents({
        "$or": [{"consent_metadata": {"$exists": False}}, {"consent_metadata.consent_given": {"$ne": True}}]
    })
    if apps_no_consent > 0:
        sev = "HIGH" if apps_no_consent > 50 else "LOW"
        alerts.append({
            "severity": sev, "type": "applications_missing_consent",
            "title": f"{apps_no_consent} applications without consent record",
            "description": "Legacy applications submitted before consent tracking was implemented.",
            "count": apps_no_consent,
        })

    # Pending data governance requests
    pending_requests = await db.data_governance_requests.count_documents({"status": "pending"})
    if pending_requests > 0:
        alerts.append({
            "severity": "HIGH", "type": "pending_governance_requests",
            "title": f"{pending_requests} pending data governance requests",
            "description": "Deletion or withdrawal requests awaiting action.",
            "count": pending_requests,
        })

    return sorted(alerts, key=lambda a: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(a["severity"], 4))


async def ensure_compliance_indexes():
    """Create indexes for compliance collections."""
    await db.consent_audit_logs.create_index("candidate_id")
    await db.consent_audit_logs.create_index("timestamp")
    await db.consent_audit_logs.create_index("action")
    await db.consent_audit_logs.create_index("source")
    await db.compliance_alerts.create_index("severity")
    await db.compliance_alerts.create_index("status")
    await db.compliance_alerts.create_index("created_at")
    await db.data_governance_requests.create_index("candidate_id")
    await db.data_governance_requests.create_index("status")
    await db.data_governance_requests.create_index("request_type")
    await db.cookie_consent_logs.create_index("timestamp")
