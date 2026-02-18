# VHC Talent OS - Product Requirements Document

## Original Problem Statement
A full-stack recruitment application (React, FastAPI, MongoDB) with a public-facing static website and an internal portal for Admin, Employer, Recruiter, and Candidate roles. The platform supports AI-powered candidate matching, job management, pipeline tracking, analytics, and dual blog engines for recruitment leads and candidate engagement.

## Core Requirements
1. **Public Website** — Responsive static site (7+ pages) with contact form, careers, SEO
2. **Authentication** — JWT-based multi-role auth (Admin, Employer, Recruiter, Candidate)
3. **Job Management** — CRUD, JD parsing, career page, shareable links
4. **Candidate Management** — Candidate bank, CV parsing, profile management
5. **AI Matching** — Quick match, full AI match, AI search with natural language
6. **Pipeline** — Kanban-style application tracking with stage transitions
7. **Analytics** — Admin and employer dashboards with revenue tracking
8. **Chrome Extension** — Naukri profile scraping integration
9. **Blog Engine** — Dual AI-powered blog engines (Employer + Candidate)
10. **SEO Content Silo** — Dynamic pillar pages for authority in industrial recruitment, HR consulting, and career insights

## Architecture
- **Frontend:** React + Tailwind + Shadcn/UI (port 3000)
- **Backend:** FastAPI + Motor (async MongoDB) (port 8001)
- **Database:** MongoDB Atlas (vhc_talent_os) — UNIFIED (single source of truth)
- **Storage:** Cloudflare R2 for files
- **AI:** OpenAI GPT-4o-mini (screening, matching, blog generation)

## What's Been Implemented

### Phases 1-8 (Previous Sessions)
- Full auth system, Job CRUD, Candidate bank, AI matching, Pipeline, Analytics
- Chrome extension, Teams, Referrals, Commercials, Bug reporting
- MongoDB Atlas SSL fix, Static site responsiveness, UI/UX audit
- Contact Form, AI Screening, SEO Meta Tags, Mobile responsive fixes
- Dual Blog Engines (Employer + Candidate) with AI generation
- Blog Auto-Scheduling, Analytics Dashboard, RSS Feed
- Forgot Password Flow, Contact Form Email Notifications, Social Sharing
- SEO-Friendly Clean URLs, AI Topic Research, Weekly Blog Digest
- Production Root URL Redirect fix, Company-Employer Assignment fix
- LLM Service Refactor, SEO Phase 1 (Technical SEO Transformation)

### Phase 9: Database Consolidation (Feb 17, 2026)
- **Critical DB Split-Brain Resolution:** Successfully merged production local MongoDB data into Atlas master
- **Migration Summary:**
  - UUID Conflicts: 4 resolved (admin, ajit, jatin, siddharth) — kept production UUIDs
  - Siddharth role: overridden from employer → admin (production UUID retained)
  - Company dedup: Panosonic India + Panasonic merged into "Panasonic India"
  - 9 orphaned Atlas applications cleaned
  - 56 production-only candidates migrated
  - 30 production-only applications migrated
  - 4 production-only real users added (rohit, manorma, 2 candidates)
  - 2 real companies added (TVS, Panasonic India)
  - 1 commercial added (TVS)
  - Test artifacts excluded (8 companies, 10+ jobs, 3 test users)
- **Post-Merge Validation:** ALL PASS
- **Backup:** Full Atlas snapshot at `/app/backup/atlas_pre_merge_20260218/`

### Phase 10: SEO Phase 2 — Content Silo Architecture (Feb 17, 2026)
- **Backend:** `pillar_pages` collection with admin CRUD + public GET API
  - Routes: `/api/admin/pillar-pages` (CRUD) + `/api/pillar-pages/{slug}` (public read)
  - Unique index on slug, constrained to 3 allowed values
  - Models: `PillarPageCreate`, `PillarPageUpdate` with hero, content, faq, status fields
- **Frontend:** Dynamic pillar page rendering
  - `PillarPage.jsx` with `PillarHero`, `PillarContent`, `PillarSidebar` components
  - `useSEOMeta` hook for reliable DOM-based meta tag injection (title, description, canonical, OG tags)
  - DOMPurify HTML sanitization, mobile-first responsive layout
  - FAQ accordion section, two CTAs per page, sticky sidebar with internal links
- **Content:** 3 pillar pages seeded with 1500+ words each
  - `/industrial-recruitment` — 1506 words, 5 FAQs
  - `/hr-consulting-services` — 1518 words, 5 FAQs
  - `/career-insights` — 1613 words, 5 FAQs (replaces old blog list at this URL)
- **SEO:** Sitemap & robots.txt updated with pillar page paths
- **Testing:** 18/18 backend tests passed, frontend verified across all 3 pages

## Key Files
- `backend/routes/pillar_pages.py` — Pillar pages CRUD + public API
- `backend/models/pillar_page.py` — Pydantic models
- `backend/scripts/seed_pillar_pages.py` — Content seeding script
- `frontend/src/pages/public/PillarPage.jsx` — Main pillar page component
- `frontend/src/components/PillarPage/` — Hero, Content, Sidebar sub-components
- `frontend/src/hooks/useSEOMeta.js` — DOM-based SEO meta tag injection hook
- `backend/config.py` — Database connection with Atlas override

