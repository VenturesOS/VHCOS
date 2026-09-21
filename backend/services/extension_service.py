"""
Extension business logic service.
Evaluation helpers, profile building, capture logging, and team visibility.
"""
import re
import uuid
import logging
import json as json_module
from datetime import datetime, timezone
from typing import Optional

from config import db
from models.extension import CompleteNaukriProfileInput
from services.identity_capture import normalized_phone as normalized_capture_phone

logger = logging.getLogger(__name__)


# ── Safe list converters (handle both Pydantic models and raw dicts/strings) ──

def _safe_list(items):
    """Convert list of Pydantic models or dicts to list of dicts."""
    if not items or not isinstance(items, list):
        return []
    result = []
    for item in items:
        if hasattr(item, 'model_dump'):
            result.append(item.model_dump())
        elif isinstance(item, dict):
            result.append(item)
        elif isinstance(item, str):
            result.append({"name": item})
    return result

def _safe_list_str(items):
    """Convert to list of strings, strip pipe chars and deduplicate."""
    if not items or not isinstance(items, list):
        return []
    seen = set()
    result = []
    for i in items:
        if not i:
            continue
        s = str(i).strip().rstrip('|').strip()
        if not s:
            continue
        s_lower = s.lower()
        if s_lower not in seen:
            seen.add(s_lower)
            result.append(s)
    return result

def _safe_cert_names(items):
    """Extract certification names."""
    if not items or not isinstance(items, list):
        return []
    result = []
    for item in items:
        if hasattr(item, 'name'):
            result.append(item.name)
        elif isinstance(item, dict):
            result.append(item.get('name', str(item)))
        elif isinstance(item, str):
            result.append(item)
    return result


# ── Phone / Name Utilities ──

def normalize_phone(phone: str) -> Optional[str]:
    """Normalize phone number for comparison"""
    if not phone:
        return None
    digits = ''.join(filter(str.isdigit, phone))
    if digits.startswith('91') and len(digits) > 10:
        digits = digits[2:]
    return digits[-10:] if len(digits) >= 10 else digits


def _names_are_similar(name_a: str, name_b: str) -> bool:
    """
    Check if two names likely refer to the same person.

    Accepts a match if ANY of:
      - First significant words are identical (e.g. "Rajat Gupta" == "Rajat G.")
      - At least one significant token (len ≥ 3) overlaps between both names
        (handles reversed token order: "G Rajat" vs "Rajat Gupta")
      - difflib SequenceMatcher ratio ≥ 0.70 on normalised strings
        (handles minor typos: "Rajut Gupta" vs "Rajat Gupta")

    Tightened with these heuristics in Feb-2026 (Phase 55.1) because the
    previous strict first-token rule was the root cause of the
    duplicate-records pileup visible in the Dedup tab — captures with
    matching email but slightly-different name spellings were creating
    new records instead of merging.
    """
    if not name_a or not name_b:
        return False
    import re as _re_n
    from difflib import SequenceMatcher as _SM

    # Strip common honorifics + punctuation, lowercase
    def _clean(s: str) -> str:
        s = _re_n.sub(r'\b(mr|mrs|ms|dr|prof|shri|smt)\.?\b', ' ', s.lower())
        s = _re_n.sub(r'[^a-z0-9\s]', ' ', s)
        return _re_n.sub(r'\s+', ' ', s).strip()

    a_clean = _clean(name_a)
    b_clean = _clean(name_b)
    if not a_clean or not b_clean:
        return False

    # FIX (Phase 56.1, Feb 2026) — Naukri occasionally renders names with
    # whitespace between every letter (e.g. "A J I T H" instead of "AJITH").
    # The naive token filter below strips all the 1-char tokens, leaving an
    # empty list and a false-negative match. When >=50% of the cleaned
    # tokens are single characters, try comparing the de-spaced form too.
    def _despace_if_letter_split(s: str) -> str:
        toks = s.split()
        if len(toks) >= 3 and sum(1 for t in toks if len(t) == 1) / len(toks) >= 0.5:
            return "".join(toks)
        return s
    a_despaced = _despace_if_letter_split(a_clean)
    b_despaced = _despace_if_letter_split(b_clean)

    words_a = [w for w in a_clean.split() if len(w) > 1]
    words_b = [w for w in b_clean.split() if len(w) > 1]
    # Fall back to the de-spaced form when token filter empties one side
    if not words_a and a_despaced:
        words_a = [a_despaced]
    if not words_b and b_despaced:
        words_b = [b_despaced]
    if not words_a or not words_b:
        return False

    # Rule 1 — first significant word match (cheap, common case)
    if words_a[0] == words_b[0]:
        return True

    # Rule 2 — any 3+-char token shared (handles reversed order)
    tokens_a = {w for w in words_a if len(w) >= 3}
    tokens_b = {w for w in words_b if len(w) >= 3}
    if tokens_a & tokens_b:
        return True

    # Rule 3 — fuzzy ratio for typos / transliteration drift
    if _SM(None, a_clean, b_clean).ratio() >= 0.70:
        return True
    # Rule 3b — same fuzzy ratio against de-spaced forms (catches
    # "A J I T H" → "ajith" against "Ajith Kumar" → "ajithkumar")
    if a_despaced != a_clean or b_despaced != b_clean:
        if _SM(None, a_despaced, b_despaced).ratio() >= 0.70:
            return True

    return False


