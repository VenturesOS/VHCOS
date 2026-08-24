# Atlas M10 → Flex Migration Runbook

> **Goal**: Move the `vhc_talent_os` database from a dedicated **M10** cluster to
> MongoDB **Atlas Flex** to kill the cold-cache lag observed on
> `/api/analytics/admin` (~44s cold, ~1.4s cached) and the residual
> `location=*` filter cost on Candidate Bank browse — with zero data loss
> and a documented rollback.
>
> **Owner**: single operator (user), executed against production. Agents may
> **not** run any step in this document against Atlas. All commands are for
> the operator's terminal.
>
> **Read this whole file once before starting.** Total wall-clock: 45–90 min.
> Actual downtime: 2–5 min at cutover (step 8).

---

## 0. Why Flex

M10 gives us a fixed **2 GB RAM / 10 GB storage** working set. Our hot
collections comfortably exceed 2 GB (candidate_bank ~170K docs, api_metrics
~635K docs, plus 25+ auxiliary collections). Every restart / off-peak idle
forces MongoDB to re-page indexes from disk, which is what the 44s cold
Analytics query is showing — the pipeline is index-appropriate, it's just
cold I/O.

Flex is Atlas's new elastic tier (GA 2025-04). Key differences vs M10:

| | M10 | Flex |
|---|---|---|
| Sizing | Fixed 2 vCPU / 2 GB RAM | Auto-scaling RAM (up to 8 GB working set) |
| Storage | 10 GB fixed | Metered, up to 5 GB base + on-demand |
| Cache eviction | Aggressive under 2 GB pressure | Adaptive, keeps hot indexes resident |
| Pricing | ~$60/mo flat | Metered by hours + ops (typically 30-50% cheaper for our load) |
| Dedicated CPU | Yes | Shared but burst-capable |
| Live Migration tool | ✅ | ✅ (M10→Flex path added 2025-Q3) |
| Backup snapshots | Continuous | On-demand + daily |

**Watch-outs**:
- Flex caps at ~8 GB working set. If candidate_bank + indexes grow past
  ~6 GB combined, we'd need M20, not Flex. Current combined size = **~1.6 GB**,
  so headroom is ~4×.
- Flex does not support `$search` (Atlas Search index tier restriction).
  We do not currently use `$search`, but if we ever add it, we bounce back to
  M-tier. Confirm with `db.candidate_bank.getSearchIndexes()` before cutover —
  should return `[]`.
- Flex shared CPU means p99 latency can jitter under noisy-neighbor load.
  Analytics cold-start should still drop from 44s → ~5s because working set
  stays resident; but expect 200-400ms variance on hot queries vs M10's
  ~100ms consistency.

---

## 1. Pre-checks (day before cutover)

Run all of these against the **current M10** and record the numbers in the
Post-Cutover Validation table (step 10). If any check fails, do not proceed.

### 1.1 Working-set size

```bash
# Connect to current M10
mongosh "mongodb+srv://vhc_admin:***@cluster0.vuhdiod.mongodb.net/vhc_talent_os"

use vhc_talent_os
db.stats(1024*1024)         # storage MB
db.stats().dataSize / 1e9   # GB (uncompressed)
```

**Expected**: `dataSize` ≤ 4 GB. If > 5 GB, escalate — Flex is not sized for it.

Per-collection size (top 10):
```javascript
db.getCollectionNames().map(n => ({
  name: n,
  gb: (db[n].stats().size / 1e9).toFixed(2),
  docs: db[n].estimatedDocumentCount()
})).sort((a,b) => b.gb - a.gb).slice(0, 10)
```

Record output → paste into cutover ticket.

### 1.2 Index audit — MUST match after migration

Live Migration copies indexes automatically, but we verify by hash:

```javascript
// Save to file BEFORE migration:
db.getCollectionNames().forEach(c => {
  const idx = db[c].getIndexes().map(i => ({
    name: i.name,
    key: i.key,
    unique: i.unique || false,
    partialFilterExpression: i.partialFilterExpression || null
  }));
  print(JSON.stringify({collection: c, indexes: idx}));
});
```

