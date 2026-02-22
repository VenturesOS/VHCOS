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

## User Roles
- **Admin**: Full portal control, system health, security audit, compliance, blog, SEO, resources
- **Employer**: Job posting, pipeline tracking, analytics, candidate bank, team management
- **Recruiter**: Mandate management, pipeline, referrals, AI screening, candidate bank
- **Candidate**: Profile, job browsing, applications, messages, alerts

## Implemented Features (Complete)
- Multi-role auth (JWT) with admin seeding
- 7-stage recruitment pipeline with drag-and-drop
- Client submission tracker
- Admin analytics & revenue dashboard
- Candidate data bank with batch upload, bulk import, AI matching
- Blog engine with auto-publish scheduler
- SEO monitoring & pillar pages
- Digest email service
- LinkedIn integration (limited by app permissions)
- System health monitoring with maintenance bot
- Security hardening: Turnstile CAPTCHA, Zero Trust, rate limiting, file validation, XSS prevention
- Security audit dashboard with posture scoring
- Compliance dashboard (GDPR/data governance)
- Cookie consent banner
- Contact submissions management
- Bug reports system
- Admin Resources page with Training Manual PDF download (Feb 2026)

## Recently Completed (Feb 22, 2026) — Production Stability Hardening
1. **Email Normalization**: All user creation, login, and lookup flows now apply `.lower().strip()` to emails. Existing emails in DB were normalized at startup. Prevents case-sensitivity mismatches.
2. **Environment Badge**: Amber banner "PREVIEW MODE — DATA MAY NOT MATCH LIVE" shown on admin/recruiter/employer dashboards when env != production. Uses `/api/system-health/env-info`.
3. **Startup Environment Logging**: Logs ENV, DB, MONGO_CLUSTER, IS_PRODUCTION at boot once.
4. **User Creation Safety Logging**: Logs env, db, user_id, email, role when users are created.
5. **Centralized Environment Resolver**: `utils/environment.py` — single source of truth for ENV_NAME, IS_PRODUCTION, IS_PREVIEW, normalize_email(), get_environment_info().

## Key Files — Environment Hardening
- `/app/backend/utils/environment.py` — Centralized environment resolver
- `/app/backend/routes/auth.py` — Email normalization on register/login/forgot-password
- `/app/backend/routes/admin.py` — Email normalization on admin user creation
- `/app/backend/server.py` — Startup env logging + email normalization migration
- `/app/frontend/src/components/shared/EnvironmentBadge.jsx` — Preview banner
- `/app/frontend/src/components/layout/DashboardLayout.jsx` — Badge integration

## Backlog / Future Tasks
- **P1: AI-driven Analytics and Insights**
- **P2: Client Dashboard Enhancements**
- **P3: Advanced Revenue Intelligence**
- **Blocked: LinkedIn Auto-Posting** (requires `w_organization_social` scope)

## Key API Endpoints
- `GET /api/system-health/env-info` — Environment metadata for frontend badge
- `GET /api/system-health/training-manual/download` — PDF training manual download
- `GET /api/system-health/security-validation` — Security layers PASS/FAIL
- `GET /api/system-health/security-posture` — Full security audit data

## Test Credentials
- **Admin:** admin@vhc.in / VhcAdmin@2024
- **Recruiter:** bhumika@vhc.in / 12345678
