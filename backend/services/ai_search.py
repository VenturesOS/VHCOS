"""
AI Search Service — Phase 1
Architecture: LLM (Extraction) → Deterministic DB Filter → Results → LLM (Explanation)
Model-agnostic: configurable model, upgrade-ready for Phase 2 hybrid routing.
"""
import os
import json
import time
import logging
import httpx
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# --- Model Configuration (Phase 2: swap to routing logic) ---
DEFAULT_MODEL = "gpt-4o-mini"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

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
    """Phase 1: always returns default. Phase 2: hybrid routing logic here."""
    return DEFAULT_MODEL


async def _call_llm(system_prompt: str, user_prompt: str, model: str = None, temperature: float = 0.0, json_mode: bool = True) -> dict:
    """Model-agnostic LLM call. Returns {"content": str, "usage": dict, "model": str}."""
    model = model or _get_model(user_prompt)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            OPENAI_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
        )

    if resp.status_code != 200:
        logger.error(f"[AI Search] LLM error {resp.status_code}: {resp.text[:300]}")
        raise RuntimeError(f"LLM call failed: {resp.status_code}")

    data = resp.json()
    return {
        "content": data["choices"][0]["message"]["content"],
        "usage": data.get("usage", {}),
        "model": data.get("model", model),
    }


# ──────────────────────────────────────────────
# STEP 1: Extract structured filters from prompt
# ──────────────────────────────────────────────
async def extract_filters(prompt: str) -> dict:
    """Call LLM to convert natural language prompt into structured JSON filters."""
    start = time.time()
    model = _get_model(prompt)
    result = await _call_llm(EXTRACTION_SYSTEM_PROMPT, prompt, model=model)
    raw_content = result["content"]

    try:
        filters = json.loads(raw_content)
    except json.JSONDecodeError:
        logger.error(f"[AI Search] LLM returned invalid JSON: {raw_content[:300]}")
        raise ValueError("AI could not parse the search prompt. Please rephrase.")

    elapsed = time.time() - start
    log_entry = {
        "raw_prompt": prompt,
        "extracted_filters": filters,
        "model": result["model"],
        "token_usage": result["usage"],
        "extraction_time_s": round(elapsed, 2),
    }
    logger.info(f"[AI Search] Extraction: {json.dumps(log_entry)}")
    return {"filters": filters, "log": log_entry}


# ──────────────────────────────────────────────
# STEP 2: Deterministic DB Filter Engine
# ──────────────────────────────────────────────
def build_mongo_query(filters: dict) -> dict:
    """Convert structured JSON filters into a MongoDB query. LLM never touches DB."""
    query = {}
    conditions = []

    # --- Experience ---
    exp_filter = {}
    if filters.get("min_experience") is not None:
        exp_filter["$gte"] = filters["min_experience"]
    if filters.get("max_experience") is not None:
        exp_filter["$lte"] = filters["max_experience"]
    if exp_filter:
        conditions.append({"experience_years": exp_filter})

    # --- Skills (search across skills, summary, headline, designation, it_skills) ---
    skills = filters.get("skills") or []
    if skills:
        skill_pattern = "|".join(skills)
        conditions.append({"$or": [
            {"skills": {"$regex": skill_pattern, "$options": "i"}},
            {"summary": {"$regex": skill_pattern, "$options": "i"}},
            {"headline": {"$regex": skill_pattern, "$options": "i"}},
            {"designation": {"$regex": skill_pattern, "$options": "i"}},
            {"raw_profile_text": {"$regex": skill_pattern, "$options": "i"}},
        ]})

    # --- Industry include/exclude ---
    industry_inc = filters.get("industry_include") or []
    industry_exc = filters.get("industry_exclude") or []
    if industry_inc:
        pattern = "|".join(industry_inc)
        conditions.append({"$or": [
            {"industry": {"$regex": pattern, "$options": "i"}},
            {"preferred_industry": {"$regex": pattern, "$options": "i"}},
        ]})
    if industry_exc:
        for ind in industry_exc:
            conditions.append({"industry": {"$not": {"$regex": ind, "$options": "i"}}})

    # --- Company type include/exclude ---
    ctype_inc = filters.get("company_type_include") or []
    ctype_exc = filters.get("company_type_exclude") or []
    if ctype_inc:
        pattern = "|".join(ctype_inc)
        conditions.append({"current_employer": {"$regex": pattern, "$options": "i"}})
    if ctype_exc:
        for ct in ctype_exc:
            conditions.append({"current_employer": {"$not": {"$regex": ct, "$options": "i"}}})

    # --- Location include/exclude ---
    loc_inc = filters.get("location_include") or []
    loc_exc = filters.get("location_exclude") or []
    if loc_inc:
        pattern = "|".join(loc_inc)
        conditions.append({"$or": [
            {"location": {"$regex": pattern, "$options": "i"}},
            {"current_city": {"$regex": pattern, "$options": "i"}},
            {"preferred_locations": {"$regex": pattern, "$options": "i"}},
        ]})
    if loc_exc:
        for loc in loc_exc:
            conditions.append({"location": {"$not": {"$regex": loc, "$options": "i"}}})
            conditions.append({"current_city": {"$not": {"$regex": loc, "$options": "i"}}})

    # --- Notice period ---
    np_val = filters.get("notice_period")
    if np_val:
        if np_val == "immediate":
            conditions.append({"$or": [
                {"notice_period": {"$regex": "immediate|0", "$options": "i"}},
                {"notice_period_days": {"$lte": 7}},
                {"is_serving_notice": True},
            ]})
        elif np_val == "not_serving":
            conditions.append({"is_serving_notice": {"$ne": True}})
        elif np_val.isdigit():
            conditions.append({"$or": [
                {"notice_period_days": {"$lte": int(np_val)}},
                {"notice_period": {"$regex": np_val, "$options": "i"}},
            ]})

    # --- CTC range ---
    ctc = filters.get("current_ctc_range")
    if ctc and isinstance(ctc, dict):
        ctc_q = {}
        if ctc.get("min") is not None:
            ctc_q["$gte"] = ctc["min"]
        if ctc.get("max") is not None:
            ctc_q["$lte"] = ctc["max"]
        if ctc_q:
            conditions.append({"current_salary": ctc_q})

    exp_ctc = filters.get("expected_ctc_range")
    if exp_ctc and isinstance(exp_ctc, dict):
        ectc_q = {}
        if exp_ctc.get("min") is not None:
            ectc_q["$gte"] = exp_ctc["min"]
        if exp_ctc.get("max") is not None:
            ectc_q["$lte"] = exp_ctc["max"]
        if ectc_q:
            conditions.append({"expected_salary": ectc_q})

    # --- Degree include/exclude ---
    deg_inc = filters.get("degree_include") or []
    deg_exc = filters.get("degree_exclude") or []
    if deg_inc:
        pattern = "|".join(deg_inc)
        conditions.append({"$or": [
            {"highest_qualification": {"$regex": pattern, "$options": "i"}},
            {"highest_degree": {"$regex": pattern, "$options": "i"}},
        ]})
    if deg_exc:
        for deg in deg_exc:
            conditions.append({"highest_qualification": {"$not": {"$regex": deg, "$options": "i"}}})
            conditions.append({"highest_degree": {"$not": {"$regex": deg, "$options": "i"}}})

    # --- Branch include/exclude ---
    br_inc = filters.get("branch_include") or []
    br_exc = filters.get("branch_exclude") or []
    if br_inc:
        pattern = "|".join(br_inc)
        conditions.append({"education.specialization": {"$regex": pattern, "$options": "i"}})
    if br_exc:
        for br in br_exc:
            conditions.append({"education.specialization": {"$not": {"$regex": br, "$options": "i"}}})

    if conditions:
        query["$and"] = conditions
    return query


