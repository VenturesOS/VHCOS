"""
Smart Tags Service — Rule-based auto-categorization for candidates.
Zero AI cost, deterministic, instant. Tags stored in candidate_bank.smart_tags.

Tag Categories:
1. Experience Level: Fresher, Junior, Mid-Level, Senior, Lead, Director+
2. Domain: 24+ technical/functional domains
3. Availability: Immediate Joiner, Short Notice, Medium Notice, Long Notice, Serving Notice
4. Salary Bracket: Budget, Mid, Premium tiers
5. Location Tier: Metro, Tier-1, Tier-2
6. Company Tier: FAANG/MAANG, Top MNC
7. Education: IIT/NIT/Premier, MBA, PhD, Engineering Grad
8. Resume Status: Has CV, No CV
9. Career Stability: Stable, Job Hopper, Rising Star
10. Management: IC, People Manager, VP+
11. Industry: IT, BFSI, Manufacturing, Healthcare, etc.
12. Contact Status: Contact Available, Contact Hidden
13. Profile Quality: Complete Profile, Incomplete Profile
14. Certifications: AWS Certified, PMP, Scrum Master, etc.
15. Composite: Hot Candidate, Premium Talent
"""
import re
import logging

logger = logging.getLogger(__name__)

# ── Metro / Tier-1 / Tier-2 city lists ──
METRO_CITIES = {"mumbai", "delhi", "bangalore", "bengaluru", "hyderabad", "chennai", "kolkata", "pune"}
TIER1_CITIES = {"ahmedabad", "jaipur", "lucknow", "chandigarh", "indore", "nagpur", "bhopal", "coimbatore", "kochi", "visakhapatnam", "thiruvananthapuram", "gurgaon", "gurugram", "noida", "ghaziabad", "faridabad", "navi mumbai", "thane", "mysore", "mangalore", "surat", "vadodara", "patna", "ranchi", "bhubaneswar", "dehradun"}

# ── Top-tier companies ──
FAANG = {"google", "meta", "facebook", "amazon", "apple", "netflix", "microsoft", "alphabet"}
TOP_MNC = {"tcs", "infosys", "wipro", "hcl", "cognizant", "accenture", "capgemini", "deloitte", "ey", "kpmg", "pwc", "ibm", "oracle", "sap", "salesforce", "adobe", "uber", "flipkart", "swiggy", "zomato", "razorpay", "paytm", "ola", "myntra", "meesho", "cred", "phonepe", "bharatpe", "jio", "reliance", "tata", "mahindra", "bajaj", "hdfc", "icici", "kotak", "axis"}

# ── IIT/NIT/Premier institutes ──
PREMIER_INSTITUTES = {"iit", "nit", "bits", "iisc", "iim", "ism", "iiit", "isb", "xlri", "fms", "srcc", "stephens"}

