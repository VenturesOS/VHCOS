# VHC Talent OS - Product Requirements Document

## Original Problem Statement
Full-stack recruitment application (React, FastAPI, MongoDB) for candidate sourcing, screening, and management. Features include candidate data bank, standard/AI-powered search, admin analytics dashboard, and Chrome extension for profile sourcing.

## Architecture
- **Frontend:** React + Tailwind CSS + Shadcn UI (port 3000)
- **Backend:** FastAPI (port 8001)
- **Database:** MongoDB Atlas
- **Integrations:** OpenAI GPT-4o-mini, Cloudflare R2, Resend email, Upstash Redis

## What's Been Implemented
- Full candidate CRUD and data bank
- Job mandate management
- AI-powered candidate search and screening
- Admin analytics dashboard
- Chrome extension for sourcing profiles
- Email/WhatsApp notifications
- Full responsive design (mobile/tablet/desktop) - tested 100% pass
- Authentication (JWT-based)

## Current Status (Feb 2026)
- **MongoDB Atlas Connection:** RESOLVED - was transient SSL issue, now working
- **Responsiveness:** COMPLETE - all pages responsive

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
