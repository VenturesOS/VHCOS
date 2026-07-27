# Asha v1.0.1 — Deployment Guide

> **v2.0.0 available** — see `ASHA_V2_UPGRADE.md`. The webhook patch in
> §4 there **replaces** the one in this file; everything else here
> (routers, Meta setup, env basics) still applies.

> v1.0.1 (post code review): scheduler jobs registered via
> functools.partial (v1.0.0 lambdas were never awaited — jobs silently
> no-oped), all /api/agent endpoints gated to admin/recruiter roles, and
> webhook processing deduped by wamid with supporting indexes.

Everything in this package is additive and ships OFF by default
(AGENT_ENABLED=0, AGENT_DRY_RUN=1). The test suite runs with no network,
no LLM, and no Mongo: `cd backend && python -m pytest tests/test_screening_logic.py -q`
— 11 tests covering the full conversation lifecycle.

## 1. Files → repo (paths mirror the package)

```
backend/models/neural_schema.py            # canonical models + parsers (Phase 9)
backend/routes/extension_preview.py        # scoring source (Phase 8 — if not already deployed)
backend/routes/agent.py                    # Asha HTTP surface
backend/services/screening_script.py       # mandate → question flow
backend/services/screening_engine.py       # dialogue state machine
backend/services/screening_llm.py          # phrasing/extraction adapter
backend/services/screening_whatsapp.py     # outbound free-form sends
backend/services/screening_tasks.py        # worklist · nudges · report
backend/scripts/seed_ontology.py           # Phase 9 dictionaries
backend/tests/test_screening_logic.py
frontend/src/components/agent/AgentScreeningPanel.jsx
frontend/src/components/agent/ScreenWithAshaButton.jsx
```

## 2. server.py registration (same _safe_import pattern)

```python
agent_router = _safe_import("routes.agent", "agent_router")
extension_preview_router = _safe_import("routes.extension_preview", "extension_preview_router")  # if not already
```
…and add both names to the same include list that registers
`extension_router` (they mount under /api like the rest).

## 3. Inbound WhatsApp — patch routes/whatsapp_webhook.py

The webhook currently processes only delivery **statuses**. Add message
handling inside `receive()`:

**Before**
```python
    updates = 0
    for entry in (payload.get("entry") or []):
        for change in (entry.get("changes") or []):
            value = change.get("value") or {}
            statuses = value.get("statuses") or []
            if statuses:
                updates += await update_status_from_webhook(db, statuses)
    return {"status": "ok", "updates": updates}
```

