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
│   ├── server.py              # Main FastAPI app, CORS, seed admin
│   ├── routes/
│   │   ├── auth.py            # Login/register/password reset
│   │   ├── admin.py           # User management, admin operations
│   │   ├── analytics.py       # Dashboard analytics + PDF export
│   │   ├── applications.py    # AI screening, job applications
│   │   ├── candidates.py      # Candidate bank CRUD + access control
│   │   ├── extension.py       # Chrome extension capture + AI extract
│   │   ├── profile.py         # NEW: Candidate profile + messaging
│   │   └── files.py           # File downloads (extension ZIP)
│   └── config.py
├── frontend/src/
│   ├── lib/api.js             # Relative API URLs (no CORS issues)
│   ├── lib/auth.js            # Auth context
│   └── pages/                 # Role-based pages
└── browser-extension/
    ├── content.js             # v3.8.5 - API calls via background proxy
    ├── background.js          # API proxy handler (CORS-exempt)
    ├── popup.html             # Ventures HRD branded
    └── manifest.json          # v3.8.5
```

## Admin Credentials (Deployed)
- admin@vhc.in / 12345678 (password synced from .env on startup)
- ajit@vhc.in / 12345678 (employer)
- jatin@vhc.in / 12345678 (recruiter)

## What's Been Implemented

### Session: Feb 12-13, 2026
1. **Domain Migration** - portal.vhc.in → ventureshrd.com
2. **Branding Update** - "VHC Talent OS" → "Ventures HRD" everywhere
3. **Favicon/Tab Logo** - Updated to VHC logo
4. **CORS Fix** - Switched to relative API URLs (eliminates cross-origin issues)
5. **CORS Hardcoded** - Production origins in server.py as fallback
6. **Admin Login Sync** - Seed function syncs admin password from .env on every startup
7. **Admin Role in Create User** - Can now create admin accounts from UI
8. **Extension v3.8.5**:
   - All API calls routed through background.js (CORS-exempt)
   - Recruiter phone/email filter on AI fallback
   - Default URL: ventureshrd.com
   - Branding: Ventures HRD
9. **Candidate Profile Routes** - /api/profile, /api/messages endpoints
10. **CRITICAL FIX: Candidate Overwrite Bug** - naukri_profile_id=None query was matching ALL records, causing new captures to overwrite old ones. Fixed by skipping lookup when ID is empty.
11. **Extension ZIP Rebuild** - Download now serves v3.8.5 with all fixes

### Previous Sessions
- Advanced Analytics Dashboard with charts, filters, PDF export
- Chrome Extension URL gating (only individual profiles)
- Inline Candidate Detail View fix
- Admin Data Cleanup
- Production Readiness (indexes, security hardening)

## Known Issues
- None critical

## Backlog (P3)
1. AI Screening Shortlist Fix - disabled when JD via "Paste/Upload JD"
2. Refactor content.js into smaller modules (tech debt)

## Cancelled
- Mobile Number Extraction (user cancelled)
- N8N / Notion Integration (user decided not needed)
