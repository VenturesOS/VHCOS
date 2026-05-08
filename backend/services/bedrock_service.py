"""
Smart Extraction Service — Claude Opus 4.6 via Emergent Universal Key.
Used for intelligent contact extraction and CV enrichment.
"""

import os
import json
import logging
import uuid
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


async def _track_key_usage(key_index: int, input_tokens: int, output_tokens: int, service: str = "bedrock"):
    """Track Anthropic API key token usage in MongoDB."""
    try:
        from config import db
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await db.anthropic_key_usage.update_one(
            {"key_index": key_index, "date": today},
            {
                "$inc": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "call_count": 1,
                },
                "$set": {"last_used": datetime.now(timezone.utc).isoformat()},
                "$setOnInsert": {"key_index": key_index, "date": today},
            },
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"[Usage Track] Failed: {e}")


async def _call_claude(system_prompt: str, user_prompt: str, max_tokens: int = 1000, model_override: str = None, use_direct_anthropic: bool = False) -> str:
    """Call AI via waterfall: Direct Anthropic (admin) → OpenRouter Free → Claude (Emergent fallback).
    model_override: e.g. 'claude-haiku-4-5' to test cheaper models.
    use_direct_anthropic: bypass Emergent/OpenRouter and call Anthropic SDK directly."""

    # ── 0. Direct Anthropic SDK with key rotation fallback ──
    if use_direct_anthropic:
        import anthropic

        # Collect all available keys: ANTHROPIC_API_KEY, ANTHROPIC_API_KEY_2, _3, _4
        keys = []
        primary = os.environ.get("ANTHROPIC_API_KEY")
        if primary:
            keys.append(primary)
        for i in range(2, 5):
            k = os.environ.get(f"ANTHROPIC_API_KEY_{i}")
            if k:
                keys.append(k)

        if not keys:
            raise ValueError("No ANTHROPIC_API_KEY found in .env")

        last_error = None
        for idx, key in enumerate(keys, 1):
            try:
                client = anthropic.AsyncAnthropic(api_key=key)
                resp = await client.messages.create(
                    model=model_override or "claude-haiku-4-5-20251001",
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                _used_model = model_override or "claude-haiku-4-5-20251001"
                logger.warning(f"[Bedrock] Direct Anthropic key#{idx} model={_used_model} | tokens: in={resp.usage.input_tokens} out={resp.usage.output_tokens}")
                await _track_key_usage(idx, resp.usage.input_tokens, resp.usage.output_tokens, "bedrock")
                return resp.content[0].text
            except anthropic.AuthenticationError as e:
                logger.warning(f"[Bedrock] Anthropic key#{idx} auth failed (expired/invalid): {e}")
                last_error = e
                continue
            except anthropic.RateLimitError as e:
                logger.warning(f"[Bedrock] Anthropic key#{idx} rate limited / credit exhausted: {e}")
                last_error = e
                continue
            except anthropic.APIStatusError as e:
                if e.status_code in (400, 401, 403, 429):
                    logger.warning(f"[Bedrock] Anthropic key#{idx} status {e.status_code}: {e}")
                    last_error = e
                    continue
                raise

        # All keys exhausted — fall through to OpenRouter/Emergent
        logger.warning(f"[Bedrock] All {len(keys)} Anthropic keys exhausted ({last_error}), falling back to OpenRouter/Emergent")

    import httpx

    # ── 1. Try OpenRouter Free first ──
    openrouter_key = os.environ.get('OPENROUTER_API_KEY')
    if openrouter_key:
        from config import get_http_client
        shared_client = get_http_client()

        models = [
            os.environ.get('OPENROUTER_FREE_MODEL', 'nvidia/nemotron-3-super-120b-a12b:free'),
            os.environ.get('OPENROUTER_FALLBACK_MODEL', 'qwen/qwen3.6-plus-preview:free'),
        ]
        for model in models:
            try:
                body = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                }
                headers = {
                    "Authorization": f"Bearer {openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": os.environ.get("SITE_URL", "https://ventureshrd.com"),
                    "X-Title": "VHC Talent OS",
                }
                # Use global client if available, else create a temporary one
                if shared_client:
                    resp = await shared_client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body)
                else:
                    async with httpx.AsyncClient(timeout=90) as tmp_client:
                        resp = await tmp_client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body)
                if resp.status_code == 200:
                    content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    if content and content.strip():
                        logger.info(f"[Bedrock] OpenRouter success via {model}")
                        return content
                logger.warning(f"[Bedrock] OpenRouter {model} returned {resp.status_code}, trying next...")
            except Exception as e:
                logger.warning(f"[Bedrock] OpenRouter {model} failed: {e}")
                continue
        logger.warning("[Bedrock] All OpenRouter models failed — falling back to Claude")

    # ── 2. Claude via Emergent ──
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    api_key = os.environ.get('EMERGENT_LLM_KEY')
    if not api_key:
        raise ValueError("EMERGENT_LLM_KEY not set")

    claude_model = model_override or "claude-haiku-4-5"
    chat = LlmChat(
        api_key=api_key,
        session_id=f"extract-{uuid.uuid4().hex[:8]}",
        system_message=system_prompt,
    ).with_model("anthropic", claude_model).with_params(temperature=0)

    logger.info(f"[Bedrock] Using model: {claude_model}")
    msg = UserMessage(text=user_prompt)
    response = await chat.send_message(msg)
    return response


