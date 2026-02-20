# Ventures HRD - Talent OS

## Original Problem Statement
Full-stack talent operating system for industrial recruitment, with CV management, ATS-friendly CV generation, pipeline tracking, revenue engine, blog/SEO, and employer/recruiter/candidate portals.

## Architecture
- **Frontend:** React (CRA) + Shadcn/UI + TailwindCSS + Static HTML pages (website/)
- **Backend:** FastAPI + MongoDB Atlas + Cloudflare R2 + Upstash Redis
- **3rd Party:** OpenAI GPT-4o-mini, Resend, Google Tag Manager, Google Analytics (GA4), LinkedIn API

## What's Been Implemented

### Phase 1: Pipeline Restructure (Feb 2026) - COMPLETE
- **New stage order:** applied → shortlisted → submitted_to_client → interview → offered → hired → joined
- **Parallel statuses:** rejected, on_hold
- **Removed stages:** over_budget, not_qualified
- **Validation rules:**
  - Cannot move to hired without offered
  - Cannot move to joined without hired
  - Joined locks previous stages (no going back)
  - DOJ required for hired stage
- **Revenue closure:** Moved from 'hired' to 'joined' stage
- **New `hired` revenue endpoint:** POST /api/revenue/hired/{app_id} with DOJ
- **Event logging service:** pipeline_events.py with validate_stage_transition()
- **Updated all 3 pipeline UIs:** Admin, Employer, Recruiter
- **Updated all backend routes:** admin.py, employer_routes.py, teams.py, candidates.py, commercials.py, revenue.py, applications.py

### Earlier Features (Previously Completed)
- LinkedIn OAuth2 + Job Share + Auto-posting settings
- Google Analytics, Recruitment Expertise page, Client Logo Carousel
- Role-based navigation, SEO URL audit, RSS feed
- CV enhancement, pipeline tracking, revenue engine, blog/SEO

## Key Files (Phase 1)
- `backend/services/pipeline_events.py` — Stage validation, event logging, canonical stage order
- `backend/routes/applications.py` — Stage transition enforcement
- `backend/routes/revenue.py` — New hired endpoint
- `backend/routes/admin.py` — Updated pipeline + stats
- `frontend/src/pages/admin/AdminPipelinePage.jsx` — Updated stages + hired dialog
- `frontend/src/pages/employer/EmployerPipelinePage.jsx` — Updated stages
- `frontend/src/pages/recruiter/PipelinePage.jsx` — Updated stages

## Prioritized Backlog

### P0 — In Progress
- **Phase 2:** Tracker Backend Foundations (submission_trackers, tracker_templates, tracker_events collections, template CRUD API, master column system)
- **Phase 4:** Tracker ↔ Pipeline Sync (moved earlier per user request)
- **Phase 3:** Tracker Frontend UI (spreadsheet-like experience)

### P1
- **Phase 5:** Revenue Probability + Analytics (probability % per stage, billing/placement fee fields, conversion metrics)

### P2
- **Phase 6:** Upload/Export & Polish (Excel/CSV upload, download, template auto-detection)

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Employer: maneet@vhc.in / 12345678
- Recruiter: jatin@vhc.in / 12345678
