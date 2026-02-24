# VHC Talent OS — Product Requirements Document

## Original Problem Statement
Full-stack React + FastAPI recruitment management platform for Ventures HRD Consulting. Features include job management, candidate tracking, submission trackers, pipeline management, AI-powered candidate matching, Chrome extension for Naukri integration, blog engine, SEO tools, revenue dashboards, compliance management, and attendance/leave management.

## Core Architecture
- **Frontend**: React (CRA with CRACO) with Shadcn/UI, React Router
- **Backend**: FastAPI with MongoDB Atlas
- **Auth**: JWT-based, role-based access control (admin, employer, recruiter, candidate)
- **3rd Party**: Cloudflare Turnstile, Cloudflare Zero Trust, MongoDB Atlas, Upstash Redis, Resend Email, OpenAI GPT-4o-mini, Cloudflare R2

## User Roles & Visibility
- **Admin**: Full system access, sees all data, manages leave banks & holidays
- **Employer**: Company-specific access, sees own + team (recruiters) attendance
- **Recruiter**: Mandate-based operations, sees own attendance only
- **Candidate**: Job browsing, applications, profile management

## Key Features Implemented

### Attendance & Leave Management (NEW - Feb 24, 2026)
- **Self Check-in/Check-out**: Work mode (Office/WFH/Field), IP logging, late/overtime tracking
- **Admin Override**: Admin can mark/override attendance for any user
- **Leave Request Workflow**: Request → Pending → Approved/Rejected. Leave types: Casual, Sick, Earned, Comp-Off
- **Leave Balance Bank**: Admin sets per-user quotas. Auto-deducted on approval.
- **Holiday Calendar**: Admin-managed (National/Festival/Company/Optional)
- **Monthly Reports**: Admin dashboard + Excel export
- **Backend**: `/app/backend/routes/attendance.py`
- **Frontend**: `AttendancePage.jsx`, `LeaveManagementPage.jsx`, `AdminAttendancePage.jsx`, `AdminLeaveManagementPage.jsx`

### Submission Tracker (Updated - Feb 24, 2026)
- Full CRUD for admin, employer, recruiter
- Role-based visibility filtering (admin sees all, recruiter sees own + assigned mandates, employer sees own + posted)
- Access control on individual tracker view (403 for unauthorized)

### Other Features
- Job CRUD with approval workflows
- Candidate pipeline management
- AI candidate matching & screening
- Chrome Extension for Naukri (v3.9.2)
- Blog engine with SEO optimization
- Revenue dashboard
- Compliance (DPDP) management
- Bulk import/export
- Team hierarchy management

## Known Technical Debt
- **P0 (BLOCKED)**: Temporary emergency hardcoded MongoDB override in `backend/config.py`. Awaiting Emergent Support to disable managed MongoDB auto-binding.

## Backlog (Prioritized)
- P1: AI-driven Analytics and Insights
- P2: Client Dashboard enhancements
- P3: Advanced Revenue Intelligence
- P4: LinkedIn Auto-Posting (blocked on API scope approval)
- P4: Training Manual PDF refinement

## DB Collections (Attendance)
- `attendance_records`: id, user_id, date, check_in, check_out, status, work_mode, hours_worked, late_minutes, overtime_minutes, is_late, ip_address, notes, marked_by
- `leave_requests`: id, user_id, leave_type, start_date, end_date, days, half_day, reason, status, approved_by
- `leave_balances`: user_id, year, {casual/sick/earned/comp_off}_leave_{total/used}
- `holidays`: id, name, date, holiday_type, is_optional
- `attendance_settings`: work_start_time, work_end_time, late_threshold_minutes, half_day_hours

## Key API Endpoints (Attendance)
- `POST /api/attendance/check-in` — Self check-in
- `POST /api/attendance/check-out` — Self check-out
- `GET /api/attendance/my` — My records
- `GET /api/attendance/today` — Today's status
- `POST /api/attendance/admin/mark` — Admin override
- `GET /api/attendance/all` — All records (admin)
- `GET /api/attendance/report/monthly` — Monthly summary
- `GET /api/attendance/report/export` — Excel export
- `POST /api/attendance/leave/request` — Request leave
- `PUT /api/attendance/leave/requests/{id}/approve` — Approve leave
- `PUT /api/attendance/leave/admin/balance/{user_id}` — Set leave balance
- CRUD `/api/attendance/holidays` — Holiday management

## Test Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Recruiter: yamini@vhc.in / VhcAdmin@2024

## Test Reports
- `/app/test_reports/iteration_88.json` — Submission tracker role access (100% pass)
- `/app/test_reports/iteration_89.json` — Visibility filtering (100% pass)
- `/app/test_reports/iteration_90.json` — Attendance & Leave Management (95%/100% pass)