def compute_stability(experience: list) -> dict:
    """Compute avg tenure and number of switches from work experience list."""
    if not experience or not isinstance(experience, list):
        return {"avg_tenure_years": None, "switches": None}
    tenures = []
    for exp in experience:
        if isinstance(exp, dict):
            years = exp.get("duration_years") or exp.get("years") or 0
            months = exp.get("duration_months") or exp.get("months") or 0
            total = float(years) + float(months) / 12.0
            if total > 0:
                tenures.append(total)
    switches = max(len(tenures) - 1, 0)
    avg_tenure = round(sum(tenures) / len(tenures), 1) if tenures else None
    return {"avg_tenure_years": avg_tenure, "switches": switches}


def apply_stability_filters(candidates: list, filters: dict) -> list:
    """Post-query filter for stability logic (requires computing per-candidate)."""
    min_tenure = filters.get("min_avg_tenure_years")
    max_switches = filters.get("max_switches")
    if min_tenure is None and max_switches is None:
        return candidates

    filtered = []
    for c in candidates:
        stability = compute_stability(c.get("experience", []))
        c["_stability"] = stability
        avg = stability["avg_tenure_years"]
        sw = stability["switches"]
        if min_tenure and avg is not None and avg < min_tenure:
            continue
        if max_switches is not None and sw is not None and sw > max_switches:
            continue
        filtered.append(c)
    return filtered


# ──────────────────────────────────────────────
# STEP 3: Generate explanations per candidate
# ──────────────────────────────────────────────
async def generate_explanations(candidates: list, filters: dict) -> list:
    """Add 1-2 line factual explanation per candidate using LLM."""
    if not candidates:
        return candidates

    # Build a batch prompt for efficiency
    batch_items = []
    for i, c in enumerate(candidates[:30]):  # Cap at 30 for token limits
        stability = c.get("_stability") or compute_stability(c.get("experience", []))
        item = {
            "idx": i,
            "name": c.get("name", "Unknown"),
            "designation": c.get("designation", ""),
            "employer": c.get("current_employer", ""),
            "industry": c.get("industry", ""),
            "experience_years": c.get("experience_years", 0),
            "location": c.get("location", ""),
            "skills": (c.get("skills") or [])[:8],
            "qualification": c.get("highest_qualification", ""),
            "notice_period": c.get("notice_period", ""),
            "current_salary": c.get("current_salary", ""),
            "avg_tenure": stability.get("avg_tenure_years"),
            "switches": stability.get("switches"),
        }
        batch_items.append(item)

    user_prompt = f"""Search filters used: {json.dumps(filters, default=str)}

Candidate data:
{json.dumps(batch_items, default=str)}

For each candidate (by idx), generate a 1-2 line factual explanation of why they match (or partially match) the search criteria. Be deterministic and factual. No marketing language. No hallucinations. Use only the provided data.

Return JSON: {{"explanations": [{{"idx": 0, "text": "..."}}]}}"""

    system = "You are a factual hiring match explainer. Generate brief, deterministic explanations based strictly on provided candidate data. Return only valid JSON."

    try:
        result = await _call_llm(system, user_prompt, temperature=0.1)
        parsed = json.loads(result["content"])
        explanations = {e["idx"]: e["text"] for e in parsed.get("explanations", [])}
        for i, c in enumerate(candidates[:30]):
            c["ai_explanation"] = explanations.get(i, "")
        logger.info(f"[AI Search] Explanations generated. Tokens: {result['usage']}")
    except Exception as e:
        logger.warning(f"[AI Search] Explanation generation failed: {e}")
        for c in candidates:
            c["ai_explanation"] = ""

    return candidates
