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

### Other Features
- Submission Tracker (CRUD, role-based visibility filtering)
- Job CRUD, candidate pipeline, AI matching
- Chrome Extension v3.9.2, blog engine, revenue dashboard, compliance

## Known Debt
- P0 (BLOCKED): Hardcoded MongoDB override in `config.py`

## Backlog
- P2: Client Dashboard enhancements
- P3: Advanced Revenue Intelligence
- P4: LinkedIn Auto-Posting (blocked), Training Manual PDF
- P5: WhatsApp/Push notifications

## Test Reports
- iteration_88: Submission tracker access (100%)
- iteration_89: Visibility filtering (100%)
- iteration_90: Attendance CRUD (95%/100%)
- iteration_91: Attendance Intelligence (100%)
- iteration_92: Attendance Settings (100%)
