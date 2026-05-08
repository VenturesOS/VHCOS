"""
Application business logic service.
Helpers for matching cache, PDF extraction, and career stability calculation.
"""
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def match_cache_key(match_req) -> str:
    """Generate a cache key from match request params."""
    key_data = json.dumps({
        "job_id": match_req.job_id,
        "jd_text": (match_req.jd_text or "")[:200],
        "mode": match_req.match_mode or "quick",
        "location": match_req.must_have_location,
        "skills": match_req.must_have_skills,
        "min_exp": match_req.min_experience,
        "max_exp": match_req.max_experience,
        "limit": match_req.limit,
    }, sort_keys=True)
    return hashlib.sha256(key_data.encode()).hexdigest()


def extract_text_from_pdf(file_path: Path) -> str:
    """Extract text from PDF file"""
    import fitz
    try:
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return ""


def calculate_career_stability(experience: List[dict]) -> Dict[str, Any]:
    """Calculate career stability score based on job history"""
    if not experience:
        return {"score": "yellow", "quick_changes": 0, "avg_tenure_months": 0}

    quick_changes = 0
    total_tenure = 0

    for job in experience:
        start = job.get("start_date")
        end = job.get("end_date", "present")

        tenure_months = 24

        if start:
            if isinstance(start, str) and "20" in start:
                try:
                    start_year = int(start.split("/")[-1] if "/" in start else start[:4])
                    if end == "present":
                        end_year = datetime.now().year
                    else:
                        end_year = int(end.split("/")[-1] if "/" in end else end[:4])
                    tenure_months = (end_year - start_year) * 12
                except (ValueError, IndexError, TypeError):
                    pass

        total_tenure += tenure_months
        if tenure_months < 12:
            quick_changes += 1

    avg_tenure = total_tenure / len(experience) if experience else 0

    if quick_changes == 0 and avg_tenure >= 24:
        score = "green"
    elif quick_changes <= 1 and avg_tenure >= 12:
        score = "yellow"
    else:
        score = "red"

    return {
        "score": score,
        "quick_changes": quick_changes,
        "avg_tenure_months": round(avg_tenure)
    }
