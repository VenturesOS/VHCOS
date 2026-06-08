"""
Train XGBoost LTR Re-ranker (Phase 2 — Jun 2026).

Per `/app/memory/XGBOOST_LTR_SCOPING.md`. This is the offline training
pipeline that consumes the `search_sessions` collection (populated by
`services/ltr_telemetry.py` live + `scripts/backfill_search_sessions.py`
historical) and produces an XGBoost-Ranker model artifact.

Pipeline
--------
1. Load labeled triplets from `search_sessions` (skipping sessions with
   no actions — they contribute no signal).
2. Compute per-candidate features by joining to `candidate_bank`.
3. Compute per-(query, candidate) relevance grades from action chain:
     no_action  → 0
     click_profile / dismiss → 1
     shortlist  → 2
     contact / add_to_pipeline → 3
     hire       → 4
4. Group rows by session_id (rank:pairwise requires grouped data).
5. Train xgboost.XGBRanker with rank:ndcg objective.
6. Eval on held-out 20% of sessions (group-aware split — never split
   within a session).
7. Save to /app/backend/models/ltr_xgb_v{N}.json + a metadata sidecar.

Usage
-----
    # Dry-run (loads data, prints stats, does NOT train)
    python -m scripts.train_ltr_model

    # Train + save
    python -m scripts.train_ltr_model --train

    # Force re-train with custom min-triplets threshold
    python -m scripts.train_ltr_model --train --min-triplets 1500

Exit codes
----------
0 — trained + saved (or dry-run summary).
1 — insufficient data (< MIN_TRIPLETS).
2 — xgboost not installed.
3 — hard error.

Dependencies
------------
xgboost + numpy + pandas (graceful if missing — just dry-run).
Install:  pip install xgboost==2.1.1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, "/app/backend")

from config import db, initialize_db  # noqa: E402

initialize_db()

logger = logging.getLogger("ltr_train")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# ─── Constants ────────────────────────────────────────────────────────────
MIN_TRIPLETS_DEFAULT = 1500   # below this we refuse to train
TEST_SPLIT = 0.20             # group-aware split
MODEL_DIR = Path("/app/backend/data/ltr_models")

ACTION_TO_LABEL: Dict[str, int] = {
    # 0 = no action (negative impression). Computed implicitly per slate.
    "click_profile": 1,
    "dismiss": 1,
    "shortlist": 2,
    "add_to_pipeline": 3,
    "contact": 3,
    "hire": 4,
    "reject": 0,            # explicit negative
    "download_resume": 2,
    "send_message": 3,
}


# ─── Data loader ──────────────────────────────────────────────────────────
async def _load_sessions(min_actions: int = 1) -> List[dict]:
    """Pull search_sessions that have at least N action events."""
    cursor = db.search_sessions.find(
        {"actions": {"$exists": True, "$ne": []}},
        {"_id": 0, "id": 1, "ts": 1, "source": 1, "query": 1,
         "query_meta": 1, "slate": 1, "actions": 1,
         "user_role": 1, "user_id": 1},
    )
    out: List[dict] = []
    async for s in cursor:
        if len(s.get("actions") or []) >= min_actions:
            out.append(s)
    return out


async def _load_candidate_features(candidate_ids: List[str]) -> Dict[str, dict]:
    """Bulk-fetch the candidate fields needed for feature engineering."""
    if not candidate_ids:
        return {}
    proj = {
        "_id": 0, "id": 1,
        "experience_years": 1, "total_experience": 1,
        "current_location": 1, "current_employer": 1,
        "designation": 1, "skills": 1,
        "created_at": 1, "updated_at": 1,
        "cluster_id": 1,
    }
    cursor = db.candidate_bank.find(
        {"id": {"$in": list(set(candidate_ids))}}, proj
    )
    out: Dict[str, dict] = {}
    async for c in cursor:
        out[c["id"]] = c
    return out


# ─── Feature engineering ──────────────────────────────────────────────────
def _feat_from_candidate(c: dict, ref_ts: datetime) -> Dict[str, float]:
    """Per-candidate feature vector. Minimal v1 set — add more as data grows."""
    f: Dict[str, float] = {}
    # Experience (numeric)
    exp = c.get("experience_years") or c.get("total_experience") or 0
    try:
        f["exp_years"] = float(exp)
    except (TypeError, ValueError):
        f["exp_years"] = 0.0
    # Skills (count of comma-separated tokens)
    skills = c.get("skills") or ""
    if isinstance(skills, str):
        f["n_skills"] = float(len([s for s in skills.split(",") if s.strip()]))
    elif isinstance(skills, list):
        f["n_skills"] = float(len(skills))
    else:
        f["n_skills"] = 0.0
    # Has employer / designation / location (binary)
    f["has_employer"] = 1.0 if c.get("current_employer") else 0.0
    f["has_designation"] = 1.0 if c.get("designation") else 0.0
    f["has_location"] = 1.0 if c.get("current_location") else 0.0
    # Recency — days since updated_at (or created_at)
    raw = c.get("updated_at") or c.get("created_at")
    try:
        if isinstance(raw, str):
            ts = datetime.fromisoformat(raw.rstrip("Z"))
            ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        elif isinstance(raw, datetime):
            ts = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        else:
            ts = None
        f["recency_days"] = float((ref_ts - ts).days) if ts else 9999.0
    except Exception:
        f["recency_days"] = 9999.0
    # Cluster membership — non-null = candidate has BGE-derived semantic identity
    f["has_cluster"] = 1.0 if c.get("cluster_id") is not None else 0.0
    return f


# ─── Triplet builder ──────────────────────────────────────────────────────
def _build_triplets(sessions: List[dict], cand_features: Dict[str, dict]) -> Tuple[list, list, list, list]:
    """Returns (X, y, group_sizes, session_ids) for XGBRanker.

    Each row = (features, relevance_label, group_id=session_idx).
    """
    X_rows: List[Dict[str, float]] = []
    y_rows: List[int] = []
    group_sizes: List[int] = []
    session_ids: List[str] = []
    ref_ts = datetime.now(timezone.utc)

    skipped_sessions = 0
    for sess in sessions:
        slate = sess.get("slate") or []
        actions = sess.get("actions") or []
        if not slate:
            skipped_sessions += 1
            continue
        # Build per-candidate label from actions (highest label wins)
        action_label: Dict[str, int] = {}
        for a in actions:
            cid = a.get("candidate_id")
            lbl = ACTION_TO_LABEL.get(a.get("action") or "", 0)
            if cid and lbl > action_label.get(cid, -1):
                action_label[cid] = lbl
        # If no candidate in slate was acted on, the session contributes no
        # positive signal — skip it (the negatives alone are uninformative).
        if not any(cid in action_label for cid in [r.get("candidate_id") for r in slate]):
            skipped_sessions += 1
            continue
        # Emit one row per (slate-rank, candidate)
        group_count = 0
        for row in slate:
            cid = row.get("candidate_id")
            if not cid:
                continue
            c = cand_features.get(cid)
            if c is None:
                continue
            feats = _feat_from_candidate(c, ref_ts)
            # Add rank as a feature (lower rank = higher original confidence)
            feats["original_rank"] = float(row.get("rank") or 0)
            feats["original_score"] = float(row.get("score") or 0.0)
            y = action_label.get(cid, 0)
            X_rows.append(feats)
            y_rows.append(y)
            group_count += 1
        if group_count > 0:
            group_sizes.append(group_count)
            session_ids.append(sess["id"])
        else:
            skipped_sessions += 1
    logger.info(f"Built {len(X_rows)} rows over {len(group_sizes)} groups "
                f"(skipped {skipped_sessions} sessions)")
    return X_rows, y_rows, group_sizes, session_ids


def _group_aware_split(X, y, groups, sids, test_frac: float):
    """Split by session — never split a slate across train/test."""
    import random
    random.seed(42)
    n = len(groups)
    idx = list(range(n))
    random.shuffle(idx)
    n_test = max(1, int(round(n * test_frac)))
    test_set = set(idx[:n_test])

    # Build row index from group boundaries
    boundaries = [0]
    for g in groups:
        boundaries.append(boundaries[-1] + g)

    def _slice(in_test: bool):
        Xs, ys, gs = [], [], []
        for i in range(n):
            start, end = boundaries[i], boundaries[i + 1]
            if (i in test_set) == in_test:
                Xs.extend(X[start:end])
                ys.extend(y[start:end])
                gs.append(end - start)
        return Xs, ys, gs

    X_tr, y_tr, g_tr = _slice(in_test=False)
    X_te, y_te, g_te = _slice(in_test=True)
    return X_tr, y_tr, g_tr, X_te, y_te, g_te


# ─── Train + eval ─────────────────────────────────────────────────────────
def _train_and_eval(X, y, groups, version: int) -> Tuple[Optional[str], dict]:
    try:
        import xgboost as xgb  # noqa: F401
        import numpy as np
    except ImportError:
        return None, {"error": "xgboost or numpy not installed"}

    if len(groups) < 5:
        return None, {"error": f"need ≥5 groups, got {len(groups)}"}

    sids_unused: List[str] = []  # not used downstream
    X_tr, y_tr, g_tr, X_te, y_te, g_te = _group_aware_split(
        X, y, groups, sids_unused, TEST_SPLIT,
    )

    # Featurize: stable column ordering
    feat_cols = sorted(X[0].keys())
    X_tr_np = np.array([[row[c] for c in feat_cols] for row in X_tr], dtype=float)
    X_te_np = np.array([[row[c] for c in feat_cols] for row in X_te], dtype=float)
    y_tr_np = np.array(y_tr, dtype=int)
    y_te_np = np.array(y_te, dtype=int)

    model = xgb.XGBRanker(
        objective="rank:ndcg",
        learning_rate=0.1,
        max_depth=5,
        n_estimators=200,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_weight=1,
        random_state=42,
    )
    model.fit(X_tr_np, y_tr_np, group=g_tr)

    # Eval: NDCG@10 on held-out
    def _ndcg_at_k(y_true_per_group: list, scores_per_group: list, k: int = 10) -> float:
        from math import log2
        ndcgs = []
        for yg, sg in zip(y_true_per_group, scores_per_group):
            order = sorted(range(len(yg)), key=lambda i: -sg[i])
            dcg = sum((2 ** yg[i] - 1) / log2(idx + 2) for idx, i in enumerate(order[:k]))
            ideal = sorted(yg, reverse=True)[:k]
            idcg = sum((2 ** v - 1) / log2(idx + 2) for idx, v in enumerate(ideal))
            ndcgs.append((dcg / idcg) if idcg > 0 else 0.0)
        return sum(ndcgs) / max(1, len(ndcgs))

    # Score test set and group predictions back by g_te boundaries
    if X_te_np.size == 0:
        eval_metrics = {"ndcg@10": None, "n_test_groups": 0}
    else:
        preds = model.predict(X_te_np)
        boundaries = [0]
        for g in g_te:
            boundaries.append(boundaries[-1] + g)
        y_groups, p_groups = [], []
        for i in range(len(g_te)):
            start, end = boundaries[i], boundaries[i + 1]
            y_groups.append(list(y_te_np[start:end]))
            p_groups.append(list(preds[start:end]))
        ndcg = _ndcg_at_k(y_groups, p_groups, k=10)
        eval_metrics = {
            "ndcg@10": round(ndcg, 4),
            "n_test_groups": len(g_te),
            "n_test_rows": int(X_te_np.shape[0]),
            "n_train_groups": len(g_tr),
            "n_train_rows": int(X_tr_np.shape[0]),
        }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / f"ltr_xgb_v{version}.json"
    meta_path = MODEL_DIR / f"ltr_xgb_v{version}.meta.json"
    model.save_model(str(model_path))
    meta = {
        "version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_columns": feat_cols,
        "eval": eval_metrics,
        "hyperparams": {
            "objective": "rank:ndcg",
            "learning_rate": 0.1,
            "max_depth": 5,
            "n_estimators": 200,
        },
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    return str(model_path), {"model_path": str(model_path), "meta": meta}


# ─── Entry point ──────────────────────────────────────────────────────────
async def run(train: bool, min_triplets: int) -> int:
    sessions = await _load_sessions(min_actions=1)
    logger.info(f"Loaded {len(sessions)} sessions with ≥1 action")

    # Gather all candidate ids touched
    cand_ids = set()
    for s in sessions:
        for r in (s.get("slate") or []):
            if r.get("candidate_id"):
                cand_ids.add(r["candidate_id"])
        for a in (s.get("actions") or []):
            if a.get("candidate_id"):
                cand_ids.add(a["candidate_id"])
    logger.info(f"Resolving features for {len(cand_ids)} unique candidates")
    cand_feats = await _load_candidate_features(list(cand_ids))
    logger.info(f"  found {len(cand_feats)} / {len(cand_ids)} in candidate_bank")

    X, y, groups, sids = _build_triplets(sessions, cand_feats)
    n_positives = sum(1 for v in y if v > 0)
    logger.info(f"Triplets: {len(X)} rows | groups: {len(groups)} | positives (label>0): {n_positives}")

    print("=" * 60)
    print("LTR triplet summary")
    print("=" * 60)
    print(f"  sessions               : {len(sessions)}")
    print(f"  candidates resolved    : {len(cand_feats)}/{len(cand_ids)}")
    print(f"  total rows             : {len(X)}")
    print(f"  groups (sessions w/ rows): {len(groups)}")
    print(f"  positive labels        : {n_positives}")
    print(f"  min-triplets threshold : {min_triplets}")
    print()

    if not train:
        print("DRY-RUN — re-run with --train to fit the model.")
        return 0

    if n_positives < min_triplets:
        print(f"REFUSED: insufficient positive triplets ({n_positives} < {min_triplets}).")
        print("        Keep collecting via auto-capture; rerun later.")
        return 1

    # Pick next version number
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(MODEL_DIR.glob("ltr_xgb_v*.json"))
    next_v = 1
    if existing:
        try:
            tags = [int(p.stem.split("_v")[-1]) for p in existing if "meta" not in p.stem]
            next_v = (max(tags) if tags else 0) + 1
        except Exception:
            next_v = 1
    logger.info(f"Training model v{next_v}")
    path, payload = _train_and_eval(X, y, groups, version=next_v)
    if not path:
        print("TRAIN FAILED:", payload.get("error"))
        return 2 if "xgboost" in (payload.get("error") or "").lower() else 3
    print("=" * 60)
    print(f"TRAINED ✓  saved to {path}")
    print(f"  eval: {payload['meta']['eval']}")
    print("=" * 60)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true",
                        help="Actually fit the model (default = dry-run).")
    parser.add_argument("--min-triplets", type=int, default=MIN_TRIPLETS_DEFAULT,
                        help=f"Refuse to train below this positive-triplet count (default {MIN_TRIPLETS_DEFAULT}).")
    args = parser.parse_args()
    rc = asyncio.run(run(train=args.train, min_triplets=args.min_triplets))
    sys.exit(rc)


if __name__ == "__main__":
    main()
