# Asha v2.0.0 — Upgrade Guide

> Read `ASHA_DEPLOYMENT.md` first for the v1 wiring (routers, env, Meta
> setup). This document covers everything v2 adds, and **replaces the v1
> webhook patch** — the inbound handler changes.
>
> Test status: `cd backend && python -m pytest tests/` → **28 passed**
> (11 v1 regression + 17 v2). Zero live dependencies in tests
> (`AGENT_LLM=0`, `AGENT_DRY_RUN=1`).

---

## 1. What v2 adds

| # | Feature | Where |
|---|---------|-------|
| 1 | **Do-not-contact registry** — STOP writes a *phone-keyed* registry; every duplicate record of the same human is suppressed on push | `screening_engine` · `agent_do_not_contact` |
| 2 | **FAQ interrupts** — candidate asks "salary kitni hai?" mid-flow; Asha answers from a mandate whitelist (never invents, never reveals confidential clients) and re-asks the pending question | `screening_flows.answer_faq` |
| 3 | **Interview scheduling** — recruiter posts slot pools; QUALIFIED candidates pick 1/2/3 (or "pehla wala"/"wednesday"); atomic capacity-guarded booking; T-24h and T-2h WhatsApp reminders; RESCHEDULE reopens the offer and releases the seat | `screening_scheduling` · `/agent/slots` |
| 4 | **Cross-mandate offer** — a NOT_QUALIFIED candidate who genuinely fits another live mandate gets *one* respectful alternative; on "haan", a new session starts with **carried answers** (notice/CTC/experience never re-asked) | `screening_flows.find_alternative` |
| 5 | **Voice notes** — Groq Whisper transcription (`AGENT_STT=1`), transcript flows through the same state machine; graceful "please type" fallback when off | `screening_media.transcribe_voice` |
| 6 | **Document collection flow** — request updated CV / photo / certs; attachments land in R2, candidate gets `needs_reparse: true` for your CV pipeline | flow=`docs` · `/agent/push-docs` |
| 7 | **Human takeover** — recruiter takes the mic mid-conversation (Asha goes silent), types from the panel, resumes Asha with one click | `/takeover` `/send` `/resume` · state `human_live` |
| 8 | **Submission note** — one-page client-ready DOCX per completed screening (verified facts + provenance) | `/sessions/{id}/submission-note` |
| 9 | **Bulk push** — up to 500 candidates per call; starts within caps, queues the rest, reports every skip with its reason | `/agent/push-bulk` |
| 10 | **Drop-off analytics** — per-block asked/answered/dropped funnel, language split, completion rate; rendered in the panel | `/agent/analytics` |
| 11 | **Stale-profile refresh** — nightly batch re-verifies profiles untouched for `AGENT_REFRESH_MONTHS`; write-back with `agent_refresh` provenance; "open to opportunities?" chains a queued screening against the best live mandate | flow=`refresh` · `run_refresh_batch` |
| 12 | **Joining shepherd** — post-offer T-7/T-3/T-1/Day-0 touchpoints; worried replies flag `ghost_risk` (surfaced in the evening report); "joined" writes the `PLACED` edge | `screening_joining` · `/agent/placements` |
| 13 | **Email + web-form fallback** — stalled sessions get one email with an HMAC-tokenized form completing the same session (no login, no PII in URL beyond the opaque token) | `screening_email` · `/agent/form/…` |
| 14 | **LTR label export** — every screening becomes a labeled (candidate, mandate) pair in `ltr_telemetry` (QUALIFIED→shortlist, NOT_QUALIFIED→reject, PLACED→contact) for the ranking model | `scripts/export_ltr_labels.py` |

Design-only in this release (deliberately — see §7): WhatsApp Flows
native forms, conversational client mandate-intake.

---

## 2. Files in this package

