"""
screening_joining.py — the joining shepherd
===========================================

Protects revenue between offer and Day 1. Recruiter creates a placement
(candidate + mandate + joining_date); Asha runs warm touchpoints at
T-7d, T-3d, T-1d and the D-day morning, records responses, and flags
ghost-risk signals into the evening report the moment they appear.

placements {id, candidate_id, candidate_name, mandate_id, mandate_title,
            phone_normalized, phone_msisdn, joining_date (UTC dt at
            03:30 = 9 AM IST), status: offered|accepted|confirmed|
            joined|ghost_risk|dropped, touchpoints_sent: [kind],
            checkins: [{kind, reply, sentiment, at}], created_by}
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from models.neural_schema import utcnow

IST = timezone(timedelta(hours=5, minutes=30))

TOUCHPOINTS = [("t7", 7), ("t3", 3), ("t1", 1), ("d0", 0)]

_NEGATIVE = re.compile(
    r"\b(not join|nahi (aa|join)|cancel|other offer|dusri (company|offer)|"
    r"change of plan|mana kar|drop|nahi ho (payega|paayega)|reconsider)\b", re.I)
_POSITIVE = re.compile(r"\b(yes|haan|ji|sure|confirm|pakka|bilkul|aaunga|aa raha|joining|ready)\b", re.I)


def touchpoint_text(kind: str, p: Dict[str, Any], language: str) -> str:
    hi = language in ("hi", "hinglish")
    title = p.get("mandate_title") or "your new role"
    jd = p["joining_date"] if p["joining_date"].tzinfo else p["joining_date"].replace(tzinfo=timezone.utc)
    date_s = f"{jd.astimezone(IST):%A %d %B}"
    name = (p.get("candidate_name") or "").split()[0] or ("ji" if hi else "")
    if kind == "t7":
        return ((f"Namaste {name}! Asha here (Ventures HRD AI assistant). {title} ki joining "
                 f"{date_s} ko hai — sab set hai? Documents/notice mein koi help chahiye toh batayein 🙂")
                if hi else
                (f"Hi {name}! Asha here (Ventures HRD AI assistant). Your joining for {title} is on "
                 f"{date_s} — all on track? Tell me if you need help with documents or notice 🙂"))
    if kind == "t3":
        return ((f"{name}, bas 3 din! {date_s} ki joining ke liye sab theek? (Haan/koi issue ho toh batayein)")
                if hi else
                (f"{name}, just 3 days to go! All set for joining on {date_s}? (Yes / tell me if anything's up)"))
    if kind == "t1":
        return ((f"Kal ka din hai {name}! 🎉 Joining time/location confirm hai? Kal subah milte hain — best of luck!")
                if hi else
                (f"Tomorrow's the day, {name}! 🎉 Time and location confirmed? Best of luck — see you on the other side!"))
    return ((f"Aaj pehla din hai {name} — all the best! 🌟 Pahunch jaayein toh ek 'joined' likh dena 🙂")
            if hi else
            (f"It's Day 1, {name} — all the best! 🌟 Drop me a 'joined' once you're in 🙂"))


async def create_placement(db, candidate_id: str, mandate_id: str,
                           joining_date: datetime, created_by: str) -> Dict[str, Any]:
    from models.neural_schema import normalize_phone
    cand = await db.candidate_bank.find_one({"id": candidate_id})
    if not cand:
        raise ValueError("candidate_not_found")
    job = await db.jobs.find_one({"id": mandate_id}) or {}
    phone = normalize_phone(cand.get("phone"))
    if not phone:
        raise ValueError("no_phone")
    p = {"id": str(uuid.uuid4()), "candidate_id": candidate_id,
         "candidate_name": cand.get("name"), "mandate_id": mandate_id,
         "mandate_title": job.get("title"), "phone_normalized": phone,
         "phone_msisdn": phone if len(phone) > 10 else f"91{phone}",
         "joining_date": joining_date, "status": "accepted",
         "touchpoints_sent": [], "checkins": [],
         "created_by": created_by, "created_at": utcnow(), "updated_at": utcnow()}
    await db.placements.insert_one(dict(p))
    await db.edges.insert_one({"src": f"cand:{candidate_id}", "src_type": "candidate",
                               "rel": "OFFERED", "dst": f"mandate:{mandate_id}",
                               "dst_type": "mandate", "weight": 1.0,
                               "evidence": f"placement:{p['id']}",
                               "created_at": utcnow(), "updated_at": utcnow()})
    return p


def due_touchpoints(p: Dict[str, Any], now: datetime) -> List[str]:
    """Touchpoints whose send moment (9:00 IST on the offset day) has
    arrived and which haven't been sent. Window = same IST day."""
    jd = p["joining_date"] if p["joining_date"].tzinfo else p["joining_date"].replace(tzinfo=timezone.utc)
    sent = set(p.get("touchpoints_sent") or [])
    due = []
    for kind, days_before in TOUCHPOINTS:
        if kind in sent:
            continue
        send_at = (jd.astimezone(IST) - timedelta(days=days_before)).replace(
            hour=9, minute=0, second=0, microsecond=0)
        if send_at <= now.astimezone(IST) < send_at + timedelta(hours=10):
            due.append(kind)
    return due


