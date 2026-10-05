# VHC Talent OS — Product Requirements & Current State

Last updated: 2026-09-08. This concise document supersedes obsolete provider instructions in historical notes.

## Original problem statement
Fix Chrome Extension background capture failures, stabilize backend infrastructure and profile extraction, reduce operating cost, and support high-quality recruitment sourcing, profile deduplication, semantic matching, deep links, and team workflows.

Current user goal: remove the retired RunPod/Qwen integration and its strict-only gate, ensure new captures have reliable AI enrichment, and show Pending/Failed status instead of a missing badge.

## Explicit current user decisions
- Keep NVIDIA first and Emergent Haiku last; remove Qwen completely from active inference.
- NVIDIA GPT-OSS-120B is retired. User approved replacing it with another current NVIDIA endpoint and supplied their available model list.
- Final verified chain: **Nemotron Super 120B → Nemotron Ultra 550B → Mistral Nemotron → Emergent Claude Haiku 4.5**. Super leads because production data showed it processes more captures successfully than Ultra (Ultra hits HTTP 429 rate limits under load).
- **DO NOT retry or re-enrich previously missed profiles.** Earlier retry approval was expressly revoked. No missed-profile re-enrichment or backfill was executed in this session.
- MongoDB awarded the user USD 500 startup credit. Credit activation/balance/expiry have not been verified here. Keep Atlas M10 for now; no urgent Flex or RDS migration.
- No AWS DocumentDB, Azure Cosmos DB, or application-managed multi-Flex sharding.
- Database migrations, embedding backfills, and destructive retention changes require separate approval.

## Personas and core flows
- Recruiter: capture Naukri/LinkedIn profiles, search candidates, review matches, manage pipelines.
- Manager/admin: manage sourcing, review candidate enrichment and data quality, monitor operations and team performance.
- Employer/account manager: inspect candidate pipelines, hiring progress, and permitted candidate information.
- Captured candidate: source of profile data; no direct UI required for this flow.

## Architecture
- React/Vite frontend with Shadcn/Tailwind; retain existing design and role permissions.
- FastAPI backend with Motor/PyMongo and MongoDB Atlas. This preview connects to real candidate data: never assume it is a disposable test database.
- Runtime backend 8001, frontend 3000, supervised services. API routes begin `/api`.
- Frontend API base: `REACT_APP_BACKEND_URL`; MongoDB: `MONGO_URL` and unchanged `DB_NAME`.
- Existing production EC2 service is separate from this preview. User-confirmed service: **`vhc-backend.service`**, NOT `gunicorn.service` (gunicorn is the process). Production repo: `/home/ubuntu/vhc-platform`; Python 3.12.3; frontend output `frontend/build/`, existing webroot `/var/www/html/`. Earlier runbooks naming `gunicorn.service` are obsolete for this host.
- Existing token key: `vhc_token`. Credentials remain in `memory/test_credentials.md`; none changed this session.
- Active Talent Graph BGE-small sidecar remains 384-dimensional in `candidate_embeddings`. Do not mix those vectors with legacy 1024-dimensional BGE-M3 or planned NVIDIA embeddings.

## Current enrichment architecture (implemented and tested 2026-09-08)
1. `nvidia/nemotron-3-super-120b-a12b`, source `nvidia_nemotron_super_120b`, badge **NS**. **Primary** — user-observed to handle more real captures cleanly than Ultra.
2. `nvidia/nemotron-3-ultra-550b-a55b`, source `nvidia_nemotron_550b`, badge **N**. Fallback for the harder profiles Super struggles on.
3. `mistralai/mistral-nemotron` via NVIDIA NIM, source `nvidia_mistral_nemotron`, badge **MN**. 15 s wall-clock budget (via `MISTRAL_TIMEOUT`) because this endpoint is intermittent on the current NVIDIA account. Fast escape to Haiku when unhealthy.
4. `claude-haiku-4-5-20251001` through existing Emergent integrations, source `emergent_haiku_4_5`, badge **EC**.

Not usable on this NVIDIA key (listed in catalog but requests hang indefinitely — do not resurrect without account-side unblock): `deepseek-ai/deepseek-v4-pro-0813`, `deepseek-ai/deepseek-v4-flash-0731`, `google/gemma-4-31b-it`, `moonshotai/kimi-k3`.

