"""
test_screening_logic.py — Asha's brain under deterministic test
================================================================
Runs with AGENT_LLM=0 and AGENT_DRY_RUN=1: no network, no LLM, no Mongo.
A minimal fake async DB implements exactly the operations the engine
uses (find_one / insert_one / update_one with $set·$push·$setOnInsert,
dotted paths, upsert).

    cd backend && python -m pytest tests/test_screening_logic.py -q
"""
import asyncio
import os
import sys

os.environ["AGENT_LLM"] = "0"
os.environ["AGENT_DRY_RUN"] = "1"
os.environ["AGENT_QUALIFY_THRESHOLD"] = "55"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from services import screening_engine as eng  # noqa: E402
from services.screening_script import compile_script, BlockedQuestionError  # noqa: E402


from tests.fakedb import FakeDB  # noqa: E402

# ─────────────────────────────── fixtures ────────────────────────────────
JOB = {
    "id": "job1", "title": "Area Sales Manager", "location": "Pune",
    "min_experience": 5, "max_experience": 10,
    "salary_min": 800000, "salary_max": 1500000,
    "max_notice_days": 60,
    "key_skills": ["Channel Sales", "Distributor Sales", "Retail Sales"],
    "skill_requirements": [
        {"skill_name": "Channel Sales", "must_have": True},
        {"skill_name": "Distributor Sales", "must_have": False},
    ],
}
CAND = {"id": "c1", "name": "Chandrashekar H S", "phone": "+91 98450 12345",
        "key_skills": ["Retail Sales"], "notice_days": None}


def make_db():
    db = FakeDB()
    db.jobs.docs.append(dict(JOB))
    db.candidate_bank.docs.append(dict(CAND))
    return db


async def converse(db, replies):
    """Start a session and play the candidate turn by turn."""
    eng.score_fn = lambda cand, job: {"score": 82}
    session = await eng.start_session(db, "c1", "job1", "test@vhc.in")
    for text in replies:
        s = await db.screening_sessions.find_one({"id": session["id"]})
        if s["state"] not in tuple(eng.ACTIVE_STATES):
            break
        await eng.handle_session_reply(db, s, text)
    return await db.screening_sessions.find_one({"id": session["id"]})


def run(coro):
    return asyncio.run(coro)


# ─────────────────────────────── tests ───────────────────────────────────
def test_script_order_and_consent_first():
    blocks = compile_script(JOB)
    kinds = [b["kind"] for b in blocks]
    assert kinds[0] == "consent" and kinds[1] == "identity"
    # notice has a cap → must come before any skill probe
    assert kinds.index("notice") < kinds.index("skill")
    # must-have skill probes precede nice-to-have
    skill_blocks = [b for b in blocks if b["kind"] == "skill"]
    assert skill_blocks[0]["param"]["skill"] == "Channel Sales"
    assert skill_blocks[0]["must_have"] is True


def test_blocked_custom_question_raises():
    bad = dict(JOB, screening_questions=["Are you married and planning children?"])
    with pytest.raises(BlockedQuestionError):
        compile_script(bad)


def test_happy_path_hinglish_qualified():
    db = make_db()
    final = run(converse(db, [
        "haan",                     # consent
        "ji haan",                  # identity
        "2 mahine ka notice hai",   # notice → 60 (cap 60 → ok)
        "8 saal ka experience",     # experience → 8
        "haan bilkul",              # Channel Sales (must-have) → yes
        "main Pune mein hi hoon",   # location → there
        "haan",                     # Distributor Sales → yes
        "12.5 lakh hai abhi",       # ctc current → 12.5
        "16 LPA chahiye",           # ctc expected → 16 (budget 15, stretch ok)
    ]))
    assert final["state"] == "completed"
    assert final["verdict"] == "QUALIFIED", final.get("disqualifier")
    assert final["score"] == 82
    v = final["verified"]
    assert v["notice_days"] == 60
    assert v["total_experience_years"] == 8.0
    assert v["current_lpa"] == 12.5 and v["expected_lpa"] == 16.0
    assert "Channel Sales" in v["verified_skills"]
    assert v["relocation_status"] == "there"
    assert final["language"] in ("hi", "hinglish")
    # edges: SCREENED + MATCHED_TO
    rels = {e["rel"] for e in db.edges.docs}
    assert rels == {"SCREENED", "MATCHED_TO"}
    # write-back: empty notice_days filled, provenance stamped
    cand = db.candidate_bank.docs[0]
    assert cand["notice_days"] == 60
    assert cand["provenance"]["source"] == "agent_screening"
    # closing message went out
    assert any("recruiter" in t["text"].lower() for t in final["transcript"] if t["dir"] == "out")


