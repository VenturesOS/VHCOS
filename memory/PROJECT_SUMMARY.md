# VHC Talent OS - Complete Project Summary
## Comprehensive Documentation for Handoff & Continuity

---

## 📋 Project Overview

**VHC Talent OS** is a full-stack recruitment management platform designed for multi-tenant B2B SaaS operations. It enables organizations to manage their entire hiring pipeline from job posting to candidate placement with AI-powered matching, governance controls, and commercial intelligence.

### Target Users
1. **Admin** - Platform administrators with full system access
2. **Employer** - Client companies managing their hiring needs
3. **Recruiter** - Recruitment agents working on assigned mandates
4. **Candidate** - Job seekers applying through career pages

### Tech Stack
| Layer | Technology |
|-------|------------|
| **Frontend** | React 18, Tailwind CSS, Shadcn/UI, Lucide Icons |
| **Backend** | FastAPI (Python 3.11), Pydantic v2 |
| **Database** | MongoDB Atlas (Cloud) |
| **Cache** | Upstash Redis |
| **Storage** | Cloudflare R2 (S3-compatible) |
| **AI/ML** | OpenAI GPT-4/5.2 (via Emergent LLM Key), OpenAI Embeddings |
| **Search** | MongoDB Atlas Search (Full-text + Fuzzy) |

---

## 🏗️ Architecture

### Backend Structure
```
/app/backend/
├── server.py              # Main FastAPI app (2439 lines)
├── config.py              # Database & service configuration
├── utils.py               # Auth utilities, helpers
├── routes/                # API route handlers
│   ├── admin.py           # Admin user management, companies
│   ├── applications.py    # Applications & AI matching (1300+ lines)
│   ├── auth.py            # Authentication (login, register, JWT)
│   ├── background_jobs.py # Background tasks, embeddings
│   ├── bulk_import.py     # Excel/CV bulk import (1400+ lines)
│   ├── candidates.py      # Candidate bank operations (1400+ lines)
│   ├── commercials.py     # Commercial intelligence & revenue (NEW)
│   ├── files.py           # File serving & downloads
│   ├── jobs.py            # Job CRUD, career page, mandates
│   ├── public.py          # Public endpoints (career page)
│   ├── referrals.py       # Referral management (NEW)
│   ├── settings.py        # User settings, notifications
│   └── teams.py           # Team management (NEW)
├── services/              # Business logic services
│   ├── cache.py           # Redis caching layer
│   ├── chunked_upload.py  # Large file upload handler
│   ├── embeddings.py      # Vector embeddings (OpenAI)
│   ├── email_service.py   # Email notifications (Resend)
│   ├── job_queue.py       # Background job processing
│   ├── matching_engine.py # AI candidate-job matching
│   ├── notification_service.py  # Multi-channel notifications
│   ├── r2_storage.py      # Cloudflare R2 integration
│   └── whatsapp_service.py # WhatsApp (Twilio) - MOCKED
├── models/                # Pydantic models
│   ├── user.py, job.py, application.py, etc.
│   └── matching.py        # AI matching models
└── scripts/
    └── create_indexes.py  # MongoDB index setup
```

### Frontend Structure
```
/app/frontend/src/
├── pages/
│   ├── admin/             # 15 admin pages
│   │   ├── AdminDashboard.jsx
│   │   ├── CandidateDataBankPage.jsx
│   │   ├── BulkImportPage.jsx
│   │   ├── JobsPage.jsx
│   │   ├── CommercialsPage.jsx
│   │   └── ... (10 more)
│   ├── employer/          # 13 employer pages
│   │   ├── EmployerDashboard.jsx
│   │   ├── FindCandidatesPage.jsx
│   │   ├── EmployerPipelinePage.jsx
│   │   └── ... (10 more)
│   ├── recruiter/         # 6 recruiter pages
│   │   ├── RecruiterDashboard.jsx
│   │   ├── RecruiterCandidateBankPage.jsx
│   │   └── ... (4 more)
│   ├── candidate/         # Candidate portal
│   ├── public/            # Career pages
│   └── auth/              # Login/Register
├── components/
│   ├── ui/                # Shadcn components
│   └── shared/            # Reusable components
└── lib/                   # Utilities
```

