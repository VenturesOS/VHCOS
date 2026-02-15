# VHC Talent OS - Product Requirements Document

## Original Problem Statement
Full-stack recruitment application (React, FastAPI, MongoDB) for candidate sourcing, screening, and management. Features include candidate data bank, standard/AI-powered search, admin analytics dashboard, and Chrome extension for profile sourcing.

## Architecture
- **Frontend:** React + Tailwind CSS + Shadcn UI (port 3000)
- **Backend:** FastAPI (port 8001)
- **Database:** MongoDB Atlas
- **Static Website:** HTML/CSS/JS at `/frontend/public/website/`
- **Integrations:** OpenAI GPT-4o-mini, Cloudflare R2, Resend email, Upstash Redis

## What's Been Implemented
- Full candidate CRUD and data bank
- Job mandate management
- AI-powered candidate search and screening
- Admin analytics dashboard
- Chrome extension for sourcing profiles
- Email/WhatsApp notifications
- Full responsive design (mobile/tablet/desktop) - React dashboard
- Static website responsiveness (all 7 pages) - Feb 2026
- Authentication (JWT-based)

## Current Status (Feb 2026)
- **MongoDB Atlas Connection:** RESOLVED
- **React Dashboard Responsiveness:** COMPLETE
- **Static Website Responsiveness:** COMPLETE - all 7 pages fixed
- **UI/UX Audit:** COMPLETE - 17/17 tests passed across all viewports

## UI/UX Fixes Applied (Feb 2026)
- Services page: Added repeat(2) CSS override for mobile grid stacking
- Index.html: Added 480px breakpoint for tab-content single column
- Employer + Recruiter Candidate Bank: Search row responsive stacking
- All static pages: Class-based headers, hamburger menus, style.css + mobile-menu.js linked

## Prioritized Backlog
### P1
- Fix AI Screening Shortlist Bug (disabled when JD pasted/uploaded, no job_id)

### P2
- External Password Reset Feature ("Forgot Password" flow)

### P3
- Refactor `content.js` (Chrome extension maintainability)
- AI Search Phase 2 Upgrade (hybrid routing, configurable model)

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Employer: ajit@vhc.in / 12345678
- Recruiter: jatin@vhc.in / 12345678

## Key Files
- `/frontend/public/website/style.css` - Master responsive CSS for static site
- `/frontend/public/website/mobile-menu.js` - Hamburger menu functionality
- `/frontend/public/website/*.html` - 7 static HTML pages
- `/frontend/src/components/layout/Sidebar.jsx` - React dashboard hamburger menu
- `/frontend/src/pages/employer/EmployerCandidateBankPage.jsx` - Employer candidate bank
- `/frontend/src/pages/recruiter/RecruiterCandidateBankPage.jsx` - Recruiter candidate bank

## Test Reports
- `/app/test_reports/iteration_58.json` - Initial mobile responsiveness (32/32 passed)
- `/app/test_reports/iteration_59.json` - UI/UX audit fixes (17/17 passed)
