# Deploy Checklist — Phase 55.7 + 55.8
**Run these on the EC2 box, in order. Estimated time: ~10 min.**

## What's shipping

| # | Feature | Files | Already tested |
|---|---|---|---|
| 1 | Bill Generator polish (`line_amount` Optional) | `backend/models/bill.py` | ✅ 11/11 e2e |
| 2 | Auto-deploy script | `scripts/deploy.sh`, `scripts/post-merge.hook` | ✅ syntax + dry-run |
| 3 | Auto-draft Bill on Hired | `backend/services/bill_auto_draft.py`, `backend/routes/applications.py` | ✅ 20/20 unit tests |
| 4 | Tally Bridge backend | `backend/services/tally_xml.py`, `backend/routes/tally_bridge.py`, `backend/server.py` | ✅ 24/24 e2e tests |
| 5 | Tally Bridge agent (Windows) | `tally_bridge/tally_bridge.py`, `tally_bridge/tally_bridge.ini.example` | ✅ one-shot cycle vs fake Tally |
| 6 | Runbooks + PRD updates | `docs/DEPLOY_RUNBOOK.md`, `docs/TALLY_BRIDGE_RUNBOOK.md`, `memory/PRD.md` | — |

**NOT deploying** (parked as requested):
- Marketing website (`marketing_review/` folder — committed but never served by Nginx)
- WhatsApp v2 deep-link page
- Unified RunPod image

---

## Step 1 — Add 2 new env vars on EC2 (one-time)

SSH to EC2, then:

```bash
cd /home/ubuntu/vhc-platform

# Add Tally Bridge token (matches the one already generated in your dev .env)
echo 'TALLY_BRIDGE_TOKEN=vhc_tally_56lldji67Z6jJrdRGwLDQ8dQHzgWqU0LBs0lLUMHmYM' >> backend/.env
echo 'TALLY_TARGET_COMPANY=VENTURE HRD CENTRE PVT LTD' >> backend/.env

# (Optional) Disable auto-draft Bill on Hired if you want to gate it:
# echo 'BILLING_AUTODRAFT_ENABLED=false' >> backend/.env

# Verify
grep -E '^(TALLY_|BILLING_AUTODRAFT)' backend/.env
```

> 📋 The token above was generated in your dev environment. If you want a different one for production, regenerate via:
> ```bash
> python3 -c 'import secrets; print("TALLY_BRIDGE_TOKEN=vhc_tally_" + secrets.token_urlsafe(32))'
> ```
> ⚠️ Whatever value you put on the server MUST match what you'll later put in `tally_bridge.ini` on the Tally Windows PC.

---

## Step 2 — Pull + auto-deploy

```bash
cd /home/ubuntu/vhc-platform
git pull origin main
```

That alone will:
1. Pull new code (backend services, routes, frontend polish)
2. **If the post-merge hook isn't installed yet**, you need to either:
   - **(a) Install the hook now** (recommended):
     ```bash
     chmod +x scripts/deploy.sh scripts/post-merge.hook
     ln -sf ../../scripts/post-merge.hook .git/hooks/post-merge
     # Re-run the deploy manually this one time:
     ./scripts/deploy.sh --skip-pull
     ```
   - **(b) Just run the deploy script once manually**:
     ```bash
     chmod +x scripts/deploy.sh
     ./scripts/deploy.sh --skip-pull
     ```

From the next `git pull` onwards, deploy is automatic (if you went with option a).

---

## Step 3 — Sudoers entry (one-time, for hands-off deploys)

The `deploy.sh` calls `sudo` for `systemctl`, `nginx`, and `rsync`. To avoid password prompts during auto-deploy:

```bash
sudo visudo -f /etc/sudoers.d/vhc-deploy
```

Paste (adjust the username if not `ubuntu`):

```
ubuntu ALL=(root) NOPASSWD: /bin/systemctl restart vhc-backend, \
                            /bin/systemctl reload nginx, \
                            /usr/sbin/nginx -t, \
                            /usr/bin/rsync
```

Save (`Ctrl+X` → `Y` → `Enter` in nano).

---

## Step 4 — Smoke test (1 min)

```bash
# Backend health
curl -sf http://127.0.0.1:8001/api/health | jq

# New Tally endpoints (use the token from Step 1)
TOK=$(grep '^TALLY_BRIDGE_TOKEN=' backend/.env | cut -d= -f2)
curl -s -H "X-Tally-Bridge-Token: $TOK" http://127.0.0.1:8001/api/tally/status | jq
# Should print: {"pending": N, "pushed_total": M, "pushed_today": X, "ts": "..."}

# Auto-draft service smoke
cd backend && source venv/bin/activate && python tests/test_bill_auto_draft.py
# Should print: 20/20 passed
```

Then load `https://ventureshrd.com/admin/bills` in your browser and click around — make sure the existing bills list still renders.

---

## Step 5 — (later, separate machine) Install the Tally Bridge on the Tally PC

This is a **separate one-time task on the Windows PC at the office**, NOT
on EC2. Follow `docs/TALLY_BRIDGE_RUNBOOK.md` step-by-step. Quick summary:

1. In Tally: enable `F11 → ODBC/HTTP Server` on port 9000
2. Ensure these ledgers exist in Tally: `Sales - Placement Consultancy`, `Output IGST @ 18%`, `Output CGST @ 9%`, `Output SGST @ 9%`
3. `mkdir C:\VHCTallyBridge`, copy `tally_bridge.py` + `tally_bridge.ini.example` (rename to `.ini`)
4. Paste the `TALLY_BRIDGE_TOKEN` value into the `.ini`
5. `py -3 -m pip install requests`
6. Test: `py -3 tally_bridge.py --once`
7. Install as Windows service via NSSM (runbook has the GUI steps)

---

## Rollback (if anything breaks)

```bash
cd /home/ubuntu/vhc-platform
git log --oneline -n 5
git reset --hard <previous-commit-sha>
./scripts/deploy.sh --skip-pull
```

Or use Emergent's **Rollback** option in the chat header — free, fastest path.

---

## What changed in production behavior

| Behavior | Before | After |
|---|---|---|
| `git pull` on EC2 | UI stays stale until manual `yarn build` + `rsync` | Auto-deploys with healthcheck (if hook installed) |
| Marking a candidate `hired`/`joined` | Stage changes only | Stage changes **+ a draft bill is auto-created** with CTC × 8.33% on the linked client company. Idempotent. Visible in `/admin/bills`. |
| New endpoints | n/a | `/api/tally/queue`, `/api/tally/ack`, `/api/tally/status` (gated by `X-Tally-Bridge-Token`) |

**Nothing else changes for existing users.**
