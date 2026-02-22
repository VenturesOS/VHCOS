"""
Training Manual PDF Service
Converts the Markdown training manual to a styled PDF.
Uses pdfkit/wkhtmltopdf as primary, reportlab as fallback.
"""
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

MANUAL_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "TRAINING_MANUAL.md"


def _wkhtmltopdf_available() -> bool:
    return shutil.which("wkhtmltopdf") is not None


async def _generate_with_pdfkit(md_content: str) -> bytes:
    import markdown
    import pdfkit

    html_body = markdown.markdown(
        md_content,
        extensions=["tables", "fenced_code", "toc", "nl2br"],
    )

    css = """
    <style>
      body { font-family: 'Segoe UI', Tahoma, sans-serif; color: #1e293b; line-height: 1.7; margin: 40px 60px; font-size: 13px; }
      h1 { color: #166534; border-bottom: 3px solid #7CB342; padding-bottom: 8px; margin-top: 32px; font-size: 22px; }
      h2 { color: #1e40af; margin-top: 24px; font-size: 17px; }
      h3 { color: #334155; margin-top: 18px; font-size: 15px; }
      table { border-collapse: collapse; width: 100%; margin: 16px 0; }
      th, td { border: 1px solid #cbd5e1; padding: 8px 12px; text-align: left; font-size: 12px; }
      th { background-color: #f1f5f9; font-weight: 600; }
      code { background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 12px; }
      blockquote { border-left: 4px solid #7CB342; margin: 16px 0; padding: 8px 16px; background: #f0fdf4; }
      ul, ol { margin: 8px 0; padding-left: 24px; }
      li { margin-bottom: 4px; }
      hr { border: none; border-top: 2px solid #e2e8f0; margin: 24px 0; }
    </style>
    """

    banner = (
        '<div style="background:linear-gradient(135deg,#166534,#7CB342);color:white;'
        'padding:24px 32px;margin:-40px -60px 32px -60px;text-align:center;">'
        '<h1 style="color:white;border:none;margin:0;font-size:26px;">Ventures HRD — Talent OS</h1>'
        '<p style="color:#dcfce7;margin:4px 0 0 0;font-size:14px;">Portal Training Manual</p>'
        '</div>'
    )

    full_html = f"<!DOCTYPE html><html><head><meta charset='utf-8'>{css}</head><body>{banner}{html_body}</body></html>"

    options = {
        "page-size": "A4",
        "margin-top": "0mm",
        "margin-right": "0mm",
        "margin-bottom": "10mm",
        "margin-left": "0mm",
        "encoding": "UTF-8",
        "enable-local-file-access": "",
        "no-outline": None,
    }

    return pdfkit.from_string(full_html, False, options=options)


async def _generate_with_reportlab(md_content: str) -> bytes:
    """Fallback: generate a clean PDF using reportlab (no system dependencies)."""
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=15*mm, leftMargin=20*mm, rightMargin=20*mm)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ManualH1", parent=styles["Heading1"], fontSize=18, textColor=HexColor("#166534"), spaceAfter=10, spaceBefore=20))
    styles.add(ParagraphStyle(name="ManualH2", parent=styles["Heading2"], fontSize=14, textColor=HexColor("#1e40af"), spaceAfter=8, spaceBefore=14))
    styles.add(ParagraphStyle(name="ManualH3", parent=styles["Heading3"], fontSize=12, textColor=HexColor("#334155"), spaceAfter=6, spaceBefore=10))
    styles.add(ParagraphStyle(name="ManualBody", parent=styles["Normal"], fontSize=10, leading=15, spaceAfter=6))
    styles.add(ParagraphStyle(name="ManualBullet", parent=styles["Normal"], fontSize=10, leading=15, leftIndent=20, spaceAfter=3))

    story = []

    # Title block
    story.append(Paragraph("Ventures HRD — Talent OS", styles["ManualH1"]))
    story.append(Paragraph("Portal Training Manual", styles["ManualH2"]))
    story.append(Spacer(1, 10))

    for line in md_content.split("\n"):
        stripped = line.strip()
        if not stripped:
            story.append(Spacer(1, 4))
            continue

        # Headings
        if stripped.startswith("### "):
            story.append(Paragraph(stripped[4:], styles["ManualH3"]))
        elif stripped.startswith("## "):
            story.append(Paragraph(stripped[3:], styles["ManualH2"]))
        elif stripped.startswith("# "):
            story.append(Paragraph(stripped[2:], styles["ManualH1"]))
        elif stripped.startswith("- ") or stripped.startswith("* "):
            text = stripped[2:]
            # Bold prefix handling
            if text.startswith("**") and "**" in text[2:]:
                end = text.index("**", 2)
                text = f"<b>{text[2:end]}</b>{text[end+2:]}"
            story.append(Paragraph(f"• {text}", styles["ManualBullet"]))
        elif stripped.startswith("---"):
            story.append(Spacer(1, 10))
        elif stripped.startswith(">"):
            text = stripped.lstrip("> ")
            story.append(Paragraph(f"<i>{text}</i>", styles["ManualBody"]))
        else:
            # Handle inline bold
            text = stripped
            while "**" in text:
                start = text.index("**")
                rest = text[start+2:]
                if "**" in rest:
                    end = rest.index("**")
                    text = text[:start] + f"<b>{rest[:end]}</b>" + rest[end+2:]
                else:
                    break
            story.append(Paragraph(text, styles["ManualBody"]))

    doc.build(story)
    return buf.getvalue()


async def generate_training_manual_pdf() -> bytes:
    """Read the training manual markdown and convert to PDF."""
    if not MANUAL_PATH.exists():
        raise FileNotFoundError(f"Training manual not found at {MANUAL_PATH}")

    md_content = MANUAL_PATH.read_text(encoding="utf-8")

    # Try pdfkit first, fall back to reportlab
    if _wkhtmltopdf_available():
        try:
            pdf_bytes = await _generate_with_pdfkit(md_content)
            logger.info("Training manual PDF generated via pdfkit (%d bytes)", len(pdf_bytes))
            return pdf_bytes
        except Exception as e:
            logger.warning("pdfkit failed, falling back to reportlab: %s", e)

    pdf_bytes = await _generate_with_reportlab(md_content)
    logger.info("Training manual PDF generated via reportlab (%d bytes)", len(pdf_bytes))
    return pdf_bytes
