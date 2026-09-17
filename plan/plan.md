# MongoDB cost reduction — options, and why 3-cluster name sharding is the wrong one

## 1. The proposal on the table

Split `candidate_bank` across three Atlas Flex clusters by first letter of candidate name
(A–L, M–X, Y–Z + everything else), replacing one M10 at roughly USD 70–80/month with
three Flex clusters at roughly USD 7–8/month each.

The cost goal is right. The mechanism is the problem, and there is a cheaper path that does
not touch the application at all.

## 2. Numbers that decide this

Atlas Flex (current published limits):

| Property | Flex | M10 |
|---|---|---|
| Price | USD 8/month base, capped at USD 30/month | ~USD 57/month + storage + backup |
| Included throughput at base price | 100 ops/sec | dedicated 2 vCPU |
| Max throughput | 500 ops/sec, then operations are queued with a cooldown | no hard cap |
| Max storage | 5 GB **per cluster** | 10 GB, expandable |
| Atlas Search / Vector Search | supported | supported |
| CPU | shared, burst-capable | dedicated |

Two consequences:

- **Flex is not billed at USD 7 once it is doing real work.** It is USD 8 only up to
  100 ops/sec, then USD 15 / 21 / 26 / 30 as throughput climbs. Three clusters carrying live
  recruiter traffic realistically land at USD 45–90/month, not USD 21 — possibly no cheaper
  than the M10, with none of its guarantees.
- **The database very likely already fits in one 5 GB Flex cluster.** The last recorded
  sizing (roughly 170k candidates, all 25+ collections, data + indexes) was about
  **1.6 GB**. If that is still broadly true, splitting the data three ways solves a storage
  problem that does not exist.

The real driver of the M10 bill is the dedicated tier itself (plus storage and backup),
not the size of the candidate data.

## 3. What 3-cluster name sharding would actually cost in behaviour

Name-initial routing only helps when a query already knows the name. Most of this
application's hot paths do not:

- **Duplicate detection** — the extension badge and capture flow look candidates up by
  phone, email and Naukri ID. None of those tell you which cluster the candidate is in, so
  every check has to hit all three clusters and merge results. The 16k+ badge scan calls per
  30 days become 3x the operations, spread across three throughput-capped clusters.
- **Counts and filters** — the Candidate Data Bank headline count, the alphabetical
  Location / Company / Skills dropdowns and the Salary Benchmark aggregations currently run
  as single pipelines over one collection. Each becomes three pipelines plus a merge step in
  application code, and "total" numbers stop being a single database answer.
- **Sorting and pagination** — any sort that is not by name (recency, salary, experience,
  match score) can no longer be paged by the database. Correct paging across three clusters
  requires over-fetching from each and re-sorting in memory.
- **Joins and consistency** — applications, jobs, revenue and embeddings live in the third
  cluster while most candidates live in the other two. Cross-cluster `$lookup` and
  multi-document transactions do not exist. Any write that spans a candidate and an
  application can half-succeed.
- **Data movement** — a corrected name or a re-capture can change a candidate's initial,
  which means physically moving the document between clusters and keeping references valid.
- **Semantic search** — the vector index would be split across clusters, so similarity
  search becomes three searches plus a merge, with no global ranking guarantee.
- **Operations** — three connection pools, three backup policies, three sets of indexes to
  keep in step, three places to look when something is slow. The per-cluster 500 ops/sec
  ceiling still applies, and fan-out multiplies the operations being counted against it.

This pattern was already evaluated and set aside earlier in the project for these reasons.
It is recorded as rejected in the current roadmap. Nothing about the invoice changes the
engineering trade-off; it only raises the pressure to act, and there are cheaper actions.

## 4. Recommended path

**Step 1 — confirm the three numbers that decide everything (no code, Atlas console only).**
Current `dataSize` + index size, peak and sustained ops/sec over the last 30 days, and the
line-item breakdown of the invoice (cluster tier vs storage vs backup/PITR vs data transfer).
If the 10x jump is mostly backup/PITR or transfer, the fix is a setting, not a migration.

**Step 2 — take the free money first.** A USD 500 MongoDB startup credit was awarded to this
account. If it is active, it covers roughly six to seven months of the current M10 bill,
which buys time to do the storage diet below and migrate calmly rather than under pressure.
Worth confirming activation, eligible charges and expiry before any migration work.

