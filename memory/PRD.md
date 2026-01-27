# VHC Talent OS - Product Requirements Document

## 🔒 BUILD STATUS: PILOT-READY STABLE (January 27, 2026)

**Phase-1 + Phase-1.5: LOCKED & APPROVED**
**Phase-2 Part A: COMPLETE & TESTED (January 19, 2026)**
**Website Content Sync: COMPLETE (January 22, 2026)**
**Home Page Restructure: COMPLETE (January 22, 2026)**
**Dual Front-End Experience: COMPLETE (January 22, 2026)**
**Header & Login UX Unification: COMPLETE (January 22, 2026)**
**Phase-A Internal Governance Backend: COMPLETE & TESTED (January 23, 2026)**
**Phase-B Admin UI for Hierarchy & Governance: COMPLETE & TESTED (January 23, 2026)**
**Phase-C Job & Referral Lifecycle UI: COMPLETE & TESTED (January 23, 2026)**
**Commercial Intelligence Phase: COMPLETE & TESTED (January 23, 2026)**
**Data Governance & Candidate Intelligence: COMPLETE & TESTED (January 24, 2026)**
**Internal OS Enhancement - Phase 1 (Access Control): COMPLETE & TESTED (January 24, 2026)**
**Internal OS Enhancement - Phase 2 (Employer Portal): COMPLETE & TESTED (January 24, 2026)**
**Internal OS Enhancement - Phase 3 (Career Page Control): COMPLETE & TESTED (January 24, 2026)**
**Shareable Job Links + Structured Job ID + JD Parsing: COMPLETE & TESTED (January 27, 2026)**

---

## Latest Feature: Shareable Job Links & JD Intelligence (January 27, 2026)

### Feature 1: Shareable Job Link + Public Job Landing Page ✅
**Testing:** 16/16 backend tests passed, all frontend components verified

**Backend Implementation:**
- Job model updated with `job_public_id` and `shareable_link_enabled` fields
- `PUT /api/jobs/{job_id}/shareable-link` - Toggle shareable link (live jobs only)
- `GET /api/public/jobs/{job_id}` - Public job detail (visibility rules enforced)
- `POST /api/public/apply` - Application with consent validation
- Consent metadata stored: timestamp, IP address, policy version

**Visibility Rules:**
- Public job pages accessible ONLY when: `career_page_status = "live"` AND `shareable_link_enabled = true`
- Company privacy: Returns `public_company_alias` instead of real company name

**Frontend Components:**
- `/jobs/{jobId}` - Public job landing page (no auth required)
- `/application-success` - Confirmation page with styled headings
- Application form: Resume upload, name, email, phone, current_salary, notice_period, consent checkbox

**Security:**
- Rate limiting: 5 applications per minute per IP
- Honeypot field for bot protection
- Consent checkbox required (unchecked by default)

### Feature 2: Structured Job ID Format ✅
**Format:** `VHC/YYYY/NNNN`

**Implementation:**
- Auto-generated on job creation using atomic sequence counter
- Sequence resets yearly
- Stored in `job_public_id` field
- Displayed in job listings and public pages

### Feature 3: JD Parsing During Job Creation ✅ ENHANCED (January 27, 2026)
**Testing:** 13/13 backend tests passed

**Two Input Modes:**
1. **Paste Text** - Textarea for pasting job description text
2. **Upload File** - Upload JD files (PDF, DOC, DOCX, TXT)

**Endpoints:**
- `POST /api/jobs/extract-jd-text` - Extract text from uploaded files (NEW)
- `POST /api/jobs/parse-jd` - AI-powered parsing with input_type tracking

**Extract Endpoint Response:**
```json
{
  "success": true,
  "extracted_text": "...",
  "filename": "job_description.pdf",
  "file_type": "pdf",
  "char_count": 1234,
  "extraction_method": "pdf_fitz",
  "extracted_by": "user_id",
  "extracted_by_role": "admin",
  "extracted_at": "2026-01-27T10:00:00Z"
}
```

