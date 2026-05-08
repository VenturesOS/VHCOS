"""
Zero-AI Feature Flag & Replacement Functions
Scoped to admin@vhc.in for testing. Once validated, can be rolled out to all users.
"""
import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Feature Flag ────────────────────────────────────────────────────────────
ZERO_AI_EMAILS = {"admin@vhc.in"}


def is_zero_ai_user(user: dict) -> bool:
    """Check if user should use zero-AI code paths."""
    return (user.get("email") or "").lower().strip() in ZERO_AI_EMAILS


# ── A1: Industry Detection Lookup ───────────────────────────────────────────
_INDUSTRY_MAP = {
    "tcs": "Information Technology", "infosys": "Information Technology",
    "wipro": "Information Technology", "hcl": "Information Technology",
    "tech mahindra": "Information Technology", "cognizant": "Information Technology",
    "accenture": "IT Consulting", "capgemini": "IT Consulting",
    "ibm": "Information Technology", "microsoft": "Information Technology",
    "google": "Information Technology", "amazon": "E-Commerce / Technology",
    "flipkart": "E-Commerce", "paytm": "Fintech", "phonepe": "Fintech",
    "razorpay": "Fintech", "cred": "Fintech", "zerodha": "Fintech",
    "oracle": "Information Technology", "sap": "Enterprise Software",
    "salesforce": "Cloud / SaaS", "adobe": "Information Technology",
    "deloitte": "Consulting", "kpmg": "Consulting", "ey": "Consulting",
    "pwc": "Consulting", "mckinsey": "Consulting", "bcg": "Consulting",
    "hdfc": "Banking & Finance", "icici": "Banking & Finance",
    "sbi": "Banking & Finance", "axis": "Banking & Finance",
    "kotak": "Banking & Finance", "bajaj finserv": "Financial Services",
    "lic": "Insurance", "icici prudential": "Insurance",
    "maruti": "Automobile", "tata motors": "Automobile",
    "mahindra": "Automobile", "hyundai": "Automobile",
    "hero": "Automobile", "honda": "Automobile", "toyota": "Automobile",
    "hindustan unilever": "FMCG", "hul": "FMCG", "nestle": "FMCG",
    "itc": "FMCG", "dabur": "FMCG", "godrej": "FMCG",
    "sun pharma": "Pharmaceutical", "cipla": "Pharmaceutical",
    "dr reddy": "Pharmaceutical", "lupin": "Pharmaceutical",
    "apollo": "Healthcare", "fortis": "Healthcare",
    "airtel": "Telecommunications", "jio": "Telecommunications",
    "vodafone": "Telecommunications", "bsnl": "Telecommunications",
    "reliance retail": "Retail", "dmart": "Retail",
    "dlf": "Real Estate", "godrej properties": "Real Estate",
    "l&t": "Engineering & Construction", "larsen": "Engineering & Construction",
    "byju": "EdTech", "unacademy": "EdTech", "vedantu": "EdTech",
    "ongc": "Oil & Gas", "reliance industries": "Oil & Gas",
    "ntpc": "Power & Energy", "adani": "Energy & Infrastructure",
    "ultratech": "Cement & Building Materials", "ultra tech": "Cement & Building Materials",
    "acc cement": "Cement & Building Materials", "ambuja": "Cement & Building Materials",
    "shree cement": "Cement & Building Materials", "dalmia": "Cement & Building Materials",
    "delhivery": "Logistics", "blue dart": "Logistics",
}

