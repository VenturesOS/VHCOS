# VHC Talent OS - Product Requirements Document

## Overview
VHC Talent OS is a production-ready, role-based recruitment portal built for VHC Talent Advisory. The system supports Executive Search, Specialist Hiring, and People Advisory services across India and the United States.

## Original Problem Statement
Build a recruitment portal with:
- Role-based access control (Admin, Recruiter, Employer, Candidate)
- AI-powered matching engine for job descriptions and resumes
- Candidate Data Bank for talent pool management
- Notification system for job alerts
- Public-facing website with secure application flow
- Phase-1 operational readiness for internal and pilot use

---

## Phase-1 Status: ✅ COMPLETE (Signed Off: January 18, 2026)

### P0: Candidate Apply & Resume Review Flow ✅
**Completed:** Two-step application process
- Step 1: Resume upload → AI parsing via GPT-5.2
- Step 2: Editable review form (name, email, phone, location, headline, skills)
- New fields: Current Salary (INR), Notice Period
- Data persisted in `applications` and `candidate_bank` collections
- Bot protection via Cloudflare Turnstile CAPTCHA

### P1: Applicant Review Screen ✅
**Completed:** Per-job applicant management
- Endpoint: `GET /api/jobs/{job_id}/applicants`
- Displays: Match score, must-have indicators, salary, notice period
- Stage tabs with counts (Applied, Shortlisted, Interview, etc.)
- Manual actions: Shortlist, Reject, Hold, Over Budget, Not Qualified
- Accessible by Admin, Employer, and Recruiter roles

### P2: Career Stability Indicator ✅
**Completed:** Visual job stability assessment
- Green: 0-1 quick job changes (≤1 year tenure)
- Yellow: 2-3 quick job changes
- Red: More than 3 quick job changes
- Displayed as colored dot with tooltip on applicant cards
- Informational only - no auto-reject logic

### P3: Website Landing & Header Fix ✅
**Completed:** Public website configuration
- Root `/` redirects to `/website/Index.html`
- Header order: Home | About | Services | Industries | Career | Contact | Global Hiring | Login
- Sticky header across all pages
- Login button navigates to portal login

---

## System Architecture

### Tech Stack
- **Backend:** FastAPI (Python), MongoDB (Motor)
- **Frontend:** React, React Router, Shadcn/UI, Tailwind CSS
- **AI Integration:** GPT-5.2 via `emergentintegrations`
- **Notifications:** Resend (email), Twilio (WhatsApp - stubbed)
- **Bot Protection:** Cloudflare Turnstile

### Database Collections
- `users` - User accounts with RBAC
- `jobs` - Job postings
- `applications` - Job applications with salary/notice period
- `candidate_bank` - Talent pool with parsed profiles
- `job_alerts` - Candidate notification preferences
- `notification_logs` - Delivery tracking

### Key API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/public/parse-resume` | POST | Parse resume (Step 1) |
| `/api/public/apply` | POST | Submit application (Step 2) |
| `/api/jobs/{id}/applicants` | GET | Get enriched applicants |
| `/api/applications/{id}` | PUT | Update application stage |
| `/api/matching/find-candidates/{job_id}` | GET | AI matching |

---

## User Credentials (Test Accounts)

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@vhc.in | VhcAdmin@2024 |
| Employer | employer@vhctalent.com | Demo@2024 |

---

## Phase-2 Backlog (NOT STARTED - Awaiting Instruction)

### P2-1: WhatsApp Automation
- Twilio integration for candidate notifications
- Opt-in/opt-out management

### P2-2: Email Campaign Automation
- Bulk email capabilities for marketing
- Template management

### P2-3: CRM Synchronization
- Integration with external CRM systems

### P2-4: Payment & Billing
- Stripe integration for subscription/usage billing

### P2-5: Advanced Analytics Engine
- Dashboard analytics and reporting

### P2-6: Workflow Automation
- n8n integration hooks

### P2-7: Backend Refactoring
- Break `server.py` into modular APIRouters
- Improve code organization

---

## File Structure
```
/app/
├── backend/
│   ├── server.py          # Main FastAPI application
│   ├── services/
│   │   ├── matching_engine.py
│   │   ├── email_service.py
│   │   └── notification_service.py
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── admin/
│   │   │   ├── employer/
│   │   │   │   └── JobApplicantsPage.jsx
│   │   │   ├── recruiter/
│   │   │   └── candidate/
│   │   └── lib/
│   │       └── currency.js   # INR formatting
│   └── public/website/       # Static public site
└── public-website/
    └── vhc-website/          # Source website files
```

---

## Constraints (Phase-1 Locked)
- No backend refactoring
- No database schema changes
- No changes to AI parsing/matching logic
- UI/UX and additive changes only
- Informational indicators only (no auto-reject)

---

## Notes
- Email notifications (Resend) and WhatsApp (Twilio) are MOCKED - API keys not configured
- Currency standardized to INR with Indian number formatting
- Rate limiting active on public endpoints (5 requests/minute)

---

*Last Updated: January 18, 2026*
*Phase-1 Sign-Off: Approved*