**Parse Endpoint Audit Metadata:**
- `input_type`: "paste" or "upload"
- `parsed_by`, `parsed_by_name`, `parsed_by_role`, `parsed_at`

**Frontend Integration:**
- Tabbed UI: "Paste Text" | "Upload File"
- Upload mode: File selection → Extract Text → Preview → Parse JD
- Read-only preview of extracted text before parsing
- Parse JD button disabled until valid input exists
- Advisory warning: "No auto-save"

**Access:** Admin, Employer, Recruiter only (Candidates denied)

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
- ✅ Professional business images (no team/culture photos)

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

## Dual Front-End Experience: ✅ COMPLETE (January 22, 2026)

### Task: Create Employer/Candidate View Switch (inspired by Michael Page)
**Scope:** Add a visible toggle at the top of the public website to switch between Employer and Candidate experiences

**Implementation:**
1. **Global View Switch**
   - Dark header bar with toggle: "For Employers" | "For Candidates"
   - Default state: "For Employers" (green active indicator)
   - Instant switching via JavaScript (no page reload)
   - State persisted in localStorage

2. **Employer View** (existing experience)
   - Hero: "Recruitment Expertise That Delivers Results"
   - Sections: Our Recruitment Expertise, How We Work, Global Hiring Support, Who We Work With
   - Unchanged from previous restructure

3. **Candidate View** (NEW - Michael Page inspired structure)
   - **Hero Carousel**: 4 rotating slides (Career Insights, Salary Benchmarks, Job Market Trends, Global Opportunities)
   - **Job Search Widget**: Keywords, Location, Salary Range fields with "Search Jobs" CTA
   - **Browse Opportunities**: Tabs for Industry, Function, Location, Popular Roles with category cards
   - **Job Match Tool**: CV upload CTA with green gradient background
   - **User Intent Selector**: "Find a Job" vs "Find Talent" cards (Find Talent routes back to Employer view)
   - **CTA Cards**: Register Profile, Looking for a Job, Job Alerts
   - **Career Insights**: 4 article preview cards
   - **Final CTA**: "Ready for Your Next Career Move?"

**Technical Details:**
- Pure HTML/CSS/JS implementation (no React changes)
- localStorage persistence for view preference
- Auto-rotating carousel (5-second interval)
- Tab-based browse navigation
- All CTAs link to existing careers.html
- Shared footer across both views

**Constraints Applied:**
- ✅ Header logo UNTOUCHED
- ✅ Navigation structure UNTOUCHED
- ✅ Login button routes to /login
- ✅ Careers page job listing UNTOUCHED (live jobs still load)
- ✅ Apply flow UNTOUCHED
- ✅ No "US hiring" mentions (uses "Global Hiring" terminology)
- ✅ No backend/API changes
- ✅ No React portal changes

**Verification completed:**
- ✅ Homepage loads correctly on first render
- ✅ Switch toggles instantly between views
- ✅ Careers page still shows live jobs
- ✅ Login button routes correctly to /login
- ✅ No console errors
- ✅ Mobile responsive intact

---

## Phase-A: Internal Governance Backend ✅ COMPLETE & TESTED (January 23, 2026)

### Overview
Enterprise-grade internal governance system for VHC Talent OS with job approval workflows, referral lifecycle management, team hierarchies, and client privacy controls.

### 1. Job Approval Workflow ✅
**States:** `draft` → `pending_approval` → `active` → `on_hold` → `closed` → `archived`

| Role | Creates Job As | Can Transition To |
|------|----------------|-------------------|
| Admin | active | All states (except from archived) |
| Employer | active | active, on_hold, closed |
| Recruiter | pending_approval | None (needs approval) |

**Key Endpoints:**
- `POST /api/jobs` - Create job (status based on role)
- `POST /api/jobs/{id}/transition` - Change job status
- `GET /api/jobs/pending-approval` - View jobs awaiting approval (Admin/Employer)

**Audit:** `approval_history` array tracks all state changes with timestamps and reasons

