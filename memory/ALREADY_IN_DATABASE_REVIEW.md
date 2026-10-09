# "Already in Database" — current structure, for external review

VHC Talent OS · prepared 9 Oct 2026 · scope: the green **ALREADY IN DATABASE** badge the Chrome
extension draws on Naukri/LinkedIn search result cards.

---

## 1. Headline finding

**This is a regression with a known date, not a feature that never worked.** It fired on roughly
62% of scanned cards until 28 Sept 2026, then dropped to zero and has stayed there.

`badge_view_stats`, one row per day, written by the extension itself:

| day | scan calls | cards scanned | badges shown | hit rate |
|---|---|---|---|---|
| 2026-09-23 | 727 | 25,237 | 17,011 | 67% |
| 2026-09-24 | 768 | 26,607 | 16,163 | 61% |
| 2026-09-25 | 761 | 24,733 | 15,394 | 62% |
| 2026-09-26 | 448 | 15,134 | 9,199 | 61% |
| **2026-09-28** | 640 | 21,681 | **4,963** | **23%** ← breaks mid-day |
| 2026-09-29 | 656 | 22,305 | **0** | **0%** |
| 2026-09-30 | 708 | 23,696 | **0** | 0% |
| 2026-10-01 | 580 | 20,363 | **0** | 0% |
| 2026-10-05 | 553 | 18,769 | **0** | 0% |
| 2026-10-06 | 617 | 20,677 | **0** | 0% |
| 2026-10-07 | 668 | 23,510 | **0** | 0% |
| 2026-10-08 | 670 | 22,570 | **0** | 0% |
| 2026-10-09 (partial) | 341 | 11,734 | **0** | 0% |

Over the last 3,000 audited requests: **102,532 cards checked, `n_exists` total = 0.**

28 Sept is the day the "evidence-first identity resolution" release went to production. The same
release stopped extension captures from reaching the candidate bank (separately diagnosed and fixed
on 8 Oct — see PRD). Both failures share one cause: a v2 identity path was placed in front of a
working legacy path, and the v2 path is configured never to assert identity.

---

## 2. Component map

| Layer | File | Role |
|---|---|---|
| Card scan + badge paint | `extension/content.js` (~4,200 lines) | finds result cards, batches them, draws the badge |
| HTTP endpoint | `backend/routes/extension_check.py` (~1,100 lines) | `POST /api/extension/check-existing`, validation, allowlist, audit |
| Retrieval | `backend/services/identity_lookup.py` (~640 lines) | turns a card into candidate-code queries, bounded fan-out |
| Scoring + decision | `backend/services/identity_resolution.py` (~790 lines) | weighted signals, rarity, decision + reason codes |
| Code generation | `backend/services/identity_capture.py`, `identity_store.py` | writes `identity.codes` onto a bank record |
| Audit | `backend/routes/badge_audit.py` → `badge_audit` collection | one doc per request, TTL'd |

Collections: `candidate_bank` (188,146 docs), `identity_observations`, `identity_code_stats`
(frequency snapshot), `badge_audit` (15,641 docs), `badge_view_stats`.

---

## 3. Request path, end to end

**Step 1 — scan (browser).** `content.js` observes the result list and extracts per card: name,
current company, designation, location, experience string, skills, and any provider id or profile
URL present in the DOM. Cards are batched into one endpoint call.

**Step 2 — gate.** `_is_user_allowed()` reads env `EXTENSION_CHECK_EXISTING_ALLOWLIST`. Empty ⇒
**everyone refused**; `*` ⇒ all; else a comma-separated email list. A refusal returns
`service_status: "disabled"` plus one `feature_disabled` result per card, so the extension stays
silent rather than erroring — indistinguishable from "no matches" at the UI.

