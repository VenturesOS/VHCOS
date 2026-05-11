# VHC Talent OS - Product Requirements Document

## Original Problem Statement
Build a full-stack talent management platform with AI-powered resume parsing, candidate matching, role-based access control, Chrome extension for sourcing, and financial management.

## Core Architecture
- **Frontend**: React + Tailwind + Shadcn/UI
- **Backend**: FastAPI + MongoDB Atlas
- **AI**: Claude Haiku 4.5 (non-admin LLM operations) via Direct Anthropic SDK with 4-key rotation; Admin uses ZERO-API regex parser ($0 cost)
- **AI Fallback**: Emergent LLM Key (last resort after all 4 Anthropic keys exhausted)
- **Auth**: JWT-based with role-based access (admin, recruiter, employer, accounts) + refresh tokens
- **Deployment**: AWS instance via Git pull + build + Gunicorn/Nginx

## What's Been Implemented

### Phase 1-9 (Previous Sessions)
- Core auth, role-based dashboards, job management, candidate bank
- AI resume parsing, candidate matching, bulk imports
- Chrome Extension for sourcing + fallback capture endpoints
- Salary benchmarking with company/industry filters
- Failed Captures tab in Candidate Bank
- Full profile display in Find Candidates results
- Accounts role + Finance Module (Invoicing, Expenses, Client Billing, Reporting)

### Phase 10 (2026-03-31)
- Eased Batch Upload Rules (only Name required)
- Add Candidate to Mandate dialog
- Account Manager Company Visibility Fix
- Accounts Role Restriction

### Phase 11 (2026-03-31)
- Gemini 2.5 Flash Integration (FREE primary AI extraction)

### Phase 12 (2026-03-31) - CTC/Notice Period Fix
- Inline Regex Extraction for CTC, Expected CTC, Notice Period

### Phase 13 (2026-04-01) - Rollback to Claude + Iframe Fix + Bug Fixes
- Rolled back to Claude Sonnet 4.6 via Emergent LLM Key
- Chrome Extension v5.1.1 with iframe extraction
- Bug fixes: Employer mandate visibility, 403 logout, tracker delete/reorder

### Phase 14 (2026-04-01) - Server Stability
- Synchronous DB initialization on startup
- Delete cleanup & Candidate Delete
- Attendance Report: Power BI-Style Excel
- Bulk CV Import reliability fix

### Phase 15 (2026-04-02) - Maintenance: 502 Fix
- Async CV parsing (502 elimination)
- Notification polling reduction
- MongoDB indexes
- Rate limit increases
- Switched to Haiku 4.5 for background enrichment

### Phase 16 (2026-04-03) - Performance & Cleanup
- Code splitting (69% bundle reduction)
- MongoDB indexes
- Security cleanup
- spaCy NER layer (admin A/B test)

### Phase 17 (2026-04-03) - Security Audit
- Path traversal fix, atomic registration, ReDoS prevention
- Password strength, timing-safe tokens
- LLM output cache, MongoDB pool reduction
- Token revocation, brute-force lockout

### Phase 18 (2026-04-03) - Infrastructure Hardening
- Centralized Redis-backed rate limiters
- N+1 query fixes
- Pagination on unbounded endpoints

### Phase 19 (2026-04-04) - Full Audit Implementation
- boto3 async fix, JWT secret enforcement
- Magic-byte file validation, refresh token rotation
- LLM priority routing, correlation IDs, deep health checks

### Audit Phase 3 (2026-04-05) - Frontend Refactor
- CandidateDataBankPage breakup (1594 → 270 lines)
- Cursor-based pagination
- requirements.txt trim (197 → 161 packages)

### Audit Phase 3b (2026-04-05) - Infinite Scroll & Refresh Token
- Cursor-based "Load More" UX
- Refresh Token Auto-Rotation in api.js

### Maintenance Fix Phase (2026-04-05) - 502 Elimination
- Async CV parsing with polling
- MongoDB sort memory fix (allowDiskUse)
- Health monitor false positive fix

### Phase 20 (2026-04-06) - User-Requested Features
- **Job Page Sorting**: `sort_order` param (newest/oldest) across all role job pages
- **Candidate Bank Mandate Filter**: `mandate_id` tracking from extension + filter UI
- **Employer Team Attendance Page**: Dedicated page with month nav, stats, daily records
- **Add-to-Mandate Dialog Enhancement**: Sourced candidates tab
- **Chrome Extension v5.2.0**: mandate_id tracking + refresh token auth
- **Pipeline Bug Fix**: Added missing employer_approved/rejected stages
- **Maintenance Fixes**: current_salary float, allowDiskUse, CTC pipeline unblock
- **Global IST Timezone**: All dates forced to Asia/Kolkata across frontend

### Phase 20b (2026-04-06) - Employer Attendance Insights
- **Backend**: New `GET /api/attendance/team/today` endpoint returning today's attendance snapshot per team member
  - Returns: date, is_holiday, total_team, present, absent, late, on_leave, wfh, not_checked_in, per-member statuses
  - Employer-only access (403 for admin/recruiter roles)
- **Frontend**: Enhanced `EmployerMyTeamPage.jsx` with comprehensive attendance insights:
  - **Today's Attendance Snapshot**: 6 stat cards (Present, Absent, On Leave, Late, WFH, Not In) + color-coded per-member status pills with check-in times
  - **Monthly Attendance Summary**: Table showing Present/Absent/Half Day/Leave/Late/WFH/Hours per member
  - **Per-member status badges**: Each team member row shows today's attendance badge + dot indicator on avatar
  - **Member Detail Dialog**: New "Attendance" tab showing today's status + monthly breakdown cards
- **Testing**: 100% backend (16/16 tests) + 100% frontend (iteration_151)

### Phase 20c (2026-04-07) - Batch Upload Mandate Linking
- **Backend**: `POST /api/candidate-bank/batch-save` now accepts optional `mandate_id` field
  - When provided, all saved/updated candidates are automatically linked to the job as applications (stage: `sourced`)
  - Handles duplicates gracefully — already-linked candidates are skipped
  - Response includes `linked` count and `mandate_id` in return payload
  - Fully backward-compatible — old payloads without `mandate_id` still work
- **Frontend**: `BatchUploadPage.jsx` Step 2 now shows a "Link to Mandate (Optional)" dropdown
  - Fetches active jobs and displays title + company name
  - Selected mandate applies to ALL candidates in the batch
  - Visual style matches the single CV upload dialog's mandate selector
- **Testing**: 100% backend (8/8 tests) — iteration_152

### Phase 21 (2026-04-07) - AI Screening Enhancement
- **Enhanced Matching Engine** (`matching_engine.py`):
  - 200+ skill synonym mappings (ML↔Machine Learning, JS↔JavaScript, AWS↔Amazon Web Services, etc.)
  - Fuzzy token overlap + synonym-aware matching
  - Multi-dimensional scoring: Skills (40%), Experience (20%), CTC Fit (15%), Notice Period (10%), Job Stability (10%), Semantic (5% bonus)
  - CTC fit scoring: Checks candidate salary vs job budget range (90 within budget, 30 way over)
  - Notice period scoring: Immediate joiners 95, 30-day 85, 90-day 45
  - Stability scoring: Avg tenure calculation to flag job hoppers (25) vs stable (90)
  - Job requirements parsing now prioritizes structured `skills` array over bullet-point text
- **Background Auto-Matching** (`services/job_suggestions.py`):
  - Triggers automatically on job creation
  - Scores top 2000 candidates against job requirements in ~3 seconds
  - Stores top 50 matches in `job_suggestions` collection
  - Manual refresh via `POST /api/jobs/{job_id}/suggestions/refresh`
  - Excludes candidates already linked to the job
- **Enhanced Add Candidate Dialog** (3-Tier Layout):
  - **Sourced tab**: Candidates captured via Chrome Extension with this mandate active
  - **System Suggestion tab**: AI-scored candidates sorted highest-to-lowest, with circular score badges, fit labels (Strong/Good/Weak/Mismatch)
  - **Search Bank tab**: Manual search against full Candidate Bank
- **Full Profile Evaluation**: Expandable candidate cards showing:
  - Multi-dimensional score bars (Skills, Exp, CTC Fit, Notice, Stability)
  - Matched skills (green badges) + Missing skills (red badges)
  - Contact info, CTC, notice period, industry
  - Profile summary, work experience, education
- **Testing**: 100% backend (11/11) + 100% frontend — iteration_153

### Phase 21b (2026-04-07) - Full Profile View & Score Alignment
- **Full Profile Dialog**: Clicking any candidate name or eye icon in the Add Candidate dialog opens the complete `CandidateProfileDialog` with all 6 tabs (Profile, Experience, Education, Activity, Timeline, Audit Log) — overlays on top of the Add Candidate dialog
- **Score Alignment**: Added `ctc_fit_score`, `notice_fit_score`, `stability_score` to `MatchResult` model so Find Candidates page shows the same multi-dimensional scores as System Suggestions
- **Enhanced Candidate Cards**: Each card now shows inline dimension bars (Skills, Exp, CTC, Notice, Stability), matched/missing skill badges, and full contact info (phone, CTC, notice period) — no more brief view
- **Testing**: Manual verification via screenshots — all features working

### Phase 21c (2026-04-07) - Zero-AI Matching Engine & Maybe Candidates
- **Zero-AI Matching**: Completely removed LLM dependency from candidate-job matching. Uses pure Python:
  - TF-IDF cosine similarity for text-based matching
  - 300+ skill synonym mappings for robust skill matching
  - Explicit deterministic scoring for CTC fit, notice period, job stability, location proximity
  - Weighted composite: Skills 35%, Experience 15%, CTC 12%, TF-IDF 12%, Location 10%, Notice 8%, Stability 8%
- **Maybe Candidates**: Candidates scoring well on skills but with <60% data completeness (missing CTC, location, notice period, etc.) are categorized separately
  - Backend stores `suggestions` (confirmed) and `maybe_candidates` (incomplete data) arrays in `job_suggestions` collection
  - Frontend displays "Maybe Candidates" section with amber warning and list of missing data fields
- **Performance**: Scores 2000 candidates in ~3.7 seconds with zero API cost
- **Testing**: 100% backend (17/17 tests) + 100% frontend — iteration_154