### 2. Referral Lifecycle ✅
**States:** `submitted` → `validated` → `linked` → `in_process` → `outcome_reached` → `closed`

**Key Endpoints:**
- `POST /api/referrals` - Create referral
- `GET /api/referrals` - List referrals (role-based access)
- `POST /api/referrals/{id}/transition` - Change referral status
- `POST /api/referrals/{id}/link-candidate` - Link to candidate bank

**Features:**
- Duplicate prevention (same email + job_id rejected)
- Audit trail via `status_history` array
- Auto-create candidate bank record on link

### 3. Team & Hierarchy Management ✅
**Structure:** Admin → Employers → Teams → (Recruiters + Companies)

**Key Endpoints:**
- `POST /api/teams` - Create team (Admin only)
- `GET /api/teams` - List teams (Admin: all, Employer: own)
- `PUT /api/teams/{id}` - Update team (Admin only)
- `DELETE /api/teams/{id}` - Soft delete team (Admin only)
- `GET /api/admin/hierarchy` - Full hierarchy view (Admin only)

**Features:**
- Teams link Employers, Recruiters, and Companies
- Recruiters auto-assigned to team via `team_id` field
- Full audit log on team changes

### 4. Client Privacy (Company Name Masking) ✅
**Implementation:**
- `public_company_alias` field on Jobs model
- Public endpoints (`/api/public/jobs`, `/api/public/jobs/{id}`) show alias instead of real company
- Default: "Confidential Client" if alias not set
- `company_id` removed from public responses

### 5. Company-Employer Assignment ✅
**Key Endpoint:**
- `PUT /api/companies/{id}/assign-employer` - Assign employer to company (Admin only)

### Testing Status ✅
- **43 pytest tests passed** (17 core + 26 edge cases)
- Test files:
  - `/app/backend/tests/test_phase_a_governance.py`
  - `/app/backend/tests/test_phase_a_edge_cases.py`

### New Database Collections/Fields

**Jobs Collection (updated):**
```javascript
{
  "status": "draft|pending_approval|active|on_hold|closed|archived",
  "public_company_alias": "string",  // For client privacy
  "team_id": "string",               // Links to teams collection
  "approval_history": [              // Audit trail
    {
      "status": "active",
      "changed_by": "user-id",
      "changed_by_name": "Admin",
      "changed_by_role": "admin",
      "timestamp": "ISO-8601",
      "reason": "Approved by admin"
    }
  ]
}
```

**Teams Collection (new):**
```javascript
{
  "id": "uuid",
  "name": "Team Name",
  "employer_id": "user-id",
  "employer_name": "string",
  "recruiter_ids": ["user-id", ...],
  "recruiter_names": ["string", ...],
  "company_ids": ["company-id", ...],
  "company_names": ["string", ...],
  "status": "active|disabled",
  "audit_log": [...]
}
```

**Referrals Collection (new):**
```javascript
{
  "id": "uuid",
  "job_id": "string",
  "job_title": "string",
  "referrer_id": "user-id",
  "referrer_name": "string",
  "candidate_name": "string",
  "candidate_email": "string",
  "candidate_phone": "string",
  "resume_url": "string|null",
  "note": "string",
  "status": "submitted|validated|linked|in_process|outcome_reached|closed",
  "linked_candidate_id": "string|null",
  "linked_application_id": "string|null",
  "status_history": [...]  // Audit trail
}
```

---

## Phase-B: Admin UI for Hierarchy & Governance ✅ COMPLETE & TESTED (January 23, 2026)

### Overview
Admin-only UI screens for managing the internal governance system, including Teams, Hierarchy visualization, and Company-Employer assignments.

### 1. Teams Management Page ✅
**Route:** `/admin/teams`

**Features:**
- Summary stats (Active Teams, Employers, Recruiters, Companies)
- Search teams functionality
- Create Team dialog with:
  - Team Name (required)
  - Employer selection (required)
  - Recruiters multi-select (checkboxes)
  - Companies multi-select (checkboxes)
