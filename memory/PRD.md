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

### Phase 4: Tracker <> Pipeline Sync (Feb 2026) - COMPLETE
- Bidirectional sync between tracker and pipeline
- Event logging for all changes

### Phase 5: Analytics Dashboard (Feb 2026) - COMPLETE
- 4-tab analytics page: Overview, Pipeline Funnel, Revenue, Performance
- Pipeline Conversion: Funnel visualization with stage-by-stage conversion rates
- Revenue Intelligence: Forecast vs realized, probability-weighted pipeline, by-stage breakdown
- Recruiter Performance: Submissions, conversions, revenue per recruiter
- Mandate Performance: Per-mandate metrics with submission rates
- Date Range Filters on Pipeline Funnel and Revenue tabs (7d/30d/90d/YTD/Custom presets)

### Phase 6: Excel Import/Export (Feb 2026) - COMPLETE
- Excel export as formatted .xlsx with styles, validation highlighting
- CSV/XLSX upload with auto-header mapping to master columns

### Client-Facing View (Feb 2026) - COMPLETE
- Read-only tracker view for employers at /employer/submission-tracker

### Stabilization (Feb 2026) - COMPLETE
- Analytics API optimized from 11s to ~2s via asyncio.gather parallelization
- Employer test account created (employer@vhc.in / VhcEmployer@2024)
- Sidebar reorganized: Submission Tracker at position 4 (visible without scrolling)

### Earlier Features (Previously Completed)
- LinkedIn OAuth2 + Job Share + Auto-posting settings
- Google Analytics, Recruitment Expertise page, Client Logo Carousel
- Role-based navigation, SEO URL audit, RSS feed
- CV enhancement, pipeline tracking, revenue engine, blog/SEO

## Key Files
- `backend/routes/tracker.py` - All tracker CRUD + rows + validation + export/import
- `backend/routes/analytics.py` - Pipeline conversion, revenue, recruiter/mandate analytics
- `backend/services/analytics_service.py` - Optimized with asyncio.gather
- `backend/services/master_columns.py` - 58 enterprise column definitions
- `backend/services/tracker_sync.py` - Bidirectional sync logic
- `backend/services/pipeline_events.py` - Stage validation, event logging, revenue probability
- `frontend/src/pages/admin/AdminAnalyticsPage.jsx` - 4-tab analytics with date filters
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
- `GET /api/analytics/pipeline-conversion?from_date=&to_date=` - Stage conversion rates
- `GET /api/analytics/revenue-forecast?from_date=&to_date=` - Revenue forecast
- `GET /api/analytics/recruiter-performance` - Recruiter metrics
- `GET /api/analytics/mandate-performance` - Mandate metrics

## Prioritized Backlog
### P2
- Client Dashboards enhancements
- AI-driven Analytics and Insights
- Advanced Revenue Intelligence features
- Automation workflows based on pipeline events

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Employer: employer@vhc.in / VhcEmployer@2024
- Recruiter: recruiter@vhc.in / VhcRecruiter@2024