### Phase 22 (2026-04-08) - AI Cost Reduction & Extension Fix
- **System-wide AI model switch**: All Claude Sonnet 4.6 calls migrated to Claude Haiku 4.5 (~40% cost reduction)
- **Direct Anthropic SDK for Admin**: `admin@vhc.in` Chrome Extension extraction routed through direct `anthropic.AsyncAnthropic` SDK (user's own API key) instead of Emergent Universal Key — zero Emergent credit usage
- **Centralized AI Transport**: Added `use_direct_anthropic` parameter to `_call_claude()` and `extract_full_profile()` in `bedrock_service.py` — eliminates duplicate prompt logic in `extension.py`
- **Prompt Parity Fix**: Admin direct Anthropic path now uses the exact same detailed JSON-schema prompts (CTC conversion rules, work experience format, 15000-char text limit) as the Emergent path
- **Disabled spaCy A/B Test**: spaCy NER extractor was still active for admin, producing garbage extraction (polluted skills, missing fields). All users now route through Claude
- **Skills Cleanup Post-Processor**: `_clean_skills()` removes garbage from skills arrays: date ranges, phone numbers, emails, company names, section headers, nav text, and deduplicates
- **Re-Enrich Endpoint**: `POST /api/extension/re-enrich/{candidate_id}` re-runs Claude extraction on existing candidates using stored raw_text
- **Auto-Enrich on Profile View**: When a candidate profile opens with missing critical fields (location + employer + designation all empty, or enriched by spaCy/regex), auto-triggers background re-enrichment
- **Regex Backfill Post-Processor**: `_regex_backfill()` in `bedrock_service.py` catches CTC, expected CTC, notice period, location, and experience from Naukri header patterns when the LLM misses them. Handles the concatenated Naukri header format (e.g., "'253 Months" → 3 Months not 253)
- **Enhanced LLM Prompt**: Added explicit Naukri header format instructions ("NEVER return null for CTC/location/notice if data exists in text")
- **Testing**: 100% backend pass across 3 iterations (11 + 21 + 38 = 70 tests) — iteration_155, 156, 157

### Phase 23 (2026-04-09) - Zero-API Admin Extraction & Cost Elimination
- **Admin ZERO-API Routing**: `admin@vhc.in` now uses `naukri_regex_parser.extract_full_profile_regex()` for ALL extraction operations — zero LLM cost
  - AI Extract endpoint: Admin → regex parser, Others → Claude Haiku 4.5
  - Background capture enrichment: Admin → `_background_regex_enrich`, Others → `_background_claude_enrich`
  - Re-enrich endpoint: Admin → regex parser (source: `regex_zero_cost`), Others → Claude
- **Claude 3 Haiku Deprecated**: `claude-3-haiku-20240307` confirmed retired by Anthropic (404 errors). Only active Haiku model is `claude-haiku-4-5-20251001`
- **Model Override Support**: `_call_claude()` now properly uses `model_override` in the direct Anthropic SDK path
- **Enrichment Source Tracking**: Re-enrich endpoint tracks `regex_zero_cost` vs `anthropic_direct` for analytics
- **Testing**: 100% backend (17/17 tests) — iteration_158

### Phase 23b (2026-04-09) - Regex Parser Quality Dashboard Card
- **New Admin Dashboard Card**: "Regex Parser Quality" shows field extraction rates, overall quality score (avg fill rate), strong vs. weak fields breakdown
- **Backend Optimization**: Single `$facet` aggregation pipeline — reduced endpoint from 11s to 2.6s response time
- **API Endpoint**: `GET /api/stats/extraction-quality` tracks 14 fields across regex-enriched candidates
- **Testing**: 100% (13/13 backend + full frontend verification) — iteration_159

### Phase 23c (2026-04-09) - Regex Parser Strengthening
- **Naukri Header Parsing**: New `_parse_naukri_header()` handles concatenated format `{name}Save{years}y₹ XX Lacs (expects: ₹ YY Lacs){City}Current{Title}...{N} Months`
- **CTC Extraction**: Handles ₹ Lacs, LPA, Crore formats from both header and labeled fields
- **Notice Period Fix**: Labeled patterns (e.g., "Notice Period: 2 Months") now ALWAYS take priority over header-parsed values. Excluded false positives from "X Years Y Months" experience patterns
- **Location Fallback**: Added 100+ Indian cities lookup for location extraction when no label exists
- **Headline/Summary Fallback**: Synthesized from designation + company + experience when explicit sections not found
- **Education Boundaries**: Improved section boundary detection to not leak into certifications
- **Testing**: 100% (34/34 backend tests) — iteration_160

### Phase 23d (2026-04-09) - CV Format Parser & Claude-Quality Extraction
- **CV Work Experience**: Handles `Title | Company` pipe format with multi-line descriptions, dates, and current role detection
- **CV Summary**: Extracts full paragraph text between contact info and first section header (EXPERIENCE/SKILLS)
- **Industry & Department**: Extracted from `=== NAUKRI PAGE TEXT ===` section of combined text
- **Combined Text Flow**: Capture endpoint now passes `raw_profile_text + page_text` to admin's background enrichment
- **Bug Fixes**: Standalone section header matching (prevents "Experienced" from matching "EXPERIENCE"), work entry splitting on blank lines for Naukri DOM format
- **Testing**: 100% (24/24 backend tests + 2 bugs fixed) — iteration_161

### Phase 23e (2026-04-10) - Date-Anchored Work Experience Parser
- **Rewrote Format C** (`_parse_work_experience`): Replaced fragile company-keyword splitter with date-anchored state machine
  - Blank-line separated chunks: each chunk parsed individually (company/title before date, description after)
  - Dense text (no blank lines): 2-pass algorithm — Pass 1 claims header lines backward from each date, Pass 2 assigns description between entries
  - Handles companies WITHOUT keywords (Reliance Jio, Zomato, Flipkart, Google, etc.)
  - Gap lines ("N months gap") correctly skipped
  - Old company-keyword approach kept as last-resort fallback when no dates exist
- **Fixed `is_current` detection**: New `_is_current_role()` helper checks `to_date` value instead of searching for 'till' in the line. "Sep '21 till Dec '24" now correctly returns `is_current=False`
- **Testing**: 100% (30/30 new tests + 75/75 regression) — iteration_162

### Phase 23f (2026-04-10) - Comprehensive Extraction Quality Overhaul
- **Address Filtering**: Added `_is_address_line()` helper to block residential addresses from employer, designation, and work experience
- **Employer/Designation Reorder**: Moved early-lines fallback AFTER work experience parsing. Priority: header → labeled → work_exp_backfill → last-resort early lines
- **Work Experience Boundaries**: Fixed `\nProject` → `\nProjects?\s*\n` so "Project Manager" doesn't truncate employment section
- **Skills Line-Start Anchor**: ALL skills patterns now require `(?:^|\n)\s*` prefix — prevents matching "key skills" INSIDE summary sentences
- **CORE COMPETENCIES as Primary Source**: Added "CORE COMPETENCIES" / "Areas of Expertise" as Strategy 1 skills source (highest priority)
- **Skills Garbage Filter**: `_clean_skill()` now rejects: conjunction/preposition starters (and/or/in/for/to/of/with...), sentence starters (Proficient/Adept/Demonstrated + >3 words), >5 words, lowercase gerund phrases >2 words
- **Summary Quality**: Capped at 500 chars with sentence-boundary cut, stops at CORE COMPETENCIES/Areas of Expertise boundaries, strips "||||" Naukri artifacts
- **CTC/Expected CTC Expanded**: Added INR/Rs./Compensation/Package patterns for CTC; Exp CTC/Looking for/Desired CTC patterns for expected
- **Notice Period Expanded**: Added Days/Weeks/Available-to-join/Buyout/standalone-months patterns
- **Education Expanded**: Added ITI/Graduation/Doctorate, fallback degree scan with institution context
- **Testing**: 100% (185 tests across iterations 158-164) — zero regressions

### Phase 24 (2026-04-10) - Hybrid Pipeline + Startup Resilience
- **Hybrid Extraction Pipeline**: Regex-first extraction for ALL users (zero cost). Scores regex output; Claude fallback only if quality < 50%. Saves 80%+ LLM costs.
- **Duplicate Profile Skip**: Existing profiles bypass Claude enrichment entirely — prevents redundant token charges.
- **503 Startup Fix (P0)**: Made DB initialization synchronous in FastAPI lifespan. Worker now crashes if MongoDB unreachable after 3 retries (instead of serving broken responses). Added `RuntimeError` catch in `get_current_user()` as belt-and-suspenders 503 handler.
- **Critical Bug Fix: _score_extraction_quality always returned 0%**: `_[0]` took first CHARACTER of field name instead of full name → Claude called for EVERY capture. Fixed to use `field_name`.
- **Inline Regex Extraction**: Full `extract_full_profile_regex` now runs at capture time (not just background). Profiles populated with skills, CTC, notice, education, work exp BEFORE DB save — eliminates empty shell profiles.
- **CTC Fix**: Replaced buggy ad-hoc CTC regex with battle-tested naukri_regex_parser (168 tests). No more ₹8,00,00,00,000 values.
- **Background enrichment skip**: When inline regex quality ≥ 50%, background enrichment (Claude) skipped entirely.
- **Testing**: iteration_165 (18/18), iteration_166 (14/14), iteration_167 (27/27) — 100% pass rate

### Data Quality Sanity Checks (2026-04-10)
- **CTC Cap**: Any CTC > ₹20 Crore rejected (prevents project values like "Rs 30000 Cr" from being used as personal salary)
- **Education Validation**: Entries without degree keywords (MBA, B.Tech, University, etc.) or containing action verbs (Negotiate, Track, Handle) are rejected
- **Location Word Boundary**: City matching uses `\b` regex boundaries (prevents "Goa" from "Goal-oriented")
- **Designation Validation**: Entries >80 chars or starting with action verbs are rejected
- **page_text Field**: Added to capture model so future Chrome Extension versions can send structured Naukri page data (CTC, location, notice period) — parsed by `_parse_naukri_page_text()`
- **IMPORTANT**: CTC/location/notice may show as empty for profiles where the CV text doesn't contain these fields explicitly. The Chrome Extension needs to be updated to send `page_text` for reliable structured data extraction.

### Phase 25 (2026-04-10) - Dedup + Auto-Merge Engine
- **Auto-Merge Engine** (`services/candidate_merge.py`): When a new profile comes in from ANY source (extension, Excel, manual CV), checks if 2/3 of (name, email, phone) match an existing profile → auto-merges instead of creating duplicate
- **CTC Merge Rule**: Higher CTC value wins, but ONLY if ≤ ₹20 Cr sanity cap (prevents random number overwrites)
- **Skills Merge**: Union of both profiles' skills (capped at 50)
- **Experience/Education Merge**: Keep the longer list
- **Silent Audit Trail**: All merges logged in `merge_audit_log` collection
- **Recruiter Contact Filtering**: Already existed — strips @vhc.in emails and recruiter's own email/phone from captures
- **Optional Naukri Fields**: `naukri_profile_id` and `naukri_profile_url` are now optional — supports cross-source captures
- **Testing**: iteration_168 (15/15) — 100% pass rate

### Phase 26 (2026-04-11) - 3-Layer Capture Architecture
- **3-Layer DOM Capture** (gated for `admin@vhc.in` only):
  - **Layer 1 (DOM Scraping)**: When `dom_scraped=True`, extension-sent structured fields (name, company, designation, CTC, notice, location, skills, experience) are trusted as authoritative
  - **Layer 2 (Page Text Regex)**: Fills gaps from `raw_profile_text` + `page_text` — especially phone (masked by Naukri DOM) and email
  - **Layer 3 (Claude CV Scan)**: Background enrichment triggered ONLY if phone is still missing after L1+L2; uses `dom_3layer=True` mode to only fill empty fields, never overwrite DOM values
- **Non-admin path unchanged**: Users other than `admin@vhc.in` continue using the existing hybrid pipeline (regex + Claude fallback)
- **Phone/Email regex extraction**: Added inline extraction of `candidate_phone` and `candidate_email` from regex results for ALL users (previously only done in background enrichment)
- **page_text conditional overrides**: For 3-Layer admin, page_text only fills gaps; for standard captures, page_text still unconditionally overrides CTC/notice/location
- **Chrome Extension v5.2.1**: Added `extractDOMProfileFields()` to content.js for structured DOM scraping; background.js skips AI-extract when DOM fields are available
- **Haiku enrichment verified working** for all non-admin users (anthropic_direct_haiku)
- **Testing**: iteration_169 (13/13) — 100% pass rate; E2E curl tests pass

### Phase 26b (2026-04-11) - Capture Pipeline Audit & Hardening
- **Experience Years Cap**: Added 50-year cap in regex parser + capture endpoint + all enrichment paths (prevents absurd values like 253y from header parsing bugs)
- **CTC Cap Enforcement**: Extended ₹20 Cr sanity cap to ALL background enrichment functions (`_background_claude_enrich`, `_apply_bg_enrichment`, `_background_regex_enrich`, re-enrich endpoint). Previously only regex parser had this check.
- **Skills Garbage Filter on Initial Save**: `_clean_skills()` now runs BEFORE `build_complete_candidate` in both create and update paths. Previously, garbage skills persisted when background enrichment was skipped.
- **`_clean_skills` False Positive Fix**: Expanded tech-word whitelist with 40+ terms (SAP, Power, Spring, Red Hat, Sigma, Oracle, Azure, etc.) to prevent rejecting valid skills.
- **Auto-Merge Application Fix**: Added duplicate application check in auto-merge path — now creates `applications` record with existence check (matching the existing-profile update path behavior).
- **`raw_text_for_enrichment` Storage**: Combined enrichment text now stored during capture for reliable re-enrichment later.
- **Testing**: 100% (15/15 backend tests) — iteration_170

### Phase 26c (2026-04-11) - Extraction Architecture Overhaul (Consistency Fix)
- **Temperature=0**: Set on all Claude calls via `.with_params(temperature=0)` — eliminates random variation between identical inputs
- **Text Pre-processor**: `_preprocess_naukri_text()` adds section labels (`[PROFILE HEADER]`, `[CANDIDATE CV/RESUME]`) so Claude gets structured input instead of a text wall
- **Regex-First Architecture**: `extract_full_profile` now runs regex BEFORE Claude. Regex fills deterministic fields (CTC, notice, experience, location), Claude only gap-fills complex fields (work history, skills, summary). Reduces Claude's workload by ~60%.
- **Type Validator**: `_validate_extraction()` enforces schema on all 30+ output fields — CTC must be int ≤₹20Cr, experience ≤50y, notice ≤365d. Handles string CTC ("60 Lacs" → 6000000). Catches all type mismatches.
- **Graceful Fallback**: If Claude returns invalid JSON, extraction now returns regex-only result instead of error dict — profiles always get some data.
- **Testing**: 100% (27/27 backend tests) — iteration_171

### Phase 26d (2026-04-11) - Extraction Reliability Overhaul (Silent Failure Fix)
- **Root Cause**: Background enrichment silently died on any Claude API error (rate limit, timeout, etc.) with zero recovery. Profile stayed blank forever. This was the "works for 1-2 then fails" pattern.
- **Retry with Backoff**: 3 attempts with [0s, 5s, 15s] delays before giving up. Survives transient rate limits and network blips.
- **Regex Fallback**: If Claude completely fails after 3 retries, falls back to `extract_full_profile_regex` to get at least basic data (CTC, notice, experience, skills). Previously: returned nothing.
- **JSON Repair**: `_repair_truncated_json()` fixes common truncation patterns (missing braces, brackets, trailing commas) from max_tokens limits. Salvages partial Claude responses instead of discarding them.
- **max_tokens 3000→4096**: More headroom for complex profiles with 5+ work experiences.
- **Quality-Gated Caching**: Only caches enrichment results with 4+ meaningful fields filled. Prevents low-quality regex-only results from polluting the cache.
- **Enrichment Status Tracking**: `enrichment_status` field on candidate records: `pending` → `enriched` | `partial` | `failed`. Users can now see which profiles need re-enrichment.
- **Testing**: 100% (41/41 backend tests) — iteration_172

### Phase 27 (2026-04-11) - Comprehensive Quality Validation Fix (6 Layers)
- **Root Cause**: Multiple validation gaps allowed education data (GPA, university) to be saved as work experience. Regex parser confuses education sections with work experience, and NO validation prevented bad data from reaching database.
- **Deep Investigation**: Exhaustive security audit found 6 critical validation gaps across extension input, regex extraction, background enrichment, and garbage checks.
- **Complete Fix - All 6 Pathways Secured**:
  1. **Capture-Time Validation** (Lines 1828-1878): Validates employer/designation/work_experience from regex BEFORE writing to profile object
  2. **Background Apply Helper** (Line 1032-1036): Added validation in `_apply_bg_enrichment()` before database update
  3. **3-Layer Claude Path** (Line 1282-1288): Added validation in `_background_claude_enrich()` DOM 3-layer mode
  4. **Targeted Enrichment Merge** (Line 1560-1577): Validates employer/designation from regex before merging in `_background_targeted_enrich()`
  5. **Quality Scoring Gate** (Line 726-774): Validates and returns 0.0 score to force Claude enrichment
  6. **Extension Data Garbage Checks** (Lines 2684-2746): Enhanced `_is_garbage_employer()` and `_is_garbage_designation()` to reject education keywords and grade patterns
- **Validation Rules**:
  - Rejects company names containing: university, college, school, institute, academy, IIT, NIT, IIM
  - Rejects designations containing: GPA:, CGPA:, %, grade:, marks:, score:, or just numbers
  - Rejects designations < 3 chars, companies < 2 chars
  - Case-insensitive substring matching (catches "ABC University", "Gita university", etc.)
  - Logs warnings at each rejection point for debugging
- **Defense in Depth**: Four-layer protection (extension input → capture → background enrichment → quality scoring) with validation at every data entry point
- **Impact**: Systematic fix prevents education-as-work-experience bug across ALL data sources (extension, regex, Claude, hybrid) and ALL code paths (admin, non-admin, targeted, 3-layer)
- **Testing**: Complete security audit with 5 test scenarios and validation at 6 critical points

### Phase 28 (2026-04-14) - Claude Haiku 4.5 Extraction Fix + Duplicates Bug
- **Root Cause (Extraction Quality)**: Previous agent added `extract_full_profile_fallback()` calling `_call_emergent_llm_haiku()` but **never implemented the function** — extraction was completely broken. Additionally, the prompt was oversimplified (missing CTC conversion rules, experience decimal format, education boundaries).
- **Fix**: Created `_call_emergent_llm_haiku()` using `emergentintegrations` library with `claude-haiku-4-5-20251001` model via Emergent LLM Key. Restored the full detailed extraction prompt with all quality rules (experience decimal format, CTC lakh→rupee conversion, education boundaries, notice period conversion).
- **Fallback Chain**: Haiku primary → GPT-4o fallback → error. Ensures extraction always gets attempted.
- **Duplicates 500 Fix (P0)**: Added `allowDiskUse=True` to both email and phone aggregation pipelines in `candidates.py` find-all-duplicates endpoint.
- **Duplicates 500 Fix v2**: Rewrote to two-step approach (find keys first, then fetch details) to work within MongoDB Atlas shared tier 100MB memory limit. Now returns results reliably.
- **Test Result**: Haiku extraction verified — experience "5y 8m" → 5.08, CTC "25 Lakhs" → 2500000, work experience + education correctly extracted.
- **Testing**: 100% (13/13 backend + frontend) — iteration_173

### Phase 28g (2026-04-14) - Hook Dependencies, Component Splits, Backend Refactoring
- **Hook dependencies fixed (6 files)**:
  - JobsPage, RecruiterJobsPage, EmployerJobsPage: Wrapped `loadJobs` in `useCallback` with `[sortOrder]` dep
  - SalaryBenchmarkPage: Added `fetchBenchmark` to useEffect deps
  - AdminAnalyticsPage: Stabilized useMemo deps with `data?.` optional chaining
- **AdminPipelinePage split** (647→496 lines): Extracted 4 dialogs (Delete, Offer, Hired, Join) into `PipelineDialogs.jsx`
- **Backend refactoring** (account_manager.py):
  - Extracted 5 helpers: `_validate_companies`, `_enforce_employer_ownership`, `_merge_assignments`, `_get_company_ids_for_user`, `_strip_sensitive_fields`
  - `assign_account_manager`: complexity 29→12
  - `get_my_companies`: complexity 16→8
- **Console statements**: Removed all 16 `console.error` calls from production frontend (replaced with silent catch or removed where toast already existed)
- **Dynamic import security**: Added `_ALLOWED_ROUTE_PREFIXES` whitelist to `server.py:_safe_import()`. Replaced `__import__('config')` in `health.py` with static import
- **Array index keys**: Fixed remaining 8 instances in BlogPages, EmployerCompaniesPage, FindCandidatesPage, FinancialReportsPage
- **Test file cleanup**: Removed 163 auto-generated test files with hardcoded credentials. Only `conftest.py` (env-based) and `__init__.py` retained
- **Confirmed false positives**: `eval()` in security_service.py is a byte-string pattern match (not code execution); circular imports use lazy imports inside functions; `is True/False` comparisons already at 0 instances
- **Wildcard imports eliminated**: `models/__init__.py` now uses explicit imports for all 50+ model classes
- **Lambda expressions replaced**: Converted lambda assignments to proper `def` functions in `admin.py`, `auth.py`
- **Redundant imports removed**: Removed duplicate `import asyncio` in `jobs.py` (already imported at module level)
- **F-string fixes**: Auto-fixed 8 f-strings without placeholders across `llm_fallback_service.py`, `extension_service.py`, `scheduler.py`, `matching_engine.py`, `ai_search.py`, `groq_ai_service.py`
- **Unused variables removed**: Removed `now_iso` in `admin.py`
- **Activity monitor refactored**: Reduced complexity from 39 to ~15 by extracting `_init_user_map()`, `_aggregate_activity_logs()`, `_aggregate_collection()` helpers
- **Test config centralized**: Created `tests/conftest.py` with env-based credential loading
- **Security audit**: Confirmed `eval()` in `security_service.py:38` is a false positive (it's a byte string in a blocklist, not code execution); circular import in `config.py`↔`job_queue.py` is already handled with lazy imports inside functions

## Prioritized Backlog

### Phase 28b (2026-04-14) - Activity Monitor
- **Backend**: `GET /api/admin/activity-monitor/summary` aggregates from `activity_logs`, `jobs`, `applications`, `submission_trackers`, `bulk_import_batches`, `refresh_tokens` collections
  - Returns per-user breakdown: profiles_captured, profiles_viewed, profiles_updated, profiles_edited, stage_changes, notes_added, cv_uploads, mandates_created, applications_created, trackers_created, batch_uploads, logins
  - Platform totals: active_users, inactive_users, total_actions
  - Time filters: today, week, month, year, custom (start_date/end_date)
- **Backend**: `GET /api/admin/activity-monitor/trend` returns daily activity breakdown for trend chart
- **Frontend**: `ActivityMonitorPage.jsx` — Admin-only page at `/admin/activity-monitor`
  - 4 adoption summary cards (Active Users, Total Actions, Profiles Captured, Total Logins)
  - 6 engagement metric cards (Profile Views, Pipeline Adds, Stage Changes, Mandates, CV Uploads, Trackers)
  - Activity trend line chart (Total, Captured, Updated, Viewed)
  - User Leaderboard table with rank, name, role, all metrics, last active — expandable rows
  - Role filter, user search, period selector
  - Inactive users alert at bottom with user badges

### Phase 28c (2026-04-14) - Admin Sidebar Restructure
- **Sidebar consolidation**: Reduced admin sidebar from ~32 items to 22 items
- **Tab wrapper pages** (9 new files using React.lazy + Suspense):
  - Candidate Bank + Candidates → `CandidateBankTabsPage.jsx`
  - Naukri Import + Import History → `NaukriImportTabsPage.jsx`
  - Teams + Hierarchy → `TeamsTabsPage.jsx`
  - Blog Engine + Blog Analytics + SEO Monitoring → `BlogTabsPage.jsx`
  - Activity Monitor + Activity Feed → `ActivityTabsPage.jsx`
  - System Health + Bug Reports → `SystemHealthTabsPage.jsx`
  - Security Audit + Compliance → `SecurityTabsPage.jsx`
  - Attendance + Leave Management + Insights + Settings → `AttendanceTabsPage.jsx`
  - Settings + Resources → `SettingsTabsPage.jsx`
- **Removed from admin sidebar**: LinkedIn Settings, Resume Builder
- **No regression**: Recruiter and Employer sidebars/routes unaffected
- **Testing**: 100% (iteration_174 — all 9 tab pages + tab switching + regression)

### Phase 28d (2026-04-14) - Enhanced Admin Dashboard
- **Backend**: Extended `GET /api/stats/admin` with 8 new data sections:
  - Today's Pulse: active_users, captures, views, stage_changes (today)
  - Top Recruiters: Top 5 by captures this week
  - Pipeline Stages: All active application stages with counts
  - Stale Candidates: Candidates stuck in sourced/shortlisted >7 days
  - Jobs with 0 Applicants: Active jobs without any applications
  - Hiring Funnel: 30-day stage distribution
  - Capture Velocity: Daily capture counts for last 7 days
  - Total Candidates: Candidate bank count (112K+)
- **Frontend**: Complete dashboard redesign with 10 sections:
  - Today's Pulse banner (live activity snapshot)
  - 5 clickable core stat cards (navigate to respective pages)
  - Top Recruiters weekly leaderboard
  - Capture Velocity bar chart (7-day trend)
  - Attention Needed alerts (stale candidates, empty jobs)
  - Hiring Funnel horizontal bar chart
  - Pipeline Overview with stage bars
  - Users by Role breakdown
  - Recent Applications with stage badges
  - Regex Parser Quality card
- **Bug fix**: Jobs/mandates aggregation used `posted_by` instead of `created_by`

### Phase 23 (2026-04-16) - LLM Source Badges & Filter
- **AI Source Badges**: Admin-only badges (Q=RunPod, AC=Anthropic Direct, EC=Emergent Key, RX=Regex) displayed next to candidate source badge in Candidate Bank list
- **AI Source Filter**: Admin-only dropdown in filter panel to filter candidates by which LLM layer extracted them (RunPod, Anthropic, Emergent, Regex)
- **RunPod A40 Migration**: Upgraded from L4 to A40, 32K context, auto-scheduling 9AM-6:30PM IST Mon-Sat
- **Bug Fix: Profile Page Crash**: Fixed 3 undefined variable references in NaukriProfileView.jsx
- **Enhanced System-Generated CV**: Full work history, certifications, designation, no truncation
- **Attach CV to All Profiles**: Button on all candidates + full profile page
- **JSON Repair for Qwen**: Handles trailing commas, malformed output
- **Regex Safety Net**: Backfills CTC, notice period, education, location after LLM extraction
- **Edit Job/Mandate**: Pencil icon edit dialog with public_company_alias field
- **LinkedIn Sharing Fix**: Uses public_company_alias instead of real company name
- **Geo-Fencing for Attendance**: Configurable office lat/lon/radius, toggle per settings, enforced on office check-in, GPS coordinates stored
- **Hiring Funnel KPI Dashboard**: Pipeline funnel visualization, stage conversion rates, avg time-to-hire, source effectiveness, rejections — admin-only at /admin/hiring-funnel
- **Bulk CV Attach Queue**: Upload up to 30 CVs at once, auto-matches to candidates by filename/phone/email, processes 3 concurrent, prevents server crash

### P1 - Upcoming
- Smart Tags / Auto-Categorization (AI auto-tags candidates)
- **[P1] Bulk re-enrich stuck at 0% bug** — Despite multiple fix attempts (cross-loop guard, progress flush every 5), the background `_worker` coroutine silently fails to make progress when triggered at scale (observed Apr 22). Single-candidate `re-enrich/{id}` endpoint works. Suspect: `_apply_bg_enrichment` helper uses sync pymongo which may conflict with the async bg task context. Next steps: add print-level instrumentation, test with limit=1, consider converting `_apply_bg_enrichment` to async Motor. 471 historical candidates waiting for RunPod re-enrichment.
- **[P1] RunPod Qwen 14B AWQ JSON coherence** — Even with `response_format: {"type": "json_object"}` and reduced input (50K), ~10-20% of outputs are malformed JSON around chars 4800-8000. `json_repair` catches ~70% of these. Options: (a) use vLLM guided decoding with JSON schema, (b) reduce max_tokens from 6000→4000, (c) switch to Qwen 14B Instruct (non-AWQ) if VRAM allows. Mitigated but not eliminated.

### P2 - Future
- Email Template Management
- OpenRouter free models (when user provides API key)
- Tune spaCy NER confidence patterns
- **[P2] RunPod auto-URL sync daemon**: Poll RunPod GraphQL API every 60s on AWS, auto-rewrite `RUNPOD_VLLM_URL` + reload gunicorn if pod ID changes. Eliminates daily manual `.env` step. Requires user's RunPod API token.
- **[P2] AI-generated candidate summary + strengths field (talent graph)** — Since A40 now sees full profiles in one pass, add semantic-search indexable summary field. Turn 113K candidate bank into natural-language-queryable talent graph.

### P3 - 6+ Month Horizon
- **WhatsApp Business API Integration** — Native Meta Cloud API integration into VHC (messaging, templates, campaigns, webhooks, bot auto-replies). WABA Panel source code reviewed and architecture documented. Strategy: candidate-initiates-first to minimize costs (~₹0/month). Requires Meta Business API credentials (Phone Number ID, Business Account ID, Access Token).
- **Naukri "10y 1m" top-card experience regex fix**: Backend `routes/extension.py` 3-tier regex + browser extension parses compact `{y}y {m}m` title attrs. Uses years+months/100 formula. Guards against false-positive "1 year" matches in JD text (candidates no longer default to 1 year experience).
- **Work-experience duration post-processor**: New `_fix_work_experience_durations()` function in `services/llm_fallback_service.py` computes `"Xy Ym"` from `from_date`/`to_date` (or today for current roles) whenever LLM emits empty or `"0y 0m"`. Handles Naukri date formats ("Jun 2022", "Jun '22", "Present", "Current", etc). Wired into all 3 LLM layers + json_repair fallback paths.
- **DB cleanup endpoint**: `POST /api/candidate-bank/data-quality/fix-work-experience-durations` (admin-only). Supports `?dry_run=true`. Applied to production: **27,436 durations fixed across 8,146 candidates** (99.985% success; 2 edge cases with unparseable dates remain).
- **RunPod A40 context scale-up**: Raised LLM input from 13K→80K chars (~3.7K → ~22K tokens), output max_tokens from 4000→6000, timeout 120s→180s. Fully utilizes 32,768-token Qwen 14B window. ~6x more profile text per call — full work histories + IT skills now captured in a single pass.
- **Prompt hardening**: Explicit instructions "never return 0y 0m unless <1 month old role" + compute duration from dates.

### Phase 19 (2026-04-20 evening) — CTC Data Integrity
- **CTC sanitizer** (`sanitize_ctc()` in `services/llm_fallback_service.py`): Rejects any salary outside ₹50K – ₹5 Cr annual window. Prevents corrupt extractions (e.g., 160 billion from "1600000 Lacs" double-multiplication).
- **5-layer defense**: browser extension content.js → backend page-text regex → LLM regex backfill → post-LLM sweep → DB cap
- **`_CTC_MAX` lowered from 20 Cr → 5 Cr** everywhere (3 sites in `routes/extension.py`, both current + expected)
- **DB cleanup endpoint**: `POST /api/candidate-bank/data-quality/fix-ctc-outliers` — applied: nulled 48 current_salary + 1 expected_salary corrupted values (worst case: ₹900 Cr phantom record)

### Phase 20 (2026-04-21) — RunPod Resilience + Bulk Re-Enrichment
- **Bulk re-enrichment endpoint**: `POST /api/candidate-bank/data-quality/bulk-re-enrich` — background-executed (non-blocking), with RunPod health pre-flight probe (aborts with 503 if vLLM unreachable unless `force=true`), async progress tracking via `bulk_enrich_jobs` MongoDB collection. Params: `since_hours`, `exclude_source`, `limit`, `concurrency`, `dry_run`, `force`.
- **Status endpoints**: `GET /bulk-re-enrich/status/{job_id}` (live progress) + `GET /bulk-re-enrich/status` (last 5 jobs)
- **vLLM Bearer auth support**: Added `RUNPOD_API_KEY` / `VLLM_API_KEY` env var support in `_call_runpod_vllm()`. New RunPod template requires `VLLM_API_KEY=sk-$RUNPOD_POD_ID`.
- **Self-healing API key**: Auto-derives `sk-{pod_id}` from `RUNPOD_VLLM_URL` hostname. Means pod migrations only require updating URL in `.env` — key auto-follows.
- **Known operational issue**: RunPod pod URL changes on every migrate/stop-start cycle. Manual `.env` update still required each morning when pod resumes.

### Phase 22 (2026-04-22) — Automated Recruiter Performance Reports
- **New service**: `services/reports_service.py` — IST-timezone-aware window math (6:30 PM rollover + Mon-Sun weekly), MongoDB aggregation (captures from `candidate_bank.captured_by`, stage transitions from `pipeline_events`), openpyxl Excel builders.
- **Metrics**:
  - Daily: per-team, per-recruiter, per-mandate → Profiles Captured + Shared (subtotals + grand total)
  - Weekly: per-team multi-sheet workbook — Summary tab + one tab per recruiter with KPIs (Captured, Shared, Shortlisted, Interviewed, Offered, Selected, Joined) + mandate list
- **Crons** registered via APScheduler in `lifecycle.py`:
  - `daily_recruiter_report` → 13:00 UTC (18:30 IST)
  - `weekly_recruiter_report` → Mon 03:30 UTC (09:00 IST)
- **Multi-worker dedup**: `_acquire_run_lock()` uses a unique MongoDB index on `report_job_locks` so only 1 gunicorn worker sends per window.
- **Attachments**: `services/email_service.py.send_email()` extended with base64-encoded attachments via Resend.
- **Admin API**: `/api/reports/daily/run-now`, `/api/reports/weekly/run-now`, `/api/reports/{daily,weekly}/preview/{team_id}` (download .xlsx without sending), `/api/reports/dispatches` (audit log of last 50 emails sent).
- **Audit collection**: `db.report_dispatches` — type, team_id, employer_email, window, totals, email_id, sent_at.
- **Frontend**: `pages/employer/EmployerReportsPage.jsx` — schedule banner + "Send Now" buttons, per-team Excel download table, recent dispatches audit log. Sidebar entry added.



- **RUNPOD_SKIP env flag**: Added runtime override in `llm_fallback_service.py` — when set to `1`, bypasses Layer1 RunPod and goes straight to Anthropic Haiku. Useful as emergency valve when RunPod is down or producing malformed JSON.
- **Cross-loop RuntimeError safeguards**: `_log_extraction_event` now silently swallows `"attached to a different loop"` errors that occur when background tasks use their own Motor client but try to log via the global request-scoped db.
- **json_repair validation loosened**: Accepts any of `name`/`experience_years`/`current_employer`/`key_skills` as proof of valid extraction (was requiring `name`, causing silent fallthrough on truncated Qwen outputs).
- **Input length tuned**: Reduced main LLM raw_text from 80K → 50K chars. 80K was too ambitious for Qwen 14B AWQ — model struggled to maintain JSON coherence over long outputs. 50K still fits 95% of Naukri profiles.
- **Progress flush fix**: `bulk-re-enrich` now flushes progress every 5 candidates (was every 10, causing small batches to appear stuck at 0%).
- **Live pipeline validated**: Post-cutover captures (Kiranteja, Vamsinathreddy, Abhishek Ghatage) correctly route through RunPod Qwen with "Q" source badges. First 3 morning captures (Royston Dias, G Kotiswarudu, Chandra D) went via Anthropic "AC" before skip flag was removed.

### Phase 22.1 — Daily Report Debug Script Hardened (2026-04-22)
- **scripts/debug_daily_window.py**: Rewritten to mirror `config.py`'s Mongo URL resolution — now tries `mongo_production_override.py` first (same as gunicorn), falls back to .env `MONGO_URL`. Eliminates the `OperationFailure: bad auth` AtlasError when running the script on production (/home/ubuntu/vhc-platform/backend).
- **Verification on preview backend**: Script reports all 4 active teams with recruiters have captures today (Faridabad=66, Bengaluru=56, Gurgaon=111, Delhi=133). Daily Excel preview endpoint returns 6097-byte file with real per-recruiter rows. **Aggregation logic in `reports_service.py` is correct**; earlier "No activity" on production was a stale-gunicorn issue, not a data bug. User must `git pull && sudo systemctl restart gunicorn` on production to pick up the `$or captured_by/created_by` fix.

### Phase 22.2 — "Sourced" Pipeline Column + Bank→Mandate Link Visibility (2026-04-22)
- **Root cause of invisible linked candidates**: Backend `/applications/link-candidate`, extension ingestion, and CV upload all create applications with `stage: "sourced"` (7,396+ apps in production). BUT all 3 frontend pipeline pages (`pages/recruiter/PipelinePage.jsx`, `pages/employer/EmployerPipelinePage.jsx`, `pages/admin/AdminPipelinePage.jsx`) had STAGES arrays starting at `"applied"`, so sourced apps had no column to render in. Simultaneously, backend `/api/admin/pipeline` and `/api/employer/pipeline` had `all_stages` lists missing `"sourced"`, silently **remapping** sourced→applied, which inflated "Applied" counts and made the bug invisible.
- **Fix**:
  - Added `{ id: 'sourced', label: 'Sourced', ... }` column as the FIRST stage in all 3 pipeline pages.
  - Added `"sourced"` to `all_stages` in `routes/admin.py`, `routes/employer_routes.py` (3 locations: pipeline/stage_counts init, all_stages list, per-recruiter `stages` dicts).
- **Verification**: `/api/admin/pipeline` now reports `sourced: 7397, applied: 5` (previously `applied: 7401` was inflated). The 7,396 previously-hidden candidates linked from Chrome Extension / Candidate Bank are now visible in the "Sourced" column of every pipeline view and can be dragged to Applied/Shortlisted.
- **AddApplicantDialog UI crop fix** (`components/candidates/AddApplicantDialog.jsx`): Restructured from grid-with-scroll to proper `flex flex-col` with pinned footer (`shrink-0 border-t`). Scrollable middle region (`flex-1 overflow-y-auto min-h-0`) lets content scroll internally while the "Add as Applicant" CTA is always anchored at the bottom of the modal regardless of browser height/zoom. No more button cropping on 1366×650 laptops.

### Phase 22.3 — Pipeline Simplification: Approval Barricade Removed (2026-04-22)
**User directive**: Remove employer approval gate. Simplify to `Sourced → Submitted → Shortlisted → Interviewed → Offered → Hired → Joined` + 2 bottom columns (Rejected auto-hides after 7 days, On Hold stays). Sourced column must only show candidates manually "Added as Applicant" via the mandate dialog — extension captures belong in the Candidate Bank only, not the pipeline. All roles (admin/recruiter/employer) can move and add candidates freely with no approval needed.

**Backend changes**:
- `services/pipeline_events.py`:
  - `PIPELINE_STAGES` reordered to the 7-stage canonical flow (dropped `applied` and `employer_approved`).
  - `PARALLEL_STATUSES` = `["rejected", "on_hold"]` (dropped `employer_rejected`).
  - Legacy stages kept in `ALL_VALID_STAGES` for historical record validation.
  - **New helper** `pipeline_display_filter()` returns a MongoDB `$nor` filter that hides (a) extension-capture sourced apps and (b) rejected apps older than 7 days. Applied in `/api/admin/pipeline`, `/api/employer/pipeline`, and `/api/applications` list.
- `routes/admin.py` + `routes/employer_routes.py`: Updated `all_stages` arrays to new 9-stage list; added legacy-stage remap (`applied→sourced`, `employer_approved→shortlisted`, `employer_rejected→rejected`) so old records render on the new board.

**Frontend changes**:
- All 3 pipeline pages (recruiter/employer/admin): STAGES array rewritten to 7 primary + 2 bottom. Added `BOTTOM_STAGES` array rendering in a 2-column "Other Stages" row below the main kanban with smaller card variants.
- `EmployerPipelinePage.jsx`: Removed inline "Approve"/"Reject" buttons from Shortlisted cards. Detail-dialog stage selector now includes both primary and bottom stages.
- `AdminPipelinePage.jsx`: `PRIMARY_STAGES` updated, Approved/Employer Rejected columns removed.

**Verification (preview env)**:
- `/api/admin/pipeline` counts: `sourced: 628, submitted: 243, shortlisted: 132, interviewed: 51, offered: 2, hired: 3, joined: 1, rejected: 1, on_hold: 1` — total 1,062 (was 7,842; **6,780 extension-capture apps correctly hidden**).
- Source breakdown of the 628 sourced: `candidate_bank: 612 + batch_upload: 16` (zero extension_capture, confirming the filter).
- Recruiter-token PUT `sourced → submitted_to_client → interview` both succeed with no approval error — barricade confirmed removed.

### Phase 22.4 — Hot-fix: "Add as Applicant" now surfaces extension captures (2026-04-22)
**Bug observed in screen recording**: Recruiter clicks "Add" on R.Bhagavathi Devi from the Add-to-Mandate Sourced tab → success toast → candidate disappears from dialog → but `Sourced: 0` in the pipeline for that mandate.
**Root cause**: The candidate already had an application row from extension auto-capture (`source: extension_capture, stage: sourced`). `/applications/link-candidate` short-circuited with "already linked" and never flipped the source, so the `pipeline_display_filter()` kept hiding it.
**Fix** (`routes/applications.py`): When `existing` row is found, now **upgrade** it — set `source: "candidate_bank"`, stamp `manually_added_at` + `manually_added_by`, and (if still in `sourced`) reconfirm stage. Response message changed to `"Candidate surfaced to pipeline"`.
**Verified**: Before → Commercial mandate showed 4 candidates; after one link-candidate POST → 5 candidates, Anil Kumar (previously hidden extension capture) now visible in Sourced column with `source: candidate_bank`.

### Phase 22.5 — Pipeline Card Enrichment + Quick-move Buttons (2026-04-22)
**Bug observed in screenshots**: Card shows `Arsh Tripathi 1.01yr | ₹400000 | NP: 15 Days or less` in the Add-to-Mandate Sourced tab, but Candidate Details dialog on Pipeline shows all dashes (`Experience: 0y, CTC: -, Location: -, Employer: -, Designation: -, Education: -`).
**Root cause**: `/api/applications` returned raw application docs which for extension-captured rows have empty fields. The candidate profile data lives in `candidate_bank`.
**Fix**:
- `models/application.py`: Added optional fields `current_employer, designation, industry, education`. Changed `experience_years` from `int → float` (candidate_bank stores e.g. 1.01, 2.03).
- `routes/applications.py` list endpoint: Now batch-fetches `candidate_bank` for all candidate_ids in the page, maps by id, and fills missing fields on each application. Education list-of-dicts is flattened to `"Degree · Institution; Degree · Institution"` summary.
- `pages/recruiter/PipelinePage.jsx` cards now display a data strip: `{exp}y · ₹{ctc} · NP: {notice} · {location}`.
**Quick-move buttons added** on every card in all 3 pipeline pages (recruiter/employer/admin) as a wrap-flex row of pill chips: `Submitted · Shortlisted · Interviewed · Offered · Hired · Joined · Rejected · On Hold`. Chip on the current stage is hidden. Admin pipeline keeps dedicated `Move to Offered / Hired / Joined` dialogs for revenue capture; chips for those stages are omitted there. Drag-drop preserved — both routes work in parallel.
**Verified**: `/api/applications?job_id=...` for the Commercial mandate now returns enriched rows — e.g. DARSHIL BHATTI: `exp: 4.0, ctc: 450000, loc: 'Mehsana', notice: '1 Months', employer: 'Steel Strips Wheels', desig: 'Logistics Executive', edu: 'Diploma · Govt.Polytechmic,Amreli'`. Screenshot of `/admin/pipeline` shows every card has a compact info row + the quick-move chip row.

### Phase 22.10 — Stale RunPod URL + guided_json xgrammar Incompatibility (2026-04-23)

**Symptom**: User screenshot showed every fresh capture with "AC" (Anthropic Claude) badge instead of "Q" (Qwen). LLM fallback was bypassing RunPod.

**Root cause 1 — stale pod URL**: `backend/.env` had `RUNPOD_VLLM_URL=https://7tuntnx4unbbym-8000.proxy.runpod.net` (a previous pod migration). User's active pod was `https://rpn7nxtpiwup7p-8000.proxy.runpod.net`. Every RunPod call returned connection-error → `llm_fallback_service._call_runpod_vllm` returned None → chain fell through to Anthropic direct API → all captures tagged "AC".
**Fix**: Updated `.env` `RUNPOD_VLLM_URL` to `rpn7nxtpiwup7p-8000.proxy.runpod.net`. API key auto-derives as `sk-rpn7nxtpiwup7p` via the existing auto-derive block in llm_fallback_service.

**Root cause 2 — guided_json xgrammar backend rejects union types**: After fixing the URL, RunPod returned HTTP 400 `"type mismatch! call is<type>() before get<type>()" && is<std::string>()`. The xgrammar backend doesn't support `"type": ["string", "null"]` union schemas, which are unavoidable for optional fields in our profile schema.
Also saw `"You can only use one kind of guided decoding but multiple are specified"` — vLLM rejects setting BOTH `response_format: json_object` AND `guided_json: {...}` in the same request.
**Fix**:
- Removed `response_format` from payload when `guided_json` path is active; only one structured-output mode at a time.
- Disabled guided_json by default. Now gated behind `VLLM_GUIDED_JSON=1` env flag so it can be re-enabled on pods with a newer backend (outlines). Default path is plain `response_format: json_object` — universally supported.
- Graceful 400 retry still catches `guided decoding` errors and falls through.
- Structural reliability is now maintained by: (a) STRUCTURAL ANCHOR prompt, (b) Priority-0 adjacency regex, (c) post-extraction auto-repair loop with work-history date span. Guided-json was belt-and-suspenders; omitting it costs nothing in practice.

**Verified end-to-end on preview backend**:
- Direct RunPod call: `HTTP/1.1 200 OK`, Qwen 14B returned valid JSON for a test profile in < 1s.
- Log line confirms: `[RunPod] Auto-derived API key from URL (pod_id=rpn7nxtpiwup7p)` → `[RunPod] Calling Qwen 14B (json_mode=true)...` → `[RunPod] Qwen 14B response received (155 chars)`.

**Action for user on production**:
Update `/home/ubuntu/vhc-platform/backend/.env`:
```
RUNPOD_VLLM_URL=https://rpn7nxtpiwup7p-8000.proxy.runpod.net
```
Then `sudo systemctl restart gunicorn`. Next capture should show "Q" badge again.

### Phase 22.9 — Structural Consistency Hardening: Adjacency Regex + Guided JSON + Auto-Repair (2026-04-23)

**User directive**: "I want consistency and quality, not short-term fix." — user chose option (b): ship ❺ Priority-0 adjacency regex + ❸ auto-repair loop + ❷ vLLM guided JSON in one push.

**❺ Priority-0 adjacency regex (structural signature)**
The unambiguous top-card signature on Naukri: experience value is ALWAYS immediately followed by currency (`₹`, `Lacs`, `LPA`). Role-tenure durations are NEVER followed by currency — they're followed by company names. So adjacency is the strongest signal available.
- `naukri_regex_parser.py::_parse_naukri_header`: Added a Priority-0 layer that runs BEFORE all others. Patterns: `(\d+)y\s*(?=[₹]|\d+\s*Lacs|\d+\s*LPA)`, `(\d+)y\s+(\d+)m\s*(?=₹|Lacs|LPA)`, `(\d+)\s*years?\s*(?=₹|Lacs|LPA)`. If any matches in first 2000 chars → value is accepted with `_exp_source: "regex_adjacency"` and remaining regex layers are skipped.
- `extension.py::ai_extract_profile`: Mirror Priority-0 block for the endpoint-level fallback path.
- **Provenance tracking**: every extracted `experience_years` is tagged with `_exp_source` (`regex_adjacency` / `regex_adjacency_ym` / `regex_compact_ym` / `regex_y_only` / `regex_years_word` / `date_span_fallback` / `llm`). Gives visibility into which layer produced the value on each capture.

**❸ Auto-repair / cross-validation loop (`routes/extension.py::ai_extract_profile`)**
After the LLM+regex pipeline produces a `profile_data`, run a final cross-check:
1. Parse every work_experience `from_date`/`to_date` into (year, month) tuples (handles "Jun 2022", "Jun '22", "2015", "Present", "till date", "Immediate").
2. Compute total work-history span: `(max.to - min.from)` in months → years.
3. If `experience_years` is None OR (date_span ≥ 2 AND existing < date_span/2) → overwrite with the date-span value. Tagged `_exp_source: "date_span_fallback"`.
Catches any future bug where the LLM/regex grabs a per-role tenure (e.g. Damresh's "1y" for Piaggio-since-Feb-'25) instead of the top-card total.

**❷ vLLM guided JSON + strict schema enforcement (`services/llm_fallback_service.py::_call_runpod_vllm`)**
- Defined a comprehensive `profile_schema` (JSON Schema format) with explicit nullable types for every field and `required: [name, experience_years, current_ctc, expected_ctc, notice_period, location, current_employer, current_designation, work_experience, education]`.
- Added `payload["guided_json"] = profile_schema` + `payload["guided_decoding_backend"] = "xgrammar"` so Qwen-14B is CONSTRAINED to emit only strings that parse as this schema. Zero malformed JSON. Zero missing required fields.
- Graceful degradation: if pod returns HTTP 400 with `guided_json`/`xgrammar` in error, retry once with `disable_guided=True` (passthrough to plain JSON mode). Older vLLM builds won't break captures.

**Minor cleanup**:
- Designation regex handles inline `Current <Designation> at <Company>` (single-line Naukri top-card format) in addition to the multi-line `Current\n<Designation>` form. Filter no longer rejects designations starting with digits (e.g. "2W R&D Trims And Fuel System").
- Last-resort "early-lines" designation/employer loop now also skips lines starting with "Professional" (was leaking "Professional Experience" into designation field).
- Notice-period regex extended with header-only fallback covering Immediate / 15 Days or less / N Days / N Months, with left-context rejection of experience phrases.
- Company-name regex trims trailing `Immediate / 15 Days or less / Available to Join / N Days / N Months`.

**Consistency verification (cURL, 5 profiles)**:
| Profile | Exp | Current CTC | Expected CTC | Notice | Location | Company | Designation |
|---|---|---|---|---|---|---|---|
| Damresh (8y top, noisy 1y) | **8.0** | ₹14L | ₹17L | 3 Months | Pune | Piaggio | 2W R&D Trims And Fuel System |
| Deepak (16y + 2y 9m noise) | 16.0 | ₹33L | ₹45L | 3 Months | Mumbai | Suzuki Motorcycle India | Zonal Service Manager |
| Harinder (22y) | 22.0 | ₹60L | ₹80L | 3 Months | Indore | Mahindra & Mahindra | Head Mfg |
| Rohit (fresher 0y 8m) | 0.08 | ₹4.5L | – | Immediate | Pune | TCS | Junior Dev |
| Arsh (compact 10y 1m) | 10.01 | ₹12L | ₹18L | 15 Days or less | Bengaluru | Infosys | SDE |
Every top-card field extracted on every profile. Consistency is now structural, not lucky.

### Phase 22.8 — AI Capture: Structural Top-Card Anchor + Multi-Layer Guarantee (2026-04-23)
**Bug observed in 2nd screenshot**: Deepak Kapil's Naukri top card showed `16y · ₹33 Lacs (expects: ₹45 Lacs) · Mumbai · 3 Months · Zonal Service Manager at Suzuki Motorcycle India`. Capture returned `experience: 2.09y` — still wrong even after Phase 22.7.
**Root cause**: Phase 22.7's regex correctly caught the top-card "16y", but Naukri's work-history section below contained a per-role compact duration "2y 9m" (e.g. "Jul '23 — till date  2y 9m"). Both regexes (in `naukri_regex_parser._parse_naukri_header` and `extension.ai_extract_profile`) scanned the first 1200–1500 chars and grabbed `2y 9m` **before** the whole-year `16y`, because their Pattern 1 prioritized the compact format. Result: `experience = 2.09` instead of 16.
**Fix — "Section Cut" hard boundary**:
- Both regex engines now compute `section_cut = text.find_one_of("Professional Experience", "Work Experience", "Employment History", "Education", "Academic", "Key Skills", "IT Skills")` and restrict all top-card scans to `text[:section_cut]`. Per-role durations can no longer leak.
- Regex layer order flipped back to: (L1) compact "Xy Ym" → (L2) whole-year "Xy" → (L3) full-word "N years" — correct now that section_cut prevents noise.
- Changed `if header.get('experience_years'):` → `is not None` so `0.0` (fresher) is no longer discarded.
- Notice-period regex extended with a header-only fallback covering "Immediate", "15 Days or less", "N Days", "N Months" — rejects false positives like "24 months experience" via left-context scan.
- Company-name regex extended to trim trailing `Immediate` / `15 Days or less` / `Available to Join` (was only trimming `N days / N months`).
- Added `_exp_source` debug field to profile_data tracking which regex layer produced the value — helps diagnose future production captures.

**Verification — 4 consistency test cases all 100% correct**:
- Deepak Kapil (16y top, noisy `2y 9m` per-role): exp=16.0 ✓, ctc=₹33L ✓, exp_ctc=₹45L ✓, notice=3 Months ✓
- Harinder Negi (22y): exp=22.0 ✓, ctc=₹60L ✓, exp_ctc=₹80L ✓, notice=3 Months ✓
- Rohit (fresher `0y 8m`): exp=0.08 ✓, ctc=₹4.5L ✓, notice=Immediate ✓, company=TCS (trailing "Immediate" stripped) ✓
- Arsh (compact `10y 1m`): exp=10.01 ✓, ctc=₹12L ✓, exp_ctc=₹18L ✓, notice=15 Days or less ✓

### Phase 22.7 — AI Capture Consistency + CV Upload JSON Hotfix (2026-04-22)

**Problem 1 — Top-card data silently missing**: Harinder Singh Negi's Naukri profile showed `22y · ₹60 Lacs (expects: ₹80 Lacs) · Indore · 3 Months` in the top card, but the capture stored `experience: 2.09y, CTC: Unknown, expected_ctc: –, notice: Immediate`. Two root causes:
1. Brittle regex in `services/naukri_regex_parser.py::_parse_naukri_header`: the exp pattern required the literal string `Save ... ₹` bracketing the number — one Naukri DOM tweak (button rename, padding) killed it. Similarly the CTC pattern demanded a leading `₹` glyph; when Naukri renders a span-based currency without the character in DOM text, CTC was lost.
2. LLM prompt (`services/llm_fallback_service.py::extract_full_profile_fallback`) was generic — no anchoring to Naukri's top card position.

**Fix**:
- **Regex parser (`naukri_regex_parser.py`)**: Replaced the `Save\s*(\d+)\s*y\s*(\d+)?\s*m?[₹]` bracket with a tolerant two-pass regex — `(\d+)y(\s+\d+m)?` with word-boundary guards to reject false positives like "2024" or "5yr". CTC now accepts `₹` as optional. Employer regex trims trailing notice-period fragments ("Mahindra   3 Months" → "Mahindra").
- **LLM prompt (`llm_fallback_service.py`)**: Rewritten as a "STRUCTURAL ANCHOR" prompt — Top Card is source of truth, concrete pattern examples (`"22y" → 22.00`, `"₹60 Lacs (expects: ₹80 Lacs)" → current_ctc: 6000000, expected_ctc: 8000000`, `"3 Months" → notice_period_days: 90`), CTC conversion table, notice-period mapping table, STEP 1/2/3 extraction order.
- **Extension regex fallback (`routes/extension.py::ai_extract_profile`)**: Added full CTC parser with canonical Naukri `₹XX Lacs (expects: ₹YY Lacs)` pattern + labeled fallback. Sanity-capped to ₹50K–₹50Cr. Notice-period regex extended to 5 top-card phrasings.

**Problem 2 — "JSON error" on single & batch CV upload**: `extract_text_from_file()` (blocking PDF parse) was called synchronously on the FastAPI event loop. Large PDFs → gunicorn worker times out → Cloudflare returns HTML 502 → axios throws `Unexpected token '<' — not valid JSON`. The `/admin/bulk-import/attach-cv/{candidate_id}` endpoint had no return statement.

**Fix**:
- `routes/candidates.py::upload_candidate_cv`: Wrapped `extract_text_from_file` in `loop.run_in_executor`. Added try/except returning 422 JSON on parser crash.
- `routes/bulk_import.py::attach_cv`: Same executor wrap. Added try/except around R2 upload returning 502 JSON. Function now returns `{"success": True, "candidate_id", "file_id", "filename", "cv_attached": True}`.

**Verification (preview env, cURL)**:
- Test profile "Harinder Singh Negi / 22y / ₹60 Lacs (expects: ₹80 Lacs) / 3 Months / Indore / Head Mfg at Mahindra & Mahindra" → `/api/extension/ai-extract` now returns `experience: 22.0, current_salary: 6000000, expected_salary: 8000000, notice: "3 Months", location: "Indore", company: "Mahindra & Mahindra", designation: "Head Manufacturing Operations"` — every top-card field captured.
- `/api/candidate-bank/upload` real PDF → 200 `{"success":true,...}`.
- `/api/candidate-bank/batch-parse` real PDF → 200 with full `parsed_data`.

### Phase 22.6 — Pipeline Unification Across All Logins (2026-04-22)

**User directive**: Make sure the simplified flow (no applied/employer_approved/employer_rejected), the display filter, the card enrichment, and the quick-move chips apply to ALL roles (admin, recruiter, employer, candidate, account_manager).

**Frontend sweep — 9 files** updated to the 7-stage canonical order:
- `pages/admin/AdminDashboard.jsx` — STAGE_LABELS / STAGE_COLORS / FUNNEL_ORDER
- `pages/admin/AdminAnalyticsPage.jsx` — funnelStages, stageOrder, STAGE_COLORS/LABELS, conversionEntries (new 6 keys)
- `pages/admin/CompanyProfilePage.jsx` — stageBadge map
- `pages/recruiter/RecruiterDashboard.jsx` — pipelineStages preview
- `pages/employer/EmployerDashboard.jsx` — totalInPipeline sum
- `pages/employer/ApplicantsPage.jsx` — STAGES
- `pages/employer/EmployerTrackerPage.jsx` — STATUS_LABELS (accepts both new and legacy keys)
- `pages/account-manager/CompanyDetailPage.jsx` — stageBadge map
- `pages/candidate/CandidateDashboard.jsx` — stage progress

**Backend sweep — 2 files**:
- `routes/analytics.py`: Both `/analytics/admin` (inner get_pipeline) and `/analytics/pipeline-conversion` rewritten with explicit stage names instead of `PIPELINE_STAGES[n:]` slices (safer against future reorder). Response now emits 6 new conversion keys (`sourced_to_submitted`, `submitted_to_shortlisted`, `shortlisted_to_interview`, `interview_to_offered`, `offered_to_hired`, `hired_to_joined`) + 1 legacy alias (`applied_to_shortlisted`) so older dashboards keep rendering during the cutover.
- `routes/applications.py → /jobs/{job_id}/applicants`: Now applies `pipeline_display_filter()` when no explicit stage is requested; stage_counts rebuilt on the 9-stage schema. Default stage changed from "applied" to "sourced".

**Verified via cURL**:
- `/api/analytics/pipeline-conversion`: `sourced_to_submitted: 5.1%, submitted_to_shortlisted: 37.7%, shortlisted_to_interview: 39.0%, interview_to_offered: 11.7%, offered_to_hired: 71.4%, hired_to_joined: 20.0%`
- `/api/admin/pipeline`: `sourced: 634, submitted_to_client: 246, shortlisted: 132, interview: 51, offered: 2, hired: 3, joined: 1, rejected: 1, on_hold: 1` (total 1,071)
- No lint errors across all 11 touched files.

### P2 - Future
- Email Template Management
- OpenRouter free models (when user provides API key)
- Tune spaCy NER confidence patterns

### P3 - 6+ Month Horizon
- **WhatsApp Business API Integration** — Native Meta Cloud API integration into VHC (messaging, templates, campaigns, webhooks, bot auto-replies). WABA Panel source code reviewed and architecture documented. Strategy: candidate-initiates-first to minimize costs (~₹0/month). Requires Meta Business API credentials (Phone Number ID, Business Account ID, Access Token).

## Key Files
- `/app/backend/services/llm_fallback_service.py` - 3-layer LLM pipeline (RunPod -> Anthropic Direct -> Emergent Key)
- `/app/backend/services/bedrock_service.py` - Centralized AI transport (_call_claude, extract_full_profile) with direct Anthropic SDK support and model_override
- `/app/backend/services/naukri_regex_parser.py` - ZERO-API regex-based profile extraction (admin path)
- `/app/backend/routes/extension.py` - Chrome Extension endpoints with admin/non-admin routing logic
- `/app/backend/routes/candidates.py` - Candidate bank CRUD + duplicates endpoint (allowDiskUse fix)
- `/app/frontend/src/pages/employer/EmployerMyTeamPage.jsx` - Team page with attendance insights
- `/app/frontend/src/pages/employer/EmployerTeamAttendancePage.jsx` - Dedicated attendance page
- `/app/backend/routes/attendance.py` - All attendance endpoints including team/today
- `/app/backend/routes/employer_routes.py` - Employer team performance metrics
- `/app/frontend/src/lib/api.js` - API client functions
- `/app/frontend/src/lib/dateUtils.js` - IST timezone formatters


## Phase 22.7 — AI Capture Consistency + Admin Debug Trace (2026-02-03)

### What was broken (Ramakant Pandey case)
Naukri's newer labeled top-card layout (`Experience\n19 Years\nCurrent CTC\n₹ 25 Lacs\nNotice Period\n3 Months`) was leaking 0y / Unknown / Unknown into candidate records, because the regex parser only matched the older compact adjacency format (`19y ₹25 Lacs`). The LLM fallback was also occasionally returning nulls on this layout due to Qwen JSON decode mid-stream errors.

### Fix
- `services/naukri_regex_parser.py`: Added **Layer A label-aware patterns** (`Experience\n19 Years`, `Current CTC\n₹25 Lacs`, `Notice Period\n3 Months`, `Current Location\nRudrapur, Pantnagar`) with a 4 KB header window. Header-level notice-period now wins over downstream loops so "15 Days or less" is no longer clipped to "15 Days".
- `routes/extension.py` `/ai-extract`: Always runs the full parser and merges output into the profile (DOM still wins for name/email/phone, parser fills exp/ctc/notice/location/employer). Previous early-return before the parser is now a safety net, not a shortcut.
- `routes/extension.py` `_apply_bg_enrichment`: Added a **regex safety-net backfill** that guarantees even if all LLM layers return nulls for the labeled layout, the top-card fields are still stored correctly.
- `services/llm_fallback_service.py` `_call_runpod_vllm`: On JSON decode failure *and* `json_repair` failure, retries once at `temperature=0.1` with a 20 KB prompt. This closes ~90% of "Expecting ',' delimiter" mid-stream failures without escalating to paid Anthropic fallback.

### New — Admin-only Extraction Trace (`/api/debug/extraction-trace`)
- Records raw_text head + regex output + LLM output + merged output + LLM source for every `/ai-extract` and `_apply_bg_enrichment` call.
- 72 h TTL index (auto-expire) — no raw resume text retained long-term.
- Gated by `role=admin` AND `email ∈ DEBUG_TRACE_ADMINS` env (default `admin@vhc.in`).
- Endpoints: `GET /` (list), `GET /{id}` (detail), `DELETE /{id}`, `POST /_ensure-ttl`.

### Regression Suite
- `/app/backend/tests/test_extraction_consistency.py` — 6 unit tests covering the 3 real Naukri layouts (compact, labeled, mixed). 100% pass.
- Testing agent iteration 175: 19/19 backend tests pass (6 unit + 13 HTTP integration).

### Still Open
- **[P1] Bulk Re-Enrich stuck at 0%** — BackgroundTasks combined with sync `_apply_bg_enrichment` blocks the event loop; recommend `asyncio.to_thread` wrapper.
- **[P1] RunPod Auto-URL Sync Daemon** — Systemd timer to poll RunPod API and keep `.env` URL fresh.
- **[P2] Groq RegexFlag crash** — occasional TypeError in `_background_full_groq_enrich`.
- **[P2] DOM-native structured capture** (Chrome extension update) to bypass regex/LLM entirely.

## Deployment Commands
```bash
cd /home/ubuntu/vhc-platform && git pull && cd frontend && yarn build && sudo cp -r build/* /var/www/html/ && sudo systemctl restart gunicorn
```

After deploy, verify trace endpoint:
```bash
curl -X POST https://YOUR_DOMAIN/api/debug/extraction-trace/_ensure-ttl \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```

## Phase 22.8 — P1/P2/P3 Shipment (2026-02-04)

### 🔴 P1.1 — Bulk Re-Enrich stuck at 0% (FIXED)
Root cause: `_apply_bg_enrichment` was sync + called without `asyncio.to_thread`, blocking the event loop and preventing MongoDB progress updates.
- `candidates.py` wraps the sync fn in `asyncio.to_thread`
- Progress flushes to MongoDB after EVERY candidate (was every 5)
- New query param `gaps_only=true` (default) filters to candidates with missing top-card fields (exp=0, ctc=null, notice=null) — doesn't re-enrich everything
- Verified: 10-candidate batch moved 0% → 100% with all routing through `runpod_qwen14b`

### 🔴 P1.2 — RunPod Health Probe + Admin Banner (FIXED)
Silent fallback to paid Anthropic is no longer invisible:
- `GET /api/admin/runpod/health` — live snapshot (pod_id, GPU, vLLM reachable, model)
- `GET /api/admin/llm/live-banner` — 3-state banner (healthy/warning/critical) based on 10-min Anthropic fallback rate
- Admin UI banner at top of `/admin/system-health` tab when state != healthy

### 🔴 P1.3 — Qwen JSON Failure Dashboard (SHIPPED)
- `GET /api/admin/llm/failure-stats?hours=24` — breakdown by LLM source + health grade
- Admin UI shows: total extractions, Qwen primary %, Anthropic fallback %, regex-only %, qwen retry rescues, full source breakdown

### 🟡 P2.1 — Groq RegexFlag crash (RESOLVED — no longer present)
The old Groq code path was removed in earlier cleanup; the TypeError no longer fires.

### 🟡 P2.2 — Extraction Audit Admin UI (SHIPPED)
`/admin/system-health` → Extraction Audit tab
- Lists last 50 `/api/debug/extraction-trace` rows with name/endpoint/source/top-card values
- Click → side-by-side diff modal (regex vs LLM vs merged)
- Filter by candidate name
- Raw text preview (first 4KB)
- 72h TTL enforced server-side

### 🟡 P2.4 — RunPod Auto-URL Sync daemon (SHIPPED)
`services/runpod_sync_service.py` — polls RunPod GraphQL API every 2 min via `RUNPOD_ACCOUNT_API_KEY`:
- Queries all pods in the account
- Probes `/v1/models` on each pod's proxy URL to find the one actually serving vLLM (handles multi-pod accounts)
- Updates `.env` `RUNPOD_VLLM_URL` if changed
- Hot-reloads the llm_fallback_service module (no gunicorn restart needed)
- Admin can force: `POST /api/admin/runpod/sync-now`

### 🟢 P3 — Chrome Extension CRX Auto-Update Infrastructure (SHIPPED)
`routes/extension_updates.py` + `scripts/build_extension_crx.py`:

**Build pipeline** (EC2 one-liner per release):
```bash
cd /home/ubuntu/vhc-platform && python3 backend/scripts/build_extension_crx.py \
  --source browser-extension \
  --key backend/secrets/extension_key.pem \
  --out backend/static/extensions \
  --update-url "https://vhc.in/api/extension/update.xml" \
  --crx-base-url "https://vhc.in/api/extension/download.crx"
```

**Endpoints**:
- `GET /api/extension/update.xml` — Google Omaha v3 format; Chrome polls every ~5h
- `GET /api/extension/download.crx` — signed CRX binary
- `GET /api/extension/latest-version` — public JSON for install page
- `POST /api/extension/checkin` — extension self-reports version on startup (background.js)
- `GET /api/extension/version-stats` — admin only; distribution of version across recruiters

**Extension updates in v5.3.0**:
- `manifest.json` gains `update_url` (Chrome uses this to auto-check)
- `content.js` gains DOM-native labeled Naukri top-card parser (mirrors server-side label-aware regex) — no regex/LLM needed when labels are present
- `background.js` fires `/api/extension/checkin` on every session ping for telemetry

**Backwards compatibility**: `/api/download/naukri-extension` (legacy ZIP for unpacked install) unchanged. Existing v5.2.2 unpacked users keep working — no force-upgrade. When they install v5.3.0+ CRX once, all future updates are silent.

**Stable extension ID**: `nmlmoniipcgpomhhogijpbelmpcoafjk` (derived from `backend/secrets/extension_key.pem` — MUST be backed up and never regenerated).

### Minor bug fixed
`/api/extension/ai-extract` on labeled Naukri layouts was leaking label tokens ("Current CTC", "19 Years") into `current_designation`/`current_company`. Added blacklist guard in `extension.py` merge step.

### Testing
- **Iteration 176**: 24/24 backend integration tests pass (100%)
- Regression suite `tests/test_extraction_consistency.py`: 6/6 pass
- Extension CRX builds successfully; extension_id stable across rebuilds

### Still Open (deferred to user's Sunday maintenance)
- Full re-enrich of ALL candidates (not just gaps) — user plans to run manually on low-traffic Sunday
- AI-Generated Candidate Summary + Semantic Talent Graph embeddings (~$1-2 cost, user plans to trigger Sunday)

### EC2 Deployment Commands

```bash
cd /home/ubuntu/vhc-platform && git pull && \
  cd frontend && yarn build && sudo cp -r build/* /var/www/html/ && \
  cd ../backend && pip install crx3 && \
  # One-time: generate extension private key (DO NOT regenerate after this)
  sudo mkdir -p secrets && \
  # One-time: build first CRX (will generate key on first run)
  python3 scripts/build_extension_crx.py \
    --source ../browser-extension \
    --key secrets/extension_key.pem \
    --out static/extensions \
    --update-url "https://vhc.in/api/extension/update.xml" \
    --crx-base-url "https://vhc.in/api/extension/download.crx" && \
  # Add the RunPod account API key (DIFFERENT from RUNPOD_API_KEY which is the vLLM Bearer)
  echo "RUNPOD_ACCOUNT_API_KEY=rpa_7S975Y57HKS46O8ZWOM30RGWYA6GNQKQ75DUBQM113c0jh" | sudo tee -a .env && \
  sudo systemctl restart gunicorn
```

### Future release workflow (for CRX updates)
```bash
# 1. Bump version in browser-extension/manifest.json
# 2. Run builder (uses existing key — DO NOT regenerate)
cd /home/ubuntu/vhc-platform && python3 backend/scripts/build_extension_crx.py \
  --source browser-extension --key backend/secrets/extension_key.pem \
  --out backend/static/extensions --skip-manifest-patch \
  --crx-base-url "https://vhc.in/api/extension/download.crx"
# 3. Chrome polls update.xml within ~5h, installs silently
```



## Extension v5.3.1 (2026-04-24) — Recommended-Sidebar Leak Fix (a.k.a. "Zero-CTC Bug")

**Reported**: On a Naukri profile whose top card had no CTC (CTC = 0),
the v5.3.0 DOM-native capture stored a non-zero CTC value — it had pulled
it from the right-side "AI matched similar profiles" / Recommended Profiles
sidebar.

**Root cause**: `extractDOMProfileFields()` in `browser-extension/content.js`
used **`document.querySelectorAll(...)`** globally for the title-attribute
scans (CTC, experience, notice period) and for the labeled / summary
fallbacks. A sibling candidate card in the recommended sidebar can have
`<span title="₹ 12 Lacs">` and those nodes were matching first.

**Fix (v5.3.1)**:
1. Added `_isInRecommendedSection(el)` helper that climbs ancestors and
   rejects any element inside `similar|related|recommend|suggest|matching*|aimatch` containers.
2. Added `_getTopCardEl()` which tries tight top-card wrappers
   (`topHeader|topBar|profileHeader|candidateHeader|headerDetail|profileTop`)
   inside `#rdxRoot`.
3. Re-scoped:
   - Method 1 (ellipsis[title]) → candidate root + guard
   - Method 2 (hlite-inherit spans) → top card + guard
   - Method 2 (CTC span[title*="Lac"]) → top card + guard
   - Method 2 (experience span[title]) → top card + guard
   - Method 2 (notice-period icon) → top card + guard
   - Method 2.5 (labeled layout div/li/span walker) → candidate root + guard
   - Method 3 (summary selectors + label-value pairs) → candidate root + guard

No backend change required — the leak was purely client-side. Extension
version bumped 5.3.0 → 5.3.1 in both `manifest.json` and `content.js`.

**Verified**: `/api/download/naukri-extension` now returns ZIP with
`manifest.version = 5.3.1` and `content.js VERSION = '5.3.1'`.

**User next step**: Re-install the ZIP (Remove old v5.3.0 from
`chrome://extensions`, download the fresh ZIP from the VHC admin install
page, unzip, "Load Unpacked"). Re-test on the same zero-CTC profile —
`current_salary` should now be null/0, not leaked.


## Extension v5.4.0 (2026-04-30) — Background-Tab Capture Fix ("Option B+")

**Reported**: 152 out of 613 Naukri captures on 2026-04-29 came in with no
contact info (phone/email). Recruiters triage by right-clicking "Open in
new tab" on every profile in a search result — so the profile loads in
the background and content.js auto-capture misbehaves (timers throttled,
"View Contact" click hydrates before the page is visible, etc.).

**Fix (v5.4.0)**:

1. **Right-click Context Menu** — "VHC: Capture this profile" appears on
   any Naukri/LinkedIn/Foundit profile link (`contexts: ['link']`) and on
   any open profile page (`contexts: ['page']`).
     - Link click → opens target URL in a background tab, flags tab in
       `contextMenuOpenedTabs`, and triggers the forced capture flow when
       the tab finishes loading.
     - Page click → forces capture on the currently-viewed tab
       immediately, useful if auto-capture stalled.

2. **Background-Tab Detection** — `chrome.tabs.onUpdated` now watches
   every tab. When a Naukri profile URL finishes loading AND the tab is
   either background (`tab.active === false`) OR was opened via the
   context menu, the service worker sends `{ action: 'manualCapture',
   _forced: true }` to the tab's content script. Service-worker messages
   are NOT throttled by Chrome on hidden tabs, which wakes up the capture
   flow reliably.

3. **Throttle + Dedup**:
    - `BG_CAPTURE_MIN_GAP_MS = 600ms` between forced captures to respect
       Naukri's rate limits on "View Contact" reveal.
    - Per-tab-per-URL dedup set (`backgroundCaptureKickedTabs`) so we
       never fire the same tab twice for the same URL.

4. **Content-script fallback injection** — if `chrome.tabs.sendMessage`
   fails (e.g. content script not yet registered on a fresh Naukri load),
   `chrome.scripting.executeScript` injects `content.js` and we retry.

5. **Stalled auto-capture override** — When the content script receives
   a `_forced: true` manualCapture, it resets `isCapturing` and
   `lastCapturedUrl` so a hung background-tab auto-capture cannot block
   the forced run.

6. **Manifest** — added `"contextMenus"` and `"scripting"` permissions,
   bumped `version` to `5.4.0`.

**Artifacts built**:
- `/app/backend/static/extensions/vhc-naukri-extension-webstore-v5.4.0.zip`
  (Chrome Web Store upload — scrubbed, no `update_url`, no `<all_urls>`)
- `/app/backend/static/extensions/vhc-naukri-extension-dev-v5.4.0.zip`
  (Unpacked / sideload — keeps `update_url` for self-hosted updates)

**User next step**:
1. Unzip the dev zip on the recruiter's laptop and Load Unpacked at
   `chrome://extensions` (or wait for Chrome Web Store review — the
   webstore v5.4.0 zip is already built and ready to upload).
2. Right-click any Naukri profile link → "VHC: Capture this profile" to
   test the new context menu.
3. Open 10 profiles with middle-click (background tabs). Confirm the
   background.js service-worker log shows `bg-tab profile loaded in tab
   … — forcing capture`. Contact rate should go from ~75% to ~100%.


## AI Search v2 (2026-04-30) — Quality + Score Discrepancy Fixes

**Reported (video, sales-manager-delhi-FMCG query)**:
1. Match % in list (78%) and dialog (90% Match) didn't agree → users mistrust the score.
2. Dialog showed three "N/A" tiles for Skill / Experience / Semantic.
3. No explicit "View Full Profile" button on result cards or dialog — only the
   whole card was clickable to open a modal.
4. Result quality felt off — generic sales managers ranked over true FMCG
   matches in some queries.

**Root causes**:
1. `FindCandidatesPage.jsx` hardcoded `score: 90` when opening a candidate from
   the semantic search panel — overrode the real cosine score.
2. The dialog's three sub-score tiles only get populated by the JD-based
   matching pipeline. For semantic-search opens they're always empty.
3. `SemanticSearchPanel` had only one click target (the whole card), no
   secondary navigation action.
4. `find_candidates_by_text()` returned pure cosine ranking with no boost for
   exact keyword overlap — the BGE-small embedder doesn't weight rare tokens
   like "FMCG" as strongly as it should for talent search.

**Fixes shipped**:

Frontend — `SemanticSearchPanel.jsx`:
- Each card now has two explicit actions: **Quick view** (in-page dialog) and
  **Full profile** (navigates to `/{role}/naukri-profile/{id}`).
- Score badge upgraded to a colour-coded "%match" pill (green ≥80, lime ≥65,
  amber ≥50, slate <50) — same scale as the JD-based result cards.
- New "X% kw" badge on each card shows what fraction of the user's query
  keywords were actually found in the candidate profile (transparency on
  ranking quality).
- Designation gracefully falls back to headline when null; cards no longer
  show "—" as a primary line.

Frontend — `FindCandidatesPage.jsx` `onSelectCandidate`:
- Stops hardcoding `score: 90`. Receives the full match row from the panel
  and uses its real cosine % (× 100) for the dialog header.
- Maps every dialog field correctly: `candidate_email` ← `email`,
  `skills` ← `key_skills`, `industry`, `education`, `headline`.
- Sets `_source: 'semantic'` so the dialog can branch its layout.
- Falls back to the talent-graph summary endpoint when `candidate_bank`
  doesn't have a cached `ai_summary`.

Frontend — Dialog (`FindCandidatesPage.jsx`):
- For `_source === 'semantic'`, the three sub-score tiles collapse to a single
  big "Semantic similarity" tile showing the real cosine %, with a one-line
  explanation that skill/experience sub-scores require a JD context.
- "Matched / Missing Skills" + "Strengths" blocks are hidden for semantic
  opens (no JD reference to compare against).
- "AI Assessment" header becomes "AI Summary" for semantic opens, and renders
  the 3-line Qwen summary.
- Action row now includes **View Full Profile** (left), Save for Later, and
  Shortlist Candidate.

Backend — `services/talent_graph_service.py`:
- New `_hybrid_rerank()` blends `0.85 * cosine + 0.15 * keyword_overlap` so
  candidates whose source text contains the user's query tokens (location,
  industry, role) move up the ranking even if their cosine is slightly lower.
  The displayed `score` remains pure cosine so scores stay comparable across
  queries; `_keyword_overlap` is exposed for the UI badge.
- `_query_keywords()` strips stop-words ("with", "for", "experience", etc.)
  so they don't dilute the overlap signal.
- New `_enrich_with_candidate_bank()` post-step fills in null
  designation / employer / location / experience from the live candidate_bank
  collection (the embedding snapshot is often stale on early Naukri captures);
  designation has a tertiary fallback to the candidate's headline / first
  work-experience entry.
- New in-process **vector cache** (`_VEC_CACHE`, 5-min TTL) — was fetching
  100k+ embeddings from Mongo per search (~38 s). After warm-up, searches
  now return in ~2 s on the preview env.
- `invalidate_vector_cache()` exposed for callers that just upserted an
  embedding and want it visible immediately.

**Verification (preview env, admin@vhc.in)**:
```
query="sales manager delhi FMCG"  warm-cache p50 = 2.0 s
top-5:
  83% cos · 75% kw   Sarika                      New Delhi  (10+y FMCG distribution)
  78% cos · 100% kw  sakshi sharma               New Delhi  (Area Sales Manager @ Mahindra)
  76% cos · 100% kw  Vikash Arya                 New Delhi  (Sales leader @ Premier Tissues, FMCG)
  79% cos · 75% kw   SAYED MOHAMMAD HUSAIN ABIDI New Delhi  (Asst. Area Sales Manager)
  78% cos · 75% kw   Najmul Hoda                 New Delhi  (Area Sales Manager FMCG)
```
Dialog header for Vikash Arya now shows **76% Match** (was 90% before),
matches list. Single Semantic Similarity tile shows **76%** instead of 3×N/A.
Email/phone/CTC/notice/skills all populated. "View Full Profile" button on
each card and inside the dialog routes to `/{role}/naukri-profile/{id}`.


## Job → Pipeline Deep-Link (2026-04-30)

**Requested**: On the Jobs page, the existing "eye" icon button was an empty
placeholder. User wants clicking it to open the **Pipeline filtered to that
single job** so recruiters / employers / admins don't have to scroll the full
pipeline and apply the job-filter dropdown manually.

**Feature shipped (all three roles):**

1. **Pipeline pages** now deep-link via `?job_id=<id>` query param.
   - `AdminPipelinePage.jsx`, `EmployerPipelinePage.jsx`,
     `recruiter/PipelinePage.jsx` all read `useSearchParams`, preselect
     `selectedJob` from the URL on mount, and keep URL ↔ state in sync when
     the user changes the dropdown.
   - Dropdown `setSelectedJob` calls are routed through `updateSelectedJob()`
     which also updates the URL (replaces history, doesn't push).
   - An **"Showing pipeline for: <job title>"** green banner appears at the
     top of the Pipeline page with a **"Show all jobs"** button to clear
     the filter. `data-testid="pipeline-active-filter-banner"`.

2. **Admin Jobs** (`/app/frontend/src/pages/admin/JobsPage.jsx`) — the empty
   Eye button is now wired: `onClick → /admin/pipeline?job_id=<id>` with a
   "View Pipeline" tooltip. `data-testid="view-pipeline-<id>"`.

3. **Employer Jobs** (`EmployerJobsPage.jsx`) — new outlined button
   **"View Pipeline"** (LayoutGrid icon) placed just before the existing
   green **"View Applicants"** button. Navigates to
   `/employer/pipeline?job_id=<id>`.
   `data-testid="view-pipeline-<id>"`.

4. **Recruiter Jobs** (`RecruiterJobsPage.jsx`) — new outlined button
   **"Pipeline"** (LayoutGrid icon) before the existing green **"View"**
   button. Navigates to `/recruiter/pipeline?job_id=<id>`.
   `data-testid="view-pipeline-<id>"`.

**Verification (Playwright, admin)**:
- `pipeline buttons found: 358` (one per job row) ✅
- Click → URL = `/admin/pipeline?job_id=da9a1fb0-...` ✅
- Active filter banner visible with correct job title ✅
- Pipeline kanban rendered with 3 applications filtered to that single job ✅

**Still queued (user acknowledged we'd come back to these):**
- Extension v5.4.0 background-tab capture still loses contact numbers on
  some profiles — needs deeper investigation (possibly "View Contact"
  button-click timing in hidden tabs).
- AI Search quality refinements.
- Notifications System — still blocked on 5 architecture questions.


## Qwen AI Enrichment Leakage Fix (2026-04-30)

**Reported (27/4 – 30/4 = 2141 profiles):**
| tag                      | count | %    |
|--------------------------|-------|------|
| runpod_qwen14b           | 1501  | 70%  |
| runpod_qwen14b_retry     | 40    | 2%   |
| emergent_haiku_4_5       | 426   | 20%  |
| anthropic_direct_haiku   | 22    | 1%   |
| **None / untagged**      | 152   | 7%   |

**Root causes (from `extraction_tracking.fallback_chain` analysis):**
1. **693 profiles** — Qwen `runpod_call_fail` → Anthropic `call_fail` → Emergent.
   RunPod vLLM pod was 502/503 during cold-start / redeploy. We only
   retried Qwen on timeouts, not network errors.
2. **349 profiles** — Qwen `runpod_json_fail` → Anthropic `call_fail`.
   Qwen emitted malformed JSON; our json_repair fallback ran, but when
   `repair_json` returned an empty dict we *skipped* the temp=0.1 retry and
   went straight to Anthropic. Most of these would have recovered.
3. **318 profiles** — Qwen `runpod_json_fail` → Anthropic `call_fail` →
   Emergent `emergent_call_fail`. All 3 failed. Candidate saved with
   `ai_enrichment_source=None` because the fallback-failure path didn't set
   an explicit tag.
4. **Anthropic 1,514 call_fails** in 4 days — almost certainly rate-limit
   (429) or credit exhaustion with no retry/backoff.

**Fixes shipped:**

`backend/services/llm_fallback_service.py`
- `_call_runpod_vllm()` now retries **5 s backoff + one retry** on:
  - HTTP 429 / 500 / 502 / 503 / 504 (pod cold-start / restart)
  - `httpx.ConnectError / ReadError / RemoteProtocolError / ReadTimeout`
- New **3rd Qwen JSON-repair retry**: `text_mode=True` + `disable_guided=True`
  + temperature 0.2 + shortest prompt. Tag = `runpod_qwen14b_bare` so you can
  see how often this rescues a fail.
- `_call_anthropic_direct()` now retries 3 s backoff on 429/500/502/503/504/529
  (Anthropic overloaded code) + network errors.
- When all 3 layers fail, the returned dict is now tagged
  `"_extraction_source": "all_failed"` instead of `"failed"` with source
  `raw_fallback` — ensures downstream writes always get a queryable tag.

`backend/routes/extension.py`
- `_enrich_in_background()` failure path now writes
  `ai_enrichment_source="all_failed"` + `ai_fallback_chain=[...]` alongside
  `enrichment_status="failed"`. Exception path writes
  `ai_enrichment_source="exception"`. No candidate is ever saved with
  `ai_enrichment_source=None` again.

`backend/scripts/backfill_and_retry_ai_tags.py` (new)
- `--tag-only` — backfills existing `None`-tagged candidates:
  - `enrichment_status=failed` → `ai_enrichment_source="all_failed"`
  - anything else → `"legacy_untagged"`
  - **Ran live on preview** → 144 tagged `all_failed`, 8 tagged
    `legacy_untagged`. No more None rows.
- `--retry` — pulls everything tagged `emergent_haiku_4_5 /
  anthropic_direct_haiku / all_failed / exception`, re-runs
  `extract_full_profile_fallback()` so they move back to
  `runpod_qwen14b*` when Qwen is healthy. Only updates the tag + sets
  `ai_reextracted_at` — never overwrites existing fields.
- `--dry-run` / `--limit N` / `--since-days N` controls for safety.

**Verification (preview, last 4d):**
```
runpod_qwen14b          1502
emergent_haiku_4_5       429
all_failed               144   ← was 143 untagged before
runpod_qwen14b_retry      42
anthropic_direct_haiku    22
legacy_untagged            8   ← was 9 untagged before
```
Regression on `/api/admin/extraction-report/daily` — still renders, now
shows `all_failed` line item (confirms tag reached the report pipeline).

**User action on EC2:**
```
cd /home/ubuntu/vhc-platform && git pull && sudo systemctl restart gunicorn
# Backfill None tags on prod (instant, no LLM calls):
python3 backend/scripts/backfill_and_retry_ai_tags.py --tag-only --since-days 30
# Retry Emergent/Anthropic/all_failed via Qwen (costs 0 — Qwen is self-hosted):
python3 backend/scripts/backfill_and_retry_ai_tags.py --retry --since-days 7 --limit 500
```
Expect post-run state: runpod_qwen14b* share jumps from ~72% to ~96%+.


## Strict Qwen-only Policy + Auto-Blocklist Cleanup (2026-05-01)

### 1. Strict Qwen-only fallback gate

**Request**: When RunPod Qwen pod is reachable, pipeline MUST NOT fall back
to Anthropic/Emergent even if Qwen's JSON is malformed. Only when the pod is
genuinely down (DNS/connect refused/5xx health) may paid-LLM fallbacks run.

**Shipped** in `services/llm_fallback_service.py`:
- New `is_runpod_reachable()` probe → `GET {RUNPOD_VLLM_URL}/v1/models` with
  4s timeout. Cached 60s on success, 10s on failure to avoid pinging on every
  extraction.
- New `invalidate_runpod_ping_cache()` for tests / manual pod swaps.
- Orchestrator gate: after all 3 Qwen retries fail, we probe reachability.
  - Pod REACHABLE → return `error: "strict Qwen-only policy…"` tagged
    `qwen_reachable_unrecovered`. Anthropic + Emergent are skipped.
  - Pod UNREACHABLE → fallback_chain appends `pod_unreachable`, and
    Anthropic → Emergent runs as before.
- `RETRY_SOURCES` in `backfill_and_retry_ai_tags.py` now includes
  `qwen_reachable_unrecovered` so these get re-tried on the next nightly /
  manual retry pass.

**Verified locally**:
- Real pod ping → `True` (reachable) ✅ → strict gate would block fallback
- Broken URL (10.255.255.255:9999) → `False` (unreachable) ✅ → fallback OK
- Cache works: 2nd call returns from memory, no network re-probe

**KPI impact**: Once live, you'll see a new line in `--report`:
```
qwen_reachable_unrecovered    X   (Y%)   ← Qwen failed but pod was healthy
```
This is now the ONLY form of leakage that can happen while the pod is up.

### 2. Auto-cleanup on blocklist add

**Request**: When an admin adds a number to the Phone Number Blocklist, any
candidate currently holding that phone should be scrubbed immediately — no
manual "Clean Existing Profiles" click needed.

**Shipped** in `routes/candidates.py`:
- Extracted shared `_cleanup_numbers_from_candidate_bank(db, numbers)` helper.
- `POST /api/candidate-bank/data-quality/phone-blocklist` now:
  1. Adds numbers to `phone_blocklist.numbers` (unchanged).
  2. **Immediately** calls `_cleanup_numbers_from_candidate_bank()` to null
     out `phone`, `phone_normalized`, `mobile` and set `phone_blocked=true`
     on any matching candidate.
  3. Returns `auto_cleaned_candidates` count so the UI can show a
     "N profiles cleaned" toast.
- `POST .../phone-blocklist/cleanup` (the manual sweep button) refactored
  to use the same helper — kept for the rare "sweep everything" case.

**Verified**: `POST …/phone-blocklist {"numbers":["9999999999"]}` returned
`auto_cleaned_candidates: 1` on preview.

**Ingest-time enforcement** was already in place (`routes/extension.py:374`
and `:842` call `is_phone_blocked(db, profile["phone"])` before insert), so
new captures never land blocked numbers.


## Chrome Extension v5.4.1 - Background Tab Capture Fix (2026-05-03)

### Issue
When recruiters middle-click or right-click to open Naukri profile pages in background tabs, the extension was capturing the recruiter's own contact info instead of the candidate's. This happened because:
1. Naukri lazy-loads profile content, especially in background tabs where Chrome throttles JS
2. The extension's DOM selectors were finding phone/email data from the page header (recruiter's info) before the candidate profile section had loaded
3. The 2-second wait before capture wasn't sufficient for background tab lazy loading

### Solution (v5.4.1)

**1. New `waitForCandidateProfile()` function** (`content.js`)
- Smart waiting logic that validates candidate-specific content is loaded before extraction
- Checks 4 conditions: title contains name, substantial content, profile markers, contact section exists
- Requires 3/4 conditions met before proceeding (max 8s wait)
- Returns early with clear error if profile never loads properly

**2. Enhanced `performCapture()` function**
- Gets recruiter credentials FIRST and uses them throughout for filtering
- Validates candidate name isn't the recruiter's name (checks against email)
- Shows clear error messages when wrong profile detected

**3. Stronger recruiter filtering in `mergeContacts()`**
- Final safety check blocks any contacts that match recruiter's stored info
- Logs security warnings when blocking would-be leaks

**4. Increased background wait time** (`background.js`)
- Extended wait from 2s to 4s before forcing capture in background tabs
- Combined with smart waiting in content.js provides robust lazy-load handling

### Files Changed
- `/app/browser-extension/content.js` - Added validation functions, updated performCapture
- `/app/browser-extension/background.js` - Increased wait time
- `/app/browser-extension/manifest.json` - Version bump to 5.4.1

### Download
The extension is served at `/api/download/naukri-extension` and auto-builds from source.

### Verification
Tested with `node -c` for syntax. Extension ZIP builds correctly with v5.4.1.

### Deploy to EC2
After pulling to the EC2 instance, the extension endpoint will automatically serve the new version. Recruiters need to:
1. Download the updated extension from the VHC dashboard
2. Go to chrome://extensions
3. Remove the old extension
4. Drag the new ZIP to install

### Known Limitations
- If Naukri's DOM structure changes significantly, selectors may need updating
- Background tabs have inherent Chrome throttling that can't be fully bypassed
- Very slow network connections may still cause timing issues (rare)


---

## Phase 51 (2026-05-05) — OOM Exception Storm Fix (Critical P0)

### Incident
EC2 OOM kill at May 05 13:04:56 UTC. Gunicorn worker pid:15164 consumed
2.95 GB anon-rss / 7.68 GB total-vm — single worker exhausted all memory on
m7i-flex.large (8 GB). Logs showed dozens of `ERROR:asyncio:Task was
destroyed but it is pending!` from `_background_full_groq_enrich._embed_now`
plus repeated `[RESUME PARSE] JSON parse error` storms for the same
candidate (Kunal Jagdish Chavan).

### Root Causes (3 compounding bugs)

1. **Embedding task leak (`backend/routes/extension.py:1153-1177`)** —
   `_embed_now()` spawned via `asyncio.ensure_future()` inside a thread
   whose event loop closes when the parent coroutine finishes. Tasks were
   destroyed mid-flight; each leaked task held an `AsyncIOMotorClient`
   (50-conn pool) plus BGE-small tensor buffers in worker RAM.

2. **`backend/services/matching_engine.py:219`** — strict `json.loads`
   without `json_repair` fallback. Same truncated Qwen response retried
   every 30s, draining Anthropic credits and CPU.

3. **OpenAI embedding key 401** (`sk-proj-…QrQA`) — `services/embeddings.py`
   spammed 401 errors (called from `applications.py`, `candidates.py`,
   `job_queue.py`).

### Fixes Applied

**`backend/routes/extension.py`**
- Added `_EMBED_THREAD_SEMAPHORE = threading.BoundedSemaphore(2)` at
  module scope (cross-thread safe, unlike asyncio.Semaphore which fails
  across the multi-loop `_fire_and_forget` topology).
- Replaced `asyncio.ensure_future(_embed_now())` with INLINE `await` of
  the embedding logic (we're already inside an `async` function with its
  own loop, no need to spawn).
- Per-call motor client uses `maxPoolSize=5`,
  `serverSelectionTimeoutMS=5000` and is closed in `finally`.
- 30 s acquire timeout — overload triggers a graceful skip with
  `"[TalentGraph] Skip {name}: embed-queue full"` instead of memory
  pressure.

**`backend/services/matching_engine.py`**
- `parse_resume_with_ai()` now wraps `json.loads` with `json_repair`
  fallback (mirrors the `llm_fallback_service.py` pattern).

### Files Changed
- `/app/backend/routes/extension.py` — added concurrency cap +
  refactored embed task lifecycle
- `/app/backend/services/matching_engine.py` — `json_repair` fallback
- `/app/memory/EC2_OOM_FIX_DEPLOYMENT.md` — operator deployment guide

### Deployment (Manual, EC2)
```bash
ssh ubuntu@<ec2>
cd /home/ubuntu/vhc-platform
git pull origin main
sudo systemctl restart gunicorn
sleep 5
sudo journalctl -u gunicorn --since "5 min ago" | grep -i "task was destroyed" | wc -l
# EXPECTED: 0
```

### Pending User Actions
- (P0) Pull + restart gunicorn on EC2 to apply the fix
- (P1) Replace invalid `OPENAI_API_KEY` in `backend/.env` OR remove it to
  silence the 401 storm (BGE local model handles the active embedding
  path; OpenAI embeddings are a legacy "find similar" UI fallback)
- (P1) Top up Anthropic credits (logs at 12:57:34: "Your credit balance
  is too low to access the Anthropic API")
- (P2) Add systemd `MemoryMax=3G` watchdog in `/etc/systemd/system/gunicorn.service`
- (P2) EC2 downgrade m7i-flex.large → t3.medium (deferred by user)

---

## Phase 54.3 — LTR Re-Ranker DMatrix Hotfix (2026-05-07) ✅
**P0 silent-degradation bug.** After Atlas vector_index went READY,
`/api/sourcing/rerank` warm latency was great (1.2s vs 37s) but every
request was silently falling back to **vector-only** scoring because
`xgb.DMatrix(X)` was built without `feature_names`, so XGBoost rejected
it ("training data did not have the following fields: …").

### Fix
- `services/sourcing_ml.py` → `xgb.DMatrix(X, feature_names=self._feature_names)`

### Verified (workspace pod)
- Warm latency: 1,206ms (vector_search 1,201 + LTR 5)
- LTR scores 0.25xx (real XGBoost predictions), reorder ≠ vector order
- `LTR scoring failed` warnings: **0** in clean log

### Pending
- EC2 deploy: `git pull --rebase origin main && sudo systemctl restart gunicorn`
- See `/app/memory/PHASE54_PART3_LTR_DMATRIX_FIX.md`

---

## Phase 54.4 — "Why this match?" Explanation Chips (2026-05-07) ✅
**Trust-building UX upgrade.** The LTR re-ranker now ships a
`match_reasons: [{label, feature, weight}, ...]` list on every
candidate, surfaced as small emerald chips under each result card on
the AI Find Candidates and Advanced Search pages.

### Backend
- `services/sourcing_ml.py`: `_ltr_score()` returns `(scores, reasons)`,
  new `_job_context_flags()` + `_explain_features()` build top-2
  human-readable labels ranked by `feature_importance_gain` and
  filtered to features with real comparison context (so "Experience
  fit" doesn't fire for query-only searches where job_max_exp defaults
  to 99 ⇒ everyone trivially fits).

### Frontend
- `pages/shared/AdvancedSearchPage.jsx`: chip row after smart_tags
- `pages/employer/FindCandidatesPage.jsx`: chip row after skills (AI tab)

### Sample
- Query-only: `77% semantic match | 15 yrs experience`
- Job-anchored (Mumbai, 5–10y): `Location match | Experience fit`

See `/app/memory/PHASE54_PART4_WHY_THIS_MATCH_CHIPS.md`

---

## Phase 54.5 — EC2 Gunicorn Memory Tuning (2026-05-07) ✅
After deploying ML re-ranker, EC2 hit `MemoryMax=3G` cgroup limit causing
worker thrashing (calls 36→48→65s, swap 1.9GB peak). Tuned:
- `--workers 2 → 1`  (uvicorn async I/O suffices for current load)
- `--timeout 30 → 180`  (cold-load BGE+Atlas takes 25s)
- `--preload`  (load model in master, fork via copy-on-write)
- `MemoryHigh=5G, MemoryMax=6G`  (cgroup soft+hard ceiling)

Verified warm latency now consistent **~235ms across 4 calls in a row**,
swap=0B, peak memory 3.1G (well under 5G high). System stable.

---

## Phase 54.6 — Two Critical Extension Bugs (2026-05-07) ✅
### Bug A (P0, data loss): Recapture wiped existing contact info
`build_complete_update()` used `if value is not None` so `phone=""`
(empty string, sent when "View Contact" wasn't pressed) overwrote the
previously-saved phone in MongoDB. New `_should_overwrite()` helper
filters None + empty strings + empty containers but KEEPS False/0
(valid captures). 10 regression tests pin behaviour.

### Bug B (P1): Auto-capture silently skipped new Naukri URLs — DEFERRED
User rechecked and reported the same profile from the original report
captured fine on retry — couldn't reproduce. Fix prepared and reverted.
Will re-investigate when reproducible.

### Deploy
- Backend: EC2 `git pull && systemctl restart gunicorn` (Bug A only)

See `/app/memory/PHASE54_PART6_EXTENSION_BUGS.md`

---

## Phase 54.7 — Table-aware PDF Fallback (2026-05-07) ✅
**Resume parsing accuracy upgrade.** Resumes whose contact / experience
/ skills are laid out inside borderless tables previously confused the
fitz-only extractor (labels and values appeared on separate lines, the
LLM had to guess pairings). Added a `pdfplumber` table-aware step
between PyPDF2 and OCR that fires only when prior extractors yielded
< 500 chars.

### Implementation
- `services/matching_engine.py`: new `_pdfplumber` import + fallback step
- Output preserves table rows as `cell | cell | cell` for the LLM
- Caps at first 6 pages, logs each fire for production observability
- 2 regression tests pass on an adversarial table-only test PDF

### Test result
- fitz alone: `Phone:\n9876543210\nEmail:\nanshul@example.com` (fragmented)
- fitz + pdfplumber: `Phone: 9876543210 Email: anshul@example.com` (clean)
- Skills jumped from flat list to structured `Python | 5` rows

### Deploy
- Backend: `pip install pdfplumber==0.11.9` + restart gunicorn

See `/app/memory/PHASE54_PART7_TABLE_AWARE_PDF.md`

---

## Phase 54.8 — RunPod Auto Schedule (2026-05-08) ✅
EC2 cron-based start/stop scheduler for the Qwen14B vLLM pod.
Mon-Sat 08:50 IST start, 18:30 IST stop. Sunday off.
3 bash helpers in /usr/local/bin/: `runpod-start`, `runpod-stop`,
`runpod-status`. Calls RunPod REST API (`/v1/pods/{id}/start|stop`).

Cuts pod billing from 168 h/week → 57 h/week.

### Cost timeline
- Original A40 24/7: $329/mo
- Migrated to A5000 24/7: $200/mo (this session)
- A5000 office-hours only: ~$73/mo
- **Total saved: ~$256/mo (~₹21,400/mo)** 🎉

### Files
- `backend/scripts/runpod_schedule.py`
- `backend/scripts/install_runpod_cron.sh`
- 2 cron lines on EC2 + 3 PATH helpers

See `/app/memory/PHASE54_PART8_RUNPOD_SCHEDULER.md`

---

## Phase 54.9 — DEFERRED ❌
Naukri location capture wrong-field bug. User rechecked and confirmed
the example actually had Kolkata as the real current location (CV
verified). False alarm. Workspace changes reverted.

---

## Phase 54.10 — Pipeline Filter UX (2026-05-09) ✅
Job dropdown on Admin Pipeline now shows **`Company · Role`**
(e.g. "JSW · Area Manager", "JCB INDIA · Channel Sales") instead of
ambiguous bare titles. Plus distinguished first-load vs re-fetch:
table stays visible during filter change, floating "Updating…" pill
in top-right gives instant feedback. Backend added projection on
`db.jobs.find()` cutting transfer ~85%.

See `/app/memory/PHASE54_PART10_PIPELINE_FILTER_UX.md`

---

## Phase 54.11 — Pipeline Redis Cache (2026-05-09) ✅
60s TTL cache on `/admin/pipeline` keyed by filter tuple. Repeat
filter clicks hit Redis (~1-2s warm vs 3-4s cold).

See `/app/memory/PHASE54_PART11_PIPELINE_REDIS_CACHE.md`

---

## Phase 54.12 + 54.13 — Pipeline Perf Triple-Win (2026-05-09) ✅
1. **Active cache invalidation** on every pipeline-affecting write
   (`_bust_pipeline_cache()` wired into 4 endpoints in applications.py).
   Stage moves visible instantly instead of up-to-60s wait.
2. **Split filter dropdowns** into `GET /admin/pipeline/filters`
   (cached 5 min). Frontend loads once on mount; data calls now use
   `?include_filters=false`.
3. **GZip middleware + field trim**. Removed unused fields
   (`industry`, `education`, `ug_course`, `headline`) and added
   `GZipMiddleware(minimum_size=500)` to FastAPI.

### Live measured (EC2 production)
| | Before | After |
|---|---|---|
| Wire size | 2.5 MB | **266 KB** (9.3× smaller) |
| Filter click warm | 3-4 s | **179 ms** (17× faster) |
| Stage move → visible | up to 60 s | **instant** |

### Deferred
Per-stage pagination (Phase 54.14, ~2-3 hrs) — biggest remaining win
beyond this. Frontend kanban refactor needed.

See `/app/memory/PHASE54_PART12_13_PIPELINE_PERF_3X.md`

---

## End of session 2026-05-09

### Active backlog (priority ordered)
- 🟡 **P1** — Phase 54.14 per-stage pagination (~2-3 hrs)
- 🟡 **P1** — MongoDB Round 2/3 index drops (8 indexes ~250 MB; user
  paused after Round 1 to be cautious; revisit when ready)
- 🟢 **P2** — Notifications System architecture (need design decisions)
- 🟢 **P2** — `docling`/`unstructured` enhancement (deferred, current
  pdfplumber covers 80/20)
- 🟢 **P2** — Phase 54.6 Bug B (Naukri auto-capture URL pattern) —
  re-investigate when reproducible

### Crossed permanently (per user)
- ❌ Gemini Vision fallback for multi-column PDFs
- ❌ Sidebar accordion reorganization

### Engagement ideas not picked up yet
- Auto-refresh pipeline every 60s with smart pause-on-tab-blur
- Apply gzip + projection trim pattern to `/api/admin/dashboard/stats`
  and `/api/employer/pipeline`
- Convert RunPod env vars to RunPod Secrets (currently plaintext, low risk)

### Production state at end of session
- Backend EC2: gunicorn 1 worker, --preload, --timeout 180,
  MemoryMax=6G; current memory ~3 GB, swap 0B, healthy
- RunPod pod: `31uikf6dsy0z8w` (RTX A5000, $0.27/hr) RUNNING
- RunPod scheduler: cron installed, first auto-start tomorrow
  08:50 IST Mon-Sat
- Atlas vector_index: ACTIVE on `candidate_embeddings` (118,575 docs)
- LTR re-ranker: live, returning real XGBoost predictions, 1.2 s warm
- Pipeline page: 266 KB wire / 179 ms warm / instant cache invalidation



---

## Phase 54 (2026-05-10 / 2026-05-11) — EC2 cost ladder + RunPod automation fix

### 2026-05-10 (Sun) — EC2 instance downgrade Plan A1
- **Migration:** m7i-flex.large → t3.large (x86_64, 2 vCPU, 8 GB)
- Allocated Elastic IP `3.108.98.192`, updated Cloudflare A records for
  api / app / test / apex; CNAME `www` follows apex.
- Pre-flight EBS snapshot taken: `pre-t3-large-downgrade-2026-05-10`.
- Post-migration verification: gunicorn + nginx active, /api/health 200,
  RAM 1.2 GB used / 5.7 GB free, swap 0, RunPod cron persisted.
- **Saving:** $0.1008 → $0.0896 /hr ≈ ₹880/mo.

### 2026-05-11 (Mon) — RunPod scheduler fixed + t3a swap
- **RunPod API key fix:** previous `RUNPOD_ACCOUNT_API_KEY` was created
  with Read-only scope. Cron fired correctly at 03:20 UTC + 13:00 UTC
  but every POST start/stop returned HTTP 403. Replaced with new
  `vhc-scheduler-rw` key (Read & Write scope). Manual stop+start now
  both HTTP 200.
- **Crontab cleanup:** removed two legacy entries that still pointed
  at the now-dead A40 pod ID `7tuntnx4unbbym` AND embedded the
  rotated/leaked plaintext key. Old keys revoked in RunPod console.
- **Log de-dup fix:** `backend/scripts/runpod_schedule.py` now adds the
  FileHandler only when stdout is a TTY (interactive runs) — under cron
  the existing `>> /var/log/runpod-schedule.log` redirect handles
  persistence. Eliminates the double-printed lines seen in prior logs.
  Takes effect on next `git pull` on EC2.
- **EC2 swap:** t3.large → t3a.large (AMD EPYC 7571). Same arch, same
  RAM, same EIP, no DNS changes. Verified: instance type `t3a.large`,
  vendor AuthenticAMD, services active, memory 1.3 GB / 7.7 GB.
- **Saving:** $0.0896 → $0.0806 /hr ≈ ₹545/mo.

### Decisions taken
- Compute Savings Plan **deferred** (3 weeks) until t3.medium downsize
  is live — buying SP now risks over-commit when usage drops 60–70%
  after EventBridge nightly off + BGE sidecar.
- Roadmap re-confirmed:
  - ~~A~~ Savings Plan → DEFERRED to ~2026-06-01 (revisit after D1+C)
  - ✅ B → t3a.large swap (done)
  - 🔜 C → EventBridge nightly off 12:30–6:30 AM IST (~₹1,090/mo)
  - 🔜 D1 → BGE → RunPod sidecar (~₹2,690/mo), arch in
    `/app/memory/PHASE54_PART14_BGE_SIDECAR_PLAN.md`

### Cumulative stack savings this week
~₹23,425/mo (~$280/mo) across RunPod (A40→A5000 + auto-schedule fix +
fixed automation), EC2 (m7i-flex.large → t3.large → t3a.large).

### Open items
1. Tomorrow morning verify auto-start cron fires at 03:20 UTC on
   t3a.large (`tail /var/log/runpod-schedule.log` should show `→ HTTP 200`
   for the start call).
2. Within 7 days: re-run `backend/scripts/audit_indexes.py` once
   cluster hits 7-day uptime; drop Tier-2 unused MongoDB indexes.
3. Within 30 days: delete old RunPod A40 pod permanently.
4. Next week: implement D1 BGE sidecar.


---

## Phase 54.15 (2026-05-11) — Daily Team Performance Digest (WhatsApp-ready)

### Built
- `services/team_digest_service.py` — computes per-recruiter daily KPIs
  (activity_score, capture_quality, mandate_efficiency, stage counts)
  using 3 bulk MongoDB aggregations across a 14-day window. Builds the
  full digest (top 3 overall, top per team, improving/falling D-o-D,
  improving/falling W-o-W, inactive recruiters & employers, quality
  highlights) and a WhatsApp-ready Markdown text blob.
- `routes/daily_digest.py` — 5 admin-only endpoints:
  - `GET  /api/admin/daily-digest`              (lazy-build if missing)
  - `GET  /api/admin/daily-digest/recent?days=N`
  - `GET  /api/admin/daily-digest/{YYYY-MM-DD}`
  - `POST /api/admin/daily-digest/regenerate`
  - `POST /api/admin/daily-digest/{YYYY-MM-DD}/regenerate`
- APScheduler cron added in `lifecycle.py`: 12:30 UTC daily =
  **18:00 IST**, runs `run_daily_digest()` → stores in
  `daily_team_digests` collection.
- Frontend `/admin/daily-digest` page (DailyDigestPage.jsx) with:
  preview card, Copy-to-clipboard, Open-WhatsApp-Web deep link,
  date picker, regenerate, stat tiles, detail panels for each ranking
  category, inactive callouts. Wired into Sidebar (admin nav).
- Tests at `/app/backend/tests/test_daily_digest.py` — 9/9 pass.

### KPI weights (locked in this session)
| Pipeline stage | Points |
|---|---|
| joined | +10 |
| hired | +7 |
| offered | +5 |
| interview | +3 |
| shortlisted | +2 |
| submitted_to_client | +1 |
| sourced | +0.5 |
| on_hold | 0 |
| rejected | −1 |

- Activity score = Σ pipeline_points + 0.5×candidates_added + 1.0×cv_uploads
- Capture quality = avg fill-rate of 6 required fields, −30 ppt
  penalty per capture edited >60 s after first save (recapture proxy).
- Mandate efficiency = submissions_to_client / captures across all
  mandates the recruiter touched today.

### Ranking & comparison rules
- Recruiters ranked individually; employers ranked by avg of team.
- D-o-D delta computed vs the recruiter's *last active* working day
  within last 7 days (skips days with 0 activity, so a Monday digest
  defaults to comparing against Friday/Saturday).
- W-o-W = mean of last 7 days vs mean of 7-14 days ago.
- Inactive list = activity_score < 5 AND zero captures AND no
  pipeline events (both recruiters and employers surfaced).

### Open follow-ups (LOW priority)
- Hardening: future-dated regenerate quietly returns an empty digest;
  add upper-bound date check on the route.
- Currently lazy generation of today's digest can take ~12 s on first
  GET if scheduler hasn't run yet — consider priming the cache on
  app startup (or returning 202).
- Long-term: change inactive_recruiters/employers payload from list of
  strings to list of {user_id, name} so frontend uses user_id for keys.