---

## 🔐 Authentication & Authorization

### JWT-Based Auth
- Token expires in 24 hours (1440 minutes)
- Stored in localStorage as `vhc_token`
- Role-based access control (RBAC)

### User Roles & Permissions
| Role | Scope |
|------|-------|
| **Admin** | Full platform access, user management, governance |
| **Employer** | Assigned companies, jobs, team management |
| **Recruiter** | Assigned mandates, candidate sourcing |
| **Candidate** | Self-service profile, applications |

### Test Credentials
```
Admin:     admin@vhc.in / VhcAdmin@2024
Employer:  employer@vhctalent.com / VhcTalent@2024
Recruiter: recruiter@vhctalent.com / VhcTalent@2024
```

---

## 🗄️ Database Schema (MongoDB Atlas)

### Collections
| Collection | Purpose | Key Indexes |
|------------|---------|-------------|
| `users` | User accounts | email (unique), role |
| `companies` | Client companies | name, assigned_employer_id |
| `jobs` | Job postings | status, company_id, Atlas Search |
| `applications` | Job applications | job_id, candidate_id, stage |
| `candidate_bank` | Candidate profiles | email, skills, Atlas Search, embedding |
| `teams` | Team hierarchy | employer_id |
| `commercials` | Revenue tracking | company_id, job_id |
| `referrals` | Candidate referrals | referred_by |
| `bulk_import_batches` | Import history | created_by |
| `notifications` | Notification logs | user_id, type |
| `settings` | User preferences | user_id |

### Atlas Search Indexes
- `candidate_search` - Full-text on name, skills, location, employer, designation
- `job_search` - Full-text on title, description, requirements

---

## 🤖 AI & Machine Learning Features

### 1. Resume/JD Parsing (GPT-4)
- Extracts structured data from PDF/DOC resumes
- Parses job descriptions to extract skills, requirements
- Uses Emergent LLM Key for API access

### 2. AI Candidate-Job Matching
**Two-Stage Process:**
1. **Pre-filter** (Fast): MongoDB aggregation with skill matching
2. **AI Scoring** (GPT): Detailed compatibility analysis

**Scoring Formula (Quick Match):**
```
Score = 40% skill_match + 25% experience + 25% semantic + 10% base
```

**Scoring Formula (Full AI Match):**
```
Score = 70% AI_score + 30% semantic_score
```

### 3. Vector Embeddings (OpenAI)
- Model: `text-embedding-3-small` (1536 dimensions)
- Coverage: 96.53% of candidates (1642/1701)
- Auto-embeds new candidates on creation
- Enables semantic search ("Python dev" matches "Django engineer")

### 4. Deduplication
- Resume fingerprinting (content hash)
- Phone/email matching
- Similarity scoring for potential duplicates

---

## 📦 External Services & Integrations

### 1. MongoDB Atlas (Database)
```env
MONGO_URL="mongodb+srv://vhc_admin:xxx@cluster0.vuhdiod.mongodb.net/"
DB_NAME="vhc_talent_os"
```
- Cloud-hosted MongoDB
- Atlas Search enabled
- Indexes optimized for performance

### 2. Upstash Redis (Caching)
```env
UPSTASH_REDIS_REST_URL=https://quality-gopher-48093.upstash.io
UPSTASH_REDIS_REST_TOKEN=xxx
```
- Caches search results (5-15 min TTL)
- Stores embeddings temporarily
- Background job queue

### 3. Cloudflare R2 (Storage)
```env
R2_ACCOUNT_ID=xxx
R2_ACCESS_KEY_ID=xxx
R2_SECRET_ACCESS_KEY=xxx
R2_BUCKET_NAME=vhc-talent-os-storage
```
- Resume/CV storage
- Signed URL generation (1-hour expiry)
- S3-compatible API

