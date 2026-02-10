# VHC Talent OS - Product Requirements Document

## Original Problem Statement
Chrome extension to scrape candidate profiles from Naukri.com (Resdex) and save them into VHC Talent OS with AI-powered parsing, team visibility, and seamless recruitment pipeline integration.

## Extension: v3.8.0

### Architecture
Extension: title (name) + auto-click View Contact + recruiter blocklist (email+phone from chrome.storage) + profile-area scan (email/phone) + cleaned text → Backend AI (OpenAI) with DOM hints + recruiter identity → Validated capture with team visibility → MongoDB

### v3.8.0 Changes (Feb 2026)
- **Recruiter blocklist**: Loads recruiter's email+phone from chrome.storage, excludes them during DOM contact extraction
- **Backend AI recruiter identity**: AI prompt explicitly receives recruiter's email/phone and instructions to ignore them
- **Phone storage at login**: background.js now stores recruiter's phone from login response for blocklist use
- **v3.7.0 preserved**: Backup at `/app/browser-extension/content.v3.7.0.js` for rollback

### v3.7.0 Changes (Previous)
- **Auto-click "View Contact"**: Clicks reveal buttons before capture to expose hidden phone numbers
- **Profile-area email/phone scan**: Uses candidate name position in text to skip recruiter's header info
- **Tighter Atlas Search**: Removed summary fuzzy (was too broad), added 5x exact name + 3x fuzzy name boost
- **Inline detail view fix**: Promise.allSettled prevents crash when Naukri candidates lack audit logs
- **Cache invalidation**: Search cache cleared after every capture for immediate visibility
- **Team visibility**: All captures visible to employer + recruiters in the same team

### Key Endpoints
- POST /api/extension/capture (validation + visibility + cache invalidation)
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

## Backlog
- P2: Admin cleanup tool for bad/test data in candidate bank
- P3: Refactor content.js into modules
- P3: Advanced analytics dashboard
