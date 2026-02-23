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
LIVE production backend was crashing on startup (502/520 errors). The previous agent had added complex .env override logic, DB_NAME prefix stripping, Atlas safety guards, and defensive try/except blocks to `config.py`. These changes worked in preview but crashed the LIVE server.

### Fix Applied
**Simplified `config.py` to bare essentials:**
- Removed `dotenv_values` double-read and MONGODB_URI override hack
- Removed `DB_NAME` prefix stripping and canonical name forcing
- Removed unused `ssl_context` block and `ssl` import
- Removed Atlas safety log block
- Now uses only: `load_dotenv()` → `os.environ.get('MONGO_URL')` → connect

### Key Files Changed
- `/app/backend/config.py` — Simplified to ~100 lines (was ~140+ with defensive code)

### Previous Stability Fixes (Still in Place)
1. **Cache-Busting Headers** (`server.py`): All `/api/` responses include no-cache headers
2. **Diagnostic Endpoint** (`maintenance_routes.py`): `/api/system-health/diagnostic/users`
3. **Email Normalization** (`auth.py`, `admin.py`): `.lower().strip()` on all user flows
4. **Environment Badge** (`EnvironmentBadge.jsx`): Shows "PREVIEW MODE" banner
5. **Centralized Environment Resolver** (`utils/environment.py`)
6. **Zero Trust in AUDIT mode** (`backend/.env`)

### Deployment Steps for LIVE
1. Deploy latest backend code (the simplified `config.py` is the critical change)
2. Verify backend starts (no 502 errors)
3. Test login: `curl https://ventureshrd.com/api/auth/login -X POST -H "Content-Type: application/json" -d '{"email":"admin@vhc.in","password":"VhcAdmin@2024"}'`
4. Once LIVE is stable, apply a clean minimal DB fix if needed (ensure correct Atlas DB)

## Backlog / Future Tasks
- **P1: AI-driven Analytics and Insights**
- **P2: Client Dashboard Enhancements**
- **P3: Advanced Revenue Intelligence**
- **Blocked: LinkedIn Auto-Posting** (requires `w_organization_social` scope)

## Test Credentials
- **Admin:** admin@vhc.in / VhcAdmin@2024
- **Recruiter:** bhumika@vhc.in / 12345678
