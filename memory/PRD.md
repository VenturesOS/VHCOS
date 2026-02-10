# VHC Talent OS - Product Requirements Document

## Original Problem Statement
Chrome extension to scrape candidate profiles from Naukri.com (Resdex) and save them into VHC Talent OS with AI-powered parsing, team visibility, and seamless recruitment pipeline integration.

## Extension: v3.7.0

### Architecture
Extension: title (name) + auto-click View Contact + profile-area scan (email/phone) + cleaned text → Backend AI (OpenAI) with DOM hints → Validated capture with team visibility → MongoDB

### v3.7.0 Changes
- **Auto-click "View Contact"**: Clicks reveal buttons before capture to expose hidden phone numbers
- **Profile-area email/phone scan**: Uses candidate name position in text to skip recruiter's header info
- **Tighter Atlas Search**: Removed summary fuzzy (was too broad), added 5x exact name + 3x fuzzy name boost
- **Inline detail view fix**: Promise.allSettled prevents crash when Naukri candidates lack audit logs
- **Cache invalidation**: Search cache cleared after every capture for immediate visibility
- **Team visibility**: All captures visible to employer + recruiters in the same team

### Key Endpoints
- POST /api/extension/capture (validation + visibility + cache invalidation)
- POST /api/extension/ai-extract (DOM hints override)
- GET /api/extension/profile/{id}
- GET /api/extension/stats
- GET /api/download/naukri-extension

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Recruiter: yamini@vhc.in / VhcAdmin@2024

## Backlog
- P2: Admin cleanup tool for bad/test data in candidate bank
- P3: Refactor content.js into modules
- P3: Advanced analytics dashboard
