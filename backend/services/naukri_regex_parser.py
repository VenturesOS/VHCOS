"""
Naukri Profile Regex Parser - Zero-LLM extraction for Naukri Resdex profiles.

Handles 3 work experience formats:
  A) CV pipe: "Title | Company"
  B) Naukri Resdex: "Title at Company"
  C) CV block: "Company\nTitle\nDATE - PRESENT\n* Description"

Returns the same dict schema as bedrock_service.extract_full_profile().
"""
import re
import logging

logger = logging.getLogger(__name__)

INDIAN_CITIES = {
    'mumbai', 'delhi', 'bangalore', 'bengaluru', 'hyderabad', 'chennai', 'kolkata',
    'pune', 'ahmedabad', 'jaipur', 'lucknow', 'kanpur', 'nagpur', 'indore',
    'thane', 'bhopal', 'visakhapatnam', 'pimpri', 'patna', 'vadodara',
    'ghaziabad', 'ludhiana', 'agra', 'nashik', 'faridabad', 'meerut',
    'rajkot', 'varanasi', 'srinagar', 'aurangabad', 'dhanbad', 'amritsar',
    'allahabad', 'ranchi', 'howrah', 'coimbatore', 'jabalpur', 'gwalior',
    'vijayawada', 'jodhpur', 'madurai', 'raipur', 'kota', 'chandigarh',
    'guwahati', 'solapur', 'noida', 'gurugram', 'gurgaon', 'greater noida',
    'mysore', 'mysuru', 'tiruchirappalli', 'mangalore', 'mangaluru',
    'hubli', 'dharwad', 'salem', 'warangal', 'guntur', 'thiruvananthapuram',
    'trivandrum', 'kochi', 'cochin', 'dehradun', 'shimla', 'jammu',
    'bikaner', 'udaipur', 'bhilai', 'navi mumbai', 'panaji', 'goa',
    'bhubaneswar', 'cuttack', 'siliguri', 'moradabad', 'gorakhpur',
    'secunderabad', 'new delhi', 'nct', 'ncr', 'tiruvallur',
    'ernakulam', 'surat', 'kolhapur', 'nanded', 'bhavnagar',
    'pondicherry', 'puducherry', 'gangtok', 'imphal', 'shillong', 'aizawl',
    'itanagar', 'agartala', 'kohima', 'dimapur', 'durgapur',
}

# Regex to detect residential address lines (should NEVER be treated as company/employer)
_ADDRESS_RE = re.compile(
    r'Residence\s*Add|C/o\b|H[\.\s]*No[\.\-]|Flat\s*No|Plot\s*No|Block\s*[A-Z\d]|'
    r'House\s*No|Street\s*No|Lane\s*No|Sector\s*\d|Pin\s*Code|Zip\s*Code|'
    r'Colony|Apartment|Apt\.|Floor\s*\d|Village|Tehsil|Taluk|Mandal|'
    r'Post\s*Office|P\.?O\.\s|^\d+[/-]\d+|Ward\s*No',
    re.IGNORECASE
)

# Garbage skill filter — these should never appear in key_skills
_SKILL_GARBAGE_RE = re.compile(
    r'^\d{2}[-/]|^\d{4,}|@[\w.]|\.com$|\.in$|naukri|resdex|'
    r'resume|curriculum|vitae|^http|^www\.|save\d|'
    r'^(male|female|married|single|unmarried|gender|age|dob|date of birth)$|'
    r'^\d+\s*(yrs?|years?|months?|lacs?|lpa|crore|lac|lakhs?|days?)$|'
    r'residence|c/o|h\.?no|colony|apartment|address|pin\s*code|'
    r'^(present|current|previous|last|till|from|since|to)$|'
    r'^\d+$',
    re.IGNORECASE
)


def _is_address_line(line):
    """Return True if the line is a residential address, not a company or title."""
    return bool(_ADDRESS_RE.search(line))


def _clean_skill(s):
    """Return cleaned skill string, or None if it's garbage."""
    s = s.strip().strip('.,;:').strip()
    if not s or len(s) < 2 or len(s) > 50:
        return None
    if _SKILL_GARBAGE_RE.search(s):
        return None
    # Reject sentence fragments starting with conjunctions / prepositions / articles
    if re.match(r'^(and|or|in|for|to|of|with|the|a|an|by|at|on|is|are|was|were|has|have|had|do|does|did|that|this|also|such|as|its|into|from)\b', s, re.IGNORECASE):
        return None
    # Reject fragments starting with lowercase (gerund phrases acting as sentence pieces)
    # e.g., "analyzing technical specifications", "conducting effective supplier negotiations"
    if re.match(r'^[a-z]', s) and len(s.split()) > 2:
        return None
    # Reject if too many words — real skills are typically 1-4 words
    if len(s.split()) > 5:
        return None
    # Reject sentence-like patterns (verb + object)
    if re.match(r'^(Proficient|Adept|Demonstrated|Experienced|Well-versed|Skilled|Expert|Proven|Capable)\b', s, re.IGNORECASE) and len(s.split()) > 3:
        return None
    # Skip if mostly numbers/punctuation
    alpha = sum(1 for c in s if c.isalpha())
    if alpha < len(s) * 0.4:
        return None
    return s

# Universal date pattern for all Naukri/CV formats
# Matches: "Jan 2020 - Present", "Jan '25 till date", "JAN, 25 - PRESENT", "Sep '21 till Dec '22"
DATE_PAT = re.compile(
    r"(\w{3,9}\.?,?\s*'?\d{2,4})\s*(?:[-\u2013]|till)\s*"
    r"(\w{3,9}\.?,?\s*'?\d{2,4}|present|current|till\s*date|date)",
    re.IGNORECASE
)


