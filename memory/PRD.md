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

## Backlog
- P2: Admin cleanup tool for bad/test data
- P3: Mobile number extraction improvements
- P3: Refactor content.js into modules
- P3: Advanced analytics dashboard
