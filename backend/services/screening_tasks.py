"""
screening_tasks.py — Asha's shift (v2): worklist, nudges, reminders,
touchpoints, refresh batch, email fallback, evening report
====================================================================

Scheduler registration (services/lifecycle.py, cron hours in UTC):
  register_agent_jobs(scheduler, db)
    04:00 UTC (09:30 IST)  run_worklist       queued/callback starts
    every 30 min           run_sweeps         nudges + interview
                                              reminders + joining
                                              touchpoints + email
                                              fallback (each internally
                                              gated by window/env)
    03:30 UTC (09:00 IST)  run_refresh_batch  stale-profile journeys
    13:45 UTC (19:15 IST)  run_evening_report

Manual triggers mirror every job under /api/agent/* for cron-less
operation and dry-run testing.
"""
from __future__ import annotations

import functools
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from models.neural_schema import utcnow
from services import screening_engine
from services import screening_joining as joining
from services import screening_scheduling as sched
from services.screening_whatsapp import send_text

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def _enabled() -> bool:
    return os.environ.get("AGENT_ENABLED", "0") == "1"


def _caps() -> Dict[str, int]:
    return {
        "active": int(os.environ.get("AGENT_MAX_ACTIVE_CONVERSATIONS", "25")),
        "daily": int(os.environ.get("AGENT_DAILY_CONTACT_CAP", "100")),
    }


def _in_window(now_ist: datetime = None) -> bool:
    now_ist = now_ist or datetime.now(IST)
    raw = os.environ.get("AGENT_HOURS", "10-19")
    try:
        lo, hi = [int(x) for x in raw.split("-")]
    except Exception:
        lo, hi = 10, 19
    return lo <= now_ist.hour < hi


async def _today_contact_count(db) -> int:
    day_start = datetime.now(IST).replace(hour=0, minute=0, second=0,
                                          microsecond=0).astimezone(timezone.utc)
    return await db.screening_sessions.count_documents({"created_at": {"$gte": day_start}})


async def _active_count(db) -> int:
    return await db.screening_sessions.count_documents(
        {"state": {"$in": ["consent", "active"]}})


async def _budget(db) -> int:
    caps = _caps()
    return min(caps["active"] - await _active_count(db),
               caps["daily"] - await _today_contact_count(db))


# ═════════════════════════ worklist dispatch ═════════════════════════════

async def run_worklist(db) -> Dict[str, Any]:
    if not _enabled():
        return {"skipped": "AGENT_ENABLED=0"}
    if not _in_window():
        return {"skipped": "outside_contact_window"}
    budget = await _budget(db)
    if budget <= 0:
        return {"started": 0, "skipped": "caps_reached"}

    started, errors = 0, []
    tasks = await (db.screening_tasks.find(
        {"state": "queued",
         "$or": [{"next_attempt_at": None},
                 {"next_attempt_at": {"$lte": utcnow()}}]})
        .sort("priority", -1).limit(budget).to_list(length=budget))

    for t in tasks:
        try:
            sess = await db.screening_sessions.find_one(
                {"candidate_id": t["candidate_id"], "mandate_id": t.get("mandate_id"),
                 "state": "callback"})
            if sess:
                await screening_engine.resume_session(db, sess)
            else:
                await screening_engine.start_session(
                    db, t["candidate_id"], t.get("mandate_id"),
                    t.get("created_by", "agent"),
                    flow=t.get("flow", "screening"),
                    docs_requested=t.get("docs_requested"))
            started += 1
        except ValueError as e:
            await db.screening_tasks.update_one(
                {"id": t["id"]},
                {"$set": {"state": "error", "last_error": str(e), "updated_at": utcnow()}})
            errors.append({"task": t["id"], "error": str(e)})
    logger.info("[Asha] worklist: started=%s errors=%s", started, len(errors))
    return {"started": started, "errors": errors}


# ═══════════════════════════════ nudges ══════════════════════════════════