Redirect to `indexes_before.jsonl`. Repeat after cutover → `indexes_after.jsonl`
→ diff. If any index missing, rebuild it manually (step 11) — do not accept
"eventually consistent" — the Candidate Bank browse regression is directly
caused by missing indexes.

### 1.3 Baseline latency (must beat these after cutover)

```bash
API=https://ventureshrd.com   # or preview URL for dry-run
TOKEN=$(curl -s -X POST "$API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@vhc.in","password":"REDACTED"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# Cold analytics — do this AFTER a 30-min idle period
time curl -s -o /dev/null -w "%{time_total}\n" \
  "$API/api/analytics/admin" -H "Authorization: Bearer $TOKEN"

# Candidate Bank browse (no search)
time curl -s -o /dev/null -w "%{time_total}\n" \
  "$API/api/candidates?limit=50" -H "Authorization: Bearer $TOKEN"

# Location-filtered browse (the slow one)
time curl -s -o /dev/null -w "%{time_total}\n" \
  "$API/api/candidates?limit=50&location=Pune" -H "Authorization: Bearer $TOKEN"

# Autocomplete
time curl -s -o /dev/null -w "%{time_total}\n" \
  "$API/api/candidates/autocomplete?q=weld&field=skills" -H "Authorization: Bearer $TOKEN"
```

Record all four numbers. Post-cutover, each must be ≤ current or within
+10%; Analytics cold and location=Pune must materially improve or the
migration failed its purpose — see rollback (step 12).

### 1.4 Snapshot (safety net)

```
Atlas UI → Cluster0 → Backup → "Take Snapshot Now"
Label: "pre-flex-migration-YYYY-MM-DD"
Retention: 7 days
```

Verify snapshot completes (green check) before starting step 3.

### 1.5 Background workers off

Anything that writes to Mongo continuously during migration will cause
sync lag. In Emergent supervisor:

```bash
# On EC2 (production host)
sudo supervisorctl status | grep -E "runpod|digest|hygiene|autocomplete_vocab"
# Stop only the schedulers — NOT the API server (we need reads until cutover)
sudo supervisorctl stop runpod_sync digest_worker candidate_hygiene_worker
```

Confirm no cron jobs are firing: `crontab -l`.

---

## 2. Provision Flex target

1. Atlas UI → **Create Cluster** → **Flex** tier.
2. Region: **same region as current M10** (AP-South-1 / Mumbai — check the
   current cluster region and match it exactly, cross-region migration adds
   latency to Live Migration).
3. Name: `Flex0` (not Cluster0 — avoids DNS collision during dual-run).
4. MongoDB version: match current M10 version (`db.version()` on M10). Do
   **not** upgrade major version in the same migration. If a version bump is
   needed, do it on M10 first, verify, then migrate.
5. Enable **Backup** (on-demand + daily) — Flex default.
6. Wait for cluster status = **Idle / Green** (~5 min).

Do **not** touch users/network access yet.

---

## 3. Network & user setup on Flex

### 3.1 Network access

Atlas UI → **Flex0** → Network Access → IP Access List.

Copy every entry from M10's list to Flex0's list. Specifically:
- EC2 production static IP (whatever `vhc-backend` connects from)
- Emergent preview egress ranges (if the preview pod connects to prod DB —
  it shouldn't; verify with `grep MONGO_URL` in preview logs before
  assuming)
- Your admin IP (for mongosh)

### 3.2 Database user

Create user with the **same** username/password as M10's `vhc_admin`. Roles:
- `readWrite@vhc_talent_os`
- `dbAdmin@vhc_talent_os` (for index management)

If passwords differ, cutover requires an env change on EC2 too — avoid this,
match the password exactly.

### 3.3 Get the Flex connection string

Atlas UI → Flex0 → Connect → Drivers → Python 3.12+. Copy the SRV URI. It
looks like:

```
mongodb+srv://vhc_admin:<PASSWORD>@flex0.xxxxx.mongodb.net/?retryWrites=true&w=majority&appName=Flex0
```

Save this — you'll swap it into `backend/.env` at step 8.

---

