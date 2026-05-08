"""
VHC Talent OS - Resume Generator API
Generates LaTeX resumes from candidate profile data with AI enhancement.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from config import db
from utils import get_current_user

logger = logging.getLogger(__name__)

resume_router = APIRouter(prefix="/api/resume", tags=["Resume Generator"])


# ── Models ──────────────────────────────────────────────────

class ExperienceItem(BaseModel):
    company: Optional[str] = ""
    title: Optional[str] = ""
    duration: Optional[str] = ""
    bullets: List[str] = []

class EducationItem(BaseModel):
    institution: Optional[str] = ""
    degree: Optional[str] = ""
    year: Optional[str] = None
    gpa: Optional[str] = None

class ResumeProfile(BaseModel):
    name: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    location: Optional[str] = ""
    linkedin: Optional[str] = ""
    summary: Optional[str] = ""
    skills: List[str] = []
    experience: List[ExperienceItem] = []
    education: List[EducationItem] = []

class GenerateRequest(BaseModel):
    profile: ResumeProfile
    template_id: str = "ats_clean"

class AiEnhanceRequest(BaseModel):
    bullets: List[str]


# ── Templates ───────────────────────────────────────────────

TEMPLATES = [
    {"id": "ats_clean", "label": "ATS Clean", "description": "Minimal, ATS-optimized single column"},
    {"id": "google_style", "label": "Google Style", "description": "Clean modern layout inspired by top tech"},
    {"id": "modern", "label": "Modern Pro", "description": "Two-column skills, contemporary design"},
]


def _escape_latex(text):
    """Escape special LaTeX characters."""
    if not text:
        return ""
    replacements = {
        '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#',
        '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


def build_latex(profile: dict, template_id: str) -> str:
    """Generate LaTeX code from profile data and template."""
    p = profile
    name = _escape_latex(p.get("name") or "")
    email = p.get("email") or ""
    phone = _escape_latex(p.get("phone") or "")
    location = _escape_latex(p.get("location") or "")
    linkedin = p.get("linkedin") or ""
    summary = _escape_latex(p.get("summary") or "")
    designation = _escape_latex(p.get("designation") or "")
    skills = p.get("skills") or []
    certifications = p.get("certifications") or []

    # Build experience entries
    exp_entries = []
    for exp in p.get("experience") or []:
        company = _escape_latex(exp.get("company") or "")
        title = _escape_latex(exp.get("title") or "")
        duration = _escape_latex(exp.get("duration") or "")
        valid_bullets = [b for b in (exp.get("bullets") or []) if b and b.strip()]
        bullets_tex = "\n".join(["  \\item " + _escape_latex(b) for b in valid_bullets])
        if bullets_tex:
            entry = (
                f"\\textbf{{{title}}} \\hfill {duration} \\\\\n"
                f"\\textit{{{company}}}\n"
                "\\begin{itemize}[leftmargin=*, itemsep=2pt, parsep=0pt]\n"
                f"{bullets_tex}\n"
                "\\end{itemize}"
            )
        else:
            entry = (
                f"\\textbf{{{title}}} \\hfill {duration} \\\\\n"
                f"\\textit{{{company}}}"
            )
        exp_entries.append(entry)

    exp_section = "\n\\vspace{4pt}\n".join(exp_entries)

    # Build education entries
    edu_entries = []
    for edu in p.get("education") or []:
        institution = _escape_latex(edu.get("institution") or "")
        degree = _escape_latex(edu.get("degree") or "")
        year = _escape_latex(edu.get("year") or "")
        gpa = edu.get("gpa") or ""
        gpa_line = f" | GPA: {_escape_latex(gpa)}" if gpa else ""
        edu_entries.append(f"\\textbf{{{degree}}} \\hfill {year} \\\\\n\\textit{{{institution}}}{gpa_line}")

    edu_section = "\n\\vspace{4pt}\n".join(edu_entries)

    # Certifications
    cert_entries = []
    for cert in certifications:
        cert_name = _escape_latex(cert.get("name") or "")
        cert_issuer = _escape_latex(cert.get("issuer") or "")
        cert_date = _escape_latex(cert.get("date") or "")
        entry = f"\\textbf{{{cert_name}}}"
        if cert_issuer:
            entry += f" — \\textit{{{cert_issuer}}}"
        if cert_date:
            entry += f" \\hfill {cert_date}"
        cert_entries.append(entry)
    cert_section = " \\\\\n".join(cert_entries)

    # Skills
    skills_escaped = [_escape_latex(s) for s in skills]

    # Pre-compute contact line parts (avoids backslash in f-string expressions)
    contact_parts = [phone]
    if email:
        contact_parts.append(email)
    if location:
        contact_parts.append(location)
    if linkedin:
        contact_parts.append(f"\\href{{{linkedin}}}{{LinkedIn}}")
    contact_line = " | ".join(p for p in contact_parts if p)

    # Designation subtitle line
    designation_line = f"\\textit{{{designation}}}\\\\[2pt]\n" if designation else ""

    if template_id == "google_style":
        skills_line = " $\\bullet$ ".join(skills_escaped)
        return (
            "\\documentclass[11pt,a4paper]{article}\n"
            "\\usepackage[top=0.5in,bottom=0.5in,left=0.6in,right=0.6in]{geometry}\n"
            "\\usepackage{enumitem}\n"
            "\\usepackage{titlesec}\n"
            "\\usepackage[hidelinks]{hyperref}\n"
            "\\usepackage{xcolor}\n"
            "\\pagenumbering{gobble}\n"
            "\\titleformat{\\section}{\\large\\bfseries}{}{0em}{}[\\titlerule]\n"
            "\\titlespacing*{\\section}{0pt}{8pt}{4pt}\n"
            "\\begin{document}\n"
            f"{{\\LARGE\\bfseries {name}}}\\\\[4pt]\n"
            f"{contact_line}\n\n"
            "\\section*{Summary}\n"
            f"{summary}\n\n"
            "\\section*{Experience}\n"
            f"{exp_section}\n\n"
            "\\section*{Education}\n"
            f"{edu_section}\n\n"
            "\\section*{Skills}\n"
            f"{skills_line}\n"
            "\\end{document}"
        )

    elif template_id == "modern":
        skills_items = "\n".join(["  \\item " + s for s in skills_escaped])
        return (
            "\\documentclass[11pt,a4paper]{article}\n"
            "\\usepackage[top=0.5in,bottom=0.5in,left=0.6in,right=0.6in]{geometry}\n"
            "\\usepackage{enumitem}\n"
            "\\usepackage{titlesec}\n"
            "\\usepackage[hidelinks]{hyperref}\n"
            "\\usepackage{multicol}\n"
            "\\pagenumbering{gobble}\n"
            "\\titleformat{\\section}{\\large\\bfseries\\scshape}{}{0em}{}[\\titlerule]\n"
            "\\titlespacing*{\\section}{0pt}{8pt}{4pt}\n"
            "\\begin{document}\n"
            "\\begin{center}\n"
            f"{{\\LARGE\\bfseries {name}}}\\\\[4pt]\n"
            f"{contact_line}\n"
            "\\end{center}\n\n"
            "\\section*{Professional Summary}\n"
            f"{summary}\n\n"
            "\\section*{Experience}\n"
            f"{exp_section}\n\n"
            "\\section*{Education}\n"
            f"{edu_section}\n\n"
            "\\section*{Technical Skills}\n"
            "\\begin{multicols}{2}\n"
            "\\begin{itemize}[leftmargin=*, itemsep=1pt]\n"
            f"{skills_items}\n"
            "\\end{itemize}\n"
            "\\end{multicols}\n"
            "\\end{document}"
        )

    else:  # ats_clean (default)
        skills_line = " $\\bullet$ ".join(skills_escaped)
        cert_block = ""
        if cert_section:
            cert_block = f"\n\\section*{{Certifications}}\n{cert_section}\n"
        return (
            "\\documentclass[11pt,a4paper]{article}\n"
            "\\usepackage[top=0.4in,bottom=0.4in,left=0.5in,right=0.5in]{geometry}\n"
            "\\usepackage{enumitem}\n"
            "\\usepackage{titlesec}\n"
            "\\usepackage[hidelinks]{hyperref}\n"
            "\\pagenumbering{gobble}\n"
            "\\titleformat{\\section}{\\normalsize\\bfseries\\uppercase}{}{0em}{}[\\rule{\\linewidth}{0.4pt}]\n"
            "\\titlespacing*{\\section}{0pt}{6pt}{4pt}\n"
            "\\begin{document}\n"
            "\\begin{center}\n"
            f"{{\\Large\\bfseries\\uppercase{{{name}}}}}\\\\[3pt]\n"
            f"{designation_line}"
            f"{contact_line}\n"
            "\\end{center}\n\n"
            "\\section*{Summary}\n"
            f"{summary}\n\n"
            "\\section*{Experience}\n"
            f"{exp_section}\n\n"
            "\\section*{Education}\n"
            f"{edu_section}\n"
            f"{cert_block}\n"
            "\\section*{Skills}\n"
            f"{skills_line}\n"
            "\\end{document}"
        )


# ── Routes ──────────────────────────────────────────────────

@resume_router.get("/templates")
async def get_templates(user=Depends(get_current_user)):
    return TEMPLATES


@resume_router.post("/generate")
async def generate_resume(req: GenerateRequest, user=Depends(get_current_user)):
    """Generate LaTeX resume from profile data."""
    profile_dict = req.profile.model_dump()
    latex = build_latex(profile_dict, req.template_id)
    return {"latex": latex, "template_id": req.template_id}


class CompilePdfRequest(BaseModel):
    latex: str


def _is_pdflatex_available():
    """Check if pdflatex is installed on the system."""
    import shutil
    return shutil.which("pdflatex") is not None


@resume_router.get("/capabilities")
async def get_resume_capabilities(user=Depends(get_current_user)):
    """Return what the resume builder can do on this server."""
    return {"pdf_compilation": True, "pdflatex_available": _is_pdflatex_available()}


@resume_router.post("/compile-pdf")
async def compile_pdf(req: CompilePdfRequest, user=Depends(get_current_user)):
    """Compile LaTeX code into a PDF and return it as a downloadable file.
    Uses pdflatex if available, otherwise falls back to fpdf2."""
    import tempfile
    import subprocess
    import os
    from fastapi.responses import Response

    if not req.latex or len(req.latex.strip()) < 20:
        raise HTTPException(status_code=400, detail="LaTeX content is too short or empty")

    # Method 1: pdflatex (best quality)
    if _is_pdflatex_available():
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = os.path.join(tmpdir, "resume.tex")
            with open(tex_path, "w") as f:
                f.write(req.latex)

            try:
                subprocess.run(
                    ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "resume.tex"],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            else:
                pdf_path = os.path.join(tmpdir, "resume.pdf")
                if os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as pf:
                        pdf_bytes = pf.read()
                    return Response(
                        content=pdf_bytes,
                        media_type="application/pdf",
                        headers={"Content-Disposition": 'inline; filename="resume.pdf"'},
                    )

    # Method 2: fpdf2 fallback — parse profile from the request context
    # Since we only have LaTeX here, return a helpful message
    raise HTTPException(
        status_code=503,
        detail="pdflatex not available. Use /api/resume/generate-pdf for direct PDF generation."
    )


class GeneratePdfRequest(BaseModel):
    profile: ResumeProfile
    template_id: str = "ats_clean"


@resume_router.post("/generate-pdf")
async def generate_pdf(req: GeneratePdfRequest, user=Depends(get_current_user)):
    """Generate a PDF resume directly from profile data using fpdf2. No system deps required."""
    from fastapi.responses import Response
    from services.pdf_generator import build_pdf_from_profile

    profile_dict = req.profile.model_dump()
    pdf_bytes = build_pdf_from_profile(profile_dict)

    return Response(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="resume.pdf"'},
    )


@resume_router.get("/my-profile")
async def get_my_resume_profile(user=Depends(get_current_user)):
    """Get current user's profile data formatted for resume builder."""
    user_id = user.get("id", "")
    role = user.get("role", "")

    # For candidates: get their own profile
    if role == "candidate":
        profile = await db.candidate_profiles.find_one({"user_id": user_id}, {"_id": 0})
        if profile:
            return _format_profile_for_resume(profile)

    # Return empty profile structure for any role
    return {
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "phone": "",
        "location": "",
        "linkedin": "",
        "summary": "",
        "skills": [],
        "experience": [],
        "education": [],
    }