_INDUSTRY_KEYWORDS = {
    "software": "Information Technology",
    "bank": "Banking & Finance", "finance": "Financial Services",
    "insurance": "Insurance", "pharma": "Pharmaceutical",
    "hospital": "Healthcare", "medical": "Healthcare",
    "food": "FMCG / Food", "beverage": "FMCG / Food",
    "retail": "Retail", "ecommerce": "E-Commerce", "e-commerce": "E-Commerce",
    "telecom": "Telecommunications", "real estate": "Real Estate",
    "construction": "Construction", "education": "Education",
    "hotel": "Hospitality", "travel": "Travel & Tourism",
    "logistics": "Logistics", "transport": "Logistics",
    "media": "Media & Entertainment", "advertis": "Advertising",
    "consult": "Consulting", "legal": "Legal",
    "cement": "Cement & Building Materials",
    "textile": "Textile & Apparel", "steel": "Manufacturing",
    "chemical": "Chemicals", "energy": "Energy",
    "power": "Power & Energy", "oil": "Oil & Gas",
    "agri": "Agriculture", "farm": "Agriculture",
    "automobile": "Automobile", "automotive": "Automobile",
}


def detect_industry_lookup(employer_name: str) -> Optional[str]:
    """Detect industry from employer name using lookup table. Zero AI."""
    if not employer_name:
        return None
    name_lower = employer_name.lower().strip()

    for key, industry in _INDUSTRY_MAP.items():
        if key in name_lower:
            return industry

    for keyword, industry in _INDUSTRY_KEYWORDS.items():
        if len(keyword) <= 5:
            if re.search(r'\b' + re.escape(keyword) + r'\b', name_lower):
                return industry
        else:
            if keyword in name_lower:
                return industry

    return None


# ── A6: Regex-based Search Filter Extraction ────────────────────────────────

def extract_search_filters_regex(prompt: str) -> dict:
    """Extract structured search filters from natural language using regex. Zero AI."""
    prompt_lower = prompt.lower().strip()
    filters = {
        "min_experience": None, "max_experience": None,
        "skills": [], "industry_include": [], "industry_exclude": [],
        "company_type_include": [], "company_type_exclude": [],
        "location_include": [], "location_exclude": [],
        "notice_period": None,
        "current_ctc_range": None, "expected_ctc_range": None,
        "degree_include": [], "degree_exclude": [],
        "branch_include": [], "branch_exclude": [],
        "min_avg_tenure_years": None, "max_switches": None,
        "additional_notes": "",
    }

    exp_m = re.search(r'(\d+)\s*(?:to|-)\s*(\d+)\s*(?:years?|yrs?)', prompt_lower)
    if exp_m:
        filters["min_experience"] = int(exp_m.group(1))
        filters["max_experience"] = int(exp_m.group(2))
    else:
        exp_m = re.search(r'(\d+)\+?\s*(?:years?|yrs?)', prompt_lower)
        if exp_m:
            filters["min_experience"] = int(exp_m.group(1))

    quoted = re.findall(r'"([^"]+)"', prompt)
    if quoted:
        filters["skills"] = quoted

    _KNOWN_SKILLS = [
        "python", "java", "javascript", "react", "angular", "vue", "node",
        "django", "flask", "fastapi", "spring", "sql", "mongodb", "postgresql",
        "aws", "azure", "gcp", "docker", "kubernetes", "devops", "ci/cd",
        "machine learning", "deep learning", "data science", "nlp", "tensorflow",
        "pytorch", "pandas", "excel", "power bi", "tableau", "salesforce",
        "sap", "tally", "c++", "c#", ".net", "golang", "rust", "kotlin",
        "swift", "flutter", "react native", "figma", "photoshop",
        "selenium", "manual testing", "automation testing", "agile", "scrum",
        "project management", "business development", "lead generation",
        "digital marketing", "seo", "sem", "content marketing",
        "accounting", "taxation", "gst", "audit", "financial analysis",
        "hr", "recruitment", "talent acquisition", "training",
        "human resources", "hr management", "payroll", "compliance",
        "sales", "b2b", "b2c", "channel sales", "distribution",
    ]
    for skill in _KNOWN_SKILLS:
        if skill in prompt_lower and skill not in [s.lower() for s in filters["skills"]]:
            filters["skills"].append(skill.title() if len(skill) > 3 else skill.upper())

    _CITIES = [
        "mumbai", "pune", "delhi", "noida", "gurgaon", "gurugram", "bangalore",
        "bengaluru", "hyderabad", "chennai", "kolkata", "ahmedabad", "jaipur",
        "lucknow", "chandigarh", "indore", "bhopal", "kochi", "surat",
        "nagpur", "coimbatore", "vizag", "remote", "pan india",
    ]
    for city in _CITIES:
        if city in prompt_lower:
            filters["location_include"].append(city.title())

    if "immediate" in prompt_lower:
        filters["notice_period"] = "immediate"
    elif re.search(r'(\d+)\s*day', prompt_lower):
        filters["notice_period"] = re.search(r'(\d+)\s*day', prompt_lower).group(1)

    ctc_m = re.search(r'(\d+)\s*(?:to|-)\s*(\d+)\s*(?:lpa|lakhs?|l)', prompt_lower)
    if ctc_m:
        filters["current_ctc_range"] = {"min": int(ctc_m.group(1)) * 100000, "max": int(ctc_m.group(2)) * 100000}

    _DEGREES = ["btech", "b.tech", "mtech", "m.tech", "mba", "bba", "bca", "mca",
                "bsc", "msc", "bcom", "mcom", "phd", "diploma", "pgdm", "ca", "cs"]
    for deg in _DEGREES:
        if deg in prompt_lower:
            filters["degree_include"].append(deg.upper())

    return filters


