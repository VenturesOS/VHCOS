# Phase 51 — Option A: LLM Architecture Simplification (2026-05-05)

## What Changed

**Before:**
```
Qwen (RunPod) → Anthropic Direct (4-key rotation) → Emergent Haiku
                ❌ Triggered "credit balance too low" outage May-05
```

**After (Option A):**
```
Qwen (RunPod) → Emergent Haiku (last-resort fallback only)
✅ Single Emergent billing channel, simpler ops
```

The "strict-Qwen" policy is preserved: if the RunPod pod is REACHABLE but
Qwen still couldn't parse, the call refuses to fall back to Emergent (saves
money on edge cases — the candidate is tagged `qwen_reachable_unrecovered`
for later retry).

## Files Changed
- `backend/services/llm_fallback_service.py`
  - Removed Layer 2 (Anthropic Direct) entirely
  - Removed `_call_anthropic_direct()` function (~50 lines)
  - Set `ANTHROPIC_API_KEY = None` at top
  - Renamed Layer 3 logs → Layer 2
- `backend/services/llm_service.py`
  - Removed Direct Anthropic SDK 4-key rotation block (~50 lines)
  - Updated docstring

## Deployment on EC2

```bash
ssh ubuntu@<ec2>
cd /home/ubuntu/vhc-platform
git pull origin main
sudo systemctl restart gunicorn
sleep 5
sudo systemctl status gunicorn --no-pager | head -10
```

## Verification (after 5 min of live traffic)

```bash
# Should be ZERO Anthropic Direct calls in logs
sudo journalctl -u gunicorn --since "5 min ago" | grep -ci "anthropic.*key#\|Layer2-Anthropic\|credit balance too low"
# EXPECTED: 0

# Confirm Qwen primary still working
sudo journalctl -u gunicorn --since "5 min ago" | grep -c "Layer1-RunPod.*SUCCESS"
# EXPECTED: > 0

# Confirm Emergent fallback wired correctly (only fires if pod unreachable)
sudo journalctl -u gunicorn --since "5 min ago" | grep -c "Layer2-Emergent"
# EXPECTED: 0 if pod is up; small number if pod was briefly down
```

## Optional Cleanup

The `ANTHROPIC_API_KEY` and `ANTHROPIC_API_KEY_2/3/4` lines in
`/home/ubuntu/vhc-platform/backend/.env` are now **unused** (code never
reads them). You can safely delete them when convenient:

```bash
cd /home/ubuntu/vhc-platform/backend
cp .env .env.backup-anth-$(date +%Y%m%d)
sudo sed -i '/^ANTHROPIC_API_KEY/d' .env
grep ANTHROPIC .env  # should show nothing
sudo systemctl restart gunicorn
```

This is purely housekeeping — leaving them in place causes no harm.

## Cost Impact

- **Before:** Anthropic Direct billed at $0.80/M input + $4/M output (Haiku
  4.5 list pricing) on top of Emergent billing
- **After:** Emergent Universal Key only — single bill, simpler budgeting,
  auto-topup possible from Profile → Universal Key
- **Estimated savings:** Variable, but you saw "credit balance too low" in
  logs at 12:57:34 on May 5 → that account had been receiving traffic that
  will now route through Emergent only.