**After**
```python
    updates = 0
    handled = 0
    for entry in (payload.get("entry") or []):
        for change in (entry.get("changes") or []):
            value = change.get("value") or {}
            statuses = value.get("statuses") or []
            if statuses:
                updates += await update_status_from_webhook(db, statuses)

            # ── Asha: route candidate replies into active sessions ──
            for msg in (value.get("messages") or []):
                if msg.get("type") != "text":
                    continue
                from models.neural_schema import normalize_phone, utcnow
                from services.screening_engine import handle_inbound
                # Meta redelivers on timeout/non-2xx — dedupe by wamid
                wamid = msg.get("id")
                if wamid:
                    try:
                        await db.wa_processed_messages.insert_one(
                            {"wamid": wamid, "created_at": utcnow()})
                    except Exception:      # DuplicateKeyError → already handled
                        continue
                phone = normalize_phone(msg.get("from") or "")
                body = ((msg.get("text") or {}).get("body") or "").strip()
                if phone and body:
                    try:
                        if await handle_inbound(db, phone, body):
                            handled += 1
                    except Exception as e:
                        logger.error(f"[Asha] inbound failed: {e}")
    return {"status": "ok", "updates": updates, "asha_handled": handled}
```
Replies with no active session fall through untouched — existing
behavior is preserved. Also subscribe the **messages** webhook field in
the Meta app dashboard (statuses alone won't deliver texts).

## 4. Scheduler — services/lifecycle.py (3 lines, next to existing add_job calls)

```python
from services.screening_tasks import register_agent_jobs, ensure_agent_indexes
await ensure_agent_indexes(db)       # hot-path indexes + webhook dedupe store
register_agent_jobs(scheduler, db)   # 09:30 IST worklist · 30-min nudges · 19:15 IST report
```
No scheduler change needed to test: POST /api/agent/run-worklist and
/run-report (admin) trigger the same functions.

## 5. Environment

| Var | Default | Meaning |
|---|---|---|
| AGENT_ENABLED | 0 | master switch for dispatch/nudges |
| AGENT_DRY_RUN | 1 | 1 = no real WhatsApp sends; simulator allowed |
| AGENT_LLM | 1 | 0 = fully deterministic (templates + parsers) |
| GROQ_API_KEY / AGENT_LLM_API_KEY | — | phrasing + extraction fallback |
| AGENT_LLM_MODEL | llama-3.3-70b-versatile | any OpenAI-compatible chat model |
| AGENT_MAX_ACTIVE_CONVERSATIONS | 25 | concurrency cap |
| AGENT_DAILY_CONTACT_CAP | 100 | new sessions per day |
| AGENT_HOURS | 10-19 | IST contact window |
| AGENT_QUALIFY_THRESHOLD | 55 | min match % for QUALIFIED |
| AGENT_INTRO_TEMPLATE | — | Meta utility template for first contact |
| WHATSAPP_ACCESS_TOKEN / _PHONE_NUMBER_ID / _API_VERSION / _ADMIN_NUMBERS | existing | reused from digest service |

## 6. Dry-run walkthrough (do this before anything real)

```bash
# 1. push a candidate (any recruiter token)
curl -X POST $API/api/agent/push -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' \
  -d '{"candidate_id":"<real id>","mandate_id":"<real job id>"}'
# → {"mode":"queued"}  (AGENT_ENABLED=0)  — flip AGENT_ENABLED=1 within
#   10:00–19:00 IST and push again → {"mode":"started","session_id":"..."}
# (AGENT_DRY_RUN=1 means the consent message is logged, not sent)

# 2. play the candidate
curl -X POST $API/api/agent/simulate/<session_id> -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' -d '{"text":"haan"}'
# → asha_said: identity question. Continue: "ji haan",
#   "2 mahine ka notice hai", "8 saal", "haan", "Pune mein hoon",
#   "haan", "12.5 lakh", "16 LPA"
# final response → {"state":"completed","verdict":"QUALIFIED","score":...}

# 3. verify write-back + edges in mongosh
db.candidate_bank.findOne({id:"<id>"},{notice_days:1,current_lpa:1,provenance:1})
db.edges.find({src:"cand:<id>"})

# 4. evening report shape
curl -X POST $API/api/agent/run-report -H "Authorization: Bearer $ADMIN_TOK"
```

## 7. Frontend mounting

Mandate/job detail page — add a tab:
```jsx
import AgentScreeningPanel from '@/components/agent/AgentScreeningPanel';
<AgentScreeningPanel mandateId={job.id} />
```
Candidate bank rows/detail (mandate context available):
```jsx
import ScreenWithAshaButton from '@/components/agent/ScreenWithAshaButton';
<ScreenWithAshaButton candidateId={c.id} mandateId={activeMandateId} />
```

## 8. Go-live checklist (in order)

1. Deploy with defaults (ENABLED=0, DRY_RUN=1) → run §6 end to end.
2. Meta app: subscribe `messages` webhook field; register utility
   template `asha_screening_intro` (body = one text variable) and set
   AGENT_INTRO_TEMPLATE once approved.
3. Pick ONE live mandate. Set AGENT_ENABLED=1, keep DRY_RUN=1 for a day
   — watch the worklist/nudge logs behave.
4. AGENT_DRY_RUN=0 with AGENT_DAILY_CONTACT_CAP=10. Team reviews every
   transcript in the Agent Screening tab for 3–4 days.
5. Raise caps gradually. The evening report is your daily quality gate.

## 9. Honest v1 limits

Nudge state is evaluated in the 30-min cron, so "+4 working hours" is
approximate near window edges. The evening WhatsApp to admins delivers
only inside an open 24h window per admin (the report is always stored in
`agent_reports` regardless — surface it in the admin UI or email next).
`FakeDB` in tests covers the engine's operations, not the task engine's
cursor queries — task-engine behavior is exercised via the manual
trigger endpoints in dry-run. And skill "adjacency" awaits Phase 9's
promoted ontology + v2 embeddings; v1 skill probes are yes/no.
