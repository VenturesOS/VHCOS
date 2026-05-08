# VHC Talent OS — Deep Backend Refactoring Plan

## FOR: Codex / Claude Opus
## AUTHOR: E1 Agent (Emergent Labs)
## DATE: March 21, 2026

---

## CRITICAL RULES — READ FIRST

### DO NOT CHANGE (will break production)
1. **API route paths** — Every URL path must stay identical. Frontend depends on them.
2. **Pydantic model field names** — DB documents use these exact field names.
3. **Environment variable names** — `MONGO_URL`, `DB_NAME`, `JWT_SECRET_KEY`, `R2_*`, `OPENAI_API_KEY`, etc.
4. **Router prefix strings** — e.g., `prefix="/api/extension"`, `prefix="/api/candidate-bank"`
5. **The `config.py` file** — This is the central config. Don't rename or restructure it.
6. **The `from config import db` pattern** — All routes access MongoDB via `db` from `config.py`.
7. **The `_safe_import` pattern in `server.py`** — This allows the server to start even if a route module fails.
8. **File upload paths** — `UPLOAD_DIR`, `PARENT_UPLOAD_DIR` from config.
9. **The `models/__init__.py` barrel export** — `server.py` imports all models from `models`.
10. **The `routes/__init__.py` barrel export** — `server.py` imports core routers from `routes`.

### TESTING AFTER REFACTORING
After each phase, run:
```bash
cd backend && python -c "from server import app; print('OK')"
```
And verify all routes are registered:
```bash
cd backend && python -c "
from server import app
for r in app.routes:
    if hasattr(r, 'path'):
        print(f'{r.methods} {r.path}')
" | sort | head -50
```

---

## CURRENT STATE ANALYSIS

### File Structure
```
backend/
├── config.py                    # 214 lines — Central config (DB, R2, JWT, paths)
├── server.py                    # 692 lines — App creation, route registration, startup, health checks
├── core/                        # Duplicate/unused — config.py, database.py, security.py, helpers.py
│   ├── config.py                # DUPLICATE of root config.py — NOT used by routes
│   ├── database.py              # Just re-exports from config.py
│   ├── security.py              # DUPLICATE of utils/auth.py — NOT used by routes
│   └── helpers.py               # DUPLICATE of utils/governance.py — NOT used by routes
├── models/                      # 1,204 lines — Pydantic models (well-organized, 14 files)
├── routes/                      # 22,080 lines — 30 route files (THE PROBLEM AREA)
├── services/                    # 9,706 lines — 30 service files (mostly fine)
├── middleware/                   # 247 lines — rate_limiter.py, zero_trust.py
├── utils/                       # 651 lines — auth.py, governance.py, etc.
├── scripts/                     # Migration/seed scripts
└── tests/                       # Test files
```

### Key Problems
1. **Route files contain business logic** — Routes should be thin (validate input → call service → return response). Currently, route files have DB queries, data transformations, AI calls, file processing all inline.
2. **42 inline Pydantic models scattered across route files** — These should be in `models/`.
3. **`core/` directory is dead code** — It duplicates `config.py`, `utils/auth.py`, and `utils/governance.py`. Only `core/database.py` is imported by `core/helpers.py`. No route uses `core/`.
4. **Some route files are 1,500-2,000 lines** — extension.py (1,970), applications.py (1,879), bulk_import.py (1,733), candidates.py (1,720).
5. **Inconsistent DB access** — Most use `from config import db` at top, but `candidates.py` uses `from config import db` inside functions (lazy import pattern).

---

## PHASE 1: Extract Inline Pydantic Models → `models/`

**Goal:** Move all inline Pydantic models from route files into the `models/` directory. This is the safest refactor — it changes imports but not behavior.

### Files to extract from:
| Route File | Inline Models | Move To |
|-----------|--------------|---------|
| `routes/extension.py` | 15 models | `models/extension.py` (NEW) |
| `routes/bulk_import.py` | 11 models | `models/bulk_import.py` (NEW) |
| `routes/tracker.py` | 8 models | `models/tracker.py` (NEW) |
| `routes/applications.py` | 4 models | `models/application.py` (EXISTING — append) |
| `routes/jobs.py` | 3 models | `models/job.py` (EXISTING — append) |
| `routes/public.py` | 1 model | `models/public.py` (NEW) |

### Steps:
1. For each route file, find all `class XxxModel(BaseModel):` definitions.
2. Move them to the appropriate models file.
3. Add the import in the route file: `from models.extension import ModelName1, ModelName2`
4. Add the new model file to `models/__init__.py` if needed.
5. Verify no circular imports.

