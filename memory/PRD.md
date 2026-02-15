# VHC Talent OS - Product Requirements Document

## Original Problem Statement
A full-stack recruitment application (React, FastAPI, MongoDB) with a public-facing static website and an internal portal for Admin, Employer, Recruiter, and Candidate roles. The platform supports AI-powered candidate matching, job management, pipeline tracking, and analytics.

## Core Requirements
1. **Public Website** — Responsive static site (7+ pages) with contact form, careers page, SEO
2. **Authentication** — JWT-based multi-role auth (Admin, Employer, Recruiter, Candidate)
3. **Job Management** — CRUD, JD parsing, career page, shareable links
4. **Candidate Management** — Candidate bank, CV parsing, profile management
5. **AI Matching** — Quick match, full AI match, AI search with natural language
6. **Pipeline** — Kanban-style application tracking with stage transitions
7. **Analytics** — Admin and employer dashboards with revenue tracking
8. **Chrome Extension** — Naukri profile scraping integration

## Architecture
- **Frontend:** React + Tailwind + Shadcn/UI (port 3000)
- **Backend:** FastAPI + Motor (async MongoDB) (port 8001)
- **Database:** MongoDB Atlas (vhc_talent_os)
- **Storage:** Cloudflare R2 for files
- **AI:** OpenAI GPT-4o-mini for screening/matching

## What's Been Implemented

### Phase 1 (Previous Sessions)
- Full authentication system with role-based access
- Job CRUD with JD parsing and career pages
- Candidate bank with CV upload/parsing
- AI matching (quick + full AI modes)
- Pipeline management with stage transitions
- Analytics dashboards (Admin + Employer)
- Chrome extension for Naukri profile scraping
- Teams, referrals, commercials management
- Bug reporting and system health monitoring

### Phase 2 (Previous Fork)
- MongoDB Atlas SSL connection fix (pymongo[srv] + certifi)
- Static website full responsiveness (7 pages)
- Hamburger menu for mobile
- Comprehensive UI/UX audit and fixes
- Micro-animations (fade-in-on-scroll, hover effects, back-to-top)
- AI Screening shortlist bug fix

### Phase 3 (Current Session - Feb 15, 2026)
- **Contact Form Backend** — `/api/contact-submission` stores submissions in MongoDB; admin dashboard page at `/admin/contact-submissions` with view/filter/status update/delete
- **AI Screening Actions** — "View Full Profile" and "Add as Applicant" buttons on AI search results in FindCandidatesPage
- **SEO Meta Tags Audit** — Added Open Graph and Twitter Card meta tags to all static pages (about, services, industries, careers, global-hiring, sitemap, contact)

## Prioritized Backlog

### P0 — None (all critical items resolved)

### P1
- Password Reset Feature — "Forgot Password" flow

### P2
- Refactor Chrome extension `content.js` into smaller modules
- AI Search Phase 2 — hybrid routing, configurable model selection
- Refactor `FindCandidatesPage.jsx` — break into smaller components

### P3
- Email notifications for contact form submissions (integrate Resend/SendGrid)
- Advanced analytics with date range filtering
- Candidate portal enhancements

## Key Files
- `/app/backend/server.py` — Main FastAPI app with route registration
- `/app/backend/config.py` — MongoDB, R2, JWT configuration
- `/app/backend/routes/contact.py` — Contact form API endpoints
- `/app/frontend/src/pages/employer/FindCandidatesPage.jsx` — AI screening with action buttons
- `/app/frontend/src/pages/admin/ContactSubmissionsPage.jsx` — Admin contact submissions page
- `/app/public-website/vhc-website/` — Static website files

## Test Credentials
- Admin: `admin@vhc.in` / `VhcAdmin@2024`
- Employer: `ajit@vhc.in` / `12345678`
- Recruiter: `jatin@vhc.in` / `12345678`
