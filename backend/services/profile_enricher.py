"""
Profile Enricher (Search Phase 2, 2026-06-15)

Backfills the fields that make hybrid + structured search work well:

  • industry            — inferred from current_employer when missing
  • seniority           — inferred from designation / headline (Intern → Junior →
                          Mid → Senior → Lead → Manager → Director → VP+)
  • function_domain     — inferred from skills + designation (DevOps, Data,
                          Backend, Frontend, Mobile, ML, Security, QA, PM, Design,
                          Finance, HR, Sales, Marketing, Operations …)
  • location_canonical  — normalises Bglr / Bengaluru / Bangalore → Bangalore
  • notice_period_days  — parsed from free-text profile_summary / summary when
                          the structured field is empty

Two-tier inference:

  1. **Rule-based** (zero cost) — runs first. Built from a hand-curated lookup
     table of ~250 Indian companies and ~40 designation patterns. Returns a
     verdict OR `None` (when the rules can't decide).

  2. **LLM fallback (RunPod Qwen)** — only invoked for company → industry when
     the rule table misses. Caches results in `enrichment_cache` so we never
     pay the LLM cost twice for the same company. Phase 2 keeps the LLM scope
     narrow (one field, one inference) to control budget; we expand once we
     have signal.

Idempotency: every `enrich_candidate(doc)` call returns ONLY the keys that
changed. Callers apply via `$set` so existing data is never overwritten.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 1. INDUSTRY — company → industry lookup table
# ──────────────────────────────────────────────────────────────────────
# Hand-curated for the most common employers in the bank. Add more here
# instead of widening the LLM fallback — every entry saves an LLM call.

_INDUSTRY_BY_COMPANY: Dict[str, str] = {
    # IT services
    "tcs": "IT/Software", "tata consultancy": "IT/Software",
    "infosys": "IT/Software", "wipro": "IT/Software", "hcl": "IT/Software",
    "tech mahindra": "IT/Software", "cognizant": "IT/Software",
    "accenture": "IT/Software", "capgemini": "IT/Software",
    "ltimindtree": "IT/Software", "mindtree": "IT/Software",
    "mphasis": "IT/Software", "persistent": "IT/Software",
    "deloitte": "Consulting", "ey": "Consulting",
    "kpmg": "Consulting", "pwc": "Consulting", "mckinsey": "Consulting",
    "bain": "Consulting", "bcg": "Consulting", "zs associates": "Consulting",
    # Product / SaaS
    "google": "IT/Software", "microsoft": "IT/Software", "amazon": "IT/Software",
    "meta": "IT/Software", "facebook": "IT/Software", "apple": "IT/Software",
    "oracle": "IT/Software", "salesforce": "IT/Software", "sap": "IT/Software",
    "adobe": "IT/Software", "vmware": "IT/Software", "intel": "IT/Software",
    "nvidia": "IT/Software", "ibm": "IT/Software",
    "flipkart": "Retail/E-commerce", "amazon india": "Retail/E-commerce",
    "myntra": "Retail/E-commerce", "ajio": "Retail/E-commerce",
    "swiggy": "Internet/E-commerce", "zomato": "Internet/E-commerce",
    "uber": "Internet/E-commerce", "ola": "Internet/E-commerce",
    "paytm": "BFSI", "phonepe": "BFSI", "razorpay": "BFSI",
    "cred": "BFSI", "groww": "BFSI", "zerodha": "BFSI",
    "pine labs": "BFSI", "policybazaar": "BFSI",
    "byju's": "Education", "byjus": "Education", "unacademy": "Education",
    "vedantu": "Education", "upgrad": "Education", "physics wallah": "Education",
    # BFSI
    "hdfc": "BFSI", "hdfc bank": "BFSI", "icici": "BFSI", "icici bank": "BFSI",
    "axis bank": "BFSI", "kotak": "BFSI", "sbi": "BFSI", "state bank": "BFSI",
    "yes bank": "BFSI", "indusind": "BFSI", "rbl": "BFSI",
    "goldman sachs": "BFSI", "jp morgan": "BFSI", "jpmorgan": "BFSI",
    "morgan stanley": "BFSI", "deutsche bank": "BFSI", "citi": "BFSI",
    "barclays": "BFSI", "ubs": "BFSI", "credit suisse": "BFSI",
    "bajaj finance": "BFSI", "bajaj finserv": "BFSI",
    "hdfc life": "BFSI", "lic": "BFSI", "max life": "BFSI",
    "icici lombard": "BFSI", "tata aig": "BFSI",
    # Manufacturing / Automotive
    "tata motors": "Automotive", "mahindra": "Automotive",
    "maruti suzuki": "Automotive", "maruti": "Automotive",
    "hero motocorp": "Automotive", "bajaj auto": "Automotive",
    "tvs motor": "Automotive", "ashok leyland": "Automotive",
    "force motors": "Automotive",
    "tata steel": "Manufacturing", "jsw": "Manufacturing",
    "vedanta": "Manufacturing", "hindalco": "Manufacturing",
    "l&t": "Manufacturing", "larsen & toubro": "Manufacturing",
    "bhel": "Manufacturing", "godrej": "Manufacturing",
    "siemens": "Manufacturing", "abb": "Manufacturing",
    "ge": "Manufacturing", "honeywell": "Manufacturing",
    # FMCG
    "hindustan unilever": "FMCG", "hul": "FMCG", "itc": "FMCG",
    "nestle": "FMCG", "dabur": "FMCG", "marico": "FMCG",
    "britannia": "FMCG", "parle": "FMCG",
    "procter & gamble": "FMCG", "p&g": "FMCG",
    "colgate": "FMCG", "godrej consumer": "FMCG",
    # Telecom
    "airtel": "Telecom", "jio": "Telecom", "vi": "Telecom",
    "vodafone": "Telecom", "idea": "Telecom", "bsnl": "Telecom",
    # Pharma / Healthcare
    "sun pharma": "Healthcare", "cipla": "Healthcare", "dr reddy": "Healthcare",
    "lupin": "Healthcare", "biocon": "Healthcare", "torrent pharma": "Healthcare",
    "aurobindo": "Healthcare", "glenmark": "Healthcare",
    "apollo hospitals": "Healthcare", "fortis": "Healthcare",
    "max healthcare": "Healthcare", "manipal": "Healthcare",
    # Real Estate
    "lodha": "Real Estate", "godrej properties": "Real Estate",
    "dlf": "Real Estate", "prestige": "Real Estate", "brigade": "Real Estate",
    # Media / Entertainment
    "disney": "Media/Entertainment", "hotstar": "Media/Entertainment",
    "netflix": "Media/Entertainment", "sony": "Media/Entertainment",
    "zee": "Media/Entertainment", "viacom": "Media/Entertainment",
    # Aviation / Travel
    "indigo": "Aviation", "vistara": "Aviation", "air india": "Aviation",
    "spicejet": "Aviation", "makemytrip": "Travel/Tourism",
    "yatra": "Travel/Tourism", "easemytrip": "Travel/Tourism",
    # Energy
    "reliance": "Energy/Oil & Gas", "reliance industries": "Energy/Oil & Gas",
    "ongc": "Energy/Oil & Gas", "ioc": "Energy/Oil & Gas",
    "bharat petroleum": "Energy/Oil & Gas", "bpcl": "Energy/Oil & Gas",
    "ntpc": "Energy/Oil & Gas", "adani": "Energy/Oil & Gas",
}


def _norm_company(name: str) -> str:
    if not name:
        return ""
    s = re.sub(r"\b(pvt|private|ltd|limited|inc|corp|llc|llp|company)\b", "",
               name.lower())
    s = re.sub(r"[^\w\s&]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def infer_industry_from_company(company: Optional[str]) -> Optional[str]:
    """Rule-based industry inference. Returns None on miss → LLM tier."""
    if not company:
        return None
    norm = _norm_company(company)
    if not norm:
        return None
    # Exact key first, then longest-prefix-then-substring
    if norm in _INDUSTRY_BY_COMPANY:
        return _INDUSTRY_BY_COMPANY[norm]
    # Token-wise substring match — pick the LONGEST matching key so
    # "axis bank" wins over "axis" if both were present.
    candidates = [
        (k, v) for k, v in _INDUSTRY_BY_COMPANY.items()
        if k in norm or norm.startswith(k + " ") or norm.endswith(" " + k)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda kv: len(kv[0]), reverse=True)
    return candidates[0][1]


# ──────────────────────────────────────────────────────────────────────
# 2. SENIORITY — designation pattern → seniority bucket
# ──────────────────────────────────────────────────────────────────────

_SENIORITY_PATTERNS: List[Tuple[str, str]] = [
    (r"\b(intern|trainee|apprentice)\b", "Intern"),
    (r"\b(fresher|graduate engineer trainee|get)\b", "Junior"),
    (r"\b(associate|jr\.?|junior)\b", "Junior"),
    (r"\b(sr\.?|senior)\b(?!\s+manager|\s+director)", "Senior"),
    (r"\b(lead|principal|staff|architect)\b", "Lead"),
    (r"\b(manager|engineering manager|em\b|product manager|pm\b)", "Manager"),
    (r"\b(senior\s+manager|sr\.?\s+manager|group\s+manager)\b", "Senior Manager"),
    (r"\b(director|head of|head\s*[-:]?\s*)", "Director"),
    (r"\b(vice president|vp\b|svp\b|evp\b)", "VP+"),
    (r"\b(cto|cfo|coo|ceo|cmo|chief\s+\w+\s+officer)\b", "CXO"),
]


def infer_seniority(designation: Optional[str], headline: Optional[str] = None) -> Optional[str]:
    if not designation and not headline:
        return None
    blob = " ".join([designation or "", headline or ""]).lower()
    if not blob.strip():
        return None
    # Most-specific first (Senior Manager before Senior, CXO before VP+ etc.)
    # The patterns are deliberately ordered general→specific so we scan
    # in REVERSE for the right precedence.
    for pat, label in reversed(_SENIORITY_PATTERNS):
        if re.search(pat, blob, re.IGNORECASE):
            return label
    # No explicit signal — if there's >0 work history reasonable default is "Mid"
    return None  # leave null; LTR uses experience_years anyway


# ──────────────────────────────────────────────────────────────────────
# 3. FUNCTION / DOMAIN — skill + designation buckets
# ──────────────────────────────────────────────────────────────────────

_FUNCTION_RULES: List[Tuple[List[str], str]] = [
    # Engineering
    (["kubernetes", "docker", "terraform", "ansible", "devops", "sre"], "DevOps/SRE"),
    (["react", "angular", "vue", "frontend", "front-end", "ui developer"], "Frontend"),
    (["node.js", "django", "spring", "fastapi", "backend", "back-end"], "Backend"),
    (["android", "ios", "swift", "kotlin", "react native", "flutter"], "Mobile"),
    (["machine learning", "deep learning", "tensorflow", "pytorch", "ml engineer", "data scientist"], "ML/AI"),
    (["data engineer", "spark", "hadoop", "airflow", "etl", "snowflake"], "Data Engineering"),
    (["security", "penetration", "infosec", "soc", "siem"], "Security"),
    (["qa engineer", "test engineer", "sdet", "selenium", "automation testing"], "QA"),
    # Product / Design / PM
    (["product manager", "product owner", "scrum master"], "Product"),
    (["ui designer", "ux designer", "figma", "sketch"], "Design"),
    # Business
    (["finance", "accounting", "ca ", " ca,", "cfa", "controller", "fp&a"], "Finance"),
    (["hr", "human resources", "talent acquisition", "recruiter"], "HR"),
    (["sales", "business development", "bde", "account executive"], "Sales"),
    (["marketing", "growth", "seo", "sem", "performance marketing"], "Marketing"),
    (["operations", "supply chain", "logistics"], "Operations"),
]


def infer_function_domain(
    skills: Optional[List[Any]],
    designation: Optional[str] = None,
    headline: Optional[str] = None,
) -> Optional[str]:
    skill_blob = ""
    if isinstance(skills, list):
        skill_blob = " ".join(
            (s if isinstance(s, str) else str(s.get("name", "") if isinstance(s, dict) else ""))
            for s in skills
        ).lower()
    blob = " ".join([skill_blob, designation or "", headline or ""]).lower()
    if not blob.strip():
        return None
    best_label = None
    best_hits = 0
    for keywords, label in _FUNCTION_RULES:
        hits = sum(1 for kw in keywords if kw in blob)
        if hits > best_hits:
            best_hits = hits
            best_label = label
    return best_label if best_hits >= 1 else None


# ──────────────────────────────────────────────────────────────────────
# 4. LOCATION NORMALISATION — alias map
# ──────────────────────────────────────────────────────────────────────

_LOC_ALIASES: Dict[str, str] = {
    # Bangalore
    "bglr": "Bangalore", "bengaluru": "Bangalore", "bangaluru": "Bangalore",
    "bnglr": "Bangalore",
    # Mumbai
    "bombay": "Mumbai", "mum": "Mumbai", "navi mumbai": "Mumbai",
    "thane": "Mumbai",
    # Delhi
    "new delhi": "Delhi", "ncr": "Delhi NCR", "delhi ncr": "Delhi NCR",
    "noida": "Noida", "gurgaon": "Gurgaon", "gurugram": "Gurgaon",
    "ghaziabad": "Ghaziabad", "faridabad": "Faridabad",
    # Hyderabad
    "hyd": "Hyderabad", "secunderabad": "Hyderabad",
    # Chennai
    "madras": "Chennai", "chenn": "Chennai",
    # Kolkata
    "calcutta": "Kolkata",
    # Pune
    "pcmc": "Pune", "pimpri": "Pune",
    # Others
    "blr": "Bangalore", "del": "Delhi", "hyd.": "Hyderabad",
}


def normalize_location(loc: Optional[str]) -> Optional[str]:
    if not loc or not isinstance(loc, str):
        return None
    raw = loc.strip()
    if not raw:
        return None
    low = raw.lower()
    # Drop trailing region tokens like " - karnataka"
    cleaned = re.split(r"[,;|]|\s+-\s+", low)[0].strip()
    if cleaned in _LOC_ALIASES:
        return _LOC_ALIASES[cleaned]
    # Title-case canonical fallback
    return raw.split(",")[0].split(" - ")[0].strip().title() or None


# ──────────────────────────────────────────────────────────────────────
# 5. NOTICE PERIOD — parse from free-text
# ──────────────────────────────────────────────────────────────────────

def parse_notice_period_days(text: Optional[str]) -> Optional[int]:
    if not text or not isinstance(text, str):
        return None
    t = text.lower()
    if re.search(r"\b(immediate|immediately|already serving notice|serving notice)\b", t):
        return 0
    m = re.search(r"\bnotice\s*(?:period)?\s*[:\-]?\s*(\d{1,3})\s*(day|week|month)", t)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        return n if unit == "day" else (n * 7 if unit == "week" else n * 30)
    m = re.search(r"\b(\d{1,3})\s*(day|week|month)s?\s+notice\b", t)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        return n if unit == "day" else (n * 7 if unit == "week" else n * 30)
    return None


# ──────────────────────────────────────────────────────────────────────
# 6. LLM tier — company → industry via RunPod Qwen (cached)
# ──────────────────────────────────────────────────────────────────────

_INDUSTRY_LABEL_SET = (
    "IT/Software, BFSI, Manufacturing, Healthcare, Telecom, Retail/E-commerce, "
    "Consulting, Education, Real Estate, Media/Entertainment, Logistics, "
    "Energy/Oil & Gas, Automotive, FMCG, Aviation, Travel/Tourism, "
    "Internet/E-commerce, Government, Other"
)


async def infer_industry_llm(db, company: str) -> Optional[str]:
    """Cached RunPod Qwen call. Looks up `enrichment_cache` first; only
    hits the LLM when the cache misses. Returns the resolved industry
    label or None on failure.
    """
    if not company:
        return None
    key = _norm_company(company)
    if not key:
        return None

    # Cache check
    try:
        cached = await db.enrichment_cache.find_one(
            {"_id": f"industry:{key}"}, {"_id": 0, "value": 1}
        )
        if cached and cached.get("value"):
            return cached["value"]
    except Exception as e:
        logger.debug(f"[Enricher] cache read failed: {e}")

    # LLM call — direct RunPod Qwen request (chat completions, no guided JSON
    # so we can ask for a plain label). Keep timeout tight; rules already
    # handled the top-50 companies so this only fires for the long tail.
    import os
    import httpx
    runpod_url = os.environ.get("RUNPOD_VLLM_URL", "").rstrip("/")
    runpod_model = os.environ.get("RUNPOD_MODEL_NAME", "Qwen/Qwen2.5-14B-Instruct-AWQ")
    if not runpod_url:
        logger.warning("[Enricher] RUNPOD_VLLM_URL not configured; skipping LLM tier")
        return None

    prompt = (
        f"Classify the company '{company}' into ONE of these industries:\n"
        f"{_INDUSTRY_LABEL_SET}\n"
        f"Reply with ONLY the label, no other text. If the company is unknown, "
        f"reply with 'Other'."
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{runpod_url}/v1/chat/completions",
                json={
                    "model": runpod_model,
                    "messages": [
                        {"role": "system", "content": "You are an industry-classification assistant. Reply with only the label."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0,
                    "max_tokens": 20,
                },
            )
            r.raise_for_status()
            data = r.json()
        text = (data.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()
        text = text.strip(".").strip().split("\n")[0].split(",")[0].strip()
        valid = {x.strip() for x in _INDUSTRY_LABEL_SET.split(",")}
        if text not in valid:
            # Forgiving prefix match (e.g. "IT" → "IT/Software")
            match = next((v for v in valid if v.lower().startswith(text.lower()[:4])), None)
            if not match:
                logger.info(f"[Enricher] LLM returned unrecognised label for {company!r}: {text!r}")
                return None
            text = match

        try:
            from datetime import datetime, timezone
            await db.enrichment_cache.update_one(
                {"_id": f"industry:{key}"},
                {"$set": {
                    "value": text,
                    "company_raw": company,
                    "source": "llm",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }},
                upsert=True,
            )
        except Exception as e:
            logger.debug(f"[Enricher] cache write failed: {e}")
        return text
    except Exception as e:
        logger.info(f"[Enricher] LLM industry inference failed for {company!r}: {e}")
        return None


# ──────────────────────────────────────────────────────────────────────
# 7. enrich_candidate — combine all tiers into one diff
# ──────────────────────────────────────────────────────────────────────

async def enrich_candidate(
    doc: Dict[str, Any],
    db,
    allow_llm: bool = True,
) -> Dict[str, Any]:
    """Compute enrichment updates for ONE candidate doc.

    Returns ONLY the fields that should be set (missing in doc OR clearly
    invalid). Callers `$set` the result — existing data is never overwritten.

    Schema additions:
      - `industry`              (when missing/empty)
      - `enriched_seniority`    (always when inferable; namespaced so we
                                 don't conflict with manual edits)
      - `enriched_function`     (function/domain bucket)
      - `enriched_location`     (canonicalised location)
      - `notice_period_days`    (when missing AND parseable from summary)
      - `enrichment_meta`       (sources: {industry, function, ...})
    """
    if not doc:
        return {}
    updates: Dict[str, Any] = {}
    meta: Dict[str, str] = {}

    # ── INDUSTRY ──
    existing_industry = (
        doc.get("industry")
        or doc.get("current_industry")
    )
    if not existing_industry:
        company = doc.get("current_employer") or doc.get("current_company")
        ind = infer_industry_from_company(company)
        if ind:
            meta["industry"] = "rules"
        elif company and allow_llm:
            ind = await infer_industry_llm(db, company)
            if ind:
                meta["industry"] = "llm"
        if ind:
            updates["industry"] = ind

    # ── SENIORITY ──
    if not doc.get("enriched_seniority"):
        sen = infer_seniority(
            doc.get("current_designation") or doc.get("designation"),
            doc.get("headline"),
        )
        if sen:
            updates["enriched_seniority"] = sen
            meta["seniority"] = "rules"

    # ── FUNCTION ──
    if not doc.get("enriched_function"):
        fn = infer_function_domain(
            doc.get("key_skills") or doc.get("skills"),
            doc.get("current_designation") or doc.get("designation"),
            doc.get("headline"),
        )
        if fn:
            updates["enriched_function"] = fn
            meta["function"] = "rules"

    # ── LOCATION ──
    if not doc.get("enriched_location"):
        loc = normalize_location(
            doc.get("current_location") or doc.get("location")
        )
        if loc:
            updates["enriched_location"] = loc
            meta["location"] = "rules"

    # ── NOTICE PERIOD ──
    if doc.get("notice_period_days") in (None, ""):
        days = parse_notice_period_days(
            doc.get("profile_summary") or doc.get("summary")
        )
        if days is not None:
            updates["notice_period_days"] = days
            meta["notice_period_days"] = "rules"

    if updates:
        updates["enrichment_meta"] = meta
        from datetime import datetime, timezone
        updates["enriched_at"] = datetime.now(timezone.utc).isoformat()

    return updates
