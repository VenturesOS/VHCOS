# Phase 54.21 — WhatsApp Cloud API Integration (Feb 2026)

**Status:** Code shipped to workspace. Awaiting Meta template approval
(24–48 h) and EC2 `git pull` to go live.

## What's shipped

### Backend
- `services/whatsapp_cloud_service.py` — Meta Cloud API client
  (`send_template_message`, `send_digest_to_admins`,
  `update_status_from_webhook`).
- `routes/whatsapp_webhook.py` — verification + delivery-status webhook
  at `GET/POST /api/webhooks/whatsapp`.
- `services/team_digest_service.py` — `run_daily_digest()` now fans the
  built digest out to admin WhatsApp numbers right after `store_digest`.
- `routes/daily_digest.py` — two new admin endpoints:
  - `POST /api/admin/daily-digest/whatsapp/send-test` — force-send NOW
  - `GET  /api/admin/daily-digest/whatsapp/status` — recent send log
- `server.py` — webhook router registered.
- `whatsapp_send_log` Mongo collection — auto-created on first send.

### Frontend
- `DailyDigestWidget.jsx` — new green outline **Auto-Send** button calls
  the Cloud API directly; toast shows sent/failed counts.
- `lib/api.js` — `teamDigestAPI.whatsappSendTest` / `whatsappStatus`.

## Env vars (already added to `/home/ubuntu/vhc-platform/backend/.env`)

```
WHATSAPP_PHONE_NUMBER_ID=1107056135824774
WHATSAPP_BUSINESS_ACCOUNT_ID=1295553745559429
WHATSAPP_API_VERSION=v25.0
WHATSAPP_ACCESS_TOKEN=<permanent token>
WHATSAPP_ADMIN_NUMBERS=919810557485
WHATSAPP_TEMPLATE_NAME=team_daily_digest_v1
WHATSAPP_TEMPLATE_LANG=en
WHATSAPP_DIGEST_URL=https://app.ventureshrd.com/admin/dashboard
# Optional — uncomment after configuring Meta webhook subscription:
# WHATSAPP_WEBHOOK_VERIFY_TOKEN=<any random 32-char string>
# WHATSAPP_APP_SECRET=<App Secret from Meta Developer Console → Settings → Basic>
```

## Approved template (Meta-side, pending review)

Name: `team_daily_digest_v1` (English, Utility category)

Body:
```
📊 *VHC Daily Team Digest – {{1}}*

*Team Performance*
• Activity Score: {{2}}
• Captures Today: {{3}}
• Pipeline Points: {{4}}
• Capture Quality: {{5}}%

🏆 *Top Performer:* {{6}}

🔗 Full report: {{7}}

_Generated automatically by VHC Talent OS_
```

Variable mapping (from `_digest_to_template_params`):
1. pretty_date              (e.g. "Mon, 12 May")
2. top_activity_score       (highest individual)
3. total_captures_today
4. total_pipeline_points
5. avg_capture_quality_pct
6. top_performer            (name + score)
7. dashboard_url

## Deploy steps on EC2 (run once template is APPROVED)

```bash
cd /home/ubuntu/vhc-platform
git pull --rebase origin main

# Rebuild frontend
cd frontend
yarn build
sudo rsync -a --delete --exclude=.well-known --exclude=assets build/ /var/www/html/
sudo chown -R www-data:www-data /var/www/html

# Restart backend (picks up new env + code)
sudo systemctl restart gunicorn
sleep 6
curl -s http://localhost:8001/api/health | python3 -m json.tool
```

## Smoke test after deploy

1. Open admin dashboard → Daily Digest widget → click **Auto-Send**.
2. Expect toast: `✅ Digest sent to 1/1 admin(s) via Cloud API` and a
   WhatsApp on `+91 98105 57485` with the digest using template variables.
3. Verify the cron path:
   ```bash
   sudo journalctl -u gunicorn --since "today" | grep -iE "TeamDigest|WA"
   ```
   At 18:00 IST (12:30 UTC) you should see:
   `[TeamDigest] ✅ Done — N top, ...` then
   `[TeamDigest] WA fan-out sent=1 failed=0 of 1`.

## Webhook configuration (optional but recommended — Phase 54.22)

Adds delivery+read receipts to `whatsapp_send_log`. Needed for the admin
status widget to show `delivered` / `read` badges.

In Meta Developer Console → your App → WhatsApp → Configuration:
- Callback URL: `https://app.ventureshrd.com/api/webhooks/whatsapp`
- Verify token: pick any random string (≥32 chars), set the same value
  as `WHATSAPP_WEBHOOK_VERIFY_TOKEN` in `.env`, then click **Verify and
  save** in Meta. Subscribe to **messages** event.
- (Optional) Set `WHATSAPP_APP_SECRET` from Settings → Basic to enable
  HMAC signature validation.

## Rollback

If anything misbehaves, just blank `WHATSAPP_ACCESS_TOKEN` in `.env` and
restart gunicorn — the fan-out path silently no-ops via `is_enabled()`,
and the manual Copy/Share buttons still work.

## Cost

Stays within Meta's free tier (1,000 service conversations/month). With
1 admin × 30 days = 30 conversations/month → ₹0.

## Open follow-ups

- [ ] Rotate access token (the one used during setup was pasted in chat —
      generate a new permanent token after smoke test passes).
- [ ] Add more admin numbers to `WHATSAPP_ADMIN_NUMBERS` (comma-separated)
      once template is APPROVED and tested with primary number.
- [ ] Subscribe to Meta webhook for delivered/read receipts (optional).
- [ ] Move from test phone number to a real business phone number when
      you want unrestricted recipient list (needs phone verification on
      Meta side).