**Step 3 — normalise to codes.** `identity_lookup.retrieval_paths(profile)` converts the card into
*canonical codes* — `canonical_code("full_name", …)`, `("name_token", …)`, `("company", …)`,
`("skill", …)`, `("location", …)`, `("institution", …)` — lowercased, punctuation and noise words
stripped, hashed to a stable string. It then composes **intersection paths**: `full_name + company`,
`full_name + skill`, `name_token + company`, … ordered most to least selective, capped at
`PATH_LIMIT`.

**Step 4 — query.** Each path is one indexed query:

```
db.candidate_bank.find({ "identity.codes": { $all: [<code>, <code>] } })
```

served by `candidate_identity_codes_v1`. Per-path document cap; per-query timeout
`IDENTITY_QUERY_TIMEOUT_S`; whole-batch budget `IDENTITY_BATCH_TIMEOUT_S`; at most
`IDENTITY_MAX_CONCURRENT_PROFILES` cards resolved in parallel. A narrower second set
(`linked_observation_paths`) may read `identity_observations` for historical evidence — name and
context codes only, never URLs or source ids. Every retrieved doc passes through `stored_profile()`,
which strips anything a browser may once have written (see §5c).

**Step 5 — score.** `identity_resolution.resolve_profile(profile, candidates)` scores each
retrieved record with additive weighted signals:

```
name 24 · name_compatible 18 · company 18 · title 12 · employment_cap 24
location 14 · skill 16 · education 10 · experience 6
experience_company 8 · experience_title 5 · experience_location 5
institution 6 · certification 4 · project 3 · language 2
source_id_hint 4 · trusted_source_profile 100
```

Past employment and education are capped below current employment on purpose — a shared ex-employer
is corroboration, not proof. Scores are meant to be **rarity-weighted** from the
`identity_code_stats` frequency snapshot, so a code shared by thousands counts for less.

**Step 6 — decide.** Four possible decisions per card:

| decision | requires | `exists` |
|---|---|---|
| `confirmed_duplicate` | a **trusted source anchor** match (`trusted_source_profile`, 100 pts) | `true` |
| `probable_match` | top score ≥ `PROBABLE_THRESHOLD = 52.0`, no anchor | `false` |
| `insufficient_data` | too few observed fields, or retrieval incomplete/timed out | `false` |
| `no_match` | nothing retrieved or nothing scored | `false` |

Machine-readable `reason_codes` ride along (`insufficient_observed_fields`,
`corpus_frequencies_unavailable`, `unique_trusted_source_profile`, …).

**Step 7 — respond.**

```json
{ "service_status": "ok|disabled|degraded",
  "audit_id": "…",
  "results": [ { "index": 0, "exists": false, "decision": "probable_match",
                 "match_confidence": "medium", "match_score": 58.0,
                 "matcher_version": "…", "reason_codes": ["…"],
                 "candidate_id": null, "profile_url": null } ] }
```

**Step 8 — paint.** `content.js` line 3973:

```js
if (match && res.exists) { markCardAsExisting(match.cardEl, { match_confidence: res.match_confidence, … }) }
```

`markCardAsExisting()` dims the card and injects a clickable `ALREADY IN DATABASE` anchor to the
profile. **`exists === true` is the only gate** — a `probable_match` scoring 95 paints nothing.

**Step 9 — audit.** One `badge_audit` doc per request: user, page URL, batch size, `n_exists`,
`n_high_confidence`, `n_via_naukri_id`, `hit_rate`, `took_ms`, per-card decisions; TTL'd via
`expires_at`.

---

## 4. Measured behaviour

- **Latency** (`badge_audit.took_ms`, last 3,000 requests): median **556 ms**, p90 **4,609 ms**,
  max **9,508 ms**. The tail is the bounded fan-out exhausting its budget, which then reports
  `insufficient_data` — a slow page and a wrong answer together.
- **Volume**: 550-770 scan calls/day, ~20,000-26,000 cards/day, steady before and after the break,
  so recruiters are still using it and getting nothing.
- **Badges shown**: 0/day since 29 Sept; ~62% before 28 Sept.

---