# ── Domain keyword mapping ──
DOMAIN_KEYWORDS = {
    "Java Developer": ["java", "spring boot", "spring", "j2ee", "hibernate", "servlet"],
    "Python Developer": ["python", "django", "flask", "fastapi", "pandas", "numpy"],
    "Frontend Developer": ["react", "angular", "vue", "next.js", "nuxt", "svelte", "typescript"],
    "Full Stack": ["full stack", "fullstack", "mern", "mean"],
    ".NET Developer": [".net", "c#", "asp.net", "blazor", "entity framework"],
    "Data Engineer": ["data engineer", "spark", "hadoop", "airflow", "etl", "data pipeline", "kafka", "bigquery"],
    "Data Scientist": ["data scientist", "machine learning", "deep learning", "tensorflow", "pytorch", "nlp", "computer vision", "ai/ml"],
    "Data Analyst": ["data analyst", "power bi", "tableau", "analytics", "excel", "looker"],
    "DevOps": ["devops", "kubernetes", "docker", "jenkins", "terraform", "ansible", "ci/cd"],
    "Cloud Engineer": ["cloud engineer", "aws", "azure", "gcp", "cloud architect"],
    "QA / Testing": ["qa", "testing", "selenium", "automation testing", "manual testing", "cypress", "jest", "appium"],
    "Mobile Developer": ["android", "ios", "flutter", "react native", "swift", "kotlin"],
    "Database / DBA": ["dba", "database admin", "sql server", "oracle dba", "mysql", "postgresql", "mongodb"],
    "SAP": ["sap", "sap hana", "sap fico", "sap mm", "sap sd", "sap abap"],
    "Networking": ["network engineer", "cisco", "ccna", "ccnp", "firewall", "routing"],
    "Cybersecurity": ["cybersecurity", "security analyst", "penetration testing", "soc", "siem", "ethical hacking"],
    "Sales": ["sales", "business development", "account manager", "sales executive", "sales manager", "revenue"],
    "HR": ["human resources", "talent acquisition", "recruitment", "recruiter", "hrm", "hrbp"],
    "Finance": ["finance", "accounting", "accounts", "chartered accountant", "audit", "taxation", "cfo"],
    "Marketing": ["marketing", "digital marketing", "seo", "sem", "social media", "content marketing", "brand"],
    "Product Manager": ["product manager", "product owner", "product management"],
    "UI/UX Designer": ["figma", "ui/ux", "user experience", "graphic design", "adobe xd", "sketch"],
    "Project Manager": ["project manager", "pmp", "scrum master", "agile", "program manager"],
    "Mechanical Engineer": ["mechanical", "autocad", "solidworks", "catia", "manufacturing"],
    "Civil Engineer": ["civil engineer", "construction", "structural", "site engineer"],
    "Electrical Engineer": ["electrical", "plc", "scada", "embedded", "power systems"],
    "Blockchain": ["blockchain", "solidity", "web3", "smart contract", "ethereum"],
    "AI/ML Engineer": ["ai engineer", "ml engineer", "mlops", "model training", "hugging face", "llm"],
}

# ── Industry keywords ──
INDUSTRY_KEYWORDS = {
    "IT/Software": ["software", "it services", "technology", "tech", "saas", "internet"],
    "BFSI": ["banking", "finance", "insurance", "fintech", "nbfc", "mutual fund"],
    "Manufacturing": ["manufacturing", "production", "factory", "plant", "automobile", "auto"],
    "Healthcare": ["healthcare", "pharma", "hospital", "medical", "biotech", "clinical"],
    "Telecom": ["telecom", "telecommunications", "5g", "networking"],
    "Retail": ["retail", "ecommerce", "e-commerce", "fashion", "fmcg", "consumer"],
    "Consulting": ["consulting", "advisory", "management consulting", "strategy"],
    "Education": ["education", "edtech", "training", "university", "teaching"],
    "Real Estate": ["real estate", "property", "construction", "infrastructure"],
    "Media": ["media", "entertainment", "gaming", "advertising", "content"],
    "Logistics": ["logistics", "supply chain", "warehousing", "shipping", "transportation"],
    "Energy": ["energy", "oil", "gas", "renewable", "solar", "power"],
}

# ── Certification keywords ──
CERT_KEYWORDS = {
    "AWS Certified": ["aws certified", "aws solution", "aws associate", "aws professional"],
    "Azure Certified": ["azure certified", "az-900", "az-104", "az-305"],
    "GCP Certified": ["gcp certified", "google cloud certified"],
    "PMP": ["pmp", "project management professional"],
    "Scrum Master": ["scrum master", "csm", "psm"],
    "CKA/CKAD": ["cka", "ckad", "kubernetes admin"],
    "CISSP": ["cissp", "certified information"],
    "CA": ["chartered accountant", " ca ", "icai"],
    "CFA": ["cfa", "chartered financial analyst"],
    "Six Sigma": ["six sigma", "lean six sigma", "green belt", "black belt"],
}

# ── Management-level keywords ──
VP_KEYWORDS = ["vp", "vice president", "svp", "evp", "cto", "ceo", "coo", "cfo", "cio", "chief", "head of", "director"]
MANAGER_KEYWORDS = ["manager", "team lead", "tech lead", "engineering manager", "delivery manager", "program manager", "group lead"]


