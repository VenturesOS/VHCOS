# VHC Talent OS - Product Requirements Document

## Original Problem Statement
Build a production-ready recruitment portal called VHC Talent OS with role-based access, AI-powered matching, and comprehensive hiring workflows.

## Phase-1 Status: ✅ OPERATIONALLY COMPLETE

### Public Website Integration (Complete - January 18, 2026)
- ✅ **Public Careers Page** (`/website/careers.html`): Dynamic job listings from backend
- ✅ **Public Jobs API** (`/api/public/jobs`): No auth required, with search/filter
- ✅ **Public Apply Flow** (`/api/public/apply`): No login required, resume parsed by AI
- ✅ **Talent Pool Upload** (`/api/public/upload-resume`): Join talent pool without applying
- ✅ **Login Dropdown**: Employer, Recruiter, Candidate (NO Admin exposed)
- ✅ **Bot Protection**: Rate limiting (5/min apply, 3/hr upload), Honeypot, CAPTCHA-ready

### Phase-1 Scope (Completed)
- ✅ Role-Based Authentication (Admin, Recruiter, Employer, Candidate)
- ✅ Role-Based Dashboards with proper terminology
- ✅ Job Management (CRUD)
- ✅ Application Management with Pipeline (Kanban)
- ✅ Candidate Data Bank with source tracking
- ✅ AI Matching Engine (GPT-5.2)
- ✅ Email Notifications & Job Alerts
- ✅ UI/UX aligned with documentation

### Phase-1 Deliverables
1. **Internal Operation Readiness** - Recruiters can use daily
2. **Employer Demo Readiness** - 5-minute demo flow works
3. **Pilot Usage Readiness** - No confusion or retraining needed

---

## User Roles & Access

### Admin
- Full system control
- User management (CRUD all roles)
- Candidate Data Bank visibility
- Company management
- System settings

### Recruiter
- **Dashboard**: Active Mandates, Pipeline Status, Daily Workflow
- **Workflow**: View Mandates → Screen CVs (AI advisory) → Move Pipeline → Track Progress
- **Features**: AI Screening, Candidate Bank access
- **Terminology**: Jobs = "Mandates"

### Employer
- **Dashboard**: 3-step onboarding, Job posting, Applicant review
- **Workflow**: Post Job → Find Matched Candidates → Review → Decide
- **Features**: Find Candidates (AI matching), Applicant management, Analytics
- **Demo Flow**: Intuitive within 5 minutes

### Candidate
- Profile management
- Resume upload (AI parsed)
- Job browsing & applications
- Job alerts & notifications
- Matching jobs (AI-powered)

---

## Technical Implementation

### API Endpoints (Core)
- `/api/auth/*` - Authentication
- `/api/users/*` - User management
- `/api/jobs/*` - Job management
- `/api/applications/*` - Application pipeline
- `/api/candidates/*` - Candidate profiles
- `/api/candidate-bank/*` - Centralized candidate database
- `/api/ai/*` - AI parsing endpoints
- `/api/matching/*` - AI matching endpoints
- `/api/alerts/*` - Job alert preferences
- `/api/notifications/*` - Notification history

### Database Collections
- users (with role-based access)
- jobs (with company linkage)
- applications (with pipeline stages)
- candidate_profiles (user profiles)
- candidate_bank (centralized data)
- companies
- notification_logs
- job_alerts
- audit_logs

### Pipeline Stages (SOP-Aligned)
1. **New CVs** - Awaiting screening
2. **Shortlisted** - Ready for interview
3. **Interview** - In process
4. **Offered** - Offer extended
5. **Hired** - Joined

---

## Credentials

### Admin
- Email: admin@vhc.in
- Password: VhcAdmin@2024

### Demo Users (No password reset required)
- **Employer**: demoemployer@vhc.in / Employer@123
- **Recruiter**: demorecruiter@vhc.in / Recruiter@123
- **Candidate**: testcandidate@vhc.in / Test@123

---

## Phase-1 Completion Checklist

### Employer Demo Readiness ✅
- [x] 3-step onboarding: Post Job → Find Candidates → Review & Decide
- [x] Clear CTAs for job posting
- [x] Find Candidates with AI matching
- [x] Shortlist/reject candidate actions
- [x] Empty states with guidance
- [x] "Find Matches" button on job cards

### Recruiter Operational Readiness ✅
- [x] Dashboard aligned with Pilot SOPs
- [x] "Mandates" terminology (not "Jobs")
- [x] "AI Screening" label (not "AI Matching")
- [x] Daily Workflow section: View Mandates → Screen CVs → Move Pipeline → Track Progress
- [x] Pipeline stages with descriptions
- [x] Workflow tip on pipeline page
- [x] "All Mandates" filter dropdown

### Candidate Data Bank Visibility ✅
- [x] Admin has clear visibility
- [x] Source badges (Direct Upload, Applied, Recruiter Upload, Registered)
- [x] Active status indicator (green dot)
- [x] Skills display with overflow indicator
- [x] Search by name/email
- [x] Filter by skills
- [x] Detailed candidate view with audit log

---

## What's NOT in Phase-1 (Deferred)

### Phase-2 Features (Do Not Implement Yet)
- WhatsApp automation
- Email campaign automation
- CRM sync
- Payment & billing
- Advanced analytics dashboards
- n8n workflow integration
- Interview scheduling calendar
- Bulk candidate import

### Refactoring (Deferred)
- server.py modularization (~1900 lines)
- Only after Phase-2 stable

---

## Test Reports
- `/app/test_reports/iteration_6.json` - Phase-1 UI/UX (100% pass)
- `/app/test_reports/iteration_5.json` - P1 Notifications (100% pass)
- `/app/test_reports/iteration_4.json` - AI Matching (100% pass)

---

## Documentation Alignment
Based on:
- VHC Talent OS Master Context Prompt
- VHC Pilot Recruiter SOPs
- VHC Phase-1 Deployment Checklists
- VHC AI Team Playbook
- VHC Developer Handoff Pack