def _parse_naukri_header(text):
    header = {}
    # Expanded header window — some Naukri pages prepend nav/chrome text, so the
    # top-card data can sit at char 2000+. 4000 is a safe upper bound (any normal
    # top card sits within the first 4KB of extracted DOM text).
    HEADER_WINDOW = text[:4000]

    # ── Layer A: Labeled top-card fields (highest signal — works for ANY layout) ──
    # Naukri's modern top-card uses labels: "Experience\n19 Years", "Current CTC\n₹ 25 Lacs",
    # "Notice Period\n3 Months". These win over adjacency because they're unambiguous.
    lbl_exp = re.search(
        r'(?:Total\s*)?Experience\s*[:\n\r\t ]+\s*(\d{1,2})\s*(?:Years?|yrs?)(?:\s*(\d{1,2})\s*(?:Months?|mos?))?',
        HEADER_WINDOW, re.IGNORECASE,
    )
    if lbl_exp:
        y = int(lbl_exp.group(1))
        m = int(lbl_exp.group(2)) if lbl_exp.group(2) else 0
        header['experience_years'] = round(y + m / 100, 2) if m else float(y)
        header['_exp_source'] = 'regex_labeled'
    lbl_ctc = re.search(
        r'(?:Current\s*CTC|Present\s*CTC|CTC)\s*[:\n\r\t ]+\s*[\u20B9]?\s*([\d.]+)\s*(Lacs?|Lakhs?|LPA|Lac|Cr|Crore|L)\b',
        HEADER_WINDOW, re.IGNORECASE,
    )
    if lbl_ctc:
        val = float(lbl_ctc.group(1))
        unit = lbl_ctc.group(2).lower()
        header['current_ctc'] = int(val * 10000000) if unit in ('cr', 'crore') else int(val * 100000)
    lbl_exp_ctc = re.search(
        r'(?:Expected\s*CTC|Expected\s*Salary|Expects?)\s*[:\n\r\t ]+\s*[\u20B9]?\s*([\d.]+)\s*(Lacs?|Lakhs?|LPA|Lac|Cr|Crore|L)\b',
        HEADER_WINDOW, re.IGNORECASE,
    )
    if lbl_exp_ctc:
        val = float(lbl_exp_ctc.group(1))
        unit = lbl_exp_ctc.group(2).lower()
        header['expected_ctc'] = int(val * 10000000) if unit in ('cr', 'crore') else int(val * 100000)
    lbl_notice = re.search(
        r'Notice\s*Period\s*[:\n\r\t ]+\s*(Immediate(?:ly)?|15\s*Days?\s*or\s*less|\d{1,3}\s*Days?|\d{1,2}\s*Months?|\d{1,2}\s*Weeks?|Serving\s*Notice)',
        HEADER_WINDOW, re.IGNORECASE,
    )
    if lbl_notice:
        raw_np = lbl_notice.group(1).strip()
        if re.match(r'immediat', raw_np, re.IGNORECASE):
            header['notice_period'] = "Immediate"
            header['notice_period_days'] = 0
        elif re.match(r'15\s*days?\s*or\s*less', raw_np, re.IGNORECASE):
            header['notice_period'] = "15 Days or less"
            header['notice_period_days'] = 15
        elif re.match(r'serving', raw_np, re.IGNORECASE):
            header['notice_period'] = "Serving Notice"
            header['notice_period_days'] = 0
        else:
            nm = re.match(r'(\d{1,3})\s*(Days?|Months?|Weeks?)', raw_np, re.IGNORECASE)
            if nm:
                n = int(nm.group(1))
                u = nm.group(2).lower()
                if u.startswith('day') and 0 <= n <= 180:
                    header['notice_period'] = f"{n} Days"
                    header['notice_period_days'] = n
                elif u.startswith('month') and 0 < n <= 12:
                    header['notice_period'] = f"{n} Month{'s' if n != 1 else ''}"
                    header['notice_period_days'] = n * 30
                elif u.startswith('week'):
                    header['notice_period'] = f"{n} Week{'s' if n != 1 else ''}"
                    header['notice_period_days'] = n * 7

    # ── Experience Years — Priority-0 adjacency signature (structural) ──
    # Naukri top card ALWAYS places experience immediately before currency:
    # "8y ₹14 Lacs", "22y  ₹60 Lacs", "10+ years ₹18 Lacs". Role durations
    # are NEVER followed by currency — they're followed by company names.
    # So this adjacency pattern is an unambiguous top-card signature.
    adjacency_patterns = [
        # "8y" / "22y" directly adjacent to ₹ / Lacs / LPA (max 5 chars gap)
        (r'(?<![A-Za-z0-9])(\d{1,2})\s*y\s{0,5}(?=[\u20B9]|\bRs\b|\bINR\b|\d+\s*(?:Lacs?|Lakhs?|LPA|Cr|Crore))', None),
        # "8y 3m" adjacent to currency
        (r'(?<![A-Za-z0-9])(\d{1,2})\s*y\s+(\d{1,2})\s*m\s{0,5}(?=[\u20B9]|\bRs\b|\bINR\b|\d+\s*(?:Lacs?|Lakhs?|LPA))', 'ym'),
        # "8 years" / "10+ yrs" adjacent to currency
        (r'(\d{1,2}(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s{0,5}(?=[\u20B9]|\bRs\b|\bINR\b|\d+\s*(?:Lacs?|Lakhs?|LPA))', None),
    ]
    for pat, kind in adjacency_patterns:
        if header.get('experience_years') is not None:
            break  # Label-based already won — don't override
        m = re.search(pat, text[:2000], re.IGNORECASE)
        if not m:
            continue
        if kind == 'ym':
            years = int(m.group(1))
            months = int(m.group(2))
            header['experience_years'] = round(years + (months / 100), 2)
            header['_exp_source'] = 'regex_adjacency_ym'
        else:
            header['experience_years'] = float(m.group(1))
            header['_exp_source'] = 'regex_adjacency'
        break

    # ── Fallback — section-cut bounded regex (when adjacency misses) ──
    section_cut = re.search(
        r'\b(?:Professional\s*Experience|Work\s*Experience|Employment\s*History|Education|Academic|Key\s*Skills|IT\s*Skills)\b',
        text, re.IGNORECASE
    )
    header_scan = text[:section_cut.start()] if section_cut else text[:1200]
    # Skip the rest of the regex layers if adjacency already caught it
    if header.get('experience_years') is None:
        # Layer 1: compact "16y 3m" / "0y 8m" — most precise when present
        exp_m = re.search(r'(?<![A-Za-z0-9])(\d{1,2})\s*y\s+(\d{1,2})\s*m(?![A-Za-z0-9])', header_scan, re.IGNORECASE)
        if exp_m:
            years = int(exp_m.group(1))
            months = int(exp_m.group(2))
            header['experience_years'] = round(years + (months / 100), 2)
            header['_exp_source'] = 'regex_compact_ym'
        else:
            # Layer 2: whole-year "16y" / "22y"
            exp_m = re.search(r'(?<![A-Za-z0-9])(\d{1,2})\s*y(?![A-Za-z0-9ears])', header_scan, re.IGNORECASE)
            if exp_m:
                header['experience_years'] = float(exp_m.group(1))
                header['_exp_source'] = 'regex_y_only'
            else:
                # Layer 3: full-word "16 years" / "16+ years"
                exp_m = re.search(r'(\d{1,2}(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b', header_scan, re.IGNORECASE)
                if exp_m:
                    v = float(exp_m.group(1))
                    if v >= 0:
                        header['experience_years'] = v
                        header['_exp_source'] = 'regex_years_word'
    # CTC (current) — ₹ optional, covers "60 Lacs", "₹60 Lacs", "60 LPA"
    if header.get('current_ctc') is None:
        ctc_m = re.search(r'[\u20B9]?\s*([\d.]+)\s*(Lacs?|LPA|Lac|Cr|Crore)\b', text[:4000], re.IGNORECASE)
        if ctc_m:
            val = float(ctc_m.group(1))
            unit = ctc_m.group(2).lower()
            header['current_ctc'] = int(val * 10000000) if unit in ('cr', 'crore') else int(val * 100000)
    if header.get('expected_ctc') is None:
        exp_ctc_m = re.search(r'expects?[:\s]*[\u20B9]?\s*([\d.]+)\s*(Lacs?|LPA|Lac|Cr|Crore)', text, re.IGNORECASE)
        if exp_ctc_m:
            val = float(exp_ctc_m.group(1))
            unit = exp_ctc_m.group(2).lower()
            header['expected_ctc'] = int(val * 10000000) if unit in ('cr', 'crore') else int(val * 100000)
    loc_m = re.search(r'(?:Lacs?|LPA|Cr|Crore)\)?\.?\s*([A-Z][a-z]+(?:[ ,]+[A-Z][a-z]+){0,2})\s+(?:Current|Remote)', text)
    if loc_m:
        loc = loc_m.group(1).strip().rstrip(',')
        if len(loc) > 2 and loc.lower() not in ('the', 'and', 'for', 'save'):
            header['location'] = loc
    # Labeled Location fallback — "Current Location\nRudrapur, Pantnagar"
    if header.get('location') is None:
        lbl_loc = re.search(
            r'(?:Current\s*Location|Location|Based\s*in|City)\s*[:\n\r\t ]+\s*([A-Za-z][A-Za-z\s,.\-/()]{2,80}?)(?:\n|$)',
            text[:4000], re.IGNORECASE,
        )
        if lbl_loc:
            loc = lbl_loc.group(1).strip().rstrip(',').rstrip('.')
            # Reject known non-locations
            if (len(loc) > 2 and len(loc) < 80
                and loc.lower() not in ('the', 'and', 'for', 'save', 'not available', 'unknown', 'n/a')
                and not re.search(r'\d{4,}|@|http', loc)):
                header['location'] = loc
    notice_patterns = [
        re.compile(r"since\s+\w+\s+\d{4}\s*(\d{1,2})\s*Months?", re.IGNORECASE),
        re.compile(r"'?\d{2,4}\s*(\d{1,2})\s*Months?\s*(?:Highest|Pref|UG|PG|Grad)", re.IGNORECASE),
        re.compile(r"(\d{1,2})\s*Months?\s*(?:Highest|Pref|UG|PG|Grad)", re.IGNORECASE),
        re.compile(r"(?:Notice|notice)\s*(?:Period)?\s*[:\-]?\s*(\d{1,2})\s*Months?", re.IGNORECASE),
        re.compile(r"(\d{1,3})\s*Days?\s*(?:Highest|Pref|UG|PG)", re.IGNORECASE),
        re.compile(r"Immediate\s*(?:Joiner|joiner)", re.IGNORECASE),
    ]
    if header.get('notice_period') is None:
      for pat in notice_patterns:
        m = pat.search(text[:2000])
        if m:
            if 'immediate' in pat.pattern.lower():
                header['notice_period'] = "Immediate"
                header['notice_period_days'] = 0
                break
            start = max(0, m.start() - 20)
            context = text[start:m.start()].lower()
            if 'year' not in context and 'yrs' not in context:
                num = int(m.group(1))
                if 'day' in pat.pattern.lower():
                    if 0 < num <= 180:
                        header['notice_period'] = f"{num} Days"
                        header['notice_period_days'] = num
                        break
                elif 0 < num <= 12:
                    header['notice_period'] = f"{num} Month{'s' if num != 1 else ''}"
                    header['notice_period_days'] = num * 30
                    break
    # sections) for common phrasings: "Immediate", "3 Months", "15 Days",
    # "15 Days or less". Requires no adjacent "year" to avoid false positives.
    if not header.get('notice_period'):
        section_cut_local = re.search(
            r'\b(?:Professional\s*Experience|Work\s*Experience|Employment\s*History|Education|Academic|Key\s*Skills|IT\s*Skills)\b',
            text, re.IGNORECASE,
        )
        np_region = text[:section_cut_local.start()] if section_cut_local else text[:1500]
        # (pattern, canonical label, days). Order matters — most specific first.
        np_patterns = [
            (r'\b(\d{1,2})\s*Months?\s*or\s*less\b', None, None),       # "2 months or less" → keep as months
            (r'\b15\s*Days?\s*or\s*less\b', "15 Days or less", 15),
            (r'\bImmediate(?:ly)?(?:\s*Joiner)?\b', "Immediate", 0),
            (r'\b(?:Available|Ready)\s*(?:to|for)\s*Join\b', "Immediate", 0),
            (r'(?<![A-Za-z])(\d{1,3})\s*Days?(?![A-Za-z])', None, None),
            (r'(?<![A-Za-z])(\d{1,2})\s*Months?(?![A-Za-z])', None, None),
        ]
        for pat, fixed_label, fixed_days in np_patterns:
            m = re.search(pat, np_region, re.IGNORECASE)
            if not m:
                continue
            if fixed_label:
                header['notice_period'] = fixed_label
                header['notice_period_days'] = fixed_days
                break
            num = int(m.group(1))
            # Reject false positives (e.g. "24 months experience")
            ctx = np_region[max(0, m.start()-30):m.start()].lower()
            if any(w in ctx for w in ('year', 'yrs', 'experience', 'exp ')):
                continue
            if 'day' in pat.lower():
                if 0 <= num <= 180:
                    header['notice_period'] = f"{num} Days"
                    header['notice_period_days'] = num
                    break
            else:
                if 0 < num <= 12:
                    header['notice_period'] = f"{num} Month{'s' if num != 1 else ''}"
                    header['notice_period_days'] = num * 30
                    break
    # Employer & Designation from Naukri header
    # Pattern: "<Company> since <Month> <Year>" — only match clean separate text
    since_m = re.search(r'(?:^|\n)\s*([A-Z][^\n₹\d]{2,50}?)\s+since\s+\w{3,}\s+\d{2,4}', text, re.MULTILINE)
    if since_m:
        co = since_m.group(1).strip()
        if not _is_address_line(co) and 2 < len(co) < 50 and not re.search(r'Save|₹|\d{3,}', co):
            header['current_employer'] = co
    # Pattern: "Current  <Designation>  at  <Company>" (all on one line — common
    # Naukri top-card format). Preferred over the multi-line "Current\n<...>"
    # form because it's more specific.
    inline_m = re.search(
        r'(?:^|\n)\s*Current\s{1,}(.+?)\s+at\s+',
        text, re.IGNORECASE | re.MULTILINE,
    )
    if inline_m:
        desig = inline_m.group(1).strip()
        # Allow designations that start with digits (e.g. "2W R&D Trims And Fuel System");
        # only reject very specific junk prefixes.
        if desig and 2 < len(desig) < 80 and not re.match(r'^(Save|http|\+|₹|===)', desig):
            header['current_designation'] = desig
    # Pattern: "Current\n<Designation>" (multi-line) — fallback
    # IMPORTANT: reject when the next line is a label word (CTC, Location, Salary, Employer)
    # as the Naukri modern top-card stacks labels like "Current CTC" on their own line.
    if not header.get('current_designation'):
        curr_m = re.search(r'Current\s*\n\s*(.+?)(?:\n|\Z)', text)
        if curr_m:
            desig = curr_m.group(1).strip()
            _label_word = re.match(
                r'^(CTC|Salary|Location|City|Employer|Company|Organization|Industry|Department|Package|Compensation|Designation|Role|Title)\b',
                desig, re.IGNORECASE,
            )
            if desig and len(desig) < 80 and not _label_word and not re.match(r'^(Save|http|\+|\d|₹|===)', desig):
                header['current_designation'] = desig
    return header


