# VHC Talent OS - Product Requirements Document

## 🔒 BUILD STATUS: PILOT-READY STABLE (January 22, 2026)

**Phase-1 + Phase-1.5: LOCKED & APPROVED**
**Phase-2 Part A: COMPLETE & TESTED (January 19, 2026)**
**Website Content Sync: COMPLETE (January 22, 2026)**
**Home Page Restructure: COMPLETE (January 22, 2026)**
**Dual Front-End Experience: COMPLETE (January 22, 2026)**

---

## Overview
VHC Talent OS is a production-ready, role-based recruitment portal built for VHC Talent Advisory. The system supports Executive Search, Specialist Hiring, and People Advisory services across India and the United States.

---

## Phase-1 Status: ✅ COMPLETE (Signed Off: January 18, 2026)

### P0: Candidate Apply & Resume Review Flow ✅
- Two-step application process with AI parsing
- Editable review form with salary/notice period capture

### P1: Applicant Review Screen ✅
- Per-job applicant management with match scores
- Manual actions: Shortlist, Reject, Hold, Over Budget, Not Qualified

### P2: Career Stability Indicator ✅
- Green/Yellow/Red indicators based on job tenure
- Informational only - no auto-reject

### P3: Website Landing & Header Fix ✅
- Root URL redirects to public website
- Header: Home | About | Services | Industries | Career | Contact | Global Hiring | Login

---

## Phase-1.5 Status: ✅ COMPLETE & TESTED (January 19, 2026)

### Task 1: Controlled Salary, Notice Period & Candidate Detail Preview/Edit ✅
**Testing:** 19 pytest tests passed - all backend and frontend functionality verified

**Visibility (Admin, Employer, Recruiter can VIEW):**
- Current salary (INR)
- Notice period
- Skills
- Experience summary

**Controlled Editing (Explicit "Edit Details" mode):**
- Current salary (INR) - number input
- Notice period - dropdown select
- Skills - add/remove with tags
- Experience summary - textarea

**Data Precedence (STRICT):**
```
Candidate self-edit > Employer edit > Recruiter edit > Resume parsing
```
- `manually_edited` flag prevents parsing overwrites
- Manual edits always take precedence

### Task 2: CV Preview & Download (Reviewer Side) ✅
- Admin, Employer, Recruiter can preview/download candidate CVs
- Download filename format: `Firstname_Lastname_VHC.ext`
- Permission-based access (Admin: all, Employer/Recruiter: their jobs only)
- Graceful fallback if CV is missing

### Task 3: Admin User Management ✅
- View ALL users across the system
- Create users (Employer, Recruiter, Candidate)
- Delete users (soft delete)
- Reset user passwords
- Assign recruiters to employers
- Deactivate/reactivate users

### Task 4: Admin Collective Pipeline View ✅
- Global read-only pipeline overview
- Stages: Applied, Shortlisted, Interview, Offered, Hired, Rejected, On Hold, Over Budget, Not Qualified
- Filters: By Employer, By Recruiter, By Job
- View-only (Admin cannot move candidates from this view)

**Audit Trail:**
- Every edit logged with:
  - Field changed
  - Old value
  - New value
  - Updated by (name, role, user_id)
  - Timestamp
- "Last updated by" displayed in UI
- Edit history endpoint: `GET /api/applications/{id}/edit-history`

**UX Constraints Respected:**
- No resume file replacement
- No identity field edits (email/phone)
- No job history date changes
- Read-only view by default

---

## API Endpoints (Phase-1.5)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/applications/{id}/details` | PUT | Update applicant details with audit |
| `/api/applications/{id}/edit-history` | GET | Get full edit audit trail |

---

## Database Schema Updates (Phase-1.5)

Applications collection now includes:
```javascript
{
  // ... existing fields
  "experience_summary": "string",  // Editable summary text
  "edit_history": [                // Audit trail
    {
      "field": "current_salary",
      "old_value": null,
      "new_value": 1800000,
      "updated_by_id": "user-id",
      "updated_by_name": "System Admin",
      "updated_by_role": "admin",
      "timestamp": "2026-01-18T16:28:53.454Z"
    }
  ],
  "last_edited_by": {
    "name": "System Admin",
    "role": "admin",
    "user_id": "user-id",
    "timestamp": "2026-01-18T16:28:53.454Z"
  },
  "manually_edited": true          // Prevents parsing overwrites
}
```

---

## Demo Login Credentials

**Login URL:** `https://[preview-url]/login`

