# VHC TALENT OS — "Already in Database" Badge Traceback

## Diagnostic Report — Prepared for Multi-AI Second Opinion
**Investigator:** E1 (Emergent AI agent)  
**Date:** Feb 2026  
**Symptom (reported by admin@vhc.in / Siddharth Rao):**  
On a Naukri search-results page, some captured-before candidates get the green **"ALREADY IN DATABASE"** badge correctly (e.g. *Ajinkya Nikam*), while other candidates that were also captured before get **no badge** (e.g. *PRITAM KUMAR*).  
This makes recruiters waste profile-view credits on candidates already in the database, and erodes trust in the diagnostic layer.

---

## 1. End-to-End Current Process (as verified against v7.0.0.1 source + production DB)

### 1.1 Extension side — `browser-extension/content.js` + `background.js`

**Trigger:** MutationObserver watches the Naukri search-results DOM. When new candidate cards appear (scroll, filter, page nav), the content script:

1. Finds all *unprocessed* candidate cards (`content.js:3951`)
2. Extracts a payload per card:
   ```
   {
     name: <text from card heading>,
     headline: <string from card>,
     location: <text>,
     naukri_id: <stable Resdex data-target-id / checkbox value>,
     current_employer: <parsed>,
     designation: <parsed>,
     experience_years: <parsed float>,
     annual_ctc: <parsed>,
     skills: <array>,
     education: <string>,
     notice_period: <string>
   }
   ```
3. Batches N cards and sends `chrome.runtime.sendMessage({ action: 'checkExisting', candidates: [...] })`
4. Background service worker (`background.js:487`) posts them to `POST /api/extension/check-existing` with the recruiter's JWT
5. When the response arrives, content.js iterates the `results[]` array and, for every `exists: true`, injects the `<div class="badge">ALREADY IN DATABASE</div>` overlay onto the corresponding card (`content.js:4233`)

### 1.2 Backend side — `backend/routes/extension_check.py`

The endpoint is gated by an **email allowlist** via env var `EXTENSION_CHECK_EXISTING_ALLOWLIST` (default: empty → nobody gets real results; `*` → everyone).

For each incoming candidate, matching proceeds through two paths:

**Fast path — `naukri_id` present:**  
Single `$in` lookup on the `naukri_profile_id` field in `candidate_bank`. Uses the existing indexed field. If a match exists, return `exists: true` immediately with `match_confidence: high`.

**Slow path — `naukri_id` absent OR fast-path miss:**  
Fuzzy multi-signal scan:

1. **Name-token bucket query** (`_bucket_query_for`):  
   - Multi-token card names (e.g. "Pritam Kumar") build a two-branch Mongo regex:
     - Branch A: `name_lower` starts with `pritam` AND matches `\bkumar` anywhere
     - Branch B (reversed): `name_lower` starts with `kumar` AND matches `\bpritam` anywhere
   - Result is bucketed and TTL-cached (5 min, 512-entry LRU-ish)
2. **Strict name filter** (`_strict_name_match`):  
   Post-filter over the bucket. For multi-token names on both sides, requires BOTH first AND last significant (≥3-char) tokens to match. Or a fuzzy ratio ≥0.92 (for typos/transliteration).
3. **Multi-signal scoring** — each corroborating signal contributes a weight:
   ```
   name:              0.5   (baseline, always required)
   employer:          0.6
   designation:       0.4
   ctc (±20%):        0.5
   experience (±1y):  0.4
   skills (≥30% ovl): 0.5
   education:         0.4
   location:          0.25
   headline_employer: 0.4
   ```
4. **Threshold gate:**  
   - `_BADGE_THRESHOLD = 1.0` (name alone at 0.5 is NOT enough)
   - `_HIGH_THRESHOLD = 1.3`
   - Additionally: **at least one STRONG signal must fire** — `employer`, `headline_employer`, `ctc`, or `skills`. Name + designation + location alone will NOT badge (too weak for common names).

The endpoint writes a `badge_audit` doc per batch (input names, results, matched signals, user, page_url) and returns to the extension.