async def record_checkin(db, p: Dict[str, Any], text: str) -> str:
    """Classify a reply, update status, return sentiment."""
    if _NEGATIVE.search(text):
        sentiment = "negative"
        status = "ghost_risk"
    elif re.search(r"\bjoined\b|join kar (liya|li)|aa gaya|pahunch", text, re.I):
        sentiment, status = "joined", "joined"
    elif _POSITIVE.search(text):
        sentiment = "positive"
        status = "confirmed" if p["status"] in ("accepted", "confirmed") else p["status"]
    else:
        sentiment, status = "neutral", p["status"]
    await db.placements.update_one(
        {"id": p["id"]},
        {"$push": {"checkins": {"reply": text[:400], "sentiment": sentiment, "at": utcnow()}},
         "$set": {"status": status, "updated_at": utcnow()}})
    if status == "joined":
        await db.edges.insert_one({"src": f"cand:{p['candidate_id']}", "src_type": "candidate",
                                   "rel": "PLACED", "dst": f"mandate:{p['mandate_id']}",
                                   "dst_type": "mandate", "weight": 1.0,
                                   "evidence": f"placement:{p['id']}",
                                   "created_at": utcnow(), "updated_at": utcnow()})
    return sentiment


def checkin_ack(sentiment: str, language: str) -> str:
    hi = language in ("hi", "hinglish")
    if sentiment == "negative":
        return ("Samajh gayi — main abhi hamare recruiter ko batati hoon, woh aapko turant call karenge. 🙏"
                if hi else
                "Understood — I'm flagging this to our recruiter right away; they'll call you shortly. 🙏")
    if sentiment == "joined":
        return "Congratulations! 🎉 Aapka bahut bahut shubhkamnayein!" if hi else "Congratulations! 🎉 Wishing you a great start!"
    if sentiment == "positive":
        return "Perfect 👍" if not hi else "Bahut badhiya 👍"
    return ("Noted 🙂 koi bhi help chahiye toh batayein." if hi else "Noted 🙂 tell me if you need anything.")


async def handle_placement_inbound(db, phone_normalized: str, text: str) -> bool:
    """Fallback when no screening session is active: replies land against
    the candidate's live placement."""
    p = await db.placements.find_one(
        {"phone_normalized": phone_normalized,
         "status": {"$in": ["accepted", "confirmed", "ghost_risk"]}})
    if not p:
        return False
    sentiment = await record_checkin(db, p, text)
    from services.screening_whatsapp import send_text
    lang = "hinglish" if re.search(r"[\u0900-\u097F]|hai|nahi|haan", text, re.I) else "en"
    await send_text(p["phone_msisdn"], checkin_ack(sentiment, lang))
    return True
