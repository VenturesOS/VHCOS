# VHC Talent OS - Product Requirements Document

## Original Problem Statement
Build a production-ready recruitment portal called VHC Talent OS with:
- Role-based access (Admin, Recruiter, Employer, Candidate)
- JWT email/password authentication
- Job Management
- Candidate Pipeline with Kanban stages
- Resume Upload
- Basic Messaging
- Settings Panel
- AI-ready architecture for future resume parsing

## User Personas
1. **Admin**: Full system control - manages users, jobs, candidates, companies, settings
2. **Recruiter**: Manages candidate pipeline, moves candidates through stages, adds notes
3. **Employer**: Posts jobs, views applicants, shortlists/rejects candidates, views analytics
4. **Candidate**: Creates profile, uploads resume, applies to jobs, tracks applications, receives messages

## Core Requirements (Static)
- Secure JWT authentication with bcrypt password hashing
- Role-based middleware and dashboard routing
- MongoDB database with proper collections (users, jobs, applications, companies, messages, settings)
- RESTful API with /api prefix for all endpoints
- Responsive UI with VHC lime green branding (#7CB342)
- Kanban board for candidate pipeline stages

## What's Been Implemented (January 18, 2026)

### Backend (FastAPI + MongoDB)
- ✅ User authentication (register, login, JWT tokens)
- ✅ Role-based access control middleware
- ✅ User management APIs (CRUD)
- ✅ Job management APIs (create, browse, update, delete)
- ✅ Application APIs with pipeline stage management
- ✅ Candidate profile management with resume upload
- ✅ Company management APIs
- ✅ Message APIs (send, receive, mark read)
- ✅ Dashboard stats APIs for all 4 roles
- ✅ Settings management for admin
- ✅ Admin user seeding on startup (admin@vhc.in / vhc@123)

### Frontend (React + Shadcn UI + Tailwind)
- ✅ Login and Registration pages with role selection
- ✅ Admin Dashboard: Stats, Users by Role, Recent Applications
- ✅ Admin pages: Users, Jobs, Candidates, Companies, Settings
- ✅ Recruiter Dashboard: Pipeline overview, Job stats
- ✅ Recruiter Pipeline: Drag-and-drop Kanban board with stages (Applied, Shortlisted, Interview, Offered, Hired)
- ✅ Employer Dashboard: Job stats, Application stages, Recent jobs
- ✅ Employer pages: My Jobs, Post Job, Applicants, Analytics
- ✅ Candidate Dashboard: Applications, Active jobs, Messages
- ✅ Candidate pages: Profile, Browse Jobs, My Applications, Messages
- ✅ VHC branding with lime green (#7CB342) accent colors
- ✅ Role-based sidebar navigation
- ✅ Responsive design with mobile menu

## Prioritized Backlog

### P0 (Critical) - DONE
- [x] Authentication system
- [x] Role-based dashboards
- [x] Job management
- [x] Application management
- [x] Candidate pipeline

### P1 (High Priority) - Future
- [ ] AI Resume Parsing with OpenAI GPT-5.2 (infrastructure ready)
- [ ] Email notifications
- [ ] Advanced search and filtering
- [ ] Job application cover letter preview

### P2 (Medium Priority) - Future
- [ ] WhatsApp/Email automation hooks
- [ ] CRM sync integration
- [ ] Interview scheduling calendar
- [ ] Bulk candidate import

### P3 (Nice to Have) - Future
- [ ] Analytics dashboards with charts
- [ ] Custom workflow automation (n8n hooks)
- [ ] Payment & billing integration
- [ ] White-label client dashboards

## Technical Stack
- Frontend: React 19, Tailwind CSS, Shadcn UI, @hello-pangea/dnd, Recharts
- Backend: FastAPI, Motor (async MongoDB), PyJWT, bcrypt
- Database: MongoDB
- Authentication: JWT with 24-hour expiry

## Admin Credentials
- Email: admin@vhc.in
- Password: vhc@123

## Next Tasks
1. Implement AI Resume Parsing using OpenAI GPT-5.2 (Emergent LLM key ready)
2. Add email notification system
3. Implement interview scheduling with calendar integration
4. Add advanced analytics with more detailed charts
