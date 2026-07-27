"""
extension_preview.py — hover-card preview endpoint for the capture extension
============================================================================

GET /api/extension/candidate-preview/{candidate_id}?mandate_id=...

Powers the v6.1.0 "Already in Database" badge hover card: contact details,
salary expectation, notice period, and a numeric match % against the
recruiter's active mandate.

Design constraints (why this isn't just /evaluate-fit):
- Hover must render in < 400 ms, so this runs ONLY the rule-based
  evaluators from services.extension_service (skills / experience /
  salary / location / notice) and deliberately skips the AI
  comprehensive evaluation and the data-completeness checks.
- /evaluate-fit takes a *scraped* profile; here the candidate is already
  in the bank, so we load the richer stored document (phone, email,
  expected_salary, notice_period) by id.
- The green/yellow/red criteria are collapsed into one weighted score:
  skills 40%, experience 20%, salary 15%, location 15%, notice 10%,
  renormalized over the categories that actually produced signal.

Registration (backend/server.py):
    extension_preview_router = _safe_import("routes.extension_preview",
                                            "extension_preview_router")
  ...then add `extension_preview_router` to the same include list that
  registers `extension_router`.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from config import db
from utils.auth import get_current_user
from services.extension_service import (
    evaluate_skills,
    evaluate_experience,
    evaluate_salary,
    evaluate_location,
    evaluate_notice,
)

logger = logging.getLogger(__name__)

extension_preview_router = APIRouter(prefix="/api/extension", tags=["Extension"])

# Category weights for the numeric score. Skills dominate because that is
# how recruiters triage; notice matters least at first glance.
_WEIGHTS = {
    "skills": 0.40,
    "experience": 0.20,
    "salary": 0.15,
    "location": 0.15,
    "notice": 0.10,
}
_COLOR_SCORE = {"green": 1.0, "yellow": 0.5, "red": 0.0}

_CANDIDATE_PROJECTION = {
    "_id": 0, "id": 1, "name": 1, "phone": 1, "email": 1,
    "current_salary": 1, "expected_salary": 1,
    "notice_period": 1, "notice_period_days": 1,
    "current_designation": 1, "designation": 1, "headline": 1,
    "current_employer": 1, "current_company": 1, "company": 1,
    "current_location": 1, "location": 1,
    "total_experience_years": 1, "experience_years": 1,
    "key_skills": 1, "skills": 1,
    "source": 1, "updated_at": 1, "created_at": 1,
}


def _coalesce(*values):
    for v in values:
        if v not in (None, "", [], {}):
            return v
    return None


def _category_color(score: float) -> str:
    if score >= 0.75:
        return "green"
    if score >= 0.40:
        return "yellow"
    return "red"


def _skill_chips(candidate: dict, job: dict):
    """Direct overlap computation for display chips (mirrors the fuzzy
    logic in evaluate_skills, but returns lists instead of prose)."""
    job_skills = [s.lower().strip() for s in (job.get("key_skills") or []) if s]
    cand_skills = [
        s.lower().strip()
        for s in (candidate.get("key_skills") or candidate.get("skills") or [])
        if s
    ]
    if not job_skills:
        return [], []
    matched, missing = [], []
    cand_set = set(cand_skills)
    for js in job_skills:
        if js in cand_set or any(js in cs or cs in js for cs in cand_set):
            matched.append(js)
        else:
            missing.append(js)
    return matched[:6], missing[:4]


def _score_fit(candidate: dict, job: dict) -> dict:
    """Run rule evaluators, collapse criteria into per-category scores and
    one weighted percentage. Categories with no signal are excluded and
    the remaining weights renormalized."""
    criteria = []
    criteria.extend(evaluate_skills(candidate, job))
    criteria.extend(evaluate_experience(candidate, job))
    criteria.extend(evaluate_salary(candidate, job))
    criteria.extend(evaluate_location(candidate, job))
    criteria.extend(evaluate_notice(candidate, job))

    by_cat: dict = {}
    for c in criteria:
        cat = c.get("category")
        if cat in _WEIGHTS:
            by_cat.setdefault(cat, []).append(_COLOR_SCORE.get(c.get("color"), 0.5))

    factors = {}
    weighted_sum = 0.0
    weight_total = 0.0
    for cat, scores in by_cat.items():
        cat_score = sum(scores) / len(scores)
        weighted_sum += cat_score * _WEIGHTS[cat]
        weight_total += _WEIGHTS[cat]
        first_line = next(
            (c["text"] for c in criteria if c.get("category") == cat), ""
        )
        factors[cat] = {
            "color": _category_color(cat_score),
            "label": first_line[:110],
        }

    score = round(100 * weighted_sum / weight_total) if weight_total else None
    matched, missing = _skill_chips(candidate, job)

    return {
        "score": score,
        "factors": factors,
        "matched_skills": matched,
        "missing_skills": missing,
        "criteria_count": len(criteria),
    }


@extension_preview_router.get("/candidate-preview/{candidate_id}")
async def candidate_preview(
    candidate_id: str,
    mandate_id: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    """Compact candidate snapshot + optional mandate fit for the badge
    hover card. Rule-based only — no AI call — so it stays fast."""
    candidate = await db.candidate_bank.find_one(
        {"id": candidate_id}, _CANDIDATE_PROJECTION
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    payload = {
        "id": candidate.get("id"),
        "name": candidate.get("name"),
        "designation": _coalesce(
            candidate.get("current_designation"),
            candidate.get("designation"),
            candidate.get("headline"),
        ),
        "employer": _coalesce(
            candidate.get("current_employer"),
            candidate.get("current_company"),
            candidate.get("company"),
        ),
        "location": _coalesce(
            candidate.get("current_location"), candidate.get("location")
        ),
        "phone": candidate.get("phone"),
        "email": candidate.get("email"),
        "current_salary": candidate.get("current_salary"),
        "expected_salary": candidate.get("expected_salary"),
        "notice_period": _coalesce(
            candidate.get("notice_period"),
            (
                f"{candidate.get('notice_period_days')} days"
                if candidate.get("notice_period_days") is not None
                else None
            ),
        ),
        "experience_years": _coalesce(
            candidate.get("total_experience_years"),
            candidate.get("experience_years"),
        ),
        "source": candidate.get("source"),
        "updated_at": _coalesce(
            candidate.get("updated_at"), candidate.get("created_at")
        ),
    }

    fit = None
    fit_error = None
    if mandate_id:
        job = await db.jobs.find_one({"id": mandate_id}, {"_id": 0})
        if not job:
            fit_error = "mandate_not_found"
        else:
            try:
                fit = _score_fit(candidate, job)
                fit["mandate_id"] = mandate_id
                fit["mandate_title"] = _coalesce(
                    job.get("title"), job.get("job_title"), "Selected mandate"
                )
                fit["mandate_code"] = job.get("job_code")
            except Exception as e:  # never let scoring break the preview
                logger.warning(
                    "[Preview] fit scoring failed for %s vs %s: %s",
                    candidate_id, mandate_id, e,
                )
                fit_error = "scoring_failed"

    # Contact details were served to an authenticated recruiter — leave a
    # trace without logging the PII itself.
    logger.info(
        "[Preview] %s viewed candidate %s (mandate=%s)",
        current_user.get("email", "?"), candidate_id, mandate_id or "-",
    )

    return {"success": True, "candidate": payload, "fit": fit, "fit_error": fit_error}