def _is_current_role(to_date_str):
    """Check if to_date indicates a current role (not a specific past date)."""
    if not to_date_str:
        return False
    val = to_date_str.strip().lower()
    return val in ('present', 'current', 'till date', 'date') or val.startswith('present')


def _parse_work_experience(exp_text):
    """Parse work experience from any Naukri/CV format.

    Three detection paths (checked in order):
      A) Pipe:  "Title | Company"
      B) At:    "Title at Company"
      C) Block: Date-anchored state machine for "Company\\nTitle\\nDate\\nDesc"
    """
    work_exp = []
    if not exp_text or len(exp_text.strip()) < 20:
        return work_exp

    has_pipe = bool(re.search(r'^.+?\s*\|\s*.+?$', exp_text, re.MULTILINE))
    has_at_fmt = bool(re.search(r'^.+?\s+at\s+[A-Z].{3,}$', exp_text, re.MULTILINE))

    _gap_re = re.compile(r'^\d+\s*months?\s*gap', re.IGNORECASE)

    def _clean_desc(line):
        return re.sub(r'^[*\u2022\-]\s*|^[a-z]\.\s*', '', line).strip()

    if has_pipe:
        # Format A: "Title | Company"
        entries_raw = re.split(r'\n(?=[^\s\n].*?\|)', exp_text)
        for entry_text in entries_raw:
            lines = [l.strip() for l in entry_text.strip().split('\n') if l.strip()]
            if not lines:
                continue
            e = {"company": None, "designation": None, "from_date": None, "to_date": None, "is_current": False, "description": None}
            tm = re.match(r'^(.+?)\s*\|\s*(.+?)$', lines[0])
            if tm:
                e["designation"] = tm.group(1).strip()
                e["company"] = tm.group(2).strip()
            desc = []
            for line in lines[1:]:
                dm = DATE_PAT.search(line)
                if dm and not e["from_date"]:
                    e["from_date"], e["to_date"] = dm.group(1), dm.group(2)
                    e["is_current"] = _is_current_role(dm.group(2))
                else:
                    c = _clean_desc(line)
                    if c and len(c) > 3:
                        desc.append(c)
            if desc:
                e["description"] = ' '.join(desc)
            if e.get("company") or e.get("designation"):
                work_exp.append(e)

    elif has_at_fmt:
        # Format B: "Title at Company" (Naukri Resdex)
        entry_start = re.compile(r'^(.+?)\s+at\s+([A-Z].{2,}?)\.?\s*$', re.MULTILINE)
        matches = list(entry_start.finditer(exp_text))
        for idx, match in enumerate(matches):
            start = match.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(exp_text)
            lines = [l.strip() for l in exp_text[start:end].strip().split('\n') if l.strip()]
            e = {"company": match.group(2).strip(), "designation": match.group(1).strip(), "from_date": None, "to_date": None, "is_current": False, "description": None}
            desc = []
            for line in lines[1:]:
                if _gap_re.match(line):
                    continue
                dm = DATE_PAT.search(line)
                if dm and not e["from_date"]:
                    e["from_date"], e["to_date"] = dm.group(1), dm.group(2)
                    e["is_current"] = _is_current_role(dm.group(2))
                else:
                    c = _clean_desc(line)
                    if c and len(c) > 3:
                        desc.append(c)
            if desc:
                e["description"] = ' '.join(desc)
            if e.get("company"):
                work_exp.append(e)

    else:
        # Format C: Date-anchored block parser
        # Handles "Company\nTitle\nDate\nDescription" without | or "at"
        #
        # Strategy:
        #   1. Split text by blank lines into chunks
        #   2. If each chunk has 1 date → parse chunk (Company/Title before date, Desc after)
        #   3. If a chunk has multiple dates (no blank lines) → date-anchored 2-pass
        #   4. Fallback: company-keyword splitting (if no dates at all)

        chunks = re.split(r'\n\s*\n', exp_text.strip())
        chunks = [c.strip() for c in chunks if c.strip()]

        def _parse_single_date_chunk(lines):
            """Parse a chunk that contains exactly 1 date line."""
            e = {"company": None, "designation": None, "from_date": None,
                 "to_date": None, "is_current": False, "description": None}
            date_idx = None
            for i, line in enumerate(lines):
                if _gap_re.match(line):
                    continue
                if DATE_PAT.search(line):
                    date_idx = i
                    dm = DATE_PAT.search(line)
                    e["from_date"], e["to_date"] = dm.group(1), dm.group(2)
                    e["is_current"] = _is_current_role(dm.group(2))
                    break
            if date_idx is not None:
                headers = [l for l in lines[:date_idx] if not _gap_re.match(l) and not _is_address_line(l)]
                if len(headers) >= 2:
                    e["company"], e["designation"] = headers[-2], headers[-1]
                elif headers:
                    e["company"] = headers[0]
                desc = []
                for line in lines[date_idx + 1:]:
                    if _gap_re.match(line) or _is_address_line(line):
                        continue
                    c = _clean_desc(line)
                    if c and len(c) > 3:
                        desc.append(c)
                if desc:
                    e["description"] = ' '.join(desc)
            else:
                valid = [l for l in lines if not _is_address_line(l)]
                if valid:
                    e["company"] = valid[0]
                if len(valid) > 1:
                    e["designation"] = valid[1]
            return e if (e.get("company") or e.get("designation")) else None

        def _parse_multi_date_block(lines):
            """Date-anchored 2-pass parser for dense text with multiple dates."""
            results = []
            date_indices = []
            for i, ln in enumerate(lines):
                if _gap_re.match(ln):
                    continue
                if DATE_PAT.search(ln):
                    date_indices.append(i)
            if not date_indices:
                return results

            # Pass 1: For each date, claim up to 2 header lines above it
            used = set()
            entry_meta = []
            for di, d_idx in enumerate(date_indices):
                dm = DATE_PAT.search(lines[d_idx])
                from_d = dm.group(1) if dm else None
                to_d = dm.group(2) if dm else None
                used.add(d_idx)

                floor = (date_indices[di - 1] + 1) if di > 0 else 0
                headers = []
                for j in range(d_idx - 1, floor - 1, -1):
                    if j in used:
                        break
                    if _gap_re.match(lines[j]) or _is_address_line(lines[j]):
                        used.add(j)
                        continue
                    if re.match(r'^[*\u2022\-]', lines[j]):
                        break
                    headers.insert(0, j)
                    if len(headers) >= 2:
                        break
                for h in headers:
                    used.add(h)

                company = lines[headers[0]] if len(headers) >= 2 else (lines[headers[0]] if headers else None)
                designation = lines[headers[1]] if len(headers) >= 2 else None
                entry_meta.append({
                    "d_idx": d_idx, "from_date": from_d, "to_date": to_d,
                    "is_current": _is_current_role(to_d),
                    "company": company, "designation": designation,
                    "first_header": min(headers) if headers else d_idx,
                })

            # Pass 2: Description = un-used lines between date+1 and next entry's first header
            for ei, meta in enumerate(entry_meta):
                desc_start = meta["d_idx"] + 1
                if ei + 1 < len(entry_meta):
                    desc_end = entry_meta[ei + 1]["first_header"]
                else:
                    desc_end = len(lines)
                desc = []
                for j in range(desc_start, desc_end):
                    if j in used or j >= len(lines):
                        continue
                    if _gap_re.match(lines[j]):
                        continue
                    c = _clean_desc(lines[j])
                    if c and len(c) > 3:
                        desc.append(c)
                e = {
                    "company": meta["company"], "designation": meta["designation"],
                    "from_date": meta["from_date"], "to_date": meta["to_date"],
                    "is_current": meta["is_current"],
                    "description": ' '.join(desc) if desc else None,
                }
                if e.get("company") or e.get("designation"):
                    results.append(e)
            return results

        # Dispatch per chunk
        for chunk in chunks:
            lines = [l.strip() for l in chunk.split('\n') if l.strip()]
            if not lines:
                continue
            n_dates = sum(1 for l in lines if DATE_PAT.search(l) and not _gap_re.match(l))
            if n_dates == 0:
                continue
            elif n_dates == 1:
                entry = _parse_single_date_chunk(lines)
                if entry:
                    work_exp.append(entry)
            else:
                work_exp.extend(_parse_multi_date_block(lines))

        # Fallback: company-keyword splitting (when no dates are found above)
        if not work_exp:
            company_kw = re.compile(
                r'(?:Ltd|Inc|Pvt|Corp|Bank|Services|Insurance|Technologies|Solutions|Consulting|Group|Limited|Company|Finserv|LLP)',
                re.IGNORECASE,
            )
            all_lines = [l.strip() for l in exp_text.split('\n') if l.strip()]
            entries, cur = [], []
            for line in all_lines:
                if (len(line) < 70 and not re.match(r'^[*\u2022\-]|^[a-z]\.', line) and
                        not DATE_PAT.search(line) and line[0:1].isupper() and company_kw.search(line) and cur):
                    entries.append(cur)
                    cur = []
                cur.append(line)
            if cur:
                entries.append(cur)
            for el in entries:
                if not el:
                    continue
                e = {"company": None, "designation": None, "from_date": None, "to_date": None, "is_current": False, "description": None}
                desc = []
                for i, line in enumerate(el):
                    dm = DATE_PAT.search(line)
                    if dm and not e["from_date"]:
                        e["from_date"], e["to_date"] = dm.group(1), dm.group(2)
                        e["is_current"] = _is_current_role(dm.group(2))
                    elif i == 0:
                        e["company"] = line
                    elif not e["designation"] and len(line) < 80 and not re.match(r'^[*\u2022\-]|^[a-z]\.', line):
                        e["designation"] = line
                    else:
                        c = _clean_desc(line)
                        if c and len(c) > 3:
                            desc.append(c)
                if desc:
                    e["description"] = ' '.join(desc)
                if e.get("company") or e.get("designation"):
                    work_exp.append(e)

    return work_exp[:15]