### 4. OpenAI (AI Services)
```env
EMERGENT_LLM_KEY=sk-emergent-xxx  # For GPT text generation
OPENAI_API_KEY=sk-proj-xxx        # For embeddings
```
- GPT-4/5.2 for parsing & matching
- text-embedding-3-small for semantic search

### 5. Resend (Email) - MOCKED
```env
RESEND_API_KEY=re_placeholder_key
SENDER_EMAIL=notifications@vhctalent.com
```
- Job match notifications
- Application status updates
- Currently returns mock responses

### 6. Twilio (WhatsApp) - MOCKED
```env
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_NUMBER=
```
- Not yet configured
- Service exists but disabled

---

## 📊 Key API Endpoints

### Authentication
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/register` | POST | User registration |
| `/api/auth/login` | POST | Login, returns JWT |
| `/api/auth/me` | GET | Current user profile |

### Jobs
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/jobs` | GET/POST | List/Create jobs |
| `/api/jobs/{id}` | GET/PUT/DELETE | Job CRUD |
| `/api/jobs/browse` | GET | Public job listing (cached) |
| `/api/career-page/jobs` | GET | Career page jobs (cached) |
| `/api/jobs/parse-jd` | POST | AI parse job description |

### Candidates
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/candidate-bank` | GET | Search candidates (paginated, cached) |
| `/api/candidate-bank/{id}` | GET/PUT | Candidate profile |
| `/api/candidate-bank/add-or-update` | POST | Upsert candidate |

### AI Matching
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/matching/find-candidates` | POST | AI candidate matching |
| `/api/ai/parse-resume` | POST | Parse resume with AI |