NUDGE_1 = {
    "en": "Just checking in 🙂 — whenever you have a minute, we can continue. Reply HUMAN anytime for our recruiter.",
    "hi": "Bas yaad dila rahi thi 🙂 — jab time mile, hum continue kar sakte hain. HUMAN likhein recruiter ke liye.",
}
NUDGE_2 = {
    "en": "Last reminder from my side — reply anytime to continue, or HUMAN to talk to our recruiter. Thank you!",
    "hi": "Meri taraf se aakhri reminder — jab chahein reply karein, ya HUMAN likhein recruiter se baat ke liye. Dhanyawaad!",
}


async def run_nudges(db) -> Dict[str, Any]:
    if not _enabled() or not _in_window():
        return {"skipped": True}
    now = utcnow()
    nudged, stalled = 0, 0
    sessions = await (db.screening_sessions.find(
        {"state": {"$in": ["consent", "active"]},
         "last_out_at": {"$lte": now - timedelta(hours=4)}})
        .to_list(length=500))
    for s in sessions:
        n = s.get("nudge_count", 0)
        lang = "hi" if s.get("language") in ("hi", "hinglish") else "en"
        if n == 0:
            await send_text(s["phone_msisdn"], NUDGE_1[lang])
            await db.screening_sessions.update_one(
                {"id": s["id"]}, {"$set": {"nudge_count": 1, "last_out_at": now, "updated_at": now}})
            nudged += 1
        elif n == 1 and s["last_out_at"] <= now - timedelta(hours=16):
            await send_text(s["phone_msisdn"], NUDGE_2[lang])
            await db.screening_sessions.update_one(
                {"id": s["id"]}, {"$set": {"nudge_count": 2, "last_out_at": now, "updated_at": now}})
            nudged += 1
        elif n >= 2 and s["last_out_at"] <= now - timedelta(hours=20):
            await db.screening_sessions.update_one(
                {"id": s["id"]}, {"$set": {"state": "stalled", "updated_at": now}})
            await db.screening_tasks.update_one(
                {"session_id": s["id"]}, {"$set": {"state": "stalled", "updated_at": now}})
            stalled += 1
    return {"nudged": nudged, "stalled": stalled}


# ═══════════════ interview reminders + joining touchpoints ═══════════════

async def run_interview_reminders(db) -> Dict[str, Any]:
    if not _enabled():
        return {"skipped": True}
    now = utcnow()
    sent = 0
    for due in await sched.due_reminders(db, now):
        iv, kind = due["interview"], due["kind"]
        lang = iv.get("language", "hinglish")
        await send_text(iv["phone_msisdn"], sched.reminder_text(iv, kind, lang))
        await db.interviews.update_one(
            {"id": iv["id"]},
            {"$set": {"status": f"reminded_{kind}", "updated_at": now}})
        sent += 1
    return {"reminders_sent": sent}


async def run_joining_touchpoints(db) -> Dict[str, Any]:
    if not _enabled() or os.environ.get("AGENT_JOINING", "1") != "1":
        return {"skipped": True}
    if not _in_window():
        return {"skipped": "outside_window"}
    now = utcnow()
    sent = 0
    placements = await (db.placements.find(
        {"status": {"$in": ["accepted", "confirmed", "ghost_risk"]}})
        .to_list(length=500))
    for p in placements:
        for kind in joining.due_touchpoints(p, now):
            lang = "hinglish"
            await send_text(p["phone_msisdn"], joining.touchpoint_text(kind, p, lang))
            await db.placements.update_one(
                {"id": p["id"]},
                {"$push": {"touchpoints_sent": kind}, "$set": {"updated_at": now}})
            sent += 1
    return {"touchpoints_sent": sent}


# ═══════════════════ email fallback for stalled sessions ═════════════════

async def run_email_fallback(db) -> Dict[str, Any]:
    from services import screening_email
    if not _enabled() or not screening_email.enabled():
        return {"skipped": True}
    sent = 0
    stalled = await (db.screening_sessions.find(
        {"state": "stalled", "flow": "screening", "email_nudged": {"$ne": True}})
        .to_list(length=100))
    for s in stalled:
        cand = await db.candidate_bank.find_one({"id": s["candidate_id"]}) or {}
        if await screening_email.send_stall_nudge(cand, s):
            await db.screening_sessions.update_one(
                {"id": s["id"]}, {"$set": {"email_nudged": True, "updated_at": utcnow()}})
            sent += 1
    return {"emails_sent": sent}