## 5. Why it cannot fire — three independent hard stops

**(a) `confirmed_duplicate` is unreachable by construction.** This is the regression.
`exists` is true only for `confirmed_duplicate`, which needs `anchor_match` — an incoming anchor
present in `_trusted_anchors(candidate)`. `identity_lookup.stored_profile()` does this to every
retrieved record:

```python
effective["_identity_trusted_anchors"] = []   # identity_lookup.py:347
```

in-code rationale: *"A completed capture is an observation, not verification of source-ID
semantics… This endpoint currently has no independently verified provider-ID adapter."* So
`anchor_match` is permanently `False`, `confirmed_duplicate` can never be returned, `exists` is
never `true`, and `content.js` never paints. The module docstring says the same outright: *"No
trusted provider verifier is enabled, so this adapter returns review suggestions, never
exists=true."*

The reasoning is defensible — refuse to assert identity without a verified provider id. The flaw is
that **the UI only consumes certainty** while the engine was deliberately built never to produce it.
The pre-28-Sept path asserted on normalised name + phone/email/provider-id agreement, which is how
it reached 62%.

**(b) 97% of the bank is invisible to retrieval.** Only **6,054 of 188,146** bank records
(**3.2%**) carry an `identity.codes` array. Every retrieval path in §3 queries that single field, so
96.8% of candidates cannot be retrieved at all. `name_lower` exists on 187,985 records (99.9%) — the
backfill meant to populate codes across the corpus never finished. Even if (a) were fixed, recall
would be capped near 3%.

**(c) Rarity weighting is dead.** `identity_code_stats` holds **0 documents** and the `__meta__`
snapshot is **absent**, so every request raises `corpus_frequencies_unavailable`. A match on "Kumar"
scores the same as a rare surname. `PROBABLE_THRESHOLD = 52.0` was calibrated against weighted
scores that are no longer produced, so the threshold is now arbitrary.

---

## 6. Questions for the consultant

1. **Where should the identity bar sit?** Naukri pid/sid and profile URLs are observations, not
   verified ids, and URLs rotate. Is there a defensible anchor at all — or should the UI present
   *likelihood* ("3 possible matches — review") instead of a binary "already in database"?
2. **Is `identity.codes` the right primary index** for a 188k-and-growing corpus, versus
   phone/email normalisation as the key with codes as secondary recall? Note phone and email are
   usually *absent* from a search result card, which is what pushed the design toward codes.
3. **Rarity**: build and maintain the frequency snapshot, or drop rarity and recalibrate the
   threshold against a labelled set?
4. **Precision vs recall.** A false "already in database" costs a recruiter a real lead; a false
   negative costs a duplicate capture, which the capture path already de-dupes on
   phone/email/provider id. That asymmetry argues for high precision — but the pre-28-Sept version
   ran at 62% recall with no complaints on record, and zero recall is worse than either.
5. **Latency budget**: p90 4.6 s against a page that paints in under a second. Is a precomputed,
   denormalised lookup table the right shape instead of per-card fan-out?
6. **Rollout**: is there a case for restoring the legacy matcher behind the badge while the
   evidence-first engine is finished, with its decisions surfaced as a non-blocking "review"
   affordance?

---

## 7. Reproduction and evidence

```bash
# coverage, rarity snapshot, daily badge telemetry, latency, indexes
cd backend && python3 -m scripts.badge_feature_report

# live call (needs an allowlisted user)
curl -X POST "$API/api/extension/check-existing" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"candidates":[{"name":"…","current_company":"…","designation":"…"}]}'
```

Read in order: `routes/extension_check.py` → `services/identity_lookup.py` (`retrieval_paths`,
`lookup_one`, `stored_profile`) → `services/identity_resolution.py` (`WEIGHTS`, `resolve_profile`)
→ `extension/content.js` line 3973 and `markCardAsExisting`. Git: the behaviour changed in the
25 Sept commit `92dc92b`, deployed 28 Sept.
