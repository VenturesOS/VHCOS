"""
Train the sourcing re-ranker bundle (XGBoost LTR + PCA + meta).

Reads from production Mongo:
  • applications  — for labels (positive = progressed past 'sourced')
  • candidate_bank — candidate features
  • jobs           — job features
  • candidate_embeddings — 384-d BGE vectors → fits PCA → 128-d

Outputs to backend/ml_models/sourcing_v1/:
  • ltr_xgb.joblib          XGBoost Booster
  • pca_384_to_128.joblib   sklearn PCA
  • meta.joblib             {trained_at, n_train, auc, feature_names, ...}

Run on EC2 (or any host with prod DB access):

    cd /home/ubuntu/vhc-platform/backend
    source venv/bin/activate
    pip install xgboost joblib  # if not yet installed
    python3 scripts/train_sourcing_models.py

Re-train weekly (cron) once the model is wired in. CPU-only; on a
t3.medium 14k applications take ~60-90s end-to-end.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Backend importable
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("train_sourcing")

# Stages we treat as "the recruiter advanced this candidate".
POSITIVE_STAGES = {
    "submitted_to_client", "shortlisted", "interview",
    "employer_approved", "offered", "hired", "joined",
}
# Stages we treat as "the recruiter rejected / parked".
NEGATIVE_STAGES = {"rejected", "removed", "on_hold"}
# All else (sourced, applied) → also treated as negative implicit signal.


async def _build_dataset(db, max_apps: int):
    """Pull applications + candidate + job docs in batches.
    Returns (X, y, feature_names, metadata).
    """
    from services.sourcing_ml import _SourcingML
    extract = _SourcingML._extract_features

    cursor = db.applications.find(
        {}, {"_id": 0, "candidate_id": 1, "job_id": 1, "stage": 1}
    ).limit(max_apps)
    apps = await cursor.to_list(max_apps)

    # Resolve candidate + job docs in batches to keep Mongo load reasonable
    cand_ids = list({a["candidate_id"] for a in apps if a.get("candidate_id")})
    job_ids = list({a["job_id"] for a in apps if a.get("job_id")})

    cand_map = {}
    for i in range(0, len(cand_ids), 500):
        batch = cand_ids[i:i + 500]
        async for c in db.candidate_bank.find(
            {"id": {"$in": batch}},
            {
                "_id": 0, "id": 1, "skills": 1, "key_skills": 1,
                "experience_years": 1, "total_experience_years": 1,
                "current_location": 1, "location": 1,
                "current_salary": 1, "current_ctc": 1,
                "notice_period_days": 1, "resume_url": 1, "resume_path": 1,
                "email": 1, "phone": 1,
            }
        ):
            cand_map[c["id"]] = c

    job_map = {}
    for i in range(0, len(job_ids), 500):
        batch = job_ids[i:i + 500]
        async for j in db.jobs.find(
            {"id": {"$in": batch}},
            {
                "_id": 0, "id": 1, "required_skills": 1, "skills": 1,
                "experience_min": 1, "experience_max": 1,
                "min_experience": 1, "max_experience": 1,
                "location": 1, "salary_max": 1, "max_salary": 1,
            }
        ):
            job_map[j["id"]] = j

    rows, labels = [], []
    skipped = 0
    for a in apps:
        cand = cand_map.get(a.get("candidate_id"))
        job = job_map.get(a.get("job_id"))
        if not cand or not job:
            skipped += 1
            continue
        # Vector_score isn't available retroactively for past applications —
        # we use 0.0 as a neutral baseline. The model still learns from the
        # other ~12 features.
        feats = extract(cand, job, vector_score=0.0)
        rows.append(feats)
        labels.append(1 if a.get("stage") in POSITIVE_STAGES else 0)

    feature_names = sorted(rows[0].keys()) if rows else []
    return rows, labels, feature_names, {"skipped": skipped, "total_apps": len(apps)}


async def _build_pca(db, dim: int = 128, max_samples: int = 5000):
    """Fit a PCA(384 → dim) on a sample of existing candidate embeddings."""
    import numpy as np
    from sklearn.decomposition import PCA

    cursor = db.candidate_embeddings.find(
        {"embedding": {"$exists": True}},
        {"_id": 0, "embedding": 1},
    ).limit(max_samples)
    docs = await cursor.to_list(max_samples)
    vecs = [d["embedding"] for d in docs if d.get("embedding")]
    if len(vecs) < 200:
        logger.warning(f"PCA: only {len(vecs)} embeddings, need >= 200. Skipping PCA.")
        return None
    X = np.array(vecs, dtype="float32")
    n_components = min(dim, X.shape[1] - 1, X.shape[0] - 1)
    pca = PCA(n_components=n_components, random_state=42).fit(X)
    var = float(pca.explained_variance_ratio_.sum())
    logger.info(f"PCA fitted: {X.shape[1]} → {n_components} dims, retains {var:.1%} variance")
    return pca


async def run(max_apps: int, output_dir: Path):
    import joblib
    import numpy as np
    import xgboost as xgb
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import train_test_split

    from config import db, initialize_db
    initialize_db()

    logger.info("Building training dataset…")
    rows, labels, feature_names, ds_meta = await _build_dataset(db, max_apps)
    logger.info(f"  rows={len(rows)} positives={sum(labels)} skipped={ds_meta['skipped']}")
    if len(rows) < 100 or sum(labels) < 10:
        logger.error("Not enough training data. Need >= 100 rows AND >= 10 positives.")
        return 1

    X = np.array([[r.get(n, 0.0) for n in feature_names] for r in rows], dtype="float32")
    y = np.array(labels, dtype="int32")

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
    logger.info(f"  train={len(X_tr)}  test={len(X_te)}")

    # Class imbalance: ~5% positive → scale_pos_weight = #neg / #pos
    pos_weight = (y_tr == 0).sum() / max((y_tr == 1).sum(), 1)
    logger.info(f"  scale_pos_weight={pos_weight:.2f}")

    dtr = xgb.DMatrix(X_tr, label=y_tr, feature_names=feature_names)
    dte = xgb.DMatrix(X_te, label=y_te, feature_names=feature_names)

    params = {
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "eta": 0.1,
        "max_depth": 5,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "scale_pos_weight": pos_weight,
        "tree_method": "hist",
        "verbosity": 0,
    }
    booster = xgb.train(
        params, dtr,
        num_boost_round=300,
        evals=[(dtr, "train"), (dte, "test")],
        early_stopping_rounds=20,
        verbose_eval=50,
    )
    auc = roc_auc_score(y_te, booster.predict(dte))
    logger.info(f"Final test AUC: {auc:.4f}")

    # Feature importance for debugging
    imp = booster.get_score(importance_type="gain")
    top = sorted(imp.items(), key=lambda x: -x[1])[:8]
    logger.info("Top features by gain:")
    for name, gain in top:
        logger.info(f"  {name:25s} {gain:>8.2f}")

    logger.info("Fitting PCA on candidate_embeddings…")
    pca = await _build_pca(db, dim=128)

    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(booster, output_dir / "ltr_xgb.joblib")
    if pca is not None:
        joblib.dump(pca, output_dir / "pca_384_to_128.joblib")
    joblib.dump(
        {
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "n_train": len(X_tr),
            "n_test": len(X_te),
            "n_positive": int((y_tr == 1).sum() + (y_te == 1).sum()),
            "auc": round(auc, 4),
            "feature_names": feature_names,
            "feature_importance_gain": dict(top),
            "scale_pos_weight": float(pos_weight),
            "pca_dims": pca.n_components_ if pca is not None else None,
            "pca_variance": float(pca.explained_variance_ratio_.sum()) if pca is not None else None,
        },
        output_dir / "meta.joblib",
    )
    logger.info(f"✅ Saved bundle → {output_dir.resolve()}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--max-apps", type=int, default=50_000,
                    help="Max applications to pull (default 50k)")
    ap.add_argument("--output", type=Path,
                    default=Path(_BACKEND_DIR) / "ml_models" / "sourcing_v1",
                    help="Output directory for model bundle")
    args = ap.parse_args()

    rc = asyncio.run(run(args.max_apps, args.output))
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
