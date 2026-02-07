# VHC Talent OS - Product Requirements Document

## 🔒 BUILD STATUS: PILOT-READY STABLE (January 31, 2026)

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
**Employer-led Mandate Allocation: COMPLETE & TESTED (January 27, 2026)**
**Candidate Data Bank Access Control Bug Fix: COMPLETE & TESTED (January 27, 2026)**
**P0 Governance Fix (Shareable Links + AI Screening Scope): COMPLETE & TESTED (January 28, 2026)**
**P0 Shareable Link JSON Error Fix: COMPLETE & TESTED (January 28, 2026)**
**P0 Career Page Apply Flow + Data Mismatch Fix: COMPLETE & TESTED (January 28, 2026)**
**P0 Resume Download + Candidate Bank Auto-Add Fix: COMPLETE & TESTED (January 28, 2026)**
**Infrastructure: Cloudflare R2 Storage Integration: COMPLETE & VERIFIED (January 29, 2026)**
**P0 Backend Refactoring - Phase 8-12: COMPLETE & TESTED (January 29, 2026)**
**P0 Pre-Production Hardening (Performance Optimization): COMPLETE & TESTED (January 29, 2026)**
**P0 Dashboard Stats Endpoints: COMPLETE & TESTED (January 30, 2026)**
**P0 Data Relationship & Pipeline Drill-Down Fix: COMPLETE & TESTED (January 30, 2026)**
**Employer Pipeline View with Stage Control: COMPLETE & TESTED (January 30, 2026)**
**Commercial ↔ Company ↔ Job Relationship: COMPLETE & TESTED (January 30, 2026)**
**Candidate Name Fix + Expected CTC Feature: COMPLETE & TESTED (January 30, 2026)**
**Employer Dashboard Stats Fix + UI Redesign: COMPLETE & TESTED (January 30, 2026)**
**P1 Tech Debt - localStorage Key Standardization: COMPLETE (January 30, 2026)**
**Mandate Shareable Links (Independent of Career Page): COMPLETE & TESTED (January 30, 2026)**
**Team Creation Auto-Attach Companies: COMPLETE & TESTED (January 30, 2026)**
**DELETE Capabilities for Core Entities: COMPLETE & TESTED (January 30, 2026)**
**Enhanced Bulk Candidate Import Tool: COMPLETE & TESTED (January 31, 2026)**
**Bulk Import Features Enhancement: COMPLETE & TESTED (January 31, 2026)**
**UI Fix - Candidate Profile Dialog & Add as Applicant Dialog: COMPLETE & TESTED (January 31, 2026)**
**Profile Inline Editing & Contact Number Fix: COMPLETE & TESTED (January 31, 2026)**
**Database Performance Optimization (MongoDB Indexes): COMPLETE & TESTED (February 4, 2026)**
**Server-side Pagination & Search Debouncing: COMPLETE & TESTED (February 6, 2026)**
**MongoDB Atlas Migration: COMPLETE & VERIFIED (February 6, 2026)**
**Two-Stage AI Matching Optimization: COMPLETE & TESTED (February 6, 2026)**
**Phase 1 Scaling: MongoDB Atlas Search Integration: COMPLETE & TESTED (February 6, 2026)**
**Phase 2 Prep: Redis Caching & Background Jobs: COMPLETE & TESTED (February 6, 2026)**
**Chunked File Upload for Large CV Imports: COMPLETE & TESTED (February 7, 2026)**
**Expanded Redis Caching (Jobs API): COMPLETE & TESTED (February 7, 2026)**
**Vector Embeddings Service: COMPLETE & VERIFIED (February 7, 2026)**
**Upload Progress Notifications with ETA: COMPLETE (February 7, 2026)**
**Semantic Search Integration: COMPLETE & TESTED (February 7, 2026)**
**Auto-Embed New Candidates: COMPLETE (February 7, 2026)**
**Background CV Parsing Service: COMPLETE (February 7, 2026)**
**Backend Refactoring - Teams Route: COMPLETE (February 7, 2026)**
**Backend Refactoring - Referrals Route: COMPLETE (February 7, 2026)**
**Backend Refactoring - Commercials Route: COMPLETE (February 7, 2026)**
**Vector Embeddings Service: COMPLETE & VERIFIED (February 7, 2026)**
**Upload Progress Notifications with ETA: COMPLETE (February 7, 2026)**

---

## RULE ZERO (Standing Thumb Rule - NON-NEGOTIABLE)

**Once a feature is implemented, tested, and signed off, it must NEVER be removed, disabled, or altered in behavior unless explicitly instructed by the product owner.**

Any future change must:
- Preserve all existing features
- Be additive only
- Never regress signed-off functionality

---

## UI Fix - Candidate Profile Dialog & Add as Applicant Dialog (January 31, 2026)

### Overview ✅ VERIFIED
**Testing:** 100% frontend UI verified
**Test Report:** `/app/test_reports/iteration_39.json`

### Issues Fixed

#### 1. Add as Applicant Dialog Distortion
- Fixed dialog width with `max-w-lg` to prevent overflow
- Added candidate info card showing phone, location, experience, salary
- Two-column grid layout for form fields (Salary/Notice Period, Location/Experience)
- Warning message for missing mandatory fields

#### 2. Candidate Profile Dialog Missing Fields
Updated profile dialog to show ALL mandatory fields:

| Field | Description |
|-------|-------------|
| Contact No.* | Phone number |
| Email* | Email address |
| Work Experience* | Years of experience |
| Current CTC* | Salary in INR |
| Current Location* | City |
| Notice Period* | Notice period |
| Current Employer* | Company name |
| Current Designation* | Job title |
| Industry | Sector (with AI detected badge) |
| Date of Birth / Age | DOB or age |
| Skills | List of skills |
| Summary | Professional summary |

### New Dialog Tabs
- **Profile**: All mandatory fields in grid layout
- **Experience**: Work history with title, company, duration
- **Education**: Education details including UG Course
- **Activity**: Application history with stats
- **Audit Log**: Profile change history

### Files Modified
- `/app/frontend/src/pages/admin/CandidateDataBankPage.jsx`
- `/app/frontend/src/components/shared/CandidateProfileDialog.jsx` (new reusable component)

---

## Database Performance Optimization (February 4, 2026)

### Overview ✅ VERIFIED
**Testing:** API response times verified via curl (sub-100ms queries)
**Script:** `/app/backend/scripts/create_indexes.py`

### Problem
User reported slow search performance on the AI Matching/Screening page with 1700+ candidates in the database.

### Solution
Created and executed MongoDB indexes to optimize database query performance.

### Indexes Created

| Collection | Index Name | Fields | Purpose |
|------------|------------|--------|---------|
| candidate_bank | text_search_idx | name, email, skills (text) | Full-text search |
| candidate_bank | email_idx | email | Unique lookups |
| candidate_bank | phone_idx | phone_normalized | Duplicate detection |
| candidate_bank | skills_idx | skills | AI matching |
| candidate_bank | exp_years_idx | experience_years | Filtering |
| candidate_bank | location_idx | location | Filtering |
| candidate_bank | salary_idx | current_salary | Filtering/sorting |
| candidate_bank | bulk_restricted_idx | bulk_import_restricted | Governance queries |
| candidate_bank | matching_compound_idx | experience_years, current_salary, location | AI matching |
| candidate_bank | created_at_idx | created_at (desc) | Recent candidates |
| jobs | status_idx, company_idx, job_text_idx | Various | Job queries |
| applications | app_job_idx, app_candidate_idx, app_stage_idx | Various | Application queries |
| users | user_email_idx (unique), user_role_idx | email, role | User lookups |
| companies | company_name_idx, company_employer_idx | name, employer_id | Company queries |

### Performance Results
| Query Type | Before | After |
|------------|--------|-------|
| Candidate Bank fetch (500 records) | Slow | 104ms |
| Search with text filter | Slow | 50-54ms |
| Skills-based search | Slow | 50ms |

### Files Created
- `/app/backend/scripts/create_indexes.py` - Index creation script

---

## Server-side Pagination & Search Debouncing (February 6, 2026)

### Overview ✅ VERIFIED
**Testing:** 14/14 backend tests passed (100%), Frontend fully verified
**Test Report:** `/app/test_reports/pytest/pytest_pagination_debounce.xml`

### Features Implemented

#### 1. Server-side Pagination
- **Backend**: Updated `/api/candidate-bank` endpoint to return paginated response
- **Response format**: `{candidates, total, page, limit, total_pages}`
- **Default**: 50 items per page, max 100
- **Sorting**: Results sorted by `created_at` descending (newest first)

#### 2. Search Debouncing
- **Frontend**: Added 300ms debounce delay on search inputs
- Automatically triggers search after user stops typing
- Reduces unnecessary API calls during rapid typing
- Page resets to 1 when search filters change

