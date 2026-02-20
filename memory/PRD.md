# Ventures HRD - Talent OS

## Original Problem Statement
Full-stack talent operating system for industrial recruitment, with CV management, ATS-friendly CV generation, pipeline tracking, revenue engine, blog/SEO, and employer/recruiter/candidate portals.

## Architecture
- **Frontend:** React (CRA) + Shadcn/UI + TailwindCSS + Static HTML pages (website/)
- **Backend:** FastAPI + MongoDB Atlas + Cloudflare R2 + Upstash Redis
- **3rd Party:** OpenAI GPT-4o-mini, Resend, Google Tag Manager, Google Analytics (GA4), LinkedIn API

## What's Been Implemented

### Phase 1: Pipeline Restructure (Feb 2026) - COMPLETE
- New stage order: applied → shortlisted → submitted_to_client → interview → offered → hired → joined
- Validation rules: can't skip stages, joined locks, DOJ required for hired
- Revenue closure at 'joined' stage. Event logging service.

### Phase 2: Tracker Backend (Feb 2026) - COMPLETE
- **Master Column System:** 58 enterprise columns across 11 categories (Basic Info, Role & Mandate, Contact, Employment, Location, Compensation, Availability, Education, Skills & Evaluation, Submission Intelligence, Process Tracking)
- **Template System:** CRUD for tracker templates with column structure, required fields, custom fields, field types (text/number/currency/date/dropdown), clone support
- **Submission Trackers:** CRUD linked to mandate/client/employer, auto-snapshot template columns
- **Tracker Rows:** Add candidate with auto-fill from profile/application data, inline edit, status management
- **Duplicate Protection:** Same candidate + same mandate blocked (409 error)
- **Download Validation:** Green (all OK) / Yellow (missing fields) / Red (empty) dynamic state
- **Auto-fill:** 20+ fields auto-populated from candidate profile and application data

### Phase 4: Tracker ↔ Pipeline Sync (Feb 2026) - COMPLETE
- **Rule A (Tracker→Pipeline):** Adding candidate to tracker auto-moves to submitted_to_client. Status changes (interview_scheduled→interview, offer_issued→offered, etc.) sync to pipeline
- **Rule B (Pipeline→Tracker):** Pipeline stage changes auto-update all tracker rows for that application
- **Event Logging:** All changes logged to tracker_events with candidateId, mandateId, previousStage, newStage, source, timestamp

### Phase 3: Tracker Frontend UI (Feb 2026) - COMPLETE
- **Tracker List View:** Cards with mandate name, candidate count, creation date
- **Spreadsheet View:** Enterprise-style table with inline editing (click-to-edit, Enter/Escape)
- **Validation Highlighting:** Required fields highlighted in red, missing data shows "Required"
- **Download Button:** Dynamic green/yellow/amber color based on validation status
- **Add Candidate Dialog:** Search and add from mandate's pipeline candidates
- **Status Dropdown:** Per-row status changes that trigger pipeline sync
- **Sidebar Link:** "Submission Tracker" in admin navigation

### Earlier Features (Previously Completed)
- LinkedIn OAuth2 + Job Share + Auto-posting settings
- Google Analytics, Recruitment Expertise page, Client Logo Carousel
- Role-based navigation, SEO URL audit, RSS feed
- CV enhancement, pipeline tracking, revenue engine, blog/SEO

## Key Files
- `backend/services/master_columns.py` — 58 enterprise column definitions
- `backend/services/tracker_sync.py` — Bidirectional sync logic
- `backend/services/pipeline_events.py` — Stage validation, event logging
- `backend/routes/tracker.py` — All tracker CRUD + rows + validation + events
- `frontend/src/pages/admin/SubmissionTrackerPage.jsx` — Full tracker UI
- `frontend/src/lib/api.js` — trackerAPI functions

## Key API Endpoints
- `GET /api/tracker/columns` — Master column definitions
- `POST/GET/PUT/DELETE /api/tracker/templates` — Template CRUD
- `POST /api/tracker/templates/{id}/clone` — Clone template
- `POST/GET/DELETE /api/tracker/trackers` — Tracker CRUD
- `POST/PUT/DELETE /api/tracker/trackers/{id}/rows` — Row operations
- `PUT /api/tracker/trackers/{id}/rows/{rowId}/status` — Status with sync
- `GET /api/tracker/trackers/{id}/validation` — Download validation
- `GET /api/tracker/events` — Audit event history

## Prioritized Backlog
### P1
- **Phase 5:** Revenue Probability + Analytics (probability % per stage, billing/placement fee fields, conversion rate metrics)
### P2
- **Phase 6:** Upload/Export & Polish (Excel/CSV upload with header detection, download as formatted Excel, template auto-detection from uploads)

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Employer: employer@vhc.in / VhcEmployer@2024
- Recruiter: recruiter@vhc.in / VhcRecruiter@2024
