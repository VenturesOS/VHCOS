"""
Training Manual PDF Service
Converts the Markdown training manual to a styled PDF.
"""
import os
import markdown
import pdfkit
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MANUAL_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "TRAINING_MANUAL.md"

CSS_STYLE = """
<style>
  body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    color: #1e293b;
    line-height: 1.7;
    margin: 40px 60px;
    font-size: 13px;
  }
  h1 {
    color: #166534;
    border-bottom: 3px solid #7CB342;
    padding-bottom: 8px;
    margin-top: 32px;
    font-size: 22px;
  }
  h2 {
    color: #1e40af;
    margin-top: 24px;
    font-size: 17px;
  }
  h3 {
    color: #334155;
    margin-top: 18px;
    font-size: 15px;
  }
  table {
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
  }
  th, td {
    border: 1px solid #cbd5e1;
    padding: 8px 12px;
    text-align: left;
    font-size: 12px;
  }
  th {
    background-color: #f1f5f9;
    font-weight: 600;
  }
  code {
    background: #f1f5f9;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 12px;
  }
  blockquote {
    border-left: 4px solid #7CB342;
    margin: 16px 0;
    padding: 8px 16px;
    background: #f0fdf4;
    color: #334155;
  }
  ul, ol {
    margin: 8px 0;
    padding-left: 24px;
  }
  li {
    margin-bottom: 4px;
  }
  hr {
    border: none;
    border-top: 2px solid #e2e8f0;
    margin: 24px 0;
  }
  .header-banner {
    background: linear-gradient(135deg, #166534, #7CB342);
    color: white;
    padding: 24px 32px;
    margin: -40px -60px 32px -60px;
    text-align: center;
  }
  .header-banner h1 {
    color: white;
    border: none;
    margin: 0;
    font-size: 26px;
  }
  .header-banner p {
    color: #dcfce7;
    margin: 4px 0 0 0;
    font-size: 14px;
  }
</style>
"""


async def generate_training_manual_pdf() -> bytes:
    """Read the training manual markdown and convert it to a styled PDF."""
    if not MANUAL_PATH.exists():
        raise FileNotFoundError(f"Training manual not found at {MANUAL_PATH}")

    md_content = MANUAL_PATH.read_text(encoding="utf-8")

    html_body = markdown.markdown(
        md_content,
        extensions=["tables", "fenced_code", "toc", "nl2br"],
    )

    header_banner = (
        '<div class="header-banner">'
        "<h1>Ventures HRD &mdash; Talent OS</h1>"
        "<p>Portal Training Manual &bull; Version 1.0 &bull; February 2026</p>"
        "</div>"
    )

    full_html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"{CSS_STYLE}</head><body>{header_banner}{html_body}</body></html>"
    )

    options = {
        "page-size": "A4",
        "margin-top": "0mm",
        "margin-right": "0mm",
        "margin-bottom": "10mm",
        "margin-left": "0mm",
        "encoding": "UTF-8",
        "enable-local-file-access": "",
        "print-media-type": "",
        "no-outline": None,
    }

    pdf_bytes = pdfkit.from_string(full_html, False, options=options)
    logger.info("Training manual PDF generated (%d bytes)", len(pdf_bytes))
    return pdf_bytes
