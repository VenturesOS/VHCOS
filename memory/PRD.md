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

## User Personas
1. **Admin**: Full system control - manages users, jobs, candidates, companies, candidate data bank, settings
2. **Recruiter**: Manages candidate pipeline, moves candidates through stages, uses AI matching
3. **Employer**: Posts jobs, views applicants, finds matching candidates using AI
4. **Candidate**: Creates profile, uploads resume, applies to jobs, views AI-matched jobs

## Core Requirements (Static)
- Secure JWT authentication with bcrypt password hashing
- Role-based middleware and dashboard routing
- MongoDB database with proper collections
- RESTful API with /api prefix for all endpoints
- Responsive UI with VHC lime green branding (#7CB342)
- Kanban board for candidate pipeline stages
- AI Matching Engine using GPT-5.2

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

### P1 (High Priority) - Next
- [ ] Email notifications for candidates on new matching jobs
- [ ] Template-based async email delivery
- [ ] Advanced search and filtering
- [ ] Job application cover letter preview

### P2 (Medium Priority) - Future
- [ ] WhatsApp automation (opt-in, compliance-ready)
- [ ] Email campaign automation
- [ ] CRM sync integration
- [ ] Interview scheduling calendar
- [ ] Bulk candidate import

### P3 (Nice to Have) - Future
- [ ] Advanced analytics dashboards with charts
- [ ] Custom workflow automation (n8n hooks)
- [ ] Payment & billing integration
- [ ] White-label client dashboards

## Technical Stack
- Frontend: React 19, Tailwind CSS, Shadcn UI, @hello-pangea/dnd, Recharts
- Backend: FastAPI, Motor (async MongoDB), PyJWT, bcrypt, emergentintegrations
- Database: MongoDB
- Authentication: JWT with 24-hour expiry
- AI Integration: GPT-5.2 via emergentintegrations library (Emergent LLM Key)

## Admin Credentials
- Email: admin@vhc.in
- Password: VhcAdmin@2024

## Test Credentials (Require Password Reset)
- Recruiter: recruiter@vhctalent.com / oBANv_5MOGyjWQqX
- Employer: employer@vhctalent.com / No9UaBkni5LXbrAS
- Candidate: candidate@vhctalent.com / n7t2qnzZQuaNyjMM

## Code Architecture
```
/app/
├── backend/
│   ├── .env                    # Environment variables
│   ├── requirements.txt
│   ├── server.py              # Main FastAPI app (~1200 lines)
│   └── services/
│       └── matching_engine.py # AI parsing and matching logic
└── frontend/
    ├── .env
    ├── package.json
    └── src/
        ├── App.js             # Main router
        ├── components/
        │   ├── layout/        # Sidebar, DashboardLayout
        │   └── ui/            # Shadcn UI components
        ├── lib/
        │   ├── api.js         # API utility functions
        │   └── auth.js        # Auth context and hooks
        └── pages/
            ├── admin/         # Admin dashboard pages
            ├── auth/          # Login, Register, PasswordReset
            ├── candidate/     # Candidate dashboard pages
            ├── employer/      # Employer dashboard pages
            └── recruiter/     # Recruiter dashboard pages
```

## Refactoring Notes (Low Priority)
- `server.py` is ~1200 lines - consider splitting into modules using FastAPI APIRouter
- Should be done only after Phase 2b is stable and before Phase 3

## Test Reports
- `/app/test_reports/iteration_4.json` - Latest comprehensive test (100% pass)
- `/app/tests/test_ai_matching_engine.py` - 18 pytest tests for AI features
