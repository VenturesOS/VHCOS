# PHASE 8 — Badge Hover Preview (backend registration + extension rollout)

The heavy lifting is already done: the extension v6.1.0 zip contains the
complete hover-card feature (new `hover-preview.js`, background handler with
5-minute cache, styles, manifest), and `backend/routes/extension_preview.py`
is a complete drop-in route. This phase is registration + verification.

## Paste into Emergent

```
You are working on VHC Talent OS (FastAPI /backend). I have uploaded
extension_preview.py. Register and verify it — do not rewrite it.

TASKS

1. Place the uploaded file at backend/routes/extension_preview.py.

2. Register it in backend/server.py following the existing _safe_import
   pattern: add
     extension_preview_router = _safe_import("routes.extension_preview", "extension_preview_router")
   next to the extension_router import line, and add
   extension_preview_router to the same router include list where
   extension_router is included (same prefix handling).

3. Verify the imports resolve: config.db, utils.auth.get_current_user,
   and the five evaluate_* functions in services/extension_service.py.
   If any evaluator name differs, adapt the IMPORT LINE ONLY — do not
   change the scoring logic.

4. Smoke test with a real candidate id from candidate_bank and a real
   job id:
   - GET /api/extension/candidate-preview/{cid} with a valid recruiter
     Bearer token → 200 with candidate fields (name, phone, email,
     current_salary, expected_salary, notice_period) and fit: null.
   - Same call with ?mandate_id={job_id} → fit.score is an integer
     0-100, fit.factors has color+label per category with data,
     matched_skills/missing_skills are arrays.
   - Nonexistent candidate id → 404. Missing token → 401.
   - Time the mandate call: must be well under 400 ms (it makes no AI
     call — if it is slow, something is wrong; report, don't "fix").

5. Do not modify routes/extension.py, the evaluators, or any extension
   frontend asset.

ACCEPTANCE: show me the two JSON responses (mask phone/email middle
digits in what you print) and the timing.
```

## Extension rollout (manual, outside Emergent)

1. Load `vhc-naukri-extension-v6.1.0` unpacked in Chrome and test on a
   Naukri Resdex results page against your production API: hover a green
   badge → skeleton → card with contact, salary → expected, notice,
   location; with a mandate selected in the popup, the match ring and
   skill chips appear; with none, the amber "Select a mandate" hint.
   Copy buttons flash ✓. Card survives moving the pointer into it;
   Esc/scroll/outside-click dismiss it.
2. Confirm repeat hovers on the same card are instant (cache) and the
   service-worker console logs "Preview served" only on first hover.
3. Roll out to the team the same way previous versions ship: package the
   folder and bump `/api/extension/update.xml` to 6.1.0 so installed
   extensions auto-update.

## Behavior notes

The card reads the SAME active mandate the capture flow stamps
(`vhc_active_mandate` in chrome.storage.sync), so match % always refers
to the mandate the recruiter is currently working — switching mandates
in the popup changes subsequent hovers immediately (per-mandate cache
keys). The score is rule-based (skills 40 / experience 20 / salary 15 /
location 15 / notice 10, renormalized when a category has no data) —
deliberately excluding the AI evaluation so hover stays instant; the
full AI verdict remains available in the existing evaluate-fit flow.
