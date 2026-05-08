# VHC Talent OS — Developer Quick Start Guide

> **Version:** 2.0 | **Last Updated:** February 8, 2026

---

## 🚀 Quick Start (5 Minutes)

### 1. Clone & Setup
```bash
# Backend
cd /app/backend
pip install -r requirements.txt

# Frontend
cd /app/frontend
yarn install
```

### 2. Environment Variables
**Backend** (`/app/backend/.env`):
```env
MONGO_URL=mongodb+srv://...
DB_NAME=vhc_talent_os
JWT_SECRET_KEY=your-secret
EMERGENT_LLM_KEY=your-key
UPSTASH_REDIS_REST_URL=https://...
UPSTASH_REDIS_REST_TOKEN=...
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=vhc-resumes
```

**Frontend** (`/app/frontend/.env`):
```env
REACT_APP_BACKEND_URL=https://your-domain.com
```

### 3. Run Services
```bash
# Backend (port 8001)
cd /app/backend
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# Frontend (port 3000)
cd /app/frontend
yarn start
```

### 4. Test Credentials
| Role | Email | Password |
|------|-------|----------|
| **Admin** | admin@vhc.in | VhcAdmin@2024 |
| **Employer** | employer@vhctalent.com | VhcTalent@2024 |
| **Recruiter** | recruiter@vhctalent.com | VhcTalent@2024 |

---

## 📁 Project Structure

```
/app/
├── backend/
│   ├── server.py          # Main FastAPI app
│   ├── routes/            # API endpoints (15 files)
│   ├── services/          # Business logic (10 files)
│   ├── models/            # Pydantic schemas
│   └── tests/             # Test suite (50+ files)
│
└── frontend/
    └── src/
        ├── App.js         # Main React app
        ├── lib/api.js     # All API calls
        ├── pages/         # Role-based pages
        └── components/    # UI components
```

---

## 🔧 Tech Stack Summary

| Layer | Technology |
|-------|------------|
| Frontend | React 18, Tailwind CSS, Shadcn/UI |
| Backend | FastAPI, Python 3.11, Pydantic v2 |
| Database | MongoDB Atlas + Atlas Search |
| Cache | Upstash Redis |
| Storage | Cloudflare R2 |
| AI | OpenAI GPT-4o + Embeddings |

---

## 🔐 Authentication

**Flow:** JWT Bearer Token

```javascript
// Login
POST /api/auth/login
Body: { "email": "...", "password": "..." }
Response: { "access_token": "eyJ...", "token_type": "bearer" }

// Use token
Headers: { "Authorization": "Bearer eyJ..." }
```

**Roles:** `admin` | `employer` | `recruiter` | `candidate`

---

## 📡 Key API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | Login |
| POST | `/api/auth/register` | Register (candidate only) |
| GET | `/api/auth/me` | Current user |

### Jobs
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/jobs` | List jobs |
| POST | `/api/jobs` | Create job |
| GET | `/api/jobs/{id}` | Get job |
| PUT | `/api/jobs/{id}` | Update job |

### Applications & Pipeline
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/applications` | List applications |
| POST | `/api/applications` | Apply for job |
| PUT | `/api/applications/{id}` | Update stage |
| GET | `/api/jobs/{id}/applicants` | Job pipeline |

### AI Matching
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/matching/find-candidates` | Find matches |
| GET | `/api/matching/jobs/{id}/status` | Poll background job |
| POST | `/api/matching/shortlist` | Add to pipeline |

### Candidate Bank
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/candidate-bank` | List candidates |
| POST | `/api/candidate-bank/add` | Add with resume |
| GET | `/api/candidate-bank/{id}` | Get candidate |

---

## 🗄️ Database Collections

| Collection | Purpose |
|------------|---------|
| `users` | User accounts (all roles) |
| `jobs` | Job postings |
| `applications` | Job applications |
| `candidate_bank` | Candidate profiles + resumes |
| `companies` | Company profiles |
| `teams` | Employer teams |
| `referrals` | Referral submissions |
| `commercials` | Fee structures |
| `match_results` | AI match history |
| `bug_reports` | User-submitted bugs |
| `system_errors` | Auto-captured errors |

---

## 🤖 AI Matching Modes

### Quick Match (Default)
- **Speed:** 2-5 seconds
- **Method:** Keyword + semantic scoring
- **LLM Calls:** Zero

### Full AI Match
- **Speed:** 1-3 minutes (background)
- **Method:** LLM-powered deep analysis
- **Polling:** `GET /api/matching/jobs/{id}/status`

---

## 📂 Key Files to Know

| File | Purpose |
|------|---------|
| `/app/backend/server.py` | FastAPI app entry point |
| `/app/backend/routes/applications.py` | AI matching logic |
| `/app/backend/services/matching_engine.py` | Core matching algorithms |
| `/app/frontend/src/lib/api.js` | All frontend API calls |
| `/app/frontend/src/pages/employer/FindCandidatesPage.jsx` | AI screening UI |

---

## ⚠️ Known Limitations

| Service | Status |
|---------|--------|
| **Resend (Email)** | MOCKED — returns success |
| **Twilio (WhatsApp)** | MOCKED — returns success |
| **MongoDB Atlas** | Requires IP whitelisting |

---

## 🧪 Running Tests

```bash
cd /app/backend
pytest tests/ -v                    # All tests
pytest tests/test_shortlist*.py -v  # Specific test
```

---

## 📊 API Documentation

- **Swagger UI:** `https://your-domain.com/docs`
- **ReDoc:** `https://your-domain.com/redoc`

---

## 🔗 Useful Commands

```bash
# Check backend logs
tail -f /var/log/supervisor/backend.err.log

# Restart services
sudo supervisorctl restart backend
sudo supervisorctl restart frontend

# Check service status
sudo supervisorctl status
```

---

## 📞 Need Help?

1. **Full Documentation:** `/app/PROJECT_DOCUMENTATION.md`
2. **PRD:** `/app/memory/PRD.md`
3. **Test Reports:** `/app/test_reports/`

---

*Quick Start Guide v2.0 — February 2026*