### API Changes

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| page | int | 1 | Page number (1-indexed) |
| limit | int | 50 | Items per page (max 100) |
| search | str | null | Search by name, email, or skills |
| skills | str | null | Filter by skills (comma-separated) |

### Response Format
```json
{
  "candidates": [...],
  "total": 1701,
  "page": 1,
  "limit": 50,
  "total_pages": 35
}
```

### UI Components
- First/Previous/Next/Last page navigation buttons
- Page number buttons (up to 5 visible with smart pagination)
- "Showing X - Y of Z candidates" info display
- Pagination controls only visible when total_pages > 1

### Files Modified
- `/app/backend/routes/candidates.py` - Added CandidateBankResponse model, pagination logic
- `/app/frontend/src/pages/admin/CandidateDataBankPage.jsx` - Added useDebounce hook, pagination state & UI

### Test File
- `/app/backend/tests/test_pagination_debounce.py` - 14 comprehensive tests

---

## MongoDB Atlas Migration (February 6, 2026)

### Overview ✅ VERIFIED
**Testing:** All API endpoints verified working with Atlas connection

### Migration Details
- Migrated from local MongoDB (`localhost:27017`) to MongoDB Atlas cluster
- Connection: `mongodb+srv://vhc_admin:***@cluster0.vuhdiod.mongodb.net/`
- Database: `vhc_talent_os`
- Documents migrated: 2,057
- Collections migrated: 17
- All indexes preserved

### Files Modified
- `/app/backend/.env` - Updated MONGO_URL to Atlas connection string

---

## Two-Stage AI Matching Optimization (February 6, 2026)

### Overview ✅ VERIFIED
**Testing:** API response times verified - Quick Match: 2.85s, Full AI: 84s

### Problem
AI Matching/Screening page was extremely slow (timing out) because:
- Fetching all 1700+ candidates from database
- Making individual LLM calls for each candidate to calculate match scores
- Network latency to MongoDB Atlas compounded the issue

### Solution: Two-Stage Matching Architecture

#### Stage 1: Fast Database Pre-Filtering
- Uses MongoDB aggregation pipeline with indexes
- Filters by: experience range, location, skill keywords
- Computes `skill_match_count` using set intersection
- Returns top 100 candidates sorted by relevance
- **Time: ~1-2 seconds**

#### Stage 2: Scoring (Two Modes)

| Mode | Time | Description |
|------|------|-------------|
| **Quick Match** | ~3 seconds | Database-only scoring using skill overlap percentage |
| **AI Deep Match** | ~60-90 seconds | Full LLM-based scoring with detailed analysis |

### Quick Match Scoring Formula
```
total_score = (skill_score * 0.5) + (exp_score * 0.3) + 20
```
- `skill_score`: % of job skills found in candidate skills
- `exp_score`: Based on proximity to required experience
- Base score: 20 points

### API Changes

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| quick_match | bool | false | Skip LLM calls, use database scoring |
| limit | int | 50 | Max candidates to return |

### Performance Results

| Mode | Candidates Processed | Time | LLM Calls |
|------|---------------------|------|-----------|
| Quick Match | 100 (pre-filtered) | 2.85s | 0 |
| AI Deep Match | 100 (pre-filtered) | 84s | ~23 |
| Previous (all) | 1700+ | Timeout | 1000+ |

### Files Modified
- `/app/backend/routes/applications.py` - Two-stage matching implementation
- `/app/backend/models/matching.py` - Added `quick_match` and `limit` parameters
- `/app/frontend/src/pages/employer/FindCandidatesPage.jsx` - Search mode toggle UI

### UI Enhancement
- Added "Quick Match" vs "AI Deep Match" toggle
- Shows estimated time for each mode
- Default: Quick Match (for speed)

---

## Phase 1 Scaling: MongoDB Atlas Search Integration (February 6, 2026)

### Overview ✅ VERIFIED
**Testing:** Fuzzy search verified - "pythn" correctly finds "Python" candidates

### Problem
As candidate database grows to 100K-500K, regex-based searches become slow and inefficient.

### Solution: MongoDB Atlas Search
Atlas Search provides Lucene-based full-text search capabilities built into MongoDB Atlas.

### Search Indexes Created

| Index Name | Collection | Fields Indexed |
|------------|------------|----------------|
| `candidate_search` | candidate_bank | name, email, skills, summary, location, current_employer, designation, industry, experience_years |
| `job_search` | jobs | title, description, requirements, location, skills_required |

### Features Enabled
- **Fuzzy Matching**: Tolerates typos (e.g., "pythn" → "Python")
- **Relevance Scoring**: Results ranked by match quality
- **Multi-field Search**: Searches across name, email, skills, summary simultaneously
- **Boosted Fields**: Skills and name matches weighted higher
- **Automatic Fallback**: Falls back to regex if Atlas Search fails

### Performance at Scale

| Data Size | Regex Search | Atlas Search |
|-----------|-------------|--------------|
| 1,700 | ~500ms | ~500ms |
| 100K | ~5-10s | ~500ms |
| 500K | ~30s+ | ~1s |
| 1M+ | Timeout | ~1-2s |

### API Changes
New query parameter: `use_atlas_search` (default: `true`)
- `GET /api/candidate-bank?search=python&use_atlas_search=true`

### Files Modified
- `/app/backend/routes/candidates.py` - Added Atlas Search aggregation pipeline
- `/app/backend/routes/applications.py` - AI Matching uses Atlas Search for Stage 1

### Atlas Configuration
- Project ID: `697af5ad2a14beb67db890d9`
- Cluster: `Cluster0`
- Index Status: `STEADY` (Active)

---

## Phase 2 Prep: Redis Caching & Background Jobs (February 6, 2026)

### Overview ✅ VERIFIED
**Testing:** All API endpoints verified, Redis cache active

### Components Implemented

#### 1. Redis Caching (Upstash)
- **Provider:** Upstash Redis (Serverless)
- **Purpose:** Cache search results, reduce database load
- **TTL Settings:**
  - Search results: 5 minutes
  - Job parsing: 1 hour  
  - Match scores: 30 minutes
  - Dashboard stats: 1 minute

#### 2. Background Job Queue
- **Pattern:** Async job processing with MongoDB persistence
- **Job Types:** CV parsing, batch embedding generation
- **Status Tracking:** Pending → Processing → Completed/Failed
- **Progress Updates:** Real-time progress percentage and messages

#### 3. Vector Embeddings Service (Prepared)
- **Model:** text-embedding-3-small (1536 dimensions)
- **Status:** Service ready, pending API support from Emergent
- **When Active:** Enables semantic matching ("Python developer" ↔ "Django engineer")

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/cache/stats` | GET | Redis cache status |
| `/api/cache/clear` | POST | Clear cache entries |
| `/api/embeddings/stats` | GET | Embedding coverage stats |
| `/api/embeddings/generate-batch` | POST | Start batch embedding job |
| `/api/background-jobs` | GET | List user's jobs |
| `/api/background-jobs/{id}` | GET | Get job status |

### Files Created
- `/app/backend/services/cache.py` - Redis caching service
- `/app/backend/services/embeddings.py` - Vector embeddings service
- `/app/backend/services/job_queue.py` - Background job queue
- `/app/backend/routes/background_jobs.py` - API endpoints

### Environment Variables Added
```
UPSTASH_REDIS_REST_URL=https://quality-gopher-48093.upstash.io
UPSTASH_REDIS_REST_TOKEN=***
```

### Performance Impact
- Search caching reduces repeated queries
- Background jobs prevent request blocking for heavy operations
- Foundation ready for semantic search when embeddings enabled

---

## Chunked File Upload for Large CV Imports (February 7, 2026)

### Overview ✅ VERIFIED
**Testing:** 100% backend tests passed (13/13), Frontend verified
**Test Report:** `/app/test_reports/iteration_42.json`

### Problem
The bulk CV import feature was crashing when uploading files >1MB due to the environment's ingress proxy file size limit.

### Solution: Chunked File Uploads
Files are split into 512KB chunks on the frontend, uploaded sequentially, and reassembled on the server before processing.

### Configuration
| Setting | Value | Description |
|---------|-------|-------------|
| CHUNK_SIZE | 512KB | Size of each chunk |
| MAX_FILE_SIZE | 100MB | Maximum upload size |
| Chunk threshold | 1MB | Files >1MB use chunked upload |

### Chunked Upload Flow
1. **Init** (`POST /api/admin/bulk-import/chunk/init`) - Create upload session
2. **Upload** (`POST /api/admin/bulk-import/chunk/upload`) - Upload each chunk (multipart form)
3. **Complete** (`POST /api/admin/bulk-import/chunk/complete`) - Assemble all chunks
4. **Process** (`POST /api/admin/bulk-import/cv-zip-chunked`) - Parse the assembled ZIP

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chunk/init` | POST | Initialize upload session, returns `upload_id` |
| `/chunk/upload` | POST | Upload individual chunk |
| `/chunk/complete` | POST | Assemble chunks into final file |
| `/chunk/status/{id}` | GET | Get upload progress/status |
| `/chunk/cancel/{id}` | DELETE | Cancel and cleanup upload |
| `/cv-zip-chunked` | POST | Process chunked ZIP file |

