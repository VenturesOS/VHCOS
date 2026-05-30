# XGBoost LTR Reranker — Scoping Doc

**Status:** P3 backlog, ready for a multi-session sprint
**Goal:** Replace the BGE cross-encoder (current precision-layer reranker) with a learned-to-rank XGBoost model trained on real recruiter feedback.
**Expected gain:** +5-15% precision@10 over cross-encoder, ~5x faster inference, eliminates the cross-encoder's GPU dependency (currently CPU on EC2 already, so the speed win is moderate).
**Risk:** Without enough labeled data, an XGBoost LTR model can be *worse* than the cross-encoder. We must collect ≥10k labeled (query, candidate, action) triplets before this is worth shipping.

---

## Why this is NOT a one-session task

| Phase | Effort | Why |
|---|---|---|
| 1. Data collection schema | 2-3 hours | Need a `search_clicks` collection that links searches to subsequent actions (clicked, viewed, added_to_mandate, applied, hired). Some of this is in `activity_logs` but not joined to search session. |
| 2. Data backfill (historical) | 4-6 hours | Mine existing `activity_logs` + `applications` to reconstruct (query → click → outcome) triplets. Will be sparse — most events have no associated search session. |
| 3. Feature engineering | 4-6 hours | Build 30-50 features per (query, candidate) pair: BGE bi-encoder cosine, BGE cross-encoder score, fuzzy name/title overlap, designation match, experience match (Δyears), location radius, skill overlap, recency, recruiter affinity, etc. |
| 4. Training pipeline | 2-3 hours | Train XGBoost-Ranker on grouped queries with `objective=rank:pairwise` or `rank:ndcg`. Use rolling 90-day window, retrain weekly. |
| 5. Eval framework | 3-4 hours | A/B test framework: route 10% of searches to XGB, log NDCG@10 + click-through, compare to cross-encoder baseline. Must beat it on 95% confidence interval over 2 weeks. |
| 6. Serving integration | 2-3 hours | Wire model into `routes/sourcing.py` rerank step. Load once at boot, predict per query batch. |
| 7. Monitoring | 2 hours | Drift detection, feature distribution alerts, automatic rollback if NDCG drops. |
| **Total** | **20-27 hours** (5-6 sessions) | |

---

## Phase 1 — Data Collection Schema (the prerequisite)

Without this in place, nothing else can start. **Recommended first sprint:**

### New collection: `search_sessions`

```json
{
  "id": "uuid",
  "session_id": "tab-session-uuid",     // ties multiple searches in one session
  "user_id": "recruiter-uuid",
  "user_role": "recruiter|account_manager|admin",
  "query": {                            // serialized query fingerprint
    "keywords": "data scientist",
    "skills": ["python", "tensorflow"],
    "min_experience": 3,
    "location": "Bangalore",
    "filters_hash": "sha256(...)"       // dedup repeat queries
  },
  "returned_candidate_ids": ["c1", "c2", ...],
  "returned_scores": [0.92, 0.88, ...],
  "rerank_source": "cross_encoder|xgboost|baseline",  // for A/B
  "ts": "ISODate"
}
```

### Extend `activity_logs` with `search_session_id`

When a recruiter clicks a candidate or moves them through stages within
N minutes of a search, attribute the action back to that search session.

```python
# In every action handler (e.g. routes/candidates.py)
await log_activity(
    user_id=user["id"],
    candidate_id=cand_id,
    action="viewed",
    metadata={"search_session_id": req.headers.get("X-Search-Session-Id")},
)
```

Frontend passes the active search session ID as a header — middleware can pick it up.

### Labels (target variable per (query, candidate) pair)

| Action chain | Label (relevance grade 0–4) |
|---|---|
| Returned in search but no click | 0 |
| Clicked / Viewed | 1 |
| Added to mandate / Shortlisted | 2 |
| Application submitted | 3 |
| Hired | 4 |

---

## Phase 3 — Feature Set (preview)

| Feature | Source | Type |
|---|---|---|
| `bi_encoder_cosine` | BGE bi-encoder | float |
| `cross_encoder_score` | BGE cross-encoder | float |
| `query_in_designation` | `routes/sourcing.py` | int (0/1) |
| `query_in_skills` | candidate.skills | int (count) |
| `exp_diff` | abs(query_min_exp - cand.total_experience) | float |
| `location_match` | candidate.current_location ⊂ query.locations | int |
| `recency_days` | (now - candidate.updated_at).days | float |
| `recruiter_affinity` | how often THIS recruiter shortlists from THIS cluster | float |
| `cluster_diversity` | candidate.cluster_id, query.cluster_distribution | float |
| ... 30+ more | ... | ... |

---

## Recommended next steps (in order)

1. **Week 1 (this becomes the next session):** Build `search_sessions` collection + auto-instrument frontend search → backend. Just collect data. **No model yet.** Ship the telemetry pipeline.
2. **Week 2-3 (data soak):** Let real recruiters use the platform. Aim for 5k+ labeled triplets. Monitor via Analytics Hub.
3. **Week 4:** Backfill historical sessions from `activity_logs` (best-effort).
4. **Week 5:** Train first XGBoost model, eval offline against held-out queries.
5. **Week 6:** Wire into `routes/sourcing.py` with 10% A/B traffic split.
6. **Week 7-8:** Monitor → either roll out fully or roll back.

---

## Alternative: lighter-weight precision win

If you want a faster win that's NOT a full LTR sprint:

**Option:** Add 3-5 hand-crafted features as a **post-rerank tie-breaker** on top of the cross-encoder. No ML training required.

Example:
```python
# In routes/sourcing.py after cross_encoder rerank:
for c in results:
    c.score += 0.05 if c.location_match else 0
    c.score += 0.10 if c.exp_in_range else -0.05
    c.score += 0.03 * min(c.skill_overlap, 5)
results.sort(key=lambda x: x.score, reverse=True)
```

Effort: 1-2 hours. Gain: ~3-5% precision@10. Good ROI without the full LTR commitment.

---

## Files this would touch (when ready)

- `backend/services/ltr_service.py` (new) — model load, predict
- `backend/scripts/train_ltr_model.py` (new) — training pipeline
- `backend/scripts/backfill_search_sessions.py` (new) — historical mining
- `backend/routes/sourcing.py` — replace cross_encoder call with `ltr_service.rerank()`
- `backend/routes/search_sessions.py` (new) — telemetry
- `frontend/src/pages/shared/AdvancedSearchPage.jsx` — pass session_id

---

## Open questions for next session start

1. Do we have enough historical click/application data to mine, OR do we need to ship telemetry first and collect for 2-3 weeks?
2. Is the BGE cross-encoder actually the bottleneck? Profile first — maybe bi-encoder + hand-crafted tie-breakers is enough.
3. What's our P95 search latency budget? XGB inference on 100 candidates is ~10ms — doable, but adds an env-loading dependency.

---

**TL;DR:** This is a 5-6 session feature. The right first step is **Phase 1 (telemetry)**, not jumping straight to training. We have all the tools (xgboost is one `pip install` away, BGE features already exist via the sidecar) — we're just missing the labeled data.