## 4. Choose migration path

Two supported paths. Use **4A (Live Migration)** unless it's unavailable.

### 4A. Live Migration (preferred, near-zero downtime)

Atlas UI → M10 (Cluster0) → **… menu** → **Migrate this cluster** →
"To another Atlas cluster" → select **Flex0**.

Atlas will:
1. Initial sync (~15-40 min for our data size, monitored in UI).
2. Apply live oplog until you press "Cut over".
3. Freeze M10 writes when you press cut-over, apply last oplog batch,
   release Flex0 for writes.

**During sync**:
- Writes continue to M10 (the app is unaffected).
- Sync lag shown in Atlas UI must reach **< 60 s** before you can cut over.
- Do not press "Cut over" yet — that's step 8.

### 4B. mongodump / mongorestore (fallback if Live Migration is unavailable)

Only use if Atlas UI says Live Migration is not offered for M10→Flex path in
your region. Requires ~5-8 min actual downtime.

```bash
# From a machine with fast link to Atlas (ideally EC2 itself)
mkdir -p /tmp/vhc_dump && cd /tmp/vhc_dump

# Dump (M10)
mongodump \
  --uri "mongodb+srv://vhc_admin:***@cluster0.vuhdiod.mongodb.net/vhc_talent_os" \
  --gzip --numParallelCollections 4 \
  --out ./dump

# ~15-30 min. Size check:
du -sh dump/
```

Do NOT restore yet — restore happens during cutover window (step 8B).

---

## 5. Dry-run validation on Flex (before cutover)

Once Live Migration reports **"Ready to cut over"** (or after 4B dump completes):

```bash
# Connect to Flex0 read-only from your laptop
mongosh "mongodb+srv://vhc_admin:***@flex0.xxxxx.mongodb.net/vhc_talent_os"

use vhc_talent_os

# Doc counts must match M10's within ±0.01% (any diff = still syncing)
db.candidate_bank.estimatedDocumentCount()
db.users.estimatedDocumentCount()
db.applications.estimatedDocumentCount()
db.api_metrics.estimatedDocumentCount()

# Sanity queries — should return real data, not empty
db.candidate_bank.findOne({}, {name:1, email:1, mobile:1})
db.users.findOne({role:"admin"}, {email:1, is_active:1})

# Index count per hot collection — must match indexes_before.jsonl
db.candidate_bank.getIndexes().length
db.applications.getIndexes().length
db.api_metrics.getIndexes().length
```

If counts drift or indexes differ, **do not cut over**. Debug or fall back
to 4B path.

---

## 6. Peak-hour check

Cutover requires 2–5 min of write freeze. Schedule the cutover for the
lowest-traffic window:

```javascript
// On M10 — traffic by hour (IST)
db.api_metrics.aggregate([
  { $match: { ts: { $gte: new Date(Date.now() - 7*24*3600*1000) } } },
  { $group: {
      _id: { $hour: { date: "$ts", timezone: "Asia/Kolkata" } },
      calls: { $sum: 1 }
  }},
  { $sort: { calls: 1 } },
  { $limit: 5 }
])
```

Pick a low-traffic hour (typically 03:00-05:00 IST for our workload).
Notify any users who might be logged in.

---

## 7. Pre-cutover checklist (T-15 min)

- [ ] Snapshot verified (step 1.4)
- [ ] `indexes_before.jsonl` saved
- [ ] Baseline latencies recorded (step 1.3)
- [ ] Background workers stopped (step 1.5)
- [ ] Flex0 provisioned, users + network match M10 (steps 2–3)
- [ ] Live Migration reports **Ready to cut over** with lag < 60s (step 4A)
      OR dump completed and staged (step 4B)
- [ ] Dry-run counts + indexes match (step 5)
- [ ] Low-traffic window active (step 6)
- [ ] `backend/.env` change ready but NOT applied — line 1 to become:
      `MONGO_URL="mongodb+srv://vhc_admin:***@flex0.xxxxx.mongodb.net/?retryWrites=true&w=majority&appName=Flex0"`
- [ ] Rollback plan re-read (step 12)

---

