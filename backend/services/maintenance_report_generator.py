"""
VHC Talent OS — Maintenance Report Generator
Generates a combined enterprise PDF with 6 sections.
Scoped to last 7 days OR 1000 records max.
"""
import io
import logging
from datetime import datetime, timezone, timedelta
from xml.sax.saxutils import escape as xml_escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak,
)
from config import db
from services.health_monitor import compute_health_score

logger = logging.getLogger(__name__)
W, H = A4
LIMIT = 1000
DAYS = 7

# ─── Color palette ───
C_PRIMARY = colors.HexColor("#0f172a")
C_ACCENT = colors.HexColor("#059669")
C_RED = colors.HexColor("#dc2626")
C_AMBER = colors.HexColor("#d97706")
C_GRAY = colors.HexColor("#64748b")
C_LIGHT = colors.HexColor("#f8fafc")
C_WHITE = colors.white


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("SectionTitle", parent=ss["Heading2"], fontSize=13, textColor=C_PRIMARY, spaceAfter=6, spaceBefore=14))
    ss.add(ParagraphStyle("SubTitle", parent=ss["Normal"], fontSize=9, textColor=C_GRAY))
    ss.add(ParagraphStyle("CellText", parent=ss["Normal"], fontSize=7.5, leading=10))
    ss.add(ParagraphStyle("SmallGray", parent=ss["Normal"], fontSize=7, textColor=C_GRAY))
    return ss


def _header_table(styles, now_str, score):
    score_color = C_ACCENT if score >= 70 else C_AMBER if score >= 40 else C_RED
    data = [
        [Paragraph("<b>Ventures HRD — Talent OS</b>", styles["Title"]),
         Paragraph(f"<b>Health Score: {score}/100</b>", ParagraphStyle("Score", parent=styles["Title"], textColor=score_color, alignment=2))],
        [Paragraph("System Maintenance Report", styles["Heading3"]),
         Paragraph(f"Generated: {now_str}", ParagraphStyle("Right", parent=styles["SubTitle"], alignment=2))],
    ]
    t = Table(data, colWidths=[W * 0.5, W * 0.5 - 40 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return t


def _summary_table(styles, stats):
    rows = [
        ["Metric", "Value"],
        ["Total Incidents", str(stats.get("total_incidents", 0))],
        ["Critical Errors", str(stats.get("critical", 0))],
        ["Warnings", str(stats.get("warnings", 0))],
        ["Auto-Fixes Executed", str(stats.get("fixes", 0))],
        ["Avg Recovery Time", f"{stats.get('avg_recovery_ms', 0)} ms"],
        ["Health Score", f"{stats.get('score', 0)} / 100"],
    ]
    t = Table(rows, colWidths=[120 * mm, 50 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY), ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.3, C_GRAY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_LIGHT]),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))
    return t


def _make_log_table(styles, headers, rows, col_widths=None):
    data = [headers] + rows[:100]  # cap displayed rows
    cw = col_widths or [W / len(headers) - 10 * mm] * len(headers)
    t = Table(data, colWidths=cw, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY), ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTSIZE", (0, 0), (-1, -1), 7), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_LIGHT]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