- Edit Team dialog (employer read-only after creation)
- Disable Team (soft delete with confirmation)
- Team cards showing recruiters, companies, and active jobs counts
- Active/Disabled sections

### 2. Organization Hierarchy Page ✅
**Route:** `/admin/hierarchy`

**Features:**
- Summary stats (Employers, Teams, Unassigned Recruiters, Unassigned Companies)
- Organization Structure tree view:
  - Expandable Employer nodes
  - Expandable Team nodes showing Recruiters and Companies
- Unassigned Recruiters section with warning styling
- Unassigned Companies section with warning styling

### 3. Read-Only Permissions Matrix ✅
**Location:** Bottom of Hierarchy Page

**Permissions Displayed:**
| Action | Admin | Employer | Recruiter |
|--------|-------|----------|-----------|
| Create Jobs | ✓ | ✓ | ✓ (Pending Approval) |
| Approve Jobs | ✓ | ✓ (Own Team) | – |
| Create Teams | ✓ | – | – |
| Manage Team Members | ✓ | – | – |
| Create Referrals | ✓ | ✓ | ✓ |
| Approve Referrals | ✓ | ✓ | – |
| View Hierarchy | ✓ | ✓ (Own Teams) | – |

### 4. Companies Page Enhancement ✅
**Route:** `/admin/companies`

**New Features:**
- Employer assignment section on each company card
- "Assign" button for unassigned companies
- "Change" button for assigned companies
- Assign Employer dialog with employer dropdown

### 5. Sidebar Navigation ✅
**New Links Added:**
- Teams (`/admin/teams`)
- Hierarchy (`/admin/hierarchy`)

### 6. Access Control ✅
- All new pages restricted to Admin role only
- Non-admin users (Employer, Recruiter) cannot see these links in sidebar
- Direct navigation attempts redirect to role-specific dashboard

### Testing Status ✅
- **11 frontend features tested and working (100%)**
- Test file: `/app/test_reports/iteration_11.json`

### Files Created/Modified
- `/app/frontend/src/pages/admin/TeamsPage.jsx` (new)
- `/app/frontend/src/pages/admin/HierarchyPage.jsx` (new)
- `/app/frontend/src/pages/admin/CompaniesPage.jsx` (enhanced)
- `/app/frontend/src/components/layout/Sidebar.jsx` (updated)
- `/app/frontend/src/App.js` (routes added)
- `/app/frontend/src/lib/api.js` (API methods added)

---

## Phase-B Backlog: Admin UI for Hierarchy & Teams (NEXT)

- Admin dashboard for team management
- Create/Edit/Disable teams UI
- View employer->team->recruiter->company hierarchy
- Assign recruiters to teams
- Permissions matrix view

---

## Phase-C: Job & Referral Lifecycle UI ✅ COMPLETE & TESTED (January 23, 2026)

### Overview
User-facing UI components for job approval workflows, referral submission, and status tracking across Employer and Recruiter roles.

### 1. Employer Job Approval Page ✅
**Route:** `/employer/approvals`

**Features:**
- Status overview cards (Pending Approval, Active, On Hold, Closed)
- Pending Approval Queue with Approve/Hold/Reject action buttons
- All Jobs Status table with status badges and quick actions
- Approval dialogs with reason input and confirmation
- Audit visibility with expandable approval history

**Actions Available:**
- Approve: pending_approval → active
- Hold: active → on_hold
- Reject: pending_approval → closed
- Reactivate: on_hold → active

### 2. Recruiter Referrals Page ✅
**Route:** `/recruiter/referrals`

**Features:**
- Stats cards (Total Referrals, Pending Review, In Process, Outcomes)
- Search by candidate name, email, or job title
- Status filter dropdown (All, Submitted, Validated, Linked, In Process, Outcome Reached, Closed)
- Referral cards with candidate info and status badges
- Expandable status history timeline
- Create Referral dialog (only for ACTIVE jobs)

**Create Referral Form Fields:**
- Job selection (active jobs only) *
- Candidate name *
- Candidate email *
- Candidate phone
- Note

