# VHC Talent OS - Product Requirements Document

## Original Problem Statement
A full-stack recruitment application (React, FastAPI, MongoDB) with a public-facing static website and an internal portal for Admin, Employer, Recruiter, and Candidate roles. The platform supports AI-powered candidate matching, job management, pipeline tracking, analytics, and now dual blog engines for recruitment leads and candidate engagement.

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
- **Database:** MongoDB Atlas (vhc_talent_os)
- **Storage:** Cloudflare R2 for files
- **AI:** OpenAI GPT-4o-mini (screening, matching, blog generation)

## What's Been Implemented

### Phase 1 (Previous Sessions)
- Full auth system, Job CRUD, Candidate bank, AI matching, Pipeline, Analytics
- Chrome extension, Teams, Referrals, Commercials, Bug reporting

### Phase 2 (Previous Fork)
- MongoDB Atlas SSL fix, Static site responsiveness, UI/UX audit, Micro-animations
- AI Screening shortlist bug fix

### Phase 3 (Feb 15, 2026)
- Contact Form Backend with admin dashboard
- AI Screening "View Full Profile" and "Add as Applicant" actions
- SEO Meta Tags audit across all static pages
- Mobile responsive fix for About page leadership cards

### Phase 4 (Feb 15, 2026 - Current)
- **Employer Blog Engine** — AI-generated 1500-2000 word recruitment articles
  - Public listing at `/website/industrial-hiring-insights`
  - Single article pages with SEO meta tags and Article schema markup
  - India/Global region tagging, recruitment-focused CTAs
  - Footer-only link (not in header nav), SEO indexable
- **Candidate Blog Engine** — AI-generated 1200-1800 word career advice articles
  - Public listing at `/website/career-insights` with category filters
  - Soft CTAs for profile creation/resume upload
  - Linked from "Career Insights & Advice" section on homepage
- **Admin Blog Management Panel** at `/admin/blog-engine`
  - One-click AI generation with topic/industry/keywords/region/category inputs
  - Full content editor with metadata editing
  - Preview mode, publish/unpublish workflow
  - Generation logging (topic, keywords, model, region, type)
- **LLM Service Layer** — Abstracted blog_generator.py with configurable model
  - Currently uses GPT-4o-mini, upgradeable via env vars
  - Controlled temperature for consistent SEO structure

## Blog Engine Schema
```json
{
  "id": "uuid",
  "title": "string",
  "slug": "string",
  "meta_description": "string",
  "content": "HTML string",
  "blog_type": "employer|candidate",
  "region": "india|global (employer only)",
  "category": "career-growth|job-switching|... (candidate only)",
  "industry": "string",
  "keywords": ["array"],
  "internal_links": ["array"],
  "cta_type": "string",
  "word_count_estimate": "number",
  "status": "draft|published",
  "generation_log": { "topic_source", "model_used", "generated_at", ... },
  "created_at": "ISO datetime",
  "published_at": "ISO datetime"
}
```

## Prioritized Backlog

### P1
- Forgot Password flow
- Blog auto-scheduling (3/week employer, 2-3/week candidate)

### P2
- Refactor Chrome extension `content.js`
- AI Search Phase 2 (hybrid routing, configurable models)
- Blog analytics dashboard
- RSS feed generation for blogs

### P3
- Email notifications for contact form
- Social sharing for blog articles
- Refactor FindCandidatesPage.jsx

## Key Files
- `/app/backend/server.py` — Main FastAPI app
- `/app/backend/services/blog_generator.py` — LLM abstraction for blog content
- `/app/backend/routes/blog.py` — Blog CRUD + public endpoints
- `/app/backend/routes/contact.py` — Contact form endpoints
- `/app/frontend/src/pages/admin/BlogEnginePage.jsx` — Admin blog management
- `/app/frontend/src/pages/public/BlogPages.jsx` — Public blog pages
- `/app/frontend/src/lib/api.js` — API client with blogAPI module

## Test Credentials
- Admin: `admin@vhc.in` / `VhcAdmin@2024`
- Employer: `ajit@vhc.in` / `12345678`
- Recruiter: `jatin@vhc.in` / `12345678`