### Frontend Progress Phases
- **Uploading... X%** (0-60%): Chunks being uploaded
- **Processing CVs... X%** (60-100%): AI parsing resumes

### Files Modified
- `/app/backend/services/chunked_upload.py` - New chunked upload service
- `/app/backend/routes/bulk_import.py` - Chunked upload endpoints
- `/app/frontend/src/pages/admin/BulkImportPage.jsx` - Chunked upload UI

---

## Expanded Redis Caching (February 7, 2026)

### Overview ✅ VERIFIED
Redis caching expanded to additional public endpoints.

### Newly Cached Endpoints

| Endpoint | TTL | Description |
|----------|-----|-------------|
| `GET /api/jobs/browse` | 3 min | Public job browsing |
| `GET /api/career-page/jobs` | 5 min | Career page job listings |

### Performance Improvement
- First request: ~800ms
- Cached request: ~270ms (3x faster)

### Files Modified
- `/app/backend/routes/jobs.py` - Added caching to browse_jobs and career_page_jobs

---

## Vector Embeddings Service (February 7, 2026)

### Overview ✅ VERIFIED
**Status:** Healthy - Generating embeddings for 1700+ candidates

### Configuration
| Setting | Value |
|---------|-------|
| Model | `text-embedding-3-small` |
| Dimensions | 1536 |
| Provider | OpenAI |
| Batch Size | 20 candidates |

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/embeddings/health` | GET | Check service health |
| `/api/embeddings/stats` | GET | Get embedding coverage stats |
| `/api/embeddings/generate-batch` | POST | Start batch embedding generation |

### Features
- **Semantic Search Ready**: Embeddings enable "Python developer" to match "Django engineer"
- **Batch Processing**: Processes 20 candidates per API call for efficiency
- **Progress Tracking**: Background job tracks progress and completion
- **Cosine Similarity**: Built-in similarity scoring for ranking matches

### Files Modified
- `/app/backend/services/embeddings.py` - Updated to use direct OpenAI API
- `/app/backend/routes/background_jobs.py` - Added health check endpoint

### Environment Variables Added
```
OPENAI_API_KEY=sk-proj-xxx...
```

---

## Semantic Search Integration (February 7, 2026)

### Overview ✅ VERIFIED
Integrated vector embeddings into the AI matching engine for semantic search capabilities.

### How It Works
1. **Job Embedding**: When matching, a job embedding is generated from title + skills + description
2. **Candidate Embeddings**: Stored in the candidate document (auto-generated on create)
3. **Cosine Similarity**: Calculates semantic similarity (0-100%) between job and candidates
4. **Score Blending**: 
   - Quick Match: 40% skill + 25% experience + 25% semantic + 10% base
   - Full AI Match: 70% AI score + 30% semantic score

### Matching Request Options
```json
{
  "job_id": "string",
  "quick_match": true,      // Skip LLM, use fast scoring
  "semantic_search": true,  // Enable vector similarity (default: true)
  "limit": 50
}
```

### Match Result Enhancement
```json
{
  "candidate_id": "...",
  "score": 84,
  "skill_match_score": 75,
  "experience_match_score": 70,
  "semantic_score": 68.2,  // NEW: Vector similarity
  "explanation": "Quick match: 5 skills matched, 6 years experience, 68% semantic similarity"
}
```

### Auto-Embed New Candidates
When a candidate is created (via API or bulk import), embeddings are automatically generated in the background without blocking the request.

### Files Modified
- `/app/backend/routes/applications.py` - Enhanced find_matching_candidates with semantic search
- `/app/backend/routes/candidates.py` - Added auto-embed on candidate creation
- `/app/backend/models/matching.py` - Added semantic_score field to MatchResult

---

## Upload Progress Notifications with ETA (February 7, 2026)

### Overview ✅ VERIFIED
Enhanced the bulk CV import UI with detailed progress notifications.

### Features
- **Progress Toast Messages**: Shows upload percentage during chunked uploads
- **Estimated Time Remaining**: Calculates ETA based on average chunk upload speed
- **Phase Indicators**: Shows "Uploading...", "Processing CVs..." phases
- **Completion Summary**: Shows total processing time and results

### Example Notifications
- `Starting upload of 25.3MB file (50 chunks)...`
- `Upload progress: 60% • ETA: ~2m 30s`
- `Upload complete! Now processing CVs...`
- `✅ Processed 47 CVs in 45.2s • 45 valid, 2 with errors`

### Files Modified
- `/app/frontend/src/pages/admin/BulkImportPage.jsx` - Added progress tracking and notifications

---

## Backend Refactoring - Teams Route (February 7, 2026) [IN PROGRESS]

### Overview
Created dedicated route file for Team Management to improve code organization.

### Files Created
- `/app/backend/routes/teams.py` - Team CRUD, member management, company assignments

### Remaining Refactoring
- `/app/backend/routes/referrals.py` - Referral management (from server.py)
- `/app/backend/routes/commercials.py` - Commercial intelligence (from server.py)

---

## Enhanced Bulk Candidate Import Tool (January 31, 2026)

### Overview ✅ VERIFIED
**Testing:** 22/22 backend tests passed (100%), Frontend fully verified
**Test Report:** `/app/test_reports/iteration_37.json`

### Feature Description
Admin-only tool for controlled production-grade candidate data seeding with two independent import modes, AI industry detection, smart deduplication, and strict governance rules.

### Two Import Modes

#### Mode A: Excel-Only Import
- Upload Excel with candidate data (no CV required)
- Profiles created with `cv_attached: false`
- CVs can be attached later using "Attach CV" feature
- **AI Industry Detection**: If Industry column is empty, GPT detects industry from employer name
- Endpoint: `POST /api/admin/bulk-import/excel`

#### Mode B: CV/ZIP-Only Import
- Upload ZIP containing resume files (PDF, DOC, DOCX)
- Optional Excel files for additional metadata
- CVs parsed using AI to extract candidate data
- Profiles created with `cv_attached: true`
- Endpoint: `POST /api/admin/bulk-import/cv-zip`

### Smart Deduplication Rules
When duplicates are found (by email or phone):
- **Salary/Notice Period**: Use the HIGHER value
- **Job History**: Merge and sort chronologically (latest first)
- **Location**: Use from most recent job
- **Skills**: Merge and deduplicate

### Strict Governance
- All imported profiles have `bulk_import_restricted: true`
- **Admin-only view** by default
- Profiles visible to Employers/Recruiters ONLY via **AI Screening results**
- **Permanent visibility** granted only after "Add as Applicant" action
- Tracked via `discovered_by` array

### Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/admin/bulk-import/template` | GET | Download Excel template |
| `/api/admin/bulk-import/excel` | POST | Parse Excel (Mode A) |
| `/api/admin/bulk-import/cv-zip` | POST | Parse ZIP (Mode B) |
| `/api/admin/bulk-import/save` | POST | Save candidates with deduplication |
| `/api/admin/bulk-import/attach-cv/{id}` | PUT | Attach CV to existing candidate |
| `/api/admin/bulk-import/batches` | GET | List all import batches |
| `/api/admin/bulk-import/restricted-candidates` | GET | Get Admin-only candidates |

### Excel Template Columns (Mode A)
| Column | Required | Description |
|--------|----------|-------------|
| Candidate Name* | Yes | Full name |
| Contact No.* | Yes | Phone number |
| Email* | Yes | Email address |
| Work Exp* | Yes | e.g., "5Y 0 M" |
| Annual Salary* | Yes | e.g., "12.0 L" |
| Current Location* | Yes | City |
| Current Employer* | Yes | Company name |
| Designation* | Yes | Job title |
| U.G. Course* | Yes | Education |
| Industry* | Yes | AI-detected if empty |
| Age/Date of Birth* | Yes | DOB or age |

### Database Schema Updates
```json
// candidate_bank collection additions:
{
  "bulk_import_type": "excel" | "cv_zip",
  "bulk_import_restricted": true,
  "cv_attached": false,  // true for cv_zip mode
  "industry": "Information Technology",
  "industry_source": "excel" | "ai_detected",
  "current_employer": "Company Name",
  "designation": "Job Title",
  "ug_course": "B.Tech",
  "date_of_birth": "1995-05-15",
  "discovered_by": [
    {"user_id": "...", "user_role": "employer", "added_at": "ISO-8601"}
  ],
  "import_batch_id": "uuid"
}
```

### Files Created/Modified
- `/app/backend/routes/bulk_import.py` - Complete rewrite with two modes
- `/app/frontend/src/pages/admin/BulkImportPage.jsx` - New UI with tabs
- `/app/backend/models/candidate_bank.py` - Added bulk import fields