# ── Salary / Notice Parsing ──

def _parse_notice_days(notice_str: str) -> int | None:
    """Parse notice period text to approximate days."""
    notice_str = notice_str.lower().strip()
    if "immediate" in notice_str:
        return 0
    m = re.search(r'(\d+)\s*day', notice_str)
    if m:
        return int(m.group(1))
    m = re.search(r'(\d+)\s*month', notice_str)
    if m:
        return int(m.group(1)) * 30
    m = re.search(r'(\d+)\s*week', notice_str)
    if m:
        return int(m.group(1)) * 7
    return None


def _parse_salary_number(val) -> float | None:
    """Parse salary to a numeric value (in INR)."""
    if not val:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        pass
    s = str(val).lower().replace(",", "").strip()
    m = re.search(r'([\d.]+)\s*(cr|crore)', s)
    if m:
        return float(m.group(1)) * 10000000
    m = re.search(r'([\d.]+)\s*(l|lac|lakh|lpa)', s)
    if m:
        return float(m.group(1)) * 100000
    m = re.search(r'([\d.]+)\s*(k)', s)
    if m:
        return float(m.group(1)) * 1000
    m = re.match(r'([\d.]+)', s)
    if m:
        v = float(m.group(1))
        if v > 100:
            return v
    return None


def _parse_salary_range(text: str) -> tuple:
    """Parse salary range text like '10-15 LPA' into (min, max) numbers."""
    if not text:
        return (None, None)
    s = text.lower().replace(",", "").strip()

    m = re.search(r'([\d.]+)\s*[-–to]+\s*([\d.]+)\s*(cr|crore|l|lac|lakh|lpa|k)?', s)
    if m:
        v1, v2 = float(m.group(1)), float(m.group(2))
        unit = m.group(3) or ""
        mult = 1
        if "cr" in unit:
            mult = 10000000
        elif unit in ("l", "lac", "lakh", "lpa"):
            mult = 100000
        elif "k" in unit:
            mult = 1000
        return (v1 * mult, v2 * mult)

    m = re.search(r'([\d.]+)\s*(cr|crore|l|lac|lakh|lpa|k)?', s)
    if m:
        v = float(m.group(1))
        unit = m.group(2) or ""
        mult = 1
        if "cr" in unit:
            mult = 10000000
        elif unit in ("l", "lac", "lakh", "lpa"):
            mult = 100000
        elif "k" in unit:
            mult = 1000
        return (None, v * mult)

    return (None, None)


def _format_salary(val) -> str:
    if not val:
        return "N/A"
    try:
        v = float(val)
        if v >= 10000000:
            return f"{v/10000000:.1f} Cr"
        if v >= 100000:
            return f"{v/100000:.1f}L"
        return str(val)
    except (ValueError, TypeError):
        return str(val)


# ── Evaluation Helpers ──

def evaluate_skills(candidate: dict, job: dict) -> list:
    """Match candidate skills against job requirements using fuzzy matching."""
    job_skills = [s.lower().strip() for s in (job.get("key_skills") or []) if s]
    if not job_skills:
        return []

    cand_skills = [s.lower().strip() for s in (candidate.get("key_skills") or candidate.get("skills") or []) if s]
    if not cand_skills:
        return [{"text": f"No skills data — job requires: {', '.join(job_skills[:6])}", "color": "red", "category": "skills"}]

    job_skills_set = set(job_skills)
    cand_skills_set = set(cand_skills)
    results = []

    exact_matched = job_skills_set & cand_skills_set

    fuzzy_matched = set()
    for js in (job_skills_set - exact_matched):
        for cs in cand_skills_set:
            if js in cs or cs in js:
                fuzzy_matched.add(js)
                break

    all_matched = exact_matched | fuzzy_matched
    missing = job_skills_set - all_matched

    if all_matched:
        results.append({"text": f"Skills match ({len(all_matched)}/{len(job_skills_set)}): {', '.join(sorted(all_matched)[:8])}", "color": "green", "category": "skills"})
    if missing:
        ratio = len(missing) / len(job_skills_set)
        if ratio <= 0.3:
            results.append({"text": f"Minor skill gaps: {', '.join(sorted(missing)[:4])}", "color": "yellow", "category": "skills"})
        else:
            results.append({"text": f"Missing key skills ({len(missing)}/{len(job_skills_set)}): {', '.join(sorted(missing)[:6])}", "color": "red", "category": "skills"})

    return results


