"""
VHC Talent OS - Analytics PDF Generator
Generates a professional PDF report from analytics data using ReportLab.
"""
import io
from datetime import datetime, timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)

WIDTH, HEIGHT = A4
BRAND = colors.HexColor("#2563eb")
BRAND_LIGHT = colors.HexColor("#dbeafe")
GREY = colors.HexColor("#64748b")
DARK = colors.HexColor("#0f172a")

SOURCE_LABELS = {
    "naukri_extension": "Naukri Extension",
    "bulk_import": "Bulk Import",
    "public_application": "Public Application",
    "admin": "Admin",
    "recruiter": "Recruiter",
    "employer": "Employer",
}


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("Title2", parent=ss["Title"], fontSize=18, textColor=DARK, spaceAfter=4))
    ss.add(ParagraphStyle("Sub", parent=ss["Normal"], fontSize=9, textColor=GREY))
    ss.add(ParagraphStyle("Section", parent=ss["Heading2"], fontSize=13, textColor=BRAND, spaceBefore=16, spaceAfter=6))
    ss.add(ParagraphStyle("Cell", parent=ss["Normal"], fontSize=9, textColor=DARK))
    ss.add(ParagraphStyle("CellBold", parent=ss["Normal"], fontSize=9, textColor=DARK, fontName="Helvetica-Bold"))
    ss.add(ParagraphStyle("CellGrey", parent=ss["Normal"], fontSize=8, textColor=GREY))
    return ss


def _kpi_table(kpis, styles):
    """Build a 4-column KPI scorecard row."""
    data = [
        [
            Paragraph("Total Captures", styles["CellGrey"]),
            Paragraph("Today / Week / Month", styles["CellGrey"]),
            Paragraph("Avg Daily (30d)", styles["CellGrey"]),
            Paragraph("Active Sources", styles["CellGrey"]),
        ],
        [
            Paragraph(f"<b>{kpis.get('total_captures', 0):,}</b>", styles["CellBold"]),
            Paragraph(
                f"<b>{kpis.get('captures_today', 0)}</b> / "
                f"{kpis.get('captures_this_week', 0)} / "
                f"{kpis.get('captures_this_month', 0)}",
                styles["CellBold"],
            ),
            Paragraph(f"<b>{kpis.get('avg_daily_rate', 0)}</b>", styles["CellBold"]),
            Paragraph(
                f"<b>{kpis.get('active_sources', 0)}</b>  ({kpis.get('total_applications', 0)} apps)",
                styles["CellBold"],
            ),
        ],
    ]
    col_w = (WIDTH - 40 * mm) / 4
    t = Table(data, colWidths=[col_w] * 4)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
        ("BACKGROUND", (0, 1), (-1, 1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _source_table(source_dist, styles):
    header = [
        Paragraph("<b>Source</b>", styles["CellBold"]),
        Paragraph("<b>Captures</b>", styles["CellBold"]),
        Paragraph("<b>Share</b>", styles["CellBold"]),
    ]
    total = sum(s["count"] for s in source_dist) or 1
    rows = [header]
    for s in source_dist:
        pct = round(s["count"] / total * 100, 1)
        rows.append([
            Paragraph(SOURCE_LABELS.get(s["source"], s["source"]), styles["Cell"]),
            Paragraph(f'{s["count"]:,}', styles["Cell"]),
            Paragraph(f"{pct}%", styles["Cell"]),
        ])
    t = Table(rows, colWidths=[80 * mm, 40 * mm, 35 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _recruiter_table(recruiters, styles):
    header = [
        Paragraph("<b>#</b>", styles["CellBold"]),
        Paragraph("<b>Name</b>", styles["CellBold"]),
        Paragraph("<b>Role</b>", styles["CellBold"]),
        Paragraph("<b>Team</b>", styles["CellBold"]),
        Paragraph("<b>Captures</b>", styles["CellBold"]),
    ]
    rows = [header]
    for i, r in enumerate(recruiters[:15], 1):
        rows.append([
            Paragraph(str(i), styles["Cell"]),
            Paragraph(r.get("name", "—"), styles["Cell"]),
            Paragraph(r.get("role", "—").capitalize(), styles["CellGrey"]),
            Paragraph(r.get("team", "—") or "—", styles["Cell"]),
            Paragraph(f'{r.get("captures", 0):,}', styles["CellBold"]),
        ])
    t = Table(rows, colWidths=[12 * mm, 50 * mm, 30 * mm, 40 * mm, 28 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _funnel_table(funnel, styles):
    header = [
        Paragraph("<b>Stage</b>", styles["CellBold"]),
        Paragraph("<b>Avg Days</b>", styles["CellBold"]),
    ]
    rows = [header]
    for stage in ["shortlisted", "interview", "offered", "hired"]:
        rows.append([
            Paragraph(stage.capitalize(), styles["Cell"]),
            Paragraph(str(funnel.get(stage, 0)), styles["CellBold"]),
        ])
    t = Table(rows, colWidths=[50 * mm, 40 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _stage_table(stage_dist, styles):
    header = [
        Paragraph("<b>Stage</b>", styles["CellBold"]),
        Paragraph("<b>Count</b>", styles["CellBold"]),
    ]
    rows = [header]
    for stage, count in sorted(stage_dist.items(), key=lambda x: -x[1]):
        rows.append([
            Paragraph(stage.capitalize(), styles["Cell"]),
            Paragraph(str(count), styles["CellBold"]),
        ])
    t = Table(rows, colWidths=[50 * mm, 40 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def build_analytics_pdf(data: dict, date_from: str = None, date_to: str = None) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=15 * mm, leftMargin=20 * mm, rightMargin=20 * mm)
    styles = _styles()
    story = []

    # Title
    story.append(Paragraph("VHC Talent OS — Analytics Report", styles["Title2"]))
    now_str = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    period = ""
    if date_from and date_to:
        period = f" | Period: {date_from} to {date_to}"
    elif date_from:
        period = f" | From: {date_from}"
    elif date_to:
        period = f" | To: {date_to}"
    story.append(Paragraph(f"Generated: {now_str}{period}", styles["Sub"]))
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 4 * mm))

    # KPI Scorecards
    story.append(Paragraph("Key Metrics", styles["Section"]))
    story.append(_kpi_table(data.get("kpis", {}), styles))

    # Source Effectiveness
    story.append(Paragraph("Source Effectiveness", styles["Section"]))
    story.append(_source_table(data.get("source_distribution", []), styles))

    # Recruiter Performance
    story.append(Paragraph("Recruiter Performance (Top 15)", styles["Section"]))
    story.append(_recruiter_table(data.get("recruiter_performance", []), styles))

    # Funnel Velocity & Stage Distribution side-by-side via a wrapper table
    story.append(Paragraph("Funnel Velocity (Avg Days)", styles["Section"]))
    story.append(_funnel_table(data.get("funnel_velocity", {}), styles))

    story.append(Paragraph("Application Stages", styles["Section"]))
    story.append(_stage_table(data.get("stage_distribution", {}), styles))

    # Capture Trends as a simple text summary
    trends = data.get("capture_trends", [])
    if trends:
        story.append(Paragraph("Capture Trends (Last 30 Days)", styles["Section"]))
        trend_lines = []
        for t in trends[-15:]:
            trend_lines.append(f'{t["date"]}: {t["count"]} captures')
        story.append(Paragraph("<br/>".join(trend_lines), styles["Cell"]))

    # Footer
    story.append(Spacer(1, 10 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0")))
    story.append(Paragraph("Confidential — VHC Talent OS", styles["CellGrey"]))

    doc.build(story)
    buf.seek(0)
    return buf
