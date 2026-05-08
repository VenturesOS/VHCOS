"""
AI Search Service — Phase 1
Architecture: LLM (Extraction) → Deterministic DB Filter → Results → LLM (Explanation)

FIXED:
- build_mongo_query() queries BOTH canonical (key_skills, profile_summary,
  work_experience, total_experience_years) AND alias (skills, summary,
  experience, experience_years) field names — no candidate invisible
- compute_stability() reads both work_experience and experience
- Regex patterns escaped to prevent injection
- Industry/location/employer queries cover both canonical and alias field names
"""
import os
import re
import json
import time
import logging
from typing import Dict, List, Optional

from services.llm_service import chat_completion

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are an Industrial Hiring Logic Translator inside an ATS system.

Your ONLY task is to convert natural language hiring requirements into STRICT structured JSON.

You must:
- Extract hiring filters precisely.
- Interpret stability logic (job hopping, tenure).
- Detect inclusion and exclusion conditions.
- Detect negation words such as: not, no, exclude, avoid, shouldn't.
- Convert industry and company type intent into structured fields.
- Handle qualification filtering including specific branches.
- Handle notice period and salary intent.
- Return JSON only.
- Never return explanation text.
- Never add commentary.
- Never format using markdown.
- Never include backticks.
- Never guess values not explicitly implied.

If a value is not specified, return null or empty array.

Stability interpretation rules:
- "Not a job hopper" → max_switches: 4 and min_avg_tenure_years: 2.5
- "Minimum 3 years stability" → min_avg_tenure_years: 3
- "Stable profile" → min_avg_tenure_years: 2.5

Negation handling:
- If the user says "not dealership", map to company_type_exclude.
- If the user says "not Big 4", map to company_type_exclude.
- If the user says "exclude diploma", map to degree_exclude.
- If the user says "OEM only", map to company_type_include: ["OEM"] and exclude dealership automatically.

Industry adjacency:
- If user says "or similar industries", include only the explicitly mentioned industries in JSON.
- Do NOT expand adjacency automatically in Phase 1.

Notice period mapping:
- "Immediate" → notice_period: "immediate"
- "30 days" → notice_period: "30"
- "Not serving notice" → notice_period: "not_serving"

Output format EXACTLY as:

{
  "min_experience": null,
  "max_experience": null,
  "skills": [],
  "industry_include": [],
  "industry_exclude": [],
  "company_type_include": [],
  "company_type_exclude": [],
  "location_include": [],
  "location_exclude": [],
  "notice_period": null,
  "current_ctc_range": null,
  "expected_ctc_range": null,
  "degree_include": [],
  "degree_exclude": [],
  "branch_include": [],
  "branch_exclude": [],
  "min_avg_tenure_years": null,
  "max_switches": null,
  "additional_notes": ""
}

