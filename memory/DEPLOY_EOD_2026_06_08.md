# Deploy Checklist — 2026-06-08 EOD

Three operator tasks. Run on the **AWS EC2 host** as root (or via sudo)
**after** "Save to Github" → `git pull` on the box.

---

## 0. Pull latest code on AWS

```bash
cd /app   # or wherever your VHC repo lives on AWS
git pull origin main
sudo systemctl restart vhc-backend
sudo systemctl status vhc-backend --no-pager | head -10
```

---

## 1. (P2) Populate prod `search_sessions` from application history

One-shot backfill. Idempotent — safe to re-run. Expected: ~1,900 docs
written (one per non-`sourced` application stage).

```bash
cd /app/backend
sudo -u $(stat -c '%U' /app/backend) /root/.venv/bin/python -m scripts.backfill_search_sessions --apply
# Or if you run as root already:
/root/.venv/bin/python -m scripts.backfill_search_sessions --apply
```

**Verify:**

```bash
# Should show n_actions jump from ~3 to ~1,900+
TOKEN=$(curl -s -X POST https://<your-domain>/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@vhc.in","password":"<your-admin-pw>"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -s "https://<your-domain>/api/admin/ltr/stats?days=365" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -m json.tool | grep -E "n_sessions|n_actions|ltr_model" -A 1
```

Expected:
- `n_actions: 1900+`
- `ltr_model.available: true` (after one search lazy-loads the model)
- `ltr_model.ab_pct: 10`

---

## 2. (P2) Add weekly LTR retrain crontab

```bash
sudo mkdir -p /var/log/vhc
sudo touch /var/log/vhc/ltr-retrain.log
sudo chown $(stat -c '%U' /app/backend) /var/log/vhc/ltr-retrain.log

# Add to root crontab (or whichever user owns /app/backend)
sudo crontab -e
```

Append this line:

```cron
0 3 * * 0 /app/backend/scripts/retrain_ltr_cron.sh >> /var/log/vhc/ltr-retrain.log 2>&1
```

Save + exit. **Verify:**

```bash
sudo crontab -l | grep ltr-retrain
# Run once manually to confirm the script + path work (exits 1 if <5000 triplets, that's OK):
sudo /app/backend/scripts/retrain_ltr_cron.sh
tail -20 /var/log/vhc/ltr-retrain.log
```

---

## 3. (P3) Raise Gunicorn `--max-requests` 500 → 1500

```bash
sudo systemctl edit vhc-backend
```

Find the `--max-requests 500 --max-requests-jitter 30` line in the
override and change to:

```ini
[Service]
ExecStart=
ExecStart=/usr/bin/gunicorn server:app \
  -w 3 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8001 \
  --max-requests 1500 \
  --max-requests-jitter 100 \
  ... (keep all other flags as-is)
```

Apply:

```bash
sudo systemctl daemon-reload
sudo systemctl restart vhc-backend
sudo systemctl status vhc-backend --no-pager | head -15
```

**Verify flags loaded:**

```bash
ps -ef | grep gunicorn | grep -v grep
# Should show --max-requests 1500 --max-requests-jitter 100
```

**Soak test (next 2–3 hours):**

```bash
watch -n 60 'ps -eo pid,rss,cmd | grep gunicorn | grep -v grep | \
  awk "{rss=\$2/1024; printf \"%s %.0f MB %s\\n\", \$1, rss, \$NF}"'
```

Workers should stay flat ~900 MB. If any climbs >3 GB, **rollback** by
reverting the override to `--max-requests 500 --max-requests-jitter 30`,
`daemon-reload`, `restart`.

---

## When all 3 are green

- `/api/admin/ltr/stats` shows `n_actions ≥ 1900` ✓
- `crontab -l` shows the weekly entry ✓
- `ps -ef | grep gunicorn` shows `--max-requests 1500` ✓
- Worker RSS flat across the 2-3h soak ✓

You're done. See you tomorrow 👋
