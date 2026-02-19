# Ventures HRD - Talent OS

## Original Problem Statement
Full-stack talent operating system for industrial recruitment, with CV management, ATS-friendly CV generation, pipeline tracking, revenue engine, blog/SEO, and employer/recruiter/candidate portals.

## Architecture
- **Frontend:** React (CRA) + Shadcn/UI + TailwindCSS + Static HTML pages (website/)
- **Backend:** FastAPI + MongoDB Atlas + Cloudflare R2 + Upstash Redis
- **3rd Party:** OpenAI GPT-4o-mini, Resend, Google Tag Manager, Google Analytics (GA4)

## What's Been Implemented
- CV + Profile Enhancement (profile parity, ATS CV generation, file naming)
- Employer route refactoring (server.py decomposition)
- Pipeline "Joined" stage bug fix
- Candidate Data Bank 500 error fix
- Endpoint stability audit (Redis, R2, MongoDB)
- CV download auth fix (query param token support)
- Google Analytics GA4 (G-MY1EXKECH6) on all public pages
- **Recruitment Expertise page** (`/recruitment-expertise`) — premium enterprise-style page with:
  - Executive hero section with CTAs
  - Sticky section navigation (Executive Search / Specialist Hiring / Talent Advisory)
  - Credibility block with 4 trust cards
  - 3 main content sections with two-column layout, process timelines, and sidebar cards
  - CTA bands between sections (all linked to /contact leads form)
  - FAQ accordion section
  - Final executive close CTA
  - Full responsive mobile layout
  - Homepage "Learn More" links updated to deep-link with anchors

## Key Files
- `frontend/public/website/recruitment-expertise.html` — New recruitment expertise page
- `frontend/public/website/Index.html` — Homepage (Learn More links updated)
- `frontend/craco.config.js` — URL mapping for /recruitment-expertise
- `frontend/src/components/GoogleAnalytics.jsx` — GA4 tracking component
- `backend/routes/candidates.py` — CV download endpoints
- `backend/services/ats_cv_generator.py` — ATS PDF generation
- `backend/routes/employer_routes.py` — Extracted employer routes

## Prioritized Backlog
- No pending P0/P1/P2 items

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Employer: employer@vhc.in / VhcEmployer@2024
- Recruiter: recruiter@vhc.in / VhcRecruiter@2024
