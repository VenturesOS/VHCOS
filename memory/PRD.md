# VHC Talent OS - Product Requirements Document

## Original Problem Statement
Build a full-stack recruitment platform (VHC Talent OS) with AI-powered candidate matching, a centralized candidate data bank, job management, and automated sourcing tools. The platform serves Admins, Employers, Recruiters, and Candidates.

A Chrome extension scrapes candidate profiles from Naukri.com (Resdex) and saves them into the VHC Talent OS candidate bank. Requirements include:
- Accurate profile scraping (main profile, not sidebar)
- Complete data extraction (experience, education, skills, contact from CV preview)
- AI-powered parsing via OpenAI for resilient structured extraction
- Deduplication using naukri_profile_id, email, phone
- Seamless viewing of captured profiles across Admin/Recruiter/Employer roles

## Core Features (Implemented)
- Multi-role authentication (Admin, Employer, Recruiter, Candidate)
- Job posting and management with AI screening
- Candidate Data Bank with deduplication, search, and visibility rules
- AI-powered Quick Match and Full AI Match (OpenAI embeddings)
- Match History tracking
- Bulk Import (Excel + CV ZIP) with AI resume parsing
- Pipeline management (shortlisting, status tracking)
- Bug reporting system (manual + automated)
- System health dashboard

## Naukri Auto-Sourcing Browser Extension (v3.6.0)
### Implementation
- **AI-Powered Pipeline**: Extension captures page text -> Backend AI endpoint (OpenAI GPT-4o-mini) extracts structured JSON -> Capture endpoint saves to DB
- **Multi-Strategy Text Extraction**:
  - Strategy A: Try 15+ Resdex-specific container selectors (profileContainer, candidateDetail, rightSection, etc.)
  - Strategy B: Clone body + aggressive DOM stripping (40+ noise selectors for nav, sidebar, chatbot, ads)
  - Strategy C: Line-by-line text post-processing (removes nav patterns, finds profile content start)
- **Direct API Calls**: Extension calls capture API directly via fetch (bypasses Manifest V3 service worker)
- **Smart Scrolling**: Multi-pass scroll with late-content detection for lazy-loaded CV preview
- **Strict AI Prompt**: Never appends years/titles to name, rejects naukri.com/placeholder emails, ignores marketing text
- **Backend Validation**: Rejects invalid names (nav text, marketing slogans), cleans appended experience years, strips fake emails
- **Deduplication**: naukri_profile_id -> email -> phone -> name match chain
- **CandidateBankRecord**: email field is Optional for Naukri profiles with hidden contacts
- **"Hidden on Naukri"**: Profile view shows italic muted text for null email/phone

### Key Endpoints
- POST /api/extension/capture (with validation)
- POST /api/extension/ai-extract (strict OpenAI prompt)
- GET /api/extension/profile/{id}
- GET /api/extension/stats
- GET /api/download/naukri-extension (no-cache headers, version header)

## Tech Stack
- **Frontend**: React, Shadcn UI, Tailwind CSS, Axios
- **Backend**: FastAPI, Python, Motor (async MongoDB)
- **Database**: MongoDB Atlas
- **AI**: OpenAI GPT-4o-mini (via Emergent LLM Key)
- **Extension**: Chrome Manifest V3

## Key Credentials
- Admin: admin@vhc.in / VhcAdmin@2024

## Completed (Dec 2025 - Feb 2026)
- Full AI extraction pipeline (DOM scraping -> AI parsing)
- Frontend routing fix (was redirecting to homepage)
- Extension stability fixes (CORS, service worker bypass)
- Backend packaging fix (manifest.json at root of ZIP)
- v3.5.0: Silent capture fix, text cleaning, CV scroll improvements
- v3.6.0: Multi-strategy text extraction, strict AI prompt, backend name/email validation, test data cleanup

## Backlog / Future Tasks
- P1: Fix inline candidate detail view (buggy for Naukri-sourced candidates)
- P2: Admin tool to clean up bad data from older extension versions
- P3: Refactor monolithic content.js into modules
- P3: Advanced analytics dashboard