### 3. Sidebar Navigation Updates ✅
**Employer:**
- Added "Approvals" link with CheckCircle icon

**Recruiter:**
- Added "Referrals" link with UserPlus icon

**Access Control:**
- Approvals visible only to Employer
- Referrals visible only to Recruiter

### Testing Status ✅
- **12 frontend features tested and working (100%)**
- Test file: `/app/test_reports/iteration_12.json`

### Files Created/Modified
- `/app/frontend/src/pages/employer/JobApprovalPage.jsx` (new)
- `/app/frontend/src/pages/recruiter/RecruiterReferralsPage.jsx` (new)
- `/app/frontend/src/components/layout/Sidebar.jsx` (updated)
- `/app/frontend/src/App.js` (routes added)
- `/app/frontend/src/lib/api.js` (API methods already added in Phase B)

---

## Commercial Intelligence Phase ✅ IMPLEMENTED (January 23, 2026)

### Overview
Enterprise-grade commercial rate management, revenue tracking, and business analytics for VHC Talent OS.

### 1. Commercials Engine (Company Level) ✅
**Backend Endpoints:**
- `POST /api/commercials` - Create commercial config
- `GET /api/commercials` - List commercials (with company filter)
- `PUT /api/commercials/{id}` - Update commercial
- `DELETE /api/commercials/{id}` - Deactivate commercial (Admin only)

**Commercial Types:**
- Percentage of Salary (e.g., 8.33%)
- Fixed Fee (e.g., ₹1,00,000)
- Level-Based (Junior: 8%, Mid: 10%, Senior: 12%, Leadership: 15%)

**Access Control:**
- Admin: Full control
- Employer: Manage assigned companies only
- Recruiters/Candidates: NO visibility

### 2. Revenue Calculation Engine ✅
**Backend Endpoints:**
- `POST /api/revenue/calculate` - Calculate revenue for application
- `PUT /api/revenue/{id}/override` - Admin-only manual override
- `GET /api/revenue/pipeline` - Pipeline revenue data

**Formula:** Revenue = Offered Salary × Applicable Commercial %

### 3. Admin Analytics Dashboard ✅
**Route:** `/admin/analytics`

**KPIs:**
- Total Active Mandates
- Total Pipeline Revenue
- Closed Revenue
- Avg Time to Close
- Offer-to-Join Ratio
- Active Employers
- Active Recruiters

**Visuals:**
- Revenue Funnel by Stage
- Stage Distribution
- Company-wise Revenue Table
- Recruiter Performance Table

### 4. Employer Analytics Dashboard ✅
**Route:** `/employer/analytics`

**KPIs:**
- Active Mandates
- Pipeline Revenue
- Closed Revenue
- Offers Pending
- Avg Fee %

**Tables:**
- Team Performance
- Company Revenue
- Recruiter Contribution

### 5. Company Pipeline View ✅
**Endpoint:** `GET /api/companies/{id}/pipeline`

**Data:**
- Total/Active/Closed Mandates
- Total Revenue
- Avg Commercial %
- Pipeline Table (Job, Level, Recruiters, Stage, Revenue)

### 6. JD Parsing ✅
**Endpoint:** `POST /api/jobs/parse-jd`

**Capabilities:**
- Text input or file upload (PDF/DOC/DOCX/TXT)
- AI parsing using GPT-5.2 via Emergent
- Extracts: Title, Skills, Experience, Location, Level, Salary, Summary

### 7. Mandate Assignment ✅
**Endpoints:**
- `POST /api/jobs/{id}/assign-recruiters` - Assign recruiters to job
- `GET /api/jobs/{id}/assignments` - Get job assignments

### 8. Security & Governance ✅
**Visibility Rules:**
- Revenue & Commercials: Admin + Assigned Employer ONLY
- Recruiters: Execution only (no financial data)
- Candidates: Zero financial visibility

**Verified:** Recruiter access to `/api/commercials` returns "Insufficient permissions"