```
backend/
  models/neural_schema.py               (v1, unchanged)
  services/
    screening_script.py                 (v1, unchanged)
    screening_llm.py                    (v1, unchanged)
    screening_whatsapp.py               (v1, unchanged)
    screening_engine.py                 ★ v2 rewrite
    screening_tasks.py                  ★ v2 rewrite
    screening_flows.py                  ★ new
    screening_scheduling.py             ★ new
    screening_media.py                  ★ new
    screening_joining.py                ★ new
    screening_analytics.py              ★ new
    screening_forms.py                  ★ new
    screening_email.py                  ★ new
    submission_note.py                  ★ new
  routes/
    agent.py                            ★ v2 rewrite
    extension_preview.py                (Phase 8, unchanged)
  scripts/
    seed_ontology.py                    (v1, unchanged)
    export_ltr_labels.py                ★ new
  tests/
    fakedb.py · test_screening_logic.py · test_screening_v2.py
  requirements-agent.txt                (python-docx)
frontend/src/components/agent/
  ScreenWithAshaButton.jsx              (v1, unchanged)
  AgentScreeningPanel.jsx               ★ v2 rewrite (takeover · funnel · note)
  InterviewSlotsCard.jsx                ★ new
  BulkScreenButton.jsx                  ★ new
docs/  ASHA_DEPLOYMENT.md (v1) · ASHA_V2_UPGRADE.md (this file)
       VIRTUAL_RECRUITER_BLUEPRINT.md · CODE_REVIEW_ASHA_V1.md
       PHASE_8_HOVER_PREVIEW.md (extension backend + relay notes)
extension/                              ★ Chrome extension v6.1.2
  manifest.json · background.js · content.js · content.css
  hover-preview.js · popup.html · popup.js · icons/
```

