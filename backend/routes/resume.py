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
    skills = p.get("skills") or []

    # Build experience entries
    exp_entries = []
    for exp in p.get("experience") or []:
        company = _escape_latex(exp.get("company") or "")
        title = _escape_latex(exp.get("title") or "")
        duration = _escape_latex(exp.get("duration") or "")
        bullets_tex = "\n".join(["  \\item " + _escape_latex(b) for b in (exp.get("bullets") or []) if b])
        entry = (
            f"\\textbf{{{title}}} \\hfill {duration} \\\\\n"
            f"\\textit{{{company}}}\n"
            "\\begin{itemize}[leftmargin=*, itemsep=2pt, parsep=0pt]\n"
            f"{bullets_tex}\n"
            "\\end{itemize}"
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
            f"{contact_line}\n"
            "\\end{center}\n\n"
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


@resume_router.post("/compile-pdf")
async def compile_pdf(req: CompilePdfRequest, user=Depends(get_current_user)):
    """Compile LaTeX code into a PDF and return it as a downloadable file."""
    import tempfile
    import subprocess
    import os
    from fastapi.responses import Response

    if not req.latex or len(req.latex.strip()) < 20:
        raise HTTPException(status_code=400, detail="LaTeX content is too short or empty")

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, "resume.tex")
        with open(tex_path, "w") as f:
            f.write(req.latex)

        try:
            result = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "resume.tex"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=500, detail="PDF compilation timed out")

        pdf_path = os.path.join(tmpdir, "resume.pdf")
        if not os.path.exists(pdf_path):
            log_path = os.path.join(tmpdir, "resume.log")
            log_tail = ""
            if os.path.exists(log_path):
                with open(log_path) as lf:
                    lines = lf.readlines()
                    # Extract error lines
                    log_tail = "".join(lines[-30:])
            raise HTTPException(
                status_code=422,
                detail=f"LaTeX compilation failed. Log tail:\n{log_tail[-500:]}"
            )

        with open(pdf_path, "rb") as pf:
            pdf_bytes = pf.read()

    return Response(
        content=pdf_bytes,
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
    """Format candidate_bank document for resume builder."""
    return {
        "name": candidate.get("name", ""),
        "email": candidate.get("email", ""),
        "phone": candidate.get("phone", candidate.get("mobile", "")),
        "location": candidate.get("location", candidate.get("current_location", "")),
        "linkedin": candidate.get("linkedin_url", ""),
        "summary": candidate.get("summary", candidate.get("profile_summary", "")),
        "skills": candidate.get("skills", []),
        "experience": [
            {
                "company": exp.get("company", exp.get("organization", "")),
                "title": exp.get("title", exp.get("designation", "")),
                "duration": exp.get("duration", exp.get("period", "")),
                "bullets": exp.get("bullets", []),
            }
            for exp in candidate.get("experience", [])
        ],
        "education": [
            {
                "institution": edu.get("institution", edu.get("university", edu.get("school", ""))),
                "degree": edu.get("degree", edu.get("qualification", "")),
                "year": edu.get("year", edu.get("passing_year", "")),
                "gpa": edu.get("gpa", ""),
            }
            for edu in candidate.get("education", [])
        ],
    }
