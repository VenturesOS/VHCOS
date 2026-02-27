# VHC Talent OS — Product Requirements Document

## Original Problem Statement
Full-stack React + FastAPI recruitment management platform for Ventures HRD Consulting.

## Core Architecture
- **Frontend**: React (CRA/CRACO) + Shadcn/UI + React Router + Recharts
- **Backend**: FastAPI + MongoDB Atlas + APScheduler
- **Auth**: JWT, RBAC (admin, employer, recruiter, candidate)
- **3rd Party**: Cloudflare Turnstile/Zero Trust, MongoDB Atlas, Upstash Redis, Resend, OpenAI GPT-4o-mini, Cloudflare R2, Emergent LLM Key (GPT-5.2)

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

### Data Mapping & Enrichment (Feb 24, 2026)
- Fixed candidate details (education, employer, designation) not showing in pipelines/trackers
- Enriched APIs: `/api/employer/pipeline`, `/api/admin/pipeline`, `/api/jobs/{job_id}/applicants`
- Fixed application creation logic to denormalize candidate fields
- Backfill endpoint for tracker education data

### Deployment-Safe Startup Fix (Feb 2026)
- Replaced blocking `AsyncIOMotorClient` instantiation at module-level in `config.py` with a lazy proxy pattern
- `db` and `client` are now lightweight proxy objects at import time (zero network cost)
- Real MongoDB client created in deferred background task (`server.py`) after server binds to port 8001
- Removed blocking `init_services()` call from module level; deferred to background task
- All 40+ files importing `from config import db` work transparently via proxy forwarding
- Health check responds instantly; MongoDB connects 1s later in background
- Fixes production "Connection refused" outage caused by SRV DNS lookup blocking server startup

### ENV Mode Detection Fix (Feb 26, 2026)
- Fixed environment detection priority: MongoDB cluster check now runs BEFORE preview pod URL check
- Root cause: Emergent pod injects APP_URL with "preview.emergentagent.com", which was checked before the DB cluster identity
- Result: Dashboard now correctly shows production mode, amber warning banner removed
- File changed: utils/environment.py (detection order only)

### Production Stabilization (Feb 25, 2026)
- Applied 12-file stabilization patch from external audit (Claude)
- Removed hardcoded MongoDB credentials from config.py + migration scripts
- Removed tlsInsecure=True (was disabling TLS validation)
- Added schema_normalizer.py — single source of truth for dual-write schema
- Fixed duplicate parse_resume_with_ai() — consolidated to matching_engine.py
- AI Search now queries BOTH canonical + alias field names (no invisible candidates)
- Embeddings cache moved from module-level dict to Redis (process-safe)
- Chunked upload sessions moved to Redis (multi-worker safe)
- Bulk import now uses upsert (idempotent, no duplicates on retry)
- All 9 validation steps PASSED — SYSTEM STABILIZATION REPORT at /app/memory/SYSTEM_STABILIZATION_REPORT.md

### AI Screening System Code Handoff (Feb 25, 2026)
- Complete extraction of 16 AI screening files for external audit
- Identified 5 architectural risks: duplicate parse_resume_with_ai, inconsistent scoring, non-idempotent bulk import, field mismatches, non-process-safe cache
- Full audit documented in `/app/memory/AI_SCREENING_AUDIT.md`

### Other Features
- Submission Tracker (CRUD, role-based visibility filtering)
- Job CRUD, candidate pipeline, AI matching
- Chrome Extension v3.9.2, blog engine, revenue dashboard, compliance

## Known Debt
- P2: LinkedIn Auto-Posting (blocked on LinkedIn API scope `w_organization_social`)
- P3: Cloudflare R2 ListBuckets returns AccessDenied (uploads may still work)

## Backlog

### AI Audit Issues — RESOLVED (Feb 25, 2026)
- ✅ P1: Deduplicated `parse_resume_with_ai()` — consolidated to matching_engine.py
- ✅ P1: Fixed inconsistent scoring — all scoring reads via schema_normalizer helpers
- ✅ P2: Bulk CV import now idempotent (upsert logic)
- ✅ P2: Standardized field names (dual-write schema via normalize_candidate())
- ✅ P2: Replaced in-memory caches with Redis (embedding_cache, upload sessions)

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
- iteration_94: Pipeline Enrichment Bug Fix (100% backend 11/11, 100% frontend)
