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

## Naukri Auto-Sourcing Browser Extension (v3.5.0)
### Implementation
- **AI-Powered Pipeline**: Extension captures page text -> Backend AI endpoint (OpenAI GPT-4o-mini) extracts structured JSON -> Capture endpoint saves to DB
- **Direct API Calls**: Extension v3.5.0 calls capture API directly via fetch (bypasses Manifest V3 service worker reliability issues)
- **Text Cleaning**: Strips nav/header/footer/sidebar noise from DOM before AI extraction
- **Smart Scrolling**: Multi-pass scroll with late-content detection for CV preview (email/phone)
- **Deduplication**: naukri_profile_id -> email -> phone -> name match chain
- **Backend**: POST /api/extension/capture, POST /api/extension/ai-extract, GET /api/extension/profile/{id}, GET /api/extension/stats
- **Frontend**: NaukriProfileView.jsx with 6 tabs (Overview, Experience, Education, Skills, Personal, Preferences)
- **Download**: GET /api/download/naukri-extension serves extension ZIP
- **CandidateBankRecord**: email field is Optional to support Naukri profiles with hidden contact info
- **"Hidden on Naukri"**: Profile view shows italic muted text for null email/phone

## Tech Stack
- **Frontend**: React, Shadcn UI, Tailwind CSS, Axios
- **Backend**: FastAPI, Python, Motor (async MongoDB)
- **Database**: MongoDB Atlas
- **AI**: OpenAI GPT-4o-mini (via Emergent LLM Key) for profile text extraction
- **Extension**: Chrome Manifest V3 (content scripts, service worker, popup)

## Key Credentials
- Admin: admin@vhc.in / VhcAdmin@2024

## Backlog / Future Tasks
- P1: Improve inline candidate detail view (buggy for Naukri-sourced candidates missing audit logs)
- P2: Admin tool to clean up bad/test data from older extension versions
- P2: Stripe integration for payments
- P2: Multi-tenancy architecture
- P3: Refactor monolithic content.js into smaller modules
- P3: Advanced analytics dashboard
- P3: Email Notifications (Resend API - ON HOLD, DNS pending)
