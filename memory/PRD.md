# VHC Talent OS — Product Requirements Document

## Original Problem Statement
Full-stack React + FastAPI recruitment management platform for Ventures HRD Consulting. Features include job management, candidate tracking, submission trackers, pipeline management, AI-powered candidate matching, Chrome extension for Naukri integration, blog engine, SEO tools, revenue dashboards, compliance management, attendance/leave management, and AI-driven attendance intelligence.

## Core Architecture
- **Frontend**: React (CRA with CRACO) with Shadcn/UI, React Router, Recharts
- **Backend**: FastAPI with MongoDB Atlas, APScheduler for cron jobs
- **Auth**: JWT-based, role-based access control (admin, employer, recruiter, candidate)
- **3rd Party**: Cloudflare Turnstile, Cloudflare Zero Trust, MongoDB Atlas, Upstash Redis, Resend Email, OpenAI GPT-4o-mini, Cloudflare R2

## User Roles & Access
| Feature | Admin | Employer | Recruiter |
|---------|-------|----------|-----------|
| Attendance Dashboard | All users | Team only | Own only |
| Attendance Insights | Full analytics | Team insights | No access |
| Leave Management | Approve + Set banks | Request own | Request own |
| Holidays | CRUD | View | View |
| Automation Controls | Full | No | No |

## Key Features Implemented

### Attendance Intelligence System (Feb 24, 2026)
**Phase 1 — Foundation**
- Notification service: `notification_events` + `notification_delivery_logs` collections
- Cron infrastructure: Job-lock mechanism, execution logging, APScheduler
- 14 DB indexes for performance at scale
- Extended configurable settings: reminder_time, auto_absent_time, overtime_threshold, grace_window, weekend_days

**Phase 2 — Automation**
- Attendance reminders: Daily cron (10AM IST) with `should_remind()` decision layer
- Auto-absent marking: Daily cron (6:30PM IST) with grace window, reason=`auto_absent`
- Both respect holidays, weekends, approved leaves, existing check-ins

**Phase 3 — Analytics**
- Extensible API returning `{metrics, charts, insights}` payload
- Metrics: headcount, attendance_rate, absentee_rate, late_rate, avg_hours, overtime
- Charts: daily_trend, weekly_late, team_comparison, work_mode_distribution
- Attendance Health Score: 0-100 per user (punctuality, consistency, absenteeism, overtime)

**Phase 4 — Dashboard UI**
- AttendanceInsightsPage with 5 tabs: Trends, Team, Patterns, Health Scores, Automation
- Line/Bar/Pie charts via Recharts
- Pattern detection insight cards (critical/warning/info)
- Admin trigger buttons for reminders and auto-absent
- Cron execution log viewer

**Phase 5 — Pattern Detection**
- Rule-based: chronic lateness (>5), overtime spikes (>5 days), frequent absences (>3), short check-ins (<4h)
- Severity: critical, warning, info
- Architecture allows future ML upgrade

### Previous Features
- Submission Tracker with role-based visibility filtering
- Job CRUD with approval workflows
- Candidate pipeline management
- AI candidate matching & screening
- Chrome Extension for Naukri (v3.9.2)
- Blog engine with SEO
- Revenue dashboard
- Compliance (DPDP) management

## Known Technical Debt
- **P0 (BLOCKED)**: Temporary emergency hardcoded MongoDB override in `backend/config.py`

## Backlog
- P2: Client Dashboard enhancements
- P3: Advanced Revenue Intelligence
- P4: LinkedIn Auto-Posting (blocked)
- P4: Training Manual PDF refinement
- P5: Attendance Settings UI page
- P5: WhatsApp/Push notification channels

## Key Files
- `backend/services/attendance_cron_service.py` — Cron jobs, locks, notifications, health scores
- `backend/routes/attendance_analytics.py` — Analytics, patterns, notifications, cron triggers
- `backend/routes/attendance.py` — Core attendance CRUD + settings
- `frontend/src/pages/admin/AttendanceInsightsPage.jsx` — Intelligence dashboard
- `frontend/src/pages/shared/AttendancePage.jsx` — Self-service attendance
- `frontend/src/pages/shared/LeaveManagementPage.jsx` — Leave requests
- `frontend/src/pages/admin/AdminAttendancePage.jsx` — Admin attendance overview
- `frontend/src/pages/admin/AdminLeaveManagementPage.jsx` — Leave approvals + banks + holidays

## Test Reports
- `/app/test_reports/iteration_88.json` — Submission tracker role access (100%)
- `/app/test_reports/iteration_89.json` — Visibility filtering (100%)
- `/app/test_reports/iteration_90.json` — Attendance CRUD (95%/100%)
- `/app/test_reports/iteration_91.json` — Attendance Intelligence (100%/100%)
