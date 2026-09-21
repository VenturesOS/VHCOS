"""Evaluate independently labelled identity queries without importing live services.

Run from any directory::

    python backend/scripts/evaluate_identity_resolution.py --input cases.json

Input is a JSON array (or {"cases": [...]}) of objects with profile, candidates,
expected_candidate_id (null means no true match), label_source (human/synthetic),
retrieval_complete, and optional expected_decision/case_id. Labels must be made
independently of matcher output. Synthetic correctness is regression evidence,
never evidence of real-world precision. No models are trained by this script.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "_offline_identity_resolution", Path(__file__).resolve().parents[1] / "services" / "identity_resolution.py",
)
_ENGINE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_ENGINE)
MAX_CASES = 10000
MAX_CANDIDATES_PER_CASE = 2000
TARGET_PRECISION = 0.99
REVIEW_DECISIONS = {"probable_match", "ambiguous", "insufficient_data"}
CONTEXT_SIGNALS = {
    "experience_company", "experience_title", "experience_location", "institution",
    "certification", "project", "language",
}


def precision_lower_bound(successes: int, total: int, alpha: float = 0.05) -> float:
    """Exact one-sided Clopper-Pearson lower bound for Bernoulli precision.

    Solves P_p(X >= successes) = alpha. The interpretation requires independent,
    representative observations; an uploaded label_source flag cannot prove
    sampling quality. Zero evaluated confirmations yields zero, not 100%.
    """
    if (isinstance(successes, bool) or isinstance(total, bool)
            or not isinstance(successes, int) or not isinstance(total, int)
            or total < 0 or not 0 <= successes <= total or not 0 < alpha < 1):
        raise ValueError("Expected 0 <= successes <= total and 0 < alpha < 1")
    if not successes:
        return 0.0
    if successes == total:
        return alpha ** (1.0 / total)

    def survival(probability):
        # Use the shorter tail; log-sum-exp avoids factorial overflow. Around
        # the root the survival probability is alpha, so 1-CDF is stable too.
        lower_tail = successes <= total - successes + 1
        indexes = range(successes) if lower_tail else range(successes, total + 1)
        terms = [
            math.lgamma(total + 1) - math.lgamma(k + 1) - math.lgamma(total - k + 1)
            + k * math.log(probability) + (total - k) * math.log1p(-probability)
            for k in indexes
        ]
        peak = max(terms)
        value = math.exp(peak) * math.fsum(math.exp(term - peak) for term in terms)
        return max(0.0, 1.0 - value) if lower_tail else value

    low, high = 0.0, 1.0
    for _ in range(64):
        midpoint = (low + high) / 2
        if midpoint == low or midpoint == high:
            break
        if survival(midpoint) < alpha:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def evaluate_cases(cases: list[dict]) -> dict:
    """Report decisions, denominator-aware metrics, and a precision evidence gate.

    Top-choice accuracy is conditional on a labelled true match being present in
    a complete retrieved set. Confirmed recall includes all positive labels, so
    abstention and retrieval misses cannot artificially improve it. Review
    coverage includes all cases asking the user for more evidence or review.
    """
    if not isinstance(cases, list) or len(cases) > MAX_CASES:
        raise ValueError(f"Input must be a list with at most {MAX_CASES} cases")
    counts = dict(human=0, synthetic=0, confirmed=0, true_confirmed=0, positives=0,
                  retrieved=0, top_evaluated=0, top_correct=0, review=0, unresolvable=0,
                  decisions_evaluated=0, decisions_correct=0, context_cases=0,
                  context_supported=0)
    seen_profiles, duplicate_observations, outcomes = set(), 0, []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"Case {index}: expected an object")
        profile, candidates = case.get("profile"), case.get("candidates")
        source = case.get("label_source")
        if (not isinstance(profile, dict) or not isinstance(candidates, list)
                or len(candidates) > MAX_CANDIDATES_PER_CASE
                or any(not isinstance(candidate, dict) for candidate in candidates)
                or source not in {"human", "synthetic"}
                or "expected_candidate_id" not in case
                or not isinstance(case.get("retrieval_complete", True), bool)):
            raise ValueError(f"Case {index}: invalid profile, candidates, label or retrieval metadata")
        expected = case["expected_candidate_id"]
        if expected is not None and (not isinstance(expected, str) or not expected):
            raise ValueError(f"Case {index}: expected_candidate_id must be a non-empty string or null")
        counts[source] += 1
        # Exact repeats must not manufacture independent statistical evidence.
        fingerprint = json.dumps(profile, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        duplicate_observations += fingerprint in seen_profiles
        seen_profiles.add(fingerprint)
        complete = case.get("retrieval_complete", True)
        result = _ENGINE.resolve_profile(profile, candidates, retrieval_complete=complete)
        input_signature = _ENGINE.build_identity_signature(profile)
        if any(input_signature["fields"].get(field) for field in CONTEXT_SIGNALS):
            counts["context_cases"] += 1
            if set(result.get("matched_signals", [])) & CONTEXT_SIGNALS:
                counts["context_supported"] += 1
        decision = result["decision"]
        top_id = (result["top_match"] or {}).get("candidate_id")
        correct_id = expected is not None and top_id == expected
        known_ids = {str(candidate.get("id") or candidate.get("candidate_id") or candidate.get("_id") or "")
                     for candidate in candidates}
        if expected is not None:
            counts["positives"] += 1
            counts["retrieved"] += expected in known_ids
            if complete and expected in known_ids:
                counts["top_evaluated"] += 1
                counts["top_correct"] += correct_id
        if result["exists"]:
            counts["confirmed"] += 1
            counts["true_confirmed"] += correct_id
        counts["review"] += decision in REVIEW_DECISIONS
        counts["unresolvable"] += decision == "insufficient_data" or not complete
        if "expected_decision" in case:
            counts["decisions_evaluated"] += 1
            counts["decisions_correct"] += decision == case["expected_decision"]
        outcomes.append({
            "case_id": case.get("case_id", str(index)), "decision": decision,
            "top_candidate_id": top_id, "expected_candidate_id": expected,
            "expected_decision": case.get("expected_decision"),
            "match_score": result["match_score"], "score_kind": result["score_kind"],
            "reason_codes": result["reason_codes"],
        })

    lower = precision_lower_bound(counts["true_confirmed"], counts["confirmed"])
    gate_reasons = []
    if counts["synthetic"]:
        gate_reasons.append("synthetic_labels_cannot_establish_production_precision")
    if not counts["human"]:
        gate_reasons.append("no_human_labelled_observations")
    if not counts["confirmed"]:
        gate_reasons.append("no_evaluated_confirmations")
    if duplicate_observations:
        gate_reasons.append("duplicate_query_observations")
    if lower < TARGET_PRECISION:
        gate_reasons.append("precision_lower_bound_below_target")
    return {
        "matcher_version": _ENGINE.MATCHER_VERSION,
        "dataset": {"cases": len(cases), "human": counts["human"], "synthetic": counts["synthetic"],
                    "duplicate_query_observations": duplicate_observations},
        "confirmed": {
            "count": counts["confirmed"], "correct": counts["true_confirmed"],
            "incorrect": counts["confirmed"] - counts["true_confirmed"],
            "precision": _ratio(counts["true_confirmed"], counts["confirmed"]),
            "recall": _ratio(counts["true_confirmed"], counts["positives"]),
            "precision_lower_95_one_sided": lower,
        },
        "top_choice": {"correct": counts["top_correct"], "evaluated": counts["top_evaluated"],
                       "accuracy": _ratio(counts["top_correct"], counts["top_evaluated"])},
        "retrieval": {"positive_labels": counts["positives"], "true_match_retrieved": counts["retrieved"],
                      "recall": _ratio(counts["retrieved"], counts["positives"])},
        "longitudinal_context": {
            "cases_observing_context": counts["context_cases"],
            "top_matches_using_context": counts["context_supported"],
            "coverage": _ratio(counts["context_supported"], counts["context_cases"]),
        },
        "review": {"count": counts["review"], "coverage": _ratio(counts["review"], len(cases))},
        "unresolvable": {"count": counts["unresolvable"], "coverage": _ratio(counts["unresolvable"], len(cases))},
        "decisions": {"correct": counts["decisions_correct"], "evaluated": counts["decisions_evaluated"],
                      "accuracy": _ratio(counts["decisions_correct"], counts["decisions_evaluated"])},
        "release_gate": not gate_reasons, "release_gate_reasons": gate_reasons,
        "target_confirmed_precision": TARGET_PRECISION,
        "statistical_method": "exact_one_sided_clopper_pearson_95",
        "sampling_requirement": "Independently labelled, representative real queries; the tool cannot verify sampling quality.",
        "cases": outcomes,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="JSON query-case dataset")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8-sig"))
        cases = payload.get("cases") if isinstance(payload, dict) else payload
        report = evaluate_cases(cases)
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
