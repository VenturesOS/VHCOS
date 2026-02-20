# Ventures HRD - Talent OS

## Original Problem Statement
Full-stack talent operating system for industrial recruitment, with CV management, ATS-friendly CV generation, pipeline tracking, revenue engine, blog/SEO, and employer/recruiter/candidate portals.

## Architecture
- **Frontend:** React (CRA) + Shadcn/UI + TailwindCSS + Static HTML pages (website/)
- **Backend:** FastAPI + MongoDB Atlas + Cloudflare R2 + Upstash Redis
- **3rd Party:** OpenAI GPT-4o-mini, Resend, Google Tag Manager, Google Analytics (GA4), LinkedIn API (OAuth2 + UGC Posts)

## What's Been Implemented
- CV + Profile Enhancement (profile parity, ATS CV generation, file naming)
- Employer route refactoring (server.py decomposition)
- Pipeline "Joined" stage bug fix
- Candidate Data Bank 500 error fix
- Endpoint stability audit (Redis, R2, MongoDB)
- CV download auth fix (query param token support)
- Google Analytics GA4 (G-MY1EXKECH6) on all public pages
- Recruitment Expertise page (`/recruitment-expertise`)
- Client Logo Carousel on Industries + Home pages
- Role-based menu visibility (Career/Contact)
- SEO URL audit (stale staging URL replaced)
- LinkedIn OAuth2 setup (backend endpoints)
- LinkedIn Job Share button (admin/recruiter/employer portals)
- **LinkedIn Auto-Posting** (Feb 2026):
  - Backend service (`linkedin_service.py`) to post blog articles to LinkedIn company page via UGC Posts API
  - Settings endpoints (`GET/PUT /api/linkedin/settings`) for org ID and auto-post toggle
  - Test post endpoint (`POST /api/linkedin/test-post`)
  - Post history endpoint (`GET /api/linkedin/post-history`)
  - Disconnect endpoint (`DELETE /api/linkedin/disconnect`)
  - Auto-post hook in blog publish flow (manual + scheduled)
  - Admin UI page at `/admin/linkedin-settings` with connection status, settings, RSS info, and post history
  - Sidebar navigation link for LinkedIn settings

## Key Files
- `backend/services/linkedin_service.py` — LinkedIn posting service
- `backend/routes/linkedin.py` — LinkedIn OAuth + settings + auto-posting endpoints
- `backend/routes/blog.py` — Blog publish with LinkedIn auto-post hook
- `backend/services/blog_scheduler.py` — Auto-publish with LinkedIn hook
- `frontend/src/pages/admin/LinkedInSettingsPage.jsx` — LinkedIn settings admin page
- `frontend/src/lib/api.js` — linkedinAPI functions
- `frontend/src/App.js` — Route for /admin/linkedin-settings
- `frontend/src/components/layout/Sidebar.jsx` — LinkedIn nav item

## Prioritized Backlog
- No pending P0/P1/P2 items

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Employer: employer@vhc.in / VhcEmployer@2024
- Recruiter: recruiter@vhc.in / VhcRecruiter@2024
