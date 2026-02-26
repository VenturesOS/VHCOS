# AI Screening System — Complete Code Extraction & Audit Report
## VHC Talent OS — Prepared for External Code Review
**Generated**: February 2026

---

# TABLE OF CONTENTS
1. [System Overview & Architecture](#1-system-overview)
2. [File Inventory](#2-file-inventory)
3. [Dependency Map](#3-dependency-map)
4. [Data Flow](#4-data-flow)
5. [Known Risk Areas](#5-known-risk-areas)
6. [Environment Variables](#6-environment-variables)

---

# 1. SYSTEM OVERVIEW

The AI screening system has **three independent pipelines**:

| Pipeline | Entry Point | LLM Used | Latency |
|----------|-------------|----------|---------|
| **Quick Match** | `POST /api/applications/match` | None (deterministic) | 1-3s |
| **Full AI Match** | `POST /api/applications/match` (mode=full_ai) | GPT-5.2 via Emergent | 30-120s (background) |
| **AI Search** | `POST /api/ai-search` | gpt-4o-mini via OpenAI direct | 3-10s |

Two LLM clients coexist:
- `emergentintegrations.llm.chat.LlmChat` → Used by `matching_engine.py` (resume parse, JD parse, AI match scoring)
- `httpx` direct OpenAI call → Used by `llm_service.py` → consumed by `ai_search.py`

Two embedding systems:
- `openai.AsyncOpenAI` → `text-embedding-3-small` (1536 dims) → Used for semantic similarity
- In-memory + Redis caching layer for embeddings

---

# 2. FILE INVENTORY

## 2.1 Core Services (Backend Logic)

### `backend/services/matching_engine.py` (576 lines)
**Purpose**: Central AI scoring engine. Contains both LLM-based and fast (non-LLM) scoring.
**Key Functions**:
- `parse_resume_with_ai()` — GPT-5.2 resume → structured JSON
- `parse_job_description_with_ai()` — GPT-5.2 JD → structured JSON
- `calculate_candidate_job_match()` — GPT-5.2 candidate-job scoring (0-100)
- `apply_must_have_filters()` — Deterministic hard filters (location, exp, skills, qualification)
- `find_similar_candidate()` — Deduplication via email > phone > fingerprint
- `generate_resume_fingerprint()` — SHA256 of normalized resume text
- `parse_job_requirements_fast()` — Regex-based JD parsing (zero LLM)
- `calculate_fast_match_score()` — Keyword + semantic scoring (zero LLM)

### `backend/services/ai_search.py` (355 lines)
**Purpose**: Natural language candidate search. 3-step architecture: LLM extraction → DB filter → LLM explanation.
**Key Functions**:
- `extract_filters()` — LLM converts NL prompt to structured JSON filters
- `build_mongo_query()` — Converts JSON filters to MongoDB query (LLM never touches DB)
- `compute_stability()` — Calculates avg tenure and job switches from experience array
- `apply_stability_filters()` — Post-query filter for job hopping detection
- `generate_explanations()` — Batch LLM call for per-candidate match explanations
**Contains**: Full system prompt for the extraction LLM (lines 16-82)

### `backend/services/llm_service.py` (78 lines)
**Purpose**: Centralized OpenAI chat completion wrapper. Used exclusively by `ai_search.py`.
**Key Functions**:
- `chat_completion()` — Single function, model-agnostic, supports JSON mode
**Note**: Uses `httpx` direct call to OpenAI API (NOT Emergent SDK)

### `backend/services/embeddings.py` (306 lines)
**Purpose**: Vector embedding generation and similarity search using OpenAI `text-embedding-3-small`.
**Key Functions**:
- `generate_embedding()` — Single text → 1536-dim vector (with in-memory cache)
- `generate_embeddings_batch()` — Batch API call for multiple texts
- `generate_candidate_embedding()` / `generate_job_embedding()` — Domain-specific text prep
- `cosine_similarity()` — Pure Python cosine similarity
- `find_similar_candidates()` — Rank candidates by embedding similarity to job
- `process_candidate_embedding()` — Store embedding in MongoDB
- `batch_generate_embeddings()` — Batch process candidates without embeddings

### `backend/services/cache.py` (252 lines)
**Purpose**: Redis (Upstash) caching layer for search results, match scores, job parsing, and embeddings.
**Key Methods**:
- `get/set_search_results()` — 10 min TTL
- `get/set_parsed_job()` — 1 hour TTL
- `get/set_match_scores()` — 30 min TTL
- `get/set_candidate_embedding()` — 24 hour TTL
- `invalidate_*()` — Cache invalidation methods
- `@cached` decorator for automatic caching

### `backend/services/job_queue.py` (494 lines)
**Purpose**: In-process async job queue for CV parsing and batch embedding generation.
**Key Classes**: `JobQueueService`, `BackgroundJob`, `JobType`, `JobStatus`
**Handlers**:
- `handle_cv_parse_job()` — Async CV parse → candidate creation → embedding
- `handle_batch_embedding_job()` — Batch embedding for candidates without embeddings
- `handle_bulk_cv_parse_job()` — ZIP file → multiple resume parse → candidate creation

### `backend/services/pipeline_events.py` (123 lines)
**Purpose**: Audit logging for all pipeline stage transitions.
**Key Functions**:
- `log_pipeline_event()` — Logs stage change to `tracker_events` collection
- `validate_stage_transition()` — Enforces stage ordering rules

---

## 2.2 API Routes

### `backend/routes/applications.py` — AI Matching Endpoints (lines 973-1400)
**Purpose**: Main matching orchestration. Routes incoming match requests through quick or full_ai paths.
**Key Endpoints**:
- `POST /api/applications/match` — Primary matching endpoint (lines 973-1400)
- `GET /api/matching/jobs/{id}/status` — Poll background AI match job
- `GET /api/matching/history` — Match history for a user
- `GET /api/matching/history/{id}` — Detail of a specific match run
- `POST /api/applications/shortlist` — Shortlist candidate from screening results
**Concurrency Controls**: `asyncio.Semaphore(3)`, `asyncio.Lock()` per cache key, thundering herd prevention

### `backend/routes/ai_search.py` (114 lines)
**Purpose**: Natural language AI search API.
**Key Endpoint**: `POST /api/ai-search` — NL prompt → structured filters → MongoDB query → results + explanations
**Access**: admin, employer, recruiter

### `backend/routes/candidates.py` (1852 lines)
**Purpose**: Candidate bank CRUD with resume parsing, deduplication, visibility enforcement.
**AI-related Endpoints**:
- `POST /api/candidate-bank/add` — Upload resume → AI parse → dedup → create/update candidate
- `POST /api/candidate-bank/batch-parse` — Parse up to 10 CVs for preview
- `POST /api/candidate-bank/batch-save` — Save parsed candidates with validation
- `GET /api/candidate-bank` — Search with Atlas Search + fallback regex
**Contains**: Duplicate `parse_resume_with_ai()` function (lines 130-175) separate from matching_engine.py

### `backend/routes/background_jobs.py` (192 lines)
**Purpose**: API endpoints for job queue management and embedding operations.
**Key Endpoints**:
- `POST /api/background-jobs` — Create and start background job
- `GET /api/embeddings/health` — Check embedding service status
- `GET /api/embeddings/stats` — Embedding coverage statistics
- `POST /api/embeddings/generate-batch` — Trigger batch embedding generation
- `POST /api/cache/clear` — Clear cache by pattern

---

## 2.3 Models / Schemas

### `backend/models/matching.py` (61 lines)
**Purpose**: Pydantic models for matching requests and results.
**Models**:
- `MatchRequest` — Input for matching (job_id, jd_text, filters, mode selection)
- `MatchResult` — Output per candidate (score, skills, explanation, source)
- `MatchJobStatus` — Background job status tracking
- `JobMatchForCandidate` — Reverse match (jobs for a candidate)

---

## 2.4 Configuration

### Environment Variables
```
EMERGENT_LLM_KEY    — Used by matching_engine.py (GPT-5.2 via Emergent SDK)
OPENAI_API_KEY      — Used by llm_service.py (gpt-4o-mini direct) + embeddings.py (text-embedding-3-small)
UPSTASH_REDIS_REST_URL   — Redis cache
UPSTASH_REDIS_REST_TOKEN — Redis cache
LLM_DEFAULT_MODEL   — Default model for llm_service.py (defaults to "gpt-4o-mini")
```

---

# 3. DEPENDENCY MAP

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           ENTRY POINTS                                          │
│                                                                                 │
│  POST /api/applications/match          POST /api/ai-search                      │
│  (routes/applications.py:973)          (routes/ai_search.py:44)                 │
│           │                                      │                              │
│           ▼                                      ▼                              │
│  ┌─────────────────────┐              ┌──────────────────────┐                  │
│  │ Quick Match Path    │              │ AI Search Service    │                  │
│  │ (no LLM)            │              │ (services/ai_search) │                  │
│  │                     │              │                      │                  │
│  │ 1. parse_job_reqs   │              │ 1. extract_filters() │                  │
│  │    _fast()          │              │    ▼                 │                  │
│  │ 2. Atlas Search or  │              │    llm_service.py    │                  │
│  │    regex fallback   │              │    (gpt-4o-mini)     │                  │
│  │ 3. apply_must_have  │              │                      │                  │
│  │    _filters()       │              │ 2. build_mongo_query()│                 │
│  │ 4. calculate_fast   │              │    (deterministic)   │                  │
│  │    _match_score()   │              │                      │                  │
│  │ 5. Optional:        │              │ 3. apply_stability   │                  │
│  │    semantic score   │              │    _filters()        │                  │
│  │    via embeddings   │              │                      │                  │
│  └─────────────────────┘              │ 4. generate_         │                  │
│           │                           │    explanations()    │                  │
│  ┌─────────────────────┐              │    ▼                 │                  │
│  │ Full AI Path        │              │    llm_service.py    │                  │
│  │ (background job)    │              │    (gpt-4o-mini)     │                  │
│  │                     │              └──────────────────────┘                  │
│  │ 1. parse_jd_with_ai │                                                       │
│  │    ▼ matching_engine│                                                       │
│  │    (GPT-5.2)        │     ┌──────────────────────────────┐                  │
│  │ 2. Per candidate:   │     │  SHARED COMPONENTS           │                  │
│  │    calculate_cand   │     │                              │                  │
│  │    _job_match()     │     │  embeddings.py               │                  │
│  │    ▼ (GPT-5.2)      │     │  ├─ OpenAI text-embedding   │                  │
│  │ 3. Fallback: fast   │     │  ├─ In-memory cache          │                  │
│  │    score on timeout │     │  └─ Cosine similarity        │                  │
│  │ 4. Combine:         │     │                              │                  │
│  │    AI*0.7 + sem*0.3 │     │  cache.py                    │                  │
│  └─────────────────────┘     │  ├─ Upstash Redis            │                  │
│                              │  ├─ Search result cache      │                  │
│  POST /api/candidate-bank/add│  ├─ Match score cache        │                  │
│  (routes/candidates.py:932)  │  └─ Embedding cache          │                  │
│           │                  │                              │                  │
│           ▼                  │  job_queue.py                 │                  │
│  1. Extract text from PDF    │  ├─ CV parse handler          │                  │
│  2. parse_resume_with_ai()   │  ├─ Bulk import handler       │                  │
│  3. find_similar_candidate() │  └─ Batch embedding handler   │                  │
│  4. Create/update candidate  │                              │                  │
│  5. Auto-embed (background)  │  pipeline_events.py           │                  │
│                              │  ├─ Stage transition audit    │                  │
│                              │  └─ Stage validation rules    │                  │
│                              └──────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Inter-File Call Graph

```
applications.py ──imports──► matching_engine.py
                              ├── parse_job_requirements_fast()
                              ├── calculate_fast_match_score()
                              ├── parse_job_description_with_ai()
                              ├── calculate_candidate_job_match()
                              └── apply_must_have_filters()

applications.py ──imports──► embeddings.py
                              └── embedding_service (global instance)

applications.py ──imports──► cache.py
                              └── cache (global instance)

ai_search.py (route) ──imports──► ai_search.py (service)
                                   ├── extract_filters()
                                   ├── build_mongo_query()
                                   ├── apply_stability_filters()
                                   └── generate_explanations()

ai_search.py (service) ──imports──► llm_service.py
                                     └── chat_completion()

candidates.py ──imports──► matching_engine.py
                            ├── find_similar_candidate()
                            └── generate_resume_fingerprint()

candidates.py ──DUPLICATES──► parse_resume_with_ai() (local copy, lines 130-175)

candidates.py ──imports──► embeddings.py
                            └── embedding_service

job_queue.py ──imports──► matching_engine.py (lazy, inside handlers)
job_queue.py ──imports──► embeddings.py (lazy, inside handlers)
```

---

# 4. DATA FLOW

## 4.1 Quick Match Flow
```
Request → Cache check → Rate limit → Semaphore acquire
    → Parse JD (fast, regex-based)
    → Atlas Search (fuzzy text search across skills/summary/headline)
       └─ Fallback: regex aggregation pipeline
       └─ Fallback: simple experience sort
    → Apply must-have hard filters
    → For each candidate: calculate_fast_match_score()
       ├── Skill matching: substring check in skills + text fields
       ├── Experience scoring: range-based with penalties
       └── (Optional) Semantic: cosine similarity of pre-stored embeddings
    → Sort by score DESC
    → Cache results (in-memory, 5 min TTL)
    → Store in match_results collection (history)
    → Return MatchResult[]
```

## 4.2 Full AI Match Flow
```
Request → Same pre-filtering as Quick Match
    → Create match_jobs record (status: processing)
    → Fire-and-forget asyncio.create_task()
    → Return immediately with job_id

    Background Task:
    → Parse JD with GPT-5.2 (LLM call)
    → For each candidate (max 5 concurrent):
       → calculate_candidate_job_match() (GPT-5.2 LLM call)
       → On timeout/error: fallback to calculate_fast_match_score()
       → Combine: AI_score * 0.7 + semantic_score * 0.3
       → Update match_jobs.progress
    → Store results in match_jobs collection
    → Status: completed
```

## 4.3 AI Search Flow
```
Request → Rate limit check
    → STEP 1: extract_filters()
       └─ LLM call (gpt-4o-mini) converts NL to JSON filters
    → STEP 2: build_mongo_query()
       └─ Pure deterministic: JSON → MongoDB query
    → Execute MongoDB query (candidate_bank)
    → apply_stability_filters() (post-query, per-candidate)
    → STEP 3: generate_explanations()
       └─ Batch LLM call for top 30 candidates
    → Log to ai_search_logs
    → Return candidates + filters + explanations
```

## 4.4 Resume Ingestion Flow
```
File upload → Save to disk + R2
    → Extract text (PyMuPDF for PDF)
    → generate_resume_fingerprint() (SHA256)
    → parse_resume_with_ai() (GPT-5.2 via Emergent)
    → find_similar_candidate() (email > phone > fingerprint)
    → Create or update candidate_bank record
    → Auto-embed (background asyncio.create_task)
```

---

# 5. KNOWN RISK AREAS

## 5.1 Search Results May Be Inconsistent

**RISK: DUPLICATE `parse_resume_with_ai()` FUNCTIONS**
- `matching_engine.py` lines 29-138: Full implementation with backwards-compat mapping
- `candidates.py` lines 130-175: Simplified local copy with different prompt/field names
- **Impact**: Same resume parsed through different paths produces different structured data
- **Affected Fields**: `summary` vs `profile_summary`, `skills` vs `key_skills`, `experience` vs `work_experience`
- **Severity**: MEDIUM — affects data consistency in candidate_bank

**RISK: ATLAS SEARCH FALLBACK INCONSISTENCY**
- `applications.py` lines 1069-1163: Three fallback tiers (Atlas → regex agg → simple query)
- Each tier uses different scoring/ranking logic
- Atlas Search returns relevance-scored results; regex returns skill-count-sorted; simple returns experience-sorted
- **Impact**: Same query can return different candidate order depending on which tier executes
- **Severity**: LOW — functionally correct but ranking varies

**RISK: FIELD NAME MISMATCHES IN CANDIDATE_BANK**
- Some candidates have `summary`, others have `profile_summary`
- Some have `skills`, others have `key_skills`
- Some have `experience`, others have `work_experience`
- AI Search query in `build_mongo_query()` searches `summary` but not `profile_summary`
- **Impact**: Candidates with `profile_summary` but not `summary` won't match text searches
- **Severity**: MEDIUM — missed search results for subset of candidates

## 5.2 Scoring May Loop

**RISK: FULL AI MATCH TIMEOUT FALLBACK**
- `applications.py` line 1261-1267: If GPT-5.2 call times out (30s), falls back to `calculate_fast_match_score()`
- Fast score uses different weighting (50% skill + 30% exp + 20% base) vs AI score (0-100 raw + 0.7/0.3 blend with semantic)
- **Impact**: Within a single match run, some candidates get AI scores, others get fast scores, mixed in the same result set
- **Severity**: MEDIUM — score comparison across candidates is not apples-to-apples

**RISK: NO DEDUP ON MATCH RESULTS**
- Same candidate could appear multiple times if they exist in multiple Atlas Search result sets
- `pre_filtered` list is not deduplicated before scoring
- **Impact**: Unlikely in practice (single query) but possible with complex Atlas Search compound queries
- **Severity**: LOW

## 5.3 Async Operations May Duplicate

**RISK: AUTO-EMBED FIRE-AND-FORGET**
- `candidates.py` line 1091: `asyncio.create_task(_auto_embed_candidate(...))`
- If multiple resumes are uploaded for the same candidate simultaneously, multiple embedding tasks run in parallel
- Each independently reads, generates, and writes the embedding
- **Impact**: Wasted API calls and potential race condition on the `embedding` field write
- **Severity**: LOW — last write wins, embeddings are stable

**RISK: BULK CV PARSE JOB NOT IDEMPOTENT**
- `job_queue.py` `handle_bulk_cv_parse_job()` — if the job fails midway and is retried, already-created candidates are created again (no dedup check per resume in bulk flow)
- **Impact**: Duplicate candidates on retry of failed bulk import
- **Severity**: MEDIUM

**RISK: MATCH JOB ORPHANED ON SERVER RESTART**
- `match_jobs` records created with status "processing" in `applications.py` line 1223
- If server restarts during background matching, the `asyncio.create_task()` is lost
- Job stays as "processing" forever in MongoDB
- **Impact**: Stale "processing" jobs in match history
- **Severity**: LOW — cosmetic, no data corruption

## 5.4 Race Conditions

**RISK: IN-MEMORY MATCH CACHE NOT PROCESS-SAFE**
- `applications.py` lines 12-24: `_match_cache`, `_match_locks` are Python dicts
- `asyncio.Lock()` protects within a single process, but if multiple uvicorn workers are used, each worker has its own cache
- **Impact**: Under multi-worker deployment, thundering herd protection is ineffective
- **Severity**: LOW in current single-worker deployment, HIGH if scaled to multi-worker

**RISK: CANDIDATE BANK UPDATE + EMBEDDING RACE**
- `candidates.py` line 1086: `insert_one(candidate_doc)` followed by line 1091: background embedding task
- Embedding task reads from the just-inserted document
- If a concurrent update modifies the candidate between insert and embedding read, embedding may be generated from stale data
- **Impact**: Embedding slightly out of sync with current candidate data
- **Severity**: LOW — embeddings are regenerated periodically

**RISK: SEARCH CACHE INVALIDATION GAP**
- `cache.invalidate_search_cache()` is called manually but NOT automatically when candidates are added/modified
- **Impact**: Stale search results for up to 10 minutes after candidate changes
- **Severity**: LOW — acceptable for most use cases

---

# 6. COLLECTIONS USED

| Collection | Purpose | Written By |
|------------|---------|------------|
| `candidate_bank` | All candidate profiles + embeddings | candidates.py, job_queue.py, embeddings.py |
| `applications` | Job applications with scores | applications.py |
| `match_results` | Match history per search run | applications.py (quick match) |
| `match_jobs` | Background AI match job tracking | applications.py (full_ai) |
| `ai_search_logs` | AI search query + filter logs | ai_search.py (route) |
| `background_jobs` | CV parse / batch embedding jobs | job_queue.py |
| `audit_logs` | Candidate field change audit | candidates.py |
| `tracker_events` | Pipeline stage transition events | pipeline_events.py |
| `jobs` | Job postings (read for matching) | — |

---

# APPENDIX: FILE LOCATIONS FOR FULL CODE REVIEW

All files are in `/app/backend/`:

| # | File | Lines | Role |
|---|------|-------|------|
| 1 | `services/matching_engine.py` | 576 | AI scoring engine |
| 2 | `services/ai_search.py` | 355 | NL search service |
| 3 | `services/llm_service.py` | 78 | OpenAI wrapper |
| 4 | `services/embeddings.py` | 306 | Vector embeddings |
| 5 | `services/cache.py` | 252 | Redis caching |
| 6 | `services/job_queue.py` | 494 | Background jobs |
| 7 | `services/pipeline_events.py` | 123 | Stage audit |
| 8 | `routes/applications.py` | 1632 | Match orchestration (lines 973-1400) |
| 9 | `routes/ai_search.py` | 114 | AI search API |
| 10 | `routes/candidates.py` | 1852 | Candidate CRUD + resume parse |
| 11 | `routes/background_jobs.py` | 192 | Job queue + embedding API |
| 12 | `models/matching.py` | 61 | Pydantic schemas |
