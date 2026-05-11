# Phase 54.16 — #6 EventBridge Nightly EC2 Off

**Goal:** Stop EC2 from 00:30–06:30 IST (recruiters are sleeping) → save
~₹1,090/mo. Uses AWS Systems Manager + EventBridge (free service).

**Pre-req:** D1 (BGE sidecar) must be live first, so EC2 RAM is small
enough that the cold start at 6:30 AM is < 2 min.

## Architecture
```
EventBridge cron (UTC) ────► Systems Manager Automation ────► EC2 StopInstances
                                                            └─► EC2 StartInstances
```

No EC2-side scripts, no extra IAM users — fully managed by AWS.

## Schedule (IST hours, computed in UTC for EventBridge)
| Event | IST | UTC |
|---|---|---|
| Stop instance | 00:30 (Tue–Sun, after Mon–Sat work day) | 19:00 (Mon–Sat) |
| Start instance | 06:30 (Mon–Sat) | 01:00 (Mon–Sat) |

> Skips Sundays entirely — pod stays off Saturday night through Monday
> morning to maximize savings. Adjust if your team works weekends.

## Step-by-step (AWS Console)

### 1. Create IAM role for EventBridge to call EC2
1. AWS Console → **IAM → Roles → Create role**
2. Trusted entity: **AWS service** → use case: **EventBridge Scheduler**
3. Permissions: attach `AmazonEC2FullAccess` (or a narrower custom
   policy if you prefer — only `ec2:StartInstances` + `ec2:StopInstances`
   on your specific instance ARN).
4. Name: `EventBridgeEC2StartStopRole` → Create.

### 2. Create the Stop schedule
1. AWS Console → **EventBridge → Schedules → Create schedule**
2. Schedule name: `vhc-ec2-nightly-stop`
3. Schedule pattern:
   - Occurrence: **Recurring schedule**
   - Schedule type: **Cron-based**
   - Cron expression: `0 19 ? * MON-SAT *`  *(stops at 00:30 IST next day)*
   - Timezone: **UTC**
4. Flexible time window: **Off** (we want exact 00:30)
5. Next → Target: **All APIs** → search **EC2** → **StopInstances**
6. Input (JSON):
   ```json
   {
     "InstanceIds": ["i-048369e053506bc98"]
   }
   ```
7. Next → Execution role: **Use existing role** →
   `EventBridgeEC2StartStopRole`
8. Retry policy: leave defaults. **No** dead-letter queue needed.
9. Create.

### 3. Create the Start schedule
Same flow, but:
- Name: `vhc-ec2-morning-start`
- Cron: `0 1 ? * MON-SAT *` *(starts at 06:30 IST)*
- Target API: **StartInstances**
- Same JSON input + same IAM role

### 4. Verify
Both schedules should appear under **EventBridge → Schedules** with
status **Enabled** and a **Next invocation** timestamp.

### 5. Test (optional — costs you 1 stop+start cycle)
Once you're confident, manually invoke the Stop schedule from the
console (Actions → Run now). The instance should stop within ~30 s.
Then invoke Start. The Elastic IP `3.108.98.192` reattaches
automatically.

## Watchouts
1. **RunPod cron persistence** — the RunPod scheduler cron lives on
   EC2. When EC2 is off (00:30–06:30 IST), no cron fires. This is OK
   because the RunPod schedule (08:50 AM start, 18:30 stop) is
   well outside our nightly EC2 off window. Sanity-check by running:
   ```bash
   crontab -l | grep runpod_schedule
   ```
   ...after the first nightly cycle.

2. **Daily Team Digest cron at 18:00 IST** — same; well outside the
   off window. Safe.

3. **First request after morning start** — gunicorn cold start with
   D1 (sidecar) is ~30 s, with the local fallback ~60 s. Either way,
   the first recruiter logging in at 7 AM should be fine.

4. **Disk fees still apply while stopped** — ~₹230/mo for EBS gp3.
   Already factored in.

## Expected savings
- t3a.large compute: $0.0806/hr × 6 h × 30 days × 0.857 (skip Sun) =
  ~$12.45/mo = **~₹1,045/mo**
- Plus an ad-hoc bonus: ~5 min less per day spent on gunicorn keeping
  warm caches → tiny but real RAM headroom for daytime use.

## Rollback
EventBridge → Schedules → select either → **Actions → Disable**.
Schedule stays in place but stops firing. Re-enable any time.
