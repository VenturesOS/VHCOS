# Search Integration Patch — candidates.py quick search

Goal: swap the COLLSCAN regex path for the index-backed `fast_search`
service, behind a feature flag, with automatic fallback. Expected effect
on a 139k-doc candidate_bank: quick-search latency drops from
seconds (two full scans per request) to tens of milliseconds, and
results become relevance-ranked instead of newest-first.

## Deploy order (important)

1. Copy `backend/services/fast_search.py` into the repo.
2. Run the index migration **before** enabling the flag:
   ```bash
   cd /home/ubuntu/vhc-platform/backend
   source venv/bin/activate
   python scripts/ensure_search_indexes_v2.py            # review plan
   python scripts/ensure_search_indexes_v2.py --apply    # build indexes + backfill
   ```
3. Deploy code with `FAST_SEARCH=0` (default). Verify legacy path still works.
4. Flip `FAST_SEARCH=1` in `backend/.env` and restart.
5. Rollback at any time = set `FAST_SEARCH=0`. No schema changes to undo.

## Verification

```javascript
// mongosh — confirm the plan uses the text index, not COLLSCAN
db.candidate_bank.find(
  { $text: { $search: '"sap" "mm"' } }
).explain("executionStats").executionStats
// expect: totalDocsExamined ≪ collection size, stage: TEXT_MATCH
```

Then in the app: search "sheet metal riveting" in Candidate Bank —
results should return in well under 200 ms and lead with candidates whose
*name/skills/designation* match, not merely the newest captures.

## What you lose / keep

Synonym expansion ("PM" → "project manager") does not run on the fast
path by default. Two options: (a) expand the query string before the
call using the existing `synonym_service` — `$text` handles OR terms
natively; or (b) keep synonyms only on the Advanced Search page.
Recommendation: (a).

Boolean search, cursor pagination, and every fielded filter behave
exactly as before — they pass through `extra_conditions` untouched.