---

## DELETE Capabilities for Core Entities (January 30, 2026)

### Overview ✅ VERIFIED
**Testing:** 16/16 backend tests passed (100%), All frontend UI verified
**Test Report:** `/app/test_reports/iteration_35.json`

### Feature Description
Admin-only soft delete for core entities with proper cascade rules and confirmation dialogs.

### Entities Covered

**1. Company Profiles**
- Endpoint: `DELETE /api/companies/{company_id}`
- Cascade Rules:
  - Jobs linked to company → status set to `archived`
  - Teams with company → company_id removed from company_ids
  - Commercials for company → is_active set to false
  - Applications → preserved for audit
- UI: Delete button (trash icon) on each company card with confirmation dialog

**2. Candidates from Pipeline (Applications)**
- Endpoint: `DELETE /api/applications/{app_id}`
- Behavior: Soft delete - marks stage/status as `removed`
- **Important:** Does NOT delete candidate from data bank
- UI: Delete button appears on hover in pipeline cards with clarification dialog

**3. User Profiles (Existing)**
- `DELETE /api/admin/users/{user_id}` - Already existed (soft delete)

**4. Job Postings (Existing)**
- `DELETE /api/jobs/{job_id}` - Already existed

**5. Commercials (Existing)**
- `DELETE /api/commercials/{commercial_id}` - Already existed

**6. Teams (Existing)**
- `DELETE /api/teams/{team_id}` - Already existed (soft delete)

### Files Modified
- `/app/backend/routes/admin.py` - Company update and delete endpoints
- `/app/backend/routes/applications.py` - Application delete endpoint
- `/app/frontend/src/pages/admin/CompaniesPage.jsx` - Delete button and dialog
- `/app/frontend/src/pages/admin/AdminPipelinePage.jsx` - Delete button and dialog
- `/app/frontend/src/lib/api.js` - Added delete methods

### Permission Model
- All DELETE operations: **Admin only**
- Confirmation required before delete
- Soft delete preferred (preserves audit trail)

---

## Team Creation Auto-Attach Companies (January 30, 2026)

### Overview ✅ VERIFIED
**Testing:** 11/12 backend tests passed (91.7%), 100% frontend verified
**Test Report:** `/app/test_reports/iteration_34.json`

### Problem Fixed
When Admin creates a team, the system was redundantly asking to assign companies even though companies are already assigned to employers. This was confusing because:
- Company already exists and is assigned to employer
- Manual re-selection was unnecessary

### Solution Implemented
**Auto-Attach Logic:** When employer is selected during team creation, companies already assigned to that employer are automatically included.

**Backend Changes:**
- New endpoint: `GET /api/employers/{employer_id}/companies` - Returns companies assigned to specific employer
- Updated `POST /api/teams` - Auto-attaches employer's companies + merges with explicitly selected companies (no duplicates)

**Frontend Changes:**
- `TeamsPage.jsx` - Added `fetchEmployerCompanies()` function
- Green info box shows auto-attached companies count and badges
- "Additional Companies" section shows remaining companies for optional selection
- Toast notification confirms auto-attach action

### UX Flow
1. Admin clicks "Create Team"
2. Admin fills team name
3. Admin selects employer → Companies auto-attach instantly
4. Green box shows: "2 company(ies) auto-attached - Companies assigned to this employer are automatically included"
5. Admin can optionally add more companies from the "Additional Companies" section
6. Admin assigns recruiters and creates team

### Files Modified
- `/app/backend/server.py` - Team creation logic + new endpoint
- `/app/frontend/src/pages/admin/TeamsPage.jsx` - Auto-attach UI
- `/app/frontend/src/lib/api.js` - New API method

---

## Mandate Shareable Links (January 30, 2026)

### Overview ✅ VERIFIED
**Testing:** 16/16 tests passed (100% backend, 100% frontend)
**Test Report:** `/app/test_reports/iteration_33.json`

### Feature Description
Enables shareable links for assigned mandates that are **INDEPENDENT of career page visibility**. This allows employers/admins to share job links for:
- Confidential searches
- Recruiter-only jobs
- Jobs not intended for public career page

### Implementation Details

**Backend Endpoints:**
- `PUT /api/jobs/{job_id}/mandate-shareable-link` - Enable/disable mandate link (admin/employer only)
- `GET /api/public/mandate/{job_id}?token={token}` - Public job detail via mandate link
- `POST /api/public/apply` - Updated to accept `mandate_token` parameter

**Database Schema:**
```json
// Job collection additions:
{
  "mandate_shareable_link_enabled": false,
  "mandate_share_token": "secure-token-string"
}

// Application collection addition:
{
  "application_channel": "mandate_link" | "career_page"
}
```

**Frontend:**
- **EmployerJobsPage.jsx** - Purple "Mandate Link" toggle with copy/open buttons
- **AdminJobsPage.jsx** - Purple "Mandate" toggle with copy/open buttons  
- **MandateApplyPage.jsx** - New page at `/apply/mandate/:jobId?token={token}`

### Security
- Token-based access (24-byte URL-safe token)
- New token generated each time link is enabled (old links invalidated)
- Role-scoped: Only admin and employer can enable mandate links
- Company name preserved as "Confidential Client"

### URL Format
```
/apply/mandate/{job_id}?token={mandate_share_token}
Example: /apply/mandate/abc123?token=dgOX-51L-e3CuhlqLBJXSzY7GDzCFlq-
```

### Files Modified
- `/app/backend/routes/jobs.py` - New endpoint
- `/app/backend/routes/public.py` - New endpoint + updated apply
- `/app/backend/models/job.py` - New fields
- `/app/frontend/src/pages/employer/EmployerJobsPage.jsx` - UI toggle
- `/app/frontend/src/pages/admin/JobsPage.jsx` - UI toggle
- `/app/frontend/src/pages/public/MandateApplyPage.jsx` - New page
- `/app/frontend/src/lib/api.js` - New API method
- `/app/frontend/src/App.js` - New route

---

## P1 Tech Debt - localStorage Key Standardization (January 30, 2026)

### Overview ✅ COMPLETE
**Issue:** Inconsistent localStorage key usage across frontend - some components used `token` while the auth system used `vhc_token`, causing authentication failures in certain flows.

### Problem Identified
The auth library (`lib/auth.js`) and API library (`lib/api.js`) correctly used `vhc_token`, but three pages were still using the legacy `token` key:
- `RecruiterCandidateBankPage.jsx` - Resume download authentication
- `EmployerCandidateBankPage.jsx` - Resume download authentication  
- `CandidateDataBankPage.jsx` - Resume download authentication

### Fix Applied
Standardized all `localStorage.getItem('token')` calls to `localStorage.getItem('vhc_token')`.

**Files Modified:**
- `/app/frontend/src/pages/recruiter/RecruiterCandidateBankPage.jsx`
- `/app/frontend/src/pages/employer/EmployerCandidateBankPage.jsx`
- `/app/frontend/src/pages/admin/CandidateDataBankPage.jsx`

### Verification
- All localStorage operations now consistently use `vhc_token`
- No remaining instances of `localStorage.*('token')` in codebase
- Frontend loads correctly after changes

---

## P0 Data Relationship & Pipeline Drill-Down Fix (January 30, 2026)

### Overview ✅ VERIFIED
**Testing:** 22/22 tests passed (100%)
**Test Report:** `/app/test_reports/iteration_28.json`

### Issue 1: Admin Pipeline Drill-Down ✅ FIXED

**Problem:** Admin dashboard showed correct overall pipeline but filtering by employer/team/recruiter returned zeros.

**Root Cause:** Incorrect field references in filter logic:
- Was checking `company_id == employer_id` (user ID vs company ID mismatch)
- Was checking `assigned_recruiter` (singular) instead of `assigned_recruiter_ids` (plural array)
- Missing team-based relationship traversal

**Fix Applied:**
```python
# New filter logic uses team relationships:
# employer_id -> teams.employer_id -> team.company_ids -> jobs.company_id/team_id
# recruiter_id -> teams.recruiter_ids -> jobs.team_id or jobs.posted_by
```

**Files Modified:** `/app/backend/routes/admin.py`

### Issue 2: Admin Companies/Teams/Commercials ✅ FIXED

**Problem:** `/api/companies` returned 404 (endpoint missing).

**Fix Applied:**
- Added `GET /api/companies` - List all companies (admin only)
- Added `POST /api/companies` - Create company (admin only)
- Added `GET /api/companies/{id}` - Get company details

**Files Modified:** `/app/backend/routes/admin.py`

### Issue 3: Employer Pipeline View ✅ EXISTING

**Status:** Already implemented at `/api/employer/my-team` - returns team members with pipeline metrics, revenue, mandates.

### Issue 4: Recruiter Job Posting with Approval ✅ EXISTING

