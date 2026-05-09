# Phase 54.11 — Pipeline Redis cache (60s TTL)
**Date:** 2026-05-09
**Type:** Backend perf optimization
**Status:** ✅ Built & verified — pending EC2 deploy

## Goal
Cut perceived latency on `/admin/pipeline` filter clicks. The
underlying aggregation does too much work to make a cold call fast,
but typical recruiter behaviour is to click the same 2-3 filter combos
repeatedly within a minute. Redis cache turns those repeat clicks from
3s → 1.4s.

## Implementation
`backend/routes/admin.py::get_admin_pipeline()` — drop-in cache layer
keyed by the filter tuple:

```python
_cache_key = (
    f"admin:pipeline:v1:"
    f"emp={employer_id or 'all'}|"
    f"rec={recruiter_id or 'all'}|"
    f"team={team_id or 'all'}|"
    f"job={job_id or 'all'}"
)
_cached = cache.get(_cache_key)
if _cached is not None:
    return _cached
# ... full aggregation ...
cache.set(_cache_key, result, ttl=60)
```

- **Per-tuple, not per-user.** Pipeline data is identical for any
  admin viewer, so all admins share the cache.
- **60s TTL.** Stage drag-drops + new applications surface within a
  minute. Trade-off chosen vs. invalidate-on-write because pipeline
  reads are far more frequent than writes.
- **No frontend change.** Pure backend optimization.

## Verified (workspace pod)
| Scenario | Time | vs cold |
|---|---|---|
| Call 1 — cold (gunicorn just booted) | 10.6 s | baseline |
| Call 2 — cache HIT (no filter) | 3.1 s | -71% |
| Call 3 — cache HIT (no filter) | 2.0 s | -81% |
| Call 4 — cache MISS (job_id filter) | 3.0 s | new key, no hit |
| Call 5 — cache HIT (job_id filter) | **1.4 s** | **-53%** |

Repeated filter clicks within 60s are roughly **50% faster**. Remaining
latency is dominated by the 1 MB JSON payload (1,914 applications +
candidate enrichment) being serialized over HTTP, not Mongo.

## Files Changed
- `backend/routes/admin.py` — cache lookup at top, cache.set before return.

## Deploy (EC2)
```bash
cd /home/ubuntu/vhc-platform && \
  git pull --rebase origin main && \
  sudo systemctl restart gunicorn
```
No frontend rebuild needed (this PR is backend-only).

## Future wins (further latency reduction, separate phases)
- **Denormalize stage_counts** at application-write time so the dashboard
  doesn't recompute them per request (~600ms saved)
- **Paginate / lazy-load** applications inside the pipeline endpoint —
  the table only ever shows ~7 candidates per stage on screen, no need
  to ship 1,914 in one payload
- **Split dropdowns into a separate `/admin/pipeline/filters` endpoint**
  loaded ONCE on mount (employers/recruiters change rarely) — saves
  ~300ms on every filter click
- **Active cache invalidation** on stage changes so a recruiter's
  drag-drop is reflected instantly instead of waiting up to 60s. Use
  `cache.delete_pattern("admin:pipeline:v1:*")` from the stage-change
  endpoint.
