"""
Background Job Suggestions Service
Triggers on job creation — scores all active candidates against the new mandate
and stores top suggestions in `job_suggestions` collection.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List

logger = logging.getLogger(__name__)

MAX_SUGGESTIONS = 50  # Top N candidates to store per job


async def generate_job_suggestions(job_doc: Dict, db):
    """
    Score all active candidates against a job and store top matches.
    Runs as a background task after job creation/update.
    """
    from services.matching_engine import (
        calculate_fast_match_score,
        parse_job_requirements_fast,
    )

    job_id = job_doc["id"]
    start = time.time()
    logger.info(f"[JobSuggest] Starting suggestions for job {job_id}")

    try:
        # Mark suggestion generation as in-progress
        await db.job_suggestions.update_one(
            {"job_id": job_id},
            {"$set": {
                "job_id": job_id,
                "status": "processing",
                "started_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )

        # Parse job requirements (fast, no LLM)
        job_data = parse_job_requirements_fast(job_doc)

        # Fetch active candidates (limit to recent 2000 for speed)
        cursor = db.candidate_bank.find(
            {"is_active": {"$ne": False}},
            {
                "_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1,
                "skills": 1, "key_skills": 1, "experience_years": 1,
                "total_experience_years": 1, "current_salary": 1,
                "current_ctc": 1, "expected_salary": 1, "expected_ctc": 1,
                "notice_period": 1, "notice_period_days": 1,
                "current_designation": 1, "designation": 1,
                "current_employer": 1, "location": 1, "current_location": 1,
                "headline": 1, "profile_summary": 1, "summary": 1,
                "work_experience": 1, "experience": 1,
                "education": 1, "certifications": 1, "languages": 1,
                "industry": 1, "current_industry": 1,
                "embedding": 1, "source": 1, "created_by": 1,
            },
        ).sort("created_at", -1).limit(2000)

        candidates = await cursor.to_list(2000)
        logger.info(f"[JobSuggest] Scoring {len(candidates)} candidates for job {job_id}")

        # Score each candidate
        scored = []
        for cand in candidates:
            try:
                result = calculate_fast_match_score(
                    cand, job_data,
                    candidate_embedding=cand.get("embedding"),
                )
                if result["score"] >= 25:  # Only store meaningful matches
                    scored.append({
                        "candidate_id": cand["id"],
                        "name": cand.get("name", ""),
                        "email": cand.get("email", ""),
                        "phone": cand.get("phone", ""),
                        "designation": cand.get("current_designation") or cand.get("designation", ""),
                        "current_employer": cand.get("current_employer", ""),
                        "location": cand.get("location") or cand.get("current_location", ""),
                        "experience_years": cand.get("total_experience_years") or cand.get("experience_years"),
                        "current_salary": cand.get("current_salary") or cand.get("current_ctc"),
                        "notice_period": cand.get("notice_period", ""),
                        "skills": (cand.get("key_skills") or cand.get("skills") or [])[:15],
                        "education": (cand.get("education") or [])[:3],
                        "headline": cand.get("headline", ""),
                        "profile_summary": (cand.get("profile_summary") or cand.get("summary") or "")[:300],
                        "industry": cand.get("current_industry") or cand.get("industry", ""),
                        "work_experience": (cand.get("work_experience") or cand.get("experience") or [])[:5],
                        "score": result["score"],
                        "skill_match_score": result.get("skill_match_score", 0),
                        "experience_match_score": result.get("experience_match_score", 0),
                        "ctc_fit_score": result.get("ctc_fit_score", 0),
                        "location_fit_score": result.get("location_fit_score", 0),
                        "notice_fit_score": result.get("notice_fit_score", 0),
                        "stability_score": result.get("stability_score", 0),
                        "tfidf_score": result.get("tfidf_score", 0),
                        "matched_skills": result.get("matched_skills", []),
                        "partial_skills": result.get("partial_skills", []),
                        "missing_skills": result.get("missing_skills", []),
                        "explanation": result.get("explanation", ""),
                        "is_maybe": result.get("is_maybe", False),
                        "data_completeness": result.get("data_completeness", 100),
                        "missing_data_fields": result.get("missing_data_fields", []),
                    })
            except Exception as e:
                logger.warning(f"[JobSuggest] Error scoring {cand.get('id')}: {e}")

        # Sort by score descending, keep top N
        scored.sort(key=lambda x: x["score"], reverse=True)
        
        # Separate confirmed matches from maybes
        confirmed = [s for s in scored if not s.get("is_maybe")]
        maybes = [s for s in scored if s.get("is_maybe")]
        
        top_confirmed = confirmed[:MAX_SUGGESTIONS]
        top_maybes = maybes[:20]  # Keep top 20 maybe candidates

        elapsed = round(time.time() - start, 1)

        await db.job_suggestions.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "completed",
                "suggestions": top_confirmed,
                "maybe_candidates": top_maybes,
                "total_scored": len(candidates),
                "total_matched": len(confirmed),
                "total_maybes": len(maybes),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": elapsed,
            }},
        )

        logger.info(
            f"[JobSuggest] Done for job {job_id}: "
            f"{len(top_confirmed)} suggestions + {len(top_maybes)} maybes from {len(scored)} matches "
            f"(scored {len(candidates)} in {elapsed}s)"
        )

    except Exception as e:
        logger.error(f"[JobSuggest] Failed for job {job_id}: {e}")
        await db.job_suggestions.update_one(
            {"job_id": job_id},
            {"$set": {"status": "failed", "error": str(e)}},
        )