@resume_router.get("/candidate/{candidate_id}")
async def get_candidate_resume_profile(candidate_id: str, user=Depends(get_current_user)):
    """Get a candidate's profile for resume generation (admin/recruiter/employer)."""
    role = user.get("role", "")
    if role not in ("admin", "recruiter", "employer"):
        raise HTTPException(status_code=403, detail="Only admin/recruiter/employer can access candidate profiles")

    # Try candidate_bank first (more complete data)
    candidate = await db.candidate_bank.find_one({"id": candidate_id}, {"_id": 0})
    if candidate:
        return _format_bank_profile_for_resume(candidate)

    # Fallback to candidate_profiles
    profile = await db.candidate_profiles.find_one({"id": candidate_id}, {"_id": 0})
    if profile:
        return _format_profile_for_resume(profile)

    raise HTTPException(status_code=404, detail="Candidate not found")


@resume_router.post("/ai-enhance")
async def ai_enhance_bullets(req: AiEnhanceRequest, user=Depends(get_current_user)):
    """AI-enhance resume bullet points using OpenAI."""
    from services.llm_service import chat_completion

    prompt = (
        "You are an expert resume writer. Rewrite these bullet points to be stronger, more impact-driven, and ATS-optimized.\n\n"
        "Rules:\n"
        "- Start each bullet with a strong action verb\n"
        "- Include metrics and quantifiable results where possible\n"
        "- Keep each bullet concise (1-2 lines)\n"
        "- Make them ATS-friendly with industry keywords\n"
        "- Return ONLY a JSON array of strings, nothing else\n\n"
        "Bullet points to enhance:\n"
    )
    prompt += "\n".join("- " + b for b in req.bullets)

    try:
        response = await chat_completion(
            system_prompt="You are an expert resume writer. Return only valid JSON arrays.",
            user_prompt=prompt,
            model="gpt-4o-mini",
            temperature=0.7,
            json_mode=True,
        )
        import json
        # Try to parse JSON from the response
        text = response.strip()
        # Handle markdown code blocks
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        enhanced = json.loads(text)
        if isinstance(enhanced, list):
            return {"bullets": enhanced}
        return {"bullets": req.bullets}
    except Exception as e:
        logger.warning(f"AI enhance failed: {e}")
        return {"bullets": req.bullets}


