"""
test_screening_v2.py — Asha v2 features under deterministic test
=================================================================
AGENT_LLM=0, AGENT_DRY_RUN=1: no network, no LLM, no Mongo.

    cd backend && python -m pytest tests/ -q      # runs v1 + v2 suites
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ["AGENT_LLM"] = "0"
os.environ["AGENT_DRY_RUN"] = "1"
os.environ["AGENT_QUALIFY_THRESHOLD"] = "55"
os.environ["AGENT_CROSS_OFFER"] = "1"
os.environ["AGENT_AUTO_SCHEDULE"] = "1"
os.environ["AGENT_REFERRAL"] = "0"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from tests.fakedb import FakeDB  # noqa: E402
from services import screening_engine as eng  # noqa: E402
from services import screening_flows as flows  # noqa: E402
from services import screening_scheduling as sched  # noqa: E402
from services import screening_joining as joining  # noqa: E402
from services import screening_media  # noqa: E402
from services.screening_analytics import funnel  # noqa: E402
from services.screening_forms import make_token, verify_token, render_form, remaining_blocks  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))


def run(coro):
    return asyncio.run(coro)


JOB1 = {
    "id": "job1", "title": "Area Sales Manager", "location": "Pune",
    "status": "active",
    "min_experience": 5, "max_experience": 10,
    "salary_min": 800000, "salary_max": 1500000,
    "max_notice_days": 60,
    "key_skills": ["Channel Sales", "Distributor Sales"],
    "skill_requirements": [
        {"skill_name": "Channel Sales", "must_have": True},
        {"skill_name": "Distributor Sales", "must_have": False},
    ],
    "company_name": "Acme FMCG",
}
# alternative: bigger budget, same must-have, different city
JOB2 = {
    "id": "job2", "title": "Regional Sales Manager", "location": "Mumbai",
    "status": "active",
    "min_experience": 5, "max_experience": 12,
    "salary_min": 1500000, "salary_max": 3500000,
    "max_notice_days": 90,
    "key_skills": ["Channel Sales"],
    "skill_requirements": [{"skill_name": "Channel Sales", "must_have": True}],
    "confidential": True,
}
CAND = {"id": "c1", "name": "Chandrashekar H S", "phone": "+91 98450 12345",
        "key_skills": ["Retail Sales"], "notice_days": None}
CAND_DUP = {"id": "c2", "name": "Chandrashekar HS (dup)", "phone": "098450 12345",
            "key_skills": [], "notice_days": None}


def make_db(jobs=(JOB1,), cands=(CAND,)):
    db = FakeDB()
    for j in jobs:
        db.jobs.docs.append(dict(j))
    for c in cands:
        db.candidate_bank.docs.append(dict(c))
    eng.score_fn = lambda cand, job: {"score": 82}
    return db


async def converse(db, replies, candidate_id="c1", mandate_id="job1", session=None):
    if session is None:
        session = await eng.start_session(db, candidate_id, mandate_id, "test@vhc.in")
    for text in replies:
        s = await db.screening_sessions.find_one({"id": session["id"]})
        if s["state"] not in tuple(eng.ACTIVE_STATES):
            break
        await eng.handle_session_reply(db, s, text)
    return await db.screening_sessions.find_one({"id": session["id"]})


HAPPY = ["haan", "ji haan", "2 mahine ka notice hai", "8 saal",
         "haan bilkul", "Pune mein hoon", "haan", "12.5 lakh", "16 LPA"]


# ══════════════════ 1. DNC registry across duplicates ════════════════════

def test_dnc_registry_blocks_duplicate_records():
    db = make_db(cands=(CAND, CAND_DUP))  # same human, two records
    run(converse(db, ["haan", "yes", "STOP"]))
    assert db.agent_do_not_contact.docs, "STOP must write the phone registry"
    # pushing the DUPLICATE record must also be refused
    with pytest.raises(ValueError, match="do_not_contact"):
        run(eng.start_session(db, "c2", "job1", "test@vhc.in"))


# ══════════════════ 2. FAQ interrupts ════════════════════════════════════

def test_faq_interrupt_answers_and_reasks():
    db = make_db()
    final = run(converse(db, [
        "haan", "ji haan",
        "salary kitni hai?",          # interrupt on the notice question
        *HAPPY[2:],
    ]))
    assert final["state"] == "completed" and final["verdict"] == "QUALIFIED"
    outs = [t["text"] for t in final["transcript"] if t["dir"] == "out"]
    faq_reply = next(o for o in outs if "LPA" in o and "notice" in o.lower())
    assert "8" in faq_reply and "15" in faq_reply  # 8–15 LPA range disclosed
    # the interrupt consumed no block: notice answer still landed correctly
    assert final["verified"]["notice_days"] == 60


def test_faq_confidential_never_reveals_client():
    reply = flows.answer_faq("company kaun si hai?", JOB2, "hinglish")
    assert "confidential" in reply.lower()
    reply2 = flows.answer_faq("which company is this?", JOB1, "en")
    assert "Acme FMCG" in reply2


def test_faq_unknown_defers_to_recruiter():
    db = make_db()
    final = run(converse(db, [
        "haan", "ji haan",
        "PF milta hai kya?",           # not in whitelist
        *HAPPY[2:],
    ]))
    outs = [t["text"] for t in final["transcript"] if t["dir"] == "out"]
    assert any("recruiter" in o.lower() and "notice" in o.lower() for o in outs)
    assert final["verdict"] == "QUALIFIED"


# ══════════════════ 3. consent loop guard ════════════════════════════════

def test_consent_loop_guard_stalls():
    db = make_db()
    final = run(converse(db, ["hmm", "kaun ho aap", "matlab kya", "acha theek"]))
    assert final["state"] == "stalled"
    task = db.screening_tasks.docs[0]
    assert task["state"] == "stalled"


# ══════════════════ 4. interview scheduling ══════════════════════════════

def _slot(db, sid, hours_ahead, cap=1):
    s = {"id": sid, "mandate_id": "job1",
         "start": datetime.now(timezone.utc) + timedelta(hours=hours_ahead),
         "duration_min": 30, "capacity": cap, "booked_count": 0,
         "mode": "phone", "details": None}
    db.interview_slots.docs.append(dict(s))
    return s


def test_qualified_gets_slot_offer_and_books():
    db = make_db()
    _slot(db, "s1", 26)
    _slot(db, "s2", 50)
    final = run(converse(db, HAPPY))
    assert final["verdict"] == "QUALIFIED"
    assert final["pending"]["kind"] == "slot_offer"
    outs = [t["text"] for t in final["transcript"] if t["dir"] == "out"]
    assert any("1." in o and "2." in o and "IST" in o for o in outs)
    # pick slot 2
    final = run(converse(db, ["2"], session=final))
    assert final["pending"] is None
    iv = db.interviews.docs[0]
    assert iv["slot_id"] == "s2" and iv["status"] == "booked"
    slot2 = next(s for s in db.interview_slots.docs if s["id"] == "s2")
    assert slot2["booked_count"] == 1
    assert any("book" in t["text"].lower() or "✅" in t["text"]
               for t in final["transcript"] if t["dir"] == "out")


def test_slot_none_and_capacity_race():
    db = make_db()
    _slot(db, "s1", 26, cap=1)
    final = run(converse(db, HAPPY))
    # "none of these" path
    final = run(converse(db, ["none of these"], session=final))
    assert final["pending"] is None
    assert any("recruiter" in t["text"].lower() for t in final["transcript"][-2:])
    # capacity race: pre-book the seat, then a booking attempt must fail
    slot = db.interview_slots.docs[0]
    slot["booked_count"] = 1
    booked = run(sched.book(db, final, slot))
    assert booked is None


def test_reschedule_reopens_slot_offer():
    db = make_db()
    _slot(db, "s1", 26)
    _slot(db, "s2", 50)
    final = run(converse(db, [*HAPPY, "1"]))
    iv = db.interviews.docs[0]
    assert iv["status"] == "booked"
    # completed session; RESCHEDULE arrives via the webhook dispatcher
    result = run(eng.route_inbound(db, final["phone_normalized"],
                                   {"type": "text", "text": {"body": "reschedule please"}}))
    assert result == "interview"
    iv = db.interviews.docs[0]
    assert iv["status"] == "rescheduling"
    slot1 = next(s for s in db.interview_slots.docs if s["id"] == "s1")
    assert slot1["booked_count"] == 0          # seat released
    fresh = run(db.screening_sessions.find_one({"id": final["id"]}))
    assert fresh["state"] == "active" and fresh["pending"]["kind"] == "slot_offer"


def test_slot_choice_parsing():
    slots = [{"start": datetime(2026, 7, 29, 5, 0, tzinfo=timezone.utc)},   # Wed IST
             {"start": datetime(2026, 7, 30, 5, 0, tzinfo=timezone.utc)}]
    assert sched.parse_slot_choice("pehla wala", slots) == 0
    assert sched.parse_slot_choice("2", slots) == 1
    assert sched.parse_slot_choice("wednesday works", slots) == 0
    assert sched.parse_slot_choice("none of these", slots) == "none"
    assert sched.parse_slot_choice("hmm", slots) is None


# ══════════════════ 5. cross-mandate offer + carry ═══════════════════════

def test_cross_offer_with_carried_answers():
    db = make_db(jobs=(JOB1, JOB2))
    # expected 30 LPA blows job1's 15 budget → NOT_QUALIFIED → offer job2
    final = run(converse(db, [
        "haan", "ji haan", "2 mahine ka notice hai", "8 saal",
        "haan bilkul", "Pune mein hoon", "haan", "18 lakh", "30 LPA",
    ]))
    assert final["verdict"] == "NOT_QUALIFIED"
    assert final["pending"]["kind"] == "cross_offer"
    assert final["pending"]["mandate_id"] == "job2"
    outs = [t["text"] for t in final["transcript"] if t["dir"] == "out"]
    assert any("Regional Sales Manager" in o for o in outs)
    # accept → new session with carried answers, never re-asks notice/ctc
    run(eng.handle_session_reply(db, final, "haan"))
    new = run(db.screening_sessions.find_one({"mandate_id": "job2"}))
    assert new is not None and new["carried_from"] == final["id"]
    for bid in ("notice", "experience", "ctc_current", "ctc_expected"):
        assert new["answers"][bid]["value"] is not None
    # finish the short remainder: consent, identity, must-skill, location
    done = run(converse(db, ["haan", "ji", "haan", "Mumbai shift ho jaunga"],
                        session=new))
    assert done["state"] == "completed" and done["verdict"] == "QUALIFIED"
    asked = [t["text"] for t in done["transcript"] if t["dir"] == "out"]
    assert not any("notice" in q.lower() for q in asked), "carried Q re-asked!"


# ══════════════════ 6. refresh flow ══════════════════════════════════════

def test_refresh_flow_writeback_and_chaining():
    db = make_db(jobs=(JOB1,))
    db.candidate_bank.docs[0]["current_employer"] = "OldCo"
    db.candidate_bank.docs[0]["key_skills"] = ["Channel Sales"]
    session = run(eng.start_session(db, "c1", None, "refresh_batch", flow="refresh"))
    final = run(converse(db, [
        "haan",                    # consent
        "haan",                    # still at OldCo
        "Senior Sales Manager",    # designation now
        "14 lakh",                 # ctc
        "1 mahina",                # notice
        "haan",                    # open to opportunities
    ], session=session))
    assert final["verdict"] == "REFRESHED"
    cand = db.candidate_bank.docs[0]
    assert cand["current_lpa"] == 14.0 and cand["notice_days"] == 30
    assert cand["provenance"]["source"] == "agent_refresh"
    assert cand["current_designation"] == "Senior Sales Manager"
    # open-to-opps chained a queued screening task for job1
    chained = [t for t in db.screening_tasks.docs
               if t.get("flow") == "screening" and t.get("state") == "queued"]
    assert chained and chained[0]["mandate_id"] == "job1"


# ══════════════════ 7. docs flow + media ═════════════════════════════════

def test_docs_flow_receive_and_skip():
    db = make_db()

    async def fake_upload(content, key, mime):
        return {"local": True, "key": key}
    screening_media._uploader = fake_upload

    async def fake_download(media_id):
        return {"bytes": b"PDFDATA", "mime": "application/pdf", "size": 7}
    real_dl = screening_media.download_media
    screening_media.download_media = fake_download
    try:
        session = run(eng.start_session(db, "c1", None, "rec@vhc.in",
                                        flow="docs",
                                        docs_requested=["updated_cv", "photo"]))
        s = run(db.screening_sessions.find_one({"id": session["id"]}))
        run(eng.handle_session_reply(db, s, "haan"))          # consent
        # CV arrives as a document attachment
        handled = run(eng.handle_inbound_media(db, session["phone_normalized"],
                      {"type": "document", "media_id": "m1", "mime": "application/pdf"}))
        assert handled
        cand = db.candidate_bank.docs[0]
        assert cand["agent_documents"][0]["kind"] == "updated_cv"
        assert cand["needs_reparse"] is True
        # photo: skip
        s = run(db.screening_sessions.find_one({"id": session["id"]}))
        run(eng.handle_session_reply(db, s, "SKIP"))
        final = run(db.screening_sessions.find_one({"id": session["id"]}))
        assert final["verdict"] == "DOCS_COLLECTED"
        assert final["verified"]["documents_received"] == ["updated_cv"]
    finally:
        screening_media.download_media = real_dl
        screening_media._uploader = None


def test_voice_note_stt_off_fallback():
    os.environ["AGENT_STT"] = "0"
    db = make_db()
    session = run(eng.start_session(db, "c1", "job1", "rec@vhc.in"))

    async def fake_download(media_id):
        return {"bytes": b"OGG", "mime": "audio/ogg"}
    real_dl = screening_media.download_media
    screening_media.download_media = fake_download
    try:
        run(eng.handle_inbound_media(db, session["phone_normalized"],
            {"type": "audio", "media_id": "a1", "mime": "audio/ogg"}))
        fresh = run(db.screening_sessions.find_one({"id": session["id"]}))
        assert fresh["state"] == "consent"                  # nothing advanced
        assert any("text" in t["text"].lower()
                   for t in fresh["transcript"] if t["dir"] == "out")
    finally:
        screening_media.download_media = real_dl


# ══════════════════ 8. human takeover ════════════════════════════════════

def test_takeover_pauses_and_resume_reasks():
    db = make_db()
    session = run(eng.start_session(db, "c1", "job1", "rec@vhc.in"))
    s = run(db.screening_sessions.find_one({"id": session["id"]}))
    run(eng.handle_session_reply(db, s, "haan"))
    run(db.screening_sessions.update_one({"id": session["id"]},
                                         {"$set": {"state": "human_live"}}))
    s = run(db.screening_sessions.find_one({"id": session["id"]}))
    idx_before = s["idx"]
    run(eng.handle_session_reply(db, s, "mujhe kuch poochna tha"))
    fresh = run(db.screening_sessions.find_one({"id": session["id"]}))
    assert fresh["state"] == "human_live" and fresh["idx"] == idx_before
    outs_before = len([t for t in fresh["transcript"] if t["dir"] == "out"])
    run(eng.resume_session(db, fresh))
    fresh2 = run(db.screening_sessions.find_one({"id": session["id"]}))
    assert fresh2["state"] == "active"
    outs_after = len([t for t in fresh2["transcript"] if t["dir"] == "out"])
    assert outs_after == outs_before + 1                   # re-asked current Q


# ══════════════════ 9. joining shepherd ══════════════════════════════════

def test_joining_touchpoints_and_ghost_risk():
    db = make_db()
    jd = (datetime.now(IST) + timedelta(days=3)).replace(
        hour=9, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    p = run(joining.create_placement(db, "c1", "job1", jd, "rec@vhc.in"))
    now = datetime.now(IST).replace(hour=10).astimezone(timezone.utc)
    assert joining.due_touchpoints(p, now) == ["t3"]
    p["touchpoints_sent"] = ["t3"]
    assert joining.due_touchpoints(p, now) == []
    # inbound replies through the dispatcher (no session active)
    result = run(eng.route_inbound(db, p["phone_normalized"],
                 {"type": "text", "text": {"body": "sir dusri offer aa gayi hai"}}))
    assert result == "placement"
    fresh = db.placements.docs[0]
    assert fresh["status"] == "ghost_risk"
    result = run(eng.route_inbound(db, p["phone_normalized"],
                 {"type": "text", "text": {"body": "joined sir, aa gaya hoon"}}))
    assert result == "placement"
    assert db.placements.docs[0]["status"] == "joined"
    assert any(e["rel"] == "PLACED" for e in db.edges.docs)


# ══════════════════ 10. analytics funnel ═════════════════════════════════

def test_analytics_funnel():
    db = make_db()
    run(converse(db, HAPPY))                                # completed
    db.candidate_bank.docs.append({**CAND, "id": "c9", "phone": "+91 90000 00001"})
    s2 = run(eng.start_session(db, "c9", "job1", "t@vhc.in"))
    run(eng.handle_session_reply(
        db, run(db.screening_sessions.find_one({"id": s2["id"]})), "haan"))
    run(db.screening_sessions.update_one({"id": s2["id"]},
                                         {"$set": {"state": "stalled"}}))
    sessions = [dict(d) for d in db.screening_sessions.docs]
    f = funnel(sessions)
    assert f["total_sessions"] == 2 and f["completed"] == 1
    assert f["completion_rate"] == 50.0
    ident = next(b for b in f["blocks"] if b["id"] == "identity")
    assert ident["dropped_here"] == 1                       # stalled there


# ══════════════════ 11. web form fallback ════════════════════════════════

def test_form_token_and_render():
    db = make_db()
    session = run(eng.start_session(db, "c1", "job1", "rec@vhc.in"))
    s = run(db.screening_sessions.find_one({"id": session["id"]}))
    tok = make_token(s["id"])
    assert verify_token(s["id"], tok) and not verify_token(s["id"], "wrong")
    html = render_form(s)
    assert "Ventures HRD" in html and 'name="notice"' in html
    rem = remaining_blocks(s)
    assert all(b["kind"] not in ("consent", "identity") for b in rem)
    assert {b["id"] for b in rem} >= {"notice", "experience", "ctc_current"}
