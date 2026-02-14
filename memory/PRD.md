# Ventures HRD - Product Requirements Document

## Original Problem Statement
Build a recruitment operating system (formerly VHC Talent OS) with:
- React frontend + FastAPI backend + MongoDB database
- Chrome Extension for capturing Naukri profiles
- Advanced Analytics Dashboard with PDF export
- AI-powered candidate screening
- Multi-role access (Admin, Employer, Recruiter, Candidate)
- Production deployment on custom domain

## Production Domain
- **Domain:** ventureshrd.com
- **Deployment:** Emergent Platform
- **Extension:** v3.9.1 (Ventures HRD branded)

## Current Architecture
```
/app
├── backend/
│   ├── server.py
│   ├── routes/
│   │   ├── auth.py
│   │   ├── admin.py
│   │   ├── analytics.py
│   │   ├── applications.py
│   │   ├── candidates.py
│   │   ├── extension.py
│   │   ├── profile.py
│   │   ├── cv_upload.py         # NEW: CV Upload → AI Parse
│   │   └── files.py
│   └── config.py
├── frontend/src/
│   ├── components/dialogs/
│   │   └── CVUploadDialog.jsx   # NEW: CV Upload dialog
│   ├── lib/api.js
│   └── pages/
└── browser-extension/           # v3.9.0
```

## What's Been Implemented

### Session: Feb 12-13, 2026
1. Domain Migration (portal.vhc.in → ventureshrd.com)
2. Branding Update ("VHC Talent OS" → "Ventures HRD")
3. Favicon/Tab Logo updated to VHC logo
4. CORS Fix — relative API URLs
5. CORS Hardcoded origins in server.py
6. Admin role in Create User dropdown
7. Extension v3.8.5 — CORS-free via background.js proxy
8. Candidate Profile/Messages routes
9. **CRITICAL: Candidate Overwrite Bug Fix** — naukri_profile_id=None query matching all records
10. Extension ZIP auto-rebuild on download
11. **Extension phone fix** — BEFORE snapshot phones skipped (recruiter's phone)
12. **Extension version fix** — source_details uses actual version instead of hardcoded "2.0.0"
13. **NEW: CV Upload Feature** — Upload PDF/DOCX → AI parses → editable profile → save to Candidate Bank

### Session: Feb 14, 2026
14. **CRITICAL: Profile Overwrite Bug Fix v2** — `extractNaukriProfileId()` was using `sid` (search session ID, shared across all profiles in a search) instead of `id` (unique profile identifier). Fixed priority: `id` first, `sid` as fallback with timestamp.
15. **Backend Safety Net** — Even if `naukri_profile_id` matches, backend now verifies names match before allowing update. Different names = different person = new record.
16. **Extension v3.9.1** — Updated with `uresid` and `storageKey` support for Naukri v3 preview URLs.
17. **Dynamic ZIP Build** — Download endpoint now builds ZIP from source every time, ensuring latest code is always served.
18. **AI Screening Broadened Search** — Matching pipeline now searches across `summary`, `headline`, `designation`, `it_skills`, and `raw_profile_text` (not just `skills` array). Fixed `candidate_email=None` crash. Added keyword search filter.
19. **AI Search (Phase 1)** — Natural language candidate search using GPT-4o-mini.
    - Architecture: LLM (Structured Extraction) → Deterministic DB Filter Engine → Results → LLM (Explanation)
    - System prompt for extraction handles: skills, experience, industry, company type, location, notice period, CTC, degree, stability logic, negation/exclusion
    - Filter preview toggle, per-candidate AI explanation badges
    - Model-agnostic architecture ready for Phase 2 hybrid routing (GPT-4o for complex prompts)
    - New files: `/app/backend/services/ai_search.py`, `/app/backend/routes/ai_search.py`
    - Frontend: New "AI Search" tab on Find Candidates page
    - Search logging: raw prompt, extracted JSON, model, tokens, time
    - Testing: 100% backend (14/14), 100% frontend — all verified

## Admin Credentials (Deployed)
- admin@vhc.in / VhcAdmin@2024
- ajit@vhc.in / 12345678 (employer)
- jatin@vhc.in / 12345678 (recruiter)

## Backlog (P3)
1. AI Screening Shortlist Fix — disabled when JD via "Paste/Upload JD"
2. Forgot Password Feature (P2) — deferred until post-deploy verified
3. Refactor `content.js` in Chrome Extension
4. AI Search Phase 2 — Hybrid routing (GPT-4o-mini default + GPT-4o for complex prompts), conversational follow-ups
2. Refactor content.js into smaller modules
3. Password Reset (external/forgot password flow)

## Cancelled
- Mobile Number Extraction
- N8N / Notion Integration
