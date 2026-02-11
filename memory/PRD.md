# VHC Talent OS - Product Requirements Document

## Original Problem Statement
Chrome extension to scrape candidate profiles from Naukri.com (Resdex) and save them into VHC Talent OS with AI-powered parsing, team visibility, and seamless recruitment pipeline integration.

## Extension: v3.8.2 — Multi-Source Cross-Validation Pipeline

### Architecture
```
1. DOM stability wait (title check x2)
2. Scroll page (load CV iframe + lazy content)
3. Name from page title
4. SNAPSHOT all emails/phones on page (= baseline/recruiter)
5. Click "View Contact"
6. SNAPSHOT again → DIFF = candidate's contacts (NEW items only)
7. Scan CV iframe (id="cv-iframe") → email, phone, text
8. Naukri DOM selectors (i.naukri-icon-email) → fallback
9. MERGE: CV > Diff > DOM selectors (trust hierarchy)
10. Send merged contacts + page text + CV text to AI
11. AI structured extraction (GPT-4o-mini)
12. Final: merged DOM contacts override AI contacts → Capture
```

### Trust Hierarchy
`CV iframe` > `Before/After Diff` > `DOM selectors` > `AI extraction`

### v3.8.2 Changes (Feb 2026)
- **Before/After Click Diff**: Snapshots all contacts before & after "View Contact" click; NEW ones = candidate's (deterministic, no guessing)
- **CV iframe scan**: Reads iframe#cv-iframe content for email/phone (candidate's resume, zero recruiter contamination)
- **CV sanity check**: Verifies CV contains candidate name; ignores bad uploads (medical reports etc.)
- **Combined AI input**: Sends page text + CV text to AI for richer extraction
- **Removed old extractContactFromDOM**: Replaced by multi-source pipeline
- **v3.8.1 backed up**: `/app/browser-extension/content.v3.8.1.js`

### Previous Versions
- v3.8.1: DOM selectors (i.naukri-icon-email), name-similarity dedup, progress bar
- v3.8.0: Recruiter blocklist, phone storage at login, popup redesign
- v3.7.0: Team visibility, Atlas Search improvements, View Contact auto-click
- v3.6.x: AI extraction, noise removal, title-based name extraction

### Key Endpoints
- POST /api/extension/capture (name-similarity guard + name+source dedup + validation)
- POST /api/extension/ai-extract (DOM hints + recruiter blocklist + CV text support)
- GET /api/download/naukri-extension

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Recruiter: yamini@vhc.in / VhcAdmin@2024

## Known Issues (Pending)
- P2: Candidate bank search sometimes shows stale results
- P2: Inline candidate detail view empty for Naukri-sourced profiles
- P3: AI Screening shortlist disabled when using Paste/Upload JD

## Backlog
- P2: Admin cleanup tool for bad/test data
- P3: Refactor content.js into modules
- P3: Advanced analytics dashboard
