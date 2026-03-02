# VHC Talent OS - Product Requirements Document

## Product Overview
VHC Talent OS is a comprehensive recruitment management platform for Ventures HRD Consulting, serving employers, recruiters, candidates, and administrators.

## Architecture
- **Frontend**: React (CRA) + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB Atlas (cluster0.vuhdiod.mongodb.net) - external
- **AI**: OpenAI GPT-4o-mini via centralized LLM service
- **Storage**: Cloudflare R2 (credentials validated)
- **PDF Generation**: fpdf2 (pure Python) + pdflatex (optional)

## Core Features (Implemented)

### Authentication & Users
- JWT-based auth with role-based access (admin, recruiter, employer, candidate)
- Registration with notice_period, current_ctc, expected_ctc collection
- Zero Trust middleware for team-based access

### Candidate Management
- Candidate Bank (`/api/candidate-bank`) - 2032 candidates with pagination/search
- **12 Advanced Filters**: phone, email, location, company, skills, notice period, experience range, salary range, source, has resume, contact hidden (Naukri hidden profiles), capture date range
- Filter options endpoint (`/api/candidate-bank/filter-options`)
- Filter panel with chips, clear all, date presets (Today/Week/Month)
- Available on all 3 role pages: admin, recruiter, employer
- PUT /salary-notice endpoint for mandatory field updates
- PATCH update for general field updates

### Resume Builder
- Available to all roles
- 3 LaTeX templates: ATS Clean, Google Style, Modern Pro
- Preview-First UX with collapsible editor
- PDF Preview via fpdf2 (works in all environments)
- PDF download, .tex download, LaTeX code copy
- AI bullet enhancement via OpenAI GPT-4o-mini

### ATS CV System
- Auto-generates PDF resumes for all candidate bank profiles
- Token-based auth for new-tab downloads
- Pure Python PDF generation via fpdf2
- Graceful fallback: fpdf2 → pdflatex → .tex

### Browser Extension v4.5.0
- Scoped phone extraction (fixes recruiter phone leakage)
- CV deep section parsing
- Smarter "View Contact" click
- Capture history with email/phone

### Attendance System
- IST timezone, late/overtime calculation, leave management

### Jobs & Pipeline
- Job posting, approval workflow, applicant tracking
- AI-powered matching, submission tracker, revenue dashboard

## Implementation Timeline

### Mar 2, 2026 - P0 Production Deployment Fix
- Fixed `config.py`: MongoDB URI resolution now prioritizes `mongo_production_override.py` over env var with cluster validation
- Fixed `.gitignore`: Removed 78 duplicate `*.env` blocking entries (lines 98-178) so `.env` files deploy correctly
- Fixed `llm_service.py`: Removed `mongo_production_override` fallback for OPENAI_API_KEY — env-only now
- Fixed `environment.py`: Removed `mongo_production_override` imports for env detection — uses `MONGO_URL` env var only
- Updated OpenAI API key (old one was revoked)
- Added `/api/health/diagnostics` endpoint for production key verification
- Verified: health OK, 0 import failures, admin login works, 2032 candidates, correct Atlas cluster

### Mar 2, 2026 - Server Hardening (4 fixes)
1. Extension exempt from throttling: `/api/extension/ai-extract` and `/api/extension/capture` get 30 req/min (vs default 60) in HIGH_PRIORITY_ROUTES
2. Malware upload protection: Added security validation (magic bytes + threat scan) to cv_upload, profile, candidates, bulk_import routes. Files inside ZIPs are also scanned.
3. MongoDB connection pool: Upgraded from maxPoolSize=10→50, minPoolSize=1→5, maxConnecting=2→4
4. DB write retry: Added `utils/db_retry.py` with exponential backoff for transient errors (AutoReconnect, WriteError). Applied to extension capture/update operations.
5. Disabled Cloudflare Zero Trust middleware (caused login errors)

### Feb 27, 2026 - Deployment Stabilization
- Lazy proxy pattern, environment detection, IST fix, route prefix fix

### Feb 28, 2026 - Resume Builder + Bug Fixes
- Resume generation API, LaTeX templates, AI enhancement
- ATS CV overhaul, batch generation for 1,977 candidates
- P0 fixes: auth, UX, salary-notice, download-resume endpoints

### Feb 28, 2026 - PDF Preview
- fpdf2 pure-Python PDF generator
- generate-pdf endpoint, inline iframe preview
- Deployment fix: pdflatex graceful degradation

### Mar 1, 2026 - Browser Extension v4.5.0 + Advanced Filters
- Updated extension with scoped phone extraction, CV deep parsing
- 12 advanced filters on candidate bank (phone, email, location, company, skills, notice period, experience range, salary range, source, has resume, contact hidden, capture date)
- Filter panel with chips, clear all, date presets
- All 3 role pages updated (admin, recruiter, employer)
- All verified 100% (iteration_100: 27/27 backend, 15/15 frontend)

## Backlog

### P1 (Next)
- Interview Scheduling
- Candidate Activity Log
- Hiring Funnel KPIs dashboard
- In-App Notification Center

### P2
- Client CRM & Invoicing
- Candidate Duplicate Detection
- Email Template Management

### P3
- Boolean Search, Onboarding Module, Vendor Management, Mobile PWA, Custom Report Builder

### Blocked
- LinkedIn API Auto-Posting (needs w_organization_social scope approval)
