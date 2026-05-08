"""
spaCy NER + Rule-based extraction layer for Naukri profiles.
Sits between Regex and Claude Haiku — extracts skills, education,
work history, and other fuzzy fields at ZERO API cost.

Returns extracted data + confidence score (0-1).
If confidence >= threshold, Claude call is SKIPPED entirely.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Lazy-load spaCy model (loaded once, reused)
_nlp = None

def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("en_core_web_sm")
        logger.info("[SpaCy] Model en_core_web_sm loaded")
    return _nlp


# ── Common skill keywords for recruitment ──
TECH_SKILLS = {
    "python", "java", "javascript", "react", "angular", "vue", "node", "nodejs",
    "sql", "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform",
    "machine learning", "deep learning", "nlp", "data science", "ai",
    "html", "css", "typescript", "golang", "rust", "c++", "c#", ".net",
    "spring", "django", "flask", "fastapi", "express", "rails",
    "git", "jenkins", "ci/cd", "devops", "agile", "scrum",
    "tableau", "power bi", "excel", "sap", "salesforce", "oracle",
    "figma", "photoshop", "illustrator", "sketch",
    "ios", "android", "swift", "kotlin", "flutter", "react native",
    "blockchain", "solidity", "web3",
    "hadoop", "spark", "kafka", "airflow", "databricks",
    "linux", "unix", "shell scripting", "bash",
    "rest", "graphql", "microservices", "api",
    "jira", "confluence", "slack",
    "communication", "leadership", "management", "team management",
    "project management", "pmp", "prince2",
    "accounts", "finance", "accounting", "tally", "gst", "taxation",
    "hr", "recruitment", "talent acquisition", "payroll",
    "marketing", "digital marketing", "seo", "sem", "social media",
    "sales", "business development", "crm", "b2b", "b2c",
    "supply chain", "logistics", "procurement", "vendor management",
    "quality assurance", "qa", "testing", "automation testing", "selenium",
    "manual testing", "performance testing", "load testing",
}

# Education degree patterns
DEGREE_PATTERNS = [
    (r"(?i)\b(ph\.?d|doctorate)\b", "Ph.D"),
    (r"(?i)\b(m\.?tech|mtech)\b", "M.Tech"),
    (r"(?i)\b(b\.?tech|btech)\b", "B.Tech"),
    (r"(?i)\b(m\.?b\.?a|mba)\b", "MBA"),
    (r"(?i)\b(b\.?b\.?a|bba)\b", "BBA"),
    (r"(?i)\b(m\.?c\.?a|mca)\b", "MCA"),
    (r"(?i)\b(b\.?c\.?a|bca)\b", "BCA"),
    (r"(?i)\b(m\.?sc|msc)\b", "M.Sc"),
    (r"(?i)\b(b\.?sc|bsc)\b", "B.Sc"),
    (r"(?i)\b(m\.?com|mcom)\b", "M.Com"),
    (r"(?i)\b(b\.?com|bcom)\b", "B.Com"),
    (r"(?i)\b(b\.?e\.?)\b", "B.E"),
    (r"(?i)\b(m\.?e\.?)\b", "M.E"),
    (r"(?i)\b(12th|hsc|higher secondary|intermediate)\b", "12th"),
    (r"(?i)\b(10th|ssc|secondary)\b", "10th"),
    (r"(?i)\b(diploma)\b", "Diploma"),
    (r"(?i)\b(ca |chartered accountant)\b", "CA"),
    (r"(?i)\b(cs |company secretary)\b", "CS"),
    (r"(?i)\b(icwa|cma)\b", "CMA"),
    (r"(?i)\b(llb|ll\.b)\b", "LLB"),
    (r"(?i)\b(mbbs)\b", "MBBS"),
]


def extract_skills_from_text(text: str) -> List[str]:
    """Extract skills using keyword matching + NER entities."""
    text_lower = text.lower()
    found_skills = []

    # 1. Direct keyword matching
    for skill in TECH_SKILLS:
        if skill in text_lower:
            found_skills.append(skill.title() if len(skill) > 3 else skill.upper())

    # 2. Look for "Key Skills" section in Naukri profiles
    skills_section = re.search(
        r"(?i)(?:key\s*skills?|skills?\s*:?|technical\s*skills?|core\s*competenc)\s*[:\-]?\s*(.+?)(?:\n\n|\nemployment|\neducation|\nprojects|\ncertification)",
        text, re.DOTALL
    )
    if skills_section:
        section_text = skills_section.group(1)
        # Split by common delimiters
        for skill in re.split(r"[,\|;\n\t]+", section_text):
            skill = skill.strip().strip("* -•")
            if 2 <= len(skill) <= 50 and not skill.isdigit():
                found_skills.append(skill.strip())

    # Deduplicate preserving order
    seen = set()
    unique = []
    for s in found_skills:
        key = s.lower().strip()
        if key not in seen and len(key) > 1:
            seen.add(key)
            unique.append(s)

    return unique[:30]  # Cap at 30 skills


def extract_education(text: str) -> List[Dict]:
    """Extract education entries from text."""
    education = []

    # Look for education section
    edu_section = re.search(
        r"(?i)(?:education|academic|qualification)\s*[:\-]?\s*(.+?)(?:\n\n\w|\nemployment|\nwork\s*experience|\nkey\s*skills|\ncertification|\nprojects)",
        text, re.DOTALL
    )
    section = edu_section.group(1) if edu_section else text

    for pattern, degree_name in DEGREE_PATTERNS:
        match = re.search(pattern, section)
        if match:
            # Try to find institution nearby (within 200 chars after degree)
            pos = match.end()
            nearby = section[pos:pos+200]
            institution = None

            # Look for institution patterns
            inst_match = re.search(
                r"(?:from|at|in|\-|\–)\s*([A-Z][A-Za-z\s&,\.]+(?:University|Institute|College|School|Academy|IIT|IIM|NIT|BITS|IIIT))",
                nearby
            )
            if inst_match:
                institution = inst_match.group(1).strip()

            # Look for year
            year_match = re.search(r"(20\d{2}|19\d{2})", nearby)
            year = year_match.group(1) if year_match else None

            # Look for specialization
            spec_match = re.search(
                r"(?:in|specialization|branch|stream)\s*[:\-]?\s*([A-Za-z\s&]+?)(?:\n|,|\.|from|at|$)",
                nearby
            )
            specialization = spec_match.group(1).strip() if spec_match else None

            education.append({
                "degree": degree_name,
                "institution": institution,
                "year": year,
                "specialization": specialization,
            })

    return education


def extract_work_history(text: str) -> List[Dict]:
    """Extract work experience entries from structured Naukri text."""
    work_history = []

    # Look for employment/work experience section
    work_section = re.search(
        r"(?i)(?:employment|work\s*experience|experience\s*details?|professional\s*experience)\s*[:\-]?\s*(.+?)(?:\n\n(?:education|academic|qualification|key\s*skills|certification|projects)|\Z)",
        text, re.DOTALL
    )
    if not work_section:
        return []

    section = work_section.group(1)

    # Pattern: Company name followed by designation/role
    entries = re.split(
        r"\n(?=[A-Z][A-Za-z\s&,\.]+(?:Pvt|Ltd|Inc|Corp|Limited|LLP|Solutions|Technologies|Tech|Services|Consulting|Group|India))",
        section
    )

    for entry in entries:
        entry = entry.strip()
        if len(entry) < 20:
            continue

        # Extract company name (first line or prominent text)
        company = None
        designation = None
        is_current = False

        lines = entry.strip().split("\n")
        if lines:
            company_line = lines[0].strip()
            if len(company_line) > 3 and len(company_line) < 100:
                company = company_line

        # Look for designation/role
        role_match = re.search(
            r"(?i)(?:designation|role|position|title)\s*[:\-]?\s*(.+?)(?:\n|$)",
            entry
        )
        if role_match:
            designation = role_match.group(1).strip()

        # Check for current role indicators
        if re.search(r"(?i)(present|current|till date|ongoing)", entry):
            is_current = True

        # Extract dates
        date_matches = re.findall(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*[\s,]+\d{4}", entry)
        from_date = date_matches[0] if len(date_matches) > 0 else None
        to_date = date_matches[1] if len(date_matches) > 1 else ("Present" if is_current else None)

        # Get description (remaining text after first 2 lines)
        desc = "\n".join(lines[2:]).strip() if len(lines) > 2 else None

        if company or designation:
            work_history.append({
                "company": company,
                "designation": designation,
                "from_date": from_date,
                "to_date": to_date,
                "is_current": is_current,
                "description": desc[:500] if desc else None,
            })

    return work_history[:10]  # Cap at 10 entries


def extract_with_spacy_ner(text: str) -> Dict:
    """Use spaCy NER to extract organizations, persons, locations, etc."""
    nlp = _get_nlp()
    doc = nlp(text[:10000])  # Limit to 10K chars for speed

    orgs = set()
    locations = set()
    persons = set()

    for ent in doc.ents:
        if ent.label_ == "ORG":
            orgs.add(ent.text.strip())
        elif ent.label_ in ("GPE", "LOC"):
            locations.add(ent.text.strip())
        elif ent.label_ == "PERSON":
            persons.add(ent.text.strip())

    return {
        "organizations": list(orgs)[:20],
        "locations": list(locations)[:10],
        "persons": list(persons)[:5],
    }


def extract_certifications(text: str) -> List[str]:
    """Extract certification mentions from text."""
    certs = []
    cert_patterns = [
        r"(?i)(AWS\s+(?:Certified|Solutions?\s+Architect|Developer|SysOps)[\w\s\-]*)",
        r"(?i)(Azure\s+(?:Certified|Administrator|Developer)[\w\s\-]*)",
        r"(?i)(Google\s+Cloud\s+(?:Certified|Professional)[\w\s\-]*)",
        r"(?i)(PMP|Project\s+Management\s+Professional)",
        r"(?i)(Scrum\s+Master|CSM|PSM)",
        r"(?i)(ITIL[\s\w]*)",
        r"(?i)(Six\s+Sigma[\s\w]*)",
        r"(?i)(CCNA|CCNP|CCIE)",
        r"(?i)(CEH|Certified\s+Ethical\s+Hacker)",
        r"(?i)(CFA[\s\w]*)",
        r"(?i)(CISSP)",
    ]
    for pattern in cert_patterns:
        matches = re.findall(pattern, text)
        certs.extend(matches)
    return list(set(certs))[:10]


def extract_languages(text: str) -> List[str]:
    """Extract spoken languages from text."""
    languages = []
    known_languages = [
        "English", "Hindi", "Tamil", "Telugu", "Kannada", "Malayalam",
        "Bengali", "Marathi", "Gujarati", "Punjabi", "Urdu", "Odia",
        "Assamese", "Sanskrit", "French", "German", "Spanish", "Japanese",
        "Chinese", "Mandarin", "Korean", "Arabic", "Portuguese", "Russian",
    ]
    text_lower = text.lower()
    for lang in known_languages:
        if lang.lower() in text_lower:
            languages.append(lang)
    return languages


def compute_confidence(extracted: Dict) -> float:
    """
    Compute extraction confidence score (0.0 to 1.0).
    Higher = more complete extraction, less need for LLM.
    """
    weights = {
        "key_skills": 0.25,        # Most important for recruitment
        "work_experience": 0.25,    # Critical for candidate assessment
        "education": 0.20,          # Important qualification data
        "profile_summary": 0.10,    # Nice to have
        "certifications": 0.05,     # Bonus
        "languages": 0.05,          # Minor
        "candidate_phone": 0.05,    # Often from regex
        "candidate_email": 0.05,    # Often from regex
    }

    score = 0.0
    for field, weight in weights.items():
        val = extracted.get(field)
        if val:
            if isinstance(val, list) and len(val) > 0:
                # More items = higher confidence for that field
                completeness = min(len(val) / 3, 1.0)  # 3+ items = full confidence
                score += weight * completeness
            elif isinstance(val, str) and len(val) > 10:
                score += weight

    return round(score, 2)


def spacy_extract_profile(raw_text: str, existing_regex_data: Dict = None) -> Tuple[Dict, float]:
    """
    Main entry point: Extract candidate data using spaCy NER + rules.
    Returns (extracted_data, confidence_score).

    If confidence >= 0.6 → skip Claude entirely (admin A/B test).
    """
    existing = existing_regex_data or {}
    result = {}

    # 1. Skills extraction (keyword + section parsing)
    skills = extract_skills_from_text(raw_text)
    if skills:
        result["key_skills"] = skills

    # 2. Education extraction
    education = extract_education(raw_text)
    if education:
        result["education"] = education

    # 3. Work history extraction
    work_exp = extract_work_history(raw_text)
    if work_exp:
        result["work_experience"] = work_exp

    # 4. spaCy NER entities (enriches org/location context for confidence scoring)
    extract_with_spacy_ner(raw_text)

    # 5. Certifications
    certs = extract_certifications(raw_text)
    if certs:
        result["certifications"] = certs

    # 6. Languages
    languages = extract_languages(raw_text)
    if languages:
        result["languages"] = languages

    # 7. Profile summary — extract headline/summary section
    summary_match = re.search(
        r"(?i)(?:profile\s*summary|summary|about\s*me|objective)\s*[:\-]?\s*(.+?)(?:\n\n|\nemployment|\nwork|\neducation|\nkey\s*skills)",
        raw_text, re.DOTALL
    )
    if summary_match:
        summary = summary_match.group(1).strip()
        if len(summary) > 20:
            result["profile_summary"] = summary[:1000]

    # Merge with existing regex data for confidence calculation
    merged = {**existing, **result}
    confidence = compute_confidence(merged)

    logger.info(f"[SpaCy] Extracted: skills={len(skills)}, edu={len(education)}, "
                f"work={len(work_exp)}, certs={len(certs)}, langs={len(languages)} | "
                f"Confidence: {confidence}")

    return result, confidence