### Files Created
- `/app/frontend/src/pages/admin/AdminAnalyticsPage.jsx`
- `/app/frontend/src/pages/admin/CommercialsPage.jsx`
- `/app/frontend/src/pages/employer/EmployerAnalyticsPage.jsx`
- Backend: Commercial Intelligence endpoints in `server.py`

---

## Data Governance & Candidate Intelligence ✅ COMPLETE & TESTED (January 24, 2026)

### Overview
Enterprise-grade data governance layer enforcing mandatory candidate fields, providing complete activity history visibility, and ensuring audit compliance across all candidate operations.

### 1. Mandatory Field Enforcement ✅

**Mandatory Fields (All candidate creation/update points):**
- `current_salary` (INR) - Required, must be positive
- `notice_period` - Required (Immediate, 15/30/45/60/90/90+ days)
- `location` - Required (city/region)
- `experience_years` - Required (0 for freshers)

**Enforcement Points:**
- `POST /api/candidate-bank/batch-save` - Rejects candidates missing any mandatory field (422)
- `POST /api/applications/link-candidate` - Validates candidate has all mandatory fields
- `PUT /api/candidate-bank/{id}/salary-notice` - Updates all 4 mandatory fields with audit

**Pydantic Model Validation:**
- `BatchUploadCandidate` model now requires location and experience_years
- Validation helper: `validate_mandatory_candidate_fields()` centralized validation

### 2. Candidate Activity History ✅

**Endpoint:** `GET /api/candidate-bank/{id}/history`

**Response Structure:**
```json
{
  "candidate_id": "uuid",
  "candidate_name": "string",
  "applications": [
    {
      "application_id": "uuid",
      "job_id": "uuid",
      "job_title": "string",
      "company_name": "string",
      "stage": "applied|shortlisted|interview|offered|hired|rejected",
      "source": "manual_link|self|referral",
      "applied_at": "ISO-8601",
      "current_salary_at_application": 1200000
    }
  ],
  "freshness": {
    "last_profile_updated_at": "ISO-8601",
    "last_application_date": "ISO-8601",
    "profile_created_at": "ISO-8601"
  },
  "summary": {
    "total_applications": 5,
    "stages": {
      "applied": 2,
      "hired": 1,
      "rejected": 1,
      "interview": 1
    }
  },
  "profile_audit": [...]
}
```

**Access Control:** Admin, Employer, Recruiter only

### 3. Profile Freshness Metadata ✅

**New Fields on Candidate Records:**
- `last_profile_updated_at` - Updated on any profile edit
- `last_application_date` - Updated when candidate applies to any job
- `profile_created_at` - Set on creation (immutable)

**Automatic Updates:**
- Profile changes trigger freshness update
- Applications automatically update last_application_date
- Stage changes logged in application history

### 4. Audit Logging ✅

**Tracked Fields:** current_salary, notice_period, location, experience_years

**Audit Entry Structure:**
```json
{
  "field": "current_salary",
  "old_value": 1600000,
  "new_value": 1200000,
  "changed_by": "user-id",
  "changed_by_name": "Admin Name",
  "changed_by_role": "admin",
  "timestamp": "ISO-8601",
  "source": "manual_update|application_edit"
}
```

**Storage:**
- `audit_logs` collection (global)
- `profile_update_audit` array on each candidate record

### 5. SEO Verification ✅

**Action Taken:** Removed `noindex, nofollow` meta tags from all public HTML files

**Files Updated (8 total):**
- Index.html
- about.html
- services.html
- industries.html
- contact.html
- careers.html
- global-hiring.html
- sitemap.html

**Preserved:** All other meta tags (description, keywords, author, Open Graph)

### Frontend Updates ✅

**Candidate Data Bank Page (`/admin/candidate-bank`):**
- Profile dialog shows freshness metadata (Profile Updated, Last Applied dates)
- New "Activity History" tab showing:
  - Summary stats (Total Applications, Hired, Interviews)
  - Profile Freshness section
  - Application History with stages, dates, sources
  - Recent Profile Changes audit log

