"""Existing profile post-processing, preserved from the extraction service."""
import logging
from datetime import datetime, timezone
from typing import Optional
logger = logging.getLogger(__name__)
CTC_MAX_SANE = 50_000_000
CTC_MIN_SANE = 50_000


def _extract_json_from_response(response_text: str) -> str:
    """Extract and repair JSON from LLM response (handles markdown, trailing commas, missing commas, etc.)."""
    import re
    from json_repair import repair_json
    
    clean = response_text.strip()
    
    # Remove markdown code blocks
    if clean.startswith('```'):
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', clean, re.DOTALL)
        if match:
            clean = match.group(1)
        else:
            clean = clean.replace('```json', '').replace('```', '').strip()
    
    # Extract just the JSON object if there's extra text before/after
    match = re.search(r'\{.*\}', clean, re.DOTALL)
    if match:
        clean = match.group(0)
    
    # v5.4.1: Use json_repair library as PRIMARY repair method
    # This handles missing commas, trailing commas, unquoted keys, etc.
    try:
        repaired = repair_json(clean, return_objects=False)
        if repaired and repaired.startswith('{'):
            return repaired
    except Exception as e:
        logger.debug(f"[JSON-Repair] Library failed, falling back to regex: {e}")
    
    # Fallback: manual regex repairs for edge cases
    # 1. Remove trailing commas before } or ]
    clean = re.sub(r',\s*([}\]])', r'\1', clean)
    # 2. Remove comments (// style)
    clean = re.sub(r'//[^\n]*', '', clean)
    # 3. Remove control characters
    clean = re.sub(r'[\x00-\x1f\x7f]', ' ', clean)
    # 4. Fix unquoted keys (common: key: "value" instead of "key": "value")
    clean = re.sub(r'(?<=\{|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r' "\1":', clean)
    # 5. Fix missing commas between fields: }"field" or ]"field" or ""  "field"
    clean = re.sub(r'"\s*\n\s*"', '",\n"', clean)
    clean = re.sub(r'"\s+"(?=[a-zA-Z_])', '", "', clean)
    clean = re.sub(r'(\})\s*(")', r'\1, \2', clean)
    clean = re.sub(r'(\])\s*(")', r'\1, \2', clean)
    clean = re.sub(r'(null|true|false|\d)\s*\n\s*"', r'\1,\n"', clean)
    # 6. Fix single quotes used as string delimiters
    clean = re.sub(r"(?<![a-zA-Z])'([^']*)'(?=\s*[:,}\]])", r'"\1"', clean)
    
    return clean

def sanitize_ctc(val) -> Optional[int]:
    """Validate a CTC number. Returns None if out of sane range (₹50K – ₹5Cr/year).
    Prevents corrupt LLM/regex outputs from polluting the candidate DB.
    """
    if val is None:
        return None
    try:
        n = int(float(val))
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if n < CTC_MIN_SANE:
        return None
    if n > CTC_MAX_SANE:
        return None
    return n

def _regex_backfill_critical(result: dict, raw_text: str) -> dict:
    """
    Post-LLM regex safety net: Backfill CTC, notice period, education, location
    from raw text when LLM missed them. Ensures consistency regardless of LLM quality.

    Defensive: any internal error (bad regex, unexpected input) must NOT bubble up —
    the LLM result is always more valuable than a regex backfill side-effect.
    """
    try:
        return _regex_backfill_critical_impl(result, raw_text)
    except Exception as e:
        logger.error(f"[Regex Backfill] Non-fatal error — returning LLM result as-is: {e}")
        return result

def _regex_backfill_critical_impl(result: dict, raw_text: str) -> dict:
    import re

    # ── CTC (current) ──
    if not result.get('current_ctc'):
        ctc_patterns = [
            re.compile(r'₹\s*([\d.]+)\s*(Lacs?|LPA|Lac)\s*\(expects', re.IGNORECASE),
            re.compile(r'₹\s*([\d.]+)\s*(Lacs?|LPA|Lac)(?!\s*\))', re.IGNORECASE),
            re.compile(r'(?:Current\s+)?CTC[:\s]+₹?\s*([\d.]+)\s*(Lacs?|LPA|Lac|Cr|Crore)', re.IGNORECASE),
            re.compile(r'([\d.]+)\s*(Lacs?|LPA)\s*(?:per\s+annum|p\.?a\.?|annual)?', re.IGNORECASE),
        ]
        for pat in ctc_patterns:
            m = pat.search(raw_text)
            if m:
                val = float(m.group(1))
                unit = m.group(2).lower()
                if unit in ('cr', 'crore'):
                    candidate = int(val * 10000000)
                else:
                    candidate = int(val * 100000)
                clean = sanitize_ctc(candidate)
                if clean is not None:
                    result['current_ctc'] = clean
                    logger.info(f"[Regex Backfill] CTC: {clean}")
                else:
                    logger.warning(f"[Regex Backfill] CTC rejected (out of sane range): raw={candidate} from '{m.group(0)}'")
                break

    # ── CTC (expected) ──
    if not result.get('expected_ctc'):
        m = re.search(r'expects?[:\s]*₹?\s*([\d.]+)\s*(Lacs?|LPA|Lac|Cr|Crore)', raw_text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            unit = m.group(2).lower()
            if unit in ('cr', 'crore'):
                candidate = int(val * 10000000)
            else:
                candidate = int(val * 100000)
            clean = sanitize_ctc(candidate)
            if clean is not None:
                result['expected_ctc'] = clean
                logger.info(f"[Regex Backfill] Expected CTC: {clean}")
            else:
                logger.warning(f"[Regex Backfill] Expected CTC rejected (out of sane range): raw={candidate}")

    # Also sanitize any LLM-provided CTC that slipped through
    for _k in ('current_ctc', 'expected_ctc'):
        if result.get(_k) is not None:
            _clean = sanitize_ctc(result[_k])
            if _clean != result[_k]:
                logger.warning(f"[CTC-Sanitize] {_k} rejected: {result[_k]} -> None")
                result[_k] = _clean

    # ── Notice Period ──
    if not result.get('notice_period'):
        notice_patterns = [
            re.compile(r'Notice\s*(?:Period)?[:\s]+(\d{1,2})\s*Months?', re.IGNORECASE),
            re.compile(r'(\d{1,2})\s*Months?\s*(?:Notice|notice)', re.IGNORECASE),
            re.compile(r'(Immediate(?:ly)?|Serving\s+Notice)', re.IGNORECASE),
        ]
        for pat in notice_patterns:
            m = pat.search(raw_text)
            if m:
                txt = m.group(1)
                if txt.lower().startswith('immedia'):
                    result['notice_period'] = 'Immediate'
                    result['notice_period_days'] = 0
                elif txt.lower().startswith('serving'):
                    result['notice_period'] = 'Serving Notice'
                    result['notice_period_days'] = 0
                else:
                    months = int(txt)
                    result['notice_period'] = f"{months} Month{'s' if months != 1 else ''}"
                    result['notice_period_days'] = months * 30
                logger.info(f"[Regex Backfill] Notice: {result['notice_period']}")
                break

    # ── Location ──
    if not result.get('location'):
        loc_patterns = [
            re.compile(r'(?:Lacs?|LPA|Cr)\)?\.?\s*([A-Z][a-z]+(?:[,\s]+[A-Z][a-z]+){0,2})\s*Current'),
            re.compile(r'Current\s+Location[:\s]+([A-Za-z][A-Za-z\s,]+?)(?:\s*[\|\n•]|\s+Notice|\s+CTC)', re.IGNORECASE),
            re.compile(r'Location[:\s]+([A-Za-z][A-Za-z\s,]+?)(?:\s*[\|\n•]|\s*$)', re.IGNORECASE),
        ]
        for pat in loc_patterns:
            m = pat.search(raw_text)
            if m:
                loc = m.group(1).strip().rstrip(',')
                if len(loc) > 2 and loc.lower() not in ('the', 'and', 'for', 'not'):
                    result['location'] = loc
                    logger.info(f"[Regex Backfill] Location: {result['location']}")
                    break

    # ── Education (if empty or missing) ──
    edu = result.get('education', [])
    if not edu:
        degree_patterns = [
            re.compile(r'(B\.?Tech|B\.?E\.?|M\.?Tech|M\.?E\.?|MBA|MCA|BCA|B\.?Sc|M\.?Sc|BBA|B\.?Com|M\.?Com|Ph\.?D|Diploma)', re.IGNORECASE),
        ]
        for pat in degree_patterns:
            matches = pat.findall(raw_text)
            if matches:
                for deg in set(matches[:3]):
                    result.setdefault('education', []).append({
                        "degree": deg,
                        "institution": "Not Available",
                        "year_of_passing": "",
                        "specialization": None,
                        "score": None
                    })
                logger.info(f"[Regex Backfill] Education: {len(result.get('education', []))} degrees found")
                break

    # ── Highest Qualification ──
    if not result.get('highest_qualification') and result.get('education'):
        priority = ['Ph.D', 'M.Tech', 'M.E.', 'MBA', 'M.Sc', 'M.Com', 'MCA', 'B.Tech', 'B.E.', 'B.Sc', 'BBA', 'B.Com', 'BCA', 'Diploma']
        for p in priority:
            for edu_item in result.get('education', []):
                if p.lower() in (edu_item.get('degree', '') or '').lower():
                    result['highest_qualification'] = edu_item.get('degree', p)
                    break
            if result.get('highest_qualification'):
                break

    return result

def _parse_work_date(date_str):
    """Parse Naukri-style work-experience dates into (year, month).
    Handles: 'Jun 2022', "Jun '22", 'June 2020', '2020', 'Present', 'Current', 'Till Date', etc.
    Returns (year:int, month:int) or None if cannot parse. Month defaults to 6 (mid-year) if absent.
    """
    import re
    if not date_str or not isinstance(date_str, str):
        return None
    s = date_str.strip()
    if not s:
        return None
    # Present / Current / Till Date → now
    if re.search(r'\b(present|current|till\s*date|now|ongoing)\b', s, re.IGNORECASE):
        now = datetime.now(timezone.utc)
        return (now.year, now.month)
    months = {
        'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
        'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
        'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9,
        'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12,
    }
    # "Jun 2022" / "Jun '22" / "June 2020" / "06/2022" / "06-2022" / "2022"
    m = re.search(r"([A-Za-z]{3,9})[\s,'`]+(\d{2,4})", s)
    if m:
        mo = months.get(m.group(1).lower())
        if mo:
            yr = int(m.group(2))
            if yr < 100:
                yr += 2000 if yr < 70 else 1900
            return (yr, mo)
    m = re.search(r"(\d{1,2})[/\-\.](\d{2,4})", s)
    if m:
        mo = int(m.group(1))
        yr = int(m.group(2))
        if yr < 100:
            yr += 2000 if yr < 70 else 1900
        if 1 <= mo <= 12:
            return (yr, mo)
    # Year only
    m = re.search(r"\b(19|20)(\d{2})\b", s)
    if m:
        return (int(m.group(1) + m.group(2)), 6)
    return None

def _compute_duration(from_date: str, to_date: str, is_current: bool = False) -> Optional[str]:
    """Compute 'Xy Ym' from date range. Returns None if unable to compute."""
    f = _parse_work_date(from_date)
    if not f:
        return None
    if is_current or not to_date or not str(to_date).strip():
        now = datetime.now(timezone.utc)
        t = (now.year, now.month)
    else:
        t = _parse_work_date(to_date)
        if not t:
            now = datetime.now(timezone.utc)
            t = (now.year, now.month)
    total_from = f[0] * 12 + f[1]
    total_to = t[0] * 12 + t[1]
    diff = max(0, total_to - total_from)
    years = diff // 12
    months = diff % 12
    return f"{years}y {months}m"

def _fix_work_experience_durations(result: dict) -> dict:
    """Post-process work_experience list: compute duration from from_date/to_date
    whenever duration is missing, empty, or the '0y 0m' placeholder produced by LLMs.
    """
    work = result.get("work_experience")
    if not isinstance(work, list):
        return result
    fixed_count = 0
    for exp in work:
        if not isinstance(exp, dict):
            continue
        dur = (exp.get("duration") or "").strip().lower()
        needs_fix = (
            not dur
            or dur in ("0y 0m", "0 y 0 m", "0 years 0 months", "0y0m")
            or dur.startswith("0y 0m")
        )
        if needs_fix:
            computed = _compute_duration(
                exp.get("from_date"),
                exp.get("to_date"),
                bool(exp.get("is_current")),
            )
            if computed and computed != "0y 0m":
                exp["duration"] = computed
                fixed_count += 1
    if fixed_count:
        logger.info(f"[DurationFix] Recomputed {fixed_count} work_experience durations")
    return result

def _fix_experience_from_raw_text(result: dict, raw_text: str) -> dict:
    """
    Post-processing: Extract experience_years from raw text using regex
    and override the LLM's value. LLMs often use standard math division
    (months/12) instead of our custom formula (months/100).
    
    Formula: Years + (Months / 100)
    "7y 3m" = 7.03, "2y 5m" = 2.05, "0y 8m" = 0.08
    """
    import re
    
    patterns = [
        # "5y 8m", "5Y 8M", "5y8m"
        r'(\d{1,2})\s*[yY]\s*(\d{1,2})\s*[mM]',
        # "5 years 8 months", "5 year 3 month"
        r'(\d{1,2})\s*(?:years?)\s*(\d{1,2})\s*(?:months?)',
        # "5 Yrs 8 Mos"
        r'(\d{1,2})\s*(?:yrs?)\s*(\d{1,2})\s*(?:mos?)',
        # "5 Years, 8 Months" (with comma)
        r'(\d{1,2})\s*(?:years?|yrs?)\s*[,.\s]+\s*(\d{1,2})\s*(?:months?|mos?)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            years = int(match.group(1))
            months = int(match.group(2))
            correct_exp = round(years + (months / 100), 2)
            llm_exp = result.get("experience_years")
            if llm_exp != correct_exp:
                logger.info(f"[ExpFix] Corrected experience: {llm_exp} -> {correct_exp} (from '{match.group(0)}')")
                result["experience_years"] = correct_exp
                result["_experience_corrected"] = True
            return result
    
    # Year-only patterns (no months mentioned)
    year_only_patterns = [
        # "Experience : 8 Years" or "Total Experience: 8 Years" (header format)
        r'(?:Total\s*)?Experience\s*[:\-]\s*(\d{1,2})\s*(?:years?|yrs?)',
        # Naukri header: "8 Years | Current CTC" or "8 Years₹" 
        r'(\d{1,2})\s*(?:years?|yrs?)\s*(?:[|\u20b9₹•,])',
    ]
    
    for pattern in year_only_patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            years = int(match.group(1))
            if years > 0:
                correct_exp = float(years)
                llm_exp = result.get("experience_years")
                # Only override if LLM value seems wrong (e.g., defaulted to 1)
                if llm_exp is None or (llm_exp <= 1 and years > 1):
                    logger.info(f"[ExpFix] Corrected experience (year-only): {llm_exp} -> {correct_exp} (from '{match.group(0)}')")
                    result["experience_years"] = correct_exp
                    result["_experience_corrected"] = True
                return result
    
    return result

PROFILE_SYSTEM_PROMPT = 'You are an expert data-extraction agent for recruitment profiles (Naukri, LinkedIn, Monster, resume text).\n\n============================================================\nCRITICAL — STRUCTURAL ANCHOR (Naukri Top Card)\n============================================================\nNaukri profiles are structured. The FIRST 800–1500 characters of the text contain a "Top Card" with the canonical values for Experience, Current CTC, Expected CTC, Current Location, Notice Period, Current Employer, Current Designation, and Highest Degree. THESE ARE SOURCE-OF-TRUTH values. You MUST extract them if they are present in the header region.\n\nCommon Naukri top-card patterns and how to map them:\n  • "22y"                           →  experience_years = 22.00\n  • "10y 3m"                        →  experience_years = 10.03   (years + months/100, NOT months/12)\n  • "5y"                            →  experience_years = 5.00\n  • "₹60 Lacs (expects: ₹80 Lacs)"  →  current_ctc = 6000000   expected_ctc = 8000000\n  • "₹60 Lacs"                      →  current_ctc = 6000000\n  • "60 LPA"                        →  current_ctc = 6000000\n  • "18.5 Lakhs"                    →  current_ctc = 1850000\n  • "Indore"                        →  location = "Indore"\n  • "Current: Head Mfg at Mahindra" →  current_designation = "Head Mfg", current_employer = "Mahindra"\n  • "3 Months" / "60 days" / "Immediate" → notice_period = that string, notice_period_days = 90 / 60 / 0\n\nIF THE TOP CARD SHOWS A VALUE, YOU MUST RETURN IT. Leaving it null when it is visible in the header is a CRITICAL FAILURE. Only use null when the field is genuinely absent.\nReturn expected_ctc SEPARATELY from current_ctc — never merge them.\n\n============================================================\nOUTPUT — return ONLY valid JSON (no markdown, no commentary):\n============================================================\n{\n    "name": "full name",\n    "email": "email address",\n    "phone": "phone number",\n    "location": "current location/city (from top card)",\n    "experience_years": total years as decimal number (from top card),\n    "current_employer": "current company name (from top card)",\n    "current_designation": "current job title (from top card)",\n    "current_ctc": CTC in RUPEES (convert lakhs → rupees, see examples above),\n    "expected_ctc": expected CTC in RUPEES (never reuse current_ctc for this),\n    "notice_period": "exact label e.g. \'Immediate\', \'15 Days\', \'30 Days\', \'2 Months\', \'3 Months\'",\n    "notice_period_days": notice period in days (Immediate=0, 15 Days=15, 1 Month=30, 2 Months=60, 3 Months=90),\n    "profile_summary": "2-3 sentence professional summary",\n    "headline": "professional headline or null",\n    "key_skills": ["skill1", "skill2"],\n    "work_experience": [\n        {\n            "company": "company name",\n            "designation": "job title",\n            "from_date": "start date (e.g., Jun 2022, Jan 2018, 2015)",\n            "to_date": "end date or \'Present\'",\n            "is_current": true/false,\n            "duration": "e.g. 2y 3m — compute from from_date to to_date (or today if Present). NEVER return \'0y 0m\' unless the role is less than 1 month old.",\n            "description": "full role description"\n        }\n    ],\n    "education": [\n        {\n            "degree": "degree name (e.g., B.Tech, MBA, M.Sc, B.E., Bachelor, Master, Ph.D)",\n            "institution": "college/university name (or \'Not Available\' if not found)",\n            "specialization": "specialization or null",\n            "year_of_passing": "graduation year (e.g., 2015, 2020, or \'Not Available\' if not found)",\n            "score": "GPA/percentage if available (or null if not found)"\n        }\n    ],\n    "certifications": ["cert1"],\n    "languages": ["lang1"],\n    "projects": [{"name": "string", "description": "string"}],\n    "online_profiles": [{"platform": "string", "url": "string"}],\n    "preferred_locations": ["city1"],\n    "highest_qualification": "string or null",\n    "current_department": "string or null",\n    "current_industry": "string or null"\n}\n\n============================================================\nEXTRACTION ORDER (follow strictly):\n============================================================\nSTEP 1 — Scan the FIRST 1500 characters (the Top Card). Extract: experience_years, current_ctc, expected_ctc, location, notice_period, current_employer, current_designation. If any of these values are visible in the header, you MUST populate them.\nSTEP 2 — Scan the rest of the profile for work_experience, education, skills, certifications, projects.\nSTEP 3 — Cross-check: if top-card current_employer/current_designation was found, ensure the first item of work_experience matches.\n\nCTC CONVERSION RULES (CRITICAL):\n- "Lacs" / "Lakhs" / "L" → multiply by 100000. "60 Lacs" = 6000000.\n- "LPA" = Lakhs Per Annum. "60 LPA" = 6000000.\n- "Cr" / "Crore" → multiply by 10000000. "1.2 Cr" = 12000000.\n- If only a raw number is given (e.g. "600000"), return it as-is.\n- Cap sanity: reject values > 500000000 (₹50 Cr) — those are data entry errors.\n\nNOTICE PERIOD MAPPING:\n- "Immediate" / "Immediately" / "0 days" / "Available to join" → notice_period_days = 0\n- "15 days" / "15 Days or less" / "2 weeks" → 15\n- "30 days" / "1 month" → 30\n- "60 days" / "2 months" → 60\n- "90 days" / "3 months" → 90\n- ">3 months" / "90+ days" → 120\n\nEXPERIENCE RULES:\n- Use this SPECIAL formula: experience_years = Years + (Months / 100). This is NOT math — each month adds 0.01, NOT 0.083:\n  * "7y 3m" = 7.03    (NOT 7.25)\n  * "22y" = 22.00\n  * "10+ years" = 10.00\n- ALWAYS return experience_years as a decimal number (float).\n- If the top card shows experience (common in Naukri), USE THAT VALUE directly.\n\nEDUCATION RULES:\n- Look for degrees (B.Tech, B.E., MBA, M.Tech, M.Sc, Bachelor, Master, BBA, MCA, Ph.D).\n- Look for institutions: college, university, institute, IIT, NIT, IIM.\n- If top card shows "Ph.D/Doctorate Indian Institute of Management, Kolkata", extract degree="Ph.D", institution="Indian Institute of Management, Kolkata".\n- If you find ONLY a degree but no institution, still return it with institution="Not Available".\n- Never return education where ALL fields are "Not Available" — return [] instead.\n\nGENERAL RULES:\n- DO NOT mix education with work experience.\n- Extract ALL skills mentioned anywhere (Key Skills, IT Skills, Technical Skills).\n- For each work_experience item, write a 2-3 sentence description.\n- Return ONLY the JSON. No markdown fences, no explanations.\n'