async def generate_maintenance_report() -> bytes:
    """Generate the full maintenance PDF report. Returns bytes."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=DAYS)).isoformat()
    now_str = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    styles = _styles()

    # ─── Fetch data ───
    health_checks = await db.system_health_checks.find(
        {"timestamp": {"$gte": cutoff}}, {"_id": 0}
    ).sort("timestamp", -1).limit(LIMIT).to_list(LIMIT)

    system_errors = await db.system_errors.find(
        {"created_at": {"$gte": cutoff}}, {"_id": 0}
    ).sort("created_at", -1).limit(LIMIT).to_list(LIMIT)

    fixes = await db.maintenance_fixes.find(
        {"start_time": {"$gte": cutoff}}, {"_id": 0}
    ).sort("start_time", -1).limit(LIMIT).to_list(LIMIT)

    rel_events = await db.reliability_events.find(
        {"timestamp": {"$gte": cutoff}}, {"_id": 0}
    ).sort("timestamp", -1).limit(LIMIT).to_list(LIMIT)

    # ─── Compute stats ───
    latest_checks = {}
    for hc in health_checks:
        sn = hc["service_name"]
        if sn not in latest_checks:
            latest_checks[sn] = hc
    score = compute_health_score(list(latest_checks.values())) if latest_checks else 100

    critical_checks = [h for h in health_checks if h["status"] == "critical"]
    warning_checks = [h for h in health_checks if h["status"] == "warning"]
    avg_recovery = 0
    if fixes:
        durations = [f.get("recovery_duration_ms", 0) for f in fixes if f.get("recovery_duration_ms")]
        avg_recovery = round(sum(durations) / max(len(durations), 1))

    summary_stats = {
        "total_incidents": len(critical_checks) + len(warning_checks),
        "critical": len(critical_checks),
        "warnings": len(warning_checks),
        "fixes": len(fixes),
        "avg_recovery_ms": avg_recovery,
        "score": score,
    }

    # ─── Build PDF ───
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=15 * mm, leftMargin=15 * mm, rightMargin=15 * mm)
    story = []

    # SECTION 1 — Header
    story.append(_header_table(styles, now_str, score))
    story.append(HRFlowable(width="100%", thickness=1, color=C_ACCENT, spaceBefore=8, spaceAfter=8))

    # SECTION 2 — Summary
    story.append(Paragraph("Executive Summary", styles["SectionTitle"]))
    story.append(_summary_table(styles, summary_stats))
    story.append(Spacer(1, 6 * mm))

    # SECTION 3 — Error Logs
    story.append(Paragraph(f"Error Logs ({len(system_errors)} records, last {DAYS} days)", styles["SectionTitle"]))
    if system_errors:
        err_rows = []
        for e in system_errors[:100]:
            err_rows.append([
                Paragraph(str(e.get("created_at", ""))[:19], styles["CellText"]),
                Paragraph(str(e.get("source", "")), styles["CellText"]),
                Paragraph(str(e.get("error_type", "")), styles["CellText"]),
                Paragraph(str(e.get("message", ""))[:120], styles["CellText"]),
            ])
        story.append(_make_log_table(styles,
            ["Timestamp", "Source", "Type", "Message"],
            err_rows, [35 * mm, 20 * mm, 25 * mm, 90 * mm]))
    else:
        story.append(Paragraph("No errors in the reporting period.", styles["SmallGray"]))
    story.append(Spacer(1, 4 * mm))

    # SECTION 4 — Fix Done Logs
    story.append(Paragraph(f"Auto-Fix Logs ({len(fixes)} records)", styles["SectionTitle"]))
    if fixes:
        fix_rows = []
        for f in fixes[:100]:
            fix_rows.append([
                Paragraph(str(f.get("start_time", ""))[:19], styles["CellText"]),
                Paragraph(str(f.get("service_name", "")), styles["CellText"]),
                Paragraph(str(f.get("issue_detected", ""))[:80], styles["CellText"]),
                Paragraph(str(f.get("fix_action", "")), styles["CellText"]),
                Paragraph(f"{f.get('recovery_duration_ms', 0)}ms", styles["CellText"]),
                Paragraph(str(f.get("result", ""))[:60], styles["CellText"]),
            ])
        story.append(_make_log_table(styles,
            ["Time", "Service", "Issue", "Action", "Duration", "Result"],
            fix_rows, [28 * mm, 22 * mm, 35 * mm, 25 * mm, 18 * mm, 42 * mm]))
    else:
        story.append(Paragraph("No auto-fix actions in the reporting period.", styles["SmallGray"]))
    story.append(Spacer(1, 4 * mm))

    # SECTION 5 — AI Failure Analytics
    story.append(Paragraph("AI Failure Analytics", styles["SectionTitle"]))
    ai_types = {
        "automation_pipeline": "Silent Automation Failures",
        "queue_system": "Queue Overload Incidents",
        "ai_services": "AI Latency Spikes",
        "system_resources": "Memory Recovery Actions",
        "data_sync": "Sync Mismatch Recoveries",
    }
    ai_rows = []
    for svc, label in ai_types.items():
        count = len([h for h in health_checks if h["service_name"] == svc and h["status"] in ("warning", "critical")])
        fix_count = len([f for f in fixes if f.get("service_name") == svc])
        ai_rows.append([
            Paragraph(label, styles["CellText"]),
            Paragraph(str(count), styles["CellText"]),
            Paragraph(str(fix_count), styles["CellText"]),
        ])
    story.append(_make_log_table(styles, ["Failure Type", "Incidents", "Fixes Applied"], ai_rows, [80 * mm, 40 * mm, 50 * mm]))
    story.append(Spacer(1, 4 * mm))

    # SECTION 6 — Reliability Layer Events
    story.append(Paragraph(f"Reliability Layer Events ({len(rel_events)} records)", styles["SectionTitle"]))
    if rel_events:
        # Summary counts
        from collections import Counter
        event_counts = Counter(e.get("event_type", "unknown") for e in rel_events)
        rel_summary_rows = [[Paragraph(k, styles["CellText"]), Paragraph(str(v), styles["CellText"])] for k, v in event_counts.most_common(15)]
        story.append(_make_log_table(styles, ["Event Type", "Count"], rel_summary_rows, [100 * mm, 70 * mm]))
        story.append(Spacer(1, 3 * mm))
        # Recent events detail
        rel_rows = []
        for ev in rel_events[:50]:
            rel_rows.append([
                Paragraph(str(ev.get("timestamp", ""))[:19], styles["CellText"]),
                Paragraph(str(ev.get("event_type", "")), styles["CellText"]),
                Paragraph(str(ev.get("service", "")), styles["CellText"]),
                Paragraph(str(ev.get("detail", ""))[:100], styles["CellText"]),
            ])
        story.append(_make_log_table(styles, ["Time", "Event", "Service", "Detail"], rel_rows, [30 * mm, 35 * mm, 25 * mm, 80 * mm]))
    else:
        story.append(Paragraph("No reliability events in the reporting period.", styles["SmallGray"]))

    # Footer
    story.append(Spacer(1, 10 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_GRAY))
    story.append(Paragraph(f"Ventures HRD — Confidential | Report scope: Last {DAYS} days, max {LIMIT} records per section", styles["SmallGray"]))

    doc.build(story)
    buf.seek(0)
    return buf.read()
