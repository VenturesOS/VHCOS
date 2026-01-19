# VHC Talent OS - Product Requirements Document

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

## Phase-1.5 Status: ✅ COMPLETE & TESTED (January 18, 2026)

### Controlled Salary, Notice Period & Candidate Detail Preview/Edit
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

## Test Credentials

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@vhc.in | VhcAdmin@2024 |
| Employer | employer@vhctalent.com | Demo@2024 |

---

## Phase-2 Backlog (NOT STARTED)

- WhatsApp Automation
- Email Campaign Automation
- CRM Synchronization
- Payment & Billing (Stripe)
- Advanced Analytics
- Backend Refactoring

---

## Notes
- Email (Resend) and WhatsApp (Twilio) notifications are MOCKED
- Currency standardized to INR
- Rate limiting active on public endpoints

---

*Last Updated: January 18, 2026*
*Phase-1: Signed Off*
*Phase-1.5: Complete*