async def run_sweeps(db) -> Dict[str, Any]:
    """The 30-minute heartbeat: everything time-windowed in one pass."""
    return {
        "nudges": await run_nudges(db),
        "interview_reminders": await run_interview_reminders(db),
        "joining": await run_joining_touchpoints(db),
        "email_fallback": await run_email_fallback(db),
    }


# ═══════════════════════ stale-profile refresh batch ═════════════════════

async def run_refresh_batch(db) -> Dict[str, Any]:
    cap = int(os.environ.get("AGENT_REFRESH_DAILY_CAP", "0"))
    if not _enabled() or cap <= 0 or not _in_window():
        return {"skipped": True}
    budget = min(cap, await _budget(db))
    if budget <= 0:
        return {"started": 0, "skipped": "no_budget"}
    months = int(os.environ.get("AGENT_REFRESH_MONTHS", "12"))
    cutoff = utcnow() - timedelta(days=30 * months)
    stale = await (db.candidate_bank.find(
        {"updated_at": {"$lte": cutoff}, "phone": {"$ne": None}})
        .sort("updated_at", 1).limit(budget * 3).to_list(length=budget * 3))
    started = 0
    for cand in stale:
        if started >= budget:
            break
        try:
            await screening_engine.start_session(
                db, cand["id"], None, "refresh_batch", flow="refresh")
            started += 1
        except ValueError:
            continue
    logger.info("[Asha] refresh batch: started=%s", started)
    return {"started": started}


# ═══════════════════════════ evening report ══════════════════════════════

async def run_evening_report(db) -> Dict[str, Any]:
    day_start = datetime.now(IST).replace(hour=0, minute=0, second=0,
                                          microsecond=0).astimezone(timezone.utc)
    sessions = await db.screening_sessions.find(
        {"updated_at": {"$gte": day_start}}).to_list(length=1000)

    by_mandate: Dict[str, Dict[str, int]] = {}
    totals = {"contacted": 0, "responded": 0, "completed": 0, "qualified": 0,
              "callbacks": 0, "opted_out": 0, "human": 0, "refreshed": 0,
              "docs_collected": 0}
    top: List[Dict[str, Any]] = []
    for s in sessions:
        m = by_mandate.setdefault(s.get("mandate_title") or s.get("mandate_id") or s.get("flow"),
                                  {"contacted": 0, "completed": 0, "qualified": 0})
        if s.get("created_at", day_start) >= day_start:
            totals["contacted"] += 1
            m["contacted"] += 1
        if any(t.get("dir") == "in" for t in (s.get("transcript") or [])):
            totals["responded"] += 1
        if s.get("state") == "completed":
            totals["completed"] += 1
            m["completed"] += 1
            if s.get("verdict") == "QUALIFIED":
                totals["qualified"] += 1
                m["qualified"] += 1
                top.append(s)
            elif s.get("verdict") == "REFRESHED":
                totals["refreshed"] += 1
            elif s.get("verdict") == "DOCS_COLLECTED":
                totals["docs_collected"] += 1
        totals["callbacks"] += 1 if s.get("state") == "callback" else 0
        totals["opted_out"] += 1 if s.get("state") == "opted_out" else 0
        totals["human"] += 1 if s.get("state") in ("human_handoff", "human_live") else 0

    booked_today = await db.interviews.count_documents({"created_at": {"$gte": day_start}})
    tomorrow_end = utcnow() + timedelta(hours=36)
    upcoming = await db.interviews.count_documents(
        {"status": {"$in": ["booked", "reminded_24h", "reminded_2h"]},
         "start": {"$lte": tomorrow_end}})
    ghost = await (db.placements.find({"status": "ghost_risk"}).to_list(length=20))

    top.sort(key=lambda x: x.get("score") or 0, reverse=True)
    lines = [f"🤖 *Asha — Daily Report* ({datetime.now(IST):%d %b %Y})",
             f"Contacted {totals['contacted']} · Responded {totals['responded']} · "
             f"Completed {totals['completed']} · ✅ Qualified {totals['qualified']}",
             f"📅 Interviews booked today: {booked_today} · upcoming ≤36h: {upcoming}",
             f"Callbacks {totals['callbacks']} · Human {totals['human']} · "
             f"Opt-outs {totals['opted_out']} · 🔄 Refreshed {totals['refreshed']} · "
             f"📎 Docs {totals['docs_collected']}", ""]
    for title, m in by_mandate.items():
        lines.append(f"• {title}: {m['qualified']}/{m['completed']} qualified "
                     f"(contacted {m['contacted']})")
    if ghost:
        lines.append("")
        lines.append("⚠️ *Joining ghost-risk (call today):*")
        for p in ghost[:5]:
            lines.append(f"→ {p.get('candidate_name')} — {p.get('mandate_title')} "
                         f"(joining {p['joining_date']:%d %b})")
    if top:
        lines.append("")
        lines.append("*Top candidates:*")
        for s in top[:3]:
            v = s.get("verified") or {}
            lines.append(f"→ {s.get('candidate_name')} — {s.get('score')}% | "
                         f"{v.get('notice_days', '?')}d notice | exp {v.get('expected_lpa', '?')} LPA")
    report_text = "\n".join(lines)

    doc = {"date": datetime.now(IST).strftime("%Y-%m-%d"), "totals": totals,
           "by_mandate": by_mandate, "interviews_booked": booked_today,
           "ghost_risks": [p["id"] for p in ghost],
           "text": report_text, "created_at": utcnow()}
    await db.agent_reports.insert_one(dict(doc))
    admins = [n.strip() for n in os.environ.get("WHATSAPP_ADMIN_NUMBERS", "").split(",") if n.strip()]
    for admin in admins:
        await send_text(admin, report_text)
    logger.info("[Asha] evening report: %s", totals)
    return doc


