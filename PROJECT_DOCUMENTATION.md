# VHC Talent OS — Complete Project Documentation

> **Last Updated:** February 8, 2026  
> **Version:** 2.0  
> **Status:** Production Ready

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [Tech Stack](#tech-stack)
3. [Architecture](#architecture)
4. [External Services & Integrations](#external-services--integrations)
5. [Database Schema](#database-schema)
6. [API Reference](#api-reference)
7. [Feature Summary](#feature-summary)
8. [Frontend Structure](#frontend-structure)
9. [Backend Structure](#backend-structure)
10. [Authentication & Authorization](#authentication--authorization)
11. [Environment Variables](#environment-variables)
12. [Test Credentials](#test-credentials)
13. [Performance Benchmarks](#performance-benchmarks)
14. [Known Limitations & Mocked Services](#known-limitations--mocked-services)

---

## Project Overview

**VHC Talent OS** is a full-featured recruitment operating system designed for staffing agencies and HR teams. It provides end-to-end hiring workflow management including:

- Multi-role portal (Admin, Employer, Recruiter, Candidate)
- AI-powered candidate matching and screening
- Bulk candidate import with resume parsing
- Pipeline management with stage tracking
- Team and company management
- Commercial intelligence and revenue tracking
- Job alerts and notifications

---

## Tech Stack

### Frontend
| Technology | Purpose |
|------------|---------|
| React 18 | UI Framework |
| Tailwind CSS | Styling |
| Shadcn/UI | Component Library |
| React Router v6 | Routing |
| Axios | HTTP Client |
| Sonner | Toast Notifications |
| Lucide React | Icons |
| Recharts | Charts/Analytics |

### Backend
| Technology | Purpose |
|------------|---------|
| FastAPI | Web Framework |
| Python 3.11 | Runtime |
| Uvicorn | ASGI Server |
| Motor | Async MongoDB Driver |
| Pydantic v2 | Data Validation |
| PyJWT | JWT Authentication |
| PyMuPDF (fitz) | PDF Parsing |
| python-docx | DOCX Parsing |

### Database
| Service | Purpose |
|---------|---------|
| MongoDB Atlas | Primary Database |
| Atlas Search | Full-text Search |

### Caching
| Service | Purpose |
|---------|---------|
| Upstash Redis | Distributed Cache |
| In-memory LRU | Local Cache |

### Storage
| Service | Purpose |
|---------|---------|
| Cloudflare R2 | Resume/File Storage |
| Local uploads/ | Fallback Storage |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React)                         │
│   /app/frontend/src/                                             │
│   ├── pages/           # Role-based pages                        │
│   ├── components/      # Reusable UI components                  │
│   ├── lib/             # API client, auth, utilities             │
│   └── hooks/           # Custom React hooks                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ HTTPS (API calls prefixed /api)
┌─────────────────────────────────────────────────────────────────┐
│                         BACKEND (FastAPI)                        │
│   /app/backend/                                                  │
│   ├── server.py        # Main app + employer/analytics routes    │
│   ├── routes/          # Modular API routers                     │
│   ├── services/        # Business logic & external integrations  │
│   ├── models/          # Pydantic schemas                        │
│   ├── utils/           # Auth helpers, governance                │
│   └── core/            # Config, database, security              │
└─────────────────────────────────────────────────────────────────┘
          │                    │                    │
          ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ MongoDB Atlas│    │ Upstash Redis│    │ Cloudflare R2│
│  (Database)  │    │   (Cache)    │    │  (Storage)   │
└──────────────┘    └──────────────┘    └──────────────┘
          │
          ▼
┌──────────────────────────────────────────────────────────────────┐
│                    EXTERNAL AI SERVICES                           │
│   OpenAI GPT-4o (Resume/JD parsing, AI matching)                 │
│   OpenAI Embeddings (Semantic search vectors)                    │
└──────────────────────────────────────────────────────────────────┘
```

---

## External Services & Integrations

### 1. OpenAI (AI/ML)
**Purpose:** Resume parsing, JD parsing, candidate-job matching, semantic embeddings

| Endpoint | Model | Usage |
|----------|-------|-------|
| Chat Completions | GPT-4o | Parse resumes, parse JDs, score candidates |
| Embeddings | text-embedding-3-small | Generate 1536-dim vectors for semantic search |

**Files:**
- `/app/backend/services/matching_engine.py` — AI matching logic
- `/app/backend/services/embeddings.py` — Embedding generation & caching

**API Key:** `EMERGENT_LLM_KEY` or `OPENAI_API_KEY` in `.env`

---

### 2. MongoDB Atlas (Database)
**Purpose:** Primary data store with Atlas Search for full-text queries

**Collections:**
- `users`, `jobs`, `applications`, `candidate_bank`, `companies`
- `teams`, `referrals`, `commercials`, `revenues`
- `match_results`, `match_jobs`, `bug_reports`, `system_errors`
- `notifications`, `notification_history`, `job_alert_preferences`

**Indexes:**
- Atlas Search index: `candidate_search` on `candidate_bank`
- Standard indexes on `email`, `job_id`, `candidate_id`, etc.

**Connection:** `MONGO_URL` in `.env`

---

### 3. Upstash Redis (Cache)
**Purpose:** Distributed caching for match results, rate limiting

**Usage:**
- Cache match results (2-minute TTL)
- Rate limiting counters
- Thundering herd prevention locks

**Files:** `/app/backend/services/cache.py`, `/app/backend/services/rate_limiter.py`

**Connection:** `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`

---

### 4. Cloudflare R2 (Object Storage)
**Purpose:** Store uploaded resumes, CVs, and documents

**Features:**
- S3-compatible API
- Chunked uploads for large files
- Resume versioning

**Files:** `/app/backend/services/r2_storage.py`, `/app/backend/services/chunked_upload.py`

**Connection:** `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`

---

### 5. Resend (Email) — MOCKED
**Purpose:** Send email notifications (job alerts, application updates)

**Status:** Integration code exists but uses mock responses
**File:** `/app/backend/services/email_service.py`
**Key:** `RESEND_API_KEY`

---

### 6. Twilio (WhatsApp) — MOCKED
**Purpose:** Send WhatsApp notifications

**Status:** Integration code exists but uses mock responses
**File:** `/app/backend/services/whatsapp_service.py`
**Keys:** `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_NUMBER`

---

## Database Schema

### Core Collections

#### `users`
```javascript
{
  id: String (UUID),
  email: String (unique),
  password_hash: String,
  name: String,
  role: "admin" | "employer" | "recruiter" | "candidate",
  phone: String,
  company_id: String,
  team_id: String,
  status: "active" | "inactive",
  created_at: DateTime,
  updated_at: DateTime
}
```

#### `jobs`
```javascript
{
  id: String (UUID),
  title: String,
  description: String,
  requirements: String,
  location: String,
  job_type: "full-time" | "part-time" | "contract",
  salary_min: Number,
  salary_max: Number,
  company_id: String,
  posted_by: String,
  status: "draft" | "pending_approval" | "active" | "closed",
  career_page_status: "live" | "not_live",
  shareable_link_enabled: Boolean,
  mandate_shareable_link_enabled: Boolean,
  assigned_recruiters: [String],
  applicant_count: Number,
  created_at: DateTime,
  updated_at: DateTime
}
```

#### `applications`
```javascript
{
  id: String (UUID),
  job_id: String,
  candidate_id: String,
  candidate_name: String,
  candidate_email: String,
  job_title: String,
  company_name: String,
  stage: "applied" | "shortlisted" | "interview" | "offered" | "hired" | "rejected",
  status: "active" | "removed",
  source: "self" | "ai_screening" | "referral" | "recruiter",
  current_salary: Number,
  expected_salary: Number,
  notice_period: String,
  skills: [String],
  resume_url: String,
  notes: [{content, author_id, author_name, created_at}],
  edit_history: [{field, old_value, new_value, updated_by_*, timestamp}],
  created_at: DateTime,
  updated_at: DateTime
}
```

#### `candidate_bank`
```javascript
{
  id: String (UUID),
  name: String,
  email: String,
  phone: String,
  skills: [String],
  experience_years: Number,
  education: [{degree, institution, year}],
  experience: [{title, company, start_date, end_date}],
  current_salary: Number,
  notice_period: String,
  location: String,
  summary: String,
  resume_url: String,
  resume_fingerprint: String,
  embedding: [Number] (1536-dim vector),
  source: "upload" | "bulk_import" | "application",
  created_by: String,
  linked_user_id: String,
  application_history: [{job_id, job_title, company_name, stage, outcome}],
  profile_update_audit: [{field, old_value, new_value, source, timestamp}],
  created_at: DateTime,
  updated_at: DateTime
}
```

#### `companies`
```javascript
{
  id: String (UUID),
  name: String,
  industry: String,
  website: String,
  location: String,
  size: String,
  description: String,
  logo_url: String,
  employer_id: String,
  created_at: DateTime,
  updated_at: DateTime
}
```

#### `teams`
```javascript
{
  id: String (UUID),
  name: String,
  description: String,
  owner_id: String (employer),
  recruiter_ids: [String],
  company_ids: [String],
  created_at: DateTime,
  updated_at: DateTime
}
```

#### `referrals`
```javascript
{
  id: String (UUID),
  job_id: String,
  candidate_name: String,
  candidate_email: String,
  candidate_phone: String,
  referrer_id: String,
  referrer_name: String,
  notes: String,
  status: "submitted" | "reviewed" | "contacted" | "converted" | "rejected",
  linked_candidate_id: String,
  status_history: [{status, reason, changed_by, timestamp}],
  created_at: DateTime,
  updated_at: DateTime
}
```

#### `commercials`
```javascript
{
  id: String (UUID),
  company_id: String,
  fee_type: "percentage" | "fixed",
  fee_value: Number,
  payment_terms: String,
  valid_from: DateTime,
  valid_until: DateTime,
  created_by: String,
  created_at: DateTime,
  updated_at: DateTime
}
```

---

## API Reference

All endpoints are prefixed with `/api`

### Authentication (`/api/auth`)
| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/register` | Register new user (candidate only) | No |
| POST | `/login` | Login and get JWT token | No |
| GET | `/me` | Get current user profile | Yes |
| POST | `/reset-password` | Change password | Yes |

### Jobs (`/api/jobs`)
| Method | Endpoint | Description | Roles |
|--------|----------|-------------|-------|
| GET | `/jobs` | List all jobs | All |
| GET | `/jobs/browse` | Browse active jobs | All |
| GET | `/jobs/{id}` | Get job details | All |
| POST | `/jobs` | Create new job | Admin, Employer |
| PUT | `/jobs/{id}` | Update job | Admin, Employer |
| DELETE | `/jobs/{id}` | Delete job | Admin |
| POST | `/jobs/{id}/transition` | Change job status | Admin |
| GET | `/jobs/pending-approval` | Jobs awaiting approval | Admin |
| POST | `/jobs/{id}/career-page-status` | Toggle career page visibility | Admin, Employer |
| PUT | `/jobs/{id}/shareable-link` | Toggle shareable link | Admin, Employer |
| POST | `/jobs/{id}/assign-recruiters` | Assign recruiters | Employer |
| POST | `/jobs/parse-jd` | Parse JD with AI | All |

### Applications (`/api/applications`)
| Method | Endpoint | Description | Roles |
|--------|----------|-------------|-------|
| GET | `/applications` | List applications | All |
| GET | `/applications/{id}` | Get application | All |
| POST | `/applications` | Apply for job | Candidate |
| PUT | `/applications/{id}` | Update stage/status | Admin, Employer, Recruiter |
| DELETE | `/applications/{id}` | Remove from pipeline | Admin |
| PUT | `/applications/{id}/details` | Edit salary/notice/skills | Admin, Employer, Recruiter |
| POST | `/applications/{id}/notes` | Add note | Admin, Employer, Recruiter |
| GET | `/applications/{id}/edit-history` | Audit trail | Admin, Employer, Recruiter |
| GET | `/applications/{id}/resume` | Download resume | Admin, Employer, Recruiter |

### Job Pipeline (`/api/jobs/{job_id}/applicants`)
| Method | Endpoint | Description | Roles |
|--------|----------|-------------|-------|
| GET | `/jobs/{id}/applicants` | All applicants for job | Admin, Employer, Recruiter |

### AI Matching (`/api/matching`)
| Method | Endpoint | Description | Roles |
|--------|----------|-------------|-------|
| POST | `/matching/find-candidates` | Find matching candidates | Admin, Employer, Recruiter |
| GET | `/matching/jobs/{id}/status` | Poll background job status | Admin, Employer, Recruiter |
| GET | `/matching/history` | Match search history | Admin, Employer, Recruiter |
| GET | `/matching/history/{id}` | Match history detail | Admin, Employer, Recruiter |
| POST | `/matching/shortlist` | Add candidate to pipeline | Admin, Employer, Recruiter |
| GET | `/matching/jobs-for-candidate` | Matching jobs for candidate | Candidate |

### Candidate Bank (`/api/candidate-bank`)
| Method | Endpoint | Description | Roles |
|--------|----------|-------------|-------|
| GET | `/candidate-bank` | List all candidates | Admin, Employer, Recruiter |
| GET | `/candidate-bank/{id}` | Get candidate details | Admin, Employer, Recruiter |
| PUT | `/candidate-bank/{id}` | Update candidate | Admin, Employer, Recruiter |
| POST | `/candidate-bank/add` | Add candidate with resume | Admin, Employer, Recruiter |
| POST | `/candidate-bank/batch-parse` | Batch parse resumes | Admin, Employer, Recruiter |
| POST | `/candidate-bank/batch-save` | Save parsed candidates | Admin, Employer, Recruiter |
| PUT | `/candidate-bank/{id}/salary-notice` | Update mandatory fields | Admin, Employer, Recruiter |
| GET | `/candidate-bank/{id}/history` | Application history | Admin, Employer, Recruiter |
| GET | `/candidate-bank/{id}/download-resume` | Download resume | Admin, Employer, Recruiter |

### Bulk Import (`/api/admin/bulk-import`)
| Method | Endpoint | Description | Roles |
|--------|----------|-------------|-------|
| GET | `/template` | Download Excel template | Admin |
| POST | `/excel` | Parse Excel file | Admin |
| POST | `/cv-zip` | Parse ZIP of CVs | Admin |
| POST | `/cv-zip-chunked` | Chunked ZIP upload | Admin |
| POST | `/save` | Save imported candidates | Admin |
| PUT | `/attach-cv/{id}` | Attach CV to candidate | Admin |
| GET | `/batches` | List import batches | Admin |
| GET | `/batches/{id}` | Batch details | Admin |
| POST | `/chunk/init` | Initialize chunked upload | Admin |
| POST | `/chunk/upload` | Upload chunk | Admin |
| POST | `/chunk/complete` | Complete chunked upload | Admin |

### Companies (`/api/companies`)
| Method | Endpoint | Description | Roles |
|--------|----------|-------------|-------|
| GET | `/companies` | List companies | Admin |
| GET | `/companies/{id}` | Get company | Admin |
| POST | `/companies` | Create company | Admin |
| PUT | `/companies/{id}` | Update company | Admin |
| DELETE | `/companies/{id}` | Delete company | Admin |

### Teams (`/api/teams`)
| Method | Endpoint | Description | Roles |
|--------|----------|-------------|-------|
| GET | `/teams` | List teams | Admin, Employer |
| GET | `/teams/{id}` | Get team | Admin, Employer |
| POST | `/teams` | Create team | Admin |
| PUT | `/teams/{id}` | Update team | Admin |
| DELETE | `/teams/{id}` | Delete team | Admin |
| POST | `/teams/{id}/recruiters/{rid}` | Add recruiter | Admin |
| DELETE | `/teams/{id}/recruiters/{rid}` | Remove recruiter | Admin |
| POST | `/teams/{id}/companies/{cid}` | Add company | Admin |
| GET | `/teams/{id}/stats` | Team statistics | Admin, Employer |

### Referrals (`/api/referrals`)
| Method | Endpoint | Description | Roles |
|--------|----------|-------------|-------|
| GET | `/referrals` | List referrals | Admin, Employer, Recruiter |
| GET | `/referrals/{id}` | Get referral | Admin, Employer, Recruiter |
| POST | `/referrals` | Create referral | All |
| POST | `/referrals/{id}/transition` | Change status | Admin, Employer, Recruiter |
| POST | `/referrals/{id}/link-candidate` | Link to candidate | Admin, Employer, Recruiter |

### Commercials & Revenue (`/api/commercials`, `/api/revenue`)
| Method | Endpoint | Description | Roles |
|--------|----------|-------------|-------|
| GET | `/commercials` | List commercials | Admin |
| POST | `/commercials` | Create commercial | Admin |
| PUT | `/commercials/{id}` | Update commercial | Admin |
| DELETE | `/commercials/{id}` | Delete commercial | Admin |
| POST | `/revenue/calculate` | Calculate placement fee | Admin, Employer |
| PUT | `/revenue/{id}/override` | Override revenue | Admin |
| GET | `/revenue/summary` | Revenue summary | Admin |
| GET | `/revenue/by-company` | Revenue by company | Admin |

### Bug Reports (`/api/bug-reports`)
| Method | Endpoint | Description | Roles |
|--------|----------|-------------|-------|
| GET | `/bug-reports` | List bug reports | Admin |
| GET | `/bug-reports/{id}` | Get report | Admin |
| POST | `/bug-reports` | Submit bug report | All |
| PUT | `/bug-reports/{id}` | Update status/priority | Admin |
| GET | `/bug-reports/stats/summary` | Statistics | Admin |

### System Errors (`/api/system-errors`)
| Method | Endpoint | Description | Roles |
|--------|----------|-------------|-------|
| POST | `/system-errors/frontend` | Report frontend error | No Auth |
| GET | `/system-errors` | List errors | Admin |
| GET | `/system-errors/stats` | Error statistics | Admin |
| DELETE | `/system-errors/clear` | Clear old errors | Admin |

### Statistics (`/api/stats`)
| Method | Endpoint | Description | Roles |
|--------|----------|-------------|-------|
| GET | `/stats/admin` | Admin dashboard stats | Admin |
| GET | `/stats/employer` | Employer stats | Employer |
| GET | `/stats/recruiter` | Recruiter stats | Recruiter |
| GET | `/stats/candidate` | Candidate stats | Candidate |

### Public/Career Page (`/api/public`)
| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/public/jobs` | Active career page jobs | No |
| GET | `/public/jobs/{id}` | Public job details | No |
| GET | `/public/mandate/{id}` | Shareable mandate link | No |
| POST | `/public/parse-resume` | Parse resume | No |
| POST | `/public/apply` | Apply for job | No |
| POST | `/public/upload-resume` | Upload resume | No |

---

## Feature Summary

### 1. Multi-Role Authentication
- JWT-based authentication
- 4 roles: Admin, Employer, Recruiter, Candidate
- Role-based access control on all endpoints
- Public registration limited to Candidate role only

### 2. Job Management
- Full CRUD for job postings
- Job approval workflow (draft → pending → active → closed)
- Career page publishing control
- Shareable job links (public mandate links)
- Recruiter assignment to mandates

### 3. AI-Powered Candidate Matching
- **Quick Match Mode:** Zero LLM calls, keyword + semantic scoring (~2-5 sec)
- **Full AI Match Mode:** LLM-powered deep analysis (background job, ~1-3 min)
- MongoDB Atlas Search for initial candidate filtering
- OpenAI embeddings for semantic similarity
- Must-have filters (location, skills, experience, qualification)
- Match history tracking

### 4. Candidate Data Bank
- Resume upload and AI parsing (PDF, DOC, DOCX, TXT)
- Batch resume parsing
- Candidate deduplication (fingerprinting)
- Profile editing with audit trail
- Candidate-to-job linking
- Application history tracking

### 5. Bulk Import
- Excel template import (Mode A)
- ZIP of CVs import (Mode B)
- Chunked file uploads for large files
- Async parsing with progress tracking
- Batch save with validation

### 6. Pipeline Management
- Application tracking across stages
- Stage transitions with audit
- Notes and comments
- Edit history for data governance
- Resume download with proper naming

### 7. Team & Company Management
- Company profiles
- Team creation and management
- Recruiter-to-team assignment
- Company-to-team assignment

### 8. Referral System
- Referral submission
- Status workflow (submitted → reviewed → contacted → converted)
- Link referral to candidate profile

### 9. Commercial Intelligence
- Fee structures per company
- Revenue calculation on placements
- Manual override with audit

### 10. Analytics & Reporting
- Admin dashboard with KPIs
- Employer and recruiter stats
- Pipeline analytics

### 11. Notifications (MOCKED)
- Job alert preferences
- Email notifications (Resend)
- WhatsApp notifications (Twilio)
- Notification history

### 12. Error Reporting & System Health
- Manual bug report submission ("Report Issue" button)
- Automatic frontend error capture (JS errors, API failures)
- Automatic backend 500 error capture
- Admin dashboard for error monitoring
- Error trend charts and statistics

---

## Frontend Structure

```
/app/frontend/src/
├── App.js                    # Main app with routing
├── index.js                  # Entry point
├── index.css                 # Global styles (Tailwind)
│
├── lib/
│   ├── api.js               # Axios client with all API functions
│   ├── auth.js              # Auth context and hooks
│   ├── utils.js             # Utility functions (cn, etc.)
│   ├── currency.js          # Currency formatting (INR)
│   └── errorCapture.js      # Auto error capture service
│
├── components/
│   ├── ui/                  # Shadcn/UI components
│   │   ├── button.jsx
│   │   ├── card.jsx
│   │   ├── dialog.jsx
│   │   ├── input.jsx
│   │   ├── select.jsx
│   │   ├── table.jsx
│   │   ├── tabs.jsx
│   │   └── ... (30+ components)
│   ├── layout/
│   │   └── DashboardLayout.jsx
│   └── shared/
│       ├── ReportIssueDialog.jsx
│       └── ...
│
├── pages/
│   ├── auth/
│   │   ├── Login.jsx
│   │   └── Register.jsx
│   │
│   ├── admin/
│   │   ├── AdminDashboard.jsx
│   │   ├── AdminUsersPage.jsx
│   │   ├── AdminCompaniesPage.jsx
│   │   ├── AdminTeamsPage.jsx
│   │   ├── AdminBugReportsPage.jsx
│   │   ├── SystemHealthPage.jsx
│   │   └── BulkImportPage.jsx
│   │
│   ├── employer/
│   │   ├── EmployerDashboard.jsx
│   │   ├── EmployerJobsPage.jsx
│   │   ├── CreateJobPage.jsx
│   │   ├── FindCandidatesPage.jsx    # AI Screening
│   │   ├── JobApplicantsPage.jsx
│   │   ├── EmployerPipelinePage.jsx
│   │   ├── EmployerCandidateBankPage.jsx
│   │   └── ...
│   │
│   ├── recruiter/
│   │   ├── RecruiterDashboard.jsx
│   │   ├── RecruiterJobsPage.jsx
│   │   ├── RecruiterCandidateBankPage.jsx
│   │   ├── PipelinePage.jsx
│   │   └── ...
│   │
│   ├── candidate/
│   │   ├── CandidateDashboard.jsx
│   │   ├── CandidateJobsPage.jsx
│   │   ├── CandidateApplicationsPage.jsx
│   │   └── CandidateProfilePage.jsx
│   │
│   ├── shared/
│   │   └── MatchHistoryPage.jsx
│   │
│   └── public/
│       ├── PublicWebsite.jsx         # Landing page
│       └── CareersPage.jsx           # Public job listings
│
└── hooks/
    └── use-toast.js
```

---

## Backend Structure

```
/app/backend/
├── server.py                 # FastAPI app + employer/analytics routes
├── config.py                 # DB, Redis, R2, constants
├── requirements.txt          # Python dependencies
│
├── core/
│   ├── config.py            # Environment config
│   ├── database.py          # MongoDB connection
│   ├── security.py          # JWT, password hashing
│   └── helpers.py           # Common utilities
│
├── models/
│   ├── user.py              # User schemas
│   ├── job.py               # Job schemas
│   ├── application.py       # Application schemas
│   ├── candidate.py         # Candidate profile schemas
│   ├── candidate_bank.py    # Candidate bank schemas
│   ├── company.py           # Company schemas
│   ├── team.py              # Team schemas
│   ├── referral.py          # Referral schemas
│   ├── commercial.py        # Commercial schemas
│   ├── matching.py          # AI matching schemas
│   ├── message.py           # Message schemas
│   └── alerts.py            # Alert preference schemas
│
├── routes/
│   ├── auth.py              # Authentication endpoints
│   ├── admin.py             # Admin endpoints (users, companies, stats)
│   ├── jobs.py              # Job CRUD + career page + assignments
│   ├── applications.py      # Applications + AI matching + shortlist
│   ├── candidates.py        # Candidate bank CRUD
│   ├── bulk_import.py       # Bulk import endpoints
│   ├── teams.py             # Team CRUD
│   ├── referrals.py         # Referral CRUD
│   ├── commercials.py       # Commercial + revenue endpoints
│   ├── bug_reports.py       # Bug report endpoints
│   ├── system_errors.py     # System error tracking
│   ├── settings.py          # User settings + alerts
│   ├── files.py             # File serving
│   ├── public.py            # Public/career page endpoints
│   └── background_jobs.py   # Background job status + cache/embedding mgmt
│
├── services/
│   ├── matching_engine.py   # AI matching logic (parse, score, filter)
│   ├── embeddings.py        # OpenAI embeddings with caching
│   ├── rate_limiter.py      # Per-user rate limiting
│   ├── cache.py             # Redis cache wrapper
│   ├── r2_storage.py        # Cloudflare R2 integration
│   ├── chunked_upload.py    # Chunked file upload handling
│   ├── email_service.py     # Email sending (Resend - MOCKED)
│   ├── whatsapp_service.py  # WhatsApp (Twilio - MOCKED)
│   ├── notification_service.py
│   ├── notification_templates.py
│   └── job_queue.py         # Background job queue
│
├── utils/
│   ├── auth.py              # Auth decorators (get_current_user, require_role)
│   └── governance.py        # Data governance helpers (audit trail)
│
├── scripts/
│   ├── create_indexes.py    # MongoDB index creation
│   └── migrate_to_atlas.py  # Atlas migration script
│
├── tests/                   # Comprehensive test suite (50+ test files)
│
└── uploads/                 # Local file storage fallback
```

---

## Authentication & Authorization

### JWT Token Flow
1. User logs in with email/password → `POST /api/auth/login`
2. Server validates credentials, returns JWT token
3. Client stores token in localStorage as `vhc_token`
4. All authenticated requests include `Authorization: Bearer <token>`
5. Server validates token and extracts user info

### Token Structure
```json
{
  "sub": "user_id",
  "email": "user@example.com",
  "role": "employer",
  "exp": 1234567890
}
```

### Role-Based Access Control
| Role | Access Level |
|------|--------------|
| Admin | Full system access, user management, all data |
| Employer | Own jobs, candidates, teams, recruiters |
| Recruiter | Assigned jobs, candidate bank, referrals |
| Candidate | Own profile, applications, job browsing |

### Decorators (Backend)
```python
# Get current user (any authenticated user)
@Depends(get_current_user)

# Require specific roles
@Depends(require_role(["admin", "employer"]))
```

---

## Environment Variables

### Backend (`/app/backend/.env`)
```bash
# Database
MONGO_URL=mongodb+srv://...
DB_NAME=vhc_talent_os

# Authentication
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480

# AI Services
EMERGENT_LLM_KEY=your-emergent-key
OPENAI_API_KEY=your-openai-key

# Cache
UPSTASH_REDIS_REST_URL=https://...
UPSTASH_REDIS_REST_TOKEN=...

# Storage
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=vhc-resumes

# Email (MOCKED)
RESEND_API_KEY=...
SENDER_EMAIL=noreply@vhctalent.com

# WhatsApp (MOCKED)
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_NUMBER=...

# Config
CORS_ORIGINS=*
JOB_MATCH_THRESHOLD=0.5
NOTIFICATION_ENABLED=true
```

### Frontend (`/app/frontend/.env`)
```bash
REACT_APP_BACKEND_URL=https://your-domain.com
```

---

## Test Credentials

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@vhc.in | VhcAdmin@2024 |
| Employer | employer@vhctalent.com | VhcTalent@2024 |
| Recruiter | recruiter@vhctalent.com | VhcTalent@2024 |

---

## Performance Benchmarks

### Load Test Results (Feb 2026)
- **Concurrent Users:** 75
- **Total Requests:** 150
- **Error Rate:** 0%
- **Avg Response Time:** 0.24s
- **Grade:** A+

### Optimizations Implemented
1. In-memory LRU cache for match results (2-min TTL)
2. Thundering herd prevention with per-key locks
3. MongoDB connection pooling (maxConnecting=3)
4. Embedding service caching
5. Concurrency limiter (max 10 simultaneous DB operations)
6. Quick Match mode (zero LLM calls)

---

## Known Limitations & Mocked Services

### Mocked Integrations
1. **Resend (Email)** — Integration code exists, returns mock success
2. **Twilio (WhatsApp)** — Integration code exists, returns mock success

### Limitations
1. MongoDB Atlas requires IP whitelisting (dynamic pod IPs may need manual updates)
2. Cloudflare R2 may have intermittent connectivity issues
3. Full AI Match can take 1-3 minutes for large candidate pools
4. Semantic search disabled in Quick Match mode for performance

---

## Quick Start for Developers

### Running Locally
```bash
# Backend
cd /app/backend
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# Frontend
cd /app/frontend
yarn install
yarn start
```

### Running Tests
```bash
cd /app/backend
pytest tests/ -v
```

### Key Files to Start With
1. `/app/backend/server.py` — Main FastAPI application
2. `/app/frontend/src/lib/api.js` — All frontend API calls
3. `/app/backend/routes/applications.py` — AI matching logic
4. `/app/backend/services/matching_engine.py` — Core matching algorithms

---

## Contact & Support

For questions about this codebase, refer to:
- PRD: `/app/memory/PRD.md`
- Test Reports: `/app/test_reports/`
- API Documentation: FastAPI auto-docs at `/docs` or `/redoc`

---

*Document generated: February 8, 2026*
