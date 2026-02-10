# VHC Talent OS - Product Requirements Document

## Original Problem Statement
Build a Chrome extension to scrape candidate profiles from Naukri.com (Resdex) and save them into VHC Talent OS candidate bank with AI-powered parsing.

## Naukri Auto-Sourcing Browser Extension

### Current Version: v3.6.1

### Architecture
- Extension captures page text + DOM-extracted contacts → Backend AI (OpenAI) → Structured JSON → Capture endpoint → MongoDB
- Direct API calls from content.js (bypasses Manifest V3 service worker)

### v3.6.1 Changes (Email Fix)
- **DOM Contact Extraction**: 4-strategy email extraction directly from DOM before AI:
  1. `mailto:` links
  2. Contact-area CSS selectors (20+ patterns)
  3. Sibling elements near "Call candidate" buttons
  4. Body text regex scan (top 3000 chars)
- **DOM hints to AI**: `dom_extracted_email` and `dom_extracted_phone` passed to AI endpoint as verified contacts
- **Recruiter email filter**: Capture endpoint compares email against logged-in user's email and strips if match
- **Capture payload priority**: DOM-extracted email > AI-extracted email

### v3.6.0 Changes (Data Quality)
- Multi-strategy text extraction (container selectors, aggressive DOM strip, text post-processing)
- Strict AI prompt (no years in name, reject nav/marketing text)
- Backend validation (reject invalid names, clean appended years, strip placeholder emails)

### Key Endpoints
- POST /api/extension/capture (validation + recruiter email filter)
- POST /api/extension/ai-extract (DOM hints + strict prompt)
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
- P1: Auto-click "View Contact" button before capture for phone reveal
- P1: Fix inline candidate detail view for Naukri candidates
- P2: Admin tool to clean up bad data
- P3: Refactor content.js into modules