# ═══════════════════════ startup registration ════════════════════════════

async def ensure_agent_indexes(db) -> None:
    """Hot-path indexes + webhook dedupe store. Call once at startup."""
    await db.screening_sessions.create_index([("phone_normalized", 1), ("state", 1)])
    await db.screening_sessions.create_index([("mandate_id", 1), ("updated_at", -1)])
    await db.screening_sessions.create_index([("state", 1), ("last_out_at", 1)])
    await db.screening_sessions.create_index([("flow", 1), ("state", 1)])
    await db.screening_tasks.create_index([("state", 1), ("next_attempt_at", 1)])
    await db.screening_tasks.create_index("session_id")
    await db.edges.create_index([("src", 1), ("rel", 1)])
    await db.interview_slots.create_index([("mandate_id", 1), ("start", 1)])
    await db.interviews.create_index([("phone_normalized", 1), ("status", 1)])
    await db.interviews.create_index([("status", 1), ("start", 1)])
    await db.placements.create_index([("phone_normalized", 1), ("status", 1)])
    await db.placements.create_index([("status", 1), ("joining_date", 1)])
    await db.agent_do_not_contact.create_index("phone_normalized", unique=True)
    # Meta redelivers webhooks — dedupe by wamid, auto-expire after 48h
    await db.wa_processed_messages.create_index("wamid", unique=True)
    await db.wa_processed_messages.create_index("created_at", expireAfterSeconds=172800)


def register_agent_jobs(scheduler, db) -> None:
    """Add to services/lifecycle.py next to the existing add_job calls.
    functools.partial keeps these visible to AsyncIOScheduler as
    coroutine functions — a plain lambda would return an un-awaited
    coroutine and the jobs would silently never run."""
    scheduler.add_job(functools.partial(run_worklist, db), "cron", hour=4, minute=0, id="asha_worklist")
    scheduler.add_job(functools.partial(run_sweeps, db), "cron", minute="*/30", id="asha_sweeps")
    scheduler.add_job(functools.partial(run_refresh_batch, db), "cron", hour=3, minute=30, id="asha_refresh")
    scheduler.add_job(functools.partial(run_evening_report, db), "cron", hour=13, minute=45, id="asha_report")
