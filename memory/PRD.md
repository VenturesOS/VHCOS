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

## Recently Completed — Production Stability Hardening (Feb 22, 2026)

### Root Cause: LIVE vs Preview Data Mismatch
**Problem:** `bhumika@vhc.in` (recruiter) visible in preview but not on LIVE.
**Root Cause:** `config.py` line 29 checked `MONGODB_URI` before `MONGO_URL`. If the LIVE deployment platform injects `MONGODB_URI` (pointing to a different/local DB), it silently overrides the Atlas connection string from `.env`. This caused the LIVE backend to connect to a different database with different user data.

### Fixes Applied
1. **DB Connection Priority Fix** (`config.py`): `.env` `MONGO_URL` now forcibly sets BOTH `MONGO_URL` AND `MONGODB_URI` env vars. Connection string lookup now checks `MONGO_URL` first. Platform-injected `MONGODB_URI` can no longer override.

2. **API Cache-Busting** (`server.py`): All `/api/` responses now include `Cache-Control: no-store, no-cache, must-revalidate`, `Pragma: no-cache`, `CDN-Cache-Control: no-store`, `Cloudflare-CDN-Cache-Control: no-store`. Prevents Cloudflare/browser from serving stale API data.

3. **Diagnostic Endpoint** (`maintenance_routes.py`): `GET /api/system-health/diagnostic/users` — returns live user counts, list, DB name, and environment. NOT behind Zero Trust. Use on LIVE to verify data matches.

4. **Startup DB Audit** (`server.py`): Logs which connection string is active, whether MONGO_URL and MONGODB_URI match, and a user count sanity check on every boot.

5. **Email Normalization** (`auth.py`, `admin.py`): All user creation/login flows apply `.lower().strip()`.

6. **Environment Badge** (`EnvironmentBadge.jsx`): Shows "PREVIEW MODE" banner only when `APP_URL` (Emergent pod signal) is detected. Won't show on production.

7. **Centralized Environment Resolver** (`utils/environment.py`): Single source of truth for environment detection.

### Deployment Steps Required for LIVE
1. **Deploy latest backend code** — the `config.py` fix is critical
2. **Purge Cloudflare cache** for ventureshrd.com
3. **Check startup logs** — should show `ATLAS | DB: vhc_talent_os | sanity: 19 documents`
4. **Test diagnostic endpoint**: `curl https://ventureshrd.com/api/system-health/diagnostic/users -H "Authorization: Bearer <token>"`

### Key Files Changed
- `/app/backend/config.py` — DB connection priority fix
- `/app/backend/server.py` — Cache headers, startup audit
- `/app/backend/routes/maintenance_routes.py` — Diagnostic endpoint
- `/app/backend/routes/auth.py` — Email normalization
- `/app/backend/routes/admin.py` — Email normalization
- `/app/backend/utils/environment.py` — Centralized env resolver
- `/app/frontend/src/components/shared/EnvironmentBadge.jsx` — Preview banner
- `/app/frontend/src/components/layout/DashboardLayout.jsx` — Badge integration

## Backlog / Future Tasks
- **P1: AI-driven Analytics and Insights**
- **P2: Client Dashboard Enhancements**
- **P3: Advanced Revenue Intelligence**
- **Blocked: LinkedIn Auto-Posting** (requires `w_organization_social` scope)

## Test Credentials
- **Admin:** admin@vhc.in / VhcAdmin@2024
- **Recruiter:** bhumika@vhc.in / 12345678
