# VHC Talent OS - Product Requirements Document

## Original Problem Statement
Chrome extension to scrape candidate profiles from Naukri.com (Resdex) and save them into VHC Talent OS with AI-powered parsing, team visibility, and seamless recruitment pipeline integration.

## Extension: v3.8.2 (SEALED - Production)

### Architecture
```
1. DOM stability wait (title check x2)
2. Scroll page (load CV iframe + lazy content)
3. Name from page title
4. SNAPSHOT all emails/phones on page (= baseline)
5. Click "View Contact" (exact text match only)
6. SNAPSHOT again → DIFF = candidate's newly revealed contacts
7. Scan CV iframe (id="cv-iframe") → deep extraction: email, phone, sections, LinkedIn
8. Naukri DOM selectors (i.naukri-icon-email) → fallback
9. MERGE with trust hierarchy: CV > Diff > Already-visible (filtered) > DOM > AI
10. Send merged contacts + CV text (primary) + page text to AI (GPT-4o-mini)
11. Backend: name-similarity dedup guard + name+source priority dedup
12. Backend: @vhc.in + recruiter email blocklist
13. Save with email on BOTH create and update paths
```

### Trust Hierarchy
`CV iframe` > `Before/After Diff` > `Already-visible (BEFORE filtered)` > `DOM selectors` > `AI extraction`

### Blocklist
- @vhc.in (company domain)
- @naukri.com, support@, noreply@, @example.com (system)
- Logged-in recruiter's exact email and phone

### Key Fixes in v3.8.2
- Multi-source cross-validation pipeline (CV iframe + Before/After diff + DOM selectors)
- Deep CV section extraction (experience, education, skills, certifications, achievements, LinkedIn)
- "View Contact" exact text match (no more clicking "Similar profiles")
- Already-visible email fallback (handles non-hidden contacts)
- @vhc.in blocklist at extension + backend
- Email field added to build_complete_update (was missing — root cause of "Hidden on Naukri")
- Name-similarity dedup guard (prevents cross-contamination between candidates)
- Name+source priority dedup (prevents duplicates)
- Floating progress bar for both manual and auto captures
- SPA navigation detection + DOM stability wait

### Key Endpoints
- POST /api/extension/capture
- POST /api/extension/ai-extract
- GET /api/download/naukri-extension

### Backed Up Versions
- v3.7.0: /app/browser-extension/content.v3.7.0.js
- v3.8.1: /app/browser-extension/content.v3.8.1.js

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Recruiter: yamini@vhc.in / VhcAdmin@2024

## Known Issues (Pending)
- P2: Candidate bank search sometimes shows stale results
- P2: Inline candidate detail view empty for Naukri-sourced profiles
- P3: AI Screening shortlist disabled when using Paste/Upload JD

## Advanced Analytics Dashboard (COMPLETED — Feb 11, 2026)
### Backend
- `GET /api/analytics/admin` — admin-only endpoint with full analytics data
- Filters: `employer_id`, `team_id`, `recruiter_id`, `date_from`, `date_to`
- MongoDB aggregation pipelines for KPIs, source distribution, capture trends, recruiter performance, stage distribution, funnel velocity
- Filter cascading: employer → teams → recruiters
- Files: `/app/backend/services/analytics_service.py`, `/app/backend/routes/analytics.py`

### Frontend
- Recharts: LineChart (capture trends), PieChart (source effectiveness), BarChart (recruiter performance)
- KPI scorecards: Total Captures, Today/Week/Month, Avg Daily Rate, Active Sources
- Funnel velocity card: Avg days to Shortlisted/Interview/Offered/Hired
- Stage distribution: Horizontal bar breakdown
- Recruiter details table
- Cascading filter dropdowns (Employer → Team → Recruiter) + date range
- File: `/app/frontend/src/pages/admin/AdminAnalyticsPage.jsx`

### Testing
- 15/15 backend tests passed, all frontend components verified
- Test file: `/app/backend/tests/test_admin_analytics.py`

### PDF Export (Added Feb 11, 2026)
- `GET /api/analytics/admin/export-pdf` — generates downloadable PDF with same filter params
- Uses ReportLab: KPI table, source effectiveness table, recruiter performance (top 15), funnel velocity, stage distribution, capture trends
- Frontend: "Export PDF" button in dashboard header, respects active filters
- Files: `/app/backend/services/analytics_pdf.py`, `/app/backend/routes/analytics.py`

## Backlog
- P2: Admin cleanup tool for bad/test data
- P2: Mobile number extraction without "View Contact" click
- P3: AI Screening Shortlist fix
- P3: Refactor content.js into modules
