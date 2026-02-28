# VHC Talent OS - Product Requirements Document

## Product Overview
VHC Talent OS is a comprehensive recruitment management platform for Ventures HRD Consulting, serving employers, recruiters, candidates, and administrators.

## Architecture
- **Frontend**: React (CRA) + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB Atlas (cluster0.vuhdiod.mongodb.net) - external
- **AI**: OpenAI GPT-4o-mini via centralized LLM service
- **Storage**: Cloudflare R2 (credentials need validation)

## Core Features (Implemented)

### Authentication & Users
- JWT-based auth with role-based access (admin, recruiter, employer, candidate)
- Registration with notice_period, current_ctc, expected_ctc collection
- Zero Trust middleware for team-based access

### Candidate Management
- Candidate Bank (`/api/candidate-bank`) - 1800+ candidates with pagination/search
- Candidate Profiles (`/api/candidates`) - registered candidate profiles
- Naukri profile viewer, batch import, browser extension v4.2.0

### Resume Builder (NEW - Feb 2026)
- Available to all roles: admin, recruiter, employer, candidate
- 3 LaTeX templates: ATS Clean, Google Style, Modern Pro
- Inline profile editor (name, email, phone, skills, experience, education)
- AI bullet enhancement via OpenAI GPT-4o-mini
- LaTeX code preview, copy, and .tex download
- Candidate search from bank (admin/recruiter/employer only)
- Backend: `/api/resume/templates`, `/generate`, `/my-profile`, `/candidate/{id}`, `/ai-enhance`

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

## Backlog

### P0 (Immediate)
- None currently

### P1 (Next)
- Interview Scheduling
- Candidate Activity Log
- Hiring Funnel KPIs dashboard
- In-App Notification Center

### P2
- Cloudflare R2 credential fix (Access Denied)
- Client CRM
- Invoicing
- Candidate Duplicate Detection

### P3 (Future)
- Email Template Management
- Boolean Search
- Onboarding Module
- Vendor Management System
- Mobile PWA
- Custom Report Builder
