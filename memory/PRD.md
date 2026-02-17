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
  - Login tests: 5/5 pass (admin, employer, recruiter)
  - Relationship integrity: 5/5 checks pass (0 broken references)
  - Count verification: 7/7 collections match expected
  - API verification: Companies, Jobs, Teams, Applications all functional
- **Backup:** Full Atlas snapshot at `/app/backup/atlas_pre_merge_20260218/`
- **Rollback:** `mongorestore --drop --dir='/app/backup/atlas_pre_merge_20260218/vhc_talent_os'` (< 5 min)

## Current Database State (Post-Merge)
| Collection | Count |
|---|---|
| users | 14 |
| companies | 7 |
| teams | 4 |
| jobs | 6 |
| applications | 43 |
| candidate_bank | 1,719 |
| commercials | 6 |
| blog_posts | 2 |

## Prioritized Backlog

### P0 — ALL COMPLETE
- ~~Database Consolidation:~~ **DONE** (Feb 18, 2026) — Merged local DB into Atlas
- ~~Production Unification:~~ **DONE** (Feb 18, 2026) — Production now writes exclusively to Atlas
  - Root cause: Platform injected `MONGO_URL=localhost`, fixed with targeted `dotenv_values()` override in `config.py`
  - Code bug: Empty `update_many({})` crash in `admin.py:232` removed
  - All counts verified on production: 14 users, 7 companies, 1719 candidates, 4 teams, 43 applications
  - Write isolation confirmed: Atlas=YES, localhost=NO
- ~~SEO Phase 2: Content Silo Architecture~~ **DONE** (Feb 17, 2026)
  - Backend: `pillar_pages` collection with admin CRUD + public GET API. Unique index on slug.
  - Frontend: Dynamic rendering with `useSEOMeta` hook (title, description, canonical, OG tags), DOMPurify HTML sanitization, mobile-first responsive layout, two-column content+sidebar grid.
  - Content: 3 pillar pages seeded (1500+ words each, FAQ sections, internal linking placeholders, 2 CTAs per page)
    - `/industrial-recruitment` — 1506 words
    - `/hr-consulting-services` — 1518 words
    - `/career-insights` — 1613 words
  - SEO: Sitemap & robots.txt updated. Each page has unique H1, proper H2→H3 hierarchy, canonical URL, OG meta tags.

### P1
- **SEO Phase 2:** Pillar Pages + FAQ Schema + Content Silo Architecture
  - Create 3 pillar pages: /industrial-recruitment/, /hr-consulting-services/, /career-insights/
  - AI-optimized FAQ pages with JSON-LD schema for LLM visibility
  - Internal linking engine between blogs, pillars, and services
- Automate Weekly Blog Digest (APScheduler recurring job)

### P2
- SEO Phase 3-5: LLM visibility strategy, internal linking engine, SEO monitoring dashboard
- Refactor employer routes into dedicated file

### P3
- Refactor Chrome extension content.js
- AI Search Phase 2 (hybrid routing, configurable models)

## Test Credentials
- Admin: `admin@vhc.in` / `VhcAdmin@2024`
- Employer: `ajit@vhc.in` / `12345678`
- Recruiter: `jatin@vhc.in` / `12345678`
- Admin (alt): `siddharth@vhc.in` / `12345678`

## Key Files
- `/app/backend/server.py` — Main FastAPI app
- `/app/backend/routes/admin.py` — Admin routes (employer/team fixes)
- `/app/backend/routes/seo.py` — SEO infrastructure
- `/app/backend/services/llm_service.py` — Centralized LLM service
- `/app/backend/migration_execute.py` — Database merge script (executed)
- `/app/backend/migration_dry_run.py` — Dry-run simulation script
- `/app/memory/MIGRATION_PREVIEW_REPORT.md` — Full migration analysis
- `/app/memory/MIGRATION_EXECUTION_LOG.md` — Execution log
- `/app/backup/atlas_pre_merge_20260218/` — Atlas backup (pre-merge)
- `/app/backup/production_snapshot_20260218/` — Production data snapshot