async def extract_contact_from_text(
    raw_text: str,
    recruiter_phone: str = None,
    recruiter_email: str = None,
) -> dict:
    """
    Use Claude Opus 4.6 to intelligently extract candidate contact info
    from raw Naukri page text, filtering out recruiter/system numbers.
    """
    system_prompt = """You are a data extraction specialist. You will receive raw text scraped from a Naukri.com candidate profile page. 

Your task: Extract the CANDIDATE's contact information — NOT the recruiter's, NOT Naukri's system numbers, NOT license/registration numbers.

Rules:
- Phone numbers: Indian mobile numbers are 10 digits, often prefixed with +91 or 91. Landlines are shorter. IGNORE any number that matches the recruiter's phone.
- Email: Extract the candidate's personal/work email. IGNORE naukri system emails or recruiter emails.
- Name: The candidate's full name as displayed on the profile.
- Current Designation: Their current job title/role (NOT the job they applied for).
- Current Employer: Their current company name.
- Location: Current city/location.
- Skills: Comma-separated key skills.
- Notice Period: If mentioned.
- Experience: Total years of experience.

Return ONLY a valid JSON object with these exact keys (use null for missing fields):
{
  "candidate_phone": "10-digit number or null",
  "candidate_email": "email or null", 
  "candidate_name": "full name or null",
  "current_designation": "job title or null",
  "current_employer": "company name or null",
  "location": "city or null",
  "skills": "comma-separated skills or null",
  "notice_period": "period or null",
  "experience_years": number or null,
  "confidence": "high/medium/low",
  "phone_source": "where you found the phone (e.g., 'contact section', 'CV text', 'header') or null"
}

Do NOT include any explanation — just the JSON."""

    user_msg = f"Recruiter phone to EXCLUDE: {recruiter_phone or 'unknown'}\nRecruiter email to EXCLUDE: {recruiter_email or 'unknown'}\n\n--- RAW PAGE TEXT ---\n{raw_text[:12000]}"

    try:
        response_text = await _call_claude(system_prompt, user_msg, max_tokens=1000)

        # Parse JSON from response
        clean = response_text.strip()
        if clean.startswith('```'):
            clean = clean.split('\n', 1)[1] if '\n' in clean else clean[3:]
            clean = clean.rsplit('```', 1)[0]
        result = json.loads(clean.strip())

        # Validate phone — keep only 10-digit numbers
        phone = result.get('candidate_phone')
        if phone:
            digits = ''.join(filter(str.isdigit, str(phone)))
            if len(digits) >= 10:
                result['candidate_phone'] = digits[-10:]
            else:
                result['candidate_phone'] = None

        logger.info(f"[Claude] Extracted contact: phone={result.get('candidate_phone')}, email={result.get('candidate_email')}, confidence={result.get('confidence')}")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"[Claude] JSON parse error: {e}")
        return {"error": "json_parse_failed"}
    except Exception as e:
        logger.error(f"[Claude] Error: {e}")
        return {"error": str(e)}