### Phase 11: Blog Digest Email Distribution (Feb 17, 2026)
- **Backend:** `digest_email_service.py` — Recipient segmentation, HMAC-based unsubscribe tokens, mobile-responsive HTML email template with personalized greeting, pillar page references, and CTA
- **Routes:** Extended `blog_digest.py` with 8 endpoints:
  - `POST /api/admin/blog-digest/send` — Send to segments with duplicate prevention
  - `GET /api/admin/blog-digest/preview` — Preview email HTML
  - `GET /api/admin/blog-digest/recipients` — Preview recipient list
  - `GET /api/admin/blog-digest/send-logs` — Send history
  - `GET /api/admin/blog-digest/subscription-stats` — Unsubscribe stats
  - `GET /api/unsubscribe/{token}` — Public unsubscribe (HTML page)
  - `GET /api/resubscribe/{token}` — Public resubscribe (HTML page)
- **Frontend:** `DigestEmailPage.jsx` — Admin dashboard for digest distribution
  - Stats cards, digest selector, segment toggles, email preview iframe, recipient preview, send history table
- **DB Collections:** `email_subscriptions`, `digest_send_logs`
- **Testing:** 18/18 backend tests passed, frontend 100% verified

### Phase 12: Company + Commercials Merge (Feb 18, 2026)
- **Schema change:** Commercials embedded as subdocument in company (no longer a separate collection)
- **Commercial types:** `percentage` (flat %), `fixed` (fixed fee), `level_based` (salary range array)
- **HR Contacts:** Array of `{name, email, phone, designation}` — multiple per company
- **Migration:** 5 existing commercials migrated into company docs. 2 level_based preserved with `legacy_level_mapping`. Old `commercials` collection kept as backup
- **Validation:** Overlapping ranges, min<max, percentage>0, commercial required at creation
- **Revenue calc:** `calculate_revenue()` and `get_applicable_commercial()` refactored to read from `company.commercial`
- **5 server.py references updated:** employer my-team, employer companies, employer analytics, admin company pipeline, admin analytics
- **Frontend:** Unified create/edit form with 3 sections (Company Info, HR Contacts, Commercial Model)
- **Sidebar:** "Commercials" menu item removed. Commercials exist ONLY within Company
- **Testing:** 19/19 backend tests passed, all frontend verified. Zero regressions

### Phase 13: Revenue Engine (Feb 18, 2026)
- **Central Engine:** `services/revenue_engine.py` — Single `calculate_revenue()` returning structured `{salary, commercial_type, slab_applied, percentage_used, revenue_amount}`. Strict errors via `RevenueCalculationError` (no silent fallback to 0)
- **Revenue Routes:** `routes/revenue.py` — 8 endpoints:
  - `POST /api/revenue/forecast` — Pipeline forecast (stored on application, NOT in revenue collection)
  - `POST /api/revenue/offered/{app_id}` — Creates revenue record with commercial snapshot + slab shift detection
  - `POST /api/revenue/joined/{app_id}` — Locks revenue (immutable after joined)
  - `GET /api/revenue/aggregate/by-company` — Date-filtered aggregation
  - `GET /api/revenue/aggregate/by-job` — Date-filtered aggregation
  - `GET /api/revenue/aggregate/by-recruiter` — Date-filtered aggregation with name enrichment
  - `GET /api/revenue/records` — Role-filtered revenue list
  - `GET /api/revenue/by-application/{app_id}` — Single revenue lookup
- **Stage Enforcement:** Applications route enforces: no offered without offered_ctc, no joined without offered_ctc, locked after joined
- **Role-Based Visibility:** Recruiter NEVER sees revenue fields (stripped at API layer)
- **DB Indexes:** 7 indexes on revenue collection (company_id, job_id, recruiter_id, join_date, revenue_status, compound, application_id unique)
- **Testing:** 41/41 tests (19 API + 22 unit). Zero regressions on employer/analytics endpoints

## Prioritized Backlog

### P0 — ALL COMPLETE
- ~~Database Consolidation~~ **DONE**
- ~~Production Unification~~ **DONE**
- ~~SEO Phase 2: Content Silo Architecture~~ **DONE**
- ~~SEO Phases 3-5~~ **DONE** (JSON-LD, Internal Linking, SEO Dashboard)
- ~~Weekly Blog Digest Generation~~ **DONE** (APScheduler)
- ~~Blog Digest Email Distribution~~ **DONE** (Resend integration)
- ~~Company + Commercials Merge~~ **DONE** (Unified workflow)
- ~~Revenue Engine~~ **DONE** (Dual-layer: forecast + financial)

### P1
- Revenue Engine Frontend (admin dashboard for revenue visualization, offered/joined stage UI in pipeline)
- Refactor employer routes (`server.py` → `employer_routes.py`) — ON HOLD per user (stability first)

### P2
- Refactor Chrome extension content.js
- AI Search Phase 2 (hybrid routing, configurable models)

## Test Credentials
- Admin: `admin@vhc.in` / `VhcAdmin@2024`
- Employer: `ajit@vhc.in` / `12345678`
- Recruiter: `jatin@vhc.in` / `12345678`
- Admin (alt): `siddharth@vhc.in` / `12345678`
