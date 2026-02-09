# VHC Talent OS - Product Requirements Document

## Original Problem Statement
Build a full-stack recruitment platform (VHC Talent OS) with AI-powered candidate matching, a centralized candidate data bank, job management, and automated sourcing tools. The platform serves Admins, Employers, Recruiters, and Candidates.

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

## Naukri Auto-Sourcing Browser Extension (P0 - COMPLETED Feb 2026)
### Requirements
- Manifest V3 browser extension for automatic profile scraping on Naukri.com
- Passive auto-capture 2-3 seconds after page load + manual capture button
- **Comprehensive 1:1 data capture**: ALL Naukri profile fields including personal details (DOB, gender, marital status), full work history, complete education, IT skills with proficiency, certifications, projects, languages, career preferences, online profiles
- Backend duplicate detection: naukri_profile_id -> email -> phone (CREATE or UPDATE)
- Dedicated NaukriProfileView page with tabbed layout (Overview, Experience, Education, Skills, Personal, Preferences)
- Download button in sidebar for extension ZIP
- Non-intrusive toast notifications

### Implementation
- **Backend**: `POST /api/extension/capture`, `GET /api/extension/profile/{id}`, `GET /api/extension/stats`
- **Model**: `CompleteNaukriProfileInput` with 60+ fields in `backend/models/naukri_profile.py`
- **Frontend**: `NaukriProfileView.jsx` with 6 tabs, routed under admin/recruiter/employer
- **Extension**: `content.js` v2.0 with comprehensive DOM scraping, `background.js`, `popup.html/js`
- **CandidateBank pages**: Updated with Naukri source badge and "Full Profile" navigation button

## Email Notifications (P1 - ON HOLD)
- Resend API integration for real email notifications
- Subdomain: notifications.vhc.in (DNS verification pending)
- API key stored in backend/.env

## Future/Backlog
- P2: Stripe integration for payments
- P2: Multi-tenancy architecture
- P2: Real WhatsApp integration (Twilio)
- P3: Production deployment optimization
- P3: Advanced analytics dashboard
- P3: Candidate deduplication improvements

## Tech Stack
- **Frontend**: React, Shadcn UI, Tailwind CSS, Axios
- **Backend**: FastAPI, Python, Motor (async MongoDB)
- **Database**: MongoDB Atlas
- **AI**: OpenAI API (Emergent LLM Key) for embeddings
- **Extension**: Chrome Manifest V3

## Key Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