def evaluate_experience(candidate: dict, job: dict) -> list:
    """Check experience years against job requirements."""
    cand_exp = candidate.get("total_experience_years") or candidate.get("experience_years")
    min_exp = job.get("min_experience")
    max_exp = job.get("max_experience")

    if cand_exp is None and (min_exp is not None or max_exp is not None):
        return [{"text": f"Experience data missing — job needs {min_exp or '?'}-{max_exp or '?'} yrs", "color": "yellow", "category": "experience"}]

    if cand_exp is None:
        return []

    try:
        cand_exp = float(cand_exp)
    except (ValueError, TypeError):
        return []

    if min_exp is not None and max_exp is not None:
        try:
            min_exp, max_exp = float(min_exp), float(max_exp)
        except (ValueError, TypeError):
            return []
        if min_exp <= cand_exp <= max_exp:
            return [{"text": f"Experience {cand_exp:.0f} yrs — within {min_exp:.0f}-{max_exp:.0f} yr range", "color": "green", "category": "experience"}]
        elif cand_exp < min_exp:
            gap = min_exp - cand_exp
            color = "yellow" if gap <= 2 else "red"
            return [{"text": f"Experience {cand_exp:.0f} yrs — needs {min_exp:.0f}+ yrs ({gap:.0f} yr gap)", "color": color, "category": "experience"}]
        else:
            over = cand_exp - max_exp
            color = "yellow" if over <= 3 else "red"
            return [{"text": f"Experience {cand_exp:.0f} yrs — overqualified (max {max_exp:.0f} yrs, {over:.0f} yr over)", "color": color, "category": "experience"}]

    exp_req = job.get("experience_required", "")
    if exp_req:
        return [{"text": f"Experience: {cand_exp:.0f} yrs (requirement: {exp_req})", "color": "yellow", "category": "experience"}]

    return []


def evaluate_salary(candidate: dict, job: dict) -> list:
    """Compare salary expectations with actual number comparison."""
    prefs = candidate.get("career_preferences") or {}
    current = _parse_salary_number(prefs.get("current_salary") or candidate.get("current_salary"))
    expected = _parse_salary_number(prefs.get("expected_salary") or candidate.get("expected_salary"))

    salary_range = job.get("salary_range", "")
    if not salary_range:
        return []

    if not current and not expected:
        return [{"text": f"Salary data missing — budget: {salary_range}", "color": "yellow", "category": "salary"}]

    job_min, job_max = _parse_salary_range(salary_range)

    compare_val = expected or current
    if compare_val and job_max:
        if compare_val <= job_max * 1.1:
            return [{"text": f"Salary fit: {_format_salary(compare_val)} expected — budget {salary_range}", "color": "green", "category": "salary"}]
        elif compare_val <= job_max * 1.3:
            return [{"text": f"Salary stretch: {_format_salary(compare_val)} expected — budget {salary_range}", "color": "yellow", "category": "salary"}]
        else:
            return [{"text": f"Salary mismatch: {_format_salary(compare_val)} expected — budget {salary_range}", "color": "red", "category": "salary"}]

    parts = []
    if current:
        parts.append(f"Current: {_format_salary(current)}")
    if expected:
        parts.append(f"Expected: {_format_salary(expected)}")
    return [{"text": f"{', '.join(parts)} — Budget: {salary_range}", "color": "yellow", "category": "salary"}]


def evaluate_location(candidate: dict, job: dict) -> list:
    """Check location compatibility — stricter matching."""
    job_loc = (job.get("location") or "").lower().strip()
    if not job_loc or job_loc in ("remote", "work from home", "wfh", "anywhere"):
        return []

    prefs = candidate.get("career_preferences") or {}
    cand_loc = (prefs.get("current_location") or candidate.get("location") or "").lower().strip()
    preferred_locs = [loc.lower().strip() for loc in (prefs.get("preferred_locations") or []) if loc]
    willing_to_relocate = prefs.get("willing_to_relocate", False)

    if not cand_loc:
        return [{"text": f"Location unknown — role is in {job.get('location')}", "color": "yellow", "category": "location"}]

    city_aliases = {
        "bengaluru": "bangalore", "mumbai": "bombay", "kolkata": "calcutta",
        "chennai": "madras", "gurgaon": "gurugram", "ncr": "delhi",
        "new delhi": "delhi", "noida": "delhi", "greater noida": "delhi",
    }
    norm_job = city_aliases.get(job_loc, job_loc)
    norm_cand = city_aliases.get(cand_loc, cand_loc)

    if norm_cand == norm_job or norm_cand in norm_job or norm_job in norm_cand:
        return [{"text": f"Location match: {cand_loc.title()}", "color": "green", "category": "location"}]

    for ploc in preferred_locs:
        norm_ploc = city_aliases.get(ploc, ploc)
        if norm_ploc == norm_job or norm_ploc in norm_job or norm_job in norm_ploc:
            return [{"text": f"Preferred location match: {ploc.title()} (current: {cand_loc.title()})", "color": "green", "category": "location"}]

    if willing_to_relocate:
        return [{"text": f"Location mismatch: {cand_loc.title()} vs {job.get('location')} — but willing to relocate", "color": "yellow", "category": "location"}]

    return [{"text": f"Location mismatch: {cand_loc.title()} — role is in {job.get('location')}", "color": "red", "category": "location"}]


