# VHC Talent OS - Product Requirements Document

## Original Problem Statement
Build a Chrome extension to scrape candidate profiles from Naukri.com (Resdex) and save them into VHC Talent OS candidate bank with AI-powered parsing.

## Naukri Auto-Sourcing Browser Extension

### Current Version: v3.6.2

### Architecture
Extension captures: page title (name) + targeted DOM selectors (email/phone) + page text → Backend AI (OpenAI) with DOM hints → Structured JSON → Capture endpoint with validation → MongoDB

### v3.6.2 Fixes (Name + Email accuracy)
- **Name from document.title**: Extracts candidate name from page title (e.g., "Kalim Pathan | Naukri Resdex") — most reliable source, unaffected by DOM stripping
- **Removed body text scan (Strategy 4)**: Was picking up the logged-in recruiter's email from Naukri header/nav
- **Simplified postProcessText**: Only removes definite noise lines (nav items), no longer tries to detect "profile start" — preserves full profile text including candidate name
- **DOM hints to AI**: `dom_extracted_name`, `dom_extracted_email`, `dom_extracted_phone` passed as verified data
- **Backend override**: AI extract response is overridden with DOM values when available
- **Priority chain**: DOM name > AI name, DOM email > AI email, DOM phone > AI phone

### Key Endpoints
- POST /api/extension/capture (validation + recruiter email filter)
- POST /api/extension/ai-extract (DOM hints + strict prompt + post-override)
- GET /api/extension/profile/{id}
- GET /api/extension/stats
- GET /api/download/naukri-extension (no-cache headers)

## Tech Stack
- Frontend: React, Shadcn UI, Tailwind CSS
- Backend: FastAPI, Python, Motor (async MongoDB)
- Database: MongoDB Atlas
- AI: OpenAI GPT-4o-mini (Emergent LLM Key)
- Extension: Chrome Manifest V3

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024

## Backlog
- P1: Auto-click "View Contact" button before capture for phone number reveal
- P1: Fix inline candidate detail view for Naukri candidates
- P2: Admin tool to clean up bad data
- P3: Refactor content.js into modules
