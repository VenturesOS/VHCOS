"""
Router imports + registration list.

Every router lives in `routes/`. This module imports each one via a safe
loader so a single broken file doesn't take the whole server down. The
list of import failures is exposed to the health router.

Public surface:
    all_routers                    — flat list of router objects (some may be None)
    route_import_failures          — list[str] of "module.attr: error"
    log_system_error(...)          — async fn for the global exception handler;
                                     no-op if routes.system_errors failed to import.
"""
import logging

logger = logging.getLogger(__name__)

_ALLOWED_ROUTE_PREFIXES = ("routes.",)
route_import_failures: list[str] = []


def _safe_import(module_path: str, attr_name: str):
    """Import a router safely; return None on failure so the server can still start."""
    if not any(module_path.startswith(p) for p in _ALLOWED_ROUTE_PREFIXES):
        logger.error(f"[IMPORT BLOCKED] {module_path} not in allowed prefixes")
        return None
    try:
        mod = __import__(module_path, fromlist=[attr_name])
        return getattr(mod, attr_name)
    except Exception as e:
        route_import_failures.append(f"{module_path}.{attr_name}: {e}")
        logger.error(f"[IMPORT FAIL] {module_path}.{attr_name}: {e}")
        return None


# ── Core routes (batch import; failure here degrades many surfaces) ──
try:
    from routes import (
        auth_router, public_router, files_router, admin_router, jobs_router,
        candidates_router, applications_router, settings_router, background_jobs_router,
        teams_router, referrals_router, analytics_router, revenue_router,
        employer_router, linkedin_router,
    )
except Exception as e:
    logger.error(f"[IMPORT FAIL] Core routes: {e}")
    auth_router = public_router = files_router = admin_router = jobs_router = None
    candidates_router = applications_router = settings_router = background_jobs_router = None
    teams_router = referrals_router = analytics_router = None
    revenue_router = employer_router = linkedin_router = None


# ── Individually-loaded routers (one-at-a-time so failures are isolated) ──
bulk_import_router = _safe_import("routes.bulk_import", "bulk_import_router")
bills_router = _safe_import("routes.bills", "bills_router")
tally_router = _safe_import("routes.tally_bridge", "tally_router")
ext_check_router = _safe_import("routes.extension_check", "ext_check_router")
badge_audit_router = _safe_import("routes.badge_audit", "router")
ext_feedback_router = _safe_import("routes.badge_audit", "ext_feedback_router")
ltr_router = _safe_import("routes.ltr", "ltr_router")
ltr_admin_router = _safe_import("routes.ltr", "ltr_admin_router")
embed_admin_router = _safe_import("routes.embed_admin", "embed_admin_router")
bug_reports_router = _safe_import("routes.bug_reports", "bug_reports_router")

# system_errors gives us log_system_error too — need a working stub if it fails
try:
    from routes.system_errors import system_errors_router, log_system_error  # type: ignore
except Exception as e:
    logger.error(f"[IMPORT FAIL] system_errors: {e}")
    system_errors_router = None

    async def log_system_error(*a, **kw):  # noqa: D401 — silent fallback
        pass

extension_router = _safe_import("routes.extension", "extension_router")
profile_router = _safe_import("routes.profile", "profile_router")
analytics_pageviews_router = _safe_import("routes.analytics_pageviews", "analytics_pageviews_router")
clustering_router = _safe_import("routes.clustering", "clustering_router")
cv_upload_router = _safe_import("routes.cv_upload", "cv_upload_router")
ai_search_router = _safe_import("routes.ai_search", "ai_search_router")
sourcing_router = _safe_import("routes.sourcing_search", "sourcing_router")
talent_search_router = _safe_import("routes.talent_search", "router")
talent_feedback_router = _safe_import("routes.talent_feedback", "router")
# ── Asha agent v2.0.0 (2026-07-24) — ships DARK; controlled via AGENT_ENABLED env
agent_router = _safe_import("routes.agent", "agent_router")
extension_preview_router = _safe_import("routes.extension_preview", "extension_preview_router")
contact_router = _safe_import("routes.contact", "router")
blog_router = _safe_import("routes.blog", "router")
seo_router = _safe_import("routes.seo", "router")
public_careers_router = _safe_import("routes.public_careers", "router")
pillar_pages_router = _safe_import("routes.pillar_pages", "router")
blog_digest_router = _safe_import("routes.blog_digest", "router")
seo_dashboard_router = _safe_import("routes.seo_dashboard", "router")
tracker_router = _safe_import("routes.tracker", "router")
compliance_router = _safe_import("routes.compliance_routes", "compliance_router")
maintenance_router = _safe_import("routes.maintenance_routes", "maintenance_router")
attendance_router = _safe_import("routes.attendance", "router")
attendance_analytics_router = _safe_import("routes.attendance_analytics", "router")
resume_router = _safe_import("routes.resume", "resume_router")
account_manager_router = _safe_import("routes.account_manager", "account_manager_router")
team_lead_router = _safe_import("routes.team_lead", "team_lead_router")
finance_router = _safe_import("routes.finance", "finance_router")
notification_router = _safe_import("routes.notifications", "notification_router")
activity_router = _safe_import("routes.activity_log", "activity_router")
activity_monitor_router = _safe_import("routes.activity_monitor", "router")
extraction_report_router = _safe_import("routes.extraction_report", "router")
extraction_trace_router = _safe_import("routes.extraction_trace", "router")
capture_diagnostics_router = _safe_import("routes.capture_diagnostics", "router")
candidate_hygiene_router = _safe_import("routes.candidate_hygiene", "router")
admin_monitoring_router = _safe_import("routes.admin_monitoring", "router")
extension_updates_router = _safe_import("routes.extension_updates", "router")
reports_router = _safe_import("routes.reports", "router")
talent_graph_router = _safe_import("routes.talent_graph", "router")
daily_digest_router = _safe_import("routes.daily_digest", "digest_router")
whatsapp_webhook_router = _safe_import("routes.whatsapp_webhook", "webhook_router")

# Health router is not optional — it exposes /api/health used by k8s + monitoring.
from routes.health import health_router, set_route_import_failures  # noqa: E402

# Pass the failure list up so /api/health can surface it.
set_route_import_failures(route_import_failures)


all_routers = [
    health_router,
    auth_router, public_router, files_router, admin_router, jobs_router,
    candidates_router, applications_router, settings_router, background_jobs_router,
    bulk_import_router, teams_router, referrals_router,
    bills_router,
    tally_router,
    ext_check_router,
    embed_admin_router,
    bug_reports_router, system_errors_router, profile_router, cv_upload_router,
    ai_search_router, extension_router, analytics_router, contact_router,
    blog_router, seo_router, public_careers_router, pillar_pages_router, blog_digest_router,
    seo_dashboard_router, revenue_router, employer_router, linkedin_router,
    tracker_router, compliance_router, maintenance_router, attendance_router,
    attendance_analytics_router, resume_router, account_manager_router,
    team_lead_router,
    notification_router, activity_router, finance_router,
    activity_monitor_router,
    extraction_report_router,
    extraction_trace_router,
    capture_diagnostics_router,
    candidate_hygiene_router,
    admin_monitoring_router,
    extension_updates_router,
    reports_router,
    talent_graph_router,
    daily_digest_router,
    whatsapp_webhook_router,
    sourcing_router,
    analytics_pageviews_router,
    clustering_router,
    badge_audit_router,
    ext_feedback_router,
    ltr_router,
    ltr_admin_router,
    talent_search_router,
    talent_feedback_router,
    agent_router,
    extension_preview_router,
]
