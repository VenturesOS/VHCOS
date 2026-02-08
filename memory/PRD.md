# VHC Talent OS — Product Requirements Document

## Original Problem Statement
Build an Enhanced Bulk Candidate Import Tool for a recruitment portal (VHC Talent OS). Scope expanded to include UI fixes, inline editing, performance optimizations, MongoDB Atlas migration, and a phased scaling plan. Most recently: stress-test the platform, identify bottlenecks, achieve A+ grade performance for 50-75 concurrent users with <5% error rate.

## Tech Stack
- **Frontend:** React, Tailwind CSS, Shadcn/UI
- **Backend:** FastAPI (Python), Uvicorn
- **Database:** MongoDB Atlas (with Atlas Search)
- **Cache:** Upstash Redis
- **Storage:** Cloudflare R2
- **AI:** OpenAI GPT (resume parsing, JD parsing, matching), OpenAI Embeddings (semantic search)
- **Auth:** JWT-based custom auth

## Core Features (Implemented)
1. **Bulk Candidate Import** — Chunked file uploads, async CV parsing, progress notifications
2. **AI Matching Engine** — Quick Match (non-LLM, keyword+semantic) and Full AI Match (LLM-powered, background job)
3. **Vector Embeddings & Semantic Search** — OpenAI embeddings for candidate bank
4. **Multi-role Portal** — Admin, Employer, Recruiter dashboards
5. **Teams, Referrals, Commercials** — Full CRUD, modular route files
6. **Rate Limiting** — Per-user, per-endpoint
7. **Caching** — In-memory + Redis for match results, thundering herd prevention
8. **Analytics** — Admin dashboard with KPIs
9. **Pipeline Management** — Application tracking across hiring stages

## Performance Benchmarks (Achieved)
- **Load Test:** 150 requests at 75 concurrent — 0% error rate, 0.24s avg response
- **Grade:** A+
- **Cache hit latency:** <0.25s

## User Personas
- **Admin:** Full system control, team/user management, analytics
- **Employer:** Job posting, candidate matching, team oversight
- **Recruiter:** Job management, candidate sourcing, referrals

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Employer: employer@vhctalent.com / VhcTalent@2024
- Recruiter: recruiter@vhctalent.com / VhcTalent@2024

## Mocked Integrations
- Resend (email)
- Twilio (WhatsApp)

## Architecture
```
/app/backend/
├── config.py              # DB, Redis, R2 config
├── server.py              # FastAPI app, middleware, employer/analytics endpoints
├── models/                # Pydantic models
├── routes/
│   ├── applications.py    # AI matching (quick + full_ai + polling)
│   ├── auth.py            # JWT auth + rate limiting
│   ├── bulk_import.py     # Chunked uploads + async parsing
│   ├── teams.py           # Teams CRUD
│   ├── referrals.py       # Referrals CRUD
│   ├── commercials.py     # Commercials + Revenue CRUD
│   ├── admin.py           # Admin endpoints
│   ├── jobs.py, candidates.py, files.py, settings.py, public.py
│   └── background_jobs.py
├── services/
│   ├── matching_engine.py # Fast + AI scoring functions
│   ├── embeddings.py      # OpenAI embeddings with caching
│   └── rate_limiter.py    # Per-user rate limiting
└── tests/
    ├── load_test_v3.py    # Performance load test
    └── test_matching_refactor.py
```

## What's Been Completed (Feb 2026)
- [x] P0: AI matching performance bottleneck resolved — Quick Match (zero LLM), Full AI (background job)
- [x] P0: Load test passed — 75 concurrent users, 0% error rate, A+ grade
- [x] P1: server.py refactored — teams/referrals/commercials extracted to dedicated route files
- [x] P2: UI toggle for Quick Match vs Full AI Match with background job progress polling
- [x] Match History page for Employer & Recruiter — list + detail view with saved top results
- [x] In-memory caching with thundering herd prevention
- [x] MongoDB connection pooling optimized for Atlas (maxConnecting=3)
- [x] Embedding service caching (LRU for job embeddings)
- [x] System Health monitoring — auto-capture frontend JS errors, API failures, backend 500s with admin dashboard
- [x] Bug Reports system — "Report Issue" button for all roles + Admin dashboard with stats/filtering
- [x] Signup restricted to candidate-only (employer/recruiter/admin created by admin)
- [x] Copyright year updated to 2026 across login/register pages
- [x] MongoDB startup resilience (non-blocking validation, auto-reconnect)

## Backlog (Prioritized)
### P1
- Implement WhatsApp & Email Campaign Automation (currently mocked)

### P2
- Integrate Stripe for payments
- Build multi-tenancy architecture for B2B SaaS model
- Semantic search toggle in Quick Match mode (currently skipped for speed)

### P3
- Production deployment optimization (multi-worker uvicorn, gunicorn)
- Advanced analytics dashboard
- Candidate deduplication improvements