Return only valid JSON.
No extra characters before or after."""


def _get_model(prompt: str = "") -> str:
    from services.llm_service import get_model
    return get_model()


async def _call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str = None,
    temperature: float = 0.0,
    json_mode: bool = True,
) -> dict:
    model = model or _get_model(user_prompt)
    return await chat_completion(
        system_prompt, user_prompt,
        model=model, temperature=temperature,
        json_mode=json_mode, timeout=30.0,
        return_usage=True,
    )


# ---------------------------------------------------------------------------
# STEP 1: Extract structured filters from natural language prompt
# ---------------------------------------------------------------------------

async def extract_filters(prompt: str) -> dict:
    """Call LLM to convert natural language prompt into structured JSON filters."""
    start  = time.time()
    model  = _get_model(prompt)
    result = await _call_llm(EXTRACTION_SYSTEM_PROMPT, prompt, model=model)
    raw_content = result["content"]

    try:
        filters = json.loads(raw_content)
    except json.JSONDecodeError:
        logger.error(f"[AI Search] LLM returned invalid JSON: {raw_content[:300]}")
        raise ValueError("AI could not parse the search prompt. Please rephrase.")

    elapsed   = time.time() - start
    log_entry = {
        "raw_prompt":        prompt,
        "extracted_filters": filters,
        "model":             result["model"],
        "token_usage":       result["usage"],
        "extraction_time_s": round(elapsed, 2),
    }
    logger.info(f"[AI Search] Extraction: {json.dumps(log_entry)}")
    return {"filters": filters, "log": log_entry}


# ---------------------------------------------------------------------------
# STEP 2: Deterministic DB Filter Engine
# ---------------------------------------------------------------------------

def _safe_pattern(terms: List[str]) -> str:
    """Build a safe regex alternation pattern from a list of terms."""
    return "|".join(re.escape(t) for t in terms if t)


def build_mongo_query(filters: dict) -> dict:
    """
    Convert structured JSON filters into a MongoDB query.
    LLM never touches the DB.

    FIXED: queries BOTH canonical AND alias field names so that no candidate
    is invisible regardless of which parser wrote their document.

    Field alias pairs covered:
      key_skills          ↔  skills
      profile_summary     ↔  summary
      work_experience     ↔  experience
      total_experience_years ↔ experience_years
      current_designation ↔  designation
      current_company     ↔  current_employer
      current_industry    ↔  industry
    """
    conditions = []

    # ── Experience ────────────────────────────────────────────────────────
    exp_filter: Dict = {}
    if filters.get("min_experience") is not None:
        exp_filter["$gte"] = filters["min_experience"]
    if filters.get("max_experience") is not None:
        exp_filter["$lte"] = filters["max_experience"]
    if exp_filter:
        conditions.append({
            "$or": [
                {"total_experience_years": exp_filter},  # canonical
                {"experience_years":       exp_filter},  # alias
            ]
        })

    # ── Skills — query ALL field names and text fields ────────────────────
    skills = [s for s in (filters.get("skills") or []) if s]
    if skills:
        skill_pattern = _safe_pattern(skills)
        conditions.append({"$or": [
            {"key_skills":          {"$regex": skill_pattern, "$options": "i"}},  # canonical
            {"skills":              {"$regex": skill_pattern, "$options": "i"}},  # alias
            {"it_skills.name":      {"$regex": skill_pattern, "$options": "i"}},  # it_skills
            {"profile_summary":     {"$regex": skill_pattern, "$options": "i"}},  # canonical
            {"summary":             {"$regex": skill_pattern, "$options": "i"}},  # alias
            {"headline":            {"$regex": skill_pattern, "$options": "i"}},
            {"current_designation": {"$regex": skill_pattern, "$options": "i"}},  # canonical
            {"designation":         {"$regex": skill_pattern, "$options": "i"}},  # alias
            {"raw_profile_text":    {"$regex": skill_pattern, "$options": "i"}},
        ]})

    # ── Industry ──────────────────────────────────────────────────────────
    industry_inc = [i for i in (filters.get("industry_include") or []) if i]
    industry_exc = [i for i in (filters.get("industry_exclude") or []) if i]
    if industry_inc:
        pattern = _safe_pattern(industry_inc)
        conditions.append({"$or": [
            {"current_industry":  {"$regex": pattern, "$options": "i"}},  # canonical
            {"industry":          {"$regex": pattern, "$options": "i"}},  # alias
            {"preferred_industry":{"$regex": pattern, "$options": "i"}},
        ]})
    for ind in industry_exc:
        p = re.escape(ind)
        conditions.append({"current_industry": {"$not": {"$regex": p, "$options": "i"}}})
        conditions.append({"industry":         {"$not": {"$regex": p, "$options": "i"}}})

    # ── Company type ──────────────────────────────────────────────────────
    ctype_inc = [c for c in (filters.get("company_type_include") or []) if c]
    ctype_exc = [c for c in (filters.get("company_type_exclude") or []) if c]
    if ctype_inc:
        pattern = _safe_pattern(ctype_inc)
        conditions.append({"$or": [
            {"current_company":   {"$regex": pattern, "$options": "i"}},  # canonical
            {"current_employer":  {"$regex": pattern, "$options": "i"}},  # alias
        ]})
    for ct in ctype_exc:
        p = re.escape(ct)
        conditions.append({"current_company":  {"$not": {"$regex": p, "$options": "i"}}})
        conditions.append({"current_employer": {"$not": {"$regex": p, "$options": "i"}}})

    # ── Location ──────────────────────────────────────────────────────────
    loc_inc = [l for l in (filters.get("location_include") or []) if l]
    loc_exc = [l for l in (filters.get("location_exclude") or []) if l]
    if loc_inc:
        pattern = _safe_pattern(loc_inc)
        conditions.append({"$or": [
            {"location":            {"$regex": pattern, "$options": "i"}},
            {"current_city":        {"$regex": pattern, "$options": "i"}},
            {"preferred_locations": {"$regex": pattern, "$options": "i"}},
        ]})
    for loc in loc_exc:
        p = re.escape(loc)
        conditions.append({"location":     {"$not": {"$regex": p, "$options": "i"}}})
        conditions.append({"current_city": {"$not": {"$regex": p, "$options": "i"}}})

    # ── Notice period ─────────────────────────────────────────────────────
    np_val = filters.get("notice_period")
    if np_val:
        np_str = str(np_val)
        if np_str == "immediate":
            conditions.append({"$or": [
                {"notice_period":      {"$regex": r"immediate|0|serving", "$options": "i"}},
                {"notice_period_days": {"$lte": 7}},
            ]})
        elif np_str == "not_serving":
            conditions.append({"is_serving_notice": {"$ne": True}})
        elif np_str.isdigit():
            conditions.append({"$or": [
                {"notice_period_days": {"$lte": int(np_str)}},
                {"notice_period":      {"$regex": re.escape(np_str), "$options": "i"}},
            ]})

    # ── CTC ranges ────────────────────────────────────────────────────────
    for ctc_filter_key, db_field in (
        ("current_ctc_range",  "current_salary"),
        ("expected_ctc_range", "expected_salary"),
    ):
        ctc = filters.get(ctc_filter_key)
        if ctc and isinstance(ctc, dict):
            q: Dict = {}
            if ctc.get("min") is not None:
                q["$gte"] = ctc["min"]
            if ctc.get("max") is not None:
                q["$lte"] = ctc["max"]
            if q:
                conditions.append({db_field: q})

    # ── Degree ────────────────────────────────────────────────────────────
    deg_inc = [d for d in (filters.get("degree_include") or []) if d]
    deg_exc = [d for d in (filters.get("degree_exclude") or []) if d]
    if deg_inc:
        pattern = _safe_pattern(deg_inc)
        conditions.append({"$or": [
            {"highest_qualification": {"$regex": pattern, "$options": "i"}},
            {"highest_degree":        {"$regex": pattern, "$options": "i"}},
            {"education.degree":      {"$regex": pattern, "$options": "i"}},
        ]})
    for deg in deg_exc:
        p = re.escape(deg)
        conditions.append({"highest_qualification": {"$not": {"$regex": p, "$options": "i"}}})
        conditions.append({"highest_degree":        {"$not": {"$regex": p, "$options": "i"}}})
        conditions.append({"education.degree":      {"$not": {"$regex": p, "$options": "i"}}})

    # ── Branch ────────────────────────────────────────────────────────────
    br_inc = [b for b in (filters.get("branch_include") or []) if b]
    br_exc = [b for b in (filters.get("branch_exclude") or []) if b]
    if br_inc:
        pattern = _safe_pattern(br_inc)
        conditions.append({"education.specialization": {"$regex": pattern, "$options": "i"}})
    for br in br_exc:
        p = re.escape(br)
        conditions.append({"education.specialization": {"$not": {"$regex": p, "$options": "i"}}})

    return {"$and": conditions} if conditions else {}


def compute_stability(candidate: dict) -> dict:
    """
    Compute avg tenure and number of job switches from work experience.

    FIXED: reads BOTH work_experience (canonical) AND experience (alias).
    """
    experience = (
        candidate.get("work_experience")   # canonical
        or candidate.get("experience")      # alias
        or []
    )
    if not isinstance(experience, list):
        return {"avg_tenure_years": None, "switches": None}

    tenures = []
    for exp in experience:
        if not isinstance(exp, dict):
            continue
        years  = float(exp.get("duration_years")  or exp.get("years")  or 0)
        months = float(exp.get("duration_months") or exp.get("months") or 0)
        total  = years + months / 12.0
        if total > 0:
            tenures.append(total)

    switches   = max(len(tenures) - 1, 0)
    avg_tenure = round(sum(tenures) / len(tenures), 1) if tenures else None
    return {"avg_tenure_years": avg_tenure, "switches": switches}


def apply_stability_filters(candidates: list, filters: dict) -> list:
    """Post-query filter for stability logic."""
    min_tenure   = filters.get("min_avg_tenure_years")
    max_switches = filters.get("max_switches")
    if min_tenure is None and max_switches is None:
        return candidates

    filtered = []
    for c in candidates:
        stability = compute_stability(c)
        c["_stability"] = stability
        avg = stability["avg_tenure_years"]
        sw  = stability["switches"]
        if min_tenure is not None and avg is not None and avg < min_tenure:
            continue
        if max_switches is not None and sw is not None and sw > max_switches:
            continue
        filtered.append(c)
    return filtered


# ---------------------------------------------------------------------------
# STEP 3: Generate explanations per candidate
# ---------------------------------------------------------------------------

async def generate_explanations(candidates: list, filters: dict) -> list:
    """Add 1-2 line factual explanation per candidate using LLM."""
    if not candidates:
        return candidates

    from services.schema_normalizer import get_skills, get_experience_years

    batch_items = []
    for i, c in enumerate(candidates[:30]):
        stability = c.get("_stability") or compute_stability(c)
        batch_items.append({
            "idx":              i,
            "name":             c.get("name", "Unknown"),
            "designation":      c.get("current_designation") or c.get("designation", ""),
            "employer":         c.get("current_company") or c.get("current_employer", ""),
            "industry":         c.get("current_industry") or c.get("industry", ""),
            "experience_years": get_experience_years(c),
            "location":         c.get("location", ""),
            "skills":           get_skills(c)[:8],
            "qualification":    c.get("highest_qualification", ""),
            "notice_period":    c.get("notice_period", ""),
            "current_salary":   c.get("current_salary", ""),
            "avg_tenure":       stability.get("avg_tenure_years"),
            "switches":         stability.get("switches"),
        })

    user_prompt = (
        f"Search filters used: {json.dumps(filters, default=str)}\n\n"
        f"Candidate data:\n{json.dumps(batch_items, default=str)}\n\n"
        "For each candidate (by idx), generate a 1-2 line factual explanation of why they "
        "match (or partially match) the search criteria. Be deterministic and factual. "
        "No marketing language. No hallucinations. Use only the provided data.\n\n"
        'Return JSON: {"explanations": [{"idx": 0, "text": "..."}]}'
    )

    system = (
        "You are a factual hiring match explainer. Generate brief, deterministic explanations "
        "based strictly on provided candidate data. Return only valid JSON."
    )

    try:
        result      = await _call_llm(system, user_prompt, temperature=0.1)
        parsed      = json.loads(result["content"])
        explanations = {e["idx"]: e["text"] for e in parsed.get("explanations", [])}
        for i, c in enumerate(candidates[:30]):
            c["ai_explanation"] = explanations.get(i, "")
        logger.info(f"[AI Search] Explanations generated. Tokens: {result['usage']}")
    except Exception as e:
        logger.warning(f"[AI Search] Explanation generation failed: {e}")
        for c in candidates:
            c["ai_explanation"] = ""

    return candidates
