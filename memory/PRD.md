# VHC Talent OS - Product Requirements Document

## Original Problem Statement
Chrome extension to scrape candidate profiles from Naukri.com (Resdex) and save them into VHC Talent OS with AI-powered parsing, team visibility, and seamless integration with the recruitment pipeline.

## Naukri Auto-Sourcing Browser Extension: v3.6.2

### Architecture
Extension: page title (name) + targeted DOM selectors (email/phone) + cleaned page text → Backend AI (OpenAI) with DOM hints → Structured JSON → Capture endpoint with validation + team visibility → MongoDB

### Key Fixes in v3.6.2
- **Name from document.title** — most reliable source
- **Removed body text scan** — was picking up recruiter's email
- **Recruiter email filter** — strips logged-in user's email from captures
- **Team visibility** — captured profiles visible to all team members (employer + recruiters)
- **JS syntax fix** — duplicate code block causing content script crash
- **Shortlisting in all modes** — job picker added for paste JD / upload JD flows

### Key Endpoints
- POST /api/extension/capture (validation + visibility + email filter)
- POST /api/extension/ai-extract (DOM hints override)
- GET /api/extension/profile/{id}
- GET /api/extension/stats
- GET /api/download/naukri-extension

## Tech Stack
- Frontend: React, Shadcn UI, Tailwind CSS, Axios
- Backend: FastAPI, Python, Motor (async MongoDB)
- Database: MongoDB Atlas
- AI: OpenAI GPT-4o-mini (Emergent LLM Key)
- Extension: Chrome Manifest V3

## Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Recruiter: yamini@vhc.in / VhcAdmin@2024

## Backlog
- P1: Auto-click "View Contact" button for phone number reveal
- P1: Fix inline candidate detail view for Naukri candidates
- P2: Admin cleanup tool for bad data
- P3: Refactor content.js into modules
