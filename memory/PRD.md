# VHC Talent OS - Product Requirements Document

## Original Problem Statement
Chrome extension to scrape candidate profiles from Naukri.com (Resdex) and save them into VHC Talent OS with AI-powered parsing, team visibility, and seamless recruitment pipeline integration.

## Extension: v3.8.1

### Architecture
Extension: DOM stability wait + scroll + View Contact click + title-based name + Naukri icon-based email selector (i.naukri-icon-email) + recruiter blocklist + cleaned text → Backend AI (OpenAI) with DOM hints + recruiter identity → Name-similarity dedup guard → Name+source priority dedup → Validated capture with team visibility → MongoDB

### v3.8.1 Changes (Feb 2026)
- **Naukri DOM email selector**: Directly targets `i.naukri-icon-email` → parent `title` attribute for email extraction (no regex guessing)
- **Name-similarity dedup guard**: Backend checks first-name match before updating email/phone-matched records. Prevents overwriting Person A when Person B has stale contacts.
- **Name+source priority dedup**: `name + source=naukri_extension` check runs as HIGH PRIORITY, preventing duplicates even with different naukri_profile_ids
- **DOM stability check**: Reads page title twice with delay, waits for SPA navigation to complete before capturing
- **SPA navigation detection**: Resets capture state when URL changes within the same tab
- **Floating progress bar**: Shows on the Naukri page for BOTH manual and auto captures (was popup-only and manual-only before)
- **Data cleanup**: Removed duplicate Natashaa records, restored Shikha's correct email
- **v3.7.0 preserved**: Backup at `/app/browser-extension/content.v3.7.0.js`

### v3.8.0 Changes (Feb 2026)
- Recruiter email/phone blocklist from chrome.storage
- Backend AI recruiter identity in prompt
- Phone storage at login in background.js
- Popup UI redesign (progress bar, no scorecard)

### Key Endpoints
- POST /api/extension/capture (name-similarity guard + name+source dedup + validation + visibility)
- POST /api/extension/ai-extract (DOM hints override + recruiter blocklist)
- GET /api/extension/profile/{id}
- GET /api/extension/stats
- GET /api/download/naukri-extension

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Recruiter: yamini@vhc.in / VhcAdmin@2024

## Known Issues (Pending)
- P2: Candidate bank search sometimes shows stale results (frontend state / Atlas Search fuzzy)
- P2: Inline candidate detail view empty for Naukri-sourced profiles
- P3: AI Screening shortlist disabled when using Paste/Upload JD (needs job mandate selection)
- P3: Mobile number extraction (v3.8.2 planned — needs "View Contact" button click + DOM selector for phone)

## Backlog
- P2: Admin cleanup tool for bad/test data in candidate bank
- P3: Refactor content.js into modules
- P3: Advanced analytics dashboard
