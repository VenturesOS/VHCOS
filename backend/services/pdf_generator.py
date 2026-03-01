"""
Pure-Python PDF resume generator using fpdf2.
No system dependencies required — works in any deployment environment.
"""
from fpdf import FPDF
import io
import os
import re

# Font directory (optional — fpdf2 ships with Helvetica/Courier built-in)
_FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")


class _ResumePDF(FPDF):
    """Minimal subclass to set consistent defaults."""

    def __init__(self):
        super().__init__(format="A4")
        self.set_auto_page_break(auto=True, margin=15)
        self.add_page()
        self.set_margins(15, 12, 15)

    def _section_heading(self, title: str):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(30, 30, 30)
        self.cell(0, 7, title.upper(), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(180, 180, 180)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)

    def _body_text(self, text: str, size: int = 10):
        self.set_font("Helvetica", "", size)
        self.set_text_color(60, 60, 60)
        self.multi_cell(0, 5, text)
        self.ln(1)


def _clean(val) -> str:
    """Safely convert to string, stripping None."""
    if val is None:
        return ""
    return str(val).strip()


def build_pdf_from_profile(profile: dict) -> bytes:
    """Generate a professional PDF resume from profile dict. Returns PDF bytes."""
    p = profile
    name = _clean(p.get("name"))
    email = _clean(p.get("email"))
    phone = _clean(p.get("phone"))
    location = _clean(p.get("location"))
    linkedin = _clean(p.get("linkedin"))
    summary = _clean(p.get("summary"))
    skills = p.get("skills") or []
    experience = p.get("experience") or []
    education = p.get("education") or []

    pdf = _ResumePDF()

    # ── Header ──────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 10, name or "Candidate Resume", align="C", new_x="LMARGIN", new_y="NEXT")

    contact_parts = [x for x in [phone, email, location] if x]
    if contact_parts:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 5, "  |  ".join(contact_parts), align="C", new_x="LMARGIN", new_y="NEXT")
    if linkedin:
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(60, 100, 160)
        pdf.cell(0, 5, linkedin, align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_draw_color(120, 120, 120)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(4)

    # ── Summary ─────────────────────────────────────────────────────────
    if summary:
        pdf._section_heading("Summary")
        pdf._body_text(summary)
        pdf.ln(2)

    # ── Experience ──────────────────────────────────────────────────────
    if experience:
        pdf._section_heading("Experience")
        for exp in experience:
            title = _clean(exp.get("title"))
            company = _clean(exp.get("company"))
            duration = _clean(exp.get("duration"))

            # Title and duration on same line
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(30, 30, 30)
            title_w = pdf.get_string_width(title) + 2
            dur_w = pdf.get_string_width(duration) + 2
            avail = pdf.w - pdf.l_margin - pdf.r_margin

            pdf.cell(avail - dur_w, 5, title)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(130, 130, 130)
            pdf.cell(dur_w, 5, duration, align="R", new_x="LMARGIN", new_y="NEXT")

            if company:
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(80, 80, 80)
                pdf.cell(0, 5, company, new_x="LMARGIN", new_y="NEXT")

            bullets = [b for b in (exp.get("bullets") or []) if b and _clean(b)]
            for bullet in bullets:
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(60, 60, 60)
                pdf.cell(5)  # indent
                pdf.cell(4, 4.5, chr(8226))  # bullet char
                pdf.multi_cell(0, 4.5, _clean(bullet))

            pdf.ln(3)

    # ── Education ───────────────────────────────────────────────────────
    if education:
        pdf._section_heading("Education")
        for edu in education:
            degree = _clean(edu.get("degree"))
            institution = _clean(edu.get("institution"))
            year = _clean(edu.get("year"))
            gpa = _clean(edu.get("gpa"))

            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(30, 30, 30)
            yr_w = pdf.get_string_width(year) + 2 if year else 0
            avail = pdf.w - pdf.l_margin - pdf.r_margin
            pdf.cell(avail - yr_w, 5, degree)
            if year:
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(130, 130, 130)
                pdf.cell(yr_w, 5, year, align="R")
            pdf.ln()

            sub_line = institution
            if gpa:
                sub_line += f"  |  GPA: {gpa}"
            if sub_line:
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(80, 80, 80)
                pdf.cell(0, 5, sub_line, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)

    # ── Skills ──────────────────────────────────────────────────────────
    if skills:
        pdf._section_heading("Skills")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(60, 60, 60)
        skills_text = "  \u2022  ".join(str(s) for s in skills if s)
        pdf.multi_cell(0, 5, skills_text)

    # ── Output ──────────────────────────────────────────────────────────
    return pdf.output()
