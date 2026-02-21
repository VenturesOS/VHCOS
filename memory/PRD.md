# Ventures HRD - Talent OS

## Original Problem Statement
Full-stack talent operating system for industrial recruitment with pipeline tracking, submission tracker, analytics, revenue engine, multi-portal architecture, enterprise compliance (DPDP 2023), and self-healing maintenance system.

## Architecture
- **Frontend:** React (CRA) + Shadcn/UI + TailwindCSS + Recharts + react-data-grid
- **Backend:** FastAPI + MongoDB Atlas + Cloudflare R2 + Upstash Redis
- **3rd Party:** OpenAI GPT-4o-mini, Resend, Google Tag Manager, LinkedIn API

## What's Been Implemented

### Core Platform
- 7-stage Pipeline, Submission Tracker, Analytics (4 tabs), Revenue Engine
- Tracker Creation Wizard, Duplicate Tracker, Template Upload
- Unified Filter Bar, Combined PDF Export, Analytics API optimization

### Enterprise Compliance (DPDP 2023)
- Cookie Consent Banner, Candidate Data Consent, Compliance Dashboard
- Policy Pages (Privacy, Terms, Cookie), Trust Badges, Audit Logging

### Enterprise System Maintenance Bot
- Health Monitor: 11 service checks (MongoDB, API, Workers, Queue, Resources, Automation, AI, Data Sync, Naukri Capture, Security, Virus Scanner)
- Auto-Healer: Rate-limited 3/hr/service, CRITICAL escalation
- Reliability Layer: Circuit breaker, retry, graceful degradation, queue buffering, safe mode, task priority
- Background Bot: 5-min loop, daily diagnostic self-test
- PDF Report: 8 sections (Header, Summary, Errors, Fixes, AI Analytics, Reliability, Naukri Failed Captures, Security Events + ClamAV status)
- Real-Time Dashboard: Live service grid (11 cards), health score trend (24h), active incidents, auto-refresh 30s

### Naukri Extension Capture Monitoring
- Full capture logging to `naukri_capture_logs` (success + failure with candidate identity)
- Failed Naukri Captures panel in System Health dashboard with Recover button
- Health score affected by capture failure rate and unrecovered count
- PDF Section 7: Failed Capture Details with candidate name, email, profile URL, failure reason, missing fields

### Enterprise Security Hardening (COMPLETED Feb 2026)
- **CV Upload Security:** File type (PDF/DOC/DOCX only), size (5MB max), magic byte validation, pattern-based threat scanning
- **ClamAV Virus Scanner:** Optional integration with graceful fallback — when disabled, uses pattern-based scanning; logs events when scanner unavailable
- **Bot & Spam Protection:** Cloudflare Turnstile CAPTCHA on registration, resume upload, and job application — bypassed gracefully when keys not configured
- **API Abuse Protection:** Rate limiting middleware on login (5/min), register (5/min), parse-resume (10/min), apply (5/min), upload (3/min), admin routes (30/min)
- **Admin Security:** Cloudflare Zero Trust Access middleware on all admin routes — validates CF-Access-Jwt-Assertion header; bypassed when not configured
- **Security Logging:** All security events logged to `security_events` collection (event_type, severity, IP, detail)
- **System Health Dashboard:** Security Events panel, Virus Scanner service card (11 services total)
- **PDF Report:** Section 8 Security Events with ClamAV status note, event counts and details
- **CV Display Safety:** HTML sanitization of extracted resume text to prevent XSS
- **Refresh Token Support:** Short JWT expiry configurable via env

### Security Audit Dashboard (COMPLETED Feb 2026)
- **Security Posture Score:** Weighted 0-100 score ring (File Validation 15, Rate Limiting 15, Turnstile 15, Zero Trust 20, ClamAV 15, Logging 10, XSS 10)
- **Active/Inactive Layers:** Visual cards showing enabled protections and missing protections with amber warning
- **Compliance Checklist:** 17-item checklist with PASS/FAIL status and copy-to-clipboard export
- **Recent Security Events:** Last 7 days events with severity badges and timestamps
- **Event Breakdown:** Event type distribution with counts
- **Security Validation API:** `GET /api/system-health/security-validation` returns PASS/WARN/FAIL per layer for deployment checks
- **Security Posture API:** `GET /api/system-health/security-posture` returns full posture data for dashboard
- **Health Score Penalty:** System Health score reduced by -7 when security layers inactive (-2 Turnstile, -3 Zero Trust, -2 ClamAV)
- **Navigation:** Linked from System Health page header + admin sidebar
- **Production Activation Checklist:** Documentation at `/app/docs/PRODUCTION_ACTIVATION_CHECKLIST.md`

## DB Collections
### Maintenance & Monitoring
- `system_health_checks`, `maintenance_fixes`, `reliability_events`, `reliability_buffer`
- `naukri_capture_logs`, `security_events`

### Compliance
- `consent_audit_logs`, `cookie_consent_logs`, `compliance_alerts`, `data_governance_requests`

## Key API Endpoints
- `GET /api/system-health/live-status` — 11 services, score history, incidents
- `GET /api/system-health/security-events` — Security event logs with summary
- `GET /api/system-health/failed-captures` — Failed Naukri capture logs
- `POST /api/system-health/failed-captures/{id}/recover` — Mark as recovered
- `GET /api/system-health/security-validation` — Deployment check: PASS/WARN/FAIL per security layer
- `GET /api/system-health/security-posture` — Full posture data for Security Audit Dashboard
- `GET /api/system-health/maintenance-report/download` — 8-section PDF
- `POST /api/system-health/maintenance-run` — Manual maintenance trigger
- `POST /api/system-health/diagnostic-test` — Diagnostic self-test

## Environment Variables (Security)
- `TURNSTILE_SECRET_KEY` / `TURNSTILE_SITE_KEY` — Cloudflare Turnstile CAPTCHA
- `REACT_APP_TURNSTILE_SITE_KEY` — Frontend Turnstile widget
- `CF_ACCESS_TEAM_DOMAIN` / `CF_ACCESS_AUD` — Cloudflare Zero Trust
- `CLAMAV_HOST` / `CLAMAV_PORT` / `CLAMAV_ENABLED` — ClamAV virus scanner

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Employer: employer@vhc.in / VhcEmployer@2024
- Recruiter: recruiter@vhc.in / VhcRecruiter@2024

## Prioritized Backlog
### P2
- Client Dashboard enhancements
- AI-driven Analytics and Insights
- Advanced Revenue Intelligence
- Automation workflows
- Consent withdrawal flow
- Bulk consent remediation

## Known Issues
- LinkedIn API auto-posting blocked (requires `w_organization_social` scope approval from LinkedIn)
