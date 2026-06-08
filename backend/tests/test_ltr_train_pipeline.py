"""
Regression: XGBoost LTR training pipeline (Phase 2, Jun 2026).

Validates:
  - _feat_from_candidate produces stable features even when fields missing
  - _build_triplets correctly skips sessions with no positive-labeled
    candidates (uninformative)
  - _build_triplets emits one row per (slate-rank, candidate) and assigns
    the right labels via ACTION_TO_LABEL precedence (highest wins)
"""
from datetime import datetime, timezone

from scripts.train_ltr_model import (
    ACTION_TO_LABEL,
    _build_triplets,
    _feat_from_candidate,
)


def test_feat_handles_missing_fields():
    ref_ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
    feats = _feat_from_candidate({}, ref_ts)
    # Must produce a stable set of keys even on empty candidate
    assert "exp_years" in feats
    assert "n_skills" in feats
    assert feats["exp_years"] == 0.0
    assert feats["has_employer"] == 0.0


def test_feat_parses_real_candidate():
    ref_ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
    cand = {
        "experience_years": 8,
        "current_employer": "TestCo",
        "designation": "ML Engineer",
        "current_location": "Bengaluru",
        "skills": "python,tensorflow,xgboost",
        "updated_at": "2026-05-25T10:00:00+00:00",
        "cluster_id": 12,
    }
    f = _feat_from_candidate(cand, ref_ts)
    assert f["exp_years"] == 8.0
    assert f["n_skills"] == 3.0
    assert f["has_employer"] == 1.0
    assert f["has_designation"] == 1.0
    assert f["has_location"] == 1.0
    assert f["has_cluster"] == 1.0
    assert 6 <= f["recency_days"] <= 8


def test_build_triplets_skips_sessions_without_positives():
    """A session whose action target is NOT in its slate contributes no
    learning signal — must be skipped. (Defensive: backfill or telemetry
    bugs can produce this state.)"""
    sessions = [{
        "id": "s1",
        "slate": [{"rank": 0, "candidate_id": "c1", "score": 0.9}],
        "actions": [{"candidate_id": "c-other", "action": "shortlist"}],
    }]
    cand_feats = {"c1": {}, "c-other": {}}
    X, y, groups, sids = _build_triplets(sessions, cand_feats)
    assert X == [] and y == [] and groups == []


def test_build_triplets_emits_one_row_per_slate_position():
    sessions = [{
        "id": "s1",
        "slate": [
            {"rank": 0, "candidate_id": "c1", "score": 0.9},
            {"rank": 1, "candidate_id": "c2", "score": 0.8},
            {"rank": 2, "candidate_id": "c3", "score": 0.7},
        ],
        "actions": [
            {"candidate_id": "c1", "action": "shortlist"},  # label 2
            {"candidate_id": "c3", "action": "hire"},       # label 4
        ],
    }]
    cand_feats = {"c1": {}, "c2": {}, "c3": {}}
    X, y, groups, sids = _build_triplets(sessions, cand_feats)
    # 3 rows, 1 group of size 3
    assert len(X) == 3
    assert groups == [3]
    # Labels: c1=2, c2=0 (no action), c3=4
    assert y == [2, 0, 4]


def test_build_triplets_takes_highest_label_when_multiple_actions():
    """If a candidate is acted on multiple times, ranker should learn from
    the strongest signal (e.g. clicked → shortlisted → hired = label 4)."""
    sessions = [{
        "id": "s1",
        "slate": [{"rank": 0, "candidate_id": "c1", "score": 0.9}],
        "actions": [
            {"candidate_id": "c1", "action": "click_profile"},  # 1
            {"candidate_id": "c1", "action": "shortlist"},      # 2
            {"candidate_id": "c1", "action": "hire"},           # 4
        ],
    }]
    X, y, groups, sids = _build_triplets(sessions, {"c1": {}})
    assert y == [4]


def test_action_label_mapping_matches_scoping_doc():
    # Hard-pin the mapping — changes here have downstream training impact,
    # so this test forces a deliberate code review when the schema evolves.
    assert ACTION_TO_LABEL["hire"] == 4
    assert ACTION_TO_LABEL["shortlist"] == 2
    assert ACTION_TO_LABEL["contact"] == 3
    assert ACTION_TO_LABEL["click_profile"] == 1
    assert ACTION_TO_LABEL["reject"] == 0


if __name__ == "__main__":
    test_feat_handles_missing_fields()
    test_feat_parses_real_candidate()
    test_build_triplets_skips_sessions_without_positives()
    test_build_triplets_emits_one_row_per_slate_position()
    test_build_triplets_takes_highest_label_when_multiple_actions()
    test_action_label_mapping_matches_scoping_doc()
    print("PASS: all LTR training pipeline cases")