def generate_smart_tags(candidate: dict) -> list:
    """Generate smart tags from candidate profile data. Returns list of tag strings."""
    tags = []

    # ── Extract fields ──
    exp = candidate.get("experience_years") or candidate.get("total_experience_years") or 0
    if isinstance(exp, str):
        try:
            exp = float(exp)
        except ValueError:
            exp = 0

    skills = candidate.get("skills") or candidate.get("key_skills") or []
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(",")]
    skills_lower = " ".join(s.lower() for s in skills)

    headline = (candidate.get("headline") or candidate.get("designation") or candidate.get("current_designation") or "").lower()
    summary = (candidate.get("summary") or candidate.get("profile_summary") or "").lower()
    employer = (candidate.get("current_employer") or "").lower()
    location = (candidate.get("location") or "").lower()
    education = candidate.get("education") or []
    notice = (candidate.get("notice_period") or "").lower()
    notice_days = candidate.get("notice_period_days") or 0
    salary = candidate.get("current_salary") or candidate.get("current_ctc") or 0
    resume_url = candidate.get("resume_url") or ""
    phone = candidate.get("phone") or ""
    email = candidate.get("email") or ""
    industry = (candidate.get("industry") or candidate.get("current_industry") or "").lower()
    work_exp = candidate.get("experience") or candidate.get("work_experience") or []
    certifications = candidate.get("certifications") or candidate.get("certifications_detailed") or []

    searchable = f"{skills_lower} {headline} {summary}"
    cert_text = " ".join(
        (c.get("name", "") if isinstance(c, dict) else str(c))
        for c in certifications
    ).lower() if certifications else ""
    full_searchable = f"{searchable} {cert_text}"

    # ═══ 1. Experience Level ═══
    if exp <= 0:
        tags.append("Fresher")
    elif exp <= 2:
        tags.append("Junior (0-2yr)")
    elif exp <= 5:
        tags.append("Mid-Level (2-5yr)")
    elif exp <= 10:
        tags.append("Senior (5-10yr)")
    elif exp <= 15:
        tags.append("Lead (10-15yr)")
    else:
        tags.append("Director+ (15yr+)")

    # ═══ 2. Domain Tags ═══
    matched_domains = set()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in searchable:
                matched_domains.add(domain)
                break
    for d in sorted(matched_domains)[:5]:
        tags.append(d)

    # ═══ 3. Availability ═══
    if notice_days == 0 or "immediate" in notice:
        tags.append("Immediate Joiner")
    elif notice_days <= 15 or "15 day" in notice:
        tags.append("15-Day Notice")
    elif notice_days <= 30 or "1 month" in notice or "30 day" in notice:
        tags.append("30-Day Notice")
    elif notice_days <= 60 or "2 month" in notice or "45 day" in notice:
        tags.append("60-Day Notice")
    elif notice_days <= 90 or "3 month" in notice or "90 day" in notice:
        tags.append("90-Day Notice")
    else:
        tags.append("90+ Day Notice")
    if "serving" in notice:
        tags.append("Serving Notice")

    # ═══ 4. Salary Bracket ═══
    if salary:
        if isinstance(salary, str):
            try:
                salary = int(re.sub(r'[^\d]', '', salary))
            except ValueError:
                salary = 0
        if salary > 0:
            if salary < 300000:
                tags.append("CTC: <3L")
            elif salary < 500000:
                tags.append("CTC: 3-5L")
            elif salary < 1000000:
                tags.append("CTC: 5-10L")
            elif salary < 1500000:
                tags.append("CTC: 10-15L")
            elif salary < 2500000:
                tags.append("CTC: 15-25L")
            elif salary < 5000000:
                tags.append("CTC: 25-50L")
            else:
                tags.append("CTC: 50L+")

    # ═══ 5. Location Tier ═══
    loc_clean = location.replace(",", " ").replace("-", " ").strip()
    loc_words = set(loc_clean.split())
    if loc_words & METRO_CITIES:
        tags.append("Metro City")
    elif loc_words & TIER1_CITIES:
        tags.append("Tier-1 City")
    elif location and location.strip():
        tags.append("Tier-2/3 City")

    # ═══ 6. Company Tier ═══
    emp_clean = employer.replace(".", "").replace(" limited", "").replace(" ltd", "").replace(" pvt", "").replace(" private", "")
    emp_words = set(emp_clean.split())
    if emp_words & FAANG:
        tags.append("FAANG/MAANG")
    elif emp_words & TOP_MNC:
        tags.append("Top MNC")

    # ═══ 7. Education ═══
    edu_text = " ".join(
        f"{e.get('degree', '')} {e.get('institution', '')} {e.get('specialization', '')}"
        for e in education
    ).lower()

    if any(p in edu_text for p in PREMIER_INSTITUTES):
        tags.append("IIT/NIT/Premier")
    if re.search(r'\bmba\b', edu_text) or "pgdm" in edu_text:
        tags.append("MBA")
    if re.search(r'\bph\.?d\b', edu_text) or "doctorate" in edu_text:
        tags.append("PhD")
    if any(d in edu_text for d in ["b.tech", "b.e.", "bachelor of engineering", "bachelor of technology"]):
        tags.append("Engineering Grad")
    if any(d in edu_text for d in ["m.tech", "m.e.", "master of engineering", "master of technology"]):
        tags.append("PG Engineering")

    # ═══ 8. Resume Status ═══
    if resume_url:
        tags.append("Has CV")
    else:
        tags.append("No CV")

    # ═══ 9. Career Stability ═══
    if len(work_exp) >= 2:
        tenures = []
        for w in work_exp:
            dur = w.get("duration", "")
            if isinstance(dur, str):
                y_match = re.search(r'(\d+)\s*y', dur, re.IGNORECASE)
                m_match = re.search(r'(\d+)\s*m', dur, re.IGNORECASE)
                years = int(y_match.group(1)) if y_match else 0
                months = int(m_match.group(1)) if m_match else 0
                total_months = years * 12 + months
                if total_months > 0:
                    tenures.append(total_months)
        if tenures:
            avg_tenure = sum(tenures) / len(tenures)
            if avg_tenure >= 36:
                tags.append("Stable (3yr+ avg)")
            elif avg_tenure <= 12:
                tags.append("Job Hopper (<1yr avg)")
            # Rising Star: increasing seniority in titles
    elif len(work_exp) == 1:
        tags.append("Single Employer")

    # ═══ 10. Management Level ═══
    title_text = f"{headline} {summary}"
    if any(kw in title_text for kw in VP_KEYWORDS):
        tags.append("VP/C-Level")
    elif any(kw in title_text for kw in MANAGER_KEYWORDS):
        tags.append("People Manager")
    else:
        tags.append("IC")

    # ═══ 11. Industry ═══
    industry_searchable = f"{industry} {employer} {headline}"
    for ind, keywords in INDUSTRY_KEYWORDS.items():
        for kw in keywords:
            if kw in industry_searchable:
                tags.append(ind)
                break

    # ═══ 12. Contact Status ═══
    if phone and email and "@" in email:
        tags.append("Contact Available")
    elif phone or (email and "@" in email):
        tags.append("Partial Contact")
    else:
        tags.append("Contact Hidden")

    # ═══ 13. Profile Quality ═══
    completeness = 0
    if candidate.get("name"): completeness += 1
    if phone: completeness += 1
    if email and "@" in email: completeness += 1
    if location: completeness += 1
    if exp > 0: completeness += 1
    if skills and len(skills) >= 3: completeness += 1
    if education: completeness += 1
    if work_exp: completeness += 1
    if summary: completeness += 1
    if salary: completeness += 1

    if completeness >= 8:
        tags.append("Complete Profile")
    elif completeness >= 5:
        tags.append("Partial Profile")
    else:
        tags.append("Incomplete Profile")

    # ═══ 14. Certifications ═══
    for cert_tag, cert_kws in CERT_KEYWORDS.items():
        for kw in cert_kws:
            if kw in full_searchable:
                tags.append(cert_tag)
                break

    # ═══ 15. Composite / Power Tags ═══
    tag_set = set(tags)
    # Hot Candidate: Immediate + Has CV + Senior+
    if "Immediate Joiner" in tag_set and "Has CV" in tag_set and any(t.startswith("Senior") or t.startswith("Lead") for t in tags):
        tags.append("Hot Candidate")
    # Premium Talent: FAANG + Senior + High salary
    if ("FAANG/MAANG" in tag_set or "IIT/NIT/Premier" in tag_set) and any("25" in t or "50" in t for t in tags):
        tags.append("Premium Talent")
    # Quick Hire: Short notice + Has CV
    if any(t in tag_set for t in ["Immediate Joiner", "15-Day Notice", "30-Day Notice", "Serving Notice"]) and "Has CV" in tag_set:
        tags.append("Quick Hire")

    return tags
