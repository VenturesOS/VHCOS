"""
agent.py — Asha's HTTP surface (v2)
===================================

Screening (v1):
  POST /api/agent/push · GET /sessions · GET /sessions/{id}
  POST /sessions/{id}/reverse · POST /simulate/{id} · GET /config
v2:
  POST /push-bulk                      bulk push with cap-aware queueing
  POST /push-docs                      start a document-collection flow
  POST /sessions/{id}/takeover|send|resume    live human takeover
  GET  /sessions/{id}/submission-note  client-ready DOCX download
  GET  /analytics                      drop-off funnel per mandate
  GET/POST/DELETE /slots               interview slot pools (recruiter)
  GET  /interviews                     booked interviews per mandate
  POST /placements · GET /placements   joining shepherd
  POST /placements/{id}/status         mark joined/dropped
  GET/POST /form/{sid}/{token}         public web-form fallback (HMAC)
  POST /run-worklist|run-sweeps|run-report|run-refresh   manual (admin)
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from config import db
from utils.auth import get_current_user, require_role
from models.neural_schema import utcnow
from services import screening_engine, screening_tasks
from services import screening_analytics, screening_forms, screening_joining
from services.screening_whatsapp import dry_run

logger = logging.getLogger(__name__)

agent_router = APIRouter(prefix="/api/agent", tags=["Asha Agent"])

STAFF = Depends(require_role(["admin", "recruiter"]))
ADMIN = Depends(require_role(["admin"]))

_LIST_PROJECTION = {
    "_id": 0, "id": 1, "flow": 1, "candidate_id": 1, "candidate_name": 1,
    "mandate_id": 1, "mandate_title": 1, "state": 1, "verdict": 1,
    "score": 1, "disqualifier": 1, "language": 1, "idx": 1, "pending": 1,
    "created_at": 1, "updated_at": 1, "completed_at": 1, "verified": 1,
}


# ═══════════════════════════ push (single · bulk · docs) ═════════════════

class PushRequest(BaseModel):
    candidate_id: str
    mandate_id: str


async def _queue_task(candidate_id: str, mandate_id: Optional[str], who: str,
                      flow: str = "screening", docs: Optional[List[str]] = None,
                      priority: int = 5) -> None:
    await db.screening_tasks.update_one(
        {"candidate_id": candidate_id, "mandate_id": mandate_id, "flow": flow,
         "state": {"$in": ["queued", "active"]}},
        {"$setOnInsert": {"id": str(uuid.uuid4()), "candidate_id": candidate_id,
                          "mandate_id": mandate_id, "flow": flow,
                          "docs_requested": docs, "state": "queued",
                          "attempts": 0, "priority": priority,
                          "next_attempt_at": None, "created_by": who,
                          "created_at": utcnow()},
         "$set": {"updated_at": utcnow()}},
        upsert=True)


@agent_router.post("/push")
async def push(req: PushRequest, current_user: dict = STAFF):
    who = current_user.get("email", "recruiter")
    if screening_tasks._enabled() and screening_tasks._in_window():
        try:
            session = await screening_engine.start_session(db, req.candidate_id, req.mandate_id, who)
            return {"success": True, "mode": "started", "session_id": session["id"]}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    await _queue_task(req.candidate_id, req.mandate_id, who)
    return {"success": True, "mode": "queued",
            "note": "Agent disabled or outside contact hours — queued for next worklist run."}


class BulkPushRequest(BaseModel):
    candidate_ids: List[str]
    mandate_id: str


@agent_router.post("/push-bulk")
async def push_bulk(req: BulkPushRequest, current_user: dict = STAFF):
    """Push many candidates; starts within caps, queues the rest, and
    reports every skip with its reason."""
    who = current_user.get("email", "recruiter")
    started, queued, skipped = [], [], []
    live = screening_tasks._enabled() and screening_tasks._in_window()
    budget = await screening_tasks._budget(db) if live else 0
    for cid in req.candidate_ids[:500]:
        if live and budget > 0:
            try:
                s = await screening_engine.start_session(db, cid, req.mandate_id, who)
                started.append(s["id"])
                budget -= 1
                continue
            except ValueError as e:
                if str(e) in ("do_not_contact", "opted_out", "consent_revoked",
                              "no_phone", "candidate_not_found"):
                    skipped.append({"candidate_id": cid, "reason": str(e)})
                    continue
        await _queue_task(cid, req.mandate_id, who)
        queued.append(cid)
    return {"success": True, "started": len(started), "queued": len(queued),
            "skipped": skipped}


class DocsPushRequest(BaseModel):
    candidate_id: str
    documents: List[str]  # keys from screening_flows.DOC_LABELS
    mandate_id: Optional[str] = None


@agent_router.post("/push-docs")
async def push_docs(req: DocsPushRequest, current_user: dict = STAFF):
    who = current_user.get("email", "recruiter")
    if screening_tasks._enabled() and screening_tasks._in_window():
        try:
            s = await screening_engine.start_session(
                db, req.candidate_id, req.mandate_id, who,
                flow="docs", docs_requested=req.documents)
            return {"success": True, "mode": "started", "session_id": s["id"]}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    await _queue_task(req.candidate_id, req.mandate_id, who, flow="docs",
                      docs=req.documents)
    return {"success": True, "mode": "queued"}


# ═══════════════════════════ sessions ════════════════════════════════════

@agent_router.get("/sessions")
async def list_sessions(
    mandate_id: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    verdict: Optional[str] = Query(default=None),
    flow: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict = STAFF,
):
    q = {}
    if mandate_id:
        q["mandate_id"] = mandate_id
    if state:
        q["state"] = state
    if verdict:
        q["verdict"] = verdict
    if flow:
        q["flow"] = flow
    cursor = (db.screening_sessions.find(q, _LIST_PROJECTION)
              .sort("updated_at", -1).skip((page - 1) * limit).limit(limit))
    items = await cursor.to_list(length=limit)
    total = await db.screening_sessions.count_documents(q)
    return {"success": True, "sessions": items, "total": total, "page": page}


@agent_router.get("/sessions/{session_id}")
async def get_session(session_id: str, current_user: dict = STAFF):
    s = await db.screening_sessions.find_one({"id": session_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True, "session": s}


@agent_router.post("/sessions/{session_id}/reverse")
async def reverse_verdict(session_id: str, current_user: dict = STAFF):
    s = await db.screening_sessions.find_one({"id": session_id})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if s.get("verdict") != "NOT_QUALIFIED":
        raise HTTPException(status_code=400, detail="Only NOT_QUALIFIED sessions can be reversed")
    who = current_user.get("email", "recruiter")
    await db.screening_sessions.update_one(
        {"id": session_id},
        {"$set": {"verdict": "QUALIFIED", "reversed_by": who,
                  "reversed_at": utcnow(), "updated_at": utcnow()}})
    await db.edges.insert_one({
        "src": f"cand:{s['candidate_id']}", "src_type": "candidate",
        "rel": "MATCHED_TO", "dst": f"mandate:{s['mandate_id']}", "dst_type": "mandate",
        "weight": (s.get("score") or 0) / 100,
        "evidence": f"asha:{session_id}:reversed_by:{who}",
        "created_at": utcnow(), "updated_at": utcnow()})
    return {"success": True, "verdict": "QUALIFIED", "reversed_by": who}


# ═══════════════════════════ human takeover ══════════════════════════════

@agent_router.post("/sessions/{session_id}/takeover")
async def takeover(session_id: str, current_user: dict = STAFF):
    s = await db.screening_sessions.find_one({"id": session_id})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if s["state"] not in ("consent", "active", "callback"):
        raise HTTPException(status_code=400, detail=f"Session is {s['state']}")
    who = current_user.get("email", "recruiter")
    await db.screening_sessions.update_one(
        {"id": session_id},
        {"$set": {"state": "human_live", "taken_over_by": who,
                  "pending": None, "updated_at": utcnow()}})
    return {"success": True, "state": "human_live"}


class TakeoverSend(BaseModel):
    text: str


@agent_router.post("/sessions/{session_id}/send")
async def takeover_send(session_id: str, req: TakeoverSend, current_user: dict = STAFF):
    s = await db.screening_sessions.find_one({"id": session_id})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if s["state"] != "human_live":
        raise HTTPException(status_code=400, detail="Take over the session first")
    who = current_user.get("email", "recruiter")
    await screening_engine._out(db, s, req.text, agent=f"human:{who}")
    return {"success": True}


@agent_router.post("/sessions/{session_id}/resume")
async def takeover_resume(session_id: str, current_user: dict = STAFF):
    s = await db.screening_sessions.find_one({"id": session_id})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if s["state"] != "human_live":
        raise HTTPException(status_code=400, detail="Session is not in takeover")
    await screening_engine.resume_session(db, s)
    return {"success": True, "state": "active"}


# ═══════════════════════ submission note (DOCX) ══════════════════════════

@agent_router.get("/sessions/{session_id}/submission-note")
async def submission_note(session_id: str, current_user: dict = STAFF):
    s = await db.screening_sessions.find_one({"id": session_id})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if s.get("state") != "completed":
        raise HTTPException(status_code=400, detail="Session not completed yet")
    candidate = await db.candidate_bank.find_one({"id": s["candidate_id"]}) or {}
    job = await db.jobs.find_one({"id": s["mandate_id"]}) or {}
    from services.submission_note import build_submission_note
    try:
        path = build_submission_note(candidate, s, job)
    except Exception as e:
        logger.error("[Asha] submission note failed: %s", e)
        raise HTTPException(status_code=500, detail="DOCX generation failed — is python-docx installed?")
    return FileResponse(path, filename=path.split("/")[-1],
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


# ═══════════════════════════ analytics ═══════════════════════════════════

@agent_router.get("/analytics")
async def analytics(mandate_id: Optional[str] = Query(default=None),
                    flow: str = Query(default="screening"),
                    current_user: dict = STAFF):
    q = {"flow": flow}
    if mandate_id:
        q["mandate_id"] = mandate_id
    sessions = await db.screening_sessions.find(q).to_list(length=2000)
    return {"success": True, "funnel": screening_analytics.funnel(sessions)}


# ═══════════════════════ interview slots + interviews ════════════════════

class SlotCreate(BaseModel):
    mandate_id: str
    start: datetime
    duration_min: int = 30
    capacity: int = 1
    mode: str = "phone"          # phone | video | office
    details: Optional[str] = None


@agent_router.post("/slots")
async def create_slot(req: SlotCreate, current_user: dict = STAFF):
    slot = {"id": str(uuid.uuid4()), **req.model_dump(),
            "booked_count": 0, "created_by": current_user.get("email"),
            "created_at": utcnow(), "updated_at": utcnow()}
    await db.interview_slots.insert_one(dict(slot))
    slot.pop("_id", None)
    return {"success": True, "slot": slot}


@agent_router.get("/slots")
async def list_slots(mandate_id: str = Query(...), current_user: dict = STAFF):
    slots = await (db.interview_slots.find({"mandate_id": mandate_id}, {"_id": 0})
                   .sort("start", 1).to_list(length=100))
    return {"success": True, "slots": slots}


@agent_router.delete("/slots/{slot_id}")
async def delete_slot(slot_id: str, current_user: dict = STAFF):
    slot = await db.interview_slots.find_one({"id": slot_id})
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if slot.get("booked_count", 0) > 0:
        raise HTTPException(status_code=400,
                            detail="Slot has bookings — cancel those interviews first")
    await db.interview_slots.update_one({"id": slot_id}, {"$set": {"deleted": True}})
    await db.interview_slots.delete_one({"id": slot_id}) if hasattr(db.interview_slots, "delete_one") else None
    return {"success": True}


@agent_router.get("/interviews")
async def list_interviews(mandate_id: Optional[str] = Query(default=None),
                          current_user: dict = STAFF):
    q = {}
    if mandate_id:
        q["mandate_id"] = mandate_id
    items = await (db.interviews.find(q, {"_id": 0}).sort("start", 1).to_list(length=200))
    return {"success": True, "interviews": items}


# ═══════════════════════ placements (joining shepherd) ═══════════════════

class PlacementCreate(BaseModel):
    candidate_id: str
    mandate_id: str
    joining_date: datetime


@agent_router.post("/placements")
async def create_placement(req: PlacementCreate, current_user: dict = STAFF):
    try:
        p = await screening_joining.create_placement(
            db, req.candidate_id, req.mandate_id, req.joining_date,
            current_user.get("email", "recruiter"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    p.pop("_id", None)
    return {"success": True, "placement": p}


@agent_router.get("/placements")
async def list_placements(status: Optional[str] = Query(default=None),
                          current_user: dict = STAFF):
    q = {"status": status} if status else {}
    items = await (db.placements.find(q, {"_id": 0})
                   .sort("joining_date", 1).to_list(length=200))
    return {"success": True, "placements": items}


class PlacementStatus(BaseModel):
    status: str  # joined | dropped | confirmed


@agent_router.post("/placements/{placement_id}/status")
async def set_placement_status(placement_id: str, req: PlacementStatus,
                               current_user: dict = STAFF):
    if req.status not in ("joined", "dropped", "confirmed"):
        raise HTTPException(status_code=400, detail="Invalid status")
    p = await db.placements.find_one({"id": placement_id})
    if not p:
        raise HTTPException(status_code=404, detail="Placement not found")
    await db.placements.update_one(
        {"id": placement_id},
        {"$set": {"status": req.status, "updated_at": utcnow(),
                  "status_set_by": current_user.get("email")}})
    if req.status == "joined":
        await db.edges.insert_one({
            "src": f"cand:{p['candidate_id']}", "src_type": "candidate",
            "rel": "PLACED", "dst": f"mandate:{p['mandate_id']}", "dst_type": "mandate",
            "weight": 1.0, "evidence": f"placement:{placement_id}",
            "created_at": utcnow(), "updated_at": utcnow()})
    return {"success": True, "status": req.status}


# ═══════════════ public web-form fallback (HMAC token) ═══════════════════

@agent_router.get("/form/{session_id}/{token}", response_class=HTMLResponse)
async def form_get(session_id: str, token: str):
    if not screening_forms.verify_token(session_id, token):
        raise HTTPException(status_code=403, detail="Invalid link")
    s = await db.screening_sessions.find_one({"id": session_id})
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    if s["state"] in ("opted_out",):
        raise HTTPException(status_code=410, detail="This link is no longer active")
    return HTMLResponse(screening_forms.render_form(s))


@agent_router.post("/form/{session_id}/{token}", response_class=HTMLResponse)
async def form_post(session_id: str, token: str, request: Request):
    if not screening_forms.verify_token(session_id, token):
        raise HTTPException(status_code=403, detail="Invalid link")
    s = await db.screening_sessions.find_one({"id": session_id})
    if not s or s["state"] in ("opted_out",):
        raise HTTPException(status_code=410, detail="This link is no longer active")
    form = await request.form()
    blocks = {b["id"]: b for b in s.get("blocks") or []}
    for bid, raw in form.items():
        b = blocks.get(bid)
        raw = str(raw).strip()
        if not b or not raw:
            continue
        ans = await screening_engine.extract_answer(b, raw)
        s["answers"][bid] = {"raw": raw, "value": ans["value"],
                             "confident": ans["confident"], "asks": 1,
                             "via": "web_form"}
        await db.screening_sessions.update_one(
            {"id": session_id}, {"$set": {f"answers.{bid}": s["answers"][bid]}})
    # complete if everything answerable is in
    if not screening_forms.remaining_blocks(s):
        s["idx"] = len(s.get("blocks") or [])
        await db.screening_sessions.update_one(
            {"id": session_id}, {"$set": {"idx": s["idx"], "state": "active"}})
        s["state"] = "active"
        await screening_engine._complete(db, s)
    return HTMLResponse(screening_forms.THANKYOU_HTML)


# ═══════════════════════════ simulate + ops ══════════════════════════════

class SimulateRequest(BaseModel):
    text: str


@agent_router.post("/simulate/{session_id}")
async def simulate(session_id: str, req: SimulateRequest, current_user: dict = STAFF):
    if not dry_run():
        raise HTTPException(status_code=403, detail="Simulator requires AGENT_DRY_RUN=1")
    s = await db.screening_sessions.find_one({"id": session_id})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if s["state"] not in ("consent", "active", "callback", "human_live", "awaiting_choice"):
        raise HTTPException(status_code=400, detail=f"Session is {s['state']}")
    await screening_engine.handle_session_reply(db, s, req.text)
    fresh = await db.screening_sessions.find_one({"id": session_id}, {"_id": 0})
    last_out = next((t["text"] for t in reversed(fresh.get("transcript", []))
                     if t["dir"] == "out"), None)
    return {"success": True, "state": fresh["state"], "verdict": fresh.get("verdict"),
            "score": fresh.get("score"), "pending": fresh.get("pending"),
            "asha_said": last_out}


@agent_router.post("/run-worklist")
async def manual_worklist(current_user: dict = ADMIN):
    return await screening_tasks.run_worklist(db)


@agent_router.post("/run-sweeps")
async def manual_sweeps(current_user: dict = ADMIN):
    return await screening_tasks.run_sweeps(db)


@agent_router.post("/run-refresh")
async def manual_refresh(current_user: dict = ADMIN):
    return await screening_tasks.run_refresh_batch(db)


@agent_router.post("/run-report")
async def manual_report(current_user: dict = ADMIN):
    return await screening_tasks.run_evening_report(db)


@agent_router.get("/config")
async def config_echo(current_user: dict = STAFF):
    return {
        "enabled": screening_tasks._enabled(),
        "dry_run": dry_run(),
        "in_window": screening_tasks._in_window(),
        "caps": screening_tasks._caps(),
        "llm": os.environ.get("AGENT_LLM", "1"),
        "stt": os.environ.get("AGENT_STT", "0"),
        "auto_schedule": os.environ.get("AGENT_AUTO_SCHEDULE", "1"),
        "cross_offer": os.environ.get("AGENT_CROSS_OFFER", "1"),
        "joining": os.environ.get("AGENT_JOINING", "1"),
        "referral": os.environ.get("AGENT_REFERRAL", "0"),
        "email_fallback": os.environ.get("AGENT_EMAIL_FALLBACK", "0"),
        "refresh_daily_cap": os.environ.get("AGENT_REFRESH_DAILY_CAP", "0"),
        "qualify_threshold": screening_engine.QUALIFY_THRESHOLD,
    }