def extract_full_profile_regex(raw_text, recruiter_phone=None, recruiter_email=None):
    text = raw_text or ""
    result = {
        "candidate_phone": None, "candidate_email": None, "candidate_name": None,
        "current_designation": None, "current_employer": None,
        "current_department": None, "current_industry": None,
        "location": None, "headline": None, "profile_summary": None,
        "current_ctc": None, "expected_ctc": None,
        "notice_period": None, "notice_period_days": None, "is_serving_notice": False,
        "experience_years": None, "key_skills": [], "work_experience": [],
        "education": [], "certifications": [], "languages": [],
        "preferred_locations": [], "date_of_birth": None, "gender": None,
        "marital_status": None, "highest_qualification": None,
        "confidence": "medium", "phone_source": None,
    }

    recruiter_phone_norm = re.sub(r'[\s\-\+\(\)]', '', str(recruiter_phone or ''))[-10:]
    recruiter_email_lower = (recruiter_email or "").lower().strip()
    header = _parse_naukri_header(text)

    # ── Name ──
    name_before_save = re.match(r'^(.+?)(?=Save\d)', text)
    if name_before_save:
        nc = name_before_save.group(1).strip()
        words = nc.split()
        if 2 <= len(words) <= 5 and all(w[0].isupper() for w in words if w.isalpha() and len(w) > 1):
            if not any(c in nc for c in "@./:0123456789"):
                result["candidate_name"] = nc
    if not result["candidate_name"]:
        for line in text.split("\n")[:15]:
            line = line.strip()
            if not line or len(line) < 3:
                continue
            clean_line = re.sub(r'\s*Save\d.*$', '', line).strip()
            if clean_line and 2 <= len(clean_line.split()) <= 5:
                words = clean_line.split()
                if not any(c in clean_line for c in "@./:0123456789"):
                    if all(w[0].isupper() for w in words if w.isalpha() and len(w) > 1):
                        result["candidate_name"] = clean_line
                        break

    # ── Email ──
    emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', text)
    blocked = ['naukri.com', 'vhc.in', 'noreply', 'support@']
    for email in emails:
        el = email.lower()
        if any(b in el for b in blocked):
            continue
        if el == recruiter_email_lower:
            continue
        result["candidate_email"] = email
        break

    # ── Phone ──
    phones = re.findall(r'(?:\+91[\s\-]?)?(?:0)?([6-9]\d{9})', text)
    for phone in phones:
        if phone[-10:] != recruiter_phone_norm:
            result["candidate_phone"] = phone[-10:]
            result["phone_source"] = "regex extraction"
            break

    # ── Experience Years ──
    if header.get('experience_years') is not None:
        result["experience_years"] = float(header['experience_years'])
        if header.get('_exp_source'):
            result["_exp_source"] = header['_exp_source']
    else:
        for pat in [r'(\d+)\s*(?:years?|yrs?)[\s.,]*(\d+)?\s*(?:months?|mos?)?',
                    r'Experience\s*[:\-]\s*(\d+)\s*(?:years?|yrs?)',
                    r'(\d+)\s*Year\(s\)\s*(\d+)?\s*Month',
                    r'Total\s*Exp\w*\s*[:\-]?\s*(\d+)\s*(?:years?|yrs?)']:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                years = int(m.group(1))
                months = int(m.group(2)) if m.lastindex >= 2 and m.group(2) else 0
                result["experience_years"] = round(years + months / 12, 1)
                break

    # ── CTC ──
    if header.get('current_ctc'):
        result["current_ctc"] = header['current_ctc']
    else:
        for pat in [r'[\u20B9]\s*([\d.]+)\s*(Lacs?|LPA|Lac|Cr|Crore)\s*\(expects',
                    r'[\u20B9]\s*([\d.]+)\s*(Lacs?|LPA|Lac|Cr|Crore)',
                    r'(?:Current|Present)\s*(?:CTC|Salary|Annual\s*Salary|Compensation)\s*[:\-]?\s*(?:Rs\.?|INR|[\u20B9])?\s*([\d,.]+)\s*(Lac|Lakh|LPA|Lacs?|Cr|Crore|L)',
                    r'(?:CTC|Salary)\s*[:\-]?\s*(?:Rs\.?|INR|[\u20B9])?\s*([\d,.]+)\s*(Lac|Lakh|LPA|Lacs?|Cr|Crore|L)',
                    r'(?:Compensation|Package)\s*[:\-]?\s*(?:Rs\.?|INR|[\u20B9])?\s*([\d,.]+)\s*(Lac|Lakh|LPA|Lacs?|Cr|Crore|L)',
                    r'INR\s*([\d,.]+)\s*(Lac|Lakh|LPA|Lacs?|Cr|Crore|L)',
                    r'Rs\.?\s*([\d,.]+)\s*(Lac|Lakh|LPA|Lacs?|Cr|Crore|L)']:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                try:
                    val = float(m.group(1).replace(',', ''))
                    unit = m.group(2).lower()
                    result["current_ctc"] = int(val * 10000000) if unit in ('cr', 'crore') else int(val * 100000)
                except ValueError:
                    pass
                break

    # ── Expected CTC ──
    if header.get('expected_ctc'):
        result["expected_ctc"] = header['expected_ctc']
    else:
        for pat in [r'expects?[:\s]*[\u20B9]?\s*([\d.]+)\s*(Lacs?|LPA|Lac|Cr|Crore)',
                    r'Expected\s*(?:CTC|Salary|Annual\s*Salary|Compensation)\s*[:\-]?\s*(?:Rs\.?|INR|[\u20B9])?\s*([\d,.]+)\s*(Lac|Lakh|LPA|Lacs?|Cr|Crore|L)',
                    r'Exp\.?\s*(?:CTC|Salary)\s*[:\-]?\s*(?:Rs\.?|INR|[\u20B9])?\s*([\d,.]+)\s*(Lac|Lakh|LPA|Lacs?|Cr|Crore|L)',
                    r'Looking\s*for\s*(?:Rs\.?|INR|[\u20B9])?\s*([\d,.]+)\s*(Lac|Lakh|LPA|Lacs?|Cr|Crore|L)',
                    r'Desired\s*(?:CTC|Salary)\s*[:\-]?\s*(?:Rs\.?|INR|[\u20B9])?\s*([\d,.]+)\s*(Lac|Lakh|LPA|Lacs?|Cr|Crore|L)']:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                try:
                    val = float(m.group(1).replace(',', ''))
                    unit = m.group(2).lower()
                    result["expected_ctc"] = int(val * 10000000) if unit in ('cr', 'crore') else int(val * 100000)
                except ValueError:
                    pass
                break

    # ── Notice Period (header wins — it's already parsed from top-card labels) ──
    # The header parser has higher signal. Only run the global loop if the header failed.
    notice_found = False
    if header.get('notice_period'):
        result["notice_period"] = header['notice_period']
        result["notice_period_days"] = header.get('notice_period_days')
        notice_found = True
    if not notice_found:
     for pat, tag in [(r'Notice\s*Period\s*[:\-]\s*(.+?)(?:\n|$)', 'labeled'),
                     (r'Notice\s*[:\-]\s*(.+?)(?:\n|$)', 'labeled2'),
                     (r'(\d{1,2})\s*Months?\s*(?:Notice|notice)', 'months'),
                     (r'(?:Notice\s*(?:Period)?)\s*[:\-]?\s*(\d{1,3})\s*(?:Days?|days)', 'days'),
                     (r'(\d{1,3})\s*Days?\s*(?:Notice|notice)', 'days'),
                     (r'(\d{1,2})\s*(?:Week|Weeks)\s*(?:Notice|notice)', 'weeks'),
                     (r'Available\s*(?:to\s*join|in)\s*(\d{1,2})\s*(?:Months?|Days?|Weeks?)', 'available'),
                     (r'(?:Can\s*join|Joining)\s*(?:in|within)\s*(\d{1,2})\s*(?:Months?|Days?|Weeks?)', 'available'),
                     (r'Immediate(?:ly)?\s*(?:Joiner|Available|available)?', 'immediate'),
                     (r'Currently\s*Serving\s*Notice', 'serving'),
                     (r'Serving\s*Notice\s*Period', 'serving2'),
                     (r'Buyout\s*(?:Option|Available)', 'serving'),
                     (r'(?:^|\n)\s*(\d{1,2})\s*months?\s*$', 'months_standalone')]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            if tag == 'immediate':
                result["notice_period"], result["notice_period_days"] = "Immediate", 0
            elif tag in ('serving', 'serving2'):
                result["notice_period"], result["is_serving_notice"] = "Serving Notice", True
            elif tag == 'months' or tag == 'months_standalone':
                mo = int(m.group(1))
                if 0 < mo <= 6:
                    result["notice_period"] = f"{mo} Month{'s' if mo != 1 else ''}"
                    result["notice_period_days"] = mo * 30
                else:
                    continue
            elif tag == 'days':
                days = int(m.group(1))
                if 0 < days <= 180:
                    result["notice_period"] = f"{days} Days"
                    result["notice_period_days"] = days
                else:
                    continue
            elif tag == 'weeks':
                weeks = int(m.group(1))
                result["notice_period"] = f"{weeks} Week{'s' if weeks != 1 else ''}"
                result["notice_period_days"] = weeks * 7
            elif tag == 'available':
                num = int(m.group(1))
                unit = m.group(0).lower()
                if 'day' in unit:
                    result["notice_period"] = f"{num} Days"
                    result["notice_period_days"] = num
                elif 'week' in unit:
                    result["notice_period"] = f"{num} Week{'s' if num != 1 else ''}"
                    result["notice_period_days"] = num * 7
                else:
                    result["notice_period"] = f"{num} Month{'s' if num != 1 else ''}"
                    result["notice_period_days"] = num * 30
            else:
                nt = m.group(1).strip() if m.lastindex else m.group(0).strip()
                result["notice_period"] = nt
                dm = re.search(r'(\d+)\s*(?:day|month|week)', nt, re.IGNORECASE)
                if dm:
                    num = int(dm.group(1))
                    if 'month' in nt.lower():
                        result["notice_period_days"] = num * 30
                    elif 'week' in nt.lower():
                        result["notice_period_days"] = num * 7
                    else:
                        result["notice_period_days"] = num
                elif 'immediate' in nt.lower():
                    result["notice_period"], result["notice_period_days"] = "Immediate", 0
            notice_found = True
            break
    if not notice_found and header.get('notice_period'):
        result["notice_period"] = header['notice_period']
        result["notice_period_days"] = header.get('notice_period_days')

    # ── Employer ──
    if header.get('current_employer'):
        result["current_employer"] = header['current_employer']
    else:
        for pat in [r'(?:Current\s*(?:Company|Employer|Organization)|Working\s*(?:at|with|in))\s*[:\-]\s*(.+?)(?:\n|$)',
                    r'(?:Company|Employer)\s*[:\-]\s*(.+?)(?:\n|$)']:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if not _is_address_line(val):
                    result["current_employer"] = val
                    break
        if not result["current_employer"]:
            m = re.search(r'\bat\s+([A-Z][\w\s&.,]+?)(?:\s+since|\s+from|\s*\n|\s+\d+\s*(?:days?|months?|Months?|Days?)|\s+Immediate|\s+15\s*Days?\s*or\s*less|\s+Available)', text)
            if m:
                co = m.group(1).strip().rstrip('.')
                # Trim trailing notice-period fragments if a space-run leaked them in
                co = re.sub(
                    r'\s+(?:\d+\s*(?:days?|months?|Days?|Months?)|Immediate(?:ly)?|15\s*Days?\s*or\s*less|Available\s*(?:to|for)\s*Join)\s*$',
                    '', co, flags=re.IGNORECASE,
                ).strip()
                if 2 < len(co) < 80 and not _is_address_line(co):
                    result["current_employer"] = co

    # ── Designation ──
    if header.get('current_designation'):
        result["current_designation"] = header['current_designation']
    else:
        for pat in [r'(?:Current\s*)?(?:Designation|Title|Role|Position)\s*[:\-]\s*(.+?)(?:\n|$)']:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                result["current_designation"] = m.group(1).strip()
                break
        if not result["current_designation"]:
            m = re.search(r'Current\s*([A-Z][\w\s/-]+?)\s+at\s+', text)
            if m and 2 < len(m.group(1).strip()) < 80:
                result["current_designation"] = m.group(1).strip()

    # Fallback from early lines — DEFERRED until after work experience extraction
    # (moved below to avoid garbage from skills/summary lines)

    # ── Department / Industry ──
    # IMPORTANT: Match only labeled fields (start of line), not "industry-relevant" mid-sentence
    dm = re.search(r'(?:^|\n)\s*Department\s*[:\t ]\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if dm:
        dept_val = dm.group(1).strip()
        if len(dept_val) < 80 and not any(w in dept_val.lower() for w in ['proficient', 'passionate', 'experience', 'skilled', 'working']):
            result["current_department"] = dept_val
    im = re.search(r'(?:^|\n)\s*Industry\s*[:\t ]\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if im:
        ind_val = im.group(1).strip()
        if len(ind_val) < 80 and not any(w in ind_val.lower() for w in ['proficient', 'passionate', 'experience', 'skilled', 'relevant', 'software and']):
            result["current_industry"] = ind_val

    # ── Location ──
    if header.get('location'):
        result["location"] = header['location']
    else:
        for pat in [r'(?:Current\s*)?(?:Location|City)\s*[:\-]\s*(.+?)(?:\n|$)',
                    r'(?:Address|Residing\s*(?:at|in)|Based\s*in)\s*[:\-]\s*(.+?)(?:\n|$)']:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                result["location"] = m.group(1).strip().split(',')[0].strip()
                break
        if not result["location"]:
            first = text[:500].lower()
            for city in sorted(INDIAN_CITIES, key=len, reverse=True):
                # Use word boundary to prevent "goa" matching "goal-oriented"
                if re.search(r'\b' + re.escape(city) + r'\b', first):
                    result["location"] = city.title()
                    break

    # ── Preferred Locations ──
    pm = re.search(r'Preferred\s*(?:Location|City|Place)\s*[:\-]\s*(.+?)(?:\n\n|\n[A-Z])', text, re.IGNORECASE | re.DOTALL)
    if pm:
        result["preferred_locations"] = [l.strip() for l in re.split(r'[,|/]', pm.group(1)) if l.strip()][:10]

    # ── Headline ──
    for pat in [r'(?:Resume\s*)?Headline\s*[:\-]\s*\n?(.+?)(?:\n\n|\nProfile|\nSummary|\nKey|\nSkill)',
                r'(?:Resume\s*)?Headline\s*[:\-]\s*(.+?)(?:\n|$)']:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m and len(m.group(1).strip()) > 5:
            result["headline"] = m.group(1).strip()[:500]
            break
    if not result["headline"] and result["current_designation"] and result["current_employer"]:
        result["headline"] = f"{result['current_designation']} at {result['current_employer']}"

    # ── Profile Summary ──
    # Strategy 1: Labeled sections (most reliable)
    for pat in [
        r'(?:^|\n)\s*(?:Profile\s*Summary|Professional\s*Summary|Summary|About\s*Me|Objective|Career\s*Objective)\s*[:\-]?\s*\n(.+?)(?:\n\n|\nKey\s*Skills|\nSkills|\nWork\s*Experience|\nExperience|\nEmployment|\nIT\s*Skills|\nOnline\s*Profile|\nResidence|\nPersonal\s*Detail|\nCORE\s*COMPETENC|\nCore\s*Competenc|\nAreas?\s*of\s*Expertise|\nTechnical\s*Skills)',
        r'(?:^|\n)\s*(?:Profile\s*Summary|Professional\s*Summary|Summary|About\s*Me)\s*[:\-]\s*(.+?)(?:\n\n|\n[A-Z][a-z]+\s*[:\-]|\nCORE|\nCore\s*Comp)',
        r'(?:^|\n)\s*(?:Profile\s*Summary|Professional\s*Summary|Summary)\s*\n(.+?)(?:\n\n)',
        r'(?:^|\n)\s*(?:Career\s*Objective|Objective)\s*[:\-]?\s*\n(.+?)(?:\n\n|\nKey|\nSkill|\nWork|\nExperience|\nEmployment|\nCORE)',
    ]:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            summary_text = m.group(1).strip()
            # Filter out address lines and "|" artifacts
            summary_lines = [l.strip() for l in summary_text.split('\n') if l.strip() and not _is_address_line(l)]
            summary_text = ' '.join(summary_lines)
            # Remove "|" bar artifacts from Naukri
            summary_text = re.sub(r'\s*[|\u2502\u2503]{2,}\s*', ' ', summary_text)
            # Cap at reasonable length (500 chars) for clean, readable summary
            if len(summary_text) > 500:
                # Try to cut at sentence boundary
                cut = summary_text[:500].rfind('.')
                if cut > 200:
                    summary_text = summary_text[:cut + 1]
                else:
                    summary_text = summary_text[:500].rstrip() + '...'
            if len(summary_text) > 30:
                result["profile_summary"] = summary_text
                break

    # Strategy 2: CV format - paragraph between contact info and first section header
    if not result["profile_summary"]:
        lines = text.split('\n')
        contact_end = -1
        for i, line in enumerate(lines[:30]):
            if re.search(r'\d{10}|@[\w.-]+\.\w+', line.strip()):
                contact_end = i
        if contact_end >= 0:
            sec_hdr = re.compile(
                r'^(EXPERIENCE|WORK\s*EXPERIENCE|SKILLS|EDUCATION|EMPLOYMENT|CERTIFICATIONS?|PROJECTS?|LANGUAGES?)\s*$|'
                r'^(Key\s*Skills|Work\s*Experience|Employment\s*Details|Profile\s*Summary|Resume\s*Headline|IT\s*Skills|Personal\s*Details|===\s*NAUKRI)',
                re.IGNORECASE
            )
            slines = []
            for i in range(contact_end + 1, min(contact_end + 30, len(lines))):
                s = lines[i].strip()
                if not s:
                    if slines:
                        break
                    continue
                if sec_hdr.match(s):
                    break
                if re.match(r'^(LinkedIn|GitHub|Portfolio|Website|http)', s, re.IGNORECASE):
                    continue
                if _is_address_line(s):
                    continue
                slines.append(s)
            if slines:
                summary = ' '.join(slines)
                if len(summary) > 50:
                    result["profile_summary"] = summary[:2000]

    # Strategy 3: Resume Headline as a degraded summary (better than nothing)
    if not result["profile_summary"] and result.get("headline") and len(result["headline"]) > 30:
        result["profile_summary"] = result["headline"]

    # Fallback: synthesize from extracted fields
    if not result["profile_summary"]:
        parts = []
        if result["current_designation"]:
            parts.append(result["current_designation"])
        if result["current_employer"]:
            parts.append(f"at {result['current_employer']}")
        if result["experience_years"]:
            parts.append(f"with {result['experience_years']} years of experience")
        if result["location"]:
            parts.append(f"based in {result['location']}")
        if result.get("key_skills"):
            parts.append(f"skilled in {', '.join(result['key_skills'][:5])}")
        if parts:
            result["profile_summary"] = " ".join(parts) + "."

    # ── Skills ──
    skills = []
    # Strategy 1: CORE COMPETENCIES section (highest quality — Naukri Resdex format)
    for pat in [
        r'(?:^|\n)\s*(?:CORE\s*COMPETENC\w*|Areas?\s*of\s*Expertise|Core\s*Competenc\w*)\s*[:\-]?\s*\n(.+?)(?:\n\n|\nWork|\nExperience|\nEmployment|\nEducation|\nCertif|\nProfile|\nPersonal|\nResidence|\nLanguage|\nOnline|\n===|\Z)',
    ]:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            raw = m.group(1)
            skills = [s.strip() for s in re.split(r'[,|\u2022\u00B7\n\t;/]', raw) if s.strip()]
            break
    # Strategy 2: Labeled "Key Skills" / "Technical Skills" section at LINE START
    # CRITICAL: anchored with (?:^|\n) to prevent matching inside sentences
    if not skills:
        for pat in [
            r'(?:^|\n)\s*(?:Key\s*Skills?|Technical\s*Skills?|Skills?\s*&\s*Expertise|IT\s*Skills?)\s*[:\-]?\s*\n(.+?)(?:\n\n|\nWork|\nExperience|\nEmployment|\nEducation|\nCertif|\nProject|\nProfile|\nPersonal|\nResidence|\nLanguage|\nOnline|\n===|\nCORE|\Z)',
            r'(?:^|\n)\s*(?:Key\s*Skills?|Technical\s*Skills?|Skills?\s*&\s*Expertise|IT\s*Skills?)\s*[:\-]?\s*\n(.+?)(?:\n[A-Z][a-z]+\s*[:\-]|\Z)',
        ]:
            m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
            if m:
                raw = m.group(1)
                skills = [s.strip() for s in re.split(r'[,|\u2022\u00B7\n\t;]', raw) if s.strip()]
                break
    # Strategy 3: Single-line "Key Skills: X, Y, Z" at LINE START
    if not skills:
        m = re.search(r'(?:^|\n)\s*(?:Key\s*Skills?|Technical\s*Skills?|Skills?)\s*[:\-]\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
        if m:
            skills = [s.strip() for s in re.split(r'[,|\u2022\u00B7;]', m.group(1)) if s.strip()]
    # Strategy 4: "IT Skills" section
    if not skills:
        m = re.search(r'(?:^|\n)\s*IT\s*Skills?\s*[:\-]?\s*\n(.+?)(?:\n\n|\nPersonal|\nKey|\nWork|\nEmployment|\Z)', text, re.IGNORECASE | re.DOTALL)
        if m:
            for line in m.group(1).split('\n'):
                line = line.strip()
                if line and not re.match(r'^(Software|Version|Last|Expert|Intermediate|Beginner)\s*$', line, re.IGNORECASE):
                    parts = re.split(r'[,|\u2022\u00B7\t;]', line)
                    skills.extend([p.strip() for p in parts if p.strip()])
    # Apply garbage filter to all skills
    seen = set()
    clean_skills = []
    for s in skills:
        cleaned = _clean_skill(s)
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            clean_skills.append(cleaned)
    # Remove common Naukri junk that passes basic filters
    junk_exact = {'key skills', 'it skills', 'skills', 'na', 'n/a', 'none', 'nill', 'nil',
                  'technical skills', 'core competencies', 'tools', 'software',
                  'total experience', 'experience', 'employment details', 'education',
                  'areas of expertise', 'competencies'}
    result["key_skills"] = [s for s in clean_skills if s.lower() not in junk_exact][:25]

    # ── Work Experience ──
    exp_section_patterns = [
        r'\n(?:WORK\s*)?EXPERIENCE\s*\n(.+?)(?:\nEDUCATION\s*\n|\nSKILLS\s*\n|\nCERTIFICAT\w*\s*\n|\nPROJECTS?\s*\n|\nPERSONAL\s|\nLANGUAGE\w*\s*\n|\nTOOLS\s*\n|\nPROFESSIONAL\s*SUMMARY|\n=== NAUKRI|\Z)',
        r'(?:Work\s*experience|Employment\s*Details?|Experience\s*Details?|Professional\s*Experience)\s*[:\-]?\s*\n(.+?)(?:\nEducation\s*\n|\nEducation\s*$|\nQualification|\nCertificat\w*\s*\n|\nProjects?\s*\n|\nPersonal\s*Detail|\nLanguage\w*\s*\n|\nIT\s*Skills|\nKey\s*Skills|\nTOOLS\s*\n|\n=== NAUKRI|\n\n\n|\Z)',
    ]
    exp_text = ""
    for pat in exp_section_patterns:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            exp_text = m.group(1).strip()
            break
    work_exp = _parse_work_experience(exp_text)
    # Filter out work entries that are actually addresses
    work_exp = [e for e in work_exp if not (
        _is_address_line(e.get("company") or "") or
        _is_address_line(e.get("designation") or "")
    )]
    if not work_exp and result["current_employer"] and not _is_address_line(result["current_employer"]):
        work_exp = [{"company": result["current_employer"], "designation": result["current_designation"],
                     "is_current": True, "from_date": None, "to_date": "Present", "description": None}]
    result["work_experience"] = work_exp

    # ── Experience Years — date-span safety fallback ───────────────────────
    # If header/regex didn't find experience, OR the found value looks suspiciously
    # small vs the work-history span (e.g. "2.09 years" when work_exp covers 2007-2023),
    # compute total years from the earliest from_date → latest to_date.
    if work_exp:
        def _parse_ym(s):
            """Parse 'Jun 2022' / 'Jun \u201922' / '2015' / 'Present' → (year, month)."""
            if not s or not isinstance(s, str):
                return None
            s = s.strip()
            if re.match(r'^(present|current|till\s*date|date)$', s, re.IGNORECASE):
                import datetime as _dt
                n = _dt.datetime.now()
                return (n.year, n.month)
            # Full-form "Jun 2022" / "June 2022"
            m = re.search(r'([A-Za-z]{3,9})\s*[\'\u2019]?\s*(\d{2,4})', s)
            if m:
                mon_str = m.group(1)[:3].lower()
                months_map = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
                              'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
                mon = months_map.get(mon_str)
                yr = int(m.group(2))
                if yr < 100:
                    yr += 2000 if yr < 50 else 1900
                if mon and 1900 < yr < 2100:
                    return (yr, mon)
            # Year only
            m = re.match(r'^(\d{4})$', s)
            if m:
                return (int(m.group(1)), 1)
            return None

        spans = []
        for e in work_exp:
            frm = _parse_ym(e.get("from_date"))
            to = _parse_ym(e.get("to_date")) if e.get("to_date") else None
            if not to and e.get("is_current"):
                import datetime as _dt
                n = _dt.datetime.now()
                to = (n.year, n.month)
            if frm and to:
                spans.append((frm, to))
        if spans:
            earliest = min(s[0] for s in spans)
            latest = max(s[1] for s in spans)
            total_months = (latest[0] - earliest[0]) * 12 + (latest[1] - earliest[1])
            if total_months > 0:
                years_span = total_months // 12
                months_span = total_months % 12
                date_span_years = round(years_span + months_span / 100, 2)
                existing = result.get("experience_years")
                # Use date-span when (a) nothing extracted, or (b) extracted value
                # is less than half the date-span (strong signal of a regex misfire
                # like "2y 9m" from a single role getting grabbed as total).
                if existing is None or (date_span_years >= 1 and existing < date_span_years / 2):
                    if 0 < date_span_years <= 50:  # sanity bound
                        result["experience_years"] = date_span_years
                        logger.info(f"[Regex-Exp] Using date-span fallback: {date_span_years}y (was {existing})")

    # ── Backfill employer/designation from work experience ──
    if work_exp:
        current_entry = next((e for e in work_exp if e.get("is_current")), work_exp[0])
        if not result["current_employer"] and current_entry.get("company"):
            result["current_employer"] = current_entry["company"]
        if not result["current_designation"] and current_entry.get("designation"):
            result["current_designation"] = current_entry["designation"]

    # ── Last-resort employer/designation from early text lines ──
    if not result["current_employer"] or not result["current_designation"]:
        lines = [l.strip() for l in text.split('\n')[:20] if l.strip()]
        skip = re.compile(r'^(\+?\d|http|@|Experience|Professional|Industry|Department|Location|Current|Expected|Notice|Gender|Marital|DOB|Date|Profile|Key|Skills|Objective|Save\d|===|Residence|Personal|Language|Certif|Online|IT\s*Skill|Employment|Education|Qualification|Work\s*Exp|Summary|Headline|Academic)', re.IGNORECASE)
        cands = [l for l in lines if l.lower() != (result.get("candidate_name") or "").lower()
                 and not skip.match(l) and not re.match(r'^[\w.+-]+@', l)
                 and not _is_address_line(l) and 5 < len(l) < 60
                 and not re.search(r'[,|]{2,}', l)]  # Skip skill-like comma lists
        if not result["current_designation"] and cands:
            result["current_designation"] = cands[0]
        if not result["current_employer"] and len(cands) >= 2:
            result["current_employer"] = cands[1]


    # ── Education ──
    education = []
    deg_re = re.compile(r'((?:B\.?Tech|M\.?Tech|MBA|BBA|B\.?E|M\.?E|B\.?Sc|M\.?Sc|B\.?Com|M\.?Com|B\.?A|M\.?A|Ph\.?D|Diploma|PGDM|BCA|MCA|B\.?Pharm|M\.?Pharm|B\.?Arch|M\.?Arch|LLB|LLM|MBBS|MD|MS|BDS|MDS|CA|ICWA|CS|PGDBA|XII|X|10th|12th|HSC|SSC|Intermediate|ITI|Graduation|Post\s*Graduation|Doctorate)\b)', re.IGNORECASE)
    for pat in [
        r'\nEDUCATION\s*\n(.+?)(?:\nCERTIFICAT|\nPROJECT|\nPERSONAL|\nSKILLS|\nLANGUAGE|\nEXPERIENCE|\nTOOLS|\nPROFESSIONAL|\nRESIDENCE|\n=== NAUKRI|\Z)',
        r'(?:Education|Qualification|Academic|Educational\s*Detail)\s*[:\-]?\s*\n(.+?)(?:\nCertif|\nProject|\nPersonal|\nSkill|\nLanguage|\nWork|\nEmploy|\nIT\s*Skill|\nOnline|\nResidence|\n\n\n|\Z)',
        r'(?:Highest\s*Qualification|UG|PG)\s*[:\-]?\s*\n?(.+?)(?:\n\n|\nCertif|\nProject|\nPersonal|\Z)',
    ]:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            for line in m.group(1).split('\n'):
                line = line.strip()
                if not line or _is_address_line(line):
                    continue
                if deg_re.search(line):
                    parts = [p.strip() for p in re.split(r'[,|]', line) if p.strip()]
                    entry = {"degree": parts[0] if parts else line, "specialization": None, "institution": None, "year": None}
                    ym = re.search(r'((?:19|20)\d{2})', line)
                    if ym:
                        entry["year"] = ym.group(1)
                    for p in parts[1:]:
                        if re.match(r'^(19|20)\d{2}$', p.strip()):
                            continue
                        if not entry["specialization"] and len(p) < 50:
                            entry["specialization"] = p
                        elif not entry["institution"]:
                            entry["institution"] = p
                    education.append(entry)
            if education:
                break
    # Fallback: scan for degree names anywhere in text (weaker signal)
    if not education:
        for m in deg_re.finditer(text):
            start = max(0, m.start() - 80)
            context_line = text[start:m.end() + 80]
            # Only take if it looks like an education line (near year or institution keywords)
            if re.search(r'(19|20)\d{2}|University|College|Institute|School|Academy', context_line, re.IGNORECASE):
                entry = {"degree": m.group(1), "specialization": None, "institution": None, "year": None}
                ym = re.search(r'((?:19|20)\d{2})', context_line)
                if ym:
                    entry["year"] = ym.group(1)
                # Try to find institution
                inst_m = re.search(r'(?:University|College|Institute|School|Academy)\s*(?:of\s+)?[\w\s,]+', context_line, re.IGNORECASE)
                if inst_m:
                    entry["institution"] = inst_m.group(0).strip()[:80]
                education.append(entry)
                if len(education) >= 5:
                    break
    result["education"] = education[:10]

    # ── Highest Qualification ──
    qm = re.search(r'(?:Highest|Latest)\s*Qualification\s*[:\-]\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    result["highest_qualification"] = qm.group(1).strip() if qm else (education[0].get("degree") if education else None)

    # ── Personal Details ──
    dm = re.search(r'(?:Date\s*of\s*Birth|DOB|D\.O\.B)\s*[:\-]\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if dm:
        result["date_of_birth"] = dm.group(1).strip()
    gm = re.search(r'Gender\s*[:\-]\s*(Male|Female|Other|Trans\w*)', text, re.IGNORECASE)
    if gm:
        result["gender"] = gm.group(1).capitalize()
    for pat in [r'Marital\s*Status\s*[:\-]\s*(Single|Married|Divorced|Widowed|Separated|Unmarried)',
                r'(?:^|\n)(Single|Married|Divorced|Unmarried)\s*(?:\n|$)']:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result["marital_status"] = m.group(1).strip().capitalize()
            break

    # ── Languages ──
    for pat in [r'Language\w*\s*(?:Known|Spoken)?\s*[:\-]\s*(.+?)(?:\n\n|\n[A-Z])',
                r'Language\w*\s*[:\-]\s*(.+?)(?:\n\n|\n[A-Z])']:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            result["languages"] = [l.strip() for l in re.split(r'[,|\n]', m.group(1)) if l.strip() and len(l.strip()) < 30][:10]
            break

    # ── Certifications ──
    cm = re.search(r'Certification\w*\s*[:\-]?\s*\n(.+?)(?:\n\n|\nProject|\nPersonal|\nLanguage|\nOnline|$)', text, re.IGNORECASE | re.DOTALL)
    if cm:
        result["certifications"] = [c.strip() for c in cm.group(1).split('\n') if c.strip() and len(c.strip()) > 3][:10]

    # ── Confidence ──
    filled = sum(1 for v in result.values() if v and v != [] and v != {})
    result["confidence"] = "high" if filled >= 12 else "medium" if filled >= 7 else "low"

    # ═══════════════════════════════════════════════════════════════════
    # SANITY CHECKS — reject clearly wrong extractions
    # ═══════════════════════════════════════════════════════════════════

    # CTC cap: No individual salary in India exceeds ₹20 Cr (200,000,000).
    # Project values like "Rs 30000 Cr" are common in procurement CVs.
    CTC_MAX = 200_000_000  # ₹20 Crore
    if result["current_ctc"] and result["current_ctc"] > CTC_MAX:
        logger.info(f"[Regex-Sanity] CTC {result['current_ctc']:,} exceeds cap — discarded (likely project value)")
        result["current_ctc"] = None
    if result["expected_ctc"] and result["expected_ctc"] > CTC_MAX:
        logger.info(f"[Regex-Sanity] Expected CTC {result['expected_ctc']:,} exceeds cap — discarded")
        result["expected_ctc"] = None

    # Experience years cap: Nobody has > 50 years of professional experience.
    # Catches header parsing bugs (e.g., "Save253y" → 253 instead of 25.3).
    EXP_MAX = 50
    if result["experience_years"] is not None and result["experience_years"] > EXP_MAX:
        logger.info(f"[Regex-Sanity] Experience {result['experience_years']} years exceeds cap — discarded")
        result["experience_years"] = None

    # Education validation: reject entries that look like job responsibilities
    _DEGREE_KEYWORDS = {
        'b.tech', 'btech', 'b.e.', 'b.sc', 'bsc', 'b.com', 'bcom', 'b.a.', 'b.arch',
        'm.tech', 'mtech', 'm.e.', 'm.sc', 'msc', 'm.com', 'mcom', 'm.a.',
        'mba', 'pgdm', 'pgdbm', 'phd', 'ph.d', 'diploma', 'bba', 'mca', 'bca',
        'llb', 'llm', 'mbbs', 'bds',
        'bachelor', 'master', 'doctorate', 'graduate', 'graduation', 'postgraduate',
        '12th', 'hsc', 'ssc', 'intermediate', 'higher secondary',
        'iti', 'polytechnic', 'university', 'institute', 'college',
        'iit', 'iim', 'nit', 'bits', 'iisc', 'xlri', 'fms', 'jntu',
    }
    _ACTION_VERBS = {
        'negotiate', 'track', 'responsible', 'manage', 'develop', 'implement', 'coordinate',
        'ensure', 'handle', 'oversee', 'prepare', 'plan', 'execute', 'monitor', 'analyze',
        'evaluate', 'maintain', 'review', 'support', 'lead', 'conduct', 'establish',
        'procurement', 'sourcing', 'supply chain', 'vendor', 'contract', 'rate estimation',
        'handling', 'systems', 'items', 'material', 'optimization', 'mapping', 'estimation',
    }
    if result["education"]:
        valid_edu = []
        for edu in result["education"]:
            deg = (edu.get("degree") or "").strip()
            inst = (edu.get("institution") or "").strip()
            combined = f"{deg} {inst}".lower()
            # Use word-boundary matching for degree keywords to avoid substring false positives
            combined_words = set(re.findall(r'\b[\w.]+\b', combined))
            has_degree_kw = bool(combined_words & _DEGREE_KEYWORDS) or any(
                kw in combined for kw in _DEGREE_KEYWORDS if len(kw) > 4
            )
            has_action_verb = any(av in combined for av in _ACTION_VERBS)
            too_long = len(deg) > 80
            if has_action_verb or (too_long and not has_degree_kw):
                logger.info(f"[Regex-Sanity] Rejected education: '{deg[:60]}' (action_verb={has_action_verb}, too_long={too_long})")
                continue
            if not has_degree_kw and len(deg) > 5:
                logger.info(f"[Regex-Sanity] Rejected education: '{deg[:60]}' (no degree keywords)")
                continue
            valid_edu.append(edu)
        result["education"] = valid_edu

    # Designation validation: reject if it's clearly a responsibility description
    desg = result.get("current_designation") or ""
    if desg:
        desg_lower = desg.lower().strip()
        # Only reject long descriptions or entries starting with action verbs
        # Short titles like "Engineering Manager" or "Head - Procurement" are valid
        _DESG_ACTION_STARTERS = (
            'responsible', 'worked', 'handling', 'managed', 'developed',
            'implemented', 'coordinated', 'ensured', 'prepared', 'executed',
            'rate estimation', 'monitoring', 'tracking', 'negotiating',
        )
        is_bad_designation = (
            len(desg) > 80 or  # Designations are short titles
            desg_lower.startswith(_DESG_ACTION_STARTERS) or
            desg_lower.count(' ') > 8  # Too many words for a title
        )
        if is_bad_designation:
            logger.info(f"[Regex-Sanity] Rejected designation: '{desg[:60]}' (looks like description)")
            result["current_designation"] = None

    logger.info(
        f"[Regex] name={result.get('candidate_name')}, phone={result.get('candidate_phone')}, "
        f"email={result.get('candidate_email')}, ctc={result.get('current_ctc')}, "
        f"notice={result.get('notice_period')}, loc={result.get('location')}, "
        f"skills={len(result.get('key_skills') or [])}, exp_entries={len(result.get('work_experience') or [])}, "
        f"edu={len(result.get('education') or [])}, summary={'Y' if result.get('profile_summary') else 'N'}, "
        f"confidence={result.get('confidence')}, filled={filled}"
    )
    return result
