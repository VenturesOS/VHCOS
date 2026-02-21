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
- Health Monitor: 9 service checks (MongoDB, API, Workers, Queue, Resources, Automation, AI, Data Sync, Naukri Capture)
- Auto-Healer: Rate-limited 3/hr/service, CRITICAL escalation
- Reliability Layer: Circuit breaker, retry, graceful degradation, queue buffering, safe mode, task priority
- Background Bot: 5-min loop, daily diagnostic self-test
- PDF Report: 7 sections (Header, Summary, Errors, Fixes, AI Analytics, Reliability, Naukri Failed Captures)
- Real-Time Dashboard: Live service grid (9 cards), health score trend (24h), active incidents, auto-refresh 30s

### Naukri Extension Capture Monitoring
- Full capture logging to `naukri_capture_logs` (success + failure with candidate identity)
- Failed Naukri Captures panel in System Health dashboard with Recover button
- Health score affected by capture failure rate and unrecovered count
- PDF Section 7: Failed Capture Details with candidate name, email, profile URL, failure reason, missing fields
- Recovery workflow: POST /api/system-health/failed-captures/{id}/recover

## DB Collections
### Maintenance & Monitoring
- `system_health_checks`, `maintenance_fixes`, `reliability_events`, `reliability_buffer`
- `naukri_capture_logs`: { id, timestamp, profile_id, profile_url, candidate_name, candidate_email, candidate_phone, status, failure_reason, failed_step, data_missing_fields, captured_to_bank, is_recovered, retry_count, capture_duration_ms, source }

### Compliance
- `consent_audit_logs`, `cookie_consent_logs`, `compliance_alerts`, `data_governance_requests`

## Key API Endpoints
- `GET /api/system-health/live-status` — 9 services, score history, incidents
- `GET /api/system-health/failed-captures` — Failed Naukri capture logs
- `POST /api/system-health/failed-captures/{id}/recover` — Mark as recovered
- `GET /api/system-health/maintenance-report/download` — 7-section PDF
- `POST /api/system-health/maintenance-run` — Manual maintenance trigger
- `POST /api/system-health/diagnostic-test` — Diagnostic self-test

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