def test_must_have_skill_no_overrides_score():
    db = make_db()
    final = run(converse(db, [
        "yes", "yes", "15 days", "7 years",
        "nahi",                    # Channel Sales must-have → no
        "Pune mein hoon", "yes", "9 lakh", "12 lakh",
    ]))
    assert final["verdict"] == "NOT_QUALIFIED"
    assert "Channel Sales" in final["disqualifier"]


def test_notice_cap_disqualifies():
    db = make_db()
    final = run(converse(db, [
        "yes", "yes",
        "3 months",                # 90d > cap 60
        "8 years", "yes", "willing to relocate", "yes", "10 LPA", "13 LPA",
    ]))
    assert final["verdict"] == "NOT_QUALIFIED"
    assert "Notice 90d" in final["disqualifier"]


def test_stop_and_suppression():
    db = make_db()
    final = run(converse(db, ["haan", "yes", "STOP"]))
    assert final["state"] == "opted_out" and final["verdict"] == "OPTED_OUT"
    assert any(e["rel"] == "OPTED_OUT" for e in db.edges.docs)
    # re-push must be refused — v2 raises do_not_contact (phone-keyed
    # registry, catches duplicate candidate records) ahead of opted_out
    with pytest.raises(ValueError, match="do_not_contact|opted_out"):
        run(eng.start_session(db, "c1", "job1", "test@vhc.in"))


def test_consent_declined():
    db = make_db()
    final = run(converse(db, ["no"]))
    assert final["state"] == "opted_out"


def test_human_handoff():
    db = make_db()
    final = run(converse(db, ["yes", "yes", "HUMAN please"]))
    assert final["state"] == "human_handoff"
    assert final["verdict"] == "HUMAN_REQUESTED"


def test_callback_scheduling():
    db = make_db()
    final = run(converse(db, ["yes", "yes", "kal baat karte hain"]))
    assert final["state"] == "callback"
    task = db.screening_tasks.docs[0]
    assert task["state"] == "queued" and task["next_attempt_at"] is not None


def test_clarify_then_advance_on_garbage():
    db = make_db()
    final = run(converse(db, [
        "yes", "yes",
        "hmm",                     # notice unparseable → clarify (ask 2)
        "dekhte hain",             # still unparseable → stored raw, advance
        "6 years", "yes", "Pune", "yes", "8 lakh", "10 lakh",
    ]))
    assert final["state"] == "completed"
    a = final["answers"]["notice"]
    assert a["value"] is None and a["confident"] is False and a["asks"] == 2
    # notice unknown → cap can't disqualify; must-haves yes; score 82 → qualified
    assert final["verdict"] == "QUALIFIED"


def test_writeback_never_overwrites_human_value():
    db = make_db()
    db.candidate_bank.docs[0]["notice_days"] = 30           # human-entered
    db.candidate_bank.docs[0]["provenance"] = {"source": "recruiter"}
    run(converse(db, [
        "yes", "yes", "2 months", "Pune", "8 years",
        "yes", "yes", "10 lakh", "12 lakh",
    ]))
    assert db.candidate_bank.docs[0]["notice_days"] == 30    # untouched