**Chrome extension (v6.1.2, "test file 3" build):** the Naukri Resdex
capture extension with the Phase 8 hover-preview — hovering a captured
candidate shows the weighted fit score against the active mandate,
served by `backend/routes/extension_preview.py` (already registered in
§3's router include if you mount it alongside `agent_router`). Load via
`chrome://extensions` → Developer mode → *Load unpacked* → the
`extension/` folder. **Known pending item:** the Cloudflare Worker relay
(`talent-relay.…workers.dev`) still 404s the `/extension/candidate-preview`
and candidate-bank paths until its allowlist is patched — hover-preview
works against a direct API base but not through the relay yet
(`PHASE_8_HOVER_PREVIEW.md` has the details).

Everything is **additive** — no existing VHCOS file is modified. The two
integration points below are the same ones v1 used.

---

## 3. server.py — router registration (unchanged from v1)

```python
from routes.agent import agent_router
api_router.include_router(agent_router)      # next to the other routers
```

`pip install python-docx` (or `pip install -r requirements-agent.txt`)
on the backend — the submission note needs it. Everything else uses
libraries already in your stack (httpx, apscheduler, motor).

## 4. Webhook — REPLACES the v1 patch

In your existing WhatsApp webhook `POST` handler, the per-message loop
becomes (dedupe first, then the v2 dispatcher — note the text-only
filter from v1 is **gone**, media now routes too):

```python
from pymongo.errors import DuplicateKeyError
from models.neural_schema import normalize_phone, utcnow
from services import screening_engine

for msg in value.get("messages", []):
    # 1. idempotency — Meta redelivers on slow ACKs
    try:
        await db.wa_processed_messages.insert_one(
            {"wamid": msg.get("id"), "created_at": utcnow()})
    except DuplicateKeyError:
        continue                       # duplicate delivery — skip

    # 2. one dispatcher for text, voice, documents, images —
    #    routes to: active session → booked interview (RESCHEDULE)
    #    → placement (joining replies) → ignored
    phone = normalize_phone(msg.get("from", ""))
    if phone:
        await screening_engine.route_inbound(db, phone, msg)
```

## 5. Lifecycle (services/lifecycle.py)

```python
from services.screening_tasks import ensure_agent_indexes, register_agent_jobs

# startup, after db is ready:
await ensure_agent_indexes(db)          # v2 indexes + wamid TTL dedupe
register_agent_jobs(scheduler, db)      # 4 jobs, functools.partial-wrapped
```

Jobs registered (UTC): worklist 04:00 (09:30 IST) · **sweeps every
30 min** (nudges + interview reminders + joining touchpoints + email
fallback, each self-gated) · refresh batch 03:30 (09:00 IST) · evening
report 13:45 (19:15 IST).

## 6. Environment — full reference

v1 flags unchanged. New in v2 (all default to the safe side):

| Var | Default | Meaning |
|-----|---------|---------|
| `AGENT_AUTO_SCHEDULE` | `1` | Offer interview slots to QUALIFIED candidates (needs slots posted; per-job off-switch: `jobs.agent_auto_schedule: false`) |
| `AGENT_CROSS_OFFER` | `1` | One alternative mandate for NOT_QUALIFIED fits |
| `AGENT_STT` | `0` | Voice-note transcription via Groq Whisper |
| `AGENT_STT_MODEL` | `whisper-large-v3` | |
| `AGENT_JOINING` | `1` | Joining-shepherd touchpoints |
| `AGENT_REFERRAL` | `0` | Referral ask after happy closings |
| `AGENT_EMAIL_FALLBACK` | `0` | Email + web form for stalled sessions |
| `AGENT_FORM_BASE_URL` | — | Public base for form links, e.g. `https://ventureshrd.com/api` |
| `AGENT_REFRESH_DAILY_CAP` | `0` | Stale-profile refreshes/day (0 = off) |
| `AGENT_REFRESH_MONTHS` | `12` | Staleness threshold |

Master switches still rule everything: `AGENT_ENABLED=0` (nothing runs)
and `AGENT_DRY_RUN=1` (no real sends, full logs).

---

## 7. Dry-run walkthrough (extends the v1 script)

With `AGENT_ENABLED=1 AGENT_DRY_RUN=1`:

```bash
# interview slots for a mandate (as recruiter/admin)
curl -X POST $API/agent/slots -H "$AUTH" -d '{
  "mandate_id":"<job_id>","start":"2026-07-28T05:30:00Z",
  "capacity":2,"mode":"phone"}'

# happy path to QUALIFIED via simulator … Asha then offers slots:
curl -X POST $API/agent/simulate/<sid> -d '{"text":"2"}'      # books slot 2
curl $API/agent/interviews?mandate_id=<job_id>                # → booked

# FAQ interrupt mid-flow
curl -X POST $API/agent/simulate/<sid2> -d '{"text":"salary kitni hai?"}'

# document collection
curl -X POST $API/agent/push-docs -d '{
  "candidate_id":"<cid>","documents":["updated_cv","photo"]}'

# bulk push with skip report
curl -X POST $API/agent/push-bulk -d '{
  "candidate_ids":["a","b","c"],"mandate_id":"<job_id>"}'

# takeover → type → resume
curl -X POST $API/agent/sessions/<sid>/takeover
curl -X POST $API/agent/sessions/<sid>/send -d '{"text":"Namaste, Rahul here from VHC"}'
curl -X POST $API/agent/sessions/<sid>/resume

# joining shepherd
curl -X POST $API/agent/placements -d '{
  "candidate_id":"<cid>","mandate_id":"<jid>","joining_date":"2026-08-03T03:30:00Z"}'

# analytics · submission note · manual runs
curl $API/agent/analytics?mandate_id=<job_id>
curl -OJ $API/agent/sessions/<sid>/submission-note
curl -X POST $API/agent/run-sweeps        # admin
```

## 8. Go-live order

1. Deploy with `AGENT_ENABLED=0`. Verify `/agent/config`.
2. `AGENT_ENABLED=1 AGENT_DRY_RUN=1` — run §7 end-to-end in the
   simulator; check the panel renders columns, funnel, transcripts.
3. Flip `AGENT_DRY_RUN=0` with caps at `5/25`. **Recruiter's own number
   first**, then 5 real candidates on one mandate. Watch takeover works.
4. Raise caps; enable `AGENT_STT=1` after testing a Hinglish voice note
   yourself; enable refresh with `AGENT_REFRESH_DAILY_CAP=20`.
5. Weekly: `python scripts/export_ltr_labels.py --dry-run` then live —
   your ranking model starts learning from verified conversations.

## 9. Honest limitations

- **Sweep jobs are unit-tested at the logic level** (due-window math,
  touchpoint selection, reminder texts) but the 30-min scheduler loop
  itself has only been exercised manually via `/agent/run-sweeps` — do
  one supervised day before trusting it unattended.
- **Email fallback** introspects `email_service.py` defensively
  (`getattr` over known send-function names). Confirm one real send in
  staging; if your send function has a different name, one line in
  `screening_email.py` fixes it.
- **STT accuracy on Hinglish voice notes is unverified** — Whisper
  large-v3 is strong but test with real candidate audio before relying
  on it for screening answers (fallback: candidate is asked to type).
- **Touchpoint language defaults to Hinglish** — placements created
  from the panel don't know the candidate's session language unless a
  screening session existed.
- **WhatsApp Flows** (native in-chat forms) and **client mandate
  intake** are designed but not built: Flows needs the Meta Flow
  builder + encrypted data-exchange endpoints (a separate small
  project); mandate intake deserves its own review cycle since it
  writes to `jobs`.
- The web form completes sessions through the same extractors, but a
  candidate filling it *while also* replying on WhatsApp could
  interleave answers; last write wins per block. Acceptable at current
  scale; a session lock is the fix if it ever matters.