## 8. Cutover (the actual 2–5 min downtime)

### 8A. Live Migration cutover

1. On EC2 (production host):
   ```bash
   sudo systemctl stop vhc-backend
   # This is what the deploy runbook uses; adjust if the unit name differs.
   ```
   The site now returns 502 briefly. **Start your stopwatch.**

2. Atlas UI → Live Migration → **Cut over**. Atlas will:
   - Freeze writes on M10 (they'll be rejected — but backend is stopped, so
     no writes will attempt anyway)
   - Apply final oplog batch to Flex0
   - Release Flex0 for writes
   Expected: 60-90 seconds.

3. When cutover reports **Complete**:
   ```bash
   # Edit /app/backend/.env on EC2 — update MONGO_URL line only
   sudo nano /app/backend/.env
   # Change line 1 to the Flex0 SRV URI. Do NOT touch DB_NAME.

   sudo systemctl start vhc-backend
   sudo journalctl -u vhc-backend -f -n 50
   ```
   Look for `MongoDB connection OK` (or equivalent — check startup logs).
   Look for `RunPodSync API HTTP 401` — pre-existing warning, ignore for now.

4. **Stop your stopwatch.** Target: < 5 min. Record actual downtime.

### 8B. mongodump/mongorestore cutover (fallback path)

```bash
# On EC2:
sudo systemctl stop vhc-backend

# Freeze M10 writes cosmetically (there are none since backend is down):
# — nothing to do; just don't run any manual writes.

# Restore to Flex0
mongorestore \
  --uri "mongodb+srv://vhc_admin:***@flex0.xxxxx.mongodb.net/vhc_talent_os" \
  --gzip --numParallelCollections 4 --noIndexRestore=false \
  /tmp/vhc_dump/dump

# ~5-15 min depending on network. Then swap env + start:
sudo nano /app/backend/.env    # change MONGO_URL to Flex0
sudo systemctl start vhc-backend
```

---

## 9. Smoke test (T+2 min after cutover)

Use the **live production URL** (not preview) and the admin token:

```bash
API=https://ventureshrd.com
TOKEN=$(curl -s -X POST "$API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@vhc.in","password":"REDACTED"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# Must return 200 with real counts
curl -s "$API/api/candidates?limit=1" -H "Authorization: Bearer $TOKEN" | head -c 400
curl -s "$API/api/analytics/admin"    -H "Authorization: Bearer $TOKEN" | head -c 400
curl -s "$API/api/notifications"      -H "Authorization: Bearer $TOKEN" | head -c 400

# Extension endpoint (used by Chrome extension every capture)
curl -s -o /dev/null -w "%{http_code}\n" "$API/api/extension/job-info?job_id=any"
```

Any 500 → **rollback (step 12)**. 4xx on the last one is fine (unknown job_id).

---

## 10. Post-cutover validation (compare vs step 1.3 baseline)

| Endpoint | M10 baseline | Flex target | Actual | Pass? |
|---|---|---|---|---|
| `/api/analytics/admin` (cold) | 44s | ≤ 10s | | |
| `/api/analytics/admin` (warm) | 1.4s | ≤ 2s | | |
| `/api/candidates?limit=50` | 3.4s | ≤ 3.4s | | |
| `/api/candidates?location=Pune&limit=50` | 16.5s | ≤ 6s | | |
| `/api/candidates/autocomplete?q=weld` | 2.8s | ≤ 2s | | |

Cold Analytics must fall dramatically — that's the primary migration goal.
If it doesn't, Flex tier isn't the bottleneck; the underlying aggregation
needs profiling instead. In that case, keep the migration (it still helps
capacity) and file a follow-up ticket for aggregation refactor.

Also compare indexes:

```bash
# On Flex0
mongosh "mongodb+srv://vhc_admin:***@flex0.xxxxx.mongodb.net/vhc_talent_os" \
  --eval 'db.getCollectionNames().forEach(c => {
    const idx = db[c].getIndexes().map(i => ({name:i.name,key:i.key,unique:i.unique||false}));
    print(JSON.stringify({collection:c,indexes:idx}));
  })' > indexes_after.jsonl

diff <(sort indexes_before.jsonl) <(sort indexes_after.jsonl)
```