def generate_explanations_regex(candidates: list, filters: dict) -> list:
    """Generate template-based explanations per candidate. Zero AI."""
    skills_wanted = set(s.lower() for s in (filters.get("skills") or []))
    for c in candidates:
        parts = []
        cand_skills = set(s.lower() for s in (c.get("skills") or c.get("key_skills") or []))
        matched = skills_wanted & cand_skills
        if matched:
            parts.append(f"Matches {len(matched)}/{len(skills_wanted)} required skills")
        exp = c.get("experience_years") or c.get("total_experience_years")
        if exp:
            parts.append(f"{exp} years experience")
        loc = c.get("location") or c.get("current_city", "")
        if loc:
            parts.append(f"Based in {loc}")
        employer = c.get("current_employer") or c.get("current_company", "")
        if employer:
            parts.append(f"Currently at {employer}")
        c["ai_explanation"] = ". ".join(parts) if parts else "Profile matches search criteria"
    return candidates


# ── B2: Regex Resume Parser ─────────────────────────────────────────────────

def parse_resume_regex(resume_text: str) -> Dict:
    """Parse resume text using regex patterns. Zero AI."""
    text = resume_text or ""
    lines = text.split("\n")
    text_lower = text.lower()
    result = {
        "name": None, "email": None, "phone": None,
        "headline": None, "profile_summary": None,
        "current_company": None, "current_designation": None,
        "current_industry": None, "total_experience_years": None,
        "location": None, "date_of_birth": None, "gender": None,
        "current_salary": None, "expected_salary": None,
        "notice_period": None,
        "key_skills": [], "it_skills": [],
        "work_experience": [], "education": [],
        "certifications": [], "projects": [],
        "languages": [], "online_profiles": [],
        "preferred_locations": [],
    }

    # ── Email ──
    emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', text)
    blocked = ['naukri.com', 'vhc.in', 'noreply', 'support@', 'example.com']
    for email in emails:
        if not any(b in email.lower() for b in blocked):
            result["email"] = email
            break

    # ── Phone ──
    phones = re.findall(r'(?:\+91[\s\-]?)?(?:0)?([6-9]\d{9})', text)
    if phones:
        result["phone"] = phones[0][-10:]

    # ── Name ──
    name_m = re.search(r'(?:Name|Full\s*Name|Candidate\s*Name)\s*[:\-]\s*([A-Z][a-zA-Z\s.]{2,40})', text)
    if name_m:
        result["name"] = name_m.group(1).strip()
    else:
        _skip = re.compile(r'^(resume|curriculum|cv |profile|objective|summary|experience|education|skill|contact|personal|address|phone|email|mobile|tel |http|www|\+?\d)', re.IGNORECASE)
        for line in lines[:12]:
            line = line.strip()
            if not line or len(line) < 3 or len(line) > 50:
                continue
            if _skip.match(line):
                continue
            if any(c in line for c in "@:;/\\(){}[]<>"):
                continue
            if re.match(r'^[\d\+\-\(\)]{6,}', line):
                continue
            words = line.split()
            if 2 <= len(words) <= 5:
                caps = sum(1 for w in words if len(w) > 1 and w[0].isupper())
                if caps >= len(words) * 0.6:
                    result["name"] = line
                    break

    # ── Experience Years ──
    for pat in [
        r'(?:Total|Overall|Work)?\s*Experience\s*[:\-]\s*(\d+)[\s.]*(?:years?|yrs?)[\s,]*(\d+)?\s*(?:months?|mos?)?',
        r'(\d+)\s*(?:years?|yrs?)\s*(?:and\s*)?(\d+)?\s*(?:months?|mos?)?\s*(?:of\s*)?(?:experience|exp)',
        r'(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s*)?(?:experience|exp|in\s+)',
        r'Experience\s*[:\-]\s*(\d+)',
        r'(\d+)\s*Year\(s\)\s*(\d+)?\s*Month',
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            yrs = int(m.group(1))
            mos = int(m.group(2)) if m.lastindex >= 2 and m.group(2) else 0
            if yrs <= 50:
                result["total_experience_years"] = round(yrs + mos / 12, 1)
                break

    # ── CTC ──
    for pat, mult in [
        (r'(?:Current|Present)\s*(?:CTC|Salary|Annual\s*Salary|Compensation)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*(\d+[\d,.]*)\s*(?:Lac|Lakh|LPA|L)', 100000),
        (r'(?:CTC|Salary)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*(\d+[\d,.]*)\s*(?:Lac|Lakh|LPA|L)', 100000),
        (r'(\d+[\d,.]*)\s*(?:Lac|Lakh|LPA)\s*(?:per\s*annum)?', 100000),
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                result["current_salary"] = int(float(m.group(1).replace(',', '')) * mult)
            except ValueError:
                pass
            break

    exp_ctc = re.search(r'Expected\s*(?:CTC|Salary)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*(\d+[\d,.]*)\s*(?:Lac|Lakh|LPA|L)', text, re.IGNORECASE)
    if exp_ctc:
        try:
            result["expected_salary"] = int(float(exp_ctc.group(1).replace(',', '')) * 100000)
        except ValueError:
            pass

    # ── Notice Period ──
    for pat in [
        r'Notice\s*Period\s*[:\-]\s*(.+?)(?:\n|$)',
        r'(\d+)\s*(?:months?|days?)\s*notice',
        r'(?:Immediate(?:ly)?)\s*(?:Joiner|Available)?',
        r'Currently\s*Serving\s*Notice',
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            if 'immediate' in m.group(0).lower():
                result["notice_period"] = "Immediate"
            elif 'serving' in m.group(0).lower():
                result["notice_period"] = "Serving Notice"
            else:
                result["notice_period"] = m.group(1).strip() if m.lastindex else m.group(0).strip()
            break

    # ── Location ──
    loc_m = re.search(r'(?:Current\s*)?(?:Location|City|Address|Residence|Based\s*in|Residing)\s*[:\-]\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if loc_m:
        loc = loc_m.group(1).strip().split(',')[0].strip()
        if len(loc) < 50 and not re.match(r'^\d+', loc):
            result["location"] = loc

    # ── Current Employer ──
    for pat in [
        r'(?:Current\s*(?:Company|Employer|Organization)|Working\s*(?:at|with|in)|Employed\s*(?:at|with))\s*[:\-]\s*(.+?)(?:\n|$)',
        r'(?:Company|Employer|Organization)\s*[:\-]\s*(.+?)(?:\n|$)',
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if 1 < len(val) < 60:
                result["current_company"] = val
                break

    # ── Designation ──
    for pat in [
        r'(?:Current\s*)?(?:Designation|Title|Role|Position)\s*[:\-]\s*(.+?)(?:\n|$)',
        r'(?:Job\s*Title)\s*[:\-]\s*(.+?)(?:\n|$)',
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if 1 < len(val) < 60:
                result["current_designation"] = val
                break

    # ── Profile Summary ──
    sum_m = re.search(
        r'(?:Profile\s*Summary|Summary|About\s*Me|Objective|Career\s*Objective|Professional\s*Summary)\s*[:\-]?\s*\n(.+?)(?:\n\n|\nKey\s*Skills|\nSkills|\nTechnical|\nWork|\nExperience|\nEmployment|\nProfessional)',
        text, re.IGNORECASE | re.DOTALL
    )
    if sum_m and len(sum_m.group(1).strip()) > 30:
        result["profile_summary"] = sum_m.group(1).strip()[:500]
        result["headline"] = result["profile_summary"][:100]

    # ── Skills — AGGRESSIVE full-text keyword scan ──
    skills = set()

    # Strategy 1: Skills section
    sk_sec = re.search(
        r'(?:Key\s*Skills?|Technical\s*Skills?|Core\s*Competenc\w*|Skills?\s*(?:&\s*)?(?:Expertise|Set)|IT\s*Skills?|Areas?\s*of\s*Expertise)\s*[:\-]?\s*\n?(.+?)(?:\n\n|\nWork|\nExperience|\nEmployment|\nEducation|\nCertif|\nProject|\nAchieve|\nPersonal)',
        text, re.IGNORECASE | re.DOTALL
    )
    if sk_sec:
        for s in re.split(r'[,|;:\t/\n]+', sk_sec.group(1)):
            s = s.strip().strip('-').strip('*').strip()
            if 2 < len(s) < 50 and not re.match(r'^\d+$', s):
                skills.add(s)

    # Strategy 2: Full-text keyword scan
    _ALL_SKILLS = {
        "python", "java", "javascript", "typescript", "react", "angular", "vue",
        "node.js", "nodejs", "django", "flask", "fastapi", "spring boot", "spring",
        "sql", "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
        "aws", "azure", "gcp", "docker", "kubernetes", "git", "jenkins",
        "html", "css", "sass", "bootstrap", "tailwind",
        "machine learning", "deep learning", "data science", "nlp",
        "tensorflow", "pytorch", "pandas", "numpy", "scikit-learn",
        "selenium", "cypress", "jest", "junit", "pytest",
        "agile", "scrum", "jira", "confluence",
        "rest api", "graphql", "microservices", "kafka", "rabbitmq",
        "linux", "bash", "shell scripting",
        "c++", "c#", ".net", "asp.net", "golang", "rust", "kotlin", "swift",
        "flutter", "react native", "android", "ios",
        "figma", "photoshop", "illustrator",
        "power bi", "tableau", "excel", "advanced excel", "ms office",
        "sap", "salesforce", "servicenow", "oracle", "tally", "erp",
        "devops", "ci/cd", "terraform", "ansible",
        "project management", "product management", "business analysis",
        "business development", "lead generation", "account management",
        "digital marketing", "seo", "sem", "social media marketing",
        "content marketing", "email marketing", "google analytics",
        "financial analysis", "financial modeling", "accounting", "taxation",
        "gst", "tds", "audit", "compliance", "risk management",
        "human resources", "talent acquisition", "recruitment",
        "training and development", "employee engagement",
        "supply chain", "procurement", "inventory management",
        "quality assurance", "quality control", "six sigma", "lean",
        "sales", "b2b sales", "b2c sales", "channel sales", "retail sales",
        "customer service", "customer success", "crm",
        "data entry", "data analysis", "data engineering", "etl",
        "networking", "cisco", "ccna", "windows server",
        "vmware", "cloud computing", "information security",
        "autocad", "solidworks", "catia",
        "plc", "scada", "embedded systems", "iot",
        "operations management", "logistics", "warehouse management",
        "communication skills", "leadership", "team management",
        "negotiation", "presentation skills", "problem solving",
        "hr management", "payroll", "statutory compliance",
        "vendor management", "client management", "stakeholder management",
    }
    for skill in _ALL_SKILLS:
        if re.search(r'\b' + re.escape(skill) + r'\b', text_lower):
            display = skill.title() if len(skill) > 3 else skill.upper()
            skills.add(display)

    result["key_skills"] = list(skills)[:30]

    # ── Education ──
    _DEG = r'(B\.?Tech|M\.?Tech|MBA|BBA|B\.?E\.?|M\.?E\.?|B\.?Sc|M\.?Sc|B\.?Com|M\.?Com|B\.?A\.?|M\.?A\.?|Ph\.?D|Diploma|PGDM|BCA|MCA|B\.?Pharm|M\.?Pharm|MBBS|MD|10th|12th|HSC|SSC|Intermediate|Bachelor|Master)'
    edu_sec = re.search(
        r'(?:Education|Qualification|Academic|Degree)\s*[:\-]?\s*\n(.+?)(?:\nCertif|\nProject|\nPersonal|\nSkill|\nTechnical|\nLanguage|\nWork|\nEmploy|\nAchieve|\nHobb|\n\n\n|$)',
        text, re.IGNORECASE | re.DOTALL
    )
    if edu_sec:
        for line in edu_sec.group(1).split('\n'):
            line = line.strip()
            if not line:
                continue
            dm = re.search(_DEG, line, re.IGNORECASE)
            if dm:
                parts = [p.strip() for p in re.split(r'[,|\-]', line) if p.strip()]
                edu_entry = {"degree": dm.group(1), "specialization": None, "institution": None, "year_of_passing": None}
                ym = re.search(r'((?:19|20)\d{2})', line)
                if ym:
                    edu_entry["year_of_passing"] = ym.group(1)
                for p in parts:
                    if p.strip() == dm.group(1) or re.match(r'^\d{4}$', p.strip()):
                        continue
                    if len(p) > 5 and not edu_entry["institution"]:
                        edu_entry["institution"] = p.strip()
                    elif not edu_entry["specialization"] and len(p) > 3:
                        edu_entry["specialization"] = p.strip()
                result["education"].append(edu_entry)

    # ── Work Experience ──
    exp_sec = re.search(
        r'(?:Employment|Work\s*Experience|Experience\s*Details?|Professional\s*Experience|Career\s*History)\s*[:\-]?\s*\n(.+?)(?:\nEducation|\nQualification|\nAcademic|\nCertif|\nProject|\nPersonal|\nSkill|\nTechnical|\nHobb|\n\n\n|$)',
        text, re.IGNORECASE | re.DOTALL
    )
    if exp_sec:
        exp_text = exp_sec.group(1)
        date_pat = r'(\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*[\s\-,\']*\d{4}\s*(?:to|[-])\s*(?:\w+[\s\-,\']*\d{4}|Present|Current|Till\s*Date))'
        date_ranges = list(re.finditer(date_pat, exp_text, re.IGNORECASE))

        if date_ranges:
            for i, drm in enumerate(date_ranges):
                preceding = exp_text[:drm.start()].rsplit('\n', 3)
                end = date_ranges[i+1].start() if i+1 < len(date_ranges) else len(exp_text)
                entry_text = exp_text[drm.end():end].strip()

                exp_entry = {"company": None, "designation": None, "from_date": None, "to_date": None, "is_current": False, "description": None}
                dates = re.findall(r'(\w+[\s,\']*\d{4}|Present|Current|Till\s*Date)', drm.group(1), re.IGNORECASE)
                if dates:
                    exp_entry["from_date"] = dates[0]
                    exp_entry["to_date"] = dates[1] if len(dates) > 1 else None
                if any(w in drm.group(1).lower() for w in ['present', 'current', 'till']):
                    exp_entry["is_current"] = True

                for pl in reversed(preceding):
                    pl = pl.strip()
                    if pl and len(pl) > 1:
                        if not exp_entry["company"]:
                            exp_entry["company"] = pl
                        elif not exp_entry["designation"]:
                            exp_entry["designation"] = pl
                        else:
                            break

                if entry_text:
                    exp_entry["description"] = entry_text[:300]
                if exp_entry["company"] or exp_entry["designation"]:
                    result["work_experience"].append(exp_entry)
        else:
            blocks = re.split(r'\n\n+', exp_text)
            for block in blocks[:8]:
                blines = [bl.strip() for bl in block.split('\n') if bl.strip()]
                if not blines:
                    continue
                exp_entry = {"company": blines[0], "designation": None, "from_date": None, "to_date": None, "is_current": False, "description": None}
                for bl in blines[1:]:
                    if re.search(r'\d{4}', bl):
                        dates = re.findall(r'(\w+\s*\d{4}|\d{4}|Present|Current)', bl, re.IGNORECASE)
                        if dates:
                            exp_entry["from_date"] = dates[0]
                            exp_entry["to_date"] = dates[1] if len(dates) > 1 else None
                        if any(w in bl.lower() for w in ['present', 'current']):
                            exp_entry["is_current"] = True
                    elif not exp_entry["designation"] and len(bl) < 80:
                        exp_entry["designation"] = bl
                result["work_experience"].append(exp_entry)

    if not result["work_experience"] and result["current_company"]:
        result["work_experience"].append({
            "company": result["current_company"], "designation": result["current_designation"],
            "is_current": True, "from_date": None, "to_date": "Present", "description": None,
        })

    # ── DOB / Gender ──
    dob_m = re.search(r'(?:Date\s*of\s*Birth|DOB|D\.O\.B)\s*[:\-]\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if dob_m:
        result["date_of_birth"] = dob_m.group(1).strip()
    gender_m = re.search(r'Gender\s*[:\-]\s*(Male|Female|Other)', text, re.IGNORECASE)
    if gender_m:
        result["gender"] = gender_m.group(1).capitalize()

    # ── Industry ──
    if result["current_company"]:
        result["current_industry"] = detect_industry_lookup(result["current_company"])

    # ── Normalize ──
    from services.schema_normalizer import normalize_candidate
    normalized = normalize_candidate(result)

    logger.info(f"[ZeroAI Resume] name={normalized.get('name')}, skills={len(normalized.get('key_skills', []))}, exp={normalized.get('total_experience_years')}, company={normalized.get('current_company')}")
    return {"success": True, "data": normalized}


# ── B4: Template-based Bullet Enhancement ───────────────────────────────────
_ACTION_VERBS = [
    "Spearheaded", "Architected", "Orchestrated", "Implemented", "Delivered",
    "Optimized", "Streamlined", "Developed", "Led", "Managed", "Designed",
    "Automated", "Established", "Drove", "Accelerated", "Transformed",
    "Built", "Scaled", "Reduced", "Increased", "Launched", "Pioneered",
]


def enhance_bullets_template(bullets: list) -> list:
    """Enhance resume bullets using templates. Zero AI."""
    import random
    enhanced = []
    for bullet in bullets:
        bullet = bullet.strip()
        if not bullet:
            continue
        first_word = bullet.split()[0] if bullet.split() else ""
        if first_word in _ACTION_VERBS:
            enhanced.append(bullet)
            continue
        verb = random.choice(_ACTION_VERBS)
        if bullet[0].isupper():
            bullet = bullet[0].lower() + bullet[1:]
        enhanced.append(f"{verb} {bullet}")
    return enhanced
