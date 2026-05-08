# Phase 54 — Part 4: "Why this match?" explanation chips
**Date:** 2026-05-07
**Type:** Engagement / UX feature
**Status:** ✅ Built & verified (workspace) — pending EC2 deploy

## Goal
Turn the LTR re-ranker's black-box scores into trust-building UX by
showing the top-2 *contributing favorable features* under each
candidate card on:
  • `/advanced-search` (Smart Re-rank ON)
  • `/find-candidates` AI tab (Smart Re-rank ON)

## Implementation

### Backend — `services/sourcing_ml.py`
1. `_ltr_score()` now returns `(scores, reasons_list)` instead of just
   scores. It calls `_explain_features()` per candidate using the model
   meta's `feature_importance_gain` map.
2. New `_job_context_flags(job)` — detects whether the job has
   skills/location/exp/ctc fields populated. Used to suppress
   misleading explanations like "Experience fit" for query-only
   searches (where `job_max_exp` defaults to `99` ⇒ everyone trivially
   fits).
3. New `_explain_features(feats, ctx, top_n=2)` — assembles a list of
   `{label, feature, weight}` dicts, sorted by global gain desc, then
   takes the top 2.
4. `rerank()` attaches the explanations as `c["match_reasons"]`.

### Frontend — chip row added to two pages
- `pages/shared/AdvancedSearchPage.jsx` — after smart_tags row
- `pages/employer/FindCandidatesPage.jsx` — after skills row in
  `aiResults` map

Chip styling: emerald-50 / emerald-700 / emerald-200 border, 11px,
small `<CheckCircle>` icon, rounded-full pill. Each chip's `title`
attribute exposes the underlying feature name + gain weight for
power users / debugging.

## Sample Output

### Query-only mode (`/api/sourcing/rerank` with `query` only)
```
#1: ltr=0.251 reasons → 77% semantic match
#2: ltr=0.250 reasons → 78% semantic match
#5: ltr=0.192 reasons → 79% semantic match | 15 yrs experience
```

### Job-anchored mode (`/api/sourcing/rerank` with `job_id`)
```
job: Area Manager – Mechanical Engineering (Mumbai, 5–10 yrs)
#1: ltr=0.402 reasons → Location match | 77% semantic match
#2: ltr=0.282 reasons → Location match | Experience fit
#3: ltr=0.248 reasons → 75% semantic match | 13 yrs experience
#4: ltr=0.233 reasons → Location match | Experience fit
```

## Files Changed
- `backend/services/sourcing_ml.py` (~60 LOC added)
- `frontend/src/pages/shared/AdvancedSearchPage.jsx` (~16 LOC)
- `frontend/src/pages/employer/FindCandidatesPage.jsx` (~16 LOC)

## EC2 Deploy
```bash
cd /home/ubuntu/vhc-platform && \
  git pull --rebase origin main && \
  cd frontend && yarn build && cd .. && \
  sudo systemctl restart gunicorn
```
(No new Python deps; chip icons already imported from lucide-react.)

## Testing
- Backend curl tests: pass (warm 1.2s, reasons populated correctly)
- Lint (ruff + eslint): clean on all 3 files
- Visual smoke test on EC2 still pending user confirmation
