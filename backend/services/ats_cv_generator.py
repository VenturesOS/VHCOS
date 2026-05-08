"""
ATS-Friendly CV Generator — On-Demand PDF Generation
Generates clean, professional CVs from structured candidate profiles.
Never stores files — generates in memory at request time.

Excludes: CTC, Expected CTC, Notice Period
Includes: Name, Contact, Summary, Experience, Education, Skills, Certifications
"""
import io
import logging
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER

logger = logging.getLogger(__name__)

# Colors
PRIMARY = HexColor("#1a1a2e")
ACCENT = HexColor("#7CB342")
MUTED = HexColor("#555555")
LIGHT_GRAY = HexColor("#e0e0e0")


def _build_styles():
    """Build custom paragraph styles for the CV."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "CVName", parent=styles["Title"],
        fontSize=20, leading=24, textColor=PRIMARY,
        spaceAfter=2, alignment=TA_LEFT, fontName="Helvetica-Bold"
    ))
    styles.add(ParagraphStyle(
        "CVHeadline", parent=styles["Normal"],
        fontSize=10, leading=13, textColor=MUTED,
        spaceAfter=6, fontName="Helvetica"
    ))
    styles.add(ParagraphStyle(
        "CVSection", parent=styles["Heading2"],
        fontSize=12, leading=15, textColor=PRIMARY,
        spaceBefore=12, spaceAfter=4, fontName="Helvetica-Bold",
        borderWidth=0
    ))
    styles.add(ParagraphStyle(
        "CVBody", parent=styles["Normal"],
        fontSize=9.5, leading=13, textColor=HexColor("#333333"),
        fontName="Helvetica"
    ))
    styles.add(ParagraphStyle(
        "CVBodyBold", parent=styles["Normal"],
        fontSize=9.5, leading=13, textColor=HexColor("#222222"),
        fontName="Helvetica-Bold"
    ))
    styles.add(ParagraphStyle(
        "CVSmall", parent=styles["Normal"],
        fontSize=8.5, leading=11, textColor=MUTED,
        fontName="Helvetica"
    ))
    styles.add(ParagraphStyle(
        "CVContact", parent=styles["Normal"],
        fontSize=9, leading=12, textColor=MUTED,
        alignment=TA_LEFT, fontName="Helvetica"
    ))
    return styles


def generate_ats_cv(candidate: dict) -> bytes:
    """
    Generate an ATS-friendly PDF CV from a candidate profile dict.
    Returns raw PDF bytes (never stored).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm
    )
    styles = _build_styles()
    story = []

    # === NAME ===
    name = candidate.get("name") or "Candidate"
    story.append(Paragraph(name, styles["CVName"]))

    # === HEADLINE / DESIGNATION ===
    headline = candidate.get("headline") or candidate.get("designation") or candidate.get("current_designation")
    if headline:
        story.append(Paragraph(headline, styles["CVHeadline"]))

    # === CONTACT LINE ===
    contact_parts = []
    if candidate.get("email"):
        contact_parts.append(candidate["email"])
    if candidate.get("phone"):
        contact_parts.append(candidate["phone"])
    if candidate.get("location"):
        contact_parts.append(candidate["location"])
    elif candidate.get("current_city"):
        loc = candidate["current_city"]
        if candidate.get("current_state"):
            loc += f", {candidate['current_state']}"
        contact_parts.append(loc)
    if contact_parts:
        story.append(Paragraph("  |  ".join(contact_parts), styles["CVContact"]))

    # LinkedIn / GitHub
    links = []
    if candidate.get("linkedin_url"):
        links.append(f"LinkedIn: {candidate['linkedin_url']}")
    if candidate.get("github_url"):
        links.append(f"GitHub: {candidate['github_url']}")
    for op in (candidate.get("online_profiles") or []):
        url = op.get("url") if isinstance(op, dict) else None
        if url and url not in str(links):
            platform = op.get("platform", "Link") if isinstance(op, dict) else "Link"
            links.append(f"{platform}: {url}")
    if links:
        story.append(Paragraph("  |  ".join(links[:3]), styles["CVSmall"]))

    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LIGHT_GRAY))

    # === SUMMARY ===
    summary = candidate.get("summary") or candidate.get("profile_summary") or candidate.get("resume_headline")
    if summary:
        story.append(Paragraph("PROFESSIONAL SUMMARY", styles["CVSection"]))
        story.append(Paragraph(summary, styles["CVBody"]))

    # === EXPERIENCE ===
    experience = candidate.get("experience") or candidate.get("work_experience") or []
    if experience:
        story.append(Paragraph("WORK EXPERIENCE", styles["CVSection"]))
        for exp in experience:
            if isinstance(exp, dict):
                title = exp.get("designation") or exp.get("title") or ""
                company = exp.get("company") or exp.get("organization") or ""
                from_d = exp.get("from_date") or exp.get("start_date") or ""
                to_d = exp.get("to_date") or exp.get("end_date") or ""
                is_current = exp.get("is_current", False)
                if is_current and not to_d:
                    to_d = "Present"
                date_str = f"{from_d} - {to_d}" if from_d else ""

                story.append(Paragraph(
                    f"<b>{title}</b>  —  {company}" + (f"  <font color='#888888'>({date_str})</font>" if date_str else ""),
                    styles["CVBody"]
                ))
                desc = exp.get("description") or exp.get("details") or ""
                if desc:
                    story.append(Paragraph(desc, styles["CVSmall"]))
                story.append(Spacer(1, 2 * mm))

    # === EDUCATION ===
    education = candidate.get("education") or []
    if education:
        story.append(Paragraph("EDUCATION", styles["CVSection"]))
        for edu in education:
            if isinstance(edu, dict):
                degree = edu.get("degree") or edu.get("qualification") or ""
                spec = edu.get("specialization") or edu.get("field") or ""
                inst = edu.get("institution") or edu.get("university") or edu.get("institute") or ""
                year = edu.get("year_of_passing") or edu.get("year") or ""
                line = f"<b>{degree}</b>"
                if spec:
                    line += f" in {spec}"
                if inst:
                    line += f"  —  {inst}"
                if year:
                    line += f"  <font color='#888888'>({year})</font>"
                story.append(Paragraph(line, styles["CVBody"]))
                story.append(Spacer(1, 1.5 * mm))

    # === SKILLS ===
    skills = candidate.get("skills") or candidate.get("key_skills") or []
    if skills:
        story.append(Paragraph("SKILLS", styles["CVSection"]))
        if isinstance(skills, list):
            skills_str = ", ".join(str(s) for s in skills if s)
        else:
            skills_str = str(skills)
        story.append(Paragraph(skills_str, styles["CVBody"]))

    # IT Skills (if different from key skills)
    it_skills = candidate.get("it_skills") or []
    if it_skills:
        it_names = []
        for s in it_skills:
            if isinstance(s, dict):
                n = s.get("name", "")
                v = s.get("version", "")
                it_names.append(f"{n} {v}".strip() if n else "")
            elif isinstance(s, str):
                it_names.append(s)
        it_names = [n for n in it_names if n]
        if it_names:
            existing_lower = set(s.lower() for s in skills) if isinstance(skills, list) else set()
            unique_it = [n for n in it_names if n.lower() not in existing_lower]
            if unique_it:
                story.append(Spacer(1, 1 * mm))
                story.append(Paragraph(f"<b>Technical:</b> {', '.join(unique_it)}", styles["CVSmall"]))

    # === CERTIFICATIONS ===
    certs = candidate.get("certifications") or candidate.get("certifications_detailed") or []
    if certs:
        story.append(Paragraph("CERTIFICATIONS", styles["CVSection"]))
        for cert in certs:
            if isinstance(cert, dict):
                cert_name = cert.get("name") or cert.get("title") or ""
            elif isinstance(cert, str):
                cert_name = cert
            else:
                continue
            if cert_name:
                story.append(Paragraph(f"- {cert_name}", styles["CVBody"]))

    # === PROJECTS ===
    projects = candidate.get("projects") or []
    if projects:
        story.append(Paragraph("PROJECTS", styles["CVSection"]))
        for proj in projects:
            if isinstance(proj, dict):
                title = proj.get("title") or proj.get("name") or ""
                desc = proj.get("description") or ""
                if title:
                    story.append(Paragraph(f"<b>{title}</b>", styles["CVBody"]))
                if desc:
                    story.append(Paragraph(desc, styles["CVSmall"]))
                story.append(Spacer(1, 1.5 * mm))

    # === LANGUAGES ===
    languages = candidate.get("languages") or []
    if languages:
        lang_strs = []
        for lang in languages:
            if isinstance(lang, dict):
                l = lang.get("language") or lang.get("name") or ""
                p = lang.get("proficiency") or ""
                lang_strs.append(f"{l} ({p})" if p else l)
            elif isinstance(lang, str):
                lang_strs.append(lang)
        if lang_strs:
            story.append(Paragraph("LANGUAGES", styles["CVSection"]))
            story.append(Paragraph(", ".join(lang_strs), styles["CVBody"]))

    # Build PDF
    try:
        doc.build(story)
    except Exception as e:
        logger.error(f"[ATS CV] PDF build failed: {e}")
        raise

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def get_cv_filename(candidate: dict) -> str:
    """Generate standardized filename: Firstname_Lastname_VHC.pdf"""
    import re
    name = candidate.get("name") or "Unknown Candidate"
    parts = name.strip().split()
    first = parts[0] if parts else "Unknown"
    last = parts[-1] if len(parts) > 1 else ""
    first = re.sub(r'[^a-zA-Z0-9]', '', first)
    last = re.sub(r'[^a-zA-Z0-9]', '', last) if last else "Candidate"
    return f"{first}_{last}_VHC.pdf"
