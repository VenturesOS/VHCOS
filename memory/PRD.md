# Ventures HRD - Product Requirements Document

## Original Problem Statement
VHC Talent OS — a full-stack Recruitment Operating System for Ventures HRD recruitment agency. The platform manages the end-to-end hiring pipeline across Admin, Employer, Recruiter, and Candidate roles.

## Core Architecture
- Frontend: React + Tailwind CSS + Shadcn UI
- Backend: FastAPI + MongoDB
- Browser Extension: Chrome Extension (v3.9.1) for Naukri profile capture
- AI Integration: OpenAI GPT-4o-mini for AI Search and JD parsing

## What's Been Implemented

### Authentication & Authorization
- JWT-based auth with role-based access (Admin, Employer, Recruiter, Candidate)
- Login, Register pages

### Admin Features
- Dashboard with stats overview
- User Management (CRUD)
- Jobs Management with career page, shareable links, mandate links
- Candidate Data Bank with search, filters, CV upload, profile editing
- Pipeline (Kanban-style) with 9 stages
- Bulk Import (Excel + CV/ZIP modes) with AI industry detection
- Import History
- Companies Management with employer assignment
- Commercials Management (percentage, fixed, level-based)
- Teams & Hierarchy Management
- Advanced Analytics with filters, charts, KPI scorecards, PDF export
- AI Search Analytics (usage, cost tracking in PDF report)
- Naukri Extension download

### Employer Features
- Dashboard with quick actions and job stats
- Job Creation with AI JD Parser
- Find Candidates with Quick Match + Full AI Match modes
- AI Search (natural language prompt-based candidate search)
- Candidate Bank (scoped to own team/applicants)
- Pipeline Management
- Analytics
- Match History

### Recruiter Features
- Dashboard with daily workflow and pipeline overview
- Jobs assigned view
- Candidate Bank (scoped to own captures)
- Pipeline Management
- Match History

### Candidate Features
- Dashboard with application status
- Browse Jobs
- Profile Management

### Chrome Extension (v3.9.1)
- Naukri profile capture with robust profile ID extraction
- Backend safety net for duplicate prevention

### AI Features
- AI Search: GPT-4o-mini translates natural language to structured DB queries
- AI JD Parser: Extracts job details from pasted/uploaded JDs
- AI Screening: Quick match + Full AI match modes
- AI Industry Detection: For bulk imported candidates

### Mobile & Tablet Responsiveness (Feb 2026)
- Hamburger menu with slide-out sidebar on mobile/tablet (< 1024px)
- Responsive stat card grids (2-col mobile, 4-col desktop)
- Responsive headings (text-xl → text-2xl → text-3xl)
- Candidate rows stack vertically on mobile with compact action buttons
- Dialog/modal mobile optimization with scrollable content
- Table horizontal scroll for data-heavy pages
- Tab lists with overflow-x-auto for mobile scrolling
- Responsive form layouts and button groups

## Prioritized Backlog

### P1 - Fix AI Screening Shortlist Bug
- "Shortlist" button disabled when JD is pasted/uploaded (no job_id available)

### P2 - External Password Reset
- "Forgot Password" flow for users

### P3 - Refactor content.js
- Chrome extension technical debt - break into smaller modules

### P3 - AI Search Phase 2
- Hybrid model routing (GPT-4o for complex prompts, GPT-4o-mini default)
- Configurable model selection

## Tech Stack
- React 18, Tailwind CSS, Shadcn/UI, Recharts
- FastAPI, PyMongo/Motor, fpdf2
- MongoDB Atlas
- OpenAI GPT-4o-mini (via emergentintegrations)

## Key Credentials
- Admin: admin@vhc.in / VhcAdmin@2024
- Employer: ajit@vhc.in / 12345678
- Recruiter: jatin@vhc.in / 12345678
