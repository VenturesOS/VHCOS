# VHC Talent OS — Product Requirements Document

## Original Problem Statement
Full-stack React + FastAPI recruitment management platform for Ventures HRD Consulting. Features include job management, candidate tracking, submission trackers, pipeline management, AI-powered candidate matching, Chrome extension for Naukri integration, blog engine, SEO tools, revenue dashboards, and compliance management.

## Core Architecture
- **Frontend**: React (CRA) with Shadcn/UI, React Router
- **Backend**: FastAPI with MongoDB Atlas
- **Auth**: JWT-based, role-based access control (admin, employer, recruiter, candidate)
- **3rd Party**: Cloudflare Turnstile, Cloudflare Zero Trust, MongoDB Atlas, Upstash Redis, Resend Email, OpenAI GPT-4o-mini

## User Roles
- **Admin**: Full system access
- **Employer**: Company-specific job/candidate management
- **Recruiter**: Mandate-based recruitment operations
- **Candidate**: Job browsing, applications, profile management

## Key Features Implemented
- Job CRUD with approval workflows
- Candidate pipeline management
- Submission Tracker (full CRUD for admin, employer, recruiter)
- AI candidate matching & screening
- Chrome Extension for Naukri (v3.9.2)
- Blog engine with SEO optimization
- Revenue dashboard
- Compliance (DPDP) management
- Bulk import/export
- Team hierarchy management

## Recent Changes (Feb 24, 2026)
- **Submission Tracker Access**: Granted employer and recruiter roles full CRUD access to Submission Tracker (previously admin-only). Updated 15 backend routes in `tracker.py`, frontend routing in `App.js`, and sidebar navigation in `Sidebar.jsx`.

## Known Technical Debt
- **P0 (BLOCKED)**: Temporary emergency hardcoded MongoDB override in `backend/config.py`. Awaiting Emergent Support to disable managed MongoDB auto-binding before this can be removed.

## Backlog (Prioritized)
- P1: AI-driven Analytics and Insights
- P2: Client Dashboard enhancements
- P3: Advanced Revenue Intelligence
- P4: LinkedIn Auto-Posting (blocked on API scope approval)
- P4: Training Manual PDF refinement
- P5: Chrome extension backup files organization

## Key Files
- `backend/config.py` — Contains temporary DB override (critical)
- `backend/routes/tracker.py` — Submission tracker API
- `frontend/src/App.js` — Frontend routing
- `frontend/src/components/layout/Sidebar.jsx` — Navigation
- `frontend/src/pages/admin/SubmissionTrackerPage.jsx` — Full CRUD tracker page

## Test Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Recruiter: yamini@vhc.in / VhcAdmin@2024
- Employer accounts: maneet@vhc.in (password differs from admin)
