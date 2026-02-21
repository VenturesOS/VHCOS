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
- Multi-step Tracker Creation Wizard + Duplicate Tracker
- Client-facing read-only tracker view
- Analytics Dashboard: 4 tabs, unified filter bar, combined PDF export
- Analytics API optimized from 11s to ~2s

### Enterprise Compliance (DPDP 2023) — Feb 2026
- Cookie Consent Banner, Candidate Data Consent, Compliance Dashboard
- Policy Pages (Privacy, Terms, Cookie), Trust Badges, Audit Logging

### Enterprise System Maintenance Bot — Feb 2026
- **Health Monitor:** 8 service checks (MongoDB, API, Workers, Queue, Resources, Automation, AI, Data Sync)
- **Auto-Healer:** Rate-limited 3/hr/service, CRITICAL escalation
- **Reliability Layer:** Circuit breaker, retry with backoff, graceful degradation, queue buffering, safe mode, task priority (HIGH/MEDIUM/LOW)
- **Maintenance Bot:** Background worker (5-min loop), non-blocking asyncio
- **PDF Report:** 6-section enterprise report (Header+Score, Summary, Errors, Fixes, AI Analytics, Reliability Events)
- **Real-Time Dashboard:** Live service monitor grid (8 cards), health score trend chart (24h), active incidents panel (last 5), auto-refresh 30s

## DB Collections
### Maintenance
- `system_health_checks`: { service_name, priority, status, timestamp, metrics, error_details }
- `maintenance_fixes`: { id, service_name, issue_detected, fix_action, start_time, end_time, recovery_duration_ms, result }
- `reliability_events`: { id, event_type, service, detail, timestamp }
- `reliability_buffer`: { id, action_type, payload, status, created_at, processed_at }

### Compliance
- `consent_audit_logs`, `cookie_consent_logs`, `compliance_alerts`, `data_governance_requests`

## Key API Endpoints
- `GET /api/system-health/live-status` — Real-time services, score history, incidents
- `GET /api/system-health/maintenance-status` — Bot status, health score, reliability state
- `GET /api/system-health/maintenance-report/download` — PDF report
- `POST /api/system-health/maintenance-run` — Manual maintenance trigger
- `GET /api/compliance/dashboard-stats` — Compliance health
- `GET /api/compliance/audit-logs` — Consent audit logs

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
