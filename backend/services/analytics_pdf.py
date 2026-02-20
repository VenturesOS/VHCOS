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

    # AI Search Analytics (includes cost data — PDF only)
    ai_data = data.get("ai_search", {})
    if ai_data.get("total_searches", 0) > 0:
        story.append(Paragraph("AI Search Analytics", styles["Section"]))
        ai_rows = [
            [Paragraph("<b>Metric</b>", styles["CellBold"]), Paragraph("<b>Value</b>", styles["CellBold"])],
            [Paragraph("Total AI Searches", styles["Cell"]), Paragraph(str(ai_data["total_searches"]), styles["Cell"])],
        ]
        cost = ai_data.get("cost_data", {})
        if cost:
            ai_rows.extend([
                [Paragraph("Total Input Tokens", styles["Cell"]), Paragraph(f'{cost.get("total_input_tokens", 0):,}', styles["Cell"])],
                [Paragraph("Total Output Tokens", styles["Cell"]), Paragraph(f'{cost.get("total_output_tokens", 0):,}', styles["Cell"])],
                [Paragraph("Total Cost (USD)", styles["Cell"]), Paragraph(f'${cost.get("total_cost_usd", 0):.4f}', styles["Cell"])],
                [Paragraph("Avg Cost per Search (USD)", styles["Cell"]), Paragraph(f'${cost.get("avg_cost_per_search_usd", 0):.4f}', styles["Cell"])],
                [Paragraph("Avg Response Time", styles["Cell"]), Paragraph(f'{cost.get("avg_time_s", 0)}s', styles["Cell"])],
            ])
        t = Table(ai_rows, colWidths=[120 * mm, 50 * mm])
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(t)

        # Top Searched Skills
        skills = ai_data.get("top_searched_skills", [])
        if skills:
            story.append(Spacer(1, 3 * mm))
            story.append(Paragraph("Top Searched Skills", styles["Section"]))
            skill_rows = [[Paragraph("<b>Skill</b>", styles["CellBold"]), Paragraph("<b>Search Count</b>", styles["CellBold"])]]
            for s in skills:
                skill_rows.append([Paragraph(s["skill"], styles["Cell"]), Paragraph(str(s["count"]), styles["Cell"])])
            st = Table(skill_rows, colWidths=[120 * mm, 50 * mm])
            st.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ]))
            story.append(st)

        # Zero Result Prompts (Demand Gaps)
        zeros = ai_data.get("zero_result_prompts", [])
        if zeros:
            story.append(Spacer(1, 3 * mm))
            story.append(Paragraph("Demand Gaps (Zero-Result Searches)", styles["Section"]))
            for z in zeros:
                story.append(Paragraph(f'&bull; "{z.get("raw_prompt", "")}"', styles["Cell"]))

    story.append(Spacer(1, 5 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0")))
    story.append(Paragraph("Confidential — VHC Talent OS", styles["CellGrey"]))

    doc.build(story)
    buf.seek(0)
    return buf


def _table_style():
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ])


STAGE_LABELS = {
    "applied": "Applied", "shortlisted": "Shortlisted", "submitted_to_client": "Submitted to Client",
    "interview": "Interview", "offered": "Offered", "hired": "Hired", "joined": "Joined",
    "rejected": "Rejected", "on_hold": "On Hold",
}


def _fmt_currency(v):
    if v >= 100000:
        return f"{v/100000:.1f}L"
    if v >= 1000:
        return f"{v/1000:.0f}K"
    return f"{v:,.0f}"


