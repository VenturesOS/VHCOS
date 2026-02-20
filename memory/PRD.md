# Ventures HRD - Talent OS

## Original Problem Statement
Full-stack talent operating system for industrial recruitment, with CV management, ATS-friendly CV generation, pipeline tracking, revenue engine, blog/SEO, and employer/recruiter/candidate portals. Extended with a fully integrated Client Submission Tracker System and redesigned Recruitment Pipeline Architecture.

## Architecture
- **Frontend:** React (CRA) + Shadcn/UI + TailwindCSS + Recharts + react-data-grid + Static HTML pages (website/)
- **Backend:** FastAPI + MongoDB Atlas + Cloudflare R2 + Upstash Redis
- **3rd Party:** OpenAI GPT-4o-mini, Resend, Google Tag Manager, Google Analytics (GA4), LinkedIn API

## What's Been Implemented

### Phase 1: Pipeline Restructure (Feb 2026) - COMPLETE
- New stage order: applied > shortlisted > submitted_to_client > interview > offered > hired > joined
- Validation rules: can't skip stages, joined locks, DOJ required for hired
- Revenue closure at 'joined' stage. Event logging service.

### Phase 2: Tracker Backend (Feb 2026) - COMPLETE
- Master Column System: 58 enterprise columns across 11 categories
- Template System: CRUD with column structure, required fields, custom fields
- Submission Trackers: CRUD linked to mandate/client/employer
- Tracker Rows: Add candidate with auto-fill, inline edit, status management
- Duplicate Protection: 409 for same candidate + same mandate
- Download Validation: Green/Yellow/Red dynamic state

### Phase 3: Tracker Frontend UI (Feb 2026) - COMPLETE
- Tracker List View with cards, Spreadsheet View with inline editing
- Validation Highlighting, Dynamic Download Button color
- Add Candidate Dialog, Status Dropdown with pipeline sync
- Sidebar Link: "Submission Tracker" in admin navigation

### Phase 4: Tracker <> Pipeline Sync (Feb 2026) - COMPLETE
- Bidirectional sync between tracker and pipeline
- Event logging for all changes

### Phase 5: Analytics Dashboard (Feb 2026) - COMPLETE
- **Pipeline Conversion:** Funnel visualization with stage-by-stage conversion rates
- **Revenue Intelligence:** Forecast vs realized, probability-weighted pipeline, by-stage breakdown
- **Recruiter Performance:** Submissions, conversions, revenue per recruiter
- **Mandate Performance:** Per-mandate metrics with submission rates
- Enhanced Admin Analytics page with 4 tabs: Overview, Pipeline Funnel, Revenue, Performance
- Backend endpoints: pipeline-conversion, revenue-forecast, recruiter-performance, mandate-performance

### Phase 6: Excel Import/Export (Feb 2026) - COMPLETE
- Excel export as formatted .xlsx with styles, validation highlighting
- CSV/XLSX upload with auto-header mapping to master columns
- Both tested and verified working

### Client-Facing View (Feb 2026) - COMPLETE
- Read-only tracker view for employers at /employer/submission-tracker

### Sidebar Reorganization (Feb 2026) - COMPLETE
- Reordered admin sidebar: Dashboard > Jobs > Pipeline > Submission Tracker > Analytics > Revenue > Candidates...
- Submission Tracker now visible at position 4 without scrolling

### Earlier Features (Previously Completed)
- LinkedIn OAuth2 + Job Share + Auto-posting settings
- Google Analytics, Recruitment Expertise page, Client Logo Carousel
- Role-based navigation, SEO URL audit, RSS feed
- CV enhancement, pipeline tracking, revenue engine, blog/SEO

## Key Files
- `backend/routes/tracker.py` - All tracker CRUD + rows + validation + export/import
- `backend/routes/analytics.py` - Pipeline conversion, revenue, recruiter/mandate analytics
- `backend/services/master_columns.py` - 58 enterprise column definitions
- `backend/services/tracker_sync.py` - Bidirectional sync logic
- `backend/services/pipeline_events.py` - Stage validation, event logging, revenue probability
- `frontend/src/pages/admin/AdminAnalyticsPage.jsx` - 4-tab analytics (Overview, Pipeline, Revenue, Performance)
- `frontend/src/pages/admin/SubmissionTrackerPage.jsx` - Tracker spreadsheet UI
- `frontend/src/pages/employer/EmployerTrackerPage.jsx` - Client-facing tracker
- `frontend/src/components/layout/Sidebar.jsx` - Reordered navigation

## Key API Endpoints
- `GET /api/tracker/columns` - Master column definitions
- `POST/GET/PUT/DELETE /api/tracker/templates` - Template CRUD
- `POST/GET/DELETE /api/tracker/trackers` - Tracker CRUD
- `POST/PUT/DELETE /api/tracker/trackers/{id}/rows` - Row operations
- `PUT /api/tracker/trackers/{id}/rows/{rowId}/status` - Status with sync
- `GET /api/tracker/trackers/{id}/validation` - Download validation
- `GET /api/tracker/trackers/{id}/export` - Excel export
- `POST /api/tracker/trackers/{id}/upload` - Excel/CSV import
- `GET /api/tracker/events` - Audit event history
- `GET /api/analytics/pipeline-conversion` - Stage conversion rates
- `GET /api/analytics/revenue-forecast` - Revenue forecast
- `GET /api/analytics/recruiter-performance` - Recruiter metrics
- `GET /api/analytics/mandate-performance` - Mandate metrics

## Prioritized Backlog
### P1
- Performance optimization for /api/analytics/admin endpoint (~11s response time)
- Create employer test account (employer@vhc.in doesn't exist)

### P2
- Client Dashboards enhancements
- AI-driven Analytics and Insights
- Advanced Revenue Intelligence features
- Automation workflows based on pipeline events

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Employer: employer@vhc.in / VhcEmployer@2024 (NOTE: account may not exist)
- Recruiter: recruiter@vhc.in / VhcRecruiter@2024
