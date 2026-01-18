# VHC Talent OS - Product Requirements Document

## Original Problem Statement
Build a production-ready recruitment portal called VHC Talent OS with:
- Role-based access (Admin, Recruiter, Employer, Candidate)
- JWT email/password authentication
- Job Management
- Candidate Pipeline with Kanban stages
- Resume Upload
- Basic Messaging
- Settings Panel
- AI-powered resume/JD parsing and candidate-job matching
- Email/WhatsApp notifications for job matches

## User Personas
1. **Admin**: Full system control - manages users, jobs, candidates, companies, candidate data bank, settings
2. **Recruiter**: Manages candidate pipeline, moves candidates through stages, uses AI matching
3. **Employer**: Posts jobs, views applicants, finds matching candidates using AI
4. **Candidate**: Creates profile, uploads resume, applies to jobs, views AI-matched jobs, manages job alerts

## Core Requirements (Static)
- Secure JWT authentication with bcrypt password hashing
- Role-based middleware and dashboard routing
- MongoDB database with proper collections
- RESTful API with /api prefix for all endpoints
- Responsive UI with VHC lime green branding (#7CB342)
- Kanban board for candidate pipeline stages
- AI Matching Engine using GPT-5.2
- Email notifications using Resend API
- WhatsApp notifications using Twilio (opt-in only)

## What's Been Implemented

### Phase 1 - Core Platform (Complete - January 2026)
- ✅ User authentication (register, login, JWT tokens)
- ✅ Role-based access control middleware
- ✅ User management APIs (CRUD)
- ✅ Job management APIs (create, browse, update, delete)
- ✅ Application APIs with pipeline stage management
- ✅ Candidate profile management with resume upload
- ✅ Company management APIs
- ✅ Message APIs (send, receive, mark read)
- ✅ Dashboard stats APIs for all 4 roles
- ✅ Settings management for admin
- ✅ Security hardening (env-based admin seeding, password reset on first login)
- ✅ Role-based dashboards for Admin, Recruiter, Employer, Candidate

### Phase 2b - AI Matching Engine & Candidate Data Bank (Complete - January 18, 2026)
- ✅ **AI JD Parsing** (`/api/ai/parse-jd`): GPT-5.2 extracts structured data from job descriptions
- ✅ **AI Resume Parsing** (`/api/ai/parse-resume`): GPT-5.2 extracts skills, experience, education from resumes
- ✅ **AI Candidate Matching** (`/api/matching/find-candidates`): Match candidates against JD with scores
- ✅ **Candidate Data Bank** (`/api/candidate-bank/*`): Centralized candidate repository
- ✅ **Resume Deduplication**: Fingerprinting to detect duplicate resumes
- ✅ **Must-Have Filters**: Hard filters for location, experience, mandatory skills
- ✅ **Audit Trail**: Track all candidate data changes
- ✅ **Frontend Pages**: Admin Candidate Data Bank, Employer Find Candidates, Candidate Matching Jobs

### Phase 2.5 / P1 - Email Notifications & Job Alerts (Complete - January 18, 2026)
- ✅ **Email Notification Service** (`/app/backend/services/email_service.py`): Resend API integration
- ✅ **WhatsApp Notification Service** (`/app/backend/services/whatsapp_service.py`): Twilio integration (opt-in only)
- ✅ **Notification Templates** (`/app/backend/services/notification_templates.py`): Centralized email/WhatsApp templates
- ✅ **Job Alert Preferences**: Candidates can set skills, location, experience range, job types
- ✅ **Notification Channels**: Email always enabled, WhatsApp optional with explicit consent
- ✅ **Alert Frequency**: Instant, Daily, Weekly options
- ✅ **Pause/Resume Alerts**: Candidates can temporarily pause notifications
- ✅ **Notification Deduplication**: Max 1 notification per job per candidate per channel
- ✅ **Notification History/Audit Log**: Track all sent/skipped/failed notifications
- ✅ **Admin Notification Stats**: Dashboard with subscriber counts and delivery stats
- ✅ **Background Job Triggers**: Async notifications when jobs created/updated
- ✅ **Frontend Notification Settings**: `/candidate/notifications` page with full CRUD

## API Endpoints Summary

### Authentication
- `POST /api/auth/login` - Login
- `POST /api/auth/register` - Register
- `POST /api/auth/reset-password` - Reset password (mandatory on first login)
- `GET /api/auth/me` - Get current user

### AI & Matching (Phase 2b)
- `POST /api/ai/parse-jd` - Parse job description with AI
- `POST /api/ai/parse-resume` - Parse resume file with AI
- `POST /api/matching/find-candidates` - Find matching candidates for a JD
- `GET /api/matching/jobs-for-candidate` - Find matching jobs for a candidate

### Candidate Data Bank (Phase 2b)
- `GET /api/candidate-bank` - List all candidates
- `POST /api/candidate-bank/add` - Add candidate via resume upload
- `GET /api/candidate-bank/{id}` - Get candidate details
- `PUT /api/candidate-bank/{id}` - Update candidate
- `GET /api/candidate-bank/{id}/audit-log` - View audit trail
- `GET /api/candidate-bank/{id}/resume-history` - View resume versions

### Job Alerts & Notifications (P1 - NEW)
- `GET /api/alerts/preferences` - Get candidate's alert preferences
- `POST /api/alerts/preferences` - Create/enable job alerts
- `PUT /api/alerts/preferences` - Update alert preferences
- `DELETE /api/alerts/preferences` - Unsubscribe from alerts
- `POST /api/alerts/pause` - Temporarily pause alerts
- `POST /api/alerts/resume` - Resume paused alerts
- `POST /api/alerts/whatsapp/opt-in` - Enable WhatsApp notifications (requires valid phone)
- `POST /api/alerts/whatsapp/opt-out` - Disable WhatsApp notifications
- `PUT /api/alerts/whatsapp/number` - Update WhatsApp number
- `GET /api/notifications/history` - Get candidate's notification history
- `GET /api/admin/notifications/stats` - Admin notification statistics
- `POST /api/jobs/with-notifications` - Create job and trigger notifications
- `POST /api/jobs/{job_id}/notify-candidates` - Manually trigger notifications

### Core APIs
- `/api/users/*` - User CRUD (Admin)
- `/api/jobs/*` - Job CRUD
- `/api/applications/*` - Application management
- `/api/candidates/*` - Candidate profiles
- `/api/companies/*` - Company management
- `/api/messages/*` - Messaging
- `/api/settings` - Admin settings
- `/api/stats/*` - Dashboard statistics

## Prioritized Backlog

### P0 (Critical) - COMPLETE ✅
- [x] Authentication system
- [x] Role-based dashboards
- [x] Job management
- [x] Application management
- [x] Candidate pipeline
- [x] Security hardening
- [x] AI Matching Engine (GPT-5.2)
- [x] Candidate Data Bank

### P1 (High Priority) - COMPLETE ✅
- [x] Email notifications for candidates on new matching jobs
- [x] Job Alert subscriptions with preferences
- [x] WhatsApp notifications (opt-in, consent-based)
- [x] Notification history and audit log
- [x] Admin notification statistics

### P2 (Medium Priority) - Next
- [ ] Email campaign automation for recruiters
- [ ] Interview scheduling with calendar integration
- [ ] Bulk candidate import (CSV/Excel)
- [ ] Advanced search and filtering
- [ ] Job application cover letter preview

### P3 (Nice to Have) - Future
- [ ] Advanced analytics dashboards with charts
- [ ] Custom workflow automation (n8n hooks)
- [ ] Payment & billing integration
- [ ] White-label client dashboards
- [ ] CRM sync integration

## Technical Stack
- Frontend: React 19, Tailwind CSS, Shadcn UI, @hello-pangea/dnd, Recharts
- Backend: FastAPI, Motor (async MongoDB), PyJWT, bcrypt, emergentintegrations
- Database: MongoDB
- Authentication: JWT with 24-hour expiry
- AI Integration: GPT-5.2 via emergentintegrations library (Emergent LLM Key)
- Email: Resend API
- WhatsApp: Twilio Business API

## Environment Variables
```
# Backend (.env)
MONGO_URL="mongodb://localhost:27017"
DB_NAME="vhc_talent_os"
JWT_SECRET=<auto-generated>
ADMIN_EMAIL="admin@vhc.in"
ADMIN_PASSWORD="VhcAdmin@2024"
EMERGENT_LLM_KEY=<provided>
RESEND_API_KEY=<user-provided>
SENDER_EMAIL=notifications@vhctalent.com
TWILIO_ACCOUNT_SID=<optional>
TWILIO_AUTH_TOKEN=<optional>
TWILIO_WHATSAPP_NUMBER=<optional>
JOB_MATCH_THRESHOLD=60
NOTIFICATION_ENABLED=true
```

## Admin Credentials
- Email: admin@vhc.in
- Password: VhcAdmin@2024

## Test Credentials
- Test Candidate: testcandidate@vhc.in / Test@123
- Recruiter: recruiter@vhctalent.com (requires password reset)
- Employer: employer@vhctalent.com (requires password reset)
- Candidate: candidate@vhctalent.com (requires password reset)

## Code Architecture
```
/app/
├── backend/
│   ├── .env
│   ├── requirements.txt
│   ├── server.py              # Main FastAPI app (~1900 lines)
│   ├── services/
│   │   ├── matching_engine.py # AI parsing and matching logic
│   │   ├── email_service.py   # Resend email delivery
│   │   ├── whatsapp_service.py # Twilio WhatsApp delivery
│   │   ├── notification_service.py # Notification orchestration
│   │   └── notification_templates.py # Centralized templates
│   └── tests/
│       ├── test_ai_matching_engine.py
│       └── test_notifications_alerts.py
└── frontend/
    ├── .env
    ├── package.json
    └── src/
        ├── App.js
        ├── components/
        │   ├── layout/
        │   └── ui/
        ├── lib/
        │   ├── api.js
        │   └── auth.js
        └── pages/
            ├── admin/
            ├── auth/
            ├── candidate/
            │   ├── NotificationSettingsPage.jsx  # NEW
            │   └── ...
            ├── employer/
            └── recruiter/
```

## Test Reports
- `/app/test_reports/iteration_5.json` - Latest comprehensive test (100% pass - P1 Notifications)
- `/app/test_reports/iteration_4.json` - Phase-2b AI Matching (100% pass)
- `/app/tests/test_notifications_alerts.py` - 20 pytest tests for notification system
- `/app/tests/test_ai_matching_engine.py` - 18 pytest tests for AI features

## Refactoring Notes (Low Priority)
- `server.py` is ~1900 lines - consider splitting into modules using FastAPI APIRouter
- Should be done only after P2 features are stable
