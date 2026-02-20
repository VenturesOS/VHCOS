# Ventures HRD - Talent OS

## Original Problem Statement
Full-stack talent operating system for industrial recruitment, with CV management, ATS-friendly CV generation, pipeline tracking, revenue engine, blog/SEO, and employer/recruiter/candidate portals. Extended with a fully integrated Client Submission Tracker System and redesigned Recruitment Pipeline Architecture.

## Architecture
- **Frontend:** React (CRA) + Shadcn/UI + TailwindCSS + Recharts + react-data-grid + Static HTML pages (website/)
- **Backend:** FastAPI + MongoDB Atlas + Cloudflare R2 + Upstash Redis
- **3rd Party:** OpenAI GPT-4o-mini, Resend, Google Tag Manager, Google Analytics (GA4), LinkedIn API

## What's Been Implemented

### Phase 1: Pipeline Restructure - COMPLETE
- 7-stage pipeline: applied > shortlisted > submitted_to_client > interview > offered > hired > joined
- Validation rules, revenue closure at 'joined', event-based logging

### Phase 2: Tracker Backend - COMPLETE
- Master Column System: 58 enterprise columns across 11 categories
- Template System with custom columns, field types (text/number/currency/date/dropdown)
- Submission Trackers CRUD linked to mandate/client/employer
- Tracker Row operations, duplicate protection, download validation

### Phase 3: Tracker Frontend UI - COMPLETE
- **Multi-step Tracker Creation Wizard** (NEW - 5 steps):
  - Step 1: Basic Setup (name, mandate, template mode: existing/new/upload)
  - Step 2: Column Selection with categorized dropdown, search, alphabetical ordering
  - Step 3: Custom Columns with field types, dropdown options, required toggle
  - Step 4: Required Field Configuration (Required/Optional switches)
  - Step 5: Review with full summary before creation
- Template Upload: Parse XLSX/CSV, auto-map headers to master columns
- Spreadsheet View with inline editing, validation highlighting
- Dynamic Download Button (Green/Yellow/Red)

### Phase 4: Tracker <> Pipeline Sync - COMPLETE
- Bidirectional sync, event logging

### Phase 5: Analytics Dashboard - COMPLETE
- 4-tab analytics: Overview, Pipeline Funnel, Revenue, Performance
- Date Range Filters (7d/30d/90d/YTD/Custom) on Pipeline Funnel and Revenue tabs
- Analytics API optimized from 11s to ~2s with asyncio.gather

### Phase 6: Excel Import/Export - COMPLETE
- Excel export as .xlsx, CSV/XLSX upload with auto-mapping

### Client-Facing View - COMPLETE
- Read-only tracker view for employers at /employer/submission-tracker

### Stabilization - COMPLETE
- Employer test account (employer@vhc.in / VhcEmployer@2024)
- Sidebar reorganized for better visibility

## Key Files
- `frontend/src/components/admin/CreateTrackerWizard.jsx` - NEW: Multi-step wizard
- `backend/routes/tracker.py` - All tracker CRUD + parse-template-file endpoint
- `backend/services/master_columns.py` - 58 enterprise column definitions
- `frontend/src/pages/admin/AdminAnalyticsPage.jsx` - 4-tab analytics with date filters
- `frontend/src/pages/admin/SubmissionTrackerPage.jsx` - Tracker list + spreadsheet UI

## Key API Endpoints
- `POST /api/tracker/parse-template-file` - Parse XLSX/CSV for template creation
- `POST /api/tracker/templates` - Create template with custom columns
- `POST /api/tracker/trackers` - Create tracker linked to template
- `GET /api/tracker/columns` - Master column definitions (58 columns, 11 categories)
- `GET /api/analytics/pipeline-conversion?from_date=&to_date=` - Pipeline funnel
- `GET /api/analytics/revenue-forecast?from_date=&to_date=` - Revenue forecast

## Prioritized Backlog
### P2
- Client Dashboard enhancements
- AI-driven Analytics and Insights
- Advanced Revenue Intelligence features
- Automation workflows based on pipeline events

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Employer: employer@vhc.in / VhcEmployer@2024
- Recruiter: recruiter@vhc.in / VhcRecruiter@2024
