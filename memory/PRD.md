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
- Full responsive design (mobile/tablet/desktop) - React dashboard + static website
- Authentication (JWT-based)
- Scroll animations & micro-interactions on static website (Feb 2026)
- P1 Shortlist bug fix (Feb 2026)

## Session Changes (Feb 15, 2026)
1. MongoDB Atlas Connection: RESOLVED (transient SSL issue)
2. Static website mobile responsiveness: FIXED (7 pages, hamburger menu, CSS overrides)
3. UI/UX Audit: FIXED (services grid, candidate bank search, tab-content breakpoint)
4. Scroll Animations: ADDED (reveal-on-scroll, stagger, parallax, back-to-top, hover effects)
5. P1 Shortlist Bug: FIXED (button no longer disabled, highlighted job picker in modal)

## Prioritized Backlog
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
- `/frontend/public/website/style.css` - Master responsive CSS + animations
- `/frontend/public/website/scroll-animations.js` - Scroll reveal, back-to-top, parallax
- `/frontend/public/website/mobile-menu.js` - Hamburger menu functionality
- `/frontend/public/website/*.html` - 7 static HTML pages
- `/frontend/src/pages/employer/FindCandidatesPage.jsx` - AI matching + shortlist (P1 fix)
- `/frontend/src/pages/employer/EmployerCandidateBankPage.jsx` - Employer candidate bank
- `/frontend/src/pages/recruiter/RecruiterCandidateBankPage.jsx` - Recruiter candidate bank
- `/frontend/src/components/layout/Sidebar.jsx` - React dashboard hamburger menu

## Test Reports
- `/app/test_reports/iteration_58.json` - Mobile responsiveness (32/32 passed)
- `/app/test_reports/iteration_59.json` - UI/UX audit fixes (17/17 passed)