def evaluate_notice(candidate: dict, job: dict) -> list:
    """Check notice period — with proper red for long notice."""
    prefs = candidate.get("career_preferences") or {}
    notice = prefs.get("notice_period") or candidate.get("notice_period")
    notice_days = prefs.get("notice_period_days")
    is_serving = prefs.get("is_serving_notice", False)

    if not notice and notice_days is None:
        return []

    days = notice_days
    if days is None and notice:
        days = _parse_notice_days(str(notice))

    if is_serving:
        lwd = prefs.get("last_working_day", "")
        return [{"text": f"Currently serving notice — LWD: {lwd or 'not specified'}", "color": "green", "category": "notice"}]

    if days is not None:
        if days <= 15:
            return [{"text": f"Notice period: {notice or f'{days} days'} — can join quickly", "color": "green", "category": "notice"}]
        elif days <= 30:
            return [{"text": f"Notice period: {notice or f'{days} days'} — short notice", "color": "green", "category": "notice"}]
        elif days <= 60:
            return [{"text": f"Notice period: {notice or f'{days} days'} — moderate wait", "color": "yellow", "category": "notice"}]
        elif days <= 90:
            return [{"text": f"Notice period: {notice or f'{days} days'} — long notice (3 months)", "color": "yellow", "category": "notice"}]
        else:
            return [{"text": f"Notice period: {notice or f'{days} days'} — very long notice", "color": "red", "category": "notice"}]

    notice_str = str(notice).lower()
    if "immediate" in notice_str or notice_str.strip() == "0":
        return [{"text": "Notice period: Immediate — can join quickly", "color": "green", "category": "notice"}]
    elif any(x in notice_str for x in ["15 day", "1 month", "30 day"]):
        return [{"text": f"Notice period: {notice} — short notice", "color": "green", "category": "notice"}]
    elif any(x in notice_str for x in ["2 month", "60 day"]):
        return [{"text": f"Notice period: {notice} — moderate wait", "color": "yellow", "category": "notice"}]
    elif any(x in notice_str for x in ["3 month", "90 day"]):
        return [{"text": f"Notice period: {notice} — long notice", "color": "yellow", "category": "notice"}]
    else:
        return [{"text": f"Notice period: {notice}", "color": "yellow", "category": "notice"}]


def evaluate_data_completeness(candidate: dict) -> list:
    """Flag critical missing data that limits evaluation quality."""
    missing = []
    if not candidate.get("key_skills") and not candidate.get("skills"):
        missing.append("skills")
    if not candidate.get("total_experience_years") and not candidate.get("experience_years"):
        missing.append("experience")
    if not candidate.get("current_company") and not candidate.get("current_designation"):
        missing.append("current role")
    if not (candidate.get("work_experience") or []):
        missing.append("work history")

    if len(missing) >= 3:
        return [{"text": f"Limited profile data (missing: {', '.join(missing)}) — evaluation may be inaccurate", "color": "red", "category": "data_quality"}]
    elif missing:
        return [{"text": f"Some profile data missing: {', '.join(missing)}", "color": "yellow", "category": "data_quality"}]
    return []