def _regex_backfill(result: dict, raw_text: str) -> dict:
    """Fill missing CTC, notice period, location, and experience from raw Naukri text.
    
    Naukri profile header typically appears as concatenated text like:
        {name}Save{years}y₹ 39 Lacs (expects: ₹ 55 Lacs)GuwahatiCurrent{Title}...3 Months
    This function uses regex to catch what the LLM missed.
    """
    import re

    # ── CTC (current) ──
    if not result.get('current_ctc'):
        # Pattern: "₹ 39 Lacs" or "₹ 12.5 Lacs" or "₹ 1.3 Cr" or "39 LPA" etc.
        ctc_patterns = [
            # ₹ XX Lacs (expects: ₹ YY Lacs) — Naukri header format
            re.compile(r'₹\s*([\d.]+)\s*(Lacs?|LPA|Lac)\s*\(expects', re.IGNORECASE),
            # ₹ XX Lacs — standalone
            re.compile(r'₹\s*([\d.]+)\s*(Lacs?|LPA|Lac)(?!\s*\))', re.IGNORECASE),
            # "Current CTC: XX Lacs" or "CTC: XX LPA"
            re.compile(r'(?:Current\s+)?CTC[:\s]+₹?\s*([\d.]+)\s*(Lacs?|LPA|Lac|Cr|Crore)', re.IGNORECASE),
            # "XX Lacs" near "CTC" or "Annual" or "Salary"
            re.compile(r'([\d.]+)\s*(Lacs?|LPA|Lac|Cr|Crore)\s*(?:per\s+annum|p\.?a\.?|annual)?', re.IGNORECASE),
        ]
        for pat in ctc_patterns:
            m = pat.search(raw_text)
            if m:
                val = float(m.group(1))
                unit = m.group(2).lower()
                if unit in ('cr', 'crore'):
                    result['current_ctc'] = int(val * 10000000)
                else:  # lacs, lpa, lac
                    result['current_ctc'] = int(val * 100000)
                logger.info(f"[Regex Backfill] CTC found: {m.group(0)} -> {result['current_ctc']}")
                break

    # ── CTC (expected) ──
    if not result.get('expected_ctc'):
        m = re.search(r'expects?[:\s]*₹?\s*([\d.]+)\s*(Lacs?|LPA|Lac|Cr|Crore)', raw_text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            unit = m.group(2).lower()
            if unit in ('cr', 'crore'):
                result['expected_ctc'] = int(val * 10000000)
            else:
                result['expected_ctc'] = int(val * 100000)
            logger.info(f"[Regex Backfill] Expected CTC: {m.group(0)} -> {result['expected_ctc']}")

    # ── Notice Period ──
    if not result.get('notice_period'):
        notice_patterns = [
            # "Notice Period: X Months" or "Notice: X Months" (explicit label - highest priority)
            re.compile(r'Notice\s*(?:Period)?[:\s]+(\d{1,2})\s*Months?', re.IGNORECASE),
            # Naukri header: year+notice concatenated like "'253 Months" → notice=3
            # The year is always 2 digits after apostrophe, so the notice is what follows
            re.compile(r"'\d{2}(\d{1,2})\s*Months?\s*(?:Highest|Pref|$)", re.IGNORECASE),
            # "Immediate" or "Immediately" or "Currently serving notice"
            re.compile(r'(Immediate(?:ly)?|Serving\s+Notice)', re.IGNORECASE),
        ]
        for pat in notice_patterns:
            m = pat.search(raw_text)
            if m:
                if m.group(1).lower().startswith('immedia'):
                    result['notice_period'] = 'Immediate'
                    result['notice_period_days'] = 0
                elif m.group(1).lower().startswith('serving'):
                    result['notice_period'] = 'Serving Notice'
                    result['is_serving_notice'] = True
                else:
                    months = int(m.group(1))
                    result['notice_period'] = f"{months} Month{'s' if months != 1 else ''}"
                    result['notice_period_days'] = months * 30
                logger.info(f"[Regex Backfill] Notice: {result['notice_period']}")
                break

    # ── Location ──
    if not result.get('location'):
        # In Naukri header, location appears between CTC and "Current" keyword
        # Pattern: "Lacs)Gurugram Current" or "LPA)Pune, India Current"
        m = re.search(r'(?:Lacs?|LPA|Cr)\)?\.?\s*([A-Z][a-z]+(?:[,\s]+[A-Z][a-z]+){0,2})\s*Current', raw_text)
        if m:
            loc = m.group(1).strip().rstrip(',')
            if len(loc) > 2 and loc.lower() not in ('the', 'and', 'for'):
                result['location'] = loc
                logger.info(f"[Regex Backfill] Location: {result['location']}")

        # Fallback: "Current Location: City" pattern
        if not result.get('location'):
            m = re.search(r'Current\s+Location[:\s]+([A-Za-z][A-Za-z\s,]+?)(?:\s*[\|\n•]|\s+Notice|\s+CTC)', raw_text, re.IGNORECASE)
            if m:
                result['location'] = m.group(1).strip().rstrip(',')
                logger.info(f"[Regex Backfill] Location (label): {result['location']}")

    # ── Experience Years ──
    if not result.get('experience_years'):
        # Pattern: "Save13y₹" or "13 Years 0 Month" or "Experience: 13 Years"
        patterns = [
            re.compile(r'Save\s*(\d+)\s*y\s*₹'),  # Naukri header: Save13y₹
            re.compile(r'Experience[:\s]+(\d+)\s+Years?\s+(\d+)\s+Months?', re.IGNORECASE),
            re.compile(r'(\d+)\s+Years?\s+(\d+)\s+Months?\s+(?:of\s+)?(?:exp|Exp)', re.IGNORECASE),
            re.compile(r'(\d+)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?experience', re.IGNORECASE),
        ]
        for pat in patterns:
            m = pat.search(raw_text)
            if m:
                years = int(m.group(1))
                months = int(m.group(2)) if m.lastindex >= 2 else 0
                result['experience_years'] = round(years + months / 12, 1)
                logger.info(f"[Regex Backfill] Experience: {result['experience_years']} years")
                break

    return result


# ═══════════════════════════════════════════════════════════════════
#  NEW: Text Pre-processor — structures raw Naukri text for LLM
# ═══════════════════════════════════════════════════════════════════

def _preprocess_naukri_text(raw_text: str) -> str:
    """Add section labels to raw Naukri text so Claude gets structured input.
    
    Raw Naukri text is a wall of concatenated HTML-to-text with no separators.
    This function identifies likely section boundaries and adds labels.
    """
    import re
    
    # The first ~600 chars usually contain the Naukri header (name, CTC, location, title)
    header_text = raw_text[:600]
    body_text = raw_text[600:]
    
    labeled_parts = []
    labeled_parts.append("[PROFILE HEADER — most authoritative for CTC, location, notice, current title]")
    labeled_parts.append(header_text.strip())
    labeled_parts.append("")
    
    # Try to identify CV/resume section
    cv_markers = ['CURRICULUM VITAE', 'RESUME', 'C U R R I C U L U M', 'PROFESSIONAL SUMMARY',
                  'CAREER OBJECTIVE', 'WORK EXPERIENCE', 'EMPLOYMENT HISTORY', 'PROFESSIONAL EXPERIENCE']
    
    cv_start = -1
    body_upper = body_text.upper()
    for marker in cv_markers:
        idx = body_upper.find(marker)
        if idx != -1 and (cv_start == -1 or idx < cv_start):
            cv_start = idx
    
    if cv_start != -1:
        profile_section = body_text[:cv_start].strip()
        cv_section = body_text[cv_start:].strip()
        
        if profile_section:
            labeled_parts.append("[NAUKRI PROFILE DETAILS — skills, preferences, personal details]")
            labeled_parts.append(profile_section)
            labeled_parts.append("")
        
        labeled_parts.append("[CANDIDATE CV/RESUME — full work history, education, certifications]")
        labeled_parts.append(cv_section)
    else:
        labeled_parts.append("[PROFILE + CV BODY]")
        labeled_parts.append(body_text.strip())
    
    return '\n'.join(labeled_parts)


# ═══════════════════════════════════════════════════════════════════
#  NEW: Post-extraction type validator — enforces schema on output
# ═══════════════════════════════════════════════════════════════════

def _validate_extraction(result: dict) -> dict:
    """Enforce types and sanity caps on all extracted fields.
    
    Claude sometimes returns strings for numeric fields, lists for string fields,
    or absurd values. This function normalizes everything.
    """
    # ── Numeric fields: must be int/float or null ──
    CTC_MAX = 200_000_000  # ₹20 Crore
    EXP_MAX = 50  # 50 years
    NOTICE_MAX = 365  # days
    
    for ctc_key in ('current_ctc', 'expected_ctc'):
        val = result.get(ctc_key)
        if val is not None:
            try:
                val = int(float(str(val).replace(',', '').replace('₹', '').strip()))
                result[ctc_key] = val if 0 < val <= CTC_MAX else None
            except (ValueError, TypeError):
                # String like "60 Lacs" — try to parse
                import re
                m = re.search(r'([\d.]+)\s*(lacs?|lpa|cr|crore)', str(val), re.IGNORECASE)
                if m:
                    num = float(m.group(1))
                    unit = m.group(2).lower()
                    parsed = int(num * 10000000) if unit in ('cr', 'crore') else int(num * 100000)
                    result[ctc_key] = parsed if 0 < parsed <= CTC_MAX else None
                else:
                    result[ctc_key] = None
    
    # Experience years
    exp = result.get('experience_years')
    if exp is not None:
        try:
            exp = float(str(exp))
            result['experience_years'] = round(exp, 1) if 0 <= exp <= EXP_MAX else None
        except (ValueError, TypeError):
            result['experience_years'] = None
    
    # Notice period days
    npd = result.get('notice_period_days')
    if npd is not None:
        try:
            npd = int(float(str(npd)))
            result['notice_period_days'] = npd if 0 <= npd <= NOTICE_MAX else None
        except (ValueError, TypeError):
            result['notice_period_days'] = None
    
    # ── String fields: must be string or null ──
    for str_key in ('candidate_name', 'candidate_phone', 'candidate_email', 'current_designation',
                     'current_employer', 'current_department', 'current_industry', 'location',
                     'headline', 'profile_summary', 'notice_period', 'date_of_birth',
                     'gender', 'marital_status', 'phone_source', 'confidence'):
        val = result.get(str_key)
        if val is not None and not isinstance(val, str):
            result[str_key] = str(val) if val else None
    
    # ── List fields: must be list or empty ──
    for list_key in ('key_skills', 'work_experience', 'education', 'certifications',
                      'languages', 'preferred_locations'):
        val = result.get(list_key)
        if val is not None and not isinstance(val, list):
            if isinstance(val, str):
                result[list_key] = [s.strip() for s in val.split(',') if s.strip()]
            else:
                result[list_key] = []
    
    # ── Boolean fields ──
    is_sn = result.get('is_serving_notice')
    if is_sn is not None and not isinstance(is_sn, bool):
        result['is_serving_notice'] = str(is_sn).lower() in ('true', '1', 'yes')
    
    return result


def _repair_truncated_json(text: str) -> dict:
    """Try to repair JSON that was truncated mid-stream (e.g., Claude hit max_tokens).
    
    Common truncation patterns:
    - Missing closing brackets: {"key": "val", "arr": [1, 2
    - Cut off mid-string: {"key": "some long tex
    - Missing closing brace: {"key": "val"
    """
    import re
    
    # Find the JSON start
    start = text.find('{')
    if start == -1:
        return None
    
    text = text[start:]
    
    # Strategy 1: Try as-is (maybe just trailing garbage)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Truncate at the last complete key-value pair
    # Find the last comma or colon that's followed by a complete value
    # Then close all open brackets/braces
    
    # Remove any trailing incomplete string value
    text = re.sub(r',\s*"[^"]*":\s*"[^"]*$', '', text)  # incomplete string value
    text = re.sub(r',\s*"[^"]*":\s*\[[^\]]*$', '', text)  # incomplete array
    text = re.sub(r',\s*"[^"]*":\s*\{[^\}]*$', '', text)  # incomplete object
    text = re.sub(r',\s*"[^"]*":\s*$', '', text)  # key with no value
    text = re.sub(r',\s*"[^"]*$', '', text)  # incomplete key
    text = re.sub(r',\s*$', '', text)  # trailing comma
    
    # Count open brackets and close them
    open_braces = text.count('{') - text.count('}')
    open_brackets = text.count('[') - text.count(']')
    
    text += ']' * max(0, open_brackets)
    text += '}' * max(0, open_braces)
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


async def extract_full_profile(
    raw_text: str,
    recruiter_phone: str = None,
    recruiter_email: str = None,
    model_override: str = None,
    use_direct_anthropic: bool = False,
) -> dict:
    """
    Regex-First extraction with Claude gap-fill.
    
    Architecture:
    1. Regex extracts everything deterministically (CTC, notice, location, experience, etc.)
    2. Pre-process text with section labels for Claude
    3. Claude receives regex results + labeled text → fills ONLY the gaps
    4. Merge (regex wins for numeric fields, Claude wins for text fields)
    5. Post-extraction type validation enforces schema
    
    This gives 100% consistency on regex-extractable fields while using Claude
    only for complex text fields (work history, skills, summary).
    """
    # ── Step 1: Regex extraction (deterministic, zero variance) ──
    regex_result = _regex_backfill({}, raw_text)
    
    regex_filled = {k: v for k, v in regex_result.items() if v is not None}
    logger.info(f"[Extract] Regex pre-fill: {list(regex_filled.keys())}")
    
    # ── Step 2: Pre-process text with section labels ──
    processed_text = _preprocess_naukri_text(raw_text)
    
    # ── Step 3: Build focused Claude prompt ──
    # Tell Claude what we already know so it focuses on gaps
    pre_filled_summary = ""
    if regex_filled:
        parts = []
        for k, v in regex_filled.items():
            parts.append(f"  - {k}: {v}")
        pre_filled_summary = "ALREADY EXTRACTED (verify but do NOT override unless clearly wrong):\n" + "\n".join(parts)
    
    system_prompt = """You are an expert recruitment data extraction system. You will receive text scraped from a Naukri.com candidate profile page which may include embedded CV/resume text.

IMPORTANT: Some fields have ALREADY been extracted by a deterministic parser. They are listed under "ALREADY EXTRACTED". Your job:
1. VERIFY the pre-extracted values — only override if they are CLEARLY wrong based on the text.
2. FILL all remaining null/missing fields from the text.
3. Focus especially on: work_experience, education, key_skills, profile_summary, certifications — these need YOUR intelligence.

CRITICAL RULES:
- The text has section labels like [PROFILE HEADER], [CANDIDATE CV/RESUME]. Use them to locate data.
- PROFILE HEADER is the MOST CURRENT source for CTC, location, notice, current title.
- CTC: "1.3 Cr" = 13000000, "60 Lacs" = 6000000, "35 LPA" = 3500000. Convert to integer INR.
- Phone: 10-digit Indian mobile starting with 6-9. IGNORE recruiter's phone.
- Email: Candidate's personal/work email only. IGNORE @naukri.com, @vhc.in, noreply@.
- Work history: Capture EVERY role with FULL descriptions, not just current.
- Experience: Convert to decimal years (5 years 6 months = 5.5).

Return ONLY a valid JSON object with these exact keys (use null for missing):
{
  "candidate_phone": "10-digit number or null",
  "candidate_email": "email or null",
  "candidate_name": "full name or null",
  "current_designation": "current job title or null",
  "current_employer": "current company or null",
  "current_department": "department or null",
  "current_industry": "industry or null",
  "location": "current city or null",
  "headline": "resume headline or null",
  "profile_summary": "full profile summary text or null",
  "current_ctc": integer in INR or null,
  "expected_ctc": integer in INR or null,
  "notice_period": "e.g. 1 Month, 2 Months, Immediate, or null",
  "notice_period_days": integer or null,
  "is_serving_notice": false,
  "experience_years": decimal number or null,
  "key_skills": ["skill1", "skill2"],
  "work_experience": [
    {
      "company": "company name",
      "designation": "job title",
      "from_date": "start date or null",
      "to_date": "end date or null",
      "is_current": true/false,
      "description": "FULL role description with responsibilities, achievements, technologies used"
    }
  ],
  "education": [
    {"degree": "degree", "institution": "college/university", "year": "year or null", "specialization": "field or null"}
  ],
  "certifications": ["cert1", "cert2"],
  "languages": ["language1", "language2"],
  "preferred_locations": ["city1", "city2"],
  "date_of_birth": "DOB or null",
  "gender": "Male/Female/Other or null",
  "marital_status": "status or null",
  "confidence": "high/medium/low",
  "phone_source": "where phone was found or null"
}

Do NOT include any explanation — just the JSON."""

    user_msg_parts = [
        f"Recruiter phone to EXCLUDE: {recruiter_phone or 'unknown'}",
        f"Recruiter email to EXCLUDE: {recruiter_email or 'unknown'}",
    ]
    if pre_filled_summary:
        user_msg_parts.append(f"\n{pre_filled_summary}")
    user_msg_parts.append(f"\n--- RAW PAGE + CV TEXT ---\n{processed_text[:14000]}")
    user_msg = "\n".join(user_msg_parts)

    try:
        response_text = await _call_claude(system_prompt, user_msg, max_tokens=4096, model_override=model_override, use_direct_anthropic=use_direct_anthropic)

        clean = response_text.strip()
        if clean.startswith('```'):
            clean = clean.split('\n', 1)[1] if '\n' in clean else clean[3:]
            clean = clean.rsplit('```', 1)[0]
        
        # ── JSON repair for truncated responses ──
        clean = clean.strip()
        try:
            result = json.loads(clean)
        except json.JSONDecodeError:
            # Try to repair truncated JSON (Claude may have hit max_tokens)
            repaired = _repair_truncated_json(clean)
            if repaired:
                result = repaired
                logger.warning("[Claude] Repaired truncated JSON successfully")
            else:
                logger.error("[Claude] JSON parse failed even after repair attempt")
                return _validate_extraction(regex_result)

        # Validate phone
        phone = result.get('candidate_phone')
        if phone:
            digits = ''.join(filter(str.isdigit, str(phone)))
            if len(digits) >= 10:
                result['candidate_phone'] = digits[-10:]
            else:
                result['candidate_phone'] = None

        # ── Step 4: Merge — regex wins for numeric fields (deterministic) ──
        for rk, rv in regex_filled.items():
            if rk in ('current_ctc', 'expected_ctc', 'experience_years', 'notice_period_days'):
                # Regex is deterministic for numeric fields — prefer it
                result[rk] = rv
            elif not result.get(rk):
                # Claude missed it but regex got it — use regex
                result[rk] = rv

        # ── Step 5: Type validation ──
        result = _validate_extraction(result)

        logger.info(
            f"[Claude] Full extraction: phone={result.get('candidate_phone')}, "
            f"email={result.get('candidate_email')}, ctc={result.get('current_ctc')}, "
            f"notice={result.get('notice_period')}, location={result.get('location')}, "
            f"skills={len(result.get('key_skills') or [])}, "
            f"confidence={result.get('confidence')}"
        )
        return result

    except json.JSONDecodeError as e:
        logger.error(f"[Claude] Full profile JSON parse error: {e}")
        # Fall back to regex-only result with validation
        return _validate_extraction(regex_result)
    except Exception as e:
        logger.error(f"[Claude] Full profile extraction error: {e}")
        # Fall back to regex-only result with validation
        return _validate_extraction(regex_result)


async def enrich_candidate_from_cv_text(cv_text: str) -> dict:
    """
    Use Claude Opus 4.6 to extract structured candidate data from CV/resume text.
    """
    system_prompt = """You are a resume/CV parsing specialist. Extract structured candidate information from the CV text below.

Return ONLY a valid JSON object:
{
  "name": "full name",
  "email": "email or null",
  "phone": "10-digit phone or null",
  "current_designation": "current job title or null",
  "current_employer": "current company or null",
  "location": "city or null",
  "experience_years": number or null,
  "skills": ["skill1", "skill2"],
  "education": [{"degree": "...", "institution": "...", "year": "..."}],
  "experience": [{"title": "...", "company": "...", "duration": "...", "location": "..."}],
  "summary": "2-3 sentence professional summary or null",
  "certifications": ["cert1", "cert2"],
  "notice_period": "period or null",
  "languages": ["lang1", "lang2"]
}

Do NOT include any explanation — just the JSON."""

    try:
        response_text = await _call_claude(system_prompt, cv_text[:15000], max_tokens=2000)

        clean = response_text.strip()
        if clean.startswith('```'):
            clean = clean.split('\n', 1)[1] if '\n' in clean else clean[3:]
            clean = clean.rsplit('```', 1)[0]
        result = json.loads(clean.strip())

        logger.info(f"[Claude] CV enrichment: name={result.get('name')}, skills={len(result.get('skills', []))}")
        return result

    except json.JSONDecodeError:
        logger.error("[Claude] CV JSON parse error")
        return {"error": "json_parse_failed"}
    except Exception as e:
        logger.error(f"[Claude] CV enrichment error: {e}")
        return {"error": str(e)}



async def extract_phone_and_work_experience_only(raw_text: str, candidate_name: str = None) -> dict:
    """
    TARGETED extraction - Claude is ONLY used for:
    1. Phone number (Naukri masks it in DOM)
    2. Structured work experience with timeline and descriptions
    
    This reduces token usage from ~11,000 to ~3,000 per profile (65% savings).
    
    Args:
        raw_text: Raw profile text from Naukri
        candidate_name: Optional name for validation
    
    Returns:
        {
            "phone": "9876543210",
            "work_experience": [
                {
                    "company": "Company Name",
                    "designation": "Job Title",
                    "from_date": "Apr 2020",
                    "to_date": "Present",
                    "duration": "3y 6m",
                    "is_current": true,
                    "description": "Detailed job responsibilities..."
                }
            ]
        }
    """
    system_prompt = """You are a data extraction specialist. Extract ONLY phone number and work experience from Naukri profiles.
Be precise and structured. Return valid JSON only."""

    user_prompt = f"""Extract from this Naukri profile:

{raw_text[:8000]}

Return JSON with this EXACT structure:
{{
  "phone": "10-digit number or null",
  "work_experience": [
    {{
      "company": "company name",
      "designation": "job title",  
      "from_date": "MMM YYYY",
      "to_date": "MMM YYYY or Present",
      "duration": "Xy Ym format",
      "is_current": true/false,
      "description": "detailed responsibilities and achievements"
    }}
  ]
}}

Rules:
1. Phone: Extract the 10-digit mobile number (usually starts with 7/8/9)
2. Work Experience: List ALL jobs in reverse chronological order (most recent first)
3. For each job:
   - Extract company name, designation, dates, duration
   - Write detailed description (3-5 sentences) covering responsibilities, achievements, technologies
   - is_current: true ONLY for most recent job if "Present" or "Till date"
4. If phone not found: return null
5. If work experience section empty: return empty array []

Return ONLY the JSON, no explanation."""

    try:
        response_text = await _call_claude(
            system_prompt, 
            user_prompt, 
            max_tokens=3000,  # Enough for phone + 3-4 detailed work experiences
            use_direct_anthropic=True  # Use direct Anthropic for reliability
        )

        # Clean response
        clean = response_text.strip()
        if clean.startswith('```'):
            clean = clean.split('\n', 1)[1] if '\n' in clean else clean[3:]
            clean = clean.rsplit('```', 1)[0]
        
        result = json.loads(clean.strip())
        
        # Validation
        if "phone" not in result:
            result["phone"] = None
        if "work_experience" not in result:
            result["work_experience"] = []
        
        logger.info(f"[Targeted Extract] Phone: {'found' if result.get('phone') else 'not found'}, "
                   f"Work Exp: {len(result.get('work_experience', []))} entries, "
                   f"Tokens saved: ~8000 (full) → ~3000 (targeted)")
        
        return result

    except json.JSONDecodeError as e:
        logger.error(f"[Targeted Extract] JSON parse error: {e}")
        return {"phone": None, "work_experience": [], "error": "json_parse_failed"}
    except Exception as e:
        logger.error(f"[Targeted Extract] Error: {e}")
        return {"phone": None, "work_experience": [], "error": str(e)}
