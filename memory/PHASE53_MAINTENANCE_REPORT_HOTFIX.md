# Phase 53 — 7-Day Maintenance Report Hotfix Batch (2026-05-07)

## Triage of the 7-Day Report

| # | Issue | Status | Resolution |
|---|---|---|---|
| 1 | Resume parsing 500s (`Expecting ',' delimiter`) | **FIXED** | Added `json_repair` fallback in match-calc parser path |
| 2 | `/notifications/unread-count` 502s | **No-op** | Already mitigated in code; report 502s were historical (gunicorn restart windows) |
| 3 | `naukri_capture` "15 unrecovered" false alarm | **FIXED** | Health-check query now scoped to 24h + `$ne True` |
| 4 | `ApplicationResponse.education` ValidationError 500s | **FIXED** | Schema accepts `Any` (str OR list of dicts) |

## Bug Details

### Fix 1 — Resume / Match parsing 500s
`backend/services/matching_engine.py:402` (the match-calc parser, separate from the resume parser at line 219 we fixed earlier in Phase 51) was still using strict `json.loads`. When Qwen returns a truncated payload with the same trailing-quote issue we saw on May 5 (`"current_designation"`...), the call propagates as a 500 to the frontend.

**Now mirrors the same json_repair fallback** as `parse_resume_with_ai` and `extract_full_profile_fallback`.

### Fix 2 — 502 Bad Gateway on unread-count
After investigation:
- `backend/routes/notifications.py:98` already returns `{count: 0}` on any DB error (try/except)
- `frontend/src/lib/errorCapture.js:81` already filters 5xx errors
- `frontend/src/lib/errorCapture.js:85` explicitly skips `/notifications/unread-count` from error reporting
- `NotificationBell.jsx:48` polls with exponential backoff (60s → 5min on failure)

The 502s in the report all occurred during gunicorn restart windows (May 5 13:05 OOM, May 6 04:58 git-pull, May 7 05:02 nightly restart). Once nginx detects the upstream is back, the next poll succeeds. This is **not a code bug** — it's the expected behaviour during deploys.

**No code change needed.** Report's 502s were filed BEFORE the maintenance report's filter-bypass logic. Future restarts will not show up in the report.

### Fix 3 — `naukri_capture` "15 unrecovered" false-alarm storm
`backend/services/health_monitor.py:160` had:
```python
unrecovered = await db.naukri_capture_logs.count_documents(
    {"status": "failed", "is_recovered": False}
)
```
The query had **no time bound**, so every historical failed capture (stretching back months) with `is_recovered=false` was counted. Even after a recruiter / backfill script recovered them, the field could still show `False` if it was never explicitly flipped to `True` (only flipped via the `--retry` script, not the live extension recovery path).

Result: 252 auto-fix log entries in 7 days, all firing `generic_health_check → no specific fix available`. Pure noise.

**Fixed by:**
1. Scoping the query to the same 24-hour window as `total` and `failed`
2. Using `$ne: True` so missing-field docs aren't counted as failures
3. Updating the error message to `"X unrecovered failed captures (24h)"` for clarity

### Fix 4 — ApplicationResponse.education ValidationError
`backend/models/application.py:46` declared `education: Optional[str]`. The candidate_bank document stores `education_details` as a list of dicts (e.g., `[{"degree":"BTech","institution":"IIT Delhi"}]`), and several routes pass that value through unchanged.

When a candidate with structured education tried to view their application detail, Pydantic raised `ValidationError 1 validation error for ApplicationResponse education Input should be a valid string` → 500.

**Fixed by** changing the field to `Optional[Any]` so it tolerates both the legacy string and the structured list. Frontend handles both shapes.

## Files Changed

- `backend/services/matching_engine.py` — json_repair fallback in match-calc parser
- `backend/services/health_monitor.py` — 24h + `$ne True` scope on unrecovered query
- `backend/models/application.py` — education schema accepts Any

## Deployment on EC2

```bash
ssh ubuntu@<ec2>
cd /home/ubuntu/vhc-platform
git pull --rebase origin main
sudo systemctl restart gunicorn
sleep 5

# Verify
sudo systemctl status gunicorn --no-pager | head -8
curl -s -o /dev/null -w "%{http_code}\n" https://ventureshrd.com/api/health/incident-analysis
# Expected: 200
```

## Verification After Deploy (24h soak)

```bash
# Should DROP to 0 or near-zero from 252 in last week:
sudo journalctl -u gunicorn --since "24 hours ago" | grep -c "unrecovered failed captures"

# Should DROP to 0 from 10 in last week:
sudo journalctl -u gunicorn --since "24 hours ago" | grep -c "Resume parsing failed"

# Should DROP to 0 from 2 in last week:
sudo journalctl -u gunicorn --since "24 hours ago" | grep -c "ApplicationResponse"
```

## Expected Health Score Improvement

- Before: **84/100** (92 incidents, 91 critical)
- After (projected): **92-95/100** — eliminating the resume-parsing 500s + ApplicationResponse 500s removes ~14 critical errors; killing the 252 false-alarm auto-fix events removes the spammy noise that was diluting the signal.