### 1.3 Persistence pipeline (for context — how a captured candidate lands in candidate_bank in the first place)

1. Extension captures → `POST /api/extension/capture/async` → returns `job_id`
2. Background worker processes the capture:
   - Extracts CV text via 4-strategy fallback (iframe, background relay, fetch, PDF.js)
   - Calls `/api/extension/ai-extract` (LLM extraction — runpod_qwen14b primary, regex/haiku fallback)
   - Merges extracted fields into a candidate_bank doc
   - Runs dedupe → either creates new candidate or merges into existing
3. Writes `naukri_capture_logs` entry with `captured_to_bank: true/false` and `data_missing_fields[]`

---

## 2. Investigation into the specific case

**Ajinkya Nikam (badge fires correctly):**
- Present in `candidate_bank` with matching current_employer ("KSB Valves"), phone, notice period
- Card sends `naukri_id` → **fast path hits** → instant `exists: true` with `high` confidence

**PRITAM KUMAR (no badge, but user expects one):**  
Live DB evidence:
- `naukri_capture_logs` has a **PRITAM KUMAR entry on 2026-08-10** with `status: success` and `captured_to_bank: True`
- BUT `candidate_bank` searched by name prefix "pritam" AND (employer ~ Kirloskar OR KSB OR designation ~ Senior Manager) returned **zero rows** matching the screenshot's PRITAM KUMAR at Kirloskar Brothers
- Ten different "Pritam Kumar" exact-name records exist in `candidate_bank`, none at Kirloskar Brothers
- `badge_audit` batch history returned no records containing "Pritam" in the input_names for that user's recent scans

---

## 3. Root-cause hypotheses (E1's shortlist — for pressure-test)

- **H1 — Persistence gap:** The 2026-08-10 PRITAM KUMAR capture logged `captured_to_bank: True` but the actual insert failed silently (dedupe collision, index conflict, or LLM-extracted employer mis-matched a different existing record → merged the wrong way). This matches the 33% pre-extraction gap Meta AI identified in the parallel Capture Diagnostics investigation.

- **H2 — Employer-string mismatch defeats the STRONG-signal gate:** The candidate IS in DB, but the DB record's current_employer is "Kirloskar" or "Kirloskar Bros" while the Resdex card says "Kirloskar Brothers Limited". The `_employer_matches` substring rule requires ≥4 chars overlap AND won't match after stripping "limited/ltd/pvt". Case fails → name matches at 0.5 → no strong signal → threshold not met.

- **H3 — Naukri_id missing from the card payload:** The extension's Resdex card parser sometimes fails to extract `data-target-id` (perhaps for cards rendered by lazy-scroll where the attribute is populated later). Fast path skipped, falls to slow path with weak signals.

- **H4 — Extension never sent the card:** MutationObserver marks a card `processed` after first scan attempt. If the scan happened before the card DOM was fully rendered, the card gets tagged processed but never sent to `check-existing`. `badge_audit` returning no Pritam batch supports this hypothesis. When the user later scrolls back to look at the card, it's already marked processed → no re-scan.

- **H5 — Common-name false-negative by design:** 12 different Pritam Kumar records exist. The strict matcher correctly rejects most as false positives. But if the "right" Pritam Kumar (at Kirloskar) IS in DB with correct employer, the fuzzy first+last token match should have fired and the employer signal should have added 0.6. Total 1.1 → above threshold → badge should fire. If this doesn't happen, either H2 or H1 explains it.

- **H6 — Extension's local dedup cache is stale:** The extension caches "already-processed" card fingerprints in `chrome.storage.local` to avoid re-badging on scroll re-render. If the user last logged in weeks ago and the cache still holds the card as "no badge", it may never re-hit the API for the same fingerprint.

---

## 4. The three pressure-test checks for second opinions

1. **Persistence integrity:** For every capture with `naukri_capture_logs.status = success` AND `captured_to_bank = true` in the last 30 days, does a matching `candidate_bank` row actually exist (joined by candidate_name OR naukri_profile_id)? If yes at 99%, H1 is dead. If no, H1 is confirmed.

