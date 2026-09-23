"""Bill PDF renderer — Phase 55.6.

Renders a single-page (or multi-line) tax invoice in the VHC house style.
Uses reportlab — lightweight, no headless browser dependency, ~5ms/page.

Public:
    render_bill_pdf(bill_dict, signature_png_bytes=None) -> bytes
"""
from __future__ import annotations

import io
import os
from datetime import datetime
from typing import Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# ──────────────────────────────────────────────────────────────────────
# Indian-style number → words (handles up to 99,99,99,999.99)
# ──────────────────────────────────────────────────────────────────────
_ONES = [
    "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
    "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
    "Sixteen", "Seventeen", "Eighteen", "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return _TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")


def _three(n: int) -> str:
    h = n // 100
    rest = n % 100
    s = ""
    if h:
        s += _ONES[h] + " Hundred"
        if rest:
            s += " "
    if rest:
        s += _two(rest)
    return s


def amount_to_words(amount: float) -> str:
    """Indian-style amount-in-words. e.g. 4,60,998.86 → 'Four Lakh Sixty
    Thousand Nine Hundred Ninety Eight and Eighty Six paise Only'."""
    rupees = int(amount)
    paise = round((amount - rupees) * 100)
    if rupees == 0 and paise == 0:
        return "Zero Only"

    crore = rupees // 10_000_000
    rupees %= 10_000_000
    lakh = rupees // 100_000
    rupees %= 100_000
    thousand = rupees // 1000
    rupees %= 1000
    parts = []
    if crore:
        parts.append(_two(crore) + " Crore")
    if lakh:
        parts.append(_two(lakh) + " Lakh")
    if thousand:
        parts.append(_two(thousand) + " Thousand")
    if rupees:
        parts.append(_three(rupees))
    words = " ".join(parts).strip() or "Zero"

    if paise:
        words += f" and {_two(paise)} paise"
    return "Indian Rupees " + words + " Only"


# ──────────────────────────────────────────────────────────────────────
# Style helpers
# ──────────────────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=14, leading=16, textColor=colors.HexColor("#111111"),
            alignment=1,  # centre
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=10, leading=12, textColor=colors.HexColor("#222222"),
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9, leading=12, textColor=colors.HexColor("#222222"),
        ),
        "small": ParagraphStyle(
            "small", parent=base["BodyText"], fontName="Helvetica",
            fontSize=8, leading=10, textColor=colors.HexColor("#555555"),
        ),
    }


def _fmt_inr(n: float) -> str:
    """Indian numeric formatting — 12,34,567.89."""
    neg = n < 0
    n = abs(n)
    int_part = int(n)
    frac = round((n - int_part) * 100)
    s = str(int_part)
    if len(s) > 3:
        head = s[:-3]
        tail = s[-3:]
        # group head from the right into 2's
        chunks = []
        while len(head) > 2:
            chunks.insert(0, head[-2:])
            head = head[:-2]
        if head:
            chunks.insert(0, head)
        s = ",".join(chunks) + "," + tail
    out = f"{s}.{frac:02d}"
    return ("-" if neg else "") + out


# ──────────────────────────────────────────────────────────────────────
# Letterhead — drawn as a page background on every page.
# The two entities (Ventures HRD Centre / Ventures HRD Centre Pvt. Ltd.)
# share this exact layout; only the top-centre legal name changes.
# ──────────────────────────────────────────────────────────────────────
def _make_letterhead_painter(sender_name: str, tagline: str, address: str,
                              logo_png_bytes: Optional[bytes] = None):
    def _paint(canvas, doc):
        canvas.saveState()
        page_w, page_h = A4

        # ── Top-of-page letterhead ─────────────────────────────────
        if logo_png_bytes:
            try:
                from reportlab.lib.utils import ImageReader
                img = ImageReader(io.BytesIO(logo_png_bytes))
                canvas.drawImage(img, 15 * mm, page_h - 30 * mm,
                                 width=22 * mm, height=22 * mm,
                                 preserveAspectRatio=True, mask="auto")
            except Exception:
                pass
        canvas.setFillColor(colors.HexColor("#0B1F3A"))
        canvas.setFont("Helvetica-Bold", 20)
        canvas.drawCentredString(page_w / 2, page_h - 18 * mm, sender_name)
        canvas.setFont("Helvetica-Oblique", 10)
        canvas.setFillColor(colors.HexColor("#7A8794"))
        canvas.drawCentredString(page_w / 2, page_h - 24 * mm, tagline)
        # Thin brand rule below the letterhead.
        canvas.setStrokeColor(colors.HexColor("#7CB342"))
        canvas.setLineWidth(1.2)
        canvas.line(15 * mm, page_h - 27 * mm, page_w - 15 * mm, page_h - 27 * mm)

        # ── Bottom-of-page footer strip ────────────────────────────
        canvas.setStrokeColor(colors.HexColor("#7CB342"))
        canvas.setLineWidth(0.8)
        canvas.line(15 * mm, 17 * mm, page_w - 15 * mm, 17 * mm)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(colors.HexColor("#0B1F3A"))
        canvas.drawCentredString(page_w / 2, 12 * mm, address)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#556270"))
        canvas.drawCentredString(
            page_w / 2, 7 * mm,
            "E-mail : bsy@vhc.in    |    Web : www.ventureshrd.com",
        )
        canvas.restoreState()
    return _paint