### Example for `routes/extension.py`:
```python
# BEFORE (in routes/extension.py):
class CompleteNaukriProfileInput(BaseModel):
    name: str
    ...

# AFTER:
# 1. Create models/extension.py with all 15 models
# 2. In routes/extension.py:
from models.extension import CompleteNaukriProfileInput, EvaluateFitInput, ...
```

---

## PHASE 2: Extract Business Logic → `services/`

**Goal:** Route handlers should be thin controllers. Extract DB operations, data transformations, and AI calls into service functions.

### Priority Files (largest, most logic-heavy):

#### 2A. `routes/extension.py` (1,970 lines, 26 functions)
Create: `services/extension_service.py`

Extract these operations:
- AI-powered candidate evaluation logic (the LLM prompt building, response parsing)
- Profile capture and enrichment logic (name validation, phone filtering, duplicate detection)
- Source platform detection and tagging
- Mandate evaluation scoring

The route handler should only:
```python
@extension_router.post("/capture")
async def capture_profile(profile: CompleteNaukriProfileInput, current_user = Depends(get_current_user)):
    result = await extension_service.capture_profile(profile, current_user)
    return result
```

#### 2B. `routes/candidates.py` (1,720 lines, 28 functions)
Create: `services/candidate_bank_service.py`

Extract:
- CV text extraction (already partially in `utils/doc_extractor.py`)
- Candidate search/filter logic
- Batch operations
- Duplicate detection
- Profile enrichment

#### 2C. `routes/applications.py` (1,879 lines, 26 functions)
Create: `services/application_service.py`

Extract:
- Application stage transitions and audit logging
- Revenue forecasting calculations
- Offer letter generation
- Application search and filtering

#### 2D. `routes/bulk_import.py` (1,733 lines, 24 functions)
Create: `services/bulk_import_service.py`

Extract:
- File parsing (Excel, CSV, PDF, DOCX, ZIP)
- Chunked upload management
- Batch save operations
- Template generation
- The `extract_text_from_file()` function → move to `utils/doc_extractor.py`

#### 2E. `routes/jobs.py` (1,363 lines, 22 functions)
Create: `services/job_service.py`

Extract:
- Job CRUD with mandate logic
- JD parsing (AI)
- Career page publishing
- Mandate link generation and validation

### Pattern for extraction:
```python
# services/extension_service.py
from config import db
from services.llm_service import call_llm
from models.extension import CompleteNaukriProfileInput

async def capture_profile(profile: CompleteNaukriProfileInput, user: dict) -> dict:
    """Business logic extracted from route handler."""
    # All the DB queries, validation, AI calls go here
    ...
    return {"success": True, "action": "created", "candidate_id": cid}
```

```python
# routes/extension.py (thin handler)
from services.extension_service import capture_profile as _capture

@extension_router.post("/capture")
async def capture_profile(profile: CompleteNaukriProfileInput, current_user = Depends(get_current_user)):
    return await _capture(profile, current_user)
```

---

## PHASE 3: Clean Up Dead Code & Consolidate

### 3A. Remove `core/` directory
The `core/` directory is **completely unused by any route or service**. It's a duplicate of:
- `core/config.py` → duplicate of `config.py`
- `core/database.py` → just re-exports `from config import client, db, db_name`
- `core/security.py` → duplicate of `utils/auth.py`
- `core/helpers.py` → duplicate of `utils/governance.py`

**Action:** Delete the entire `core/` directory. If any file does reference it, update the import to use the canonical source (`config`, `utils.auth`, `utils.governance`).

### 3B. Consolidate `utils/doc_extractor.py`
Move the `extract_text_from_file()` function from `routes/bulk_import.py` into `utils/doc_extractor.py` (which already exists but may be incomplete). All file text extraction should live in one place.

### 3C. Remove unused imports
After moving models and services, run:
```bash
ruff check --select F401 routes/ services/ --fix
```

---

## PHASE 4: Standardize Error Handling

### Current State:
Routes use a mix of:
- `raise HTTPException(status_code=400, detail="...")`
- `return {"success": False, "error": "..."}`
- `return {"detail": "..."}`
- Raw dict responses with no consistent structure

### Target:
Create `utils/responses.py`:
```python
from fastapi.responses import JSONResponse

def success_response(data=None, message="OK", status_code=200):
    body = {"success": True, "message": message}
    if data is not None:
        body["data"] = data
    return JSONResponse(content=body, status_code=status_code)

def error_response(message="Error", status_code=400, details=None):
    body = {"success": False, "error": message}
    if details:
        body["details"] = details
    return JSONResponse(content=body, status_code=status_code)
```

**IMPORTANT:** Do NOT change existing response shapes that the frontend already parses. Only use this for NEW code or where the route already returns `{"success": bool, ...}`.

---

## PHASE 5: Slim Down `server.py`