def _format_profile_for_resume(profile: dict) -> dict:
    """Format candidate_profiles document for resume builder."""
    return {
        "name": profile.get("name", ""),
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "location": profile.get("location", ""),
        "linkedin": profile.get("linkedin", ""),
        "summary": profile.get("summary", ""),
        "skills": profile.get("skills", []),
        "experience": [
            {
                "company": exp.get("company", ""),
                "title": exp.get("title", exp.get("role", "")),
                "duration": exp.get("duration", exp.get("period", "")),
                "bullets": exp.get("bullets", exp.get("description", "").split("\n") if exp.get("description") else []),
            }
            for exp in profile.get("experience", [])
        ],
        "education": [
            {
                "institution": edu.get("institution", edu.get("school", "")),
                "degree": edu.get("degree", ""),
                "year": edu.get("year", edu.get("graduation_year", "")),
                "gpa": edu.get("gpa", ""),
            }
            for edu in profile.get("education", [])
        ],
    }


def _format_bank_profile_for_resume(candidate: dict) -> dict:
    """Format candidate_bank document for resume builder — comprehensive version."""
    # Format experience - handle various field names from different sources
    formatted_exp = []
    for exp in candidate.get("experience", []):
        title = exp.get("title") or exp.get("designation", "")
        company = exp.get("company") or exp.get("organization", "")
        # Try multiple duration formats
        duration = exp.get("duration") or exp.get("period", "")
        if not duration:
            from_date = exp.get("from_date", "")
            to_date = exp.get("to_date") or ("Present" if exp.get("is_current") else "")
            if from_date or to_date:
                duration = f"{from_date} - {to_date}".strip(" -")
        # Get bullets from description — be comprehensive, don't truncate
        bullets = exp.get("bullets", [])
        if not bullets and exp.get("description"):
            desc = exp.get("description", "")
            # Split by newlines first, then by periods for sentence-level detail
            lines = [line.strip() for line in desc.replace("\r\n", "\n").split("\n") if line.strip()]
            if len(lines) <= 1 and desc:
                # Single block of text — split by sentences
                import re
                lines = [s.strip() for s in re.split(r'(?<=[.!])\s+', desc) if s.strip() and len(s.strip()) > 10]
            if not lines and desc:
                # Fallback: split by commas but keep meaningful chunks
                lines = [s.strip() for s in desc.split(",") if s.strip() and len(s.strip()) > 10]
            bullets = lines  # Include ALL bullets, not limited to 3
        formatted_exp.append({
            "company": company,
            "title": title,
            "duration": duration,
            "bullets": bullets,
        })

    # Format education - handle various field names
    formatted_edu = []
    for edu in candidate.get("education", []):
        institution = edu.get("institution") or edu.get("university") or edu.get("school", "")
        degree = edu.get("degree") or edu.get("qualification", "")
        specialization = edu.get("specialization", "")
        if specialization and specialization not in degree:
            degree = f"{degree} — {specialization}" if degree else specialization
        year = edu.get("year") or edu.get("passing_year") or edu.get("year_of_passing", "")
        gpa = edu.get("gpa") or edu.get("score", "")
        formatted_edu.append({
            "institution": institution,
            "degree": degree,
            "year": str(year) if year else "",
            "gpa": gpa,
        })

    # Format certifications
    formatted_certs = []
    for cert in candidate.get("certifications_detailed", []):
        name = cert.get("name", "")
        issuer = cert.get("issuing_authority", "")
        date = cert.get("issue_date", "")
        if name:
            formatted_certs.append({
                "name": name,
                "issuer": issuer,
                "date": date,
            })

    # Build comprehensive summary
    summary = candidate.get("summary") or candidate.get("profile_summary", "")
    if not summary:
        # Auto-generate a brief summary from available data
        parts = []
        if candidate.get("designation"):
            parts.append(candidate["designation"])
        if candidate.get("current_employer"):
            parts.append(f"at {candidate['current_employer']}")
        if candidate.get("experience_years"):
            parts.append(f"with {candidate['experience_years']} years of experience")
        if candidate.get("industry"):
            parts.append(f"in {candidate['industry']}")
        if parts:
            summary = " ".join(parts) + "."

    return {
        "name": candidate.get("name", ""),
        "email": candidate.get("email", ""),
        "phone": candidate.get("phone") or candidate.get("mobile", ""),
        "location": candidate.get("location") or candidate.get("current_location", ""),
        "linkedin": candidate.get("linkedin_url", ""),
        "summary": summary,
        "designation": candidate.get("designation") or candidate.get("headline", ""),
        "skills": candidate.get("skills", []),
        "experience": formatted_exp,
        "education": formatted_edu,
        "certifications": formatted_certs,
    }
