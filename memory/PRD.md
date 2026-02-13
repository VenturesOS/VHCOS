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
- **Extension:** v3.8.5 (Ventures HRD branded)

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
└── browser-extension/           # v3.8.5
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

## Admin Credentials (Deployed)
- admin@vhc.in / VhcAdmin@2024
- ajit@vhc.in / 12345678 (employer)
- jatin@vhc.in / 12345678 (recruiter)

## Backlog (P3)
1. AI Screening Shortlist Fix — disabled when JD via "Paste/Upload JD"
2. Refactor content.js into smaller modules
3. Password Reset (external/forgot password flow)

## Cancelled
- Mobile Number Extraction
- N8N / Notion Integration
