# VHC Talent OS - Product Requirements Document

## Product Overview
VHC Talent OS is a comprehensive recruitment management platform for Ventures HRD Consulting, serving employers, recruiters, candidates, and administrators.

## Architecture
- **Frontend**: React (CRA) + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB Atlas (cluster0.vuhdiod.mongodb.net) - external
- **AI**: OpenAI GPT-4o-mini via centralized LLM service
- **Storage**: Cloudflare R2 (credentials validated)
- **PDF Generation**: fpdf2 (pure Python, zero system deps) + pdflatex (optional, server-side)

## Core Features (Implemented)

### Authentication & Users
- JWT-based auth with role-based access (admin, recruiter, employer, candidate)
- Registration with notice_period, current_ctc, expected_ctc collection
- Zero Trust middleware for team-based access

### Candidate Management
- Candidate Bank (`/api/candidate-bank`) - 1800+ candidates with pagination/search
- Candidate Profiles (`/api/candidates`) - registered candidate profiles
- Naukri profile viewer, batch import, browser extension v4.2.0
- Candidate Edit - Profile editing with mandatory fields (salary, notice, location, experience)
- PUT /salary-notice endpoint for mandatory field updates
- PATCH update for general field updates

### Resume Builder
- Available to all roles: admin, recruiter, employer, candidate
- 3 LaTeX templates: ATS Clean, Google Style, Modern Pro
- **Preview-First UX** - visual resume preview shown immediately, edit section collapsible
- **PDF Preview** - inline iframe PDF viewer using fpdf2 (works in all environments)
- PDF download, .tex download, LaTeX code copy
- AI bullet enhancement via OpenAI GPT-4o-mini
- Candidate search from bank (admin/recruiter/employer only)
- Backend: `/api/resume/templates`, `/generate`, `/generate-pdf`, `/compile-pdf`, `/my-profile`, `/candidate/{id}`, `/ai-enhance`, `/capabilities`

### ATS CV System
- Auto-generates **PDF resumes** for all candidate bank profiles (was .tex, now PDF)
- Token-based auth for new-tab downloads (`?token=` query param)
- Pure Python PDF generation via fpdf2 (no system dependency on pdflatex)
- Graceful fallback: fpdf2 → pdflatex → .tex
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
- fpdf2 for PDF generation (pure Python, no system deps)
- Optional: texlive for higher-quality pdflatex compilation

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
- Fix 1: ATS CV download auth - token-based query param auth for new-tab downloads
- Fix 2: Resume Builder UX refactored to preview-first with collapsible editor
- Fix 3: Created missing PUT /salary-notice endpoint for candidate mandatory fields
- Fix 4: Created GET /download-resume endpoint with token auth
- All fixes verified 100% pass rate (iteration_97)

### Feb 28, 2026 - PDF Preview & Download Fix (Session 3)
- Created pure-Python PDF generator using fpdf2 (services/pdf_generator.py)
- ATS CV download now returns **PDF** instead of .tex file
- New POST /api/resume/generate-pdf endpoint (works without pdflatex)
- Frontend Resume Builder uses generate-pdf for inline preview
- Graceful degradation: fpdf2 → pdflatex → .tex fallback chain
- Deployment fix: pdflatex FileNotFoundError no longer crashes production
- Unicode char normalization (en-dash, smart quotes → ASCII)
- Long text handling with multi_cell wrapping
- All verified 100% (iteration_99: 10/10 backend, frontend verified)

## Backlog

### P0 (Immediate)
- None currently

### P1 (Next)
- Updated Browser Extension (pending user sharing new version)
- Interview Scheduling
- Candidate Activity Log

### P2
- Hiring Funnel KPIs dashboard
- In-App Notification Center
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
