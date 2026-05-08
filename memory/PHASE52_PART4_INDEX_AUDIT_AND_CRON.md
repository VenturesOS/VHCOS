# Phase 52 (Part 4) — Index Audit Tool + Cron Setup (2026-05-06)

## What's New

### `scripts/audit_indexes.py`
Read-only MongoDB index auditor. Surfaces unused indexes per collection
with concrete drop commands. Pulled live numbers from your prod DB while
building it:

**candidate_bank alone has ~193 MB of indexes that are never accessed.**

Quick examples:
- `text_search_idx` (110 MB) — 0 ops since last reset
- `skills_idx` (58 MB) — 0 ops since last reset
- `bulk_restricted_idx`, `created_by_1`, `idx_captured_by_name`, etc.

## Usage

### Pretty report (run on EC2)
```bash
ssh ubuntu@<ec2>
cd /home/ubuntu/vhc-platform/backend
source venv/bin/activate
python3 scripts/audit_indexes.py
```

### One specific collection
```bash
python3 scripts/audit_indexes.py --collection candidate_bank
python3 scripts/audit_indexes.py --collection applications
python3 scripts/audit_indexes.py --collection naukri_capture_logs
```

### Tweak thresholds
```bash
# More aggressive: drop if < 1 op/day, ignore < 16 KB
python3 scripts/audit_indexes.py --min-size-kb 16 --min-daily-ops 1

# More conservative: drop only if 0 ops AND > 256 KB
python3 scripts/audit_indexes.py --min-size-kb 256 --min-daily-ops 0
```

### JSON for further analysis
```bash
python3 scripts/audit_indexes.py --json > /tmp/index_audit.json
```

## ⚠️ Critical Safety Notes

1. **Server uptime matters.** The `$indexStats` counter resets on every
   mongod restart. The script prints uptime — wait at least **7 days** of
   normal traffic before trusting DROP_CANDIDATE flags.

2. **Read-only.** The script never drops anything. It prints suggested
   mongo shell commands; you copy-paste only the ones you've verified.

3. **Hot-field guard.** The script always tags indexes covering these
   fields as KEEP, regardless of access count: `id`, `candidate_id`,
   `user_id`, `employer_id`, `team_id`, `mandate_id`, `job_id`,
   `naukri_id`, `email`, `phone`. This prevents accidentally dropping
   the indexes behind your dedup / linkage logic.

4. **Drop one at a time.** When you're ready to drop, do **one** index,
   wait 24 hours, watch for slow query alerts, then drop the next.

5. **How to actually drop** (use Atlas Data Explorer or mongo shell):
   ```javascript
   // Atlas Data Explorer → "Indexes" tab on the collection → ⋯ menu
   // OR via mongosh:
   db.candidate_bank.dropIndex('text_search_idx')
   ```

## Recommended First Pass (after 7-day soak)

These were unused with 0 ops over 4.6 days. Start with the largest:

```javascript
// ~168 MB reclaimable from these two alone:
db.candidate_bank.dropIndex('text_search_idx')      // 110 MB
db.candidate_bank.dropIndex('skills_idx')           //  58 MB

// Lower priority, still safe drops (audit again after 7-day soak first):
db.candidate_bank.dropIndex('bulk_restricted_idx')
db.candidate_bank.dropIndex('created_by_1')
db.candidate_bank.dropIndex('idx_captured_by_name')
db.candidate_bank.dropIndex('company_id_1_created_at_-1')
```

Re-create on demand if a query slows down — they take a few minutes to
rebuild on a 19k-doc collection.

---

## Cron Setup for Stale-Skip Backfills

Run this once on EC2:

```bash
sudo mkdir -p /var/log/vhc
sudo chown ubuntu:ubuntu /var/log/vhc

crontab -e
```

Paste at the bottom:

```cron
# VHC OS — weekly cold-skip embedding backfill (Sat 21:30 UTC = Sun 03:00 IST)
30 21 * * 6 cd /home/ubuntu/vhc-platform/backend && /home/ubuntu/vhc-platform/backend/venv/bin/python3 scripts/backfill_talent_graph.py --skip-cold-days 90 --fast-summary >> /var/log/vhc/talent-graph-backfill.log 2>&1

# VHC OS — daily AI-tag retry (22:30 UTC = 04:00 IST)
30 22 * * * cd /home/ubuntu/vhc-platform/backend && /home/ubuntu/vhc-platform/backend/venv/bin/python3 scripts/backfill_and_retry_ai_tags.py --retry --skip-cold --since-days 7 --limit 200 >> /var/log/vhc/ai-tag-retry.log 2>&1

# VHC OS — weekly index audit report (Mon 02:00 UTC = 07:30 IST)
0 2 * * 1 cd /home/ubuntu/vhc-platform/backend && /home/ubuntu/vhc-platform/backend/venv/bin/python3 scripts/audit_indexes.py >> /var/log/vhc/index-audit.log 2>&1
```

Save & exit. Verify:

```bash
crontab -l | tail -10
# Tomorrow morning, check the first run landed:
tail -f /var/log/vhc/ai-tag-retry.log
```

## Observability — daily team report

Quick one-liner to see how dedup + retries are performing:

```bash
echo ""
echo "── Daily Phase 52 Report — $(date '+%Y-%m-%d') ──"
echo "Captures (UPDATE):     $(sudo journalctl -u gunicorn --since today | grep -c 'Extension] UPDATE')"
echo "Dedup skipped Qwen:    $(sudo journalctl -u gunicorn --since today | grep -c 'Dedup.*SKIP_QWEN')"
echo "Qwen successes:        $(sudo journalctl -u gunicorn --since today | grep -c 'Layer1-RunPod.*SUCCESS')"
echo "Embedding skipped:     $(sudo journalctl -u gunicorn --since today | grep -c 'embed-queue full')"
echo "Memory peak today:     $(systemctl show gunicorn -p MemoryPeak --value | awk '{printf "%.1f MB", $1/1024/1024}')"
echo "OOM events:            $(sudo journalctl --since today | grep -ci 'oom-kill')"
echo ""
```

Save as `~/vhc-daily-report.sh` and make it executable.
