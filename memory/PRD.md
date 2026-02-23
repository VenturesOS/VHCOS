# VHC Talent OS — Product Requirements Document

## Original Problem Statement
Build a comprehensive recruitment management portal (Talent OS) for Ventures HRD, covering industrial hiring with a 7-stage pipeline, multi-role dashboards, AI-powered features, enterprise compliance, and security hardening.

## Core Architecture
- **Frontend:** React 18 + Shadcn/UI + Tailwind CSS
- **Backend:** FastAPI (Python) + MongoDB Atlas
- **Storage:** Cloudflare R2
- **Security:** Cloudflare Turnstile (CAPTCHA), Cloudflare Zero Trust, Rate Limiting, File Validation
- **AI:** OpenAI GPT-4o-mini (blog, matching, search)
- **Email:** Resend
- **Cache:** Upstash Redis

## Recent Fix — P0 Backend Crash Resolution (Feb 23, 2026)

### Problem
LIVE production backend was crashing on startup (502/520 errors). Previous agent had added complex .env override logic, DB_NAME prefix stripping, Atlas safety guards, and defensive try/except blocks to `config.py`.

### Fixes Applied
1. **Simplified `config.py`** — Removed dotenv_values double-read, MONGODB_URI override, DB_NAME prefix stripping, unused ssl_context. Now uses only `load_dotenv()` → `os.environ.get()` → connect.
2. **CORS wildcard** — Updated CORS_ORIGINS to `*` for Emergent deployment compatibility. Server.py now detects wildcard and uses it directly.

### Deployment Readiness
- Backend starts clean, login works, CORS allows all origins
- Supervisor config valid for both frontend + backend
- LinkedIn OAuth redirect hardcoded to ventureshrd.com (known limitation)

### Deployment Steps for LIVE
1. Deploy latest backend code
2. Verify backend starts (no 502 errors)
3. Test login endpoint
4. Once LIVE stable, apply clean minimal DB fix if connecting to wrong DB

## Previous Stability Fixes (Still in Place)
- Cache-Busting Headers on all /api/ responses
- Diagnostic Endpoint: `/api/system-health/diagnostic/users`
- Email Normalization in auth/admin routes
- Environment Badge (PREVIEW MODE banner)
- Centralized Environment Resolver (`utils/environment.py`)
- Zero Trust in AUDIT mode

## Backlog / Future Tasks
- **P1: AI-driven Analytics and Insights**
- **P2: Client Dashboard Enhancements**
- **P3: Advanced Revenue Intelligence**
- **Blocked: LinkedIn Auto-Posting** (requires `w_organization_social` scope)

## Test Credentials
- **Admin:** admin@vhc.in / VhcAdmin@2024
- **Recruiter:** bhumika@vhc.in / 12345678