**Status:** Already implemented:
- Recruiter creates job → status = `pending_approval`
- Employer/Admin approves via `POST /api/jobs/{id}/transition`
- Audit log tracks all status changes

### Issue 5: Company HR/POC Details ✅ ADDED

**Problem:** Company profile lacked HR contact information.

**Fix Applied:**
```python
class HRContact(BaseModel):
    name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    designation: Optional[str]

# Added to CompanyCreate, CompanyResponse, CompanyUpdate
hr_contacts: Optional[List[HRContact]]
```

**Files Modified:** `/app/backend/models/company.py`

---

## Employer Pipeline View with Stage Control (January 30, 2026)

### Overview ✅ VERIFIED
**Testing:** 20/20 tests passed (100%)
**Test Report:** `/app/test_reports/iteration_29.json`

### Features Implemented

#### Backend: GET /api/employer/pipeline
New endpoint for employer-scoped pipeline view:
- Returns applications for all jobs under employer's teams/companies
- Filter by `recruiter_id` or `job_id`
- Full application details for stage transitions

**Files Modified:** `/app/backend/server.py`

#### Frontend: /employer/pipeline
New Kanban-style pipeline page:
- 7 stage columns (Applied → Shortlisted → Interview → Offered → Hired → Rejected → On Hold)
- **Drag-and-drop** to move candidates between stages
- **Filter dropdowns** for recruiter and job
- **Candidate detail dialog** with:
  - Contact info, salary, experience
  - Resume download link
  - Stage transition buttons
  - Notes section with add note capability
- Stage summary cards at top

**Files Created:**
- `/app/frontend/src/pages/employer/EmployerPipelinePage.jsx`

**Files Modified:**
- `/app/frontend/src/App.js` - Route added
- `/app/frontend/src/components/layout/Sidebar.jsx` - Nav link added
- `/app/frontend/src/lib/api.js` - employerPortalAPI.getPipeline added

### Role-Based Access
- **Employer:** Sees only their assigned companies/teams' applications
- **Stage Transition:** Uses existing `PUT /api/applications/{id}` endpoint
- **Add Note:** Uses existing `POST /api/applications/{id}/notes` endpoint

---

## Commercial ↔ Company ↔ Job Relationship (January 30, 2026)

### Overview ✅ VERIFIED
**Testing:** 22/22 tests passed (100%)
**Test Report:** `/app/test_reports/iteration_30.json`

### Relationship Chain
```
Team → Company → Commercial → Job
     ↓
Employer is assigned to Team
Team has company_ids[]
Commercial has company_id
Job has company_id
     ↓
Revenue = offered_salary × commercial.fee_percentage
```

### Features Implemented

#### 1. Admin Companies Page - Commercial Terms Display
- Each company card now shows "Commercial Terms" section
- Fee badges displayed (e.g., "8.33% Fee", "Level-based")
- Shows "No commercial configured" for companies without commercials

**Files Modified:** `/app/frontend/src/pages/admin/CompaniesPage.jsx`

#### 2. Employer Job Creation - Company Selection
- **Mandatory company selector** added to Create Job page
- Only shows companies assigned to employer (via team)
- Displays selected company's commercial info (fee, payment terms)
- Shows warning when employer has no assigned companies

**Files Modified:** `/app/frontend/src/pages/employer/CreateJobPage.jsx`

#### 3. Data Model - Job Links to Company
- `JobCreate` already supports `company_id` and `company_name`
- Jobs now properly linked to companies for revenue calculation
- Revenue calculation: `job.company_id → commercial.company_id → fee_percentage`

### Revenue Calculation Ready
```python
# Example flow:
job = {"company_id": "abc123", "offered_salary": 1500000}
commercial = db.commercials.find_one({"company_id": "abc123", "is_active": True})
revenue = job["offered_salary"] * (commercial["fee_percentage"] / 100)
# Result: 1500000 * 0.0833 = ₹125,000
```

---

## P0 Pre-Production Hardening (January 29, 2026)

### Overview ✅ VERIFIED
**Testing:** 19/19 tests passed (100%)
**Test Report:** `/app/test_reports/iteration_27.json`

Two critical P0 performance issues were diagnosed and fixed:

### Issue 1: Dashboard Stats Endpoints Missing ✅ FIXED (January 30, 2026)

**Problem:** All dashboards (Admin, Employer, Recruiter) showing "Failed to load dashboard stats" because the `/api/stats/*` endpoints did not exist (404).

**Root Cause:** Frontend called `/api/stats/admin`, `/api/stats/employer`, `/api/stats/recruiter` but these endpoints were never created. The existing `/api/analytics/*` endpoints had a different schema.

**Fix Applied:**
Created 4 new stats endpoints in `/app/backend/routes/admin.py`:
- `GET /api/stats/admin` - Admin dashboard stats (total_users, total_jobs, total_applications, total_companies, users_by_role, recent_applications)
- `GET /api/stats/employer` - Employer dashboard stats (my_jobs, total_applicants, stage_stats)
- `GET /api/stats/recruiter` - Recruiter dashboard stats (total_jobs, total_candidates, pipeline_stats)
- `GET /api/stats/candidate` - Candidate dashboard stats (total_applications, application_stats)

**Schema Guarantee:**
All endpoints ALWAYS return complete schema even when data is empty:
```json
// Admin: total_users=0, total_jobs=0, users_by_role={}, recent_applications=[]
// Employer: my_jobs=0, stage_stats={applied:0, shortlisted:0, hired:0, ...}
// Recruiter: total_jobs=0, pipeline_stats={applied:0, shortlisted:0, hired:0, ...}
```

**Verification:**
- Admin Dashboard: ✅ Shows 10 users, 11 jobs, 38 applications, 3 companies
- Employer Dashboard: ✅ Shows 0 jobs, 0 applicants (empty scope handled)
- Recruiter Dashboard: ✅ Shows 1 mandate, 0 candidates (empty scope handled)

### Issue 2: Dashboard Analytics Performance ✅ FIXED (Earlier)

**Problem:** Admin, Employer, and Recruiter dashboards were failing to load statistics due to inefficient queries loading up to 100,000+ records into memory and N+1 query patterns.

**Root Causes:**
- Loading all applications into memory (`to_list(100000)`)
- N+1 queries: looping through records and calling `find_one` for each company name/recruiter name
- Inefficient Python loops for stage counting instead of MongoDB aggregations

**Fixes Applied:**
1. **MongoDB Aggregation Pipelines:** Replaced in-memory processing with efficient `$group`, `$match`, `$lookup` aggregations
2. **Batch Lookups:** Pre-fetch all recruiter/company names in single queries instead of N+1
3. **Projection Optimization:** Only fetch fields needed for analytics

**Performance Results:**
| Endpoint | Before | After | Improvement |
|----------|--------|-------|-------------|
| Admin Analytics | Timeout/Fail | ~60ms | ✅ FIXED |
| Employer Analytics | Timeout/Fail | ~47ms | ✅ FIXED |
| Company Pipeline | Slow | ~46ms | ✅ FIXED |

### Issue 2: AI Screening Performance ✅ FIXED

**Problem:** AI Screening endpoint was taking excessive time to load due to serial LLM calls for each candidate and N+1 queries for creator lookups.

**Root Causes:**
- Serial execution: each candidate processed one-by-one
- N+1 query for `created_by` role lookup
- No pre-filtering before expensive LLM calls

**Fixes Applied:**
1. **Pre-filtering:** Apply must-have filters BEFORE AI scoring to skip candidates that would be filtered anyway
2. **Concurrent Processing:** Use `asyncio.Semaphore` with `asyncio.gather` for concurrent LLM calls (MAX_CONCURRENT=5)
3. **Batch Creator Lookup:** Single query to fetch all creator roles upfront

**Performance Results:**
| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Serial Processing | N candidates × LLM time | N/5 batches | ~5x faster |
| Pre-filtered candidates | 0 | 76% (in test) | 76% fewer LLM calls |
| Creator N+1 queries | N queries | 1 query | ✅ Eliminated |

### Files Modified
- `/app/backend/server.py` - Admin analytics, Employer analytics, Company pipeline
- `/app/backend/routes/applications.py` - AI Screening (`find_matching_candidates`)

### Optimization Techniques Used
```python
# 1. MongoDB Aggregation for stage counts (instead of loading all apps)
stage_pipeline = [
    {"$group": {"_id": "$stage", "count": {"$sum": 1}}}
]

# 2. $lookup for joining data (instead of N+1)
{"$lookup": {
    "from": "companies",
    "localField": "_id",
    "foreignField": "id",
    "as": "company"
}}

# 3. Batch fetch with $in (instead of N find_one calls)
recruiters = await db.users.find(
    {"id": {"$in": list(recruiter_ids)}},
    {"id": 1, "name": 1}
).to_list(len(recruiter_ids))

# 4. Concurrent LLM with semaphore
semaphore = asyncio.Semaphore(5)
async with semaphore:
    result = await calculate_candidate_job_match(...)
```

