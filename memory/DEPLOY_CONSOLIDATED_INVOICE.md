# Deploy — Consolidated Invoices + Revenue Rework

Code-only release. **No migrations, no backfill scripts.** The placement
ledger, review-record resolutions and the restored Rajendra Singh Negi row
already live in the shared Atlas DB (`vhc_talent_os`) — preview and prod
point at the same cluster, so the data is already in production. Only the
Python routes and the React bundle need to ship.

## Ship it

1. Click **Save to Github** in the Emergent chat (pushes to `main`).
2. On the EC2 box:

```bash
cd /home/ubuntu/vhc-platform
git pull
```

The `post-merge` hook fires `scripts/deploy.sh`, which does the whole
chain: pip install (if requirements changed) → restart `vhc-backend` →
healthcheck `127.0.0.1:8001/api/health` → `yarn build` → rsync to
`/var/www/html/` → `nginx -t` + reload.

If the hook isn't installed on this box, run it directly:

```bash
cd /home/ubuntu/vhc-platform
git pull --ff-only origin main
./scripts/deploy.sh --skip-pull
```

## Verify (2 min)

```bash
# 1. Backend up, new route present
curl -s http://127.0.0.1:8001/api/health
curl -s -o /dev/null -w "%{http_code}\n" \
  http://127.0.0.1:8001/api/bills/consolidated-invoice   # 401/403 = route exists

# 2. Fresh bundle actually reached Nginx
ls -la --time-style=+%H:%M /var/www/html/static/js/ | head -5

# 3. No errors on boot
sudo journalctl -u vhc-backend -n 40 --no-pager | grep -Ei "error|traceback|MongoDB"
```

Then in the browser (hard-refresh once, Ctrl+Shift+R):

- **Bills → Invoices & Payments** loads with the status filter.
- Type `VECV Sales` in search, wait ~½ second for the debounce → rows filter.
- Tick 2 rows of the same client → the bar shows
  `2 selected · VECV Sales · ₹…` and **Bill 2 on one invoice** is enabled.
- Tick a row from a different client → button greys out with
  *"an invoice can only cover one client"*.
- **Performance Records** shows the reconciliation panel green at 9/9.

Expected totals on prod right now:

| Figure | Value |
|---|---|
| Tracker active revenue | ₹5,28,65,785.81 |
| Platform revenue | ₹4,45,081.30 |
| Company achieved | ₹5,33,10,867.11 |
| Reconciliation | 9 / 9 pass |

## Rollback

```bash
cd /home/ubuntu/vhc-platform
git log --oneline -5
git reset --hard <previous-commit>
./scripts/deploy.sh --skip-pull
```

Safe to roll back: nothing in this release changes schema. A rolled-back
frontend simply loses the consolidated-invoice button; any consolidated
bill already raised stays valid (it's an ordinary multi-line bill).

## Also landing in this deploy

- Shared-office IP no longer triggers login 429 (per-IP limiter fix).
- Repaired PostHog script in `index.html` — this is what was throwing
  the JS syntax error on the live site. Confirm the browser console is
  clean after deploying.
