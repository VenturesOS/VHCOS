# ENV Recovery Report — Feb 26, 2026

## === ENV RECOVERY REPORT ===

* **Wrong DB detected**: NO — Backend was connected to the correct production Atlas cluster (`cluster0.vuhdiod.mongodb.net`) the entire time. All 1804 candidates, 28 users, 50 applications present.
* **Root cause**: Environment detection priority bug. Emergent preview pod injects `APP_URL=https://...preview.emergentagent.com` via supervisor. The `_detect_environment()` function in `utils/environment.py` checked `APP_URL` (Step 2) **before** the MongoDB cluster check (Step 3), so it returned `"preview"` instead of `"production"`. This caused `is_production=false` in the `/api/system-health/env-info` response, triggering the amber "UNKNOWN MODE — DATA MAY NOT MATCH LIVE" banner on the frontend.
* **DB restored**: N/A — DB was never wrong
* **Mode detection fixed**: YES — Reordered `_detect_environment()` to check MongoDB cluster identity FIRST (authoritative for data identity), before the preview pod URL check. Now correctly returns `"production"` when connected to the production Atlas cluster.
* **Data counts after fix**:
  - Users: 28
  - Active Jobs: 1
  - Applications: 50
  - Companies: 22
  - Candidate Bank: 1,804
* **Files modified**: `backend/utils/environment.py` (1 file, detection priority reorder only)
* **Security risk introduced**: NO
