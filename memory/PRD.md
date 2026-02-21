# Ventures HRD - Talent OS

## Original Problem Statement
Full-stack talent operating system for industrial recruitment with pipeline tracking, submission tracker, analytics, revenue engine, multi-portal architecture, enterprise compliance (DPDP 2023), and self-healing maintenance system.

## Architecture
- **Frontend:** React (CRA) + Shadcn/UI + TailwindCSS + Recharts + react-data-grid
- **Backend:** FastAPI + MongoDB Atlas + Cloudflare R2 + Upstash Redis
- **3rd Party:** OpenAI GPT-4o-mini, Resend, Google Tag Manager, LinkedIn API

## What's Been Implemented
- 7-stage Pipeline (applied→joined) with validation, event logging, revenue closure
- Submission Tracker: Master columns (58), templates, CRUD, spreadsheet UI, bidirectional sync
- Multi-step Tracker Creation Wizard (5 steps: setup, columns, custom, required, review)
- Duplicate Tracker feature (clone structure to new mandate)
- Template Upload: Parse XLSX/CSV, auto-map headers
- Client-facing read-only tracker view at /employer/submission-tracker
- Analytics Dashboard with 4 tabs: Overview, Pipeline Funnel, Revenue, Performance
- Unified Filter Bar (Employer, Team, Recruiter, Date) shared across ALL tabs
- Combined PDF Export (Revenue → Pipeline → Performance → Overview) in single report
- Excel import/export, validation-aware download states
- Analytics API optimized from 11s to ~2s

### Enterprise Compliance Upgrade (DPDP 2023) — Completed Feb 2026
- Cookie Consent Banner with Accept All, Reject Non-Essential, Manage Settings
- Candidate Data Consent (mandatory DPDP consent block on apply forms)
- Compliance Dashboard at /admin/compliance-dashboard
- Policy Pages: Privacy Policy, Terms of Use, Cookie Policy
- Enterprise Trust Badges on candidate-facing pages
- Consent Audit Logging in consent_audit_logs collection

### Enterprise System Maintenance Bot — Completed Feb 2026
- **Health Monitor:** 8 service checks (MongoDB, API, workers, queue, resources, automation, AI, data sync)
- **Auto-Healer:** Rate-limited (3/hr/service), escalates to CRITICAL if exceeded
- **Reliability Layer:** Circuit breaker, retry with backoff, graceful degradation, queue buffering, read-only safe mode, task priority system (HIGH/MEDIUM/LOW)
- **AI Failure Monitoring:** Silent automation failures, queue backlog explosion, AI response degradation, memory leaks, data sync drift
- **Maintenance Bot:** Background worker (5-min interval), non-blocking asyncio loop
- **PDF Report:** 6-section enterprise report (Header+Score, Summary, Errors, Fixes, AI Analytics, Reliability Events), scoped to 7 days / 1000 records
- **Health Score:** Weighted 0-100 score (priority-based: HIGH=3x, MEDIUM=2x, LOW=1x)
- **Download Button:** Top-right on System Health page with spinner + toast

## DB Collections
### Compliance
- `consent_audit_logs`, `cookie_consent_logs`, `compliance_alerts`, `data_governance_requests`

### Maintenance
- `system_health_checks`: { service_name, priority, status, timestamp, metrics, error_details }
- `maintenance_fixes`: { id, service_name, issue_detected, fix_action, start_time, end_time, recovery_duration_ms, result }
- `reliability_events`: { id, event_type, service, detail, timestamp }
- `reliability_buffer`: { id, action_type, payload, status, created_at, processed_at }

## Key Files
### Maintenance Bot
- `backend/services/health_monitor.py` - 8 health check functions + score computation
- `backend/services/auto_healer.py` - Auto-fix with 3/hr rate limit
- `backend/services/reliability_layer.py` - Circuit breaker, retry, safe mode, stress mode
- `backend/services/maintenance_bot.py` - Background bot orchestrator
- `backend/services/maintenance_report_generator.py` - Enterprise PDF report
- `backend/routes/maintenance_routes.py` - 3 API endpoints

### Compliance
- `backend/routes/compliance_routes.py` - 5 compliance endpoints
- `backend/services/compliance_service.py` - Consent health, audit logging
- `frontend/src/pages/admin/ComplianceDashboardPage.jsx` - Admin compliance dashboard
- `frontend/src/components/compliance/CookieConsentBanner.jsx` - Cookie banner
- `frontend/src/components/compliance/TrustBadge.jsx` - Trust badges
- `frontend/src/pages/policy/PolicyPages.jsx` - 3 policy pages

## Key API Endpoints
- `GET /api/system-health/maintenance-status` - Bot status, health score, services
- `GET /api/system-health/maintenance-report/download` - PDF report download
- `POST /api/system-health/maintenance-run` - Manual maintenance trigger
- `GET /api/compliance/dashboard-stats` - Compliance dashboard data
- `GET /api/compliance/audit-logs` - Consent audit logs
- `POST /api/compliance/cookie-consent` - Cookie consent logging
- `GET /api/compliance/consent-version` - Current consent version

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Employer: employer@vhc.in / VhcEmployer@2024
- Recruiter: recruiter@vhc.in / VhcRecruiter@2024

## Prioritized Backlog
### P2
- Client Dashboard enhancements
- AI-driven Analytics and Insights
- Advanced Revenue Intelligence
- Automation workflows based on pipeline events
- Consent withdrawal flow (data governance requests)
- Bulk consent remediation for legacy profiles
