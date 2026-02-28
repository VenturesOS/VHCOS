# VHC Talent OS - Product Requirements Document

## Product Overview
VHC Talent OS is a comprehensive recruitment management platform for Ventures HRD Consulting, serving employers, recruiters, candidates, and administrators.

## Architecture
- **Frontend**: React (CRA) + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB Atlas (cluster0.vuhdiod.mongodb.net) - external
- **AI**: OpenAI GPT-4o-mini via centralized LLM service
- **Storage**: Cloudflare R2 (credentials validated)

## Core Features (Implemented)

### Authentication & Users
- JWT-based auth with role-based access (admin, recruiter, employer, candidate)
- Registration with notice_period, current_ctc, expected_ctc collection
- Zero Trust middleware for team-based access

### Candidate Management
- Candidate Bank (`/api/candidate-bank`) - 1800+ candidates with pagination/search
- Candidate Profiles (`/api/candidates`) - registered candidate profiles
- Naukri profile viewer, batch import, browser extension v4.2.0
- **Candidate Edit** - Profile editing with mandatory fields (salary, notice, location, experience)
- **PUT /salary-notice** endpoint for mandatory field updates
- **PATCH update** for general field updates

### Resume Builder (Feb 2026)
- Available to all roles: admin, recruiter, employer, candidate
- 3 LaTeX templates: ATS Clean, Google Style, Modern Pro
- **Preview-First UX** - visual resume preview shown immediately, edit section collapsible
- Inline profile editor (name, email, phone, skills, experience, education)
- AI bullet enhancement via OpenAI GPT-4o-mini
- LaTeX code preview, copy, and .tex download
- Candidate search from bank (admin/recruiter/employer only)
- Backend: `/api/resume/templates`, `/generate`, `/my-profile`, `/candidate/{id}`, `/ai-enhance`

### ATS CV System
- Auto-generates LaTeX resumes for all candidate bank profiles
- **Token-based auth** for new-tab downloads (`?token=` query param)
- Batch generation for all 1,977 existing candidates completed
- Download endpoints: `/api/candidate-bank/{id}/ats-cv`, `/api/candidate-bank/{id}/download-resume`

### Attendance System
- Check-in/check-out with IST timezone (UTC+5:30)
- Late/overtime calculation, leave management
- Analytics dashboard, health scores, cron service

### Jobs & Pipeline
- Job posting, approval workflow, applicant tracking
- AI-powered candidate matching, submission tracker
- Revenue dashboard

### Content & Marketing
- Blog engine, SEO monitoring, digest emails
- LinkedIn integration, contact form submissions

## Deployment Architecture
- Kubernetes container with supervisor-managed services
- Frontend: port 3000, Backend: port 8001
- Lazy MongoDB proxy pattern for deployment-safe startup
- `mongo_production_override.py` for Atlas connection override

## What's Been Implemented (Timeline)

### Feb 27, 2026 - Deployment Stabilization
- P0 Fix: Lazy proxy pattern for MongoDB client (deployment-safe startup)
- Environment detection fix (checks override file for production mode)
- Attendance IST timezone fix (37 instances across 3 files)
- Candidate bank route prefix fix (/api/candidate-bank)

### Feb 28, 2026 - Resume Builder Feature
- Full resume generation API (5 endpoints)
- 3 LaTeX templates with proper escaping
- AI bullet enhancement with fallback
- Frontend page for all roles with inline editing
- Registration enhanced with notice_period + CTC fields
- Sidebar navigation updated for all roles
- ATS CV process overhauled with LaTeX engine
- Batch resume generation for all 1,977 candidates
- Public website navigation updated

### Feb 28, 2026 - P0 Bug Fixes (Session 2)
- **Fix 1**: ATS CV download auth - token-based query param auth for new-tab downloads
- **Fix 2**: Resume Builder UX refactored to preview-first with collapsible editor
- **Fix 3**: Created missing PUT /salary-notice endpoint for candidate mandatory fields
- **Fix 4**: Created GET /download-resume endpoint with token auth
- All fixes verified with 100% pass rate (iteration_97)

## Backlog

### P0 (Immediate)
- None currently

### P1 (Next)
- Updated Browser Extension (pending user sharing new version)
- Interview Scheduling
- Candidate Activity Log
- Hiring Funnel KPIs dashboard
- In-App Notification Center

### P2
- Client CRM & Invoicing
- Candidate Duplicate Detection
- Email Template Management

### P3 (Future)
- Boolean Search
- Onboarding Module
- Vendor Management System
- Mobile PWA
- Custom Report Builder

### Blocked
- LinkedIn API Auto-Posting (needs w_organization_social scope approval)
