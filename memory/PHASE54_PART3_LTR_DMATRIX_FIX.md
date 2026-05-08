# Phase 54 — Part 3: LTR DMatrix feature_names hotfix
**Date:** 2026-05-07
**Severity:** P0 (silent degradation)
**Status:** ✅ Fixed & Verified (workspace pod) — pending EC2 deploy

## Symptom
Atlas vector_index went READY/QUERYABLE (118,575 docs indexed across
all 3 nodes) and `/api/sourcing/rerank` warm latency dropped from
~37,000ms → ~1,200ms. **However:** every rerank request silently fell
back to vector-only ranking with this warning in the backend log:

```
WARNING:services.sourcing_ml:[SourcingML] LTR scoring failed,
falling back: training data did not have the following fields:
cand_exp_years, ctc_to_max_ratio, ctc_within_budget, exp_distance,
exp_in_band, has_email, has_phone, has_resume, loc_match,
notice_days, skill_overlap, skill_overlap_pct, vector_score
```

i.e. all 13 features were "missing" — meaning the XGBoost predict()
was never actually scoring candidates, despite `model_loaded: true`
in `/api/sourcing/health`. Customers got vector-only results, the
LTR re-ranker was effectively a no-op.

## Root Cause
Training (`scripts/train_sourcing_models.py:167`) builds the DMatrix
**with** `feature_names=feature_names`, which embeds the column
schema into the booster. Inference (`services/sourcing_ml.py:177`)
built the DMatrix **without** the names:
```python
dmat = xgb.DMatrix(X)            # ← anonymous columns
```
XGBoost ≥1.6 strict-validates names and rejects the matrix with
the "training data did not have the following fields" error,
which our `_ltr_score` catches and silently falls back to
`c.get("score", 0.0)` (the vector cosine score).

## Fix
Single-line change in `services/sourcing_ml.py`:
```python
dmat = xgb.DMatrix(X, feature_names=self._feature_names)
```

## Verification (workspace pod, post-fix)
```
=== fresh rerank call ===
http=200 time=2.66s
timing_ms: {'vector_search': 1201, 'ltr_and_diversify': 5, 'total': 1206}
top5 ltr_scores: [0.2505, 0.2505, 0.2498, 0.2498, 0.2433]
top5 vec_scores: [0.7366, 0.7356, 0.7318, 0.7347, 0.7555]
total returned: 15

=== fresh ML warnings (should be EMPTY) ===
Warnings: 0    ✅
```
LTR scores are now real XGBoost predictions (not echoes of vector
scores) and they reorder candidates differently from raw cosine —
confirming the re-ranker is doing its job.

## Files Changed
- `/app/backend/services/sourcing_ml.py` — added
  `feature_names=self._feature_names` to inference DMatrix.

## EC2 Deploy (1 line)
```bash
ssh ubuntu@<ec2>
cd /home/ubuntu/vhc-platform && \
  git pull --rebase origin main && \
  sudo systemctl restart gunicorn && \
  sleep 6 && \
  sudo journalctl -u gunicorn --since "1 min ago" | \
    grep -i "ltr scoring failed" | wc -l    # EXPECTED: 0
```