async def ai_comprehensive_evaluation(candidate: dict, job: dict, has_structured_data: bool) -> list:
    """Use LLM for comprehensive candidate evaluation."""
    return []  # AI evaluation disabled to save tokens (saves $0.83-$1.63/month, 1.2M tokens)
    from services.llm_service import chat_completion

    cand_summary = {
        "name": candidate.get("name"),
        "skills": (candidate.get("key_skills") or candidate.get("skills") or [])[:20],
        "experience_years": candidate.get("total_experience_years") or candidate.get("experience_years"),
        "current_company": candidate.get("current_company"),
        "current_designation": candidate.get("current_designation"),
        "current_department": candidate.get("current_department"),
        "current_industry": candidate.get("current_industry"),
        "headline": candidate.get("headline") or candidate.get("resume_headline"),
        "profile_summary": (candidate.get("profile_summary") or "")[:600],
        "highest_qualification": candidate.get("highest_qualification"),
        "work_experience": [
            {
                "company": w.get("company"),
                "role": w.get("designation"),
                "duration": w.get("duration"),
                "description": (w.get("description") or "")[:200],
                "industry": w.get("industry"),
            }
            for w in (candidate.get("work_experience") or [])[:5]
        ],
        "education": [
            {"degree": e.get("degree"), "institution": e.get("institution"), "specialization": e.get("specialization")}
            for e in (candidate.get("education") or [])[:3]
        ],
        "career_preferences": {
            "current_salary": candidate.get("career_preferences", {}).get("current_salary") or candidate.get("current_salary"),
            "expected_salary": candidate.get("career_preferences", {}).get("expected_salary") or candidate.get("expected_salary"),
            "current_location": candidate.get("career_preferences", {}).get("current_location") or candidate.get("location"),
            "notice_period": candidate.get("career_preferences", {}).get("notice_period") or candidate.get("notice_period"),
        },
    }

    job_summary = {
        "title": job.get("title"),
        "company": job.get("company_name"),
        "location": job.get("location"),
        "description": (job.get("description") or "")[:1500],
        "requirements": (job.get("requirements") or "")[:1500],
        "key_skills": (job.get("key_skills") or [])[:15],
        "salary_range": job.get("salary_range"),
        "experience_range": f"{job.get('min_experience', '?')}-{job.get('max_experience', '?')} yrs" if job.get("min_experience") else None,
    }

    structured_note = ""
    if has_structured_data:
        structured_note = """Note: Skills match, experience range, and salary have ALREADY been checked by rule-based logic.
Focus your analysis on: domain/industry relevance, role seniority fit, career trajectory, education fit, and red flags.
Do NOT duplicate the skills/experience/salary checks."""
    else:
        structured_note = """IMPORTANT: This job has NO structured skill/experience/salary fields — only free-text description and requirements.
You MUST extract and evaluate ALL of the following from the description text:
1. Required skills vs candidate's skills — are they a match?
2. Required experience level vs candidate's experience
3. Domain/industry relevance — is the candidate from the right industry?
4. Role seniority fit — is the candidate too junior, right level, or too senior?
5. Education/qualification requirements if mentioned
6. Salary expectations vs budget if mentioned in the description
7. Any critical red flags or concerns

Be STRICT and HONEST. If there's a mismatch, mark it RED. If uncertain, mark YELLOW. Only mark GREEN if there's clear evidence of a match.
Do NOT default to green — a recruiter's time is wasted on false positives."""

    prompt = f"""You are an expert recruitment consultant evaluating a candidate against a job opening.

{structured_note}

Return a JSON array of 5-8 evaluation criteria. Each item MUST have:
- "text": One clear sentence about the match/mismatch
- "color": "green" (clear match), "yellow" (partial/uncertain), or "red" (mismatch/concern)
- "category": One of "skills", "experience", "domain", "seniority", "education", "salary", "industry", "red_flag"

RULES:
- You MUST use all three colors (green, yellow, red). A candidate cannot match everything — find real concerns.
- If the candidate has limited data (no skills, no work history), that itself is a RED flag.
- If the candidate's industry/domain is completely different from the job, that is RED.
- Be specific — mention actual skill names, company names, years of experience.
- Never say "good match" without evidence.

CANDIDATE:
{json_module.dumps(cand_summary, default=str)}

JOB:
{json_module.dumps(job_summary, default=str)}

Return ONLY a valid JSON array."""

    try:
        content = await chat_completion(
            system_prompt="You are a strict recruitment evaluator. Be honest and critical. Use all three colors (green/yellow/red). Return only valid JSON array.",
            user_prompt=prompt,
            temperature=0.2,
            json_mode=True,
            timeout=60.0,
        )
        
        # Handle empty or error responses
        if not content or not content.strip():
            logger.warning("[Evaluate-Fit] Empty response from LLM")
            return []
        
        import json as _json
        
        try:
            parsed = _json.loads(content)
        except _json.JSONDecodeError as e:
            logger.warning(f"[Evaluate-Fit] JSON decode error: {e}")
            logger.warning(f"[Evaluate-Fit] Raw response (first 500 chars): {content[:500]}")
            
            # Likely an error message from LLM provider (rate limit, etc.)
            if "rate" in content.lower() or "limit" in content.lower() or "error" in content.lower():
                logger.error(f"[Evaluate-Fit] LLM provider error detected: {content[:200]}")
            
            return []
        
        if isinstance(parsed, dict):
            parsed = parsed.get("criteria") or parsed.get("evaluation") or parsed.get("results") or []
        if isinstance(parsed, list):
            valid = []
            for item in parsed:
                if isinstance(item, dict) and "text" in item and "color" in item:
                    if item["color"] not in ("green", "yellow", "red"):
                        item["color"] = "yellow"
                    item["category"] = item.get("category", "ai_analysis")
                    valid.append(item)
            return valid[:8]
    except Exception as e:
        logger.warning(f"[Evaluate-Fit] Unexpected error: {type(e).__name__}: {e}")

    return []


# ── Capture Logging ──

async def log_capture(profile, user, status, action, candidate_id, failure_reason=None, failed_step=None, capture_start=None):
    """Log every capture attempt to naukri_capture_logs for monitoring."""
    import time as _time
    now = datetime.now(timezone.utc).isoformat()
    duration_ms = round((_time.time() - capture_start) * 1000) if capture_start else 0

    missing = []
    if not getattr(profile, 'email', None):
        missing.append('email')
    if not getattr(profile, 'phone', None):
        missing.append('phone')
    if not getattr(profile, 'current_company', None):
        missing.append('current_company')
    if not getattr(profile, 'current_designation', None):
        missing.append('current_designation')
    if not getattr(profile, 'total_experience_years', None):
        missing.append('experience')

    doc = {
        "id": str(uuid.uuid4()),
        "timestamp": now,
        "profile_id": getattr(profile, 'naukri_profile_id', None) or '',
        "profile_url": getattr(profile, 'naukri_profile_url', None) or '',
        "candidate_name": getattr(profile, 'name', None) or '',
        "candidate_email": getattr(profile, 'email', None) or '',
        "candidate_phone": getattr(profile, 'phone', None) or '',
        "status": status,
        "action": action,
        "candidate_id": candidate_id or '',
        "failure_reason": failure_reason,
        "failed_step": failed_step,
        "data_missing_fields": missing,
        "captured_to_bank": status == "success" and bool(candidate_id),
        "is_recovered": False,
        "retry_count": 0,
        "capture_duration_ms": duration_ms,
        "source": "naukri_extension",
        "captured_by": user.get("id", "") if user else "",
        "captured_by_name": user.get("name", "") if user else "",
    }
    try:
        from utils.db_retry import retry_write
        await retry_write(db.naukri_capture_logs.insert_one, doc)
    except Exception as e:
        logger.error(f"[CaptureLog] Failed to log: {e}")


# ── Team Visibility ──