# ──────────────────────────────────────────────────────────────────────
# Renderer
# ──────────────────────────────────────────────────────────────────────
def render_bill_pdf(bill: Dict, signature_png_bytes: Optional[bytes] = None,
                    logo_png_bytes: Optional[bytes] = None) -> bytes:
    """Render a tax invoice PDF and return the bytes.

    `bill` matches the shape of `models.bill.BillRecord.model_dump()`.
    Uses the two-entity letterhead (VHC.docx / VHCPL.docx) as a page background
    picked from `bill["sender_legal_name"]`; the invoice body content is
    unchanged from the pre-template renderer.
    """
    # Entity tagline is fixed for both sender variants (user templates 2026-02).
    sender_name = bill.get("sender_legal_name", "Ventures HRD Centre")
    tagline = "For Complete HR Solutions"
    address = bill.get("sender_address", "")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        # Top margin must clear the letterhead (name + tagline + rule ≈ 30 mm).
        # Bottom margin must clear the footer strip (rule + address + web ≈ 22 mm).
        topMargin=32 * mm, bottomMargin=24 * mm,
        title=f"Bill {bill.get('bill_number')}",
        author=sender_name,
    )
    S = _styles()
    story = []
    paint = _make_letterhead_painter(sender_name, tagline, address, logo_png_bytes)

    # The sender name + tagline + address are now painted as the page
    # letterhead (see `_make_letterhead_painter`). We keep the GSTIN / PAN
    # here so the tax details still sit inside the invoice body — the legacy
    # renderer's inline sender header is intentionally removed to avoid a
    # visual duplicate of the entity name.
    if bill.get("sender_gstin") or bill.get("sender_pan"):
        gp_html = (
            f'GSTIN: <b>{bill.get("sender_gstin","")}</b>'
            + (f' &nbsp;&nbsp; PAN: <b>{bill.get("sender_pan","")}</b>' if bill.get("sender_pan") else "")
        )
        story.append(Paragraph(gp_html, S["body"]))
        story.append(Spacer(1, 3 * mm))

    # ── Title ──
    story.append(Paragraph("<b>TAX INVOICE</b>", S["h1"]))
    story.append(Spacer(1, 3 * mm))

    # ── Invoice meta ──
    bill_no = bill.get("bill_number", "")
    bill_date = bill.get("bill_date", "")
    due_date = bill.get("due_date") or "-"
    meta_tbl = Table([
        [
            Paragraph(f"<b>Invoice No:</b> {bill_no}", S["body"]),
            Paragraph(f"<b>Invoice Date:</b> {bill_date}", S["body"]),
            Paragraph(f"<b>Due Date:</b> {due_date}", S["body"]),
        ]
    ], colWidths=[None, None, None])
    meta_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#888888")),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#aaaaaa")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 4 * mm))

    # ── Bill To ──
    bill_to_html = (
        f'<b>Bill To:</b><br/>'
        f'<b>{bill.get("client_legal_name","")}</b><br/>'
        f'{bill.get("client_address","")}<br/>'
        f'GSTIN: <b>{bill.get("client_gstin","")}</b><br/>'
        f'State Code: {bill.get("client_state_code","")}'
    )
    btbl = Table([[Paragraph(bill_to_html, S["body"])]], colWidths=[None])
    btbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#888888")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(btbl)
    story.append(Spacer(1, 4 * mm))

    # ── Line items ──
    items: List[Dict] = bill.get("line_items") or []
    gst_kind = (bill.get("totals") or {}).get("gst_kind") or "IGST"
    nature = "Interstate" if gst_kind == "IGST" else "Intrastate"

    table_data = [[
        Paragraph("<b>#</b>", S["body"]),
        Paragraph("<b>Particulars</b>", S["body"]),
        Paragraph("<b>HSN/SAC</b>", S["body"]),
        Paragraph("<b>Annual CTC</b>", S["body"]),
        Paragraph("<b>%</b>", S["body"]),
        Paragraph("<b>Amount (Rs.)</b>", S["body"]),
    ]]
    for idx, li in enumerate(items, 1):
        particulars = (
            f"CONSULTANCY CHARGES – {nature}<br/>"
            f"<b>{li.get('candidate_name','')}</b>"
            + (f" — {li.get('designation')}" if li.get("designation") else "")
            + f"<br/>D.O.J: {li.get('joining_date','')}"
        )
        table_data.append([
            Paragraph(str(idx), S["body"]),
            Paragraph(particulars, S["body"]),
            Paragraph(li.get("hsn_sac", "998512"), S["body"]),
            Paragraph(_fmt_inr(li.get("annual_ctc", 0)), S["body"]),
            Paragraph(f"{li.get('commercial_rate_pct', 0):.2f}%", S["body"]),
            Paragraph(_fmt_inr(li.get("line_amount", 0)), S["body"]),
        ])

    items_tbl = Table(table_data, colWidths=[10 * mm, 70 * mm, 18 * mm, 28 * mm, 16 * mm, 28 * mm], repeatRows=1)
    items_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#666666")),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#bbbbbb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (3, 0), (5, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 3 * mm))

    # ── Totals ──
    totals = bill.get("totals") or {}
    taxable = totals.get("taxable_value", 0)
    grand = totals.get("grand_total", 0)
    tax_total = totals.get("tax_total", 0)
    rows = [
        ["Taxable Value", _fmt_inr(taxable)],
    ]
    if gst_kind == "IGST":
        rows.append([f"IGST @ {totals.get('igst_pct', 18)}%", _fmt_inr(tax_total)])
    else:
        cg = round(taxable * (totals.get("cgst_pct", 9) / 100), 2)
        sg = round(taxable * (totals.get("sgst_pct", 9) / 100), 2)
        rows.append([f"CGST @ {totals.get('cgst_pct', 9)}%", _fmt_inr(cg)])
        rows.append([f"SGST @ {totals.get('sgst_pct', 9)}%", _fmt_inr(sg)])
    rows.append(["Grand Total", _fmt_inr(grand)])

    tot_tbl = Table(rows, colWidths=[120 * mm, 50 * mm], hAlign="RIGHT")
    tot_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#666666")),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#bbbbbb")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F4F4F4")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(tot_tbl)
    story.append(Spacer(1, 4 * mm))

    # ── Amount in words ──
    story.append(Paragraph(f"<b>Amount in Words:</b> {totals.get('amount_in_words','')}", S["body"]))
    story.append(Paragraph(f"<b>Tax Amount (in words):</b> {totals.get('tax_in_words','')}", S["body"]))
    story.append(Spacer(1, 5 * mm))

    # ── Bank details block (fix.docx 2026-09-15) ──
    _bank = bill.get("bank_account") or {}
    if _bank and (_bank.get("account_number") or _bank.get("bank_name")):
        bank_rows = [
            [Paragraph("<b>Bank Details (for NEFT / RTGS / IMPS)</b>", S["body"]), ""],
            [Paragraph("Bank Name",        S["small"]), Paragraph(_bank.get("bank_name", ""),        S["small"])],
            [Paragraph("Beneficiary Name", S["small"]), Paragraph(_bank.get("beneficiary_name", ""), S["small"])],
            [Paragraph("Branch",           S["small"]), Paragraph(_bank.get("branch", ""),           S["small"])],
            [Paragraph("A/C Number",       S["small"]), Paragraph(_bank.get("account_number", ""),   S["small"])],
            [Paragraph("IFSC Code",        S["small"]), Paragraph(_bank.get("ifsc", ""),             S["small"])],
        ]
        bank_tbl = Table(bank_rows, colWidths=[45 * mm, None])
        bank_tbl.setStyle(TableStyle([
            ("SPAN",     (0, 0), (1, 0)),
            ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#F4F4F4")),
            ("BOX",      (0, 0), (-1, -1), 0.5, colors.HexColor("#666666")),
            ("INNERGRID",(0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
            ("VALIGN",   (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING",   (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ]))
        story.append(bank_tbl)
        story.append(Spacer(1, 5 * mm))

    # ── Declaration / payment terms ──
    decl = (
        "<b>Declaration:</b><br/>"
        "1. Cheques to be issued in favour of "
        f"<b>{bill.get('sender_legal_name','')}</b>, Payable at Delhi.<br/>"
        "2. Delay in payment after the due date will incur interest at 18% p.a.<br/>"
        "3. This is a Computer Generated Invoice."
    )
    story.append(Paragraph(decl, S["small"]))
    story.append(Spacer(1, 12 * mm))

    # ── Signature block ──
    sig_cells = []
    if signature_png_bytes:
        try:
            sig_img = Image(io.BytesIO(signature_png_bytes), width=42 * mm, height=18 * mm)
            sig_cells.append(sig_img)
        except Exception:
            sig_cells.append(Paragraph("&nbsp;", S["body"]))
    else:
        sig_cells.append(Paragraph("&nbsp;", S["body"]))

    sig_tbl = Table([
        [sig_cells[0]],
        [Paragraph(f"for <b>{bill.get('sender_legal_name','')}</b>", S["small"])],
        [Paragraph("<b>Authorised Signatory</b>", S["small"])],
    ], colWidths=[60 * mm], hAlign="RIGHT")
    sig_tbl.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(sig_tbl)

    doc.build(story, onFirstPage=paint, onLaterPages=paint)
    return buf.getvalue()
