"""
screening_engine.py — Asha's dialogue state machine (v2)
========================================================

v1 invariants preserved: the LLM only phrases and rescues extraction;
every decision is deterministic; sessions/verdicts/write-backs behave
identically (the v1 test suite runs unchanged).

v2 adds:
  • agent_do_not_contact registry keyed on phone_normalized — opt-out
    suppresses every duplicate record of the same human
  • flows: screening | refresh | docs (compile dispatch + carried
    answers so a candidate is never asked a verified question twice)
  • FAQ interrupts: mid-flow questions answered from a mandate
    whitelist, current question re-asked, block not consumed
  • media: documents/images stored to R2 in docs flow; voice notes
    transcribed (AGENT_STT=1) and fed through the same text path
  • human takeover: state "human_live" — Asha pauses, recruiter types
  • post-completion chains: interview slot offer on QUALIFIED,
    cross-mandate offer on NOT_QUALIFIED, referral tail
  • RESCHEDULE handling for booked interviews (even after completion)
  • consent-loop guard (repeated unclear turns → stalled)

Webhook entry point: route_inbound(db, phone_normalized, msg_dict) —
dispatches text/audio/document/image and the fallback chain
(sessions → interviews → placements).
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from models.neural_schema import (
    normalize_phone, parse_notice_to_days, parse_salary_to_lpa, utcnow,
)
from services import screening_flows as flows
from services import screening_llm
from services import screening_scheduling as sched
from services.screening_script import compile_script
from services.screening_whatsapp import send_intro, send_text

logger = logging.getLogger(__name__)

QUALIFY_THRESHOLD = int(os.environ.get("AGENT_QUALIFY_THRESHOLD", "55"))
BUDGET_STRETCH = 1.15

STOP_WORDS = {"stop", "band karo", "band kar", "बंद", "unsubscribe", "opt out", "mat bhejo"}
HUMAN_WORDS = {"human", "इंसान", "insan", "recruiter se", "recruiter baat", "talk to person", "call me"}
CALLBACK_WORDS = {"later", "baad me", "baad mein", "busy", "kal", "call back", "callback", "abhi nahi", "not now", "tomorrow"}
YES_WORDS = {"yes", "y", "yeah", "yep", "sure", "ok", "okay", "haan", "han", "ha", "ji", "ji haan", "bilkul", "theek", "thik", "done", "confirm"}
NO_WORDS = {"no", "n", "nope", "nahi", "nahin", "nhi", "na"}
RESCHEDULE_RE = re.compile(r"\breschedule|re-schedule|dobara (time|slot)|time change|badal", re.I)

ACTIVE_STATES = ["consent", "active", "callback", "human_live", "awaiting_choice"]

_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_HINGLISH_HINTS = re.compile(r"\b(hai|hain|nahi|nhi|haan|mera|meri|kitna|kitni|mahina|mahine|saal|din|karta|karti|chahiye|abhi)\b", re.I)
_NUM = re.compile(r"(\d+(?:\.\d+)?)")


def detect_language(text: str, current: str = "en") -> str:
    if _DEVANAGARI.search(text):
        return "hi"
    if _HINGLISH_HINTS.search(text):
        return "hinglish"
    return current if current != "hi" else "hinglish"


def _contains_any(text: str, words) -> bool:
    t = f" {text.lower().strip()} "
    return any(f" {w} " in t or t.strip() == w for w in words)


def _yesno(text: str) -> Optional[str]:
    t = text.lower().strip().rstrip("!.")
    first = t.split()[0] if t.split() else ""
    if first in YES_WORDS or _contains_any(t, {"haan", "yes", "bilkul", "ji haan"}):
        return "yes"
    if first in NO_WORDS or _contains_any(t, {"nahi", "nahin", "no experience"}):
        return "no"
    return None


# ═══════════════════════ rule-first extraction (v1) ══════════════════════

def rule_extract(kind: str, text: str, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    t = text.strip()
    if kind in ("consent", "identity", "skill"):
        yn = _yesno(t)
        if yn:
            return {"value": yn, "confident": True}
        return None
    if kind == "notice":
        days = parse_notice_to_days(t)
        if days is not None:
            return {"value": days, "confident": True}
        return None
    if kind in ("ctc_current", "ctc_expected"):
        lpa = parse_salary_to_lpa(t)
        if lpa is not None:
            return {"value": lpa, "confident": True}
        return None
    if kind == "experience":
        m = _NUM.search(t)
        if m:
            years = float(m.group(1))
            if re.search(r"month|mahin", t, re.I):
                years = years / 12
            if 0 <= years <= 50:
                return {"value": round(years, 1), "confident": True}
        return None
    if kind == "location":
        tl = t.lower()
        loc = str(param.get("location", "")).lower()
        if loc and loc.split(",")[0].strip() in tl:
            return {"value": "there", "confident": True}
        if _contains_any(tl, {"relocate", "shift ho", "move kar", "willing", "ready to relocate", "kahin bhi"}):
            return {"value": "willing", "confident": True}
        yn = _yesno(tl)
        if yn == "yes":
            return {"value": "willing", "confident": True}
        if yn == "no" or _contains_any(tl, {"relocate nahi", "not willing", "can't relocate", "cannot relocate"}):
            return {"value": "not_willing", "confident": True}
        return None
    if kind == "doc":
        if _contains_any(t.lower(), {"skip", "nahi hai", "baad mein bhejunga", "don't have"}):
            return {"value": "skipped", "confident": True}
        return None
    if kind == "custom":
        return {"value": t[:400], "confident": True}
    return None


_LLM_KIND = {
    "consent": "yesno", "identity": "yesno", "skill": "yesno",
    "notice": "notice", "ctc_current": "salary", "ctc_expected": "salary",
    "experience": "number", "location": "location", "custom": "text",
}


async def extract_answer(block: Dict[str, Any], text: str) -> Dict[str, Any]:
    rule = rule_extract(block["kind"], text, block.get("param") or {})
    if rule is not None:
        return rule
    if block["kind"] == "doc":
        return {"value": None, "confident": False}  # docs need media, not LLM
    llm = await screening_llm.extract(_LLM_KIND.get(block["kind"], "text"),
                                      block.get("en", ""), text)
    if llm is not None:
        return llm
    return {"value": None, "confident": False}


# ═══════════════════════════ messaging helpers ═══════════════════════════

CLOSING = {
    "qualified": {
        "en": "Thank you {name}! You're a strong match — our recruiter will contact you shortly with next steps. 🙏",
        "hi": "Dhanyawaad {name}! Aap achhe match hain — hamare recruiter jaldi hi aapse next steps ke liye contact karenge. 🙏",
    },
    "not_qualified": {
        "en": "Thank you {name} for your time! We've noted your details and will reach out when a matching role opens up.",
        "hi": "Dhanyawaad {name}! Aapki details save kar li hain — matching role aane par zaroor contact karenge.",
    },
    "opted_out": {
        "en": "Understood — you won't receive further messages from us. Thank you!",
        "hi": "Theek hai — aapko ab hamari taraf se message nahi aayenge. Dhanyawaad!",
    },
    "human": {
        "en": "Of course! Our recruiter will call you soon. Thank you!",
        "hi": "Bilkul! Hamare recruiter jaldi aapko call karenge. Dhanyawaad!",
    },
    "callback": {
        "en": "No problem — I'll message you tomorrow. Have a good day!",
        "hi": "Koi baat nahi — main aapko kal message karungi. Aapka din shubh ho!",
    },
    "refreshed": {
        "en": "That's everything — thank you {name}! Your profile is up to date. 🙏",
        "hi": "Bas ho gaya — dhanyawaad {name}! Aapki profile update ho gayi. 🙏",
    },
    "docs_done": {
        "en": "All received — thank you {name}! Our recruiter will take it from here. 🙏",
        "hi": "Sab mil gaya — dhanyawaad {name}! Aage recruiter handle karenge. 🙏",
    },
    "stalled_politely": {
        "en": "No worries — our recruiter will reach out directly. Thank you!",
        "hi": "Koi baat nahi — hamare recruiter aapse direct contact karenge. Dhanyawaad!",
    },
}


def _closing(key: str, session) -> str:
    lang = "hi" if session.get("language") in ("hi", "hinglish") else "en"
    name = (session.get("candidate_name") or "").split()[0] if session.get("candidate_name") else "ji"
    return CLOSING[key][lang].replace("{name}", name)


async def _out(db, session: Dict[str, Any], text: str, intro: bool = False,
               agent: str = "asha") -> None:
    to = session["phone_msisdn"]
    res = await (send_intro(to, text) if intro else send_text(to, text))
    await db.screening_sessions.update_one(
        {"id": session["id"]},
        {"$push": {"transcript": {"dir": "out", "agent": agent, "text": text,
                                  "at": utcnow(), "ok": res.get("ok", False)}},
         "$set": {"updated_at": utcnow(), "last_out_at": utcnow()}},
    )
    if not res.get("ok"):
        await db.screening_tasks.update_one(
            {"session_id": session["id"]},
            {"$set": {"last_error": res.get("error"), "updated_at": utcnow()}},
        )


def _skip_answered(session: Dict[str, Any]) -> None:
    """Advance idx past blocks whose answers were carried from a prior
    session (never re-ask a verified question)."""
    answers = session.get("answers") or {}
    while session["idx"] < len(session["blocks"]):
        b = session["blocks"][session["idx"]]
        a = answers.get(b["id"])
        if b["kind"] in ("consent", "identity") or not (a and a.get("value") is not None):
            break
        session["idx"] += 1


async def _ask_current(db, session: Dict[str, Any]) -> None:
    _skip_answered(session)
    await db.screening_sessions.update_one(
        {"id": session["id"]}, {"$set": {"idx": session["idx"]}})
    if session["idx"] >= len(session["blocks"]):
        return await _complete(db, session)
    block = session["blocks"][session["idx"]]
    name = (session.get("candidate_name") or "").split()[0] if session.get("candidate_name") else ""
    text = await screening_llm.phrase(block, name, session.get("language", "en"))
    await _out(db, session, text, intro=(block["kind"] == "consent"))


async def resume_session(db, session: Dict[str, Any]) -> None:
    """Public: reopen a callback/paused session and re-ask (task engine +
    takeover-resume use this)."""
    session["state"] = "active"
    await db.screening_sessions.update_one({"id": session["id"]}, {"$set": {"state": "active"}})
    await _ask_current(db, session)


# ═══════════════════ do-not-contact registry (phone-keyed) ═══════════════

async def is_do_not_contact(db, phone_normalized: str) -> bool:
    return bool(await db.agent_do_not_contact.find_one({"phone_normalized": phone_normalized}))


async def add_do_not_contact(db, phone_normalized: str, reason: str, evidence: str) -> None:
    await db.agent_do_not_contact.update_one(
        {"phone_normalized": phone_normalized},
        {"$set": {"reason": reason, "evidence": evidence, "updated_at": utcnow()},
         "$setOnInsert": {"created_at": utcnow()}},
        upsert=True,
    )


# ═══════════════════════════ session lifecycle ═══════════════════════════

async def start_session(db, candidate_id: str, mandate_id: Optional[str], pushed_by: str,
                        flow: str = "screening",
                        carry_from_session_id: Optional[str] = None,
                        docs_requested: Optional[List[str]] = None) -> Dict[str, Any]:
    candidate = await db.candidate_bank.find_one({"id": candidate_id})
    if not candidate:
        raise ValueError("candidate_not_found")

    phone = normalize_phone(candidate.get("phone"))
    if not phone:
        raise ValueError("no_phone")
    if await is_do_not_contact(db, phone):
        raise ValueError("do_not_contact")
    if ((candidate.get("consent") or {}).get("status") == "revoked"):
        raise ValueError("consent_revoked")
    opted = await db.edges.find_one({"src": f"cand:{candidate_id}", "rel": "OPTED_OUT"})
    if opted:
        raise ValueError("opted_out")

    job = {}
    if flow == "screening":
        job = await db.jobs.find_one({"id": mandate_id})
        if not job:
            raise ValueError("mandate_not_found")
        blocks = compile_script(job)
    elif flow == "refresh":
        blocks = flows.compile_refresh(candidate)
    elif flow == "docs":
        blocks = flows.compile_docs(docs_requested or ["updated_cv"])
    else:
        raise ValueError(f"unknown_flow:{flow}")

    existing = await db.screening_sessions.find_one(
        {"candidate_id": candidate_id, "mandate_id": mandate_id, "flow": flow,
         "state": {"$in": ACTIVE_STATES}})
    if existing:
        return existing

    answers: Dict[str, Any] = {}
    language = "en"
    if carry_from_session_id:
        old = await db.screening_sessions.find_one({"id": carry_from_session_id})
        if old:
            answers = flows.carry_answers(blocks, old)
            language = old.get("language", "en")

    session = {
        "id": str(uuid.uuid4()),
        "flow": flow,
        "candidate_id": candidate_id,
        "candidate_name": candidate.get("name"),
        "mandate_id": mandate_id,
        "mandate_title": (job.get("title") or job.get("job_title")) if job else None,
        "phone_normalized": phone,
        "phone_msisdn": phone if len(phone) > 10 else f"91{phone}",
        "channel": "whatsapp",
        "state": "consent",
        "blocks": blocks,
        "idx": 0,
        "answers": answers,
        "carried_from": carry_from_session_id,
        "language": language,
        "transcript": [],
        "pending": None,
        "verdict": None, "score": None, "disqualifier": None,
        "pushed_by": pushed_by,
        "created_at": utcnow(), "updated_at": utcnow(),
    }
    await db.screening_sessions.insert_one(dict(session))
    await db.screening_tasks.update_one(
        {"candidate_id": candidate_id, "mandate_id": mandate_id, "flow": flow},
        {"$set": {"state": "active", "session_id": session["id"],
                  "updated_at": utcnow(), "last_contact_at": utcnow()},
         "$setOnInsert": {"id": str(uuid.uuid4()), "attempts": 1,
                          "created_by": pushed_by, "created_at": utcnow()}},
        upsert=True,
    )
    await _ask_current(db, session)
    return session


async def handle_inbound(db, phone_normalized: str, text: str) -> bool:
    session = await db.screening_sessions.find_one(
        {"phone_normalized": phone_normalized, "state": {"$in": ACTIVE_STATES}})
    if not session:
        return False
    await handle_session_reply(db, session, text)
    return True


# ═════════════════════ the reply state machine ═══════════════════════════

async def handle_session_reply(db, session: Dict[str, Any], text: str) -> None:
    await db.screening_sessions.update_one(
        {"id": session["id"]},
        {"$push": {"transcript": {"dir": "in", "text": text, "at": utcnow()}},
         "$set": {"updated_at": utcnow()}},
    )
    session["language"] = detect_language(text, session.get("language", "en"))
    await db.screening_sessions.update_one(
        {"id": session["id"]}, {"$set": {"language": session["language"]}})

    # Human is live — Asha stays silent, recruiter reads the transcript.
    if session["state"] == "human_live":
        return

    low = text.lower()
    if _contains_any(low, STOP_WORDS):
        await add_do_not_contact(db, session["phone_normalized"], "stop_reply",
                                 f"asha:{session['id']}")
        return await _finish(db, session, state="opted_out", verdict="OPTED_OUT",
                             closing="opted_out", edge="OPTED_OUT")
    if _contains_any(low, HUMAN_WORDS):
        return await _finish(db, session, state="human_handoff", verdict="HUMAN_REQUESTED",
                             closing="human", edge="SCREENED", notify=True)

    # Post-completion chains awaiting a choice
    pending = session.get("pending")
    if pending:
        return await _handle_pending(db, session, text, pending)

    if session["state"] != "consent" and _contains_any(low, CALLBACK_WORDS):
        tomorrow = utcnow().replace(hour=5, minute=30, second=0) + timedelta(days=1)
        await db.screening_sessions.update_one({"id": session["id"]}, {"$set": {"state": "callback"}})
        await db.screening_tasks.update_one(
            {"session_id": session["id"]},
            {"$set": {"state": "queued", "next_attempt_at": tomorrow, "updated_at": utcnow()}})
        return await _out(db, session, _closing("callback", session))

    if session["state"] == "callback":
        return await resume_session(db, session)

    block = session["blocks"][session["idx"]]
    ans = await extract_answer(block, text)

    # ── FAQ interrupt: candidate asked a question instead of answering ──
    if (session["state"] == "active" and ans["value"] is None
            and flows.looks_like_question(text)):
        job = (await db.jobs.find_one({"id": session["mandate_id"]}) or {}) \
            if session.get("mandate_id") else {}
        faq = flows.answer_faq(text, job, session["language"])
        prefix = faq if faq else flows.unknown_faq_reply(session["language"])
        question = (block["hi"] if session["language"] in ("hi", "hinglish")
                    else block["en"]).replace("{name}", "")
        return await _out(db, session, f"{prefix}\n\n{question}")

    prior = session["answers"].get(block["id"], {})
    asks = prior.get("asks", 1)

    if not ans["confident"] and ans["value"] is None:
        if block["kind"] in ("consent", "identity") and asks >= 3:
            # loop guard: a chatty non-answer never traps the conversation
            await db.screening_tasks.update_one(
                {"session_id": session["id"]},
                {"$set": {"state": "stalled", "updated_at": utcnow()}})
            await db.screening_sessions.update_one(
                {"id": session["id"]},
                {"$set": {"state": "stalled", "updated_at": utcnow()}})
            return await _out(db, session, _closing("stalled_politely", session))
        if asks < 2:
            session["answers"][block["id"]] = {"raw": text, "value": None,
                                               "confident": False, "asks": asks + 1}
            await db.screening_sessions.update_one(
                {"id": session["id"]},
                {"$set": {f"answers.{block['id']}": session["answers"][block["id"]]}})
            if block["kind"] == "doc":
                gentle = ("Attachment ke roop mein bhejein 🙏 ya SKIP likhein."
                          if session["language"] in ("hi", "hinglish")
                          else "Please send it as an attachment 🙏 or reply SKIP.")
                return await _out(db, session, gentle)
            clarify = ("Sorry, samajh nahi aaya 🙏 — " if session["language"] in ("hi", "hinglish")
                       else "Sorry, I didn't catch that — ")
            return await _out(db, session, clarify +
                              (block["hi"] if session["language"] in ("hi", "hinglish")
                               else block["en"]).replace("{name}", ""))
        if block["kind"] == "doc":
            ans = {"value": "skipped", "confident": False}

    if not ans["confident"] and ans["value"] is None \
            and block["kind"] in ("consent", "identity"):
        asks += 1  # count toward the consent/identity loop guard only
    record = {"raw": text, "value": ans["value"], "confident": ans["confident"], "asks": asks}
    session["answers"][block["id"]] = record
    await db.screening_sessions.update_one(
        {"id": session["id"]}, {"$set": {f"answers.{block['id']}": record}})

    if block["kind"] == "consent":
        if ans["value"] == "yes":
            session["state"] = "active"
            await db.screening_sessions.update_one({"id": session["id"]}, {"$set": {"state": "active"}})
        elif ans["value"] == "no":
            return await _finish(db, session, "opted_out", "OPTED_OUT", "opted_out", edge="OPTED_OUT")
        else:
            return await _out(db, session,
                              "Please reply YES to continue, HUMAN for our recruiter, or STOP to opt out.")
    if block["kind"] == "identity" and ans["value"] == "no":
        return await _finish(db, session, "human_handoff", "WRONG_PERSON", "human",
                             edge="SCREENED", notify=True)

    session["idx"] += 1
    if session["idx"] < len(session["blocks"]):
        return await _ask_current(db, session)
    await _complete(db, session)


# ═══════════════════ media (documents · images · voice) ══════════════════

async def handle_inbound_media(db, phone_normalized: str, media: Dict[str, Any]) -> bool:
    """media: {type: audio|document|image, media_id, mime}. Returns True
    when routed into a session."""
    from services import screening_media as sm

    session = await db.screening_sessions.find_one(
        {"phone_normalized": phone_normalized, "state": {"$in": ACTIVE_STATES}})
    if not session:
        return False

    if media.get("type") == "audio":
        blob = await sm.download_media(media["media_id"]) if media.get("media_id") else None
        transcript = await sm.transcribe_voice({**media, **(blob or {})}) if blob else None
        if transcript:
            await db.screening_sessions.update_one(
                {"id": session["id"]},
                {"$push": {"transcript": {"dir": "in", "text": f"[voice] {transcript}",
                                          "at": utcnow()}}})
            await handle_session_reply(db, session, transcript)
        else:
            await _out(db, session, sm.voice_unavailable_text(session.get("language", "en")))
        return True

    # document / image
    if session["state"] == "human_live":
        await db.screening_sessions.update_one(
            {"id": session["id"]},
            {"$push": {"transcript": {"dir": "in", "text": f"[attachment {media.get('mime','')}]",
                                      "at": utcnow()}}})
        return True

    block = (session["blocks"][session["idx"]]
             if session["idx"] < len(session["blocks"]) else None)
    if session.get("flow") == "docs" and block and block["kind"] == "doc" \
            and session["state"] == "active":
        blob = await sm.download_media(media["media_id"]) if media.get("media_id") else None
        if not blob:
            await _out(db, session, "Attachment receive nahi hua 🙏 — dobara try karein?")
            return True
        entry = await sm.store_candidate_doc(db, session["candidate_id"],
                                             block["param"]["doc_key"], blob)
        value = entry["r2_key"] if entry else "receive_failed"
        session["answers"][block["id"]] = {"raw": f"[{media.get('mime')}]",
                                           "value": value, "confident": bool(entry), "asks": 1}
        await db.screening_sessions.update_one(
            {"id": session["id"]},
            {"$set": {f"answers.{block['id']}": session["answers"][block["id"]]},
             "$push": {"transcript": {"dir": "in", "text": f"[attachment {media.get('mime','')}]",
                                      "at": utcnow()}}})
        ack = "Mil gaya ✅" if session.get("language") in ("hi", "hinglish") else "Received ✅"
        await _out(db, session, ack)
        session["idx"] += 1
        if session["idx"] < len(session["blocks"]):
            await _ask_current(db, session)
        else:
            await _complete(db, session)
        return True

    # attachment outside the docs flow — acknowledge, don't advance
    note = ("Attachment mil gaya 🙏 — recruiter dekh lenge. Abhi ke liye text mein reply karein."
            if session.get("language") in ("hi", "hinglish")
            else "Got the attachment 🙏 — our recruiter will see it. For now, please reply in text.")
    await db.screening_sessions.update_one(
        {"id": session["id"]},
        {"$push": {"transcript": {"dir": "in", "text": f"[attachment {media.get('mime','')}]",
                                  "at": utcnow()}}})
    await _out(db, session, note)
    return True


# ═══════════════ pending chains: slots + cross-offer ═════════════════════

async def _handle_pending(db, session: Dict[str, Any], text: str,
                          pending: Dict[str, Any]) -> None:
    kind = pending.get("kind")

    if kind == "slot_offer":
        slots = [await db.interview_slots.find_one({"id": sid})
                 for sid in pending.get("slot_ids", [])]
        slots = [s for s in slots if s]
        choice = sched.parse_slot_choice(text, slots)
        if choice == "none":
            await _clear_pending(db, session)
            msg = ("Theek hai — recruiter aapko call karke time fix karenge. 🙏"
                   if session["language"] in ("hi", "hinglish")
                   else "No problem — our recruiter will call you to fix a time. 🙏")
            return await _out(db, session, msg)
        if choice is None:
            if pending.get("retries", 0) >= 1:
                await _clear_pending(db, session)
                return await _out(db, session, _closing("stalled_politely", session))
            pending["retries"] = pending.get("retries", 0) + 1
            await db.screening_sessions.update_one(
                {"id": session["id"]}, {"$set": {"pending": pending}})
            return await _out(db, session, sched.offer_text(slots, session["language"]))
        slot = slots[choice]
        interview = await sched.book(db, session, slot)
        if not interview:
            fresh = await sched.open_slots(db, session["mandate_id"])
            if not fresh:
                await _clear_pending(db, session)
                return await _out(db, session,
                                  "Woh slot abhi bhar gaya — recruiter aapko call karenge. 🙏")
            pending["slot_ids"] = [s["id"] for s in fresh]
            await db.screening_sessions.update_one(
                {"id": session["id"]}, {"$set": {"pending": pending}})
            return await _out(db, session, "Woh slot abhi book ho gaya — " +
                              sched.offer_text(fresh, session["language"]))
        await db.interviews.update_one(
            {"id": interview["id"]},
            {"$set": {"phone_normalized": session["phone_normalized"],
                      "language": session["language"]}})
        await _clear_pending(db, session)
        await _out(db, session, sched.confirmation_text(interview, session["language"]))
        return await _referral_tail(db, session)

    if kind == "cross_offer":
        yn = _yesno(text)
        if yn == "yes":
            await _clear_pending(db, session)
            alt_id = pending["mandate_id"]
            try:
                await start_session(db, session["candidate_id"], alt_id,
                                    pushed_by=f"cross_offer:{session['id']}",
                                    carry_from_session_id=session["id"])
            except ValueError as e:
                logger.warning("[Asha] cross-offer start failed: %s", e)
            return
        if yn == "no":
            await _clear_pending(db, session)
            return await _out(db, session, _closing("not_qualified", session))
        return await _out(db, session,
                          "Haan ya Nahi likhein 🙂" if session["language"] in ("hi", "hinglish")
                          else "A quick Yes or No 🙂")

    await _clear_pending(db, session)


async def _clear_pending(db, session: Dict[str, Any]) -> None:
    session["pending"] = None
    session["state"] = "completed"
    await db.screening_sessions.update_one(
        {"id": session["id"]},
        {"$set": {"pending": None, "state": "completed"}})


# ═══════════════════ completion · scoring · write-back ═══════════════════

def _default_scorer():
    from routes.extension_preview import _score_fit
    return _score_fit

score_fn: Callable = None


def _verified_fields(session) -> Dict[str, Any]:
    a = session["answers"]
    get = lambda k: (a.get(k) or {}).get("value")
    out: Dict[str, Any] = {}
    if isinstance(get("notice"), int):
        out["notice_days"] = get("notice")
    if isinstance(get("experience"), (int, float)):
        out["experience_months"] = int(float(get("experience")) * 12)
        out["total_experience_years"] = float(get("experience"))
    if isinstance(get("ctc_current"), (int, float)):
        out["current_lpa"] = float(get("ctc_current"))
    if isinstance(get("ctc_expected"), (int, float)):
        out["expected_lpa"] = float(get("ctc_expected"))
    skills_yes, skills_no = [], []
    for b in session["blocks"]:
        if b["kind"] == "skill":
            v = (a.get(b["id"]) or {}).get("value")
            (skills_yes if v == "yes" else skills_no if v == "no" else []).append(b["param"]["skill"])
    if skills_yes:
        out["verified_skills"] = skills_yes
    if skills_no:
        out["verified_skill_gaps"] = skills_no
    loc = get("location")
    if loc in ("there", "willing", "not_willing"):
        out["relocation_status"] = loc
    return out


def _verdict(session, verified, job, score):
    a = session["answers"]
    for b in session["blocks"]:
        if b["kind"] == "skill" and b.get("must_have"):
            if (a.get(b["id"]) or {}).get("value") == "no":
                return "NOT_QUALIFIED", f"Missing must-have skill: {b['param']['skill']}"
    cap = next((b["param"].get("cap_days") for b in session["blocks"]
                if b["kind"] == "notice" and b.get("param")), None)
    if cap is not None and isinstance(verified.get("notice_days"), int) and verified["notice_days"] > cap:
        return "NOT_QUALIFIED", f"Notice {verified['notice_days']}d exceeds cap {cap}d"
    exp_block = next((b for b in session["blocks"] if b["kind"] == "experience"), None)
    if exp_block and exp_block.get("must_have"):
        mn = (exp_block["param"] or {}).get("min_years")
        yrs = verified.get("total_experience_years")
        if mn and isinstance(yrs, (int, float)) and yrs < mn * 0.8:
            return "NOT_QUALIFIED", f"Experience {yrs:g}y below minimum {mn:g}y"
    bmax = next((b["param"].get("budget_max_lpa") for b in session["blocks"]
                 if b["kind"] == "ctc_expected" and b.get("param")), None)
    if bmax and isinstance(verified.get("expected_lpa"), (int, float)) and \
            verified["expected_lpa"] > bmax * BUDGET_STRETCH:
        return "NOT_QUALIFIED", f"Expected {verified['expected_lpa']:g} LPA exceeds budget {bmax:g} LPA"
    if verified.get("relocation_status") == "not_willing":
        return "NOT_QUALIFIED", "Not willing to relocate to job location"
    if score is not None and score < QUALIFY_THRESHOLD:
        return "NOT_QUALIFIED", f"Match score {score}% below threshold {QUALIFY_THRESHOLD}%"
    return "QUALIFIED", None


async def _writeback(db, session, candidate, verified, source: str) -> None:
    sets = {}
    prov_agent = (candidate.get("provenance") or {}).get("source") in ("agent_screening", "agent_refresh")
    for field in ("notice_days", "current_lpa", "expected_lpa", "experience_months"):
        if field in verified and (candidate.get(field) is None or prov_agent):
            sets[field] = verified[field]
    if verified.get("verified_skills"):
        sets["verified_skills"] = verified["verified_skills"]
    if verified.get("verified_skill_gaps"):
        sets["verified_skill_gaps"] = verified["verified_skill_gaps"]
    if sets:
        sets["provenance.resolved_at"] = utcnow()
        sets["provenance.source"] = source
        await db.candidate_bank.update_one({"id": session["candidate_id"]}, {"$set": sets})


async def _complete(db, session) -> None:
    candidate = await db.candidate_bank.find_one({"id": session["candidate_id"]}) or {}

    # ── refresh flow: no verdict, just an updated profile ──
    if session.get("flow") == "refresh":
        verified = _verified_fields(session)
        a = session["answers"]
        desig = (a.get("designation_now") or {}).get("value")
        await db.screening_sessions.update_one(
            {"id": session["id"]},
            {"$set": {"state": "completed", "verdict": "REFRESHED",
                      "verified": verified, "completed_at": utcnow(), "updated_at": utcnow()}})
        await db.screening_tasks.update_one(
            {"session_id": session["id"]}, {"$set": {"state": "done", "updated_at": utcnow()}})
        await _writeback(db, session, candidate, verified, "agent_refresh")
        if desig and isinstance(desig, str) and len(desig) < 100 \
                and (candidate.get("current_designation") is None
                     or (candidate.get("provenance") or {}).get("source", "").startswith("agent")):
            await db.candidate_bank.update_one(
                {"id": session["candidate_id"]},
                {"$set": {"current_designation": desig}})
        await _out(db, session, _closing("refreshed", session))
        # open to opportunities → queue a screening against the best live mandate
        if (a.get("open_to_opps") or {}).get("value") == "yes":
            try:
                fn = score_fn or _default_scorer()
                alt = await flows.find_alternative(
                    db, {**session, "mandate_id": None}, candidate, verified, fn)
            except Exception:
                alt = None
            if alt:
                await db.screening_tasks.update_one(
                    {"candidate_id": session["candidate_id"],
                     "mandate_id": alt["job"]["id"], "flow": "screening"},
                    {"$setOnInsert": {"id": str(uuid.uuid4()), "state": "queued",
                                      "attempts": 0, "priority": 7, "next_attempt_at": None,
                                      "created_by": f"refresh:{session['id']}",
                                      "created_at": utcnow()},
                     "$set": {"updated_at": utcnow()}}, upsert=True)
        return

    # ── docs flow ──
    if session.get("flow") == "docs":
        received = [b["param"]["doc_key"] for b in session["blocks"] if b["kind"] == "doc"
                    and (session["answers"].get(b["id"]) or {}).get("value")
                    not in (None, "skipped", "receive_failed")]
        await db.screening_sessions.update_one(
            {"id": session["id"]},
            {"$set": {"state": "completed", "verdict": "DOCS_COLLECTED",
                      "verified": {"documents_received": received},
                      "completed_at": utcnow(), "updated_at": utcnow()}})
        await db.screening_tasks.update_one(
            {"session_id": session["id"]}, {"$set": {"state": "done", "updated_at": utcnow()}})
        return await _out(db, session, _closing("docs_done", session))

    # ── screening flow (v1 semantics) ──
    job = await db.jobs.find_one({"id": session["mandate_id"]}) or {}
    verified = _verified_fields(session)
    merged = dict(candidate)
    merged.update({k: v for k, v in verified.items() if k != "verified_skill_gaps"})
    if verified.get("verified_skills"):
        merged["key_skills"] = list({*(candidate.get("key_skills") or []), *verified["verified_skills"]})

    score = None
    try:
        fn = score_fn or _default_scorer()
        fit = fn(merged, job)
        score = fit.get("score")
    except Exception as e:
        logger.warning("[Asha] scoring failed: %s", e)

    verdict, disq = _verdict(session, verified, job, score)
    await db.screening_sessions.update_one(
        {"id": session["id"]},
        {"$set": {"state": "completed", "verdict": verdict, "score": score,
                  "disqualifier": disq, "verified": verified,
                  "completed_at": utcnow(), "updated_at": utcnow()}})
    await db.screening_tasks.update_one(
        {"session_id": session["id"]}, {"$set": {"state": "done", "updated_at": utcnow()}})

    await _writeback(db, session, candidate, verified, "agent_screening")

    edges = [{"src": f"cand:{session['candidate_id']}", "src_type": "candidate",
              "rel": "SCREENED", "dst": f"mandate:{session['mandate_id']}",
              "dst_type": "mandate", "weight": (score or 0) / 100,
              "evidence": f"asha:{session['id']}", "created_at": utcnow(), "updated_at": utcnow()}]
    if verdict == "QUALIFIED":
        edges.append({**edges[0], "rel": "MATCHED_TO"})
    for e in edges:
        await db.edges.insert_one(dict(e))

    # ── post-completion chains ──
    if verdict == "QUALIFIED":
        await _out(db, session, _closing("qualified", session))
        if os.environ.get("AGENT_AUTO_SCHEDULE", "1") == "1" \
                and job.get("agent_auto_schedule") is not False:
            slots = await sched.open_slots(db, session["mandate_id"])
            if slots:
                pending = {"kind": "slot_offer", "slot_ids": [s["id"] for s in slots], "retries": 0}
                session["pending"] = pending
                session["state"] = "awaiting_choice"
                await db.screening_sessions.update_one(
                    {"id": session["id"]},
                    {"$set": {"pending": pending, "state": "awaiting_choice"}})
                return await _out(db, session, sched.offer_text(slots, session["language"]))
        return await _referral_tail(db, session)

    # NOT_QUALIFIED → one respectful alternative, if a genuine fit exists
    try:
        fn = score_fn or _default_scorer()
        alt = await flows.find_alternative(db, session, candidate, verified, fn)
    except Exception as e:
        logger.warning("[Asha] cross-offer search failed: %s", e)
        alt = None
    if alt:
        pending = {"kind": "cross_offer", "mandate_id": alt["job"]["id"],
                   "score": alt["score"]}
        session["pending"] = pending
        session["state"] = "awaiting_choice"
        await db.screening_sessions.update_one(
            {"id": session["id"]},
            {"$set": {"pending": pending, "state": "awaiting_choice"}})
        return await _out(db, session,
                          flows.cross_offer_text(alt["job"], session["language"]))

    await _out(db, session, _closing("not_qualified", session))
    logger.info("[Asha] session %s → %s (score=%s) %s",
                session["id"], verdict, score, disq or "")


async def _referral_tail(db, session) -> None:
    job = (await db.jobs.find_one({"id": session["mandate_id"]}) or {}) \
        if session.get("mandate_id") else {}
    text = flows.referral_text(job, session.get("language", "en"))
    if text:
        await _out(db, session, text)


async def _finish(db, session, state, verdict, closing, edge=None, notify=False) -> None:
    await db.screening_sessions.update_one(
        {"id": session["id"]},
        {"$set": {"state": state, "verdict": verdict, "pending": None,
                  "completed_at": utcnow(), "updated_at": utcnow()}})
    await db.screening_tasks.update_one(
        {"session_id": session["id"]},
        {"$set": {"state": "opted_out" if state == "opted_out" else "done",
                  "updated_at": utcnow()}})
    if edge:
        await db.edges.insert_one({
            "src": f"cand:{session['candidate_id']}", "src_type": "candidate",
            "rel": edge, "dst": f"mandate:{session['mandate_id']}", "dst_type": "mandate",
            "weight": 0.0, "evidence": f"asha:{session['id']}",
            "created_at": utcnow(), "updated_at": utcnow()})
    if notify:
        logger.info("[Asha] HUMAN HANDOFF requested — candidate %s mandate %s",
                    session["candidate_id"], session["mandate_id"])
    await _out(db, session, _closing(closing, session))


# ═══════════════ webhook dispatcher (single entry point) ═════════════════

async def route_inbound(db, phone_normalized: str, msg: Dict[str, Any]) -> str:
    """msg: WhatsApp message object. Returns which handler consumed it:
    'session' | 'interview' | 'placement' | 'ignored'."""
    mtype = msg.get("type")

    if mtype == "text":
        body = ((msg.get("text") or {}).get("body") or "").strip()
        if not body:
            return "ignored"
        if await handle_inbound(db, phone_normalized, body):
            return "session"
        # booked interview? (RESCHEDULE and acknowledgements)
        interview = await db.interviews.find_one(
            {"phone_normalized": phone_normalized,
             "status": {"$in": ["booked", "reminded_24h", "reminded_2h"]}})
        if interview:
            await _handle_interview_reply(db, interview, body)
            return "interview"
        from services.screening_joining import handle_placement_inbound
        if await handle_placement_inbound(db, phone_normalized, body):
            return "placement"
        return "ignored"

    if mtype in ("audio", "voice", "document", "image"):
        media = {"type": "audio" if mtype in ("audio", "voice") else mtype,
                 "media_id": (msg.get(mtype) or {}).get("id"),
                 "mime": (msg.get(mtype) or {}).get("mime_type", "")}
        if await handle_inbound_media(db, phone_normalized, media):
            return "session"
        return "ignored"

    return "ignored"


async def _handle_interview_reply(db, interview: Dict[str, Any], text: str) -> None:
    lang = interview.get("language", "hinglish")
    to = interview["phone_msisdn"]
    if RESCHEDULE_RE.search(text):
        await sched.cancel_booking(db, interview, "rescheduling")
        session = await db.screening_sessions.find_one({"id": interview.get("session_id")})
        slots = await sched.open_slots(db, interview["mandate_id"])
        if session and slots:
            pending = {"kind": "slot_offer", "slot_ids": [s["id"] for s in slots], "retries": 0}
            await db.screening_sessions.update_one(
                {"id": session["id"]}, {"$set": {"state": "active", "pending": pending,
                                                 "updated_at": utcnow()}})
            session.update(state="active", pending=pending)
            return await _out(db, session, sched.offer_text(slots, lang))
        msg = ("Theek hai — recruiter aapko call karke naya time fix karenge. 🙏"
               if lang in ("hi", "hinglish")
               else "No problem — our recruiter will call you to fix a new time. 🙏")
        await send_text(to, msg)
        return
    yn = _yesno(text)
    if yn == "yes" or _contains_any(text.lower(), {"ok", "done", "confirm", "sure", "thik"}):
        await send_text(to, "👍 See you there!" if lang == "en" else "👍 Milte hain!")