async def build_team_visibility(user: dict) -> dict:
    """Build visibility fields so captured candidates are visible to all team members."""
    user_id = user["id"]
    user_role = user.get("role", "")

    employer_ids = []
    recruiter_ids = []

    if user_role == "employer":
        employer_ids.append(user_id)
        team = await db.teams.find_one({"employer_id": user_id, "status": "active"}, {"_id": 0})
        if team:
            recruiter_ids = team.get("recruiter_ids", [])
    elif user_role == "recruiter":
        recruiter_ids.append(user_id)
        team = await db.teams.find_one({"recruiter_ids": user_id, "status": "active"}, {"_id": 0})
        if team:
            employer_ids.append(team.get("employer_id", ""))
            for rid in team.get("recruiter_ids", []):
                if rid not in recruiter_ids:
                    recruiter_ids.append(rid)
    elif user_role == "admin":
        employer_ids.append(user_id)
        async for team in db.teams.find({"status": "active"}, {"_id": 0, "employer_id": 1, "recruiter_ids": 1}):
            if team.get("employer_id"):
                employer_ids.append(team["employer_id"])
            recruiter_ids.extend(team.get("recruiter_ids", []))

    if not employer_ids and not recruiter_ids:
        return {}

    return {
        "visibility": {
            "employer_ids": list(set(employer_ids)),
            "recruiter_ids": list(set(recruiter_ids)),
        }
    }


# ── Profile Building ──

def build_complete_candidate(profile: CompleteNaukriProfileInput, candidate_id: str, user: dict, now: str) -> dict:
    """Build complete candidate document with ALL Naukri data"""

    career_prefs = profile.career_preferences.model_dump() if profile.career_preferences else {}
    personal = profile.personal_details.model_dump() if profile.personal_details else {}

    doc = {
        "id": candidate_id,
        "name": profile.name,
        "name_lower": (profile.name or "").strip().lower(),
        "first_name": profile.first_name,
        "middle_name": profile.middle_name,
        "last_name": profile.last_name,
        "photo_url": profile.photo_url,
        "email": profile.email.lower() if profile.email else None,
        "alternate_email": profile.alternate_email,
        "phone": profile.phone,
        "phone_normalized": normalized_capture_phone(profile.phone),
        "alternate_phone": profile.alternate_phone,
        "headline": profile.headline,
        "resume_headline": profile.resume_headline,
        "summary": profile.profile_summary,
        "current_employer": profile.current_company,
        "designation": profile.current_designation,
        "department": profile.current_department,
        "industry": profile.current_industry,
        "role_category": profile.current_role_category,
        "employment_status": profile.employment_status,
        "experience_years": float(profile.total_experience_years) if profile.total_experience_years else 0,
        "experience_months": profile.total_experience_months,
        "experience_display": profile.total_experience_display,
        "experience": _safe_list(profile.work_experience),
        "highest_qualification": profile.highest_qualification,
        "highest_degree": profile.highest_degree,
        "education": _safe_list(profile.education),
        "skills": _safe_list_str(profile.key_skills),
        "skills_display": profile.key_skills_display,
        "it_skills": _safe_list(profile.it_skills),
        "soft_skills": _safe_list_str(profile.soft_skills),
        "tools": _safe_list_str(profile.tools),
        "certifications": _safe_cert_names(profile.certifications),
        "certifications_detailed": _safe_list(profile.certifications),
        "projects": _safe_list(profile.projects),
        "languages": _safe_list(profile.languages),
        "online_profiles": _safe_list(profile.online_profiles),
        "linkedin_url": profile.linkedin_url,
        "github_url": profile.github_url,
        "portfolio_url": profile.portfolio_url,
        "date_of_birth": personal.get("date_of_birth"),
        "age": personal.get("age"),
        "gender": personal.get("gender"),
        "marital_status": personal.get("marital_status"),
        "nationality": personal.get("nationality"),
        "has_passport": personal.get("has_passport", False),
        "passport_number": personal.get("passport_number"),
        "passport_expiry": personal.get("passport_expiry"),
        "permanent_address": personal.get("permanent_address"),
        "permanent_city": personal.get("permanent_city"),
        "permanent_state": personal.get("permanent_state"),
        "permanent_country": personal.get("permanent_country"),
        "permanent_pincode": personal.get("permanent_pincode"),
        "current_address": personal.get("current_address"),
        "current_city": personal.get("current_city"),
        "current_state": personal.get("current_state"),
        "current_country": personal.get("current_country"),
        "current_pincode": personal.get("current_pincode"),
        "category": personal.get("category"),
        "differently_abled": personal.get("differently_abled", False),
        "disability_type": personal.get("disability_type"),
        "work_permit_usa": personal.get("work_permit_usa"),
        "work_permit_other": personal.get("work_permit_other"),
        "current_salary": career_prefs.get("current_salary"),
        "current_salary_currency": career_prefs.get("current_salary_currency", "INR"),
        "current_salary_breakdown": career_prefs.get("current_salary_breakdown"),
        "expected_salary": career_prefs.get("expected_salary"),
        "expected_salary_currency": career_prefs.get("expected_salary_currency", "INR"),
        "expected_salary_min": career_prefs.get("expected_salary_min"),
        "expected_salary_max": career_prefs.get("expected_salary_max"),
        "notice_period": career_prefs.get("notice_period"),
        "notice_period_days": career_prefs.get("notice_period_days"),
        "is_serving_notice": career_prefs.get("is_serving_notice", False),
        "last_working_day": career_prefs.get("last_working_day"),
        "notice_negotiable": career_prefs.get("is_negotiable", False),
        "location": career_prefs.get("current_location"),
        "preferred_locations": career_prefs.get("preferred_locations", []),
        "willing_to_relocate": career_prefs.get("willing_to_relocate", False),
        "relocation_preferences": career_prefs.get("relocation_preferences", []),
        "preferred_job_type": career_prefs.get("preferred_job_type", []),
        "preferred_employment_type": career_prefs.get("preferred_employment_type", []),
        "preferred_shift": career_prefs.get("preferred_shift", []),
        "work_from_home": career_prefs.get("work_from_home", False),
        "remote_work_preference": career_prefs.get("remote_work_preference"),
        "preferred_industry": career_prefs.get("preferred_industry", []),
        "preferred_functional_area": career_prefs.get("preferred_functional_area", []),
        "preferred_role": career_prefs.get("preferred_role", []),
        "preferred_role_category": career_prefs.get("preferred_role_category", []),
        "preferred_company_type": career_prefs.get("preferred_company_type", []),
        "preferred_company_size": career_prefs.get("preferred_company_size"),
        "companies_to_avoid": career_prefs.get("companies_to_avoid", []),
        "accomplishments": profile.accomplishments,
        "about_me": profile.about_me,
        "additional_info": profile.additional_info,
        "has_resume": profile.has_resume,
        "resume_title": profile.resume_title,
        "resume_format": profile.resume_format,
        "naukri_profile_id": profile.naukri_profile_id,
        "naukri_profile_url": profile.naukri_profile_url,
        "naukri_resume_id": profile.naukri_resume_id,
        "naukri_profile_created": profile.profile_created_on,
        "naukri_profile_updated": profile.profile_last_updated,
        "naukri_last_active": profile.last_active,
        "naukri_response_rate": profile.response_rate,
        "raw_profile_text": profile.raw_profile_text,
        "raw_sections": profile.raw_sections,
        "source": f"{profile.source_platform or 'naukri'}_extension",
        "source_platform": profile.source_platform or "naukri",
        "source_details": {
            "captured_by": user["id"],
            "captured_by_name": user.get("name", user.get("email")),
            "captured_by_role": user.get("role"),
            "captured_at": profile.scraped_at,
            "extension_version": profile.extension_version or "unknown",
            "contact_hidden": profile.contact_hidden or False,
            "mandate_id": profile.mandate_id,
        },
        "mandate_id": profile.mandate_id,
        "linked_mandates": [profile.mandate_id] if profile.mandate_id else [],
        "created_at": now,
        "updated_at": now,
        "created_by": user["id"],
        "last_updated_by": user["id"],
        "resume_versions": [],
        "resume_fingerprints": [],
        "match_cache": [],
        "application_history": [],
        "profile_update_audit": [],
        "notes": [],
        "cv_attached": profile.has_resume,
        "manually_edited": False,
        "bulk_import_type": None,
        "bulk_import_restricted": False,
    }
    observation = _capture_source_observation(profile, now)
    if observation:
        doc["source_details"]["identity_observation"] = observation
    return doc


