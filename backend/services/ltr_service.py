"""
LTR (Learning-to-Rank) reranker service — Phase 56.8 / Phase 2 wire-up.

Loads the offline-trained XGBoost ranker (`scripts/train_ltr_model.py`)
and exposes a rerank function with the same shape as
`_cross_encoder_rerank` so it can slot into the talent-graph search path.

Design
------
- Lazy singleton. The model is loaded on first use, NOT at boot, so
  worker startup stays fast and missing-model deploys don't crash.
- Graceful disable. If xgboost isn't installed, the model file is
  missing, or feature_columns is empty, `is_available()` returns False
  and the caller falls back to its existing rerank path.
- Feature contract matches `scripts/train_ltr_model.py::_feat_from_candidate`
  + adds `original_rank` + `original_score` exactly as trained.
- Thread-safe enough for gunicorn — load uses a module-level lock; once
  loaded, predict() is read-only on the booster.

A/B routing happens in `find_candidates_by_text` — this module only
knows how to rerank a given pool.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Constants ────────────────────────────────────────────────────────────
# Model dir defaults to <backend>/data/ltr_models — resolved relative to
# this file so it works on any deploy path (preview /app, AWS /home/ubuntu/...).
_DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "ltr_models"
MODEL_DIR = Path(os.environ.get("LTR_MODEL_DIR") or _DEFAULT_MODEL_DIR)
DEFAULT_MODEL_FILENAME = os.environ.get("LTR_MODEL_FILENAME", "ltr_xgb_v1.json")
DEFAULT_META_FILENAME = os.environ.get("LTR_META_FILENAME", "ltr_xgb_v1.meta.json")


# ─── Singleton state ──────────────────────────────────────────────────────
_lock = threading.Lock()
_loaded = False
_load_attempted = False
_load_error: Optional[str] = None
_model = None
_feature_columns: List[str] = []
_model_version: Optional[str] = None


# ─── Feature extraction — MUST match train_ltr_model._feat_from_candidate ──
def _feat_from_result(r: Dict[str, Any], ref_ts: datetime) -> Dict[str, float]:
    """Build the feature dict from a search-pool result row.

    The training pipeline computes features from a `candidate_bank` doc;
    here we work from the result dict that's already been hydrated via
    `_enrich_with_candidate_bank`. The fields we need (`skills`,
    `cluster_id`, `updated_at`) are explicitly fetched by the extended
    projection in that enrich step.
    """
    f: Dict[str, float] = {}
    # exp_years
    exp = (
        r.get("experience_years")
        or r.get("total_experience_years")
        or 0
    )
    try:
        f["exp_years"] = float(exp)
    except (TypeError, ValueError):
        f["exp_years"] = 0.0
    # n_skills
    skills = r.get("skills") or ""
    if isinstance(skills, str):
        f["n_skills"] = float(len([s for s in skills.split(",") if s.strip()]))
    elif isinstance(skills, list):
        f["n_skills"] = float(len(skills))
    else:
        f["n_skills"] = 0.0
    # has_* binaries
    f["has_employer"] = 1.0 if r.get("current_employer") else 0.0
    f["has_designation"] = 1.0 if r.get("current_designation") else 0.0
    f["has_location"] = 1.0 if r.get("current_location") else 0.0
    # recency
    raw = r.get("updated_at") or r.get("created_at")
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
    # cluster membership
    f["has_cluster"] = 1.0 if r.get("cluster_id") is not None else 0.0
    return f


# ─── Loader ───────────────────────────────────────────────────────────────
def _load_once() -> bool:
    """Load the booster + metadata. Returns True on success, False on any
    failure (caller sees `is_available() is False`)."""
    global _loaded, _load_attempted, _load_error, _model, _feature_columns, _model_version

    if _loaded:
        return True
    if _load_attempted and not _loaded:
        # Don't keep retrying on every search.
        return False

    with _lock:
        if _loaded:
            return True
        _load_attempted = True
        try:
            model_path = MODEL_DIR / DEFAULT_MODEL_FILENAME
            meta_path = MODEL_DIR / DEFAULT_META_FILENAME
            if not model_path.exists():
                _load_error = f"model file missing: {model_path}"
                logger.info(f"[LTR] {_load_error} — A/B rerank disabled")
                return False
            try:
                import xgboost as xgb
            except ImportError as e:
                _load_error = f"xgboost not installed: {e}"
                logger.info(f"[LTR] {_load_error} — A/B rerank disabled")
                return False
            # Load model
            booster = xgb.XGBRanker()
            booster.load_model(str(model_path))
            # Load feature column ordering (CRITICAL — must match training)
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                _feature_columns = list(meta.get("feature_columns") or [])
                _model_version = str(meta.get("version") or "?")
            else:
                _load_error = f"meta file missing: {meta_path}"
                logger.warning(f"[LTR] {_load_error} — cannot trust feature ordering, disabling")
                return False
            if not _feature_columns:
                _load_error = "meta has no feature_columns"
                logger.warning(f"[LTR] {_load_error}")
                return False
            _model = booster
            _loaded = True
            logger.info(f"[LTR] model v{_model_version} loaded from {model_path} "
                        f"({len(_feature_columns)} features)")
            return True
        except Exception as e:
            _load_error = f"load failed: {e}"
            logger.warning(f"[LTR] {_load_error}")
            return False


def is_available() -> bool:
    return _load_once()


def status() -> Dict[str, Any]:
    """For the admin LTR stats dashboard — exposes whether the LTR arm is live."""
    return {
        "available": _loaded,
        "load_attempted": _load_attempted,
        "load_error": _load_error,
        "model_version": _model_version,
        "feature_columns": _feature_columns,
        "model_dir": str(MODEL_DIR),
    }


# ─── Public rerank API ────────────────────────────────────────────────────
def rerank(
    results: List[Dict[str, Any]],
    query: str,
    limit: int,
) -> Optional[List[Dict[str, Any]]]:
    """Reorder `results` by LTR model score. Returns top-`limit` rows, or
    None on any failure (caller should fall back).

    Each result must already carry `score` (cosine) and the candidate
    enrichment fields. Adds `_ltr_score` + sets `match_type=ltr_xgboost`
    on the returned rows.
    """
    if not results or len(results) < 4:
        return None
    if not _load_once():
        return None
    try:
        import numpy as np
        ref_ts = datetime.now(timezone.utc)
        pool = results[: max(limit, 64)]  # same MAX_PAIRS shape as cross-encoder
        rows: List[List[float]] = []
        for i, r in enumerate(pool):
            f = _feat_from_result(r, ref_ts)
            f["original_rank"] = float(i)
            f["original_score"] = float(r.get("score") or 0.0)
            rows.append([float(f.get(col, 0.0)) for col in _feature_columns])
        X = np.array(rows, dtype=float)
        preds = _model.predict(X)
        for i, r in enumerate(pool):
            r["_ltr_score"] = float(preds[i])
            r["match_type"] = "ltr_xgboost"
        pool.sort(key=lambda r: r.get("_ltr_score") or 0.0, reverse=True)
        for r in pool:
            r.pop("source_text", None)
        return pool[:limit]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[LTR] rerank failed: {e!s} — falling back")
        return None


# ─── A/B routing ──────────────────────────────────────────────────────────
def get_ab_pct() -> int:
    """0-100. Returns 0 if invalid/missing or the LTR arm is unavailable."""
    if not is_available():
        return 0
    try:
        v = int(os.environ.get("LTR_AB_PCT", "10"))
        return max(0, min(100, v))
    except (TypeError, ValueError):
        return 0


def should_use_ltr_arm(routing_key: str) -> bool:
    """Deterministic A/B: hash(user_id+query) % 100 < LTR_AB_PCT.

    Same `routing_key` → same arm — so a user retrying the same query
    gets a consistent experience (key for measuring NDCG over repeats).
    """
    pct = get_ab_pct()
    if pct <= 0:
        return False
    if pct >= 100:
        return True
    # Stable hash — Python's hash() is salted per-process, use a stable algo
    import hashlib
    h = hashlib.md5((routing_key or "").encode("utf-8")).hexdigest()
    bucket = int(h[:8], 16) % 100
    return bucket < pct
