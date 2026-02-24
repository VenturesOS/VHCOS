# VHC Talent OS — Product Requirements Document

## Original Problem Statement
Full-stack React + FastAPI recruitment management platform for Ventures HRD Consulting. Features include job management, candidate tracking, submission trackers, pipeline management, AI-powered candidate matching, Chrome extension for Naukri integration, blog engine, SEO tools, revenue dashboards, and compliance management.

## Core Architecture
- **Frontend**: React (CRA with CRACO) with Shadcn/UI, React Router
- **Backend**: FastAPI with MongoDB Atlas
- **Auth**: JWT-based, role-based access control (admin, employer, recruiter, candidate)
- **3rd Party**: Cloudflare Turnstile, Cloudflare Zero Trust, MongoDB Atlas, Upstash Redis, Resend Email, OpenAI GPT-4o-mini, Cloudflare R2

## User Roles
- **Admin**: Full system access, sees all data
- **Employer**: Company-specific job/candidate management, filtered tracker visibility
- **Recruiter**: Mandate-based recruitment operations, filtered tracker visibility
- **Candidate**: Job browsing, applications, profile management

## Key Features Implemented
- Job CRUD with approval workflows
- Candidate pipeline management
- Submission Tracker (full CRUD for admin, employer, recruiter) with role-based visibility filtering
- AI candidate matching & screening
- Chrome Extension for Naukri (v3.9.2)
- Blog engine with SEO optimization
- Revenue dashboard
- Compliance (DPDP) management
- Bulk import/export
- Team hierarchy management

## Recent Changes

### Feb 24, 2026 — Deployment Fix
- Removed temporary emergency hardcoded MongoDB override from `backend/config.py`
- Changed `load_dotenv(override=True)` to `load_dotenv()` so K8s-injected env vars take precedence
- MongoDB URI and DB name now read from environment variables (`MONGO_URL`, `DB_NAME`)
- Deployment agent re-scan: All checks passed, status READY

### Feb 24, 2026 — Submission Tracker Role Access + Visibility Filtering
1. **Role Access**: Granted employer and recruiter full CRUD access to Submission Tracker
2. **Visibility Filtering**: Admin sees all trackers, recruiters see own + assigned mandates, employers see own + posted mandates
3. **Access Control**: `GET /trackers/{id}` returns 403 for unauthorized users

## Known Technical Debt
- None currently (emergency override has been removed)

## Backlog (Prioritized)
- P1: AI-driven Analytics and Insights
- P2: Client Dashboard enhancements
- P3: Advanced Revenue Intelligence
- P4: LinkedIn Auto-Posting (blocked on API scope approval)
- P4: Training Manual PDF refinement

## Key Files
- `backend/config.py` — Environment-based config (fixed)
- `backend/routes/tracker.py` — Submission tracker API with role-based filtering
- `frontend/src/App.js` — Frontend routing
- `frontend/src/components/layout/Sidebar.jsx` — Navigation

## Test Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Recruiter: yamini@vhc.in / VhcAdmin@2024

## Test Reports
- `/app/test_reports/iteration_88.json` — Role access tests (100% pass)
- `/app/test_reports/iteration_89.json` — Visibility filtering tests (100% pass)