**Add as Applicant Dialog:**
- 4 mandatory fields: Salary, Notice Period, Location, Experience
- Validation warning when fields missing
- Button disabled until all fields filled

**Batch Upload Page (`/admin/batch-upload`):**
- Location and Experience years inputs added
- Updated mandatory fields notice
- Validation for all 4 fields

### Testing Status ✅
- **Backend:** 14/14 tests passed (100%)
- **Frontend:** All features working
- Test files: `/app/backend/tests/test_data_governance.py`, `/app/backend/tests/test_data_governance_comprehensive.py`
- Test report: `/app/test_reports/iteration_13.json`

### Files Modified
- `/app/backend/server.py` - Validation, history endpoint, audit logging
- `/app/frontend/src/pages/admin/CandidateDataBankPage.jsx` - Activity History tab, freshness display
- `/app/frontend/src/pages/admin/BatchUploadPage.jsx` - Location, experience fields
- `/app/frontend/src/lib/api.js` - getHistory(), updateMandatoryFields() methods
- `/app/frontend/public/website/*.html` - SEO tags removed

---

## P1 Technical Debt: Backend Refactoring ✅ IN PROGRESS (January 24, 2026)

### server.py Modularization - Phase 1 Complete

**Status:** Structural foundation created, original server.py preserved

**Completed Work:**

| Component | Status | Location |
|-----------|--------|----------|
| Core Config Module | ✅ Created | `/app/backend/core/config.py` |
| Database Module | ✅ Created | `/app/backend/core/database.py` |
| Security Module | ✅ Created | `/app/backend/core/security.py` |
| Data Governance Helpers | ✅ Created | `/app/backend/core/helpers.py` |
| User Models | ✅ Created | `/app/backend/models/user.py` |
| Job Models | ✅ Created | `/app/backend/models/job.py` |
| Candidate Models | ✅ Created | `/app/backend/models/candidate.py` |
| Application Models | ✅ Created | `/app/backend/models/application.py` |
| Company Models | ✅ Created | `/app/backend/models/company.py` |
| Team Models | ✅ Created | `/app/backend/models/team.py` |
| Referral Models | ✅ Created | `/app/backend/models/referral.py` |
| Message Models | ✅ Created | `/app/backend/models/message.py` |
| Candidate Bank Models | ✅ Created | `/app/backend/models/candidate_bank.py` |
| Alerts Models | ✅ Created | `/app/backend/models/alerts.py` |
| Commercial Models | ✅ Created | `/app/backend/models/commercial.py` |
| Matching Models | ✅ Created | `/app/backend/models/matching.py` |
| Auth Routes | ✅ Created | `/app/backend/routes/auth.py` |

**Constraints Respected:**
- ✅ NO functional changes
- ✅ NO schema changes
- ✅ NO API contract changes
- ✅ Behavior remains identical
- ✅ All 80+ tests passing

**Documentation:** `/app/backend/REFACTORING.md`

**Remaining Work (Future):**
- Migrate server.py to use module imports
- Extract remaining route modules

---

## Phase-2 Backlog (DEFERRED)

- WhatsApp Automation
- Email Campaign Automation
- CRM Synchronization
- Payment & Billing (Stripe)
- Advanced Analytics

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

*Last Updated: January 24, 2026*
*Phase-1: Signed Off*
*Phase-1.5: Complete*
*Website Content Sync: Complete*
*Phase-A Internal Governance Backend: Complete (43 tests passed)*
*Phase-B Admin UI for Hierarchy & Governance: Complete (11 features tested)*
*Phase-C Job & Referral Lifecycle UI: Complete (12 features tested)*
*Commercial Intelligence Phase: Complete*
*Data Governance & Candidate Intelligence: Complete (14 tests passed)*
*Internal OS Enhancement - Phase 1 (Access Control): Complete*
*Internal OS Enhancement - Phase 2 (Employer Portal): Complete (14 tests passed)*
*Internal OS Enhancement - Phase 3 (Career Page Control): Complete*
*P1 Backend Refactoring: In Progress (modular structure created)*
