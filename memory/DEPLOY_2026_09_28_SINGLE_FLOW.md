# Deploy — one flow (pipeline → joining → invoice → payment) + DOJ edit + manual add to mandate

Code-only release. **No migrations to run on EC2.** The legacy-stage migration
(305 `applied` → `sourced`, 36 `employer_approved` → `shortlisted`) was already
executed against the shared Atlas cluster `vhc_talent_os` from preview, so
production data is done. `frontend/yarn.lock` is back in sync with
`package.json`, so `--frozen-lockfile` will not fail this time.

## Ship it

1. Click **Save to Github** in the Emergent chat (pushes to `main`).
2. On the EC2 box:

```bash
cd /home/ubuntu/vhc-platform
git pull
```

The `post-merge` hook runs `scripts/deploy.sh`: pip install (if requirements
changed) → restart `vhc-backend` → healthcheck `127.0.0.1:8001/api/health` →
`yarn build` → rsync to `/var/www/html/` → `nginx -t` + reload.

If the hook is not installed on this box:

```bash
cd /home/ubuntu/vhc-platform
git pull --ff-only origin main
./scripts/deploy.sh --skip-pull
```

Manual fallback (only if `deploy.sh` is missing):

```bash
cd /home/ubuntu/vhc-platform
git pull --ff-only origin main
source venv/bin/activate && pip install -r backend/requirements.txt
sudo systemctl restart vhc-backend
curl -s http://127.0.0.1:8001/api/health
cd frontend && yarn install --frozen-lockfile && yarn build
sudo rsync -a --delete build/ /var/www/html/
sudo nginx -t && sudo systemctl reload nginx
```

## Verify (3 min)

```bash
# 1. Backend healthy
curl -s http://127.0.0.1:8001/api/health

# 2. Old approval process is gone (must be 404)
curl -s -o /dev/null -w "%{http_code}\n" \
  http://127.0.0.1:8001/api/applications/pending-approval

# 3. New payment-due reminder route exists (401/403 = present)
curl -s -o /dev/null -w "%{http_code}\n" \
  -X POST "http://127.0.0.1:8001/api/joinings/payment-reminders/run?dry_run=true"

# 4. Fresh bundle actually reached Nginx
ls -la --time-style=+%H:%M /var/www/html/static/js/ | head -5

# 5. Clean boot
sudo journalctl -u vhc-backend -n 60 --no-pager | grep -Ei "error|traceback|MongoDB|PaymentDue"
```

Expect in the boot log: `[PaymentDue] Monday 10:00 IST reminder scheduled.`
and **no** `[ReportsScheduler]` / `[WeeklyDigest]` lines (those mail crons were
removed).

Then in the browser (hard-refresh once, Ctrl+Shift+R):

- **Joining List** — one row per candidate, DOJ is an editable date field on
  pipeline rows, Joining CTC + Billing Amount save, **Raise Invoice** goes
  straight to Accounts when both figures exist.
- **Bills → Invoices & Payments** — "Raise invoice" opens a dialog in place and
  the URL stays on the bills page (no more bounce to the dashboard).
- **Pipeline** (any role) — pick a mandate → **Add Candidate** → bank search /
  sourced captures / **Upload a CV instead**. Every stage chip moves a card with
  no CTC dialog.
- **Recruiter login** — sidebar shows **Joining List** with DOJ / Candidate /
  Client / Client Position only, and the DOJ can be corrected.

## Live smoke test from your laptop (optional)

```bash
API=https://api.ventureshrd.com   # the production API domain
TOKEN=$(curl -s -X POST "$API/api/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"admin@vhc.in","password":"VhcAdmin@2024"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# joinings deduped + fields present
curl -s "$API/api/joinings?date_from=2026-04-01&date_to=2027-03-31&limit=5" \
  -H "Authorization: Bearer $TOKEN" | head -c 400

# payment-due reminder dry run (sends nothing)
curl -s -X POST "$API/api/joinings/payment-reminders/run?dry_run=true" \
  -H "Authorization: Bearer $TOKEN"
```

## Rollback

`git log --oneline -5` on EC2, then `git reset --hard <previous-sha>` and re-run
`./scripts/deploy.sh --skip-pull`. No schema change to undo; the migrated
applications keep their original value in `legacy_stage`.
