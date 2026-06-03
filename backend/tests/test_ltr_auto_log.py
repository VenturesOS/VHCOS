"""
Regression: LTR server-side auto-capture (Option B).

`auto_log_action()` attaches a high-signal action (shortlist / contact /
reject / hire) to the user's most recent search_session — no frontend
wiring required. Verifies:
  1. Action appended to the most recent session within the lookback window.
  2. Rank is captured when the candidate is in that session's slate.
  3. Rank stays None when the candidate is NOT in the slate.
  4. Stale sessions (>1h old) are NOT used.
  5. No session → graceful False, no exception.
  6. STAGE_TO_LTR_ACTION mapping is complete for the stages we actually
     dispatch from routes/applications.py.

Note: Motor binds to the event loop that creates the client. We therefore
run ALL async assertions inside a single asyncio.run() (one event loop for
the whole module) instead of one per test.
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta

from config import db, initialize_db

initialize_db()

from services.ltr_telemetry import (  # noqa: E402
    STAGE_TO_LTR_ACTION,
    auto_log_action,
    log_slate,
)


def _user():
    return {"id": f"u-{uuid.uuid4().hex[:8]}", "email": "test@vhc.in", "role": "recruiter"}


async def _seed_session(user, slate, ts=None):
    sid = await log_slate(
        user=user,
        source="talent_graph_search",
        query="python developer",
        slate=slate,
    )
    if ts is not None:
        await db.search_sessions.update_one({"id": sid}, {"$set": {"ts": ts}})
    return sid


def test_auto_log_end_to_end():
    """Single end-to-end async block — keeps one event loop alive for Motor."""

    async def _run_all():
        # ── 1. Attaches to recent session + records rank ──
        user = _user()
        cid = f"cand-{uuid.uuid4().hex[:8]}"
        sid = await _seed_session(user, [{"candidate_id": cid, "score": 0.8}])

        ok = await auto_log_action(user=user, candidate_id=cid, action="shortlist")
        assert ok is True
        sess = await db.search_sessions.find_one({"id": sid}, {"_id": 0})
        actions = sess["actions"]
        assert len(actions) == 1
        assert actions[0]["candidate_id"] == cid
        assert actions[0]["action"] == "shortlist"
        assert actions[0]["rank"] == 0

        # ── 2. No rank when candidate is outside the slate ──
        user2 = _user()
        sid2 = await _seed_session(user2, [{"candidate_id": "in-slate", "score": 0.8}])
        ok = await auto_log_action(user=user2, candidate_id="off-slate", action="reject")
        assert ok is True
        sess2 = await db.search_sessions.find_one({"id": sid2}, {"_id": 0})
        assert len(sess2["actions"]) == 1
        assert sess2["actions"][0]["action"] == "reject"
        assert "rank" not in sess2["actions"][0]

        # ── 3. Stale sessions (>1h) are ignored ──
        user3 = _user()
        stale_ts = datetime.now(timezone.utc) - timedelta(hours=3)
        cid3 = f"cand-{uuid.uuid4().hex[:8]}"
        sid3 = await _seed_session(user3, [{"candidate_id": cid3, "score": 0.8}], ts=stale_ts)
        ok = await auto_log_action(user=user3, candidate_id=cid3, action="shortlist")
        assert ok is False
        sess3 = await db.search_sessions.find_one({"id": sid3}, {"_id": 0})
        assert sess3["actions"] == []

        # ── 4. No session → False, never raises ──
        user4 = _user()
        ok = await auto_log_action(user=user4, candidate_id="any-id", action="shortlist")
        assert ok is False

        # ── 5. Missing fields → False ──
        assert await auto_log_action(user=None, candidate_id="x", action="shortlist") is False
        assert await auto_log_action(user=user4, candidate_id="", action="shortlist") is False
        assert await auto_log_action(user=user4, candidate_id="x", action="") is False

        # ── 6. Cleanup: drop the test sessions we created ──
        await db.search_sessions.delete_many({"user_email": "test@vhc.in"})

    asyncio.run(_run_all())


def test_stage_to_ltr_action_covers_real_stages():
    """The mapping must cover every stage routes/applications.py emits."""
    required = {"shortlisted", "interview", "offered", "hired", "joined", "rejected", "dropped"}
    missing = required - set(STAGE_TO_LTR_ACTION.keys())
    assert not missing, f"Stages missing from STAGE_TO_LTR_ACTION: {missing}"