def _should_overwrite(value) -> bool:
    """Decide whether to include a captured field in an UPDATE.

    Rule:
      - None  -> skip (preserve existing DB value)
      - empty string (after .strip()) -> skip (e.g. when "View Contact"
        wasn't pressed, the extension sends phone="" — without this guard
        we silently wipe the previously-saved phone number on recapture)
      - empty list/dict -> skip (extension sent no items in this section)
      - everything else (incl. False, 0, 0.0) -> overwrite

    Preserves False booleans and 0 numerics which CAN be valid captured
    values (e.g. has_resume=False, experience_months=0).
    """
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, (list, dict)) and len(value) == 0:
        return False
    return True


def _capture_source_observation(profile: CompleteNaukriProfileInput, observed_at: str) -> Optional[dict]:
    """Record where an identifier was observed without claiming verification.

    The capture adapter currently mixes profile IDs with pid/sid and URL hashes.
    Successful persistence validates none of those identifier semantics. Keep
    this observation for diagnosis; it must never create a trusted anchor.
    """
    source = str(getattr(profile, "source_platform", None) or "naukri").lower()
    source = "naukri" if source.startswith("naukri") else source
    identifier = getattr(profile, "naukri_profile_id", None)
    if source != "naukri" or not isinstance(identifier, str):
        return None
    identifier = identifier.strip()
    if not identifier or len(identifier) > 256 or not re.fullmatch(r"[A-Za-z0-9_.-]+", identifier):
        return None
    return {
        "source": "naukri", "id": identifier,
        "kind": "unverified_identifier", "provenance": "capture_observed",
        "observed_at": observed_at,
    }


