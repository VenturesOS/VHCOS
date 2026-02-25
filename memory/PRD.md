# VHC Talent OS — Product Requirements Document

## Original Problem Statement
Full-stack React + FastAPI recruitment management platform for Ventures HRD Consulting.

## Core Architecture
- **Frontend**: React (CRA/CRACO) + Shadcn/UI + React Router + Recharts
- **Backend**: FastAPI + MongoDB Atlas + APScheduler
- **Auth**: JWT, RBAC (admin, employer, recruiter, candidate)
- **3rd Party**: Cloudflare Turnstile/Zero Trust, MongoDB Atlas, Upstash Redis, Resend, OpenAI GPT-4o-mini, Cloudflare R2

## Features Implemented

### Attendance Intelligence System (Feb 24, 2026)
- Self check-in/check-out (Office/WFH/Field), admin override, late/overtime/IP tracking
- Leave request/approval workflow, leave bank per user, holiday calendar
- Automated reminders (10AM) + auto-absent marking (6:30PM) with `should_remind()` decision layer
- Analytics dashboard: `{metrics, charts, insights}`, Recharts (Line/Bar/Pie), pattern detection, health scores (0-100)
- **Settings page**: Visual admin config for work hours, thresholds, automation times, weekend days
- Notification system: `notification_events` + `notification_delivery_logs`, email via Resend
- Cron infrastructure: job locks, execution logging, APScheduler, 14 DB indexes

### Pause & Pre-Launch Reset (Feb 24, 2026)
- **Pause toggle**: Global `is_paused` flag in attendance_settings, guards check-in/out APIs (403), cron jobs skip when paused
- **UI indicators**: Amber banner on AttendancePage when paused, "System: Active/Paused" badge on AdminAttendancePage
- **Pre-Launch Reset**: Admin-only endpoint clears 10 operational collections, preserves users/settings/holidays
- **Safety**: Typed "RESET DATA" confirmation, audit log with admin ID + timestamp in `system_audit_logs`
- Collections cleared: attendance_records, leave_requests, leave_balances, attendance_health_scores, notification_events, notification_delivery_logs, cron_job_logs, jobs, revenue_entries, invoices, revenue_analytics

### Other Features
- Submission Tracker (CRUD, role-based visibility filtering)
- Job CRUD, candidate pipeline, AI matching
- Chrome Extension v3.9.2, blog engine, revenue dashboard, compliance

## Known Debt
- P0 (BLOCKED): Hardcoded MongoDB override in `config.py`

## Backlog

### ATS Gap Audit (Feb 24, 2026) — from RecruitChamp comparison
**P0 — Competitive Blockers**
- Interview Scheduling (calendar integration, reminders, no-show tracking)
- Candidate Activity Log (calls, emails, notes, status changes per candidate)
- Hiring Funnel KPIs (time-to-fill, source effectiveness, pipeline conversion)
- In-App Notification Center (UI for existing notification_events DB)

**P1 — High Impact**
- Client CRM (leads, deals, sales pipeline, revenue forecasting)
- Invoicing & Billing Calendar (auto-generate invoices, track payments)
- Candidate Duplicate Detection (auto-merge, dedup on import)
- Email Template Management (user-facing create/edit/share templates)
- Team Collaboration — Notes/Comments on candidates
- Boolean Search (AND/OR/NOT operators for power recruiters)

**P2 — Long-Term Differentiation**
- Onboarding Module (post-hire workflows, checklists)
- Vendor Management System (external recruiter management)
- P&L / Cost Tracking (placement profitability analysis)
- Multi-Board Job Posting (Indeed, Monster, Naukri integration)
- Branded Career Portals (per-company career pages)
- Mobile PWA
- Custom Report Builder (self-service analytics)

### Existing Backlog
- P2: Client Dashboard enhancements
- P3: Advanced Revenue Intelligence
- P4: LinkedIn Auto-Posting (blocked on LinkedIn API scope), Training Manual PDF
- P5: WhatsApp/Push notifications
- P5: Chrome Extension backup cleanup

## Test Reports
- iteration_88: Submission tracker access (100%)
- iteration_89: Visibility filtering (100%)
- iteration_90: Attendance CRUD (95%/100%)
- iteration_91: Attendance Intelligence (100%)
- iteration_92: Attendance Settings (100%)
- iteration_93: Pause & Pre-Launch Reset (100% backend 16/16, 100% frontend)
