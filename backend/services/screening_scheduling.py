"""
screening_scheduling.py — interview slots, booking, reminders
=============================================================

Collections:
  interview_slots {id, mandate_id, start(UTC dt), duration_min, capacity,
                   booked_count, mode: video|phone|office, details, created_by}
  interviews      {id, candidate_id, candidate_name, mandate_id, slot_id,
                   session_id, start, mode, details, status:
                   booked|reminded_24h|reminded_2h|rescheduling|cancelled|
                   completed|no_show, created_at}

Booking is capacity-guarded with an atomic filtered $inc:
  update_one({id, booked_count < capacity}, {$inc: {booked_count: 1}})
so two candidates can't take the last seat.

WhatsApp reminders at T-24h and T-2h are the no-show lever; both invite
"reply RESCHEDULE" which cancels the booking and re-offers slots.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from models.neural_schema import utcnow

IST = timezone(timedelta(hours=5, minutes=30))

OFFER_COUNT = 3

_ORDINALS = {"1": 0, "2": 1, "3": 2, "one": 0, "two": 1, "three": 2,
             "first": 0, "second": 1, "third": 2,
             "pehla": 0, "pehli": 0, "doosra": 1, "dusra": 1, "teesra": 2, "tisra": 2}
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_NONE_WORDS = re.compile(r"\b(none|nahi|no|koi nahi|not (possible|suitable)|different|aur (slot|time)|other)\b", re.I)


def fmt_slot(slot: Dict[str, Any], idx: int) -> str:
    st = slot["start"]
    if st.tzinfo is None:
        st = st.replace(tzinfo=timezone.utc)
    ist = st.astimezone(IST)
    mode = {"video": "Video call", "phone": "Phone call", "office": "In person"}.get(slot.get("mode"), "Interview")
    return f"{idx + 1}. {ist:%a %d %b, %I:%M %p} IST — {mode}"


def offer_text(slots: List[Dict[str, Any]], language: str) -> str:
    lines = [fmt_slot(s, i) for i, s in enumerate(slots)]
    if language in ("hi", "hinglish"):
        head = "Badhai ho! 🎉 Interview ke liye yeh slots available hain:"
        tail = "Number reply karein (1/2/3), ya 'none' likhein agar koi suit nahi karta."
    else:
        head = "Great news! 🎉 These interview slots are available:"
        tail = "Reply with the number (1/2/3), or 'none' if these don't suit you."
    return head + "\n" + "\n".join(lines) + "\n" + tail


def parse_slot_choice(text: str, slots: List[Dict[str, Any]]) -> Optional[Any]:
    """Return slot index, 'none', or None (unparseable)."""
    t = text.lower().strip()
    if _NONE_WORDS.search(t):
        return "none"
    m = re.search(r"\b([123])\b", t)
    if m:
        i = int(m.group(1)) - 1
        return i if i < len(slots) else None
    for word, i in _ORDINALS.items():
        if re.search(rf"\b{word}\b", t) and i < len(slots):
            return i
    for i, s in enumerate(slots):
        st = s["start"] if s["start"].tzinfo else s["start"].replace(tzinfo=timezone.utc)
        if _WEEKDAYS[st.astimezone(IST).weekday()] in t:
            return i
    return None


async def open_slots(db, mandate_id: str, limit: int = OFFER_COUNT) -> List[Dict[str, Any]]:
    now = utcnow() + timedelta(hours=3)  # never offer slots <3h away
    slots = await db.interview_slots.find({"mandate_id": mandate_id}).sort("start", 1).to_list(length=50)
    out = []
    for s in slots:
        st = s["start"] if s["start"].tzinfo else s["start"].replace(tzinfo=timezone.utc)
        if st >= now and s.get("booked_count", 0) < s.get("capacity", 1):
            out.append(s)
        if len(out) >= limit:
            break
    return out


async def book(db, session: Dict[str, Any], slot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Atomic capacity-guarded booking. Returns interview doc or None if
    the seat vanished (caller re-offers)."""
    cap = slot.get("capacity", 1)
    res = await db.interview_slots.update_one(
        {"id": slot["id"], "booked_count": {"$lt": cap}},
        {"$inc": {"booked_count": 1}, "$set": {"updated_at": utcnow()}},
    )
    # Only the caller whose filter matched gets modified_count == 1 —
    # this is the atomic seat claim (capacity + race in one guard).
    if not res or not getattr(res, "modified_count", 0):
        return None
    interview = {
        "id": str(uuid.uuid4()),
        "candidate_id": session["candidate_id"],
        "candidate_name": session.get("candidate_name"),
        "mandate_id": session["mandate_id"],
        "mandate_title": session.get("mandate_title"),
        "slot_id": slot["id"], "session_id": session["id"],
        "start": slot["start"], "mode": slot.get("mode", "phone"),
        "details": slot.get("details"),
        "phone_msisdn": session["phone_msisdn"],
        "status": "booked", "created_at": utcnow(), "updated_at": utcnow(),
    }
    await db.interviews.insert_one(dict(interview))
    return interview


