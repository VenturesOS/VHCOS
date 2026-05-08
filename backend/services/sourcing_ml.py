"""
Sourcing ML Re-Ranker — XGBoost LTR + PCA + k-Means Diversifier.

Loaded once per gunicorn worker (lazy singleton). Inference is pure CPU
numpy/scikit-learn — no GPU, no network calls. Total RAM footprint per
worker after warm-up: ~150-200 MB (scikit-learn + xgboost + matrices).

Usage:
    from services.sourcing_ml import sourcing_ml

    # Re-rank a top-k pool from vector search
    ranked = sourcing_ml.rerank(
        job_doc=job,
        pool=[{"candidate_id": "..", "score": 0.83, ...}, ...],
        top_k=25,
        diversify=True,
    )

Models are trained by `scripts/train_sourcing_models.py` and stored at
`backend/ml_models/sourcing_v1/*.joblib`. If models are missing, every
public method returns the input pool unchanged (graceful degradation).
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Model artifacts directory — shared across gunicorn workers.
_MODEL_DIR = Path(os.environ.get(
    "SOURCING_MODEL_DIR",
    str(Path(__file__).parent.parent / "ml_models" / "sourcing_v1"),
))


class _SourcingML:
    """Singleton wrapper around the 3-stage re-ranking pipeline."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded = False
        self._xgb = None         # xgboost.Booster
        self._pca = None         # sklearn.decomposition.PCA  (384 → 128)
        self._feature_names: list[str] = []
        self._meta: dict = {}

    # ── Lazy loader ───────────────────────────────────────────────────────
    def _ensure_loaded(self) -> bool:
        if self._loaded:
            return self._xgb is not None
        with self._lock:
            if self._loaded:
                return self._xgb is not None
            self._loaded = True
            try:
                import joblib  # noqa: F401
                xgb_path = _MODEL_DIR / "ltr_xgb.joblib"
                pca_path = _MODEL_DIR / "pca_384_to_128.joblib"
                meta_path = _MODEL_DIR / "meta.joblib"

                if not xgb_path.exists():
                    logger.warning(
                        f"[SourcingML] Model bundle missing at {_MODEL_DIR}. "
                        f"Run `python3 scripts/train_sourcing_models.py` "
                        f"to enable LTR re-ranking. Re-rank will pass-through."
                    )
                    return False

                self._xgb = joblib.load(xgb_path)
                if pca_path.exists():
                    self._pca = joblib.load(pca_path)
                if meta_path.exists():
                    self._meta = joblib.load(meta_path)
                self._feature_names = self._meta.get("feature_names", [])
                logger.info(
                    f"[SourcingML] Loaded: xgb({len(self._feature_names)} feats) "
                    f"+ pca({self._pca is not None}). "
                    f"Trained {self._meta.get('trained_at', '?')} on "
                    f"{self._meta.get('n_train', '?')} examples "
                    f"(AUC={self._meta.get('auc', '?')})."
                )
                return True
            except Exception as e:
                logger.error(f"[SourcingML] Load failed: {e}", exc_info=True)
                self._xgb = None
                return False

    # ── PCA helper (query-time embedding compression) ─────────────────────
    def compress_embedding(self, vec: list[float]) -> list[float]:
        """Compress a 384-d BGE vector to 128-d using the trained PCA matrix.
        Returns the original vector if PCA isn't loaded."""
        if not self._ensure_loaded() or self._pca is None or not vec:
            return vec
        try:
            import numpy as np
            v = np.array(vec, dtype="float32").reshape(1, -1)
            if v.shape[1] != self._pca.n_features_in_:
                return vec  # mismatched, skip
            return self._pca.transform(v)[0].tolist()
        except Exception as e:
            logger.warning(f"[SourcingML] compress_embedding failed: {e}")
            return vec

    # ── Feature extraction (single candidate × job pair) ──────────────────
    @staticmethod
    def _extract_features(candidate: dict, job: dict, vector_score: float) -> dict[str, float]:
        """Cheap per-pair features. Mirrors what
        `scripts/train_sourcing_models.py` builds during training — keep in
        lockstep or model accuracy degrades silently.
        """
        def _num(v, default=0.0):
            try:
                return float(v) if v not in (None, "", "Not Available") else default
            except (ValueError, TypeError):
                return default

        def _list(v):
            if isinstance(v, list):
                return [str(x).lower().strip() for x in v if x]
            return []

        cand_skills = set(_list(candidate.get("skills") or candidate.get("key_skills")))
        job_skills = set(_list(job.get("required_skills") or job.get("skills")))
        skill_overlap = len(cand_skills & job_skills)
        skill_overlap_pct = skill_overlap / max(len(job_skills), 1)

        cand_exp = _num(candidate.get("experience_years") or candidate.get("total_experience_years"))
        job_min_exp = _num(job.get("experience_min") or job.get("min_experience"))
        job_max_exp = _num(job.get("experience_max") or job.get("max_experience"), 99.0)
        exp_in_band = 1.0 if job_min_exp <= cand_exp <= job_max_exp else 0.0
        exp_distance = max(job_min_exp - cand_exp, cand_exp - job_max_exp, 0.0)

        cand_loc = (candidate.get("current_location") or candidate.get("location") or "").lower().strip()
        job_loc = (job.get("location") or "").lower().strip()
        loc_match = 1.0 if cand_loc and job_loc and (cand_loc in job_loc or job_loc in cand_loc) else 0.0

        cand_ctc = _num(candidate.get("current_salary") or candidate.get("current_ctc"))
        job_max_sal = _num(job.get("salary_max") or job.get("max_salary"))
        ctc_within_budget = 1.0 if (cand_ctc and job_max_sal and cand_ctc <= job_max_sal) else 0.0
        ctc_to_max_ratio = (cand_ctc / job_max_sal) if (cand_ctc and job_max_sal) else 0.0

        notice_days = _num(candidate.get("notice_period_days"))

        return {
            "vector_score": float(vector_score),
            "skill_overlap": float(skill_overlap),
            "skill_overlap_pct": float(skill_overlap_pct),
            "cand_exp_years": cand_exp,
            "exp_in_band": exp_in_band,
            "exp_distance": float(exp_distance),
            "loc_match": loc_match,
            "ctc_within_budget": ctc_within_budget,
            "ctc_to_max_ratio": float(ctc_to_max_ratio),
            "notice_days": notice_days,
            "has_resume": 1.0 if (candidate.get("resume_url") or candidate.get("resume_path")) else 0.0,
            "has_email": 1.0 if candidate.get("email") else 0.0,
            "has_phone": 1.0 if candidate.get("phone") else 0.0,
        }

    # ── Stage A: XGBoost LTR re-rank ──────────────────────────────────────
    def _ltr_score(self, pool: list[dict], job: dict) -> tuple[list[float], list[list[dict]]]:
        """Score the pool with the trained LTR booster and ALSO return a
        list of `match_reasons` for each candidate (top-2 favorable
        features by global gain × is_favorable). Falls back to
        (vector_scores, []) on any failure.
        """
        if not self._ensure_loaded() or not pool:
            return [c.get("score", 0.0) for c in pool], [[] for _ in pool]
        try:
            import numpy as np
            import xgboost as xgb
            features = [
                self._extract_features(c, job, c.get("score", 0.0))
                for c in pool
            ]
            X = np.array([[f.get(name, 0.0) for name in self._feature_names] for f in features],
                         dtype="float32")
            dmat = xgb.DMatrix(X, feature_names=self._feature_names)
            scores = self._xgb.predict(dmat)
            ctx = self._job_context_flags(job)
            reasons_list = [self._explain_features(f, ctx) for f in features]
            return [float(s) for s in scores], reasons_list
        except Exception as e:
            logger.warning(f"[SourcingML] LTR scoring failed, falling back: {e}")
            return [c.get("score", 0.0) for c in pool], [[] for _ in pool]

    # ── Job-context flags: which comparison features are meaningful? ──────
    @staticmethod
    def _job_context_flags(job: dict) -> dict[str, bool]:
        """Return which job fields exist so we don't show misleading
        explanations like "Experience fit" when no job exp range was
        supplied (defaulted 0..99 ⇒ everyone trivially fits).
        """
        if not job:
            return {"skills": False, "loc": False, "exp": False, "ctc": False}
        skills = job.get("required_skills") or job.get("skills") or []
        return {
            "skills": bool(skills) if isinstance(skills, list) else bool(str(skills).strip()),
            "loc":    bool((job.get("location") or "").strip()),
            "exp":    bool(job.get("experience_min") or job.get("min_experience")
                           or job.get("experience_max") or job.get("max_experience")),
            "ctc":    bool(job.get("salary_max") or job.get("max_salary")),
        }

    # ── Per-candidate explanation: top-N favorable features ───────────────
    def _explain_features(self, feats: dict, ctx: dict[str, bool], top_n: int = 2) -> list[dict]:
        """Return up to `top_n` `{label, feature, weight}` dicts ranked by
        the model's global gain importance, filtered to features that
        actually look favorable for this candidate AND that had a real
        comparison context (so we don't show "Experience fit" for a
        query-only search where no exp range was supplied).
        """
        gain = (self._meta.get("feature_importance_gain") or {})
        # Cosine semantic match — always meaningful (it's the query similarity)
        # is hard-coded with a sensible weight floor since it doesn't show up
        # in tree-gain dict (vectors aren't a tree split feature).
        SEMANTIC_GAIN = 30.0
        skill_pct = feats.get("skill_overlap_pct", 0.0)
        candidates: list[dict] = []

        # Job-comparison features (only when context exists)
        if ctx.get("skills") and skill_pct >= 0.2:
            candidates.append({
                "label": f"{int(round(skill_pct * 100))}% skill match",
                "feature": "skill_overlap_pct",
                "weight": float(gain.get("skill_overlap_pct", 0.0)),
            })
        if ctx.get("ctc") and feats.get("ctc_within_budget", 0) >= 1.0:
            candidates.append({
                "label": "Within budget",
                "feature": "ctc_within_budget",
                "weight": float(gain.get("ctc_within_budget", 0.0)),
            })
        if ctx.get("loc") and feats.get("loc_match", 0) >= 1.0:
            candidates.append({
                "label": "Location match",
                "feature": "loc_match",
                "weight": float(gain.get("loc_match", 0.0)),
            })
        if ctx.get("exp") and feats.get("exp_in_band", 0) >= 1.0:
            candidates.append({
                "label": "Experience fit",
                "feature": "exp_in_band",
                "weight": float(gain.get("exp_in_band", 0.0)),
            })

        # Always-meaningful candidate-quality signals
        v = feats.get("vector_score", 0.0)
        if v >= 0.6:
            candidates.append({
                "label": f"{int(round(v * 100))}% semantic match",
                "feature": "vector_score",
                "weight": SEMANTIC_GAIN,
            })
        nd = feats.get("notice_days", 0.0)
        if 0 < nd <= 30:
            candidates.append({
                "label": f"{int(nd)}d notice",
                "feature": "notice_days",
                "weight": float(gain.get("notice_days", 0.0)),
            })
        ce = feats.get("cand_exp_years", 0.0)
        if ce >= 8:
            candidates.append({
                "label": f"{int(ce)} yrs experience",
                "feature": "cand_exp_years",
                "weight": float(gain.get("cand_exp_years", 0.0)) + 5.0,
            })
        if feats.get("has_phone", 0) >= 1.0:
            candidates.append({
                "label": "Phone available",
                "feature": "has_phone",
                "weight": float(gain.get("has_phone", 0.0)),
            })
        if feats.get("has_resume", 0) >= 1.0:
            candidates.append({
                "label": "Resume on file",
                "feature": "has_resume",
                "weight": float(gain.get("has_resume", 0.0)),
            })

        # Sort by global gain desc — the most impactful "yes" signal first.
        candidates.sort(key=lambda x: -x["weight"])
        return candidates[:top_n]

    # ── Stage B: k-Means diversification ──────────────────────────────────
    @staticmethod
    def _diversify(pool: list[dict], top_k: int, n_clusters: int = 10) -> list[dict]:
        """Cluster the top pool by embedding (or skills+exp+loc proxy) and
        return the highest-LTR candidate from each cluster, in LTR order.
        Avoids returning 25 near-duplicate profiles.
        """
        if len(pool) <= top_k:
            return pool
        try:
            import numpy as np
            from sklearn.cluster import KMeans

            # Build a simple feature matrix from each candidate's available
            # vector. Falls back to skill-count / exp / loc-hash if no vec.
            vecs = []
            for c in pool:
                v = c.get("embedding") or c.get("_embedding")
                if v and isinstance(v, list):
                    vecs.append(v)
                else:
                    # Cheap fallback signature — keeps clustering working
                    # even when embeddings aren't carried through.
                    skills = c.get("skills") or c.get("key_skills") or []
                    sig = [
                        len(skills) if isinstance(skills, list) else 0,
                        float(c.get("experience_years") or 0),
                        hash((c.get("current_location") or "").lower()) % 1000 / 1000.0,
                        hash((c.get("current_employer") or "").lower()) % 1000 / 1000.0,
                    ]
                    vecs.append(sig)

            # Normalize to common dimensionality
            target_dim = max(len(v) for v in vecs)
            vecs = [v + [0.0] * (target_dim - len(v)) for v in vecs]
            X = np.array(vecs, dtype="float32")

            n_clusters = min(n_clusters, top_k, len(pool))
            km = KMeans(n_clusters=n_clusters, n_init=3, random_state=42).fit(X)
            labels = km.labels_

            # Pick the highest LTR-scored candidate from each cluster
            picked: dict[int, dict] = {}
            for c, lbl in zip(pool, labels):
                if lbl not in picked or c.get("ltr_score", 0) > picked[lbl].get("ltr_score", 0):
                    picked[lbl] = c

            # Order picked clusters by their representative's ltr_score, then
            # fill remaining slots from the unselected pool by ltr_score.
            picks = sorted(picked.values(), key=lambda x: -x.get("ltr_score", 0))
            chosen_ids = {c.get("candidate_id") or c.get("id") for c in picks}
            remaining = [
                c for c in pool
                if (c.get("candidate_id") or c.get("id")) not in chosen_ids
            ]
            remaining.sort(key=lambda x: -x.get("ltr_score", 0))
            return (picks + remaining)[:top_k]
        except Exception as e:
            logger.warning(f"[SourcingML] Diversify failed, falling back: {e}")
            return sorted(pool, key=lambda x: -x.get("ltr_score", 0))[:top_k]

    # ── Public API ────────────────────────────────────────────────────────
    def rerank(
        self,
        job_doc: dict,
        pool: list[dict],
        top_k: int = 25,
        diversify: bool = True,
    ) -> list[dict]:
        """Re-rank a candidate pool using XGBoost LTR + (optional) k-Means.
        Falls through to vector_score-sorted top-k if model artifacts are
        missing — never raises.
        """
        if not pool:
            return []

        # Stage A: LTR
        scores, reasons_list = self._ltr_score(pool, job_doc or {})
        for c, s, reasons in zip(pool, scores, reasons_list):
            c["ltr_score"] = s
            c["match_reasons"] = reasons

        # Stage B: diversify (optional) — operates on top 200 by LTR
        head = sorted(pool, key=lambda x: -x.get("ltr_score", 0))[:200]
        if diversify:
            return self._diversify(head, top_k)
        return head[:top_k]

    @property
    def is_loaded(self) -> bool:
        self._ensure_loaded()
        return self._xgb is not None

    @property
    def meta(self) -> dict:
        self._ensure_loaded()
        return dict(self._meta)


# Module-level singleton
sourcing_ml = _SourcingML()
