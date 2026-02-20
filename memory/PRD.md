# Ventures HRD - Talent OS

## Original Problem Statement
Full-stack talent operating system for industrial recruitment with pipeline tracking, submission tracker, analytics, revenue engine, and multi-portal architecture.

## Architecture
- **Frontend:** React (CRA) + Shadcn/UI + TailwindCSS + Recharts + react-data-grid
- **Backend:** FastAPI + MongoDB Atlas + Cloudflare R2 + Upstash Redis
- **3rd Party:** OpenAI GPT-4o-mini, Resend, Google Tag Manager, LinkedIn API

## What's Been Implemented
- 7-stage Pipeline (applied→joined) with validation, event logging, revenue closure
- Submission Tracker: Master columns (58), templates, CRUD, spreadsheet UI, bidirectional sync
- Multi-step Tracker Creation Wizard (5 steps: setup, columns, custom, required, review)
- Duplicate Tracker feature (clone structure to new mandate)
- Template Upload: Parse XLSX/CSV, auto-map headers
- Client-facing read-only tracker view at /employer/submission-tracker
- Analytics Dashboard with 4 tabs: Overview, Pipeline Funnel, Revenue, Performance
- **Unified Filter Bar** (Employer, Team, Recruiter, Date presets + custom) shared across ALL tabs
- **Combined PDF Export** (Revenue → Pipeline → Performance → Overview) in single report
- Excel import/export, validation-aware download states
- Analytics API optimized from 11s to ~2s

## Key Files
- `frontend/src/pages/admin/AdminAnalyticsPage.jsx` - 4-tab analytics with unified filters + export
- `frontend/src/components/admin/CreateTrackerWizard.jsx` - Multi-step wizard
- `backend/routes/analytics.py` - All analytics endpoints + combined PDF export
- `backend/services/analytics_pdf.py` - PDF generation (single + combined)
- `backend/routes/tracker.py` - Tracker CRUD, rows, sync, export/import, duplicate

## Key API Endpoints
- `GET /api/analytics/export-combined-pdf` - Combined PDF (all 4 sections)
- `GET /api/analytics/pipeline-conversion?from_date=&to_date=`
- `GET /api/analytics/revenue-forecast?from_date=&to_date=`
- `GET /api/analytics/recruiter-performance`
- `GET /api/analytics/mandate-performance`
- `POST /api/tracker/trackers/{id}/duplicate`
- `POST /api/tracker/parse-template-file`

## Prioritized Backlog
### P2
- Client Dashboard enhancements
- AI-driven Analytics and Insights
- Advanced Revenue Intelligence
- Automation workflows based on pipeline events

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Employer: employer@vhc.in / VhcEmployer@2024
- Recruiter: recruiter@vhc.in / VhcRecruiter@2024