2. **Employer-string canonicalization:** Sample 50 captures where card employer differs slightly from DB employer (e.g. "Kirloskar Brothers Limited" vs "Kirloskar Brothers"). Does `_employer_matches` correctly return true for these ≥90% of the time? If not, H2 is the biggest wire to fix.

3. **`naukri_profile_id` capture rate:** Of the recent `check-existing` API batches, what fraction of incoming candidates carry a non-null `naukri_id`? If <70%, H3 is real and the fast path is being bypassed for most cards — meaning the whole system depends on the slow-path fuzzy scoring, which is where all the failure modes live.

---

## 5. What was NOT verified (open items for reviewers)

- **`badge_audit` completeness:** empty Pritam-batch results could mean either "extension didn't send" (H4) or my query semantics don't match how `input_names` is stored. Needs schema inspection.

- **Extension local-cache stickiness (H6):** would need to be checked by clearing `chrome.storage.local` and re-visiting the same search page. Not verifiable from DB.

- **Ajinkya vs Pritam card structure:** why does one card provide `naukri_id` reliably and the other not? Could be a Resdex A/B test on card HTML — needs a live DOM inspection.

---

## 6. What was verified (findings E1 stands behind)

- The endpoint code exists and is well-structured with strict precision (multi-signal, honorific stripping, corp-suffix normalization)
- The `EXTENSION_CHECK_EXISTING_ALLOWLIST` env gate exists and defaults to empty — misconfigure this and NOBODY gets badges regardless of DB state
- The fast-path `naukri_profile_id` lookup exists and is the correct primary key for candidate identity from Naukri
- The `_strict_name_match` logic correctly rejects false-positive same-first-name candidates
- The signal weights and thresholds prevent "single first name" false badging (Manish/Akash problem)
- A `badge_audit` collection exists and stores per-batch results — the data is there, we just need the right query to inspect it

---

## 7. Preliminary recommendation (E1's bias — pressure-test this)

**Two immediate zero-risk fixes:**

- **A. Widen the employer matcher (H2):** current substring rule is ≥4 char overlap. Add token-set intersection: split both employer strings on whitespace, if ≥60% of DB employer's meaningful tokens appear in card employer (or vice-versa), match. This catches "Kirloskar Brothers Limited" ↔ "Kirloskar Brothers" without loosening precision.

- **B. Ensure `naukri_profile_id` capture (H3):** log to the audit trail whether `naukri_id` was sent per card. If overall rate is <70%, fix the Resdex card parser to also look at post-lazy-load ID attributes and re-scan on card mutation, not just on card mount.

**Longer play (needs the telemetry from the parallel Capture Diagnostics work):**

- **C. Fix persistence integrity (H1):** if the second-opinion check #1 comes back <99%, the badge system is only as good as the underlying candidate_bank. No amount of matching logic will help if captures are silently landing under wrong candidates.

---

## 8. What I want the second opinion to answer

- Which hypothesis (H1–H6) is most likely, given the evidence in Sections 2–3?
- Are there hypotheses I've missed?
- If forced to ship ONE fix this week to move badge accuracy from ~60% to ~95%, which would it be?
- Is the 60% number even plausible, or is the system's real accuracy above 90% and only the anecdotal "PRITAM KUMAR" case caused the user's alarm?
- Would you touch the STRONG-signal gate (currently: at least one of employer / headline_employer / ctc / skills)? Loosening it improves recall but risks the "3 Manish Kumar" false-positive class.

---

## Appendix — files referenced

- `backend/routes/extension_check.py` — endpoint + scoring logic
- `backend/services/extension_service.py` — `_names_are_similar` (dedup matcher, distinct from `_strict_name_match`)
- `browser-extension/content.js` (v7.0.0.1) — card scanning + badge injection
- `browser-extension/background.js` (v7.0.0.1) — API call orchestration
- Collections: `candidate_bank`, `naukri_capture_logs`, `badge_audit`, `extension_capture_jobs`