Configuration: existing `NEMOTRON_API_KEY`, `NEMOTRON_BASE_URL`, `NEMOTRON_MODEL` (Ultra); `NVIDIA_FALLBACK_MODEL=nvidia/nemotron-3-super-120b-a12b`; `NVIDIA_MISTRAL_MODEL=mistralai/mistral-nemotron`; `EMERGENT_LLM_KEY`. Env variable **names** are unchanged — only the chain-order in `APPROVED_SOURCES` was flipped, so nothing to update in production `.env` beyond what was already added.

- Adapters: `backend/services/llm_providers.py`. Non-thinking Nemotron requests omit unsupported `response_format`; structured content is parsed and validated locally.
- Orchestration: `backend/services/llm_fallback_service.py`; shared facade `services/llm_service.py`.
- Existing salary/date/regex normalization moved intact to `services/profile_extraction_helpers.py`.
- Three attempts maximum for transient NVIDIA 502/503/504/network errors within a total 90-second budget per provider. Permanent failures/throttling proceed to the next provider; no strict-provider gate.
- CV extraction, industry classification, billing body generation, and talent summaries use the approved shared path rather than direct Qwen calls.
- RunPod sync daemon is no longer scheduled. Historical monitoring endpoints return an explicit retired status without network access. Legacy remote BGE-M3 transport is disabled; BGE-small is unchanged.
- `routes/extension.py` success persistence atomically saves enrichment status/source/time/hash/chain and clears stale errors. Conditional writes discard stale recapture results; failed attempts cannot replace an already-successful status.
- UI: `EnrichmentBadge.jsx` shows N/NS/MN/EC/Pending/Failed/Not enriched. Historical successful sources remain represented truthfully; old data is not rewritten.
- `useEnrichmentPolling.js` checks a bounded number of visible Pending rows, avoids overlapping requests, and cleans up on unmount. It does not initiate enrichment.
- Admin A/B now compares Ultra vs Super. Historical reports are not relabeled as the new models.
- `/admin/ai-monitoring` aliases existing `/admin/system-health`. Provider configuration display is not represented as proof of live availability.
- The former `scripts/retry_all_failed_enrichment.py` is deliberately **read-only** and accepts no execution mode. No recovery worker exists.

## Verification and limitations
- Reports: `test_reports/iteration_192.json` (initial findings), **`test_reports/iteration_193.json` (final pass)**.
- 29 targeted tests passed: 19 provider/chain/persistence cases plus 10 retry/full-profile post-processing cases.
- All three current providers were called live with synthetic input; forced fallback tests mocked only upstream failures while downstream calls were real.
- Full-profile persistence/post-processing and error scenarios used **MOCKED** fixtures; no existing candidate writes were performed for tests.
- UI passed read-only checks for badges, NS filter, alias, provider configuration, and pending polling using **MOCKED** response fixtures for state transitions.
- Main follow-up: 10 deterministic tests passed again; Python compilation passed; `/api/health` healthy with MongoDB/Redis OK and zero import failures. Optional Ruff is not installed.
- Production update completed by user on 2026-09-08: merge `7ef8e308`, fallback env setting, successful Vite build, **`vhc-backend` restart active**, and frontend copy. CSV security removal, housekeeping script and dependency lock preserved. Fresh production logs show successful `nvidia_nemotron_super_120b` extraction/persistence and normal live capture processing; Ultra HTTP429 falls through correctly. Main independently retrieved **`https://ventureshrd.com/api/health`**: healthy, MongoDB OK, Redis OK/local, import_failures=0. The previously supplied `app.ventureshrd.com` hostname has a certificate-name mismatch and is NOT the verified health-check hostname. Do not bypass TLS checks. Production badge display still awaits user observation; no repeat pull/build/restart or missed-profile backfill needed.
- NVIDIA transient overload remains possible; verified retries/fallback handle it. No promise of permanent upstream availability.

## Roles & access (as of 2026-09-17)
- **Recruiter**: Dashboard, Mandates, Pipeline, Advanced Search, Candidate Bank, Submission Tracker,
  Attendance, Leaves. Sees their target as a **percentage only**.
