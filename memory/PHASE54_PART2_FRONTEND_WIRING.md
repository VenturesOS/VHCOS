# Phase 54 (Part 2) — Frontend Wiring for ML Sourcing Re-Ranker (2026-05-07)

## What's New

Two pages now have a **Smart Re-rank** toggle that calls `/api/sourcing/rerank`:

### 1. `frontend/src/pages/employer/FindCandidatesPage.jsx` (AI tab)
- Toggle: **"Smart Re-rank — ML-trained on your team's hires (recommended)"**
- **Default: ON.** When ON, AI Search uses `/sourcing/rerank` (XGBoost LTR + k-Means + PCA) instead of legacy `/ai-search`.
- When OFF, falls back to the existing `/ai-search` endpoint (filter extraction → structured search).
- Shows live timing + AUC after each search: `200 pool · re-ranked in 350ms · AUC 0.72`

### 2. `frontend/src/pages/shared/AdvancedSearchPage.jsx`
- Toggle: **"Smart Re-rank"** (disabled when no keywords entered).
- **Default: OFF.** When ON AND user has entered keywords, the page calls `/sourcing/rerank` with keywords as the natural-language query.
- When OFF or no keywords, falls back to the existing structured filter search via `candidateBankAPI.getAll`.
- Shows `200 pool · 350ms · AUC 0.72` after each search.

## API Wiring (`frontend/src/lib/api.js`)

```javascript
export const sourcingAPI = {
  rerank: (params) => api.post('/sourcing/rerank', params),  // { job_id?, query?, top_k?, diversify? }
  health: () => api.get('/sourcing/health'),                  // { model_loaded, AUC, RAM }
};
```

## Why Two Different Default Settings?

- **FindCandidatesPage AI tab** is purely natural-language search → ML re-rank is the default winning UX.
- **AdvancedSearchPage** is a structured-filter UI; users come here specifically for hard constraints (location, exp, salary). The ML toggle is opt-in, only active when they provide free-text keywords.

## Graceful Degradation (Already Handled Backend-Side)

If the model bundle is missing on EC2, `/api/sourcing/rerank` returns vector-search-only results (`model_loaded: false`). Frontend stays functional — no error toasts, just slightly less smart ranking. The toggle is meaningful from day 1 even if EC2 hasn't been retrained yet.

## Files Changed

- `frontend/src/lib/api.js` — added `sourcingAPI` block
- `frontend/src/pages/employer/FindCandidatesPage.jsx` — toggle + dual-path search
- `frontend/src/pages/shared/AdvancedSearchPage.jsx` — toggle + dual-path search

All 3 lint clean ✅

## Deployment

```bash
ssh ubuntu@<ec2>
cd /home/ubuntu/vhc-platform
git pull --rebase origin main
cd frontend && yarn build
# nginx auto-serves the new build/
```

## Cron — Weekly Retraining

Add to your crontab (one new line; the others from PHASE52_PART4 stay):

```cron
# VHC OS — weekly LTR model retrain (Sat 22:00 UTC = Sun 03:30 IST)
0 22 * * 6 cd /home/ubuntu/vhc-platform/backend && /home/ubuntu/vhc-platform/backend/venv/bin/python3 scripts/train_sourcing_models.py >> /var/log/vhc/ltr-train.log 2>&1
```

After cron runs, restart gunicorn ON DEMAND (Sunday morning) to pick up the new bundle:
```bash
sudo systemctl restart gunicorn
```

(Or wait for the next deploy — workers naturally pick up the new bundle on next restart.)

## Test Plan (After Deploy)

1. **Admin** → AdvancedSearch → enter "SAP MM Pune 8 years" in Keywords → check "Smart Re-rank" → click Find. Should return semantic + LTR-ranked results in ~1s.
2. **Employer** → Find Candidates → AI Search tab → ensure "Smart Re-rank" is ON by default → enter prompt → click "AI Search". Should show timing + AUC under the toggle.
3. **Toggle OFF** path: same searches as above but unchecked → should fall back to legacy filter search.
4. **Health check**: `curl https://ventureshrd.com/api/sourcing/health` (with admin token) → should show `model_loaded: true, AUC: 0.72`.

## Telemetry

Each `/sourcing/rerank` call writes to `db.sourcing_search_logs`:
- User + role
- Job ID / query
- Pool size, timing per stage, memory delta, returned IDs
- This becomes the labelled data for **Phase 56** (training v2 LTR model on actual recruiter clicks)