### Bulk Import
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/admin/bulk-import/excel` | POST | Excel import |
| `/api/admin/bulk-import/cv-zip` | POST | CV ZIP import |
| `/api/admin/bulk-import/chunk/*` | POST | Chunked upload (large files) |

### Embeddings
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/embeddings/health` | GET | Service health check |
| `/api/embeddings/stats` | GET | Coverage statistics |
| `/api/embeddings/generate-batch` | POST | Batch generation |

---

## 🚀 Features by Module

### 1. Admin Dashboard
- Platform statistics (users, jobs, applications)
- User management (create, edit, delete)
- Company management with employer assignment
- Team hierarchy management
- Commercial intelligence & revenue tracking
- Bulk candidate import (Excel + CV modes)
- Candidate data bank with full access

### 2. Employer Portal
- Dashboard with assigned companies stats
- Job creation with AI JD parsing
- Mandate allocation to recruiters
- AI candidate screening/matching
- Pipeline management (stage transitions)
- Team member view
- Candidate bank (filtered by access)

### 3. Recruiter Portal
- Dashboard with assigned mandates
- Job pipeline view
- Candidate sourcing & referrals
- Application tracking
- Limited candidate bank access

### 4. Career Page (Public)
- Company-branded job listings
- Shareable job links (VHC-XXXX-XXXX format)
- Public application form
- Cloudflare Turnstile bot protection

### 5. Bulk Import Tool
- **Excel Mode**: Upload spreadsheet with candidate data
- **CV/ZIP Mode**: Upload ZIP with resumes + optional Excel
- **Features**:
  - AI resume parsing
  - Deduplication detection
  - Industry auto-detection
  - Chunked upload (up to 100MB)
  - Progress notifications with ETA
  - Admin-only governance controls

### 6. AI Matching Engine
- Two-stage matching (pre-filter + AI scoring)
- Semantic search with vector embeddings
- Quick match mode (skip LLM for speed)
- Skill gap analysis
- Match explanation

---

## 📈 Performance Optimizations

### 1. Database Indexes
- 15+ indexes across collections
- Compound indexes for common queries
- Text indexes for search

### 2. Caching (Redis)
| Data | TTL | Cache Key Pattern |
|------|-----|-------------------|
| Candidate search | 5 min | `candidates:search:{hash}` |
| Job browse | 3 min | `jobs_browse:{filters}` |
| Career page jobs | 5 min | `career_page_jobs` |
| Embeddings | 30 min | `emb:{candidate_id}` |

### 3. Atlas Search
- Fuzzy matching (typo tolerance)
- Fast full-text queries (<100ms)
- Replaces slow regex searches

### 4. Pagination & Debouncing
- Server-side pagination (50/page default)
- 300ms search debounce on frontend
- Infinite scroll support

### 5. Chunked Uploads
- 512KB chunks bypass proxy limits
- Up to 100MB file support
- Progress tracking

---

## 🔧 Configuration Files

### Backend (.env)
```env
# Database
MONGO_URL="mongodb+srv://..."
DB_NAME="vhc_talent_os"

# Auth
JWT_SECRET_KEY="vhc-talent-os-jwt-secret-key-2024-production"
JWT_ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# AI Services
EMERGENT_LLM_KEY=sk-emergent-xxx
OPENAI_API_KEY=sk-proj-xxx

# Cache
UPSTASH_REDIS_REST_URL=https://...
UPSTASH_REDIS_REST_TOKEN=xxx

# Storage
R2_ACCOUNT_ID=xxx
R2_ACCESS_KEY_ID=xxx
R2_SECRET_ACCESS_KEY=xxx
R2_BUCKET_NAME=vhc-talent-os-storage

# Notifications (MOCKED)
RESEND_API_KEY=re_placeholder_key
```

### Frontend (.env)
```env
REACT_APP_BACKEND_URL=https://pause-reset-deploy.preview.emergentagent.com
WDS_SOCKET_PORT=443
```

---

## 🐛 Known Issues & Mocked Services

### Mocked/Placeholder Services
1. **Resend Email** - Returns mock success, not sending real emails
2. **Twilio WhatsApp** - Not configured, service exists but disabled
3. **Stripe Payments** - Not implemented

### Pending Refactoring
1. `server.py` still contains Team, Referral, Commercial logic (~2400 lines)
2. Should be split into dedicated route files

---

## 📅 Development Timeline

| Date | Milestone |
|------|-----------|
| Jan 19, 2026 | Phase-2 Part A Complete |
| Jan 23, 2026 | Internal Governance & Hierarchy |
| Jan 27, 2026 | Shareable Links & JD Parsing |
| Jan 29, 2026 | Cloudflare R2 Storage Integration |
| Jan 31, 2026 | Bulk Import Tool Complete |
| Feb 4, 2026 | Database Performance Optimization |
| Feb 6, 2026 | MongoDB Atlas Migration & Search |
| Feb 6, 2026 | Redis Caching & Background Jobs |
| Feb 7, 2026 | Chunked Uploads & Semantic Search |

---

## 🔮 Roadmap (Future Tasks)

### P1 - High Priority
- [ ] Background CV Parsing (use job queue)
- [ ] Complete server.py refactoring

### P2 - Medium Priority
- [ ] Real email integration (Resend)
- [ ] WhatsApp notifications (Twilio)
- [ ] Stripe payments

### P3 - Low Priority / Backlog
- [ ] Multi-tenancy architecture
- [ ] Advanced analytics dashboard
- [ ] Mobile app (React Native)

---

## 📝 Test Reports

All test reports stored in `/app/test_reports/`:
- `iteration_42.json` - Chunked upload tests (13/13 passed)
- `iteration_43.json` - Semantic search tests (15/15 passed)

---

## 🔑 Quick Start Commands

```bash
# Restart services
sudo supervisorctl restart backend frontend

# Check logs
tail -f /var/log/supervisor/backend.err.log

# Test API
API_URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2)
curl -s "$API_URL/api/health"

# Login and get token
TOKEN=$(curl -s -X POST "$API_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@vhc.in","password":"VhcAdmin@2024"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# Check embeddings
curl -s "$API_URL/api/embeddings/stats" -H "Authorization: Bearer $TOKEN"
```

---

*Document generated: February 7, 2026*
*Coverage: All features implemented across 40+ development sessions*
