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
- **Admin Resources page** with Training Manual PDF download (Feb 2026)

## Recently Completed (Feb 2026)
- **Training Manual PDF Download**: Created `/admin/resources` page with downloadable PDF training manual covering Employer, Recruiter, and Trainer guides. Backend converts Markdown to styled PDF via pdfkit/wkhtmltopdf. Endpoint: `GET /api/system-health/training-manual/download`.

## Backlog / Future Tasks
- **P1: AI-driven Analytics and Insights**
- **P2: Client Dashboard Enhancements**
- **P3: Advanced Revenue Intelligence**
- **Blocked: LinkedIn Auto-Posting** (requires `w_organization_social` scope on LinkedIn Developer App)

## Key API Endpoints
- `GET /api/system-health/training-manual/download` — PDF training manual download (admin)
- `GET /api/system-health/security-validation` — Security layers PASS/FAIL
- `GET /api/system-health/security-posture` — Full security audit data
- `GET /api/system-health/live-status` — Real-time health dashboard
- `GET /api/system-health/maintenance-status` — Bot status & health score
- `POST /api/system-health/maintenance-run` — Manual maintenance trigger
- `POST /api/system-health/diagnostic-test` — Diagnostic self-test

## Key Files
- `/app/docs/TRAINING_MANUAL.md` — Source training manual
- `/app/backend/services/training_manual_service.py` — MD→PDF conversion
- `/app/backend/routes/maintenance_routes.py` — System health & training manual endpoints
- `/app/frontend/src/pages/admin/AdminResourcesPage.jsx` — Resources & Documentation page
- `/app/frontend/src/pages/admin/SecurityAuditDashboard.jsx` — Security audit UI
- `/app/frontend/src/components/layout/Sidebar.jsx` — Navigation sidebar

## Test Credentials
- **Admin:** admin@vhc.in / VhcAdmin@2024