def build_complete_update(profile: CompleteNaukriProfileInput, user: dict, now: str, existing: Optional[dict] = None) -> dict:
    """Build captured changes while preserving omitted values and provenance.

    Pydantic defaults are not observations: an omitted ``has_resume`` or
    ``is_negotiable`` must not erase a previously captured True value.
    Explicit False/zero values remain meaningful updates.
    """

    supplied = profile.model_fields_set
    career_prefs = profile.career_preferences.model_dump(exclude_unset=True) if profile.career_preferences else {}
    personal = profile.personal_details.model_dump(exclude_unset=True) if profile.personal_details else {}
    old_details = (existing or {}).get("source_details")
    source_details = dict(old_details) if isinstance(old_details, dict) else {}
    source_details.update({
        "captured_by": user["id"],
        "captured_by_name": user.get("name", user.get("email")),
        "captured_by_role": user.get("role"),
        "captured_at": profile.scraped_at,
    })
    for field in ("extension_version", "contact_hidden", "mandate_id"):
        value = getattr(profile, field)
        if field in supplied and _should_overwrite(value):
            source_details[field] = value
    observation = _capture_source_observation(profile, now)
    if observation:
        source_details["identity_observation"] = observation

    update = {
        "updated_at": now,
        "last_updated_by": user["id"],
        "source_details": source_details,
    }
    if "source_platform" in supplied and _should_overwrite(profile.source_platform):
        update["source"] = f"{profile.source_platform}_extension"
        update["source_platform"] = profile.source_platform

    # Track mandate_id in source_details but DON'T overwrite top-level mandate_id
    # (multi-mandate linking is handled via $addToSet in the capture endpoint)

    field_mapping = {
        "naukri_profile_id": profile.naukri_profile_id,
        "naukri_profile_url": profile.naukri_profile_url,
        "naukri_resume_id": profile.naukri_resume_id,
        "naukri_profile_updated": profile.profile_last_updated,
        "naukri_last_active": profile.last_active,
        "name": profile.name,
        "name_lower": (profile.name or "").strip().lower() if profile.name else None,
        "first_name": profile.first_name,
        "middle_name": profile.middle_name,
        "last_name": profile.last_name,
        "email": profile.email.lower() if profile.email else None,
        "photo_url": profile.photo_url,
        "alternate_email": profile.alternate_email,
        "phone": profile.phone,
        "phone_normalized": normalized_capture_phone(profile.phone),
        "alternate_phone": profile.alternate_phone,
        "headline": profile.headline,
        "resume_headline": profile.resume_headline,
        "summary": profile.profile_summary,
        "current_employer": profile.current_company,
        "designation": profile.current_designation,
        "department": profile.current_department,
        "industry": profile.current_industry,
        "role_category": profile.current_role_category,
        "employment_status": profile.employment_status,
        "experience_years": float(profile.total_experience_years) if profile.total_experience_years is not None else None,
        "experience_months": profile.total_experience_months,
        "experience_display": profile.total_experience_display,
        "highest_qualification": profile.highest_qualification,
        "highest_degree": profile.highest_degree,
        "skills": profile.key_skills,
        "skills_display": profile.key_skills_display,
        "soft_skills": profile.soft_skills,
        "tools": profile.tools,
        "linkedin_url": profile.linkedin_url,
        "github_url": profile.github_url,
        "portfolio_url": profile.portfolio_url,
        "accomplishments": profile.accomplishments,
        "about_me": profile.about_me,
        "additional_info": profile.additional_info,
        "has_resume": profile.has_resume if "has_resume" in supplied else None,
        "resume_title": profile.resume_title,
        "resume_format": profile.resume_format,
        "naukri_response_rate": profile.response_rate,
        "raw_profile_text": profile.raw_profile_text,
        "raw_sections": profile.raw_sections,
    }

    for key, value in field_mapping.items():
        if _should_overwrite(value):
            update[key] = value

    if profile.work_experience:
        update["experience"] = _safe_list(profile.work_experience)
    if profile.education:
        update["education"] = _safe_list(profile.education)
    if profile.it_skills:
        update["it_skills"] = _safe_list(profile.it_skills)
    if profile.certifications:
        update["certifications"] = _safe_cert_names(profile.certifications)
        update["certifications_detailed"] = _safe_list(profile.certifications)
    if profile.projects:
        update["projects"] = _safe_list(profile.projects)
    if profile.languages:
        update["languages"] = _safe_list(profile.languages)
    if profile.online_profiles:
        update["online_profiles"] = _safe_list(profile.online_profiles)

    for key, value in personal.items():
        if _should_overwrite(value):
            update[key] = value

    career_keys = [
        "current_salary", "current_salary_currency", "current_salary_breakdown",
        "expected_salary", "expected_salary_currency", "expected_salary_min", "expected_salary_max",
        "notice_period", "notice_period_days", "is_serving_notice", "last_working_day",
        "preferred_locations", "willing_to_relocate", "relocation_preferences",
        "preferred_job_type", "preferred_employment_type", "preferred_shift",
        "work_from_home", "remote_work_preference",
        "preferred_industry", "preferred_functional_area", "preferred_role", "preferred_role_category",
        "preferred_company_type", "preferred_company_size", "companies_to_avoid"
    ]

    for key in career_keys:
        if key in career_prefs and _should_overwrite(career_prefs[key]):
            update[key] = career_prefs[key]

    if "current_location" in career_prefs and career_prefs["current_location"]:
        update["location"] = career_prefs["current_location"]

    if "is_negotiable" in career_prefs:
        update["notice_negotiable"] = career_prefs["is_negotiable"]

    return update