def build_combined_pdf(overview, pipeline, revenue, performance, date_from=None, date_to=None):
    """Build combined analytics PDF: Revenue → Pipeline → Performance → Overview."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=15 * mm, leftMargin=20 * mm, rightMargin=20 * mm)
    styles = _styles()
    story = []
    col_full = WIDTH - 40 * mm

    # Title
    story.append(Paragraph("VHC Talent OS — Complete Analytics Report", styles["Title2"]))
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

    # ═══ 1. REVENUE INTELLIGENCE ═══
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("1. Revenue Intelligence", styles["Title2"]))
    story.append(Spacer(1, 2 * mm))

    forecast = revenue.get("total_forecast_pipeline", 0)
    realized = revenue.get("total_realized_revenue", 0)
    total_cands = revenue.get("total_candidates_with_offer", 0)
    prob_map = revenue.get("probability_map", {})

    rev_kpi = [
        [Paragraph("Weighted Forecast", styles["CellGrey"]), Paragraph("Realized Revenue", styles["CellGrey"]), Paragraph("In Pipeline", styles["CellGrey"])],
        [Paragraph(f"<b>{_fmt_currency(forecast)}</b>", styles["CellBold"]), Paragraph(f"<b>{_fmt_currency(realized)}</b>", styles["CellBold"]), Paragraph(f"<b>{total_cands}</b> candidates", styles["CellBold"])],
    ]
    t = Table(rev_kpi, colWidths=[col_full / 3] * 3)
    t.setStyle(_table_style())
    story.append(t)

    by_stage = revenue.get("by_stage", {})
    if by_stage:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("Revenue by Stage", styles["Section"]))
        rows = [[Paragraph(f"<b>{h}</b>", styles["CellBold"]) for h in ["Stage", "Candidates", "Total Rev", "Weighted Rev", "Probability"]]]
        for stage in ["applied", "shortlisted", "submitted_to_client", "interview", "offered", "hired", "joined"]:
            s = by_stage.get(stage)
            if not s:
                continue
            rows.append([
                Paragraph(STAGE_LABELS.get(stage, stage), styles["Cell"]),
                Paragraph(str(s["count"]), styles["Cell"]),
                Paragraph(_fmt_currency(s["total_revenue"]), styles["Cell"]),
                Paragraph(_fmt_currency(s["weighted_revenue"]), styles["CellBold"]),
                Paragraph(f'{s["probability"]}%', styles["Cell"]),
            ])
        t = Table(rows, colWidths=[35 * mm, 25 * mm, 30 * mm, 35 * mm, 25 * mm])
        t.setStyle(_table_style())
        story.append(t)

    if prob_map:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("Stage Probability Map", styles["Section"]))
        rows = [[Paragraph(f"<b>{STAGE_LABELS.get(s, s)}</b>", styles["CellBold"]) for s in ["applied", "shortlisted", "submitted_to_client", "interview", "offered", "hired", "joined"]]]
        rows.append([Paragraph(f'{prob_map.get(s, 0)}%', styles["Cell"]) for s in ["applied", "shortlisted", "submitted_to_client", "interview", "offered", "hired", "joined"]])
        t = Table(rows, colWidths=[col_full / 7] * 7)
        t.setStyle(_table_style())
        story.append(t)

    # ═══ 2. PIPELINE FUNNEL ═══
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("2. Pipeline Funnel", styles["Title2"]))
    story.append(Spacer(1, 2 * mm))

    total_apps = pipeline.get("total_applications", 0)
    conversions = pipeline.get("conversions", {})
    stage_counts = pipeline.get("stage_counts", {})

    pipe_kpi = [
        [Paragraph("Total Applications", styles["CellGrey"]), Paragraph("Shortlisted", styles["CellGrey"]), Paragraph("Offered", styles["CellGrey"]), Paragraph("Joined", styles["CellGrey"])],
        [
            Paragraph(f"<b>{total_apps}</b>", styles["CellBold"]),
            Paragraph(f'<b>{conversions.get("applied_to_shortlisted", {}).get("count", 0)}</b> ({conversions.get("applied_to_shortlisted", {}).get("rate", 0)}%)', styles["CellBold"]),
            Paragraph(f'<b>{conversions.get("interview_to_offered", {}).get("count", 0)}</b> ({conversions.get("interview_to_offered", {}).get("rate", 0)}%)', styles["CellBold"]),
            Paragraph(f'<b>{conversions.get("hired_to_joined", {}).get("count", 0)}</b>', styles["CellBold"]),
        ],
    ]
    t = Table(pipe_kpi, colWidths=[col_full / 4] * 4)
    t.setStyle(_table_style())
    story.append(t)

    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Conversion Rates", styles["Section"]))
    conv_entries = [
        ("applied_to_shortlisted", "Applied → Shortlisted"),
        ("shortlisted_to_submitted", "Shortlisted → Submitted"),
        ("submitted_to_interview", "Submitted → Interview"),
        ("interview_to_offered", "Interview → Offered"),
        ("offered_to_hired", "Offered → Hired"),
        ("hired_to_joined", "Hired → Joined"),
    ]
    conv_rows = [[Paragraph(f"<b>{h}</b>", styles["CellBold"]) for h in ["Transition", "Count", "Rate"]]]
    for key, label in conv_entries:
        c = conversions.get(key, {})
        conv_rows.append([
            Paragraph(label, styles["Cell"]),
            Paragraph(str(c.get("count", 0)), styles["Cell"]),
            Paragraph(f'{c.get("rate", 0)}%', styles["CellBold"]),
        ])
    t = Table(conv_rows, colWidths=[60 * mm, 30 * mm, 30 * mm])
    t.setStyle(_table_style())
    story.append(t)

    if stage_counts:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("Stage Distribution", styles["Section"]))
        rows = [[Paragraph(f"<b>{h}</b>", styles["CellBold"]) for h in ["Stage", "Count"]]]
        for stage, count in sorted(stage_counts.items(), key=lambda x: -x[1]):
            rows.append([Paragraph(STAGE_LABELS.get(stage, stage), styles["Cell"]), Paragraph(str(count), styles["CellBold"])])
        t = Table(rows, colWidths=[50 * mm, 40 * mm])
        t.setStyle(_table_style())
        story.append(t)

    # ═══ 3. PERFORMANCE ═══
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("3. Performance", styles["Title2"]))
    story.append(Spacer(1, 2 * mm))

    recruiters_data = performance.get("recruiter", {}).get("recruiters", [])
    mandates_data = performance.get("mandate", {}).get("mandates", [])

    if recruiters_data:
        story.append(Paragraph("Recruiter Performance", styles["Section"]))
        rows = [[Paragraph(f"<b>{h}</b>", styles["CellBold"]) for h in ["Recruiter", "Total", "Submitted", "Offered", "Joined", "Revenue", "Conv%"]]]
        for r in recruiters_data[:15]:
            rows.append([
                Paragraph(r.get("recruiter_name", "—"), styles["Cell"]),
                Paragraph(str(r.get("total_candidates", 0)), styles["Cell"]),
                Paragraph(str(r.get("submitted", 0)), styles["Cell"]),
                Paragraph(str(r.get("offered", 0)), styles["Cell"]),
                Paragraph(str(r.get("joined", 0)), styles["CellBold"]),
                Paragraph(_fmt_currency(r.get("total_revenue", 0)), styles["Cell"]),
                Paragraph(f'{r.get("conversion_rate", 0)}%', styles["Cell"]),
            ])
        t = Table(rows, colWidths=[35 * mm, 18 * mm, 22 * mm, 20 * mm, 18 * mm, 25 * mm, 18 * mm])
        t.setStyle(_table_style())
        story.append(t)
    else:
        story.append(Paragraph("No recruiter performance data available.", styles["CellGrey"]))

    if mandates_data:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("Mandate Performance", styles["Section"]))
        rows = [[Paragraph(f"<b>{h}</b>", styles["CellBold"]) for h in ["Mandate", "Company", "Total", "Submitted", "Joined", "Revenue", "Sub%"]]]
        for m in mandates_data[:20]:
            rows.append([
                Paragraph(m.get("mandate_name", "—")[:30], styles["Cell"]),
                Paragraph(m.get("company", "—")[:20], styles["CellGrey"]),
                Paragraph(str(m.get("total_candidates", 0)), styles["Cell"]),
                Paragraph(str(m.get("submitted", 0)), styles["Cell"]),
                Paragraph(str(m.get("joined", 0)), styles["CellBold"]),
                Paragraph(_fmt_currency(m.get("total_revenue", 0)), styles["Cell"]),
                Paragraph(f'{m.get("submission_rate", 0)}%', styles["Cell"]),
            ])
        t = Table(rows, colWidths=[35 * mm, 28 * mm, 18 * mm, 22 * mm, 18 * mm, 22 * mm, 18 * mm])
        t.setStyle(_table_style())
        story.append(t)

    # ═══ 4. OVERVIEW ═══
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("4. Overview (Capture Analytics)", styles["Title2"]))
    story.append(Spacer(1, 2 * mm))

    story.append(Paragraph("Key Metrics", styles["Section"]))
    story.append(_kpi_table(overview.get("kpis", {}), styles))

    story.append(Paragraph("Source Effectiveness", styles["Section"]))
    story.append(_source_table(overview.get("source_distribution", []), styles))

    story.append(Paragraph("Recruiter Captures (Top 15)", styles["Section"]))
    story.append(_recruiter_table(overview.get("recruiter_performance", []), styles))

    story.append(Paragraph("Funnel Velocity (Avg Days)", styles["Section"]))
    story.append(_funnel_table(overview.get("funnel_velocity", {}), styles))

    story.append(Paragraph("Application Stages", styles["Section"]))
    story.append(_stage_table(overview.get("stage_distribution", {}), styles))

    # Footer
    story.append(Spacer(1, 10 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0")))
    story.append(Paragraph("Confidential — VHC Talent OS", styles["CellGrey"]))

    doc.build(story)
    buf.seek(0)
    return buf

