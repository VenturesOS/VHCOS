# Ventures HRD - Talent OS

## Original Problem Statement
Full-stack talent operating system for industrial recruitment, with CV management, ATS-friendly CV generation, pipeline tracking, revenue engine, blog/SEO, and employer/recruiter/candidate portals.

## Architecture
- **Frontend:** React (CRA) + Shadcn/UI + TailwindCSS
- **Backend:** FastAPI + MongoDB Atlas + Cloudflare R2 + Upstash Redis
- **3rd Party:** OpenAI GPT-4o-mini, Resend, Google Tag Manager, Google Analytics (GA4)

## What's Been Implemented
- CV + Profile Enhancement (profile parity, ATS CV generation, file naming)
- Employer route refactoring (server.py decomposition)
- Pipeline "Joined" stage bug fix
- Candidate Data Bank 500 error fix
- Endpoint stability audit (Redis, R2, MongoDB)
- CV download auth fix (query param token support)
- **Google Analytics GA4 (G-MY1EXKECH6)** on all public pages (landing, careers, blogs, job pages) — excluded from portal pages (admin/recruiter/employer/candidate dashboards). Added to both static `Index.html` and React app via `GoogleAnalytics` component.

## Prioritized Backlog
- No pending P0/P1/P2 items. All requested features complete.

## Key Files
- `frontend/src/components/GoogleAnalytics.jsx` — GA4 tracking component (public pages only)
- `frontend/public/website/Index.html` — Static landing page with GA4 gtag
- `frontend/src/App.js` — Main router with GoogleAnalytics component
- `backend/routes/candidates.py` — CV download endpoints
- `backend/services/ats_cv_generator.py` — ATS PDF generation
- `backend/routes/employer_routes.py` — Extracted employer routes

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Employer: employer@vhc.in / VhcEmployer@2024
- Recruiter: recruiter@vhc.in / VhcRecruiter@2024
