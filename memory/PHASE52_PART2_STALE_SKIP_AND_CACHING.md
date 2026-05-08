# Phase 52 (Part 2) — Stale Skip + Read Endpoint Caching (2026-05-06)

## Summary of This Release

Two complementary cost optimizations:

### A. Stale Candidate Skip (Backfill scripts)
Both `backfill_talent_graph.py` and `backfill_and_retry_ai_tags.py` now
support skipping cold candidates — those that:
- Already enriched (`enrichment_status=enriched`)
- Have **no** entry in the `applications` collection (never assigned to any mandate)
- Were created > N days ago (default 90)

This represents one-time recruiter captures that nobody ever acted on —
re-embedding/re-enriching them on the next backfill run is pure waste.
When a recruiter does engage one later, the live capture path
(`extension.py:_should_skip_enrichment`) handles re-enrichment via the
raw_text_hash check.

**New CLI flags:**
```bash
# Talent graph backfill
python3 scripts/backfill_talent_graph.py --skip-cold-days 90

# AI tag retry (the script that ran during May-05 OOM)
python3 scripts/backfill_and_retry_ai_tags.py --retry --skip-cold --since-days 7
```

### B. Aggressive Read Endpoint Caching
Two top-traffic endpoints now use Redis (Upstash) caching:

| Endpoint | TTL | Mongo work saved |
|---|---|---|
| `GET /api/admin/stats/admin` | 90s | ~10 aggregations per dashboard load |
| `GET /api/public/jobs` | 5 min | Full table scan + regex matching |

**Verified in dev pod:** public jobs endpoint went from 4.9s (cold) to 1.5s (cached) — ~3x faster locally; on production with internet RTT it'll be a 5-10x perceived speedup.

The cache is **graceful** — if Upstash is unreachable, the endpoint just falls back to direct Mongo (no error to the user).

## Files Changed

- `backend/scripts/backfill_talent_graph.py` — `--skip-cold-days` flag, default 90
- `backend/scripts/backfill_and_retry_ai_tags.py` — `--skip-cold` flag, doc-only `--limit` clarification (concurrency stays serial=1 by design)
- `backend/routes/admin.py` — wrapped `/stats/admin` with `cache.get` / `cache.set` (90s TTL)
- `backend/routes/public.py` — wrapped `/jobs` with cache + per-filter cache key (5 min TTL)

## Deployment on EC2

```bash
ssh ubuntu@<ec2>
cd /home/ubuntu/vhc-platform
git pull --rebase origin main
sudo systemctl restart gunicorn
sleep 5

# Quick verification
curl -s -o /dev/null -w "%{time_total}s\n" https://ventureshrd.com/api/public/jobs
curl -s -o /dev/null -w "%{time_total}s\n" https://ventureshrd.com/api/public/jobs
# Second call should be noticeably faster (cache HIT)
```

## Cache Inspection

```bash
# Quick Redis ping (Upstash):
sudo journalctl -u gunicorn --since "5 min ago" | grep -i "Cache HIT" | head -5

# If 0 HITs, check Redis is connected
sudo journalctl -u gunicorn --since "5 min ago" | grep -i "Redis\|Upstash" | head -10
```

## Rollback (Instant)

If caching causes any staleness issue, the cache can be flushed by
restarting Upstash or by adding a cache-buster version to the keys.
**Hard rollback** is just `git revert <commit>` + restart gunicorn.

## Recommended Stale-Skip Schedule

Add to crontab on EC2 (replaces any current full-backfill runs):

```bash
# Weekly cold-skip backfill — Sunday 3 AM IST
0 21 * * 6 cd /home/ubuntu/vhc-platform/backend && \
  source venv/bin/activate && \
  python3 scripts/backfill_talent_graph.py --skip-cold-days 90 --fast-summary >> /var/log/vhc/talent-graph-backfill.log 2>&1

# Daily AI-tag retry — 4 AM IST, only last 7 days, skip cold
0 22 * * * cd /home/ubuntu/vhc-platform/backend && \
  source venv/bin/activate && \
  python3 scripts/backfill_and_retry_ai_tags.py --retry --skip-cold --since-days 7 --limit 200 >> /var/log/vhc/ai-tag-retry.log 2>&1
```

(IST cron times offset by -5:30; UTC values shown.)