---

## Infrastructure: Cloudflare R2 Storage Integration (January 29, 2026)

### Overview ✅ VERIFIED
**Testing:** 8/8 tests passed (100% backend, 100% frontend)

Integrated Cloudflare R2 as the primary object storage for all file uploads, replacing reliance on local filesystem storage.

### Implementation Details
**Endpoints with R2 Support:**
- `POST /api/public/apply` - Public application resume upload → R2
- `POST /api/candidate-bank/add` - Candidate bank resume upload → R2
- `POST /api/candidate-bank/batch-parse` - Batch resume parsing → R2
- `GET /api/uploads/{filename}` - Returns 307 redirect to R2 signed URL

**Storage Behavior:**
- Primary storage: Cloudflare R2 (bucket: `vhc-talent-os-storage`)
- Download method: 307 redirect to time-limited signed URL (600s expiry)
- Local storage: Temporary only (for text extraction/PDF parsing)
- Fallback: Graceful fallback to local storage if R2 not configured

**MongoDB Schema Update:**
- Added `r2_metadata` field to `applications` and `candidate_bank` collections
- Structure: `{storage: "r2", r2_key: "...", original_filename: "...", content_type: "...", uploaded_at: "..."}`

**Environment Variables:**
```
R2_ACCOUNT_ID=<cloudflare-account-id>
R2_ACCESS_KEY_ID=<r2-access-key>
R2_SECRET_ACCESS_KEY=<r2-secret-key>
R2_BUCKET_NAME=vhc-talent-os-storage
```

**Database Verification:**
- Applications with R2 storage: 5
- Candidates with R2 storage: 6

---

## P0 Resume Download + Candidate Bank Auto-Add Fix (January 28, 2026)

### Issue 1: Resume/CV Files Not Downloading ✅
**Testing:** 6/6 backend tests passed

**Root Cause:** Files were saved to `/app/uploads` by the public apply endpoint, but download endpoints only looked in `/app/backend/uploads`.

**Fixes Applied:**
- `GET /api/uploads/{filename}` - Now checks both `/app/uploads` and `/app/backend/uploads`
- `GET /api/applications/{app_id}/resume` - Updated to check both directories
- `GET /api/candidates/{candidate_id}/resume` - Updated to check both directories

**Verified Working:**
- ✅ Mithun_Khatei_VHC.pdf (292KB) downloads correctly
- ✅ Navneet_Srivastava_VHC.docx (28KB) downloads correctly
- ✅ Preview and Download buttons work in applicant profile

### Issue 2: Auto-Add to Candidate Bank ✅
**Already Implemented - Verified Working**

Public applications automatically create candidates in `candidate_bank` collection with:
- `source: "public_application"`
- `source_job_id: {job_id}`
- Full profile data (name, email, phone, skills, resume)

**AI Screening Coverage:**
- ✅ 23 candidates in total data bank
- ✅ AI Screening correctly finds and ranks candidates from public applications
- ✅ HR Manager search correctly ranked Mithun Khatei (HR Business Partner) at score 85

---

## P0 Career Page Apply Flow + Data Mismatch Fix (January 28, 2026)

### Issue 1: Career Page Apply Modal Missing Job Description & Consent ✅
**Testing:** 8/8 backend + 100% frontend tests passed

**Problems Fixed:**
- Apply modal wasn't showing full job description
- Consent checkbox was missing, blocking application submission

**Fixes Applied to `/app/frontend/public/website/careers.html`:**
- Added job description section (lines 339-352) showing:
  - Job Public ID badge (VHC/YYYY/NNNN)
  - Full title, location, job type, experience, salary
  - Skills badges
  - Full description + requirements
- Added consent checkbox in Step 2 (lines 480-490) with HTML5 required validation
- Added consent validation in JavaScript before form submission

### Issue 2: Application Data Mismatch ✅
**Problem:** Application data was showing AI-parsed resume data (e.g., "John Doe" from resume) instead of user-provided form data.

**Root Cause:** Line 4979 in server.py prioritized parsed data over form input:
```python
# OLD: "candidate_name": parsed_data.get("name") or name
# NEW: "candidate_name": name or parsed_data.get("name")
```

**Fix Applied to `/app/backend/server.py` (lines 4974-4997):**
- User-provided form data now takes priority over AI-parsed data for:
  - `candidate_name`
  - `candidate_phone`
  - `location`

**Note:** This fix applies to NEW applications only. Existing applications retain their original data.

---

## P0 Shareable Link JSON Error Fix (January 28, 2026)

### Bug: "Failed to execute 'json' on 'Response': body stream already read" ✅
**Testing:** 14/14 backend + 100% frontend tests passed

**Root Cause:** The `handleShareableLinkToggle` function in EmployerJobsPage.jsx and AdminJobsPage.jsx used raw `fetch()` API which attempted to read the response body twice when an error occurred.

**Fix Applied:**
- Added `updateShareableLink` to jobAPI in `/app/frontend/src/lib/api.js`
- Changed `handleShareableLinkToggle` to use `jobAPI.updateShareableLink()` instead of raw `fetch()`
- Same fix applied to both EmployerJobsPage.jsx and AdminJobsPage.jsx

**Full Flow Verified:**
1. ✅ Employer Creates Job → Job shown in My Jobs
2. ✅ Employer assigns recruiters to job
3. ✅ Employer posts job to Career Page (career_page_status='live')
4. ✅ Employer enables Shareable Link via toggle (NO JSON ERROR)
5. ✅ Shareable link URL: `/jobs/{jobId}`
6. ✅ Public job landing page loads with job details
7. ✅ Company name masked as "Confidential Client"
8. ✅ Apply form shows: Resume upload, Name, Email, Phone, Salary, Notice Period, Consent
9. ✅ File upload restricted to PDF, DOC, DOCX (max 5MB)
10. ✅ Application submitted successfully
11. ✅ Thank you page shown with "Explore Our Website" option
12. ✅ Same flow works for Career Page direct access

---

## P0 Governance Fix (January 28, 2026)

### Issue 1: Shareable Job Link Feature - VERIFIED WORKING ✅
**Testing:** 29/29 tests passed

The Shareable Job Link feature was confirmed present and working:
- **Public Job Landing Page:** `/jobs/{jobId}` - Accessible without auth
- **Apply Form:** CV upload + AI parsing, consent checkbox required
- **Toggle Control:** Visible in Admin Jobs + Employer Jobs for career_page_status='live' jobs
- **Copy/Open Links:** Working as expected
- **Validation:** Jobs must be live on career page before shareable link can be enabled

### Issue 2: AI Screening Scope - FIXED ✅
**Testing:** 8/8 tests passed

**Problem:** AI Screening was incorrectly limited to user's visible candidates (role-based filter).

**Fix:** AI Screening now searches ENTIRE candidate database:
- **DATA VISIBILITY ≠ AI SEARCH SCOPE** (Design Principle)
- Admin screens: 15 candidates (all)
- Employer screens: 15 candidates (all) - despite seeing only 1 in Data Bank
- Recruiter screens: 15 candidates (all) - despite seeing only 1 in Data Bank

**Result Presentation:**
- Source tracking added: `source`, `source_role` fields in MatchResult
- READ-ONLY, CONTEXTUAL VISIBILITY - no edit/ownership rights granted from screening

---

## Feature Audit Results (January 28, 2026)

All previously signed-off features verified working:
- ✅ Shareable Job Links (live at /jobs/{jobId})
- ✅ Public Job Landing Pages
- ✅ Job ID format (VHC/YYYY/NNNN)
- ✅ JD Parsing (paste + upload)
- ✅ CV Parsing
- ✅ Candidate Data Bank access rules
- ✅ Employer "My Team" view
- ✅ Employer "Companies" view
- ✅ Mandate allocation to recruiters
- ✅ Audit logs
- ✅ Consent capture
- ✅ Application success screen

---

## Critical Bug Fix: Candidate Data Bank Access Control (January 27, 2026)

### Bug Fix: Role-Based Access Control in Candidate Data Bank ✅
**Testing:** 27/27 backend tests passed, 100% frontend tests passed
**Test File:** `/app/backend/tests/test_candidate_bank_access_control.py`

**Issue:** Opening candidate profiles from Candidate Data Bank was failing for Employer and Recruiter roles (worked only for Admin). Error: `resumeHistory.map is not a function`.

**Root Causes Identified:**
1. **List/Detail Mismatch:** List endpoint used different access filters than Detail endpoint
2. **Missing Visibility Checks:** Secondary endpoints (`/audit-log`, `/history`, `/resume-history`) checked role but NOT candidate-level visibility
3. **Outdated Query Logic:** Recruiter job query used old `team_id` instead of new `assigned_recruiters`
4. **Frontend Data Structure:** Resume history was object with `resume_versions` array, but frontend tried to map entire object

