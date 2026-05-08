"""
Bulk import business logic service.
Helpers for parsing, normalizing, and merging candidate data during bulk import.
"""
import re
import io
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


async def detect_industry_from_employer(employer_name: str) -> Optional[str]:
    """Use LLM to detect industry from employer/company name."""
    if not employer_name:
        return None

    try:
        from services.matching_engine import _llm_chat

        system_msg = (
            "You are an expert at identifying company industries. "
            "Given a company name, determine its primary industry sector. "
            "Return ONLY the industry name, nothing else. Keep it concise (1-3 words)."
        )

        prompt = f"""What industry does this company operate in? Company name: "{employer_name}"

Return ONLY the industry name (1-3 words), for example:
- Information Technology
- Automobile Manufacturing
- FMCG
- Banking & Finance
- Healthcare
- Consulting
- Retail
- Pharmaceutical
- Logistics
- Energy

Industry:"""

        response = await _llm_chat(system_msg, prompt)

        if response:
            industry = response.strip().strip('"').strip("'")
            if len(industry) > 50:
                industry = industry.split('\n')[0].strip()
            logger.info(f"[AI INDUSTRY] Detected '{industry}' for employer '{employer_name}'")
            return industry
        return None

    except Exception as e:
        logger.error(f"[AI INDUSTRY] Error detecting industry for '{employer_name}': {e}")
        return None


def parse_experience_string(exp_str: str) -> int:
    """Parse experience string like '10Y 0 M', '4Y 0 M', or '5 Year(s) 3 Month(s)' to years"""
    if not exp_str:
        return 0
    try:
        exp_str = str(exp_str).upper().strip()
        # Handle "5 Year(s) 3 Month(s)" format (Naukri export)
        year_match = re.search(r'(\d+)\s*YEAR', exp_str)
        if year_match:
            return int(year_match.group(1))
        # Handle "10Y 0M" format
        year_match = re.search(r'(\d+)\s*Y', exp_str)
        if year_match:
            return int(year_match.group(1))
        num_match = re.search(r'(\d+)', exp_str)
        if num_match:
            return int(num_match.group(1))
        return 0
    except Exception:
        return 0


def parse_salary_string(salary_str: str) -> Optional[int]:
    """Parse salary string like '10.0 L', '15.5 L', or 'Rs 27.40 Lakhs' to INR"""
    if not salary_str:
        return None
    try:
        salary_str = str(salary_str).upper().strip()
        # Handle "Rs 27.40 Lakhs" format (Naukri export)
        match = re.search(r'RS\.?\s*(\d+\.?\d*)\s*LAKH', salary_str)
        if match:
            return int(float(match.group(1)) * 100000)
        match = re.search(r'(\d+\.?\d*)\s*L', salary_str)
        if match:
            lakhs = float(match.group(1))
            return int(lakhs * 100000)
        num_match = re.search(r'(\d+\.?\d*)', salary_str)
        if num_match:
            val = float(num_match.group(1))
            if val < 100:
                return int(val * 100000)
            return int(val)
        return None
    except Exception:
        return None


def normalize_phone(phone: str) -> Optional[str]:
    """Normalize phone number to last 10 digits"""
    if not phone:
        return None
    digits = "".join(filter(str.isdigit, str(phone)))
    return digits[-10:] if len(digits) >= 10 else digits if digits else None


def extract_text_from_file(file_content: bytes, filename: str) -> str:
    """Extract text from PDF, DOC, or DOCX files"""
    ext = Path(filename).suffix.lower()

    try:
        if ext == '.pdf':
            import fitz
            doc = fitz.open(stream=file_content, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text

        elif ext == '.docx':
            from docx import Document
            doc = Document(io.BytesIO(file_content))
            return "\n".join([para.text for para in doc.paragraphs])

        elif ext == '.doc':
            try:
                import docx2txt
                text = docx2txt.process(io.BytesIO(file_content))
                if text and len(text.strip()) > 50:
                    return text
            except Exception:
                pass
            try:
                text = file_content.decode('utf-8', errors='ignore')
                text = ''.join(c for c in text if c.isprintable() or c in '\n\r\t')
                words = [w for w in text.split() if len(w) > 2 and w.isalpha()]
                if len(words) > 20:
                    return text
            except Exception:
                pass
            try:
                text = file_content.decode('latin-1', errors='ignore')
                text = ''.join(c for c in text if c.isprintable() or c in '\n\r\t')
                words = [w for w in text.split() if len(w) > 2 and w.isalpha()]
                if len(words) > 20:
                    return text
            except Exception:
                pass
            return ""

        return ""
    except Exception as e:
        logger.error(f"Error extracting text from {filename}: {e}")
        return ""


def merge_skills(existing: List[str], new: List[str]) -> List[str]:
    """Merge and deduplicate skills"""
    seen_lower = set()
    result = []
    for s in existing + new:
        if s and s.strip().lower() not in seen_lower:
            result.append(s.strip())
            seen_lower.add(s.strip().lower())
    return result


def merge_experience(existing: List[dict], new: List[dict]) -> List[dict]:
    """Merge job history and sort chronologically by latest date"""
    all_exp = existing + new

    def get_sort_key(exp):
        duration = exp.get('duration', '') or ''
        years = re.findall(r'20\d{2}', duration)
        if years:
            return max(int(y) for y in years)
        return 0

    return sorted(all_exp, key=get_sort_key, reverse=True)