def confirmation_text(interview: Dict[str, Any], language: str) -> str:
    st = interview["start"] if interview["start"].tzinfo else interview["start"].replace(tzinfo=timezone.utc)
    ist = st.astimezone(IST)
    when = f"{ist:%A %d %B, %I:%M %p} IST"
    details = f"\n{interview['details']}" if interview.get("details") else ""
    if language in ("hi", "hinglish"):
        return (f"Interview book ho gaya ✅\n📅 {when}{details}\n"
                "Reminder aa jayega. Change karna ho toh RESCHEDULE likhein.")
    return (f"Your interview is booked ✅\n📅 {when}{details}\n"
            "I'll remind you before it. Reply RESCHEDULE anytime to change.")


async def cancel_booking(db, interview: Dict[str, Any], reason: str) -> None:
    await db.interviews.update_one(
        {"id": interview["id"]},
        {"$set": {"status": reason, "updated_at": utcnow()}})
    await db.interview_slots.update_one(
        {"id": interview["slot_id"]}, {"$inc": {"booked_count": -1}})


async def due_reminders(db, now: datetime) -> List[Dict[str, Any]]:
    """Interviews whose T-24h or T-2h reminder window is open right now.
    Windows are 35 min wide so the 30-min sweep can't miss them."""
    out = []
    upcoming = await db.interviews.find(
        {"status": {"$in": ["booked", "reminded_24h"]}}).to_list(length=500)
    for iv in upcoming:
        st = iv["start"] if iv["start"].tzinfo else iv["start"].replace(tzinfo=timezone.utc)
        d24 = st - timedelta(hours=24)
        d2 = st - timedelta(hours=2)
        if iv["status"] == "booked" and d24 <= now < d24 + timedelta(minutes=35):
            out.append({"interview": iv, "kind": "24h"})
        elif iv["status"] in ("booked", "reminded_24h") and d2 <= now < d2 + timedelta(minutes=35):
            out.append({"interview": iv, "kind": "2h"})
    return out


def reminder_text(interview: Dict[str, Any], kind: str, language: str) -> str:
    st = interview["start"] if interview["start"].tzinfo else interview["start"].replace(tzinfo=timezone.utc)
    ist = st.astimezone(IST)
    hi = language in ("hi", "hinglish")
    when = f"{ist:%a %d %b, %I:%M %p} IST"
    if kind == "24h":
        return ((f"Reminder: kal aapka interview hai — {when} ({interview.get('mandate_title','')}). "
                 "All set? Change ke liye RESCHEDULE likhein.") if hi else
                (f"Reminder: your interview is tomorrow — {when} ({interview.get('mandate_title','')}). "
                 "All set? Reply RESCHEDULE to change."))
    return ((f"Aaj {ist:%I:%M %p} IST par interview hai — best of luck! 🤞 "
             "Problem ho toh RESCHEDULE likhein.") if hi else
            (f"Your interview is today at {ist:%I:%M %p} IST — best of luck! 🤞 "
             "Reply RESCHEDULE if there's a problem."))