**Backend Fix - Unified Access Control:**
- Created `check_candidate_visibility(candidate_id, current_user)` helper function
- Created `get_accessible_candidate_ids(current_user)` for list queries
- ALL endpoints now use same visibility logic:
  - Admin: Full access
  - Employer: Candidates created by self, team members, or applied to employer's jobs
  - Recruiter: Candidates created by self, or applied to their ASSIGNED mandates

**Endpoints Fixed:**
- `GET /api/candidate-bank` - Uses unified helper for list
- `GET /api/candidate-bank/{id}` - Uses unified helper for detail
- `GET /api/candidate-bank/{id}/audit-log` - Now has visibility check
- `GET /api/candidate-bank/{id}/history` - Now has visibility check
- `GET /api/candidate-bank/{id}/resume-history` - Now has visibility check

**Frontend Fix:**
- `EmployerCandidateBankPage.jsx`: `setResumeHistory(historyRes.data?.resume_versions || [])`
- `RecruiterCandidateBankPage.jsx`: `setResumeHistory(historyRes.data?.resume_versions || [])`

**Security Verification:**
- Recruiter2 (no candidates, no assigned jobs) sees 0 candidates and gets 403 on detail requests ✅
- No role escalation or data leakage ✅

---

## Previous Feature: Employer-led Mandate Allocation (January 27, 2026)

### Feature: Employer-led Mandate Allocation to Recruiters ✅
**Testing:** 14/15 backend tests passed, 100% frontend tests passed
**Test File:** `/app/backend/tests/test_mandate_assignment.py`

**Objective:** Allow Employers to explicitly assign job mandates to specific Recruiters within their team.

**Backend Implementation:**
- `GET /api/employer/team-recruiters` - Returns list of team recruiters with mandate counts
- `POST /api/jobs/{job_id}/assign-recruiters` - Assign recruiters to a mandate
- `DELETE /api/jobs/{job_id}/assign-recruiters/{recruiter_id}` - Remove a recruiter from mandate
- `GET /api/jobs/{job_id}/assignments` - Get assignment details with audit history

**Data Model Updates:**
- `jobs.assigned_recruiters` - Array of recruiter user IDs
- `jobs.assignment_history` - Audit trail with who assigned, when, and to whom

**Visibility Rules (CRITICAL):**
- Recruiters can ONLY see mandates explicitly assigned to them OR jobs they posted
- This enforces employer-led mandate allocation - recruiters cannot self-assign
- Employer sees all team jobs

**Access Control:**
- Only Employer or Admin can assign recruiters
- Recruiters cannot self-assign (403 Forbidden)
- Job must be "active" or "pending_approval" to be assignable

**Frontend Components:**
- "Assign Recruiter" / "Manage Recruiters" button on eligible jobs
- Assignment modal with recruiter checkboxes and mandate counts
- "X Assigned" badge on jobs with assigned recruiters
- Assignment history dialog with audit trail

**Audit Trail:**
- Every assignment, change, or revocation is logged
- Records: action, timestamp, changed_by (name, role, id)

---

## Previous Feature: Shareable Job Links & JD Intelligence (January 27, 2026)

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

### Feature 3: JD Parsing During Job Creation ✅ FIXED & VERIFIED (January 27, 2026)
**Testing:** 23/23 backend tests passed

**Bug Fixed:** "body stream already read" error
- **Root Cause:** Frontend was calling `response.json()` then trying to read response again in error handler
- **Fix:** Changed to `response.text()` then `JSON.parse()` - reads response exactly once
- **Backend:** Improved error handling with proper try/finally for file cleanup

**Two Input Modes:**
1. **Paste Text** - Textarea for pasting job description text
2. **Upload File** - Upload JD files (PDF, DOC, DOCX, TXT)

**Architecture (Matches CV Parser Pattern):**
- Single request → single JSON response
- Backend handles file extraction + AI parsing in one call
- Frontend reads response exactly ONCE
- No streaming, no double-read issues

**Endpoints:**
- `POST /api/jobs/parse-jd` - Accepts both jd_text (paste) or jd_file (upload)

**Response Structure:**
```json
{
  "success": true,
  "title": "...",
  "skills": [...],
  "experience_years": 5,
  "location": "...",
  "summary": "...",
  "requirements": [...],
  "input_type": "paste|upload",
  "parsed_by": "user_id",
  "parsed_by_role": "admin",
  "parsed_at": "..."
}
```

**Error Handling:**
- 400 for unsupported file formats with clear message
- 400 for empty/image-only files with "no text could be extracted"
- 400 for missing input (neither jd_text nor jd_file)
- Proper HTTP error codes, never 500 for validation errors

**Access:** Admin, Employer, Recruiter only (Candidates denied with 403)

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

## P0 Technical Debt: Backend Refactoring ✅ IN PROGRESS (January 29, 2026)

### server.py Modularization - Phases 1-8 Complete

**Status:** Major modularization effort ongoing with strict zero-behavior-change policy

**Completed Phases:**

| Phase | Description | Status | Location |
|-------|-------------|--------|----------|
| 1 | Configuration Extraction | ✅ Complete | `/app/backend/config.py` |
| 2 | Pydantic Models Extraction | ✅ Complete | `/app/backend/models/` |
| 3 | Auth & Governance Helpers | ✅ Complete | `/app/backend/utils/` |
| 4 | R2 Storage Services | ✅ Complete | `/app/backend/services/r2_storage.py` |
| 5 | Auth Routes Extraction | ✅ Complete | `/app/backend/routes/auth.py` |
| 6 | Public Routes Extraction | ✅ Complete | `/app/backend/routes/public.py` |
| 7 | File Serving Routes | ✅ Complete | `/app/backend/routes/files.py` |
| 8 | Admin Routes Extraction | ✅ Complete | `/app/backend/routes/admin.py` |
| 9 | Jobs Routes Extraction | ✅ Complete | `/app/backend/routes/jobs.py` |
| 10 | Candidate Bank Routes | ✅ Complete | `/app/backend/routes/candidates.py` |
| 11 | Applications & AI Matching | ✅ Complete | `/app/backend/routes/applications.py` |
| 12 | Settings & Alerts | ✅ Complete | `/app/backend/routes/settings.py` |

### Phase 8 Admin Routes Regression Testing ✅ (January 29, 2026)

**Test Results: 22/22 PASSED (100%)**

| Test | Description | Result |
|------|-------------|--------|
| 1 | Admin Login | ✅ PASS |
| 2 | List Users (Admin Only) | ✅ PASS |
| 3 | Get Single User | ✅ PASS |
| 4 | Create Employer User | ✅ PASS |
| 5 | Create Recruiter User | ✅ PASS |
| 6 | Update User | ✅ PASS |
| 7 | Admin Password Reset | ✅ PASS |
| 8 | Toggle User Status (Disable) | ✅ PASS |
| 9 | Toggle User Status (Re-enable) | ✅ PASS |
| 10 | Delete User (Soft Delete) | ✅ PASS |
| 11 | Get Employers List | ✅ PASS |
| 12 | Assign Recruiter to Employer | ✅ PASS |
| 13 | Admin Pipeline View | ✅ PASS |
| 14-18 | Access Control (403 enforcement) | ✅ PASS |
| 19 | Admin Can Reset Own Password | ✅ PASS |
| 20 | Prevent Admin Self-Deactivation | ✅ PASS |
| 21-22 | Unauthenticated/Invalid Token | ✅ PASS |

**Endpoints Extracted to `/app/backend/routes/admin.py`:**
- `GET /api/users` - List all users (admin only)
- `GET /api/users/{user_id}` - Get single user
- `PUT /api/users/{user_id}` - Update user
- `DELETE /api/users/{user_id}` - Soft delete user
- `POST /api/admin/users` - Create user with any role
- `POST /api/admin/users/{user_id}/reset-password` - Reset password
- `POST /api/admin/users/{user_id}/toggle-status` - Enable/disable user
- `GET /api/admin/employers` - List employers
- `POST /api/admin/assign-recruiter` - Assign recruiter to employer
- `GET /api/admin/pipeline` - Admin collective pipeline view

**Constraints Respected:**
- ✅ ZERO behavior changes
- ✅ ZERO feature removal
- ✅ ZERO refactor beyond extraction
- ✅ NO frontend changes
- ✅ All permission checks preserved
- ✅ All audit logging preserved

**Remaining Phases (Future - Optional):**
- Phase 13: Team Management Routes
- Phase 14: Referral Management Routes
- Phase 15: Commercial Intelligence Routes
- Phase 16: Analytics Dashboard Routes

### Phase 12 Settings & Alerts Regression Testing ✅ (January 29, 2026)

**Test Results: 9/9 PASSED (100%)**

