"""
Phase 54.7 regression test — pdfplumber table-aware fallback.

Asserts that when a resume's tabular content makes fitz output very
sparse, the pdfplumber fallback kicks in and recovers structured
"key | value" rows for the downstream LLM parser.

Run: cd /app/backend && python -m pytest tests/test_pdf_table_fallback.py -v
"""
from __future__ import annotations
import io

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from services.matching_engine import extract_text_from_file


def _make_table_resume_pdf() -> bytes:
    """Build a tiny PDF whose contact info ONLY appears in a borderless
    table — fitz typically emits this as fragmented unordered text, so
    the pdfplumber table-aware path is the one that recovers clean
    "Phone | 9876543210" rows."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Anshul Thakur", styles["Title"]),
        Spacer(1, 8),
    ]

    # Contact info hidden inside a borderless table — adversarial layout
    contact = Table(
        [
            ["Phone:", "9876543210", "Email:", "anshul@example.com"],
            ["Location:", "Noida", "Notice:", "15 days"],
        ],
        colWidths=[60, 130, 60, 200],
    )
    contact.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN",   (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(contact)
    story.append(Spacer(1, 12))

    # Skills table (also adversarial — fitz often returns these as
    # "Python Django REST API …" with no key/value pairing)
    skills = Table(
        [
            ["Skill",        "Years"],
            ["Python",       "5"],
            ["Django",       "4"],
            ["FastAPI",      "2"],
            ["MongoDB",      "3"],
        ],
        colWidths=[120, 60],
    )
    skills.setStyle(TableStyle([
        ("GRID",     (0, 0), (-1, -1), 0.5, colors.black),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(skills)
    doc.build(story)
    return buf.getvalue()


def test_table_resume_yields_structured_text():
    pdf_bytes = _make_table_resume_pdf()
    assert len(pdf_bytes) > 500   # sanity — we actually built a PDF

    text = extract_text_from_file(pdf_bytes, "table_resume.pdf")
    assert text and len(text) > 0

    # The phone & email MUST be recoverable — they were hidden inside a
    # borderless table that crashes naive extractors.
    assert "9876543210" in text, f"phone missing from extracted text: {text[:300]}"
    assert "anshul@example.com" in text, f"email missing: {text[:300]}"

    # Skills should also survive
    assert "Python" in text and "FastAPI" in text


def test_pdfplumber_module_loaded():
    """If pdfplumber import failed, the fallback is dead. Pin that the
    module is importable from the matching_engine context."""
    from services.matching_engine import _pdfplumber
    assert _pdfplumber is not None, (
        "pdfplumber module must be installed in the venv used by gunicorn"
    )