### Current State (692 lines):
- Route imports & registration (~150 lines)
- Health check endpoints (~100 lines)
- Startup/shutdown events (~100 lines)
- Index creation (~50 lines)
- CORS setup (~30 lines)
- Middleware setup (~20 lines)
- Global exception handler (~30 lines)
- Misc inline routes (~100 lines)

### Target:
Extract into focused modules:
1. `server.py` → Keep only: app creation, middleware, route registration (~100 lines)
2. `routes/health.py` (NEW) → All health/diagnostics endpoints
3. Move index creation into a `scripts/create_indexes.py` or call it from `config.py`'s `initialize_db()`
4. Move startup/shutdown logic into `services/lifecycle.py` (NEW)

---

## FILE-BY-FILE CHANGE SUMMARY

### New Files to Create:
```
models/extension.py          # 15 Pydantic models from routes/extension.py
models/bulk_import.py        # 11 Pydantic models from routes/bulk_import.py
models/tracker.py            # 8 Pydantic models from routes/tracker.py
models/public.py             # 1 Pydantic model from routes/public.py
services/extension_service.py    # Business logic from routes/extension.py
services/candidate_bank_service.py  # Business logic from routes/candidates.py
services/application_service.py     # Business logic from routes/applications.py
services/bulk_import_service.py     # Business logic from routes/bulk_import.py
services/job_service.py             # Business logic from routes/jobs.py
services/lifecycle.py               # Startup/shutdown from server.py
routes/health.py                    # Health endpoints from server.py
utils/responses.py                  # Standardized response helpers
```

### Files to Modify:
```
routes/extension.py      # Remove inline models & business logic, keep thin handlers
routes/candidates.py     # Remove inline logic, keep thin handlers
routes/applications.py   # Remove inline logic, keep thin handlers
routes/bulk_import.py    # Remove inline models & logic, keep thin handlers
routes/jobs.py           # Remove inline models & logic, keep thin handlers
routes/tracker.py        # Remove inline models, keep handlers
routes/public.py         # Remove inline model, keep handlers
models/__init__.py       # Add new model imports
server.py                # Slim down, move health endpoints out
```

### Files to Delete:
```
core/                    # Entire directory (dead code / duplicates)
```

---

## VERIFICATION CHECKLIST

After completing all phases, verify:

1. **Server starts:** `python -c "from server import app; print('Server OK')"`
2. **All routes registered:** Compare route list before and after (should be identical)
3. **No circular imports:** `python -c "import routes; import services; import models; print('OK')"`
4. **Lint clean:** `ruff check . --select F401,F811,E402`
5. **Existing tests pass:** `python -m pytest tests/ -v`
6. **Key API endpoints work:**
   - `POST /api/auth/login`
   - `GET /api/candidate-bank`
   - `POST /api/extension/capture`
   - `GET /api/applications`
   - `GET /api/jobs`
   - `POST /api/candidate-bank/batch-parse`
   - `GET /api/notifications/unread-count`

---

## PRIORITY ORDER

If doing incrementally:
1. **Phase 1** (Models) — Safest, biggest clarity win
2. **Phase 3A** (Delete `core/`) — Quick cleanup
3. **Phase 2A-2E** (Services) — Biggest impact but most risk
4. **Phase 5** (server.py) — Nice to have
5. **Phase 4** (Error handling) — Only for new code going forward

---

## IMPORTANT CONTEXT

### DB Access Pattern
All routes access MongoDB via:
```python
from config import db
# Then: await db.collection_name.find_one({...})
```
This MUST NOT change. The `db` object is a Motor async MongoDB client proxy.

### Authentication Pattern
```python
from utils.auth import get_current_user, require_role

@router.get("/something")
async def handler(current_user: dict = Depends(get_current_user)):
    ...

# For admin-only routes:
@router.get("/admin-thing")
async def handler(current_user: dict = Depends(require_role(["admin"]))):
    ...
```

### Cross-Route Dependencies
- `routes/account_manager.py` imports `create_notification` from `routes/notifications.py`
- `routes/applications.py` imports `create_notification` from `routes/notifications.py`
- Solution: Move `create_notification` to `services/notification_service.py` (it may already be there — check first)

### Frontend API Calls
The React frontend calls these exact paths (non-exhaustive):
```
POST /api/auth/login
GET  /api/candidate-bank
POST /api/candidate-bank/batch-parse
POST /api/candidate-bank/upload
GET  /api/applications
POST /api/extension/capture
POST /api/extension/evaluate-fit
GET  /api/jobs
GET  /api/notifications/unread-count
POST /api/public/apply
POST /api/public/upload-resume
GET  /api/system-errors
GET  /api/system-health/status
```
**ALL of these must continue to work identically after refactoring.**