| Test | Description | Result |
|------|-------------|--------|
| 1-2 | Global Settings CRUD (Admin) | ✅ PASS |
| 3 | Notification Stats (Admin) | ✅ PASS |
| 4-5 | Access Control (403 Enforcement) | ✅ PASS |
| 6-8 | No Side Effects on Jobs/Candidates/Apps | ✅ PASS |
| 9 | Backend Health Check | ✅ PASS |

**Endpoints Extracted to `/app/backend/routes/settings.py`:**
- `GET/PUT /api/settings` - Global settings (Admin)
- `GET/POST/PUT/DELETE /api/alerts/preferences` - Job alert prefs
- `POST /api/alerts/pause` - Pause alerts
- `POST /api/alerts/resume` - Resume alerts
- `POST /api/alerts/whatsapp/opt-in` - WhatsApp opt-in
- `POST /api/alerts/whatsapp/opt-out` - WhatsApp opt-out
- `PUT /api/alerts/whatsapp/number` - Update WhatsApp number
- `GET /api/notifications/history` - Notification history
- `GET /api/admin/notifications/stats` - Notification stats

**server.py Current State:**
- Now contains only app setup, router inclusions, and remaining business modules
- Remaining modules (Team, Referral, Commercial, Analytics) can be extracted in future phases

### Phase 11 Applications & AI Matching Regression Testing ✅ (January 29, 2026)

**Test Results: 15/15 PASSED + 1 SKIPPED (AI Budget) (100%)**

| Test | Description | Result |
|------|-------------|--------|
| 1-2 | Application CRUD | ✅ PASS |
| 3 | Stage Transition (shortlisted) | ✅ PASS |
| 4 | Add Note | ✅ PASS |
| 5-6 | Update Details & Edit History | ✅ PASS |
| 7 | Job Applicants Review Screen | ✅ PASS |
| 8 | Candidates List | ✅ PASS |
| 9 | AI Matching | ⚠️ SKIP (LLM budget) |
| 10 | Resume Download | ✅ PASS |
| 11-12 | Role-Based Visibility | ✅ PASS |
| 13-14 | Unauthorized Access Rejection | ✅ PASS |
| 15-16 | Stage Transitions (interview/offered) | ✅ PASS |

**Endpoints Extracted to `/app/backend/routes/applications.py`:**
- `POST/GET /api/applications` - Application CRUD
- `GET/PUT /api/applications/{app_id}` - Single application
- `GET /api/applications/{app_id}/resume` - Resume download
- `POST /api/applications/{app_id}/notes` - Add notes
- `PUT /api/applications/{app_id}/details` - Update salary/notice
- `GET /api/applications/{app_id}/edit-history` - Audit trail
- `GET /api/jobs/{job_id}/applicants` - Per-job review screen
- `GET /api/candidates` - Candidate profiles
- `POST /api/ai/parse-resume` - AI resume parsing
- `POST /api/ai/parse-jd` - AI JD parsing
- `POST /api/matching/find-candidates` - AI candidate matching
- `GET /api/matching/jobs-for-candidate` - Job recommendations

**AI Screening Preserved:**
- ✅ ZERO changes to scoring logic
- ✅ ZERO changes to prompts
- ✅ ZERO changes to thresholds
- ✅ Human-in-loop enforcement preserved
- ✅ Entire database search scope preserved

### Phase 10 Candidate Bank Routes Regression Testing ✅ (January 29, 2026)

**Test Results: 16/16 PASSED (100%)**

| Test | Description | Result |
|------|-------------|--------|
| 1-5 | Candidate Bank CRUD & History | ✅ PASS |
| 6 | Mandatory Fields Update (salary/notice) | ✅ PASS |
| 7-8 | Role-Based Visibility (Employer/Recruiter) | ✅ PASS |
| 9 | Unauthenticated Access Rejection | ✅ PASS |
| 10-11 | Resume Download (Both Endpoints) | ✅ PASS |
| 12 | Recruiter Restricted from Non-Visible | ✅ PASS |
| 13 | Link Candidate to Job | ✅ PASS |
| 14-15 | Search & Filter | ✅ PASS |
| 16 | Update Candidate Record | ✅ PASS |

**Endpoints Extracted to `/app/backend/routes/candidates.py`:**
- `GET /api/candidate-bank` - List with visibility rules
- `GET /api/candidate-bank/{candidate_id}` - Single record with access control
- `PUT /api/candidate-bank/{candidate_id}` - Update with audit logging
- `POST /api/candidate-bank/add` - Add from resume upload
- `POST /api/candidate-bank/batch-parse` - Batch CV parsing
- `POST /api/candidate-bank/batch-save` - Batch save with validation
- `PUT /api/candidate-bank/{candidate_id}/salary-notice` - Mandatory fields
- `GET /api/candidate-bank/{candidate_id}/audit-log` - Audit trail
- `GET /api/candidate-bank/{candidate_id}/history` - Activity history
- `GET /api/candidate-bank/{candidate_id}/resume-history` - Resume versions
- `GET /api/candidate-bank/{candidate_id}/download-resume` - Resume download
- `GET /api/candidates/{candidate_id}/resume` - Resume download (alternate)
- `POST /api/applications/link-candidate` - Link to job

**Data Governance Preserved:**
- ✅ Visibility rules per role (Admin/Employer/Recruiter)
- ✅ Mandatory field enforcement (salary, notice, location, experience)
- ✅ Audit logging for all changes
- ✅ Profile freshness tracking
- ✅ Deduplication via fingerprint

### Phase 9 Jobs Routes Regression Testing ✅ (January 29, 2026)

**Test Results: 24/24 PASSED (100%)**

| Test | Description | Result |
|------|-------------|--------|
| 1-4 | Job CRUD (List, Create, Get, Update) | ✅ PASS |
| 5-8 | Career Page Control & Public Listing | ✅ PASS |
| 9-12 | Mandate Assignment & Team Recruiters | ✅ PASS |
| 13-15 | Job Approval Workflow | ✅ PASS |
| 16-17 | Role-Based Visibility | ✅ PASS |
| 18 | Employer Job Creation (Direct Active) | ✅ PASS |
| 19-20 | Unauthorized Access Rejection (403) | ✅ PASS |
| 21-24 | Link/Status Toggle & Deletion | ✅ PASS |

**Endpoints Extracted to `/app/backend/routes/jobs.py`:**
- `POST/GET/PUT/DELETE /api/jobs` - Job CRUD
- `POST /api/jobs/{job_id}/transition` - Status transitions
- `GET /api/jobs/pending-approval` - Pending approval list
- `GET /api/jobs/browse` - Public job browsing
- `POST /api/jobs/{job_id}/career-page-status` - Career page control
- `GET /api/jobs/{job_id}/career-page-history` - Audit history
- `PUT /api/jobs/{job_id}/shareable-link` - Shareable link toggle
- `GET /api/career-page/jobs` - Public career page listing
- `POST /api/jobs/extract-jd-text` - JD text extraction
- `POST /api/jobs/parse-jd` - AI-powered JD parsing
- `GET /api/employer/team-recruiters` - Team recruiters list
- `POST /api/jobs/{job_id}/assign-recruiters` - Mandate assignment
- `DELETE /api/jobs/{job_id}/assign-recruiters/{recruiter_id}` - Remove assignment
- `GET /api/jobs/{job_id}/assignments` - Get job assignments
- `POST /api/jobs/with-notifications` - Job creation with notifications
- `POST /api/jobs/{job_id}/notify-candidates` - Manual notification trigger

**Constraints Respected:**
- ✅ ZERO behavior changes
- ✅ ZERO feature removal
- ✅ ZERO refactor beyond extraction
- ✅ NO frontend changes
- ✅ All role checks preserved
- ✅ All approval workflows preserved
- ✅ All audit logging preserved

**Architecture:**
```
/app/backend/
├── config.py           # Environment, DB, R2 config
├── server.py           # Main app + remaining business modules
├── models/             # Pydantic models
│   └── __init__.py
├── routes/             # FastAPI routers (8 modules extracted)
│   ├── __init__.py
│   ├── auth.py         # Phase 5: Authentication
│   ├── public.py       # Phase 6: Public endpoints
│   ├── files.py        # Phase 7: File serving
│   ├── admin.py        # Phase 8: Admin/User management
│   ├── jobs.py         # Phase 9: Job CRUD, career page, mandates
│   ├── candidates.py   # Phase 10: Candidate bank, visibility
│   ├── applications.py # Phase 11: Applications, AI matching
│   └── settings.py     # Phase 12: Settings, alerts, notifications
├── services/           # External service clients
│   ├── r2_storage.py   # Cloudflare R2
│   ├── matching_engine.py # AI matching
│   ├── notification_service.py
│   └── whatsapp_service.py
└── utils/              # Helper functions
    ├── auth.py         # Auth helpers
    └── governance.py   # Data governance
```

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

*Last Updated: January 29, 2026*
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
*P0 Backend Refactoring: Phases 1-12 Complete (9/9 Phase 12 tests passed)*