| Role | Email | Password | Notes |
|------|-------|----------|-------|
| Admin | admin@vhc.in | VhcAdmin@2024 | INTERNAL USE ONLY - Do not display on public website |
| Employer | employer@vhctalent.com | Demo@2024 | Demo employer account |
| Recruiter | recruiter@vhctalent.com | Demo@2024 | Demo recruiter account |
| Candidate | candidate@vhctalent.com | Demo@2024 | Demo candidate account |

**Notes:**
- No first-login password reset required
- Accounts are stable and will not auto-expire
- Admin credentials must NOT be shown on public website

---

## Website Content Sync: ✅ COMPLETE (January 22, 2026)

### Task: Public Website Content & Asset Synchronization
**Scope:** Content-only synchronization from user-provided zip file (`vhc-website-corrected.zip`)

**What was synced:**
- Index.html (Homepage content)
- about.html (About page content with team slider)
- services.html (Services page - Executive Search, Specialist Hiring)
- industries.html (Industries we serve)
- contact.html (Contact form and office locations)
- global-hiring.html (Bi-Continental expertise content)
- sitemap.html
- New assets: Hero images, team photos

**What was preserved (NON-NEGOTIABLE constraints):**
- ✅ Header logo (SVG, 56px height)
- ✅ Navigation structure and URLs
- ✅ Login button behavior (routes to /login)
- ✅ careers.html - NOT modified (preserves live job loading functionality)
- ✅ Cloudflare Turnstile integration on careers page

**Verification completed:**
- ✅ Homepage loads correctly on first render
- ✅ All images load without broken links
- ✅ Careers page still shows live jobs
- ✅ Login button routes correctly to /login
- ✅ Navigation active states working on all pages
- ✅ No regressions introduced

---

## Home Page Restructure: ✅ COMPLETE (January 22, 2026)

### Task: Restructure Home Page as "Recruitment Expertise" Gateway
**Scope:** Transform Home page from "About/Story" style to expertise-focused gateway (Michael Page style)

**New Home Page Sections:**
1. **Hero**: "Recruitment Expertise That Delivers Results" - expertise-focused headline with CTAs
2. **Our Recruitment Expertise**: 3 cards (Executive Search, Specialist Hiring, Talent Advisory) with professional business images
3. **How We Work**: 4-step engagement model (Discovery → Research & Sourcing → Assessment → Placement & Support)
4. **Global Hiring Support**: International reach section with region bullets (India & APAC, Middle East, Europe, Americas) - NO US-specific mentions
5. **Who We Work With**: 4 client type cards (Enterprise, Growth-Stage, Industrial, Professional Services)
6. **Final CTA**: "Ready to Find Exceptional Talent?"

**Content Rules Applied:**
- ✅ NO firm history, years of experience, philosophy, values, leadership bios (moved to About)
- ✅ Uses "Global Hiring" terminology (no US hiring mentions)
- ✅ Expertise-led, capability-focused content
- ✅ Professional business/strategy images (no team/culture photos)

**What was preserved:**
- ✅ Header logo (SVG, 56px height) - UNTOUCHED
- ✅ Navigation structure and URLs - UNTOUCHED
- ✅ Login button routing to /login - UNTOUCHED
- ✅ Footer structure with updated copy
- ✅ VHC brand colors (#9acd32 green, #111827 dark)

**Verification completed:**
- ✅ Home page loads correctly on first render
- ✅ Home content is clearly distinct from About page
- ✅ All images load correctly
- ✅ Careers page still loads live jobs
- ✅ Login button routes correctly to /login
- ✅ No layout or routing regressions

---

## Phase-2 Backlog (NOT STARTED)

- WhatsApp Automation
- Email Campaign Automation
- CRM Synchronization
- Payment & Billing (Stripe)
- Advanced Analytics
- Backend Refactoring (server.py modularization)

---

## Notes
- Email (Resend) and WhatsApp (Twilio) notifications are MOCKED
- Currency standardized to INR
- Rate limiting active on public endpoints

---

## Bug Fixes (Phase-1 Hardening)

### ✅ Blank White Screen on First Load (Fixed: January 19, 2026)
**Root Cause:** React Router's `<Navigate>` component was redirecting to `/website/Index.html`, but React was intercepting this route and rendering an empty React component instead of serving the static HTML file.

**Solution:** Replaced `<Navigate>` with a custom `PublicWebsiteRedirect` component that uses `window.location.replace()` to perform a hard redirect, bypassing React Router and allowing the static HTML to be served directly.

**Files Changed:**
- `/app/frontend/src/pages/PublicWebsite.jsx` (new)
- `/app/frontend/src/App.js` (updated imports and routes)

---

*Last Updated: January 22, 2026*
*Phase-1: Signed Off*
*Phase-1.5: Complete*
*Website Content Sync: Complete*
