# Phase 52 — Capture Deduplication + View Pipeline Deep-Link (2026-05-06)

## Two Features in One Release

### 1. View Pipeline Deep-Link (UX) — Frontend
Recruiters can now jump from a Submission Tracker straight into the underlying job's pipeline view.

- **Tracker list cards:** small `ExternalLink` icon (emerald) appears on hover next to the row count → opens `/admin/pipeline?job_id=<mandate_id>`
- **Tracker spreadsheet header:** prominent "View Pipeline" button next to "Add Candidate" → same destination

The Pipeline pages already accepted `?job_id=` query param — no backend change needed.

### 2. Capture Deduplication (Cost) — Backend
Skip the expensive Qwen + embedding pipeline when a profile is re-captured within a freshness window AND the raw text is identical.

**Decision matrix** (`backend/routes/extension.py:_should_skip_enrichment`):
| Existing record | Decision | Reason tag |
|---|---|---|
| New candidate (first capture) | RUN Qwen | `no_existing` |
| Empty raw text | SKIP | `no_raw_text` |
| Previously failed enrichment | RUN Qwen (retry) | `previous_not_enriched` |
| Enriched but missing hash baseline | RUN Qwen | `no_baseline` |
| Last enrichment > 7 days old | RUN Qwen (refresh) | `stale` |
| < 7 days but raw text hash changed | RUN Qwen (data updated) | `text_changed` |
| < 7 days AND identical raw text | **SKIP Qwen + embedding** ✅ | `fresh_unchanged` |

**Tunable:** `CAPTURE_DEDUP_FRESH_DAYS` env var (default 7). Set to 0 to disable.

## What Doesn't Change (Critical Guarantees)

- ✅ Candidate ALWAYS gets tagged to the mandate selected in the extension
- ✅ Candidate ALWAYS appears in "Add Candidate" tab for the recruiter
- ✅ Candidate visibility / assignments / activity log all still update
- ✅ `last_seen`, recruiter linkage, capture audit log all still work
- ⚡ Only the AI enrichment (Qwen call + 384-d embedding generation) is short-circuited

## Audit Logging

Every dedup decision is logged with `[Dedup]` prefix:

```
[Dedup] SKIP_QWEN 'Rohan Sharma' (reason=fresh_unchanged, candidate_id=ca2725d4-106)
[Dedup] SKIP_QWEN 'Priya Patel' (reason=fresh_unchanged, candidate_id=8d13ed68-d90, path=auto_merge)
[Extension-UPDATE] ⚡ Triggering FULL GROQ enrichment for 'Amit Singh' (dedup_decision=text_changed)
```

Run a daily count to verify savings:
```bash
sudo journalctl -u gunicorn --since today | grep -c "Dedup.*SKIP_QWEN"
sudo journalctl -u gunicorn --since today | grep -c "Layer1-RunPod.*SUCCESS"
```

## Files Changed

- `backend/routes/extension.py` — added `_should_skip_enrichment()`, applied at UPDATE + auto-merge call sites; `_apply_bg_enrichment` now persists `raw_text_hash`
- `frontend/src/pages/admin/SubmissionTrackerPage.jsx` — added `useNavigate`, `ExternalLink` icon, two deep-link entry points

## Deployment on EC2

```bash
ssh ubuntu@<ec2>
cd /home/ubuntu/vhc-platform
git pull --rebase origin main
sudo systemctl restart gunicorn
sleep 5

# Then rebuild the frontend so the deep-link buttons appear
cd frontend
yarn build
# (your nginx serves frontend/build/ — no separate restart needed)
```

## Verification

```bash
# 1. Confirm dedup helper is wired
grep -c "_should_skip_enrichment" /home/ubuntu/vhc-platform/backend/routes/extension.py
# EXPECTED: 3 (1 definition + 2 call sites)

# 2. After 30 min of live traffic, see dedup decisions in logs
sudo journalctl -u gunicorn --since "30 min ago" | grep "Dedup" | head -10

# 3. Daily savings counter (run end-of-day)
echo "Dedup skips: $(sudo journalctl -u gunicorn --since today | grep -c 'Dedup.*SKIP_QWEN')"
echo "Qwen calls:  $(sudo journalctl -u gunicorn --since today | grep -c 'Layer1-RunPod.*SUCCESS')"
echo "Total upd:   $(sudo journalctl -u gunicorn --since today | grep -c 'Extension] UPDATE')"
```

## Rollback (Instant)

If anything looks off, set the freshness window to 0 and dedup deactivates without code change:

```bash
echo "CAPTURE_DEDUP_FRESH_DAYS=0" | sudo tee -a /home/ubuntu/vhc-platform/backend/.env
sudo systemctl restart gunicorn
```

## Expected Impact

- **Today:** ~30-40% of UPDATE captures hit the `fresh_unchanged` path (team-wide re-captures of the same profiles)
- **Cost saved:** Roughly ₹2,000-4,000/mo in RunPod GPU hours + EC2 CPU on embeddings
- **Side benefit:** Faster `[Extension] UPDATE` response time (no Qwen wait) for the recruiter
