# Ventures HRD - Talent OS

## Original Problem Statement
Full-stack talent operating system for industrial recruitment with pipeline tracking, submission tracker, analytics, revenue engine, multi-portal architecture, and enterprise compliance (DPDP 2023).

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
- **Cookie Consent Banner:** Persistent banner with Accept All, Reject Non-Essential, Manage Settings; stored in localStorage; logged to backend `cookie_consent_logs` collection
- **Candidate Data Consent:** Mandatory DPDP-compliant consent block on MandateApplyPage and PublicJobPage; blocks submission without consent; captures consent version, IP, user agent, timestamp
- **Compliance Dashboard:** `/admin/compliance-dashboard` with consent health metrics, progress bars, data risk alerts (CRITICAL/HIGH/MEDIUM/LOW), paginated audit log table with action/source filters
- **Policy Pages:** Privacy Policy (`/privacy-policy`), Terms of Use (`/terms-of-use`), Cookie Policy (`/cookie-policy`) with standard DPDP 2023 compliant content
- **Trust Badges:** Subtle green checkmark badges (DPDP 2023 Compliant, Data Protected, Consent Verified) on candidate-facing pages
- **Audit Logging:** `consent_audit_logs` collection with per-action tracking; integrated into public apply flow
- **Data Governance Foundation:** `data_governance_requests` collection with indexes for future consent withdrawal/data deletion features

## New DB Collections (Compliance)
- `consent_audit_logs`: { id, candidate_id, action, consent_version, timestamp, ip_address, user_agent, source, metadata }
- `cookie_consent_logs`: { preferences, action, timestamp, ip_address, user_agent, consent_version }
- `compliance_alerts`: { id, severity, alert_type, title, description, status, created_at, resolved_at, metadata }
- `data_governance_requests`: { candidate_id, status, request_type, created_at }

## Key Files
- `backend/routes/compliance_routes.py` - 5 compliance API endpoints
- `backend/services/compliance_service.py` - Consent health, risk alerts, audit logging
- `frontend/src/pages/admin/ComplianceDashboardPage.jsx` - Admin compliance dashboard
- `frontend/src/components/compliance/CookieConsentBanner.jsx` - Cookie consent banner
- `frontend/src/components/compliance/TrustBadge.jsx` - Enterprise trust badges
- `frontend/src/pages/policy/PolicyPages.jsx` - Privacy, Terms, Cookie policy pages

## Key API Endpoints
- `GET /api/compliance/consent-version` - Public: returns current consent version
- `GET /api/compliance/dashboard-stats` - Admin: consent health, risk alerts, audit count
- `GET /api/compliance/audit-logs` - Admin: paginated audit logs with filters
- `POST /api/compliance/cookie-consent` - Public: log cookie consent action
- `GET /api/compliance/governance-requests` - Admin: data governance requests
- `GET /api/analytics/export-combined-pdf` - Combined PDF (all 4 sections)
- `POST /api/tracker/trackers/{id}/duplicate` - Duplicate tracker

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