- **Employer / team lead**: Dashboard, Analytics, My Team (sets member revenue targets + already
  achieved), Joining List (fill CTC + revenue, Raise Invoice), Companies, Pipeline, Trackers, My Jobs,
  Candidate Bank, Advanced Search, Attendance, Team Attendance, Leaves, Team Insights (own team only),
  Reports, Salary Benchmark.
- **Accounts** (accounts@vhc.in): Bills & Invoices + the accounts portal.
- **Admin**: everything, plus Teams (team-level targets) and Performance Records (monthly/quarterly/
  annual archive).
- Revenue targets are one number per calendar year (Jan–Dec). Recruiter revenue Σ = team total,
  team Σ = company total.
- Pending from the user: further employer/recruiter access tweaks as they review.

## Revenue source of truth (2026-09-20)
- `placement_ledger` (527 placements imported from the client's Excel tracker) is the authoritative
  record of revenue booked before the platform tracked joinings; new platform joinings add on top.
- Achievement uses **Active Revenue** = gross − backout − credit note − other/review. Realization % =
  received ÷ active. Every dashboard, target rollup and the Performance Records tab read this.
- Performance Records (`/admin/performance-records`) mirrors the sheet: KPI strip + Branch Summary,
  Recruiter Revenue, Placements, Teams & Targets, Review and Archive tabs, with CSV export.
- Recruiter spelling variants are merged to one person; anyone who left keeps their revenue in the team
  they worked for; no-login and blank-recruiter rows sit in the branch total as Ex-employee / Unassigned.
- Re-import a refreshed sheet with `python3 -m scripts.import_placement_ledger <file.xlsx>` (idempotent).
- The Joining List (employer + accounts + Admin Analytics) is the tracker and the pipeline merged and
  deduped, each row showing its payment state. Tracker rows are read-only; pipeline rows stay editable.
- One team per branch: Delhi = Maneet + Manorma, Gurgaon = Ajit + Jatin + Rohit (`additional_employer_ids`).
- Visibility: Admin + Accounts see every number, an employer sees only the team(s) they manage, a
  recruiter never sees a rupee value.
- Overlap is blocked at the API: a hire already in the tracker cannot have revenue booked or an invoice
  raised from the pipeline (409). `GET /api/branch-revenue/reconcile` proves the books agree (9 checks,
  surfaced as the "Number check" panel in Performance Records → Review).
- **Deferred (client, 2026-09-20)**: back-filling the 451 tracker-only hires into the pipeline. It needs
  ~451 candidate profiles (no phone/email in the sheet), 43 new client companies and ~400 historical
  mandates; options and trade-offs were put to the client and parked.
- Flagged review rows are resolvable by hand (assign recruiter / fix amount / move payment / dismiss),
  audited, and reflected everywhere instantly. Bills → **Invoices & Payments** is the Accounts worklist:
  invoice to be raised · payment pending · payment received · backout/credit note.
- Duplicate hires are detected (spelling variants, transposed letters, same name + same client/amount) and
  reviewed by hand in Performance Records → Review: merge, void the copy, or mark as different people.
  Near-name matches are blocked from double-booking revenue.
- Several candidates of one client can be billed on a single invoice (Bills → Invoices & Payments →
  tick the rows → "Bill N on one invoice"); marking that invoice paid clears every candidate on it.
- **Open item**: the client still has to judge the 8 flagged pairs, incl. Puneet Kumar (₹64,974, two invoice nos).
- **Open item**: annual targets are all ₹0 — the admin still has to set each recruiter's / team's number
  before achievement percentages mean anything.

## Billing module — current state (2026-09-17)
- Two sender entities: `VENTURE HRD CENTER` (07AAMPY9883D2ZT) and `Ventures HRD Pvt Ltd`
  (07AACCV6268J1ZW), both at Second Floor, D-12/79-80, Rohini Sector 8, New Delhi 110085.
- All historical bills/invoices/expenses/revenue were wiped on user instruction; numbering restarts at
  VHC/26-27/1. Bank accounts must be re-added by the user (invoice PDF prints the bank block from the
  default/only saved account).
- Invoices send from accounts@ventureshrd.com, reply-to + BCC accounts@vhc.in. Switch the FROM to
  accounts@vhc.in once that domain is verified in Resend.
- accounts@vhc.in (role `accounts`) can use Bills & Invoices at `/accounts/bills`.
- Pending from the user: further additions/removals to employer and recruiter access.

## Spec compliance status (2026-09-17) — both uploaded docs
All items from `fix.docx` and the Employee Performance Analytics specification are implemented and
verified live. See the 2026-09-17 entry in [CHANGELOG.md](CHANGELOG.md) for evidence per item.
- Analytics Hub is now public-website-only (internal portal routes excluded by route prefix).
- Joinings list lives on Employee Performance, derives DOJ from stage history, and follows the page's
  date/team/employee filters. Revenue stays blank until a team leader fills it in.
- "Candidates called" is tracked from three intents (extension badge click, profile open, explicit
  Mark Called) and surfaced on Badge Audit.
- Clusters has no dedicated page any more (backend service only).
- Invoice PDF always prints the company logo and the bank-transfer block (default/only saved account
  when a bill predates the feature).

Remaining backlog for this workstream: employee drill-down drawer, quarterly targets UI, composite score
weighting editor, Badge Audit "Already in Database" reuse report, Advanced Search redesign (deferred by
the spec), and unifying Daily Digest points (tracker_events) with the analytics points (stage_history).

## Documentation
- [CHANGELOG.md](CHANGELOG.md): current implementation and investigation facts.
- [ROADMAP.md](ROADMAP.md): prioritized remaining work and prohibited/deferred actions.
- [Historical archive](CHANGELOG_ARCHIVE_PRE_2026_09_08.md): exact prior 2,053-line PRD retained for older requirements and implementation history. Its RunPod/GPT routing instructions are obsolete.
- `ATLAS_FLEX_MIGRATION_RUNBOOK.md`: retained, migration paused.
- `PLATFORM_AUDIT_2026_08.md`, `badge_traceback_diagnostics.md`: earlier audit references.
## One flow, end to end (2026-09-28) — user-dictated rewrite
The sourcing → joining → invoice → payment → revenue process is now a single chain. Everything
that contradicted it was deleted.

1. Mandate is created by Recruiter / Employer / Admin.
2. The mandate is selected in the Chrome extension.
3. A captured profile lands in the **Sourced** column of that mandate's pipeline
   (`pipeline_display_filter()` no longer hides `source=extension_capture`; only a rejection
   older than 7 days leaves the board).
4. Stage movement is **unconditional**: Sourced → Submitted → Shortlisted → Interviewed →
   Offered → Hired → Joined, plus Rejected / On Hold. No CTC, offer amount or revenue is asked
   for on the board — the Offer/Hired/Join revenue dialogs are gone from the admin pipeline and
   every stage chip is available on every card.
5. Moving to **Joined** puts the candidate on the Joining List of the recruiter, the employer of
   their team, Admin and Accounts. Recruiters have their own list at `/recruiter/joinings`
   showing DOJ, candidate, client and client position only (`restricted: true`, no rupee values).
6. Admin / Accounts / the team's Employer fill in Joining CTC + Billing amount and can edit the
   DOJ (`PATCH /api/joinings/{id}` accepts `joined_ctc`, `revenue`, `join_date`).
7. **Raise Invoice** on the Joining List: both figures present → the draft goes straight to
   Accounts; a figure missing → one box asks for CTC + billing amount.
   `POST /api/joinings/{id}/raise-invoice` now takes `{joined_ctc, billing_amount}` (the
   commercial-rate input is gone; the rate is derived for the PDF) and stamps `application_id`
   on the line item so mark-paid clears the revenue row.
8-13. Accounts sees the draft in Bills & Invoices, sends it, marks payment received, and the
   amount rolls into company / team / recruiter revenue and targets.

Removed as contradicting process: auto-drafted bills on hired/joined, the employer
approve/reject gate (`/applications/pending-approval`, `/applications/{id}/employer-approval`
and their shortlist notification), and the legacy stages — 305 `applied` rows became `sourced`
and 36 `employer_approved` became `shortlisted` (original value kept in `legacy_stage`).

**Duplicate joinings fixed**: one row per candidate name; the most complete row wins (live client
first, then money already recorded, then the most recent DOJ). Caused by a candidate left behind
on a mandate that was later deleted, which showed as a second row with no client or position.

**Recruiter pipeline scope**: a recruiter now sees only their own sourced candidates plus the
mandates they own/are assigned to, sorted by most recent activity.

**Resend quota is reserved for three flows** (`ALLOWED_EMAIL_CATEGORIES` in
`services/email_service.py`): attendance reminder, marked absent/late notification, and the
payment-due reminder. `password_reset` stays on because account recovery needs it, and the
invoice-to-client mail keeps sending through `services/bill_mailer.py` (step 9 needs it).
Everything else — weekly recruiter digest, daily/weekly Excel reports, team digest, blog and
job-match mails — is dropped before it reaches Resend, and those cron jobs were removed.
New: `services/payment_due_reminders.py` mails the pending-payment list every Monday 10:00 IST —
all candidates to Admin + Accounts, team-only to each Employer. Dry run:
`POST /api/joinings/payment-reminders/run?dry_run=true`.

`frontend/yarn.lock` is back in sync with `package.json` (`yarn install --frozen-lockfile` passes),
so the AWS frontend build is unblocked.

### Follow-ups (2026-09-28, same day)
- **DOJ edit for everyone on the joining**: Accounts, the team's Employer and now the **Recruiter**
  can correct the date of joining from their own Joining List tab. A recruiter may send only
  `join_date` (a rupee field returns 403 "Only Admin, Accounts and the team's Employer can edit a
  joining") and only on their own joining (another recruiter's row returns 403). Tracker-sourced
  rows stay read-only — those are fixed through Performance Records → Review.
- **Add a candidate to a mandate by hand**: every pipeline page (Admin / Employer / Recruiter) has an
  **Add Candidate** button (`pipeline-add-candidate-btn`) that opens the Add-Candidate-to-Mandate
  dialog for the selected mandate — Sourced captures, system suggestions, or a Candidate Bank search.
  Inside it, **"Upload a CV instead"** (`open-cv-upload-btn`) parses a PDF/DOCX, saves the profile to
  the Candidate Bank and drops the candidate into that same mandate's Sourced column; the mandate is
  shown fixed instead of a dropdown when it is already known.

### Follow-ups (2026-09-28, evening)
- **Sticky save bar on the Joining List**: with 11 columns the per-row Save sat off-screen to the
  right, so DOJ/CTC/billing edits looked like they never saved. Editing any cell now raises a
  sticky bar — "N unsaved changes · Discard · Save changes" (`joinings-save-bar`,
  `joinings-save-all`, `joinings-discard-all`) — which PATCHes every edited row and reloads once.
  The per-row Save button stays. Verified: 2 rows edited → 2 PATCHes 200 → bar clears → KPI tiles
  move (49 awaiting revenue, pending ₹1.92 Cr).
- **Candidate search in the pipeline** for every role, scoped the same way the board is:
  Admin searches all, Employer searches their team, Recruiter searches their own. Matches name,
  email or phone (min 2 chars, 400 ms debounce) and the hits render **in the stage column they are
  sitting in**, so the card can be moved straight away. New `q` param on
  `GET /api/admin/pipeline`, `GET /api/employer/pipeline` and `GET /api/applications`
  (`candidate_search_filter()` in `services/pipeline_events.py`); `pipeline-search-input` /
  `pipeline-search-clear` test ids.
- **Employer pipeline performance fix**: with extension captures now on the board, `/employer/pipeline`
  loaded every application for the team (11.7k rows) and timed out at 60s. It now uses one
  index-backed count aggregation + the 100 most recent rows per stage, and the `$nor` display filter
  was replaced by `stage_display_clause()` (only rejections age out, so the query keeps the
  `job_id + stage + updated_at` index). 60s timeout → ~4s. The same fix was applied to
  `/admin/pipeline` (count aggregation 7s → 0.4s).

### Emergent Claude Haiku backstop removed (2026-09-28)
Capture is stable on the NVIDIA chain, so the paid fallback is gone. The extraction chain is now
**Nemotron Super 120B → Nemotron Ultra 550B → Mistral Nemotron**; a total failure falls through to
the regex backfill instead of a billed Anthropic call.
- `services/llm_providers.py` — `call_haiku()` and `HAIKU_MODEL` deleted.
- `services/llm_fallback_service.py` — `emergent_haiku_4_5` dropped from `APPROVED_SOURCES`.
- `routes/candidates.py` — advertised `provider_chain` trimmed; the bulk-enrich guard now requires
  `NEMOTRON_API_KEY` only (it used to accept `EMERGENT_LLM_KEY`).
- `services/batch_enrichment.py` — batch gate moved from `GROQ_API_KEY`/`EMERGENT_LLM_KEY` to
  `NEMOTRON_API_KEY`.
- `routes/admin_monitoring.py` — Emergent removed from `/api/admin/llm/provider-status`; the
  historical `anthropic_fallback` counter stays so old rows still report.
- `AIMonitoringPage.jsx` — the Haiku row now reads "retired · N historical".
- Tests updated; `test_haiku_backstop_is_gone` locks it in.
`EMERGENT_LLM_KEY` itself is still in use by the matching engine (OpenAI), so the key stays in `.env`.

**Heads-up found while testing**: NVIDIA's `mistral_nemotron` endpoint now answers **HTTP 410 Gone**,
so the third link in the chain is dead upstream. Super 120B and Ultra 550B both pass live checks
(a real capture extracted cleanly on Super), so capture is unaffected — but the chain is effectively
two providers deep until that model id is swapped.

### Manual CV upload fixed + made faster (2026-09-28)
**Root cause of "Internal server error" on Save to Candidate Bank**: `routes/cv_upload.py` and
`routes/candidates.py` imported `normalize_phone` (and `build_team_visibility`) from
`routes.extension`, but the identity-resolution port moved those helpers to
`services.extension_service` — so every save raised
`ImportError: cannot import name 'normalize_phone' from 'routes.extension'` after the parse had
already succeeded. Imports repointed at `services.extension_service` (3 call sites).

**Speed**: the review screen used to appear in ~20s. Two changes took it to ~10s:
- `cvUploadAPI.parseAndPoll` waited a flat 3s before *and* between every status poll. It now polls
  at 800 ms for the first 12 tries, then 2.5s, with a 3-minute wall-clock deadline.
- The CV parse prompt ran with the chain default `max_tokens=16000`; capped at 4000, which cut the
  LLM leg from 14.7s to 7.0s.
- The parsing screen now shows a live "Reading the CV… · Ns" counter instead of a bare spinner.

Verified in the browser end to end: mandate → Add Candidate → Upload a CV instead → parse (10.3s) →
Save to Candidate Bank → "Candidate profile created" + "Added to mandate", zero 4xx/5xx. Test
candidate and application removed afterwards.

### Master-sheet reconciliation + 75/25 shared credit (2026-09-30 → 2026-10-05)
The client sent the reworked tracker in the system format
(`Reworked_Branch_Recruiter_Revenue_FINAL_SYSTEM_FORMAT.xlsx`, `Sorted Data`, 594 placements,
gross ₹6.06 Cr, received ₹4.18 Cr). `scripts/import_placement_ledger.py` re-imported it
(idempotent on `source=excel_tracker_2026_09`).

Result in `placement_ledger`: **587 rows / 584 placement credits / gross ₹5.9654 Cr**. The gap to
the sheet is exactly the ₹9,81,280 of rows kept platform-owned (below). Branch totals tie out:
Delhi ₹2.04 Cr, Gurgaon ₹1.87 Cr, Faridabad ₹1.07 Cr, Bangalore ₹88.2 L, Hyderabad ₹10.1 L.

- **Shared credit is now 75 / 25** (`MAIN_SHARE`, `SUPPORT_SHARE`): the recruiter named first on a
  shared row owns the placement, the second supported it. Applies to revenue *and* the placement
  count — `Ajit / Avinash` (2 rows) and the new `Madhuri /Navya` (1 row).
- **New recruiter mappings** from the final sheet: `manorma → manorma@vhc.in`,
  `abhayyadav → hr7`, `sachinyadav → hr12`; `swastik` and Faridabad `nidhi` have no login so their
  rows sit in the branch as Unassigned (49 unassigned rows, ₹33.7 L, unchanged policy).
- **10 rows stay platform-owned** (₹9,81,280): a candidate who is already a `joined` application
  *and* has no invoice number in the sheet is not imported — a tracker row is read-only and would
  kill "Raise Invoice". Their Offered CTC is written to the application and the billing amount is
  carried as `master_sheet_billing`, surfaced on the Joining List as `suggested_billing` and
  pre-filled into the Raise Invoice box, so Accounts raises those invoices in-app.
  (Darshan Gondalia, ANAND S, Vinit Shah, Sumitha N, Srinivas P, Shubham Suresh Sorte,
  Ravindra Navik, Rahul Singh Ruhela, Manish Bhoi + 1.)
- Backup of the pre-import ledger: `/app/memory/placement_ledger_backup_20260930.json` (528 rows).
- The earlier interim reconciliation (`scripts/reconcile_master_sheet.py`, source
  `master_sheet_2026_09_30`) was rolled back — its 35 rows were deleted before this import, and the
  two renamed duplicates it voided (Saransh, Rahul) are absent from the final sheet anyway. The
  script is kept for future sheet-vs-ledger diffs (read-only by default).

Live after the import: Joining List 614 joinings (110 in both · 456 tracker · 48 pipeline),
gross ₹5.90 Cr, received ₹4.08 Cr, pending ₹1.80 Cr, backout/CN ₹2.34 L; bills worklist
to-raise 90 / pending 99 / received 272; targets and team rollups recomputed off the new ledger.

**Open item**: FY26-27 team targets are still near zero, so the Joining List shows
"Team achievement 4015.4% (₹5.92 Cr of ₹14.75 L)". The targets need to be set for the year.

### Name-ambiguity audit + duplicate-guard fix (2026-10-05)
Audited all 587 ledger rows for name confusion:
- **17 names appear more than once**: 3 are 75/25 shared rows (Priyadarshan, Sumitha, Ashish Kumar),
  3 are the RPO monthly billing names (rohit-rpo, Lokesh Tiwari Rpo, Aniket-rpo — 4 rows each, one
  per month), and 11 are genuinely different people in different branches/clients (Ankit Kumar,
  Manish Kumar, Rahul Kumar, Sandeep Kumar, Ayush Sharma, Abhay Yadav, Shubham Gupta,
  Saurabh Sharma ×3, Puneet Kumar, Vishal). No row is double-counted.
- **5 near-spelling pairs** the money guard would treat as one person even though they are not:
  Shubham/Shubam Gupta · Manish/Anish Kumar · Abhishek Rathor/Rathod · Praveen Kumar G/B ·
  Vishal/Vishva Sharma.
- **57 rows carry a first name only**; 8 share that first name with a full-name row (Sachin,
  Gaurav, Ravi ×3 each, Navdeep, Hemant, Ankush). A bare first name cannot be matched to a
  pipeline candidate at all, so a future in-app invoice for the same person would not be caught.
- **125 pipeline joinings are matched to a tracker row** (119 exact, 6 fuzzy). Five fuzzy ones are
  genuine typos of the same hire; **"Sumitha N" (Gurgaon, ₹91,000) vs "Sumitha" (Bangalore,
  ₹28,875) are two different people** and the guard was blocking her invoice.

**Fix**: `tracker_row_for_candidate()` now takes the application id and skips any ledger row whose
`not_duplicate_of` already lists it, so Performance Records → Review → *different people* finally
unblocks invoicing — until now that action only stopped the flagging. Verified on Sumitha N
(blocked → marked → clear → reverted, so the call stays with the user).

### How a placement's revenue is credited (reference)
Tracker rows (`scripts/import_placement_ledger.py`):
1. One sheet row = one placement; `Revenue (Numeric)` is the money.
2. `Recruiter (Standard)` → a login via `RECRUITER_EMAIL` (+ `BRANCH_OVERRIDE` where a first name
   means different people in different branches). One name → **100%**.
3. `A / B` → **main 75% / support 25%** (`MAIN_SHARE`/`SUPPORT_SHARE`), applied to the money *and*
   the placement count (0.75/0.25), so a shared hire still counts once company-wide.
4. Blank recruiter or no login → the row stays in the branch total as *Ex-employee / Unassigned*
   and credits no individual.
5. Branch → team via `BRANCH_TEAM_NAME`; buckets Payment Received / PP / IP / Backout /
   Credit Note / Other-Review. Active Revenue = Gross − Backout − Credit Note − Other.
   Target achievement uses Active Revenue; Realization % = Received / Gross.
In-app joinings (`book_joining_revenue`): the billing amount typed on the Joining List is booked
**100% to the recruiter who created the application** (`created_by`). There is no support-recruiter
field in-app yet — a shared in-app placement has to be split on the tracker side.
