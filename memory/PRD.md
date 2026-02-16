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

### Phase 5 (Feb 15, 2026)
- **Blog Auto-Scheduling** — APScheduler-based background jobs
  - Employer: 3/week (Mon, Wed, Fri at 9:00 AM IST)
  - Candidate: 2/week (Tue, Thu at 10:00 AM IST)
  - Admin can enable/disable per blog type via toggle switches
  - Manual "Publish Now" trigger from admin panel
  - Auto-publish logs tracked in `blog_schedule_log` collection
  - Draft queue counter shows available drafts
- **Blog Analytics Dashboard** at `/admin/blog-analytics`
  - KPI cards: Published count, Total Views, CTA Clicks, CTR, Draft Queue
  - Daily page views line chart (recharts)
  - Top blogs by views and CTA clicks (horizontal bar charts)
  - Blog performance table with type badges
  - Period selector (7/30/90 days)
  - Public tracking: POST /api/blog/track for views and CTA clicks
  - Auto-tracking on blog article page load
- **RSS Feed Generation** at `/api/blog/rss`
  - Valid RSS 2.0 XML with Atom namespace
  - Filterable by blog_type (employer/candidate)
  - Returns up to 50 most recent published blogs
  - Links directly accessible from admin dashboard

### Phase 6 (Feb 15, 2026)
- **Forgot Password Flow** — Full email-based password reset
  - POST /api/auth/forgot-password sends reset email via Resend
  - Token-based reset with 1-hour expiry (password_reset_tokens collection)
  - Prevents email enumeration (same response for existing/non-existing)
  - Frontend at /forgot-password with request + reset forms
  - "Forgot password?" link on Login page
  - Sender email: noreply@ventureshrd.com
- **Contact Form Email Notifications** — Admin email alerts
  - New contact submissions trigger email to admin via Resend
  - HTML-formatted email with full submission details
- **Blog Social Sharing** — Share buttons on all blog articles
  - LinkedIn, X (Twitter), WhatsApp share buttons
  - Properly encoded URLs and titles
  - Added to both employer and candidate blog article pages

### Phase 7 (Feb 15, 2026)
- **SEO-Friendly Clean URLs** — All website pages use clean paths
  - Removed /website/ prefix and .html extensions from all URLs
  - craco devServer middleware rewrites: /, /about, /services, /industries, /careers, /contact, /global-hiring, /sitemap
  - Blog routes: /industrial-hiring-insights, /career-insights (no /website/ prefix)
  - Updated all internal navigation links across 8 static HTML pages
  - Asset paths made absolute: /website/style.css, /website/mobile-menu.js
- **AI Topic & Keyword Research** — OpenAI-powered blog research
  - POST /api/blog/research-topics generates trending topic suggestions with SEO keywords
  - Integrated into Blog Engine generate dialog with "Research Topics" button
  - Clicking a suggestion auto-fills topic, keywords, and region
- **Blog Sitemap.xml** — Dynamic XML sitemap at /api/blog/sitemap.xml
  - Includes all static pages with clean URLs and priorities
  - Includes all published blog posts with lastmod dates
- **Weekly Blog Digest Email** — Candidate engagement emails
  - POST /api/blog/send-digest sends digest to all registered candidates
  - Includes blogs published in last 7 days with links
  - Admin trigger from Blog Analytics dashboard

### Phase 8 (Feb 2026)
- **P0 Fix: Production Root URL Redirect** — Made `PublicWebsiteRedirect` bulletproof with 3-layer fallback:
  1. JS `window.location.replace('/website/Index.html')`
  2. `<meta http-equiv="refresh">` HTML-level redirect
  3. Visible "Click here" link after 2s timeout
  - Requires user to **redeploy** to production for fix to take effect
- **P2: LLM Service Refactor** — Centralized all OpenAI API calls into `services/llm_service.py`
  - Single `chat_completion()` function with configurable model, temperature, max_tokens, json_mode
  - `get_model()` and `get_api_key()` helpers for consistent config
  - Updated 5 files: `blog_generator.py`, `ai_search.py`, `extension.py`, `cv_upload.py`, `blog.py`
  - Model now configurable via `LLM_DEFAULT_MODEL` env var (defaults to gpt-4o-mini)

## Prioritized Backlog

### P1
- Automate Weekly Blog Digest (APScheduler recurring job, currently manual button)

### P2
- Refactor Chrome extension `content.js`
- AI Search Phase 2 (hybrid routing, configurable models)

### P3
- Refactor FindCandidatesPage.jsx

## Key Files
- `/app/backend/server.py` — Main FastAPI app (includes APScheduler startup)
- `/app/backend/services/blog_generator.py` — LLM abstraction for blog content
- `/app/backend/services/blog_scheduler.py` — Auto-scheduling logic
- `/app/backend/services/blog_analytics.py` — Analytics tracking & aggregation
- `/app/backend/routes/blog.py` — Blog CRUD + public + RSS + analytics + schedule endpoints
- `/app/backend/routes/contact.py` — Contact form endpoints
- `/app/frontend/src/pages/admin/BlogEnginePage.jsx` — Admin blog management
- `/app/frontend/src/pages/admin/BlogAnalyticsPage.jsx` — Admin analytics dashboard
- `/app/frontend/src/pages/public/BlogPages.jsx` — Public blog pages (with view tracking)
- `/app/frontend/src/lib/api.js` — API client with blogAPI module

## Test Credentials
- Admin: `admin@vhc.in` / `VhcAdmin@2024`
- Employer: `ajit@vhc.in` / `12345678`
- Recruiter: `jatin@vhc.in` / `12345678`