Must be empty diff.

---

## 11. Restart background workers

Only after step 10 passes:

```bash
sudo supervisorctl start runpod_sync digest_worker candidate_hygiene_worker
# Or, if using systemd for these too:
sudo systemctl start vhc-runpod-sync vhc-digest vhc-hygiene
```

Watch logs for 5 minutes:

```bash
sudo journalctl -u vhc-backend -f
```

Expected: normal traffic, no repeated 500s, api_metrics collection growing
on Flex0 (`db.api_metrics.estimatedDocumentCount()` increasing).

---

## 12. Rollback plan

**Trigger rollback if any of these are true within 15 min of cutover:**
- `/api/candidates` returns 500 or > 30s consistently
- Cold Analytics is *worse* than M10 baseline
- Doc counts on Flex0 diverged from M10 pre-cutover snapshot
- Sync lag on the still-alive M10 (Live Migration mode only) was > 60s at
  cut-over — final oplog may not have applied

### Rollback steps

```bash
# 1. Stop backend
sudo systemctl stop vhc-backend

# 2. Revert /app/backend/.env line 1 to the M10 URI
sudo nano /app/backend/.env

# 3. Start backend
sudo systemctl start vhc-backend

# 4. Smoke test against M10 (same commands as step 9)
```

**Live Migration mode**: M10 is still online for 72 hours after cutover
(Atlas keeps it in read-only mode by default). Rollback is safe — writes
that happened on Flex0 during those 15 min are lost, but there were few
because it was a low-traffic window.

**Dump/restore mode**: M10 was never touched. Rollback is trivial (just
swap the env back). Writes on Flex0 are lost (again, minimal in the
window).

After a rollback:
1. File a ticket documenting the failure mode.
2. Do not retry migration until root cause is fixed.
3. Delete Flex0 cluster to stop billing.

---

## 13. Decommission M10 (T+7 days)

Only after 7 days of stable Flex0 operation:

1. Atlas UI → Cluster0 (M10) → **… menu** → **Terminate**.
2. Type the cluster name to confirm.
3. Verify billing dashboard shows M10 → $0 and Flex0 → active.
4. Delete `pre-flex-migration-YYYY-MM-DD` snapshot after another 7 days
   (kept as second safety net).

Do not skip the 7-day dwell. Cold-cache issues can surface a day later
under weekly digest / Monday-morning login spike load, and rolling back is
significantly harder after M10 is gone.

---

## 14. Post-migration to-do (follow-up items)

These are NOT blockers for the migration but should be scheduled after
stabilization:

- [ ] Re-run the `/api/analytics/admin` cold profile. If still slow, refactor
      the underlying aggregation (likely `analytics_service.py`) — cache
      already exists (1.4s warm) so this is an optimization, not a bug.
- [ ] Re-profile `location=*` candidate filter. If still slow, add compound
      index `{location_normalized: 1, updated_at: -1}` — Flex is fine, this
      is a schema issue.
- [ ] Fix `RunPodSync HTTP 401` at startup (unrelated to migration but the
      restart during cutover will re-expose it; either provision the
      credential or disable the worker).
- [ ] Update `/app/memory/PRD.md` and `/app/memory/PLATFORM_AUDIT_2026_08.md`
      with actual post-migration latency numbers from step 10.
- [ ] Delete this runbook or move it to a `completed_migrations/` folder
      once stable and decommission is done.

---

## 15. Contact / escalation

- **Atlas support**: chat via Atlas UI (paid support included with Flex).
- **Cutover blocker**: rollback first (step 12), then debug — do not
  attempt in-place fixes on a broken production DB.
- **Data mismatch discovered after 7 days**: restore from the
  `pre-flex-migration` snapshot into a new cluster and compare — do not
  overwrite live Flex0.

---

_Written 2026-08. Applies to `vhc_talent_os` on Atlas M10 Cluster0 →
Flex0 in AP-South-1. Update this doc if either cluster is renamed or
if MongoDB version differs from what step 2 assumed._