**Step 3 — put the database on a diet.** This lowers cost on any tier and is what makes a
single Flex cluster comfortable:
- Operational logs dominate document counts (api_metrics, activity_logs, badge_audit,
  extraction_traces, naukri_capture_logs — hundreds of thousands of rows). Retention windows
  already exist; tightening them is the cheapest storage win available.
- Raw captured profile text and resume blobs stored inline on candidate documents are the
  largest per-document cost. Moving them to object storage and keeping only a reference
  shrinks both storage and the working set the cluster has to keep in RAM.
- Audit the indexes: unused indexes cost storage and slow writes.

**Step 4 — move to a single Flex cluster, with a defined rollback.** One cluster, no
application changes, Atlas Live Migration, one short cutover window. Expected bill:
USD 8–30/month depending on measured throughput — the same or better than the three-cluster
plan, with none of its correctness problems. Accept in advance that shared CPU means more
latency variance than M10, and that sustained traffic above 500 ops/sec triggers queuing;
Step 1's throughput number tells us whether that is a real risk. If it turns out the workload
genuinely exceeds Flex, the honest comparison is M10 with a smaller storage/backup
configuration, or self-hosting (Step 5) — not three Flex clusters.

**Step 5 — only if Flex proves too small: self-host MongoDB on the existing EC2 host.**
Removes the Atlas bill entirely and the data stays on infrastructure already being paid for.
In exchange, backups, upgrades, monitoring and failure recovery become ours, and the host has
a history of memory pressure that would need headroom planning first. This is a real option,
but it trades money for operational risk and should be a deliberate choice, not a fallback.

## 5. If sharding is still wanted

If the decision is to proceed with multi-cluster splitting anyway, the version worth building
is **not** by name initial. Split by **age/temperature**, not alphabet:

- One primary cluster holds all operational data plus candidates touched in the last N months.
- One archive cluster holds cold candidates that are only ever read by direct lookup or
  reactivated into the primary.
- Routing is one rule ("is this candidate hot or cold"), lookups by phone/email/Naukri ID
  still work against the primary, counts and dropdowns stay single-cluster for live data, and
  cold data can be re-fetched on demand.

That still costs real work — a routing layer, a promotion/demotion job, a reconciliation
report, and accepting that archive-only searches are slower — but it does not break dedupe,
counts, sorting or transactions the way alphabetical splitting does.

## 6. Assumptions recorded

- The ~1.6 GB combined data+index figure from the earlier audit is still directionally right;
  Step 1 confirms it before anything is committed.
- No Atlas Search (`$search`) indexes are in use today, so the Flex feature set is sufficient.
- Preview and production point at the same Atlas cluster today; any migration has to account
  for both connection strings, and no migration step will be executed by an agent — cutover
  stays with the operator.
- Deleting data (log retention, archiving) needs explicit approval per collection before it
  runs, as agreed previously.

## 7. Open question to settle before Step 4

Is the USD 500 credit active on this organisation? If yes, the sensible order is
diet → measure → migrate on our own schedule. If no, the migration becomes the urgent item
and the diet happens after.

---

## Appendix — AWS production update commands (requested)

Run on the EC2 host as the deploy user. Repo `/home/ubuntu/vhc-platform`, service
`vhc-backend` (not `gunicorn`), frontend served from `/var/www/html`.

```bash
# 1. Pull latest code
cd /home/ubuntu/vhc-platform
git status                 # confirm clean tree before pulling
git pull origin main

# 2. Backend dependencies (only if requirements.txt changed)
source .venv/bin/activate  # adjust if the venv lives elsewhere
pip install -r backend/requirements.txt

# 3. Restart the API
sudo systemctl restart vhc-backend
sudo systemctl status vhc-backend --no-pager
curl -s https://ventureshrd.com/api/health

# 4. Rebuild and publish the frontend
cd /home/ubuntu/vhc-platform/frontend
yarn install --frozen-lockfile
yarn build
sudo rsync -a --delete build/ /var/www/html/

# 5. Tail logs if anything looks wrong
sudo journalctl -u vhc-backend -n 100 --no-pager
```

Notes: use `https://ventureshrd.com/api/health` for the health check — the
`app.ventureshrd.com` hostname has a certificate-name mismatch. Do not disable TLS
verification to work around it.
