# Bill Generator — Setup & Runbook (Phase 55.6, May 2026)

## 1. Files shipped

**Backend**
- `backend/models/bill.py` — Pydantic models
- `backend/services/bill_pdf.py` — ReportLab PDF renderer (Indian INR formatting + amount-in-words)
- `backend/services/bill_mailer.py` — Resend wrapper (with CC-list builder)
- `backend/services/bill_llm_body.py` — Qwen-generated mail bodies (with safe template fallback)
- `backend/routes/bills.py` — CRUD + preview + send + mark-paid + cancel
- `backend/scripts/run_bill_reminders.py` — Daily cron (T+7/14/30)

**Frontend**
- `frontend/src/pages/admin/BillsPage.jsx` — Full UI (list, new, preview, send, mark-paid, cancel)
- `frontend/src/lib/api.js` — `billsAPI`
- `App.js` route `/admin/bills`
- `Sidebar.jsx` "Bills" link with Receipt icon

## 2. One-time `.env` additions

Append to `/home/ubuntu/vhc-platform/backend/.env`:

```
# Resend transactional mail
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
BILLING_SENDER_EMAIL=billing@vhc.in
BILLING_SENDER_NAME=Venture HRD Centre
BILLING_REPLY_TO=accounts@vhc.in
BILLING_ACCOUNTS_EMAIL=accounts@vhc.in
BILLING_DEFAULT_CC_1=bsy@vhc.in
BILLING_DEFAULT_CC_2=rohit@vhc.in

# Optional — leave blank to use the built-in defaults
BILLING_SENDER_GSTIN=07AAMPY9883D2ZT
BILLING_SENDER_PAN=AAMPY9883D
BILLING_SIGNATURE_R2_KEY=billing/signature_balbir.png
```

## 3. Resend domain setup (one-time, ~15 min)

1. Sign up at https://resend.com (free tier = 3 000 mails/mo, plenty for billing).
2. Dashboard → **Domains** → **Add Domain** → enter `vhc.in`.
3. Resend will show 3 DNS records — add them to your domain DNS:
   - `MX  send.vhc.in  feedback-smtp.us-east-1.amazonses.com  10`
   - `TXT  send.vhc.in  "v=spf1 include:amazonses.com ~all"`
   - `TXT  resend._domainkey.vhc.in  <long DKIM key>`
   - (optional but recommended) DMARC `TXT _dmarc.vhc.in  "v=DMARC1; p=none;"`
4. Wait ~10 min for DNS propagation. Resend dashboard shows green check when verified.
5. Dashboard → **API Keys** → **Create API Key** → Full Access. Paste into `.env` as `RESEND_API_KEY`.

## 4. Signature PNG (one-time)

Upload your signature to R2 (or use a PNG you already have):

```bash
cd ~/vhc-platform/backend && source venv/bin/activate
python3 << 'PYEOF'
import os
from utils.r2_client import get_r2_client
cli = get_r2_client()
cli.upload_file('/path/to/balbir_signature.png',
                os.environ.get('R2_BUCKET','vhc-talent-os-storage'),
                'billing/signature_balbir.png')
print('Uploaded')
PYEOF
```

## 5. Daily reminder cron

```bash
sudo tee /etc/systemd/system/vhc-bill-reminders.service > /dev/null <<'EOF'
[Unit]
Description=VHC bill reminders (T+7/14/30)
After=network.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu/vhc-platform/backend
EnvironmentFile=/home/ubuntu/vhc-platform/backend/.env
ExecStart=/home/ubuntu/vhc-platform/backend/venv/bin/python scripts/run_bill_reminders.py
EOF

sudo tee /etc/systemd/system/vhc-bill-reminders.timer > /dev/null <<'EOF'
[Unit]
Description=Daily run of VHC bill reminders

[Timer]
OnCalendar=*-*-* 04:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now vhc-bill-reminders.timer
sudo systemctl list-timers | grep vhc-bill
```

## 6. Smoke test

```bash
cd ~/vhc-platform && git pull --no-rebase --no-edit
sudo systemctl restart vhc-backend
sleep 5 && systemctl is-active vhc-backend
curl -sS http://127.0.0.1:8001/openapi.json | python3 -c "import sys,json;d=json.load(sys.stdin);print([p for p in d['paths'] if '/bills' in p])"

# Frontend rebuild + deploy
cd ~/vhc-platform/frontend
yarn build
sudo rsync -a --delete build/ /var/www/html/
sudo systemctl reload nginx
```

Open https://ventureshrd.com/admin/bills (hard-refresh). Verify the new "Bills" link appears in the sidebar and the page loads.

## 7. Workflow

1. **New Bill** → pick client → add line items → save draft
2. **Preview** (eye icon) → check the PDF inline
3. **Send** (paper-plane icon) → modal opens → LLM auto-fills body via Qwen → edit if needed → tick `Test mode` to send to yourself first → uncheck and Send Now
4. **Mark Paid** (green tick) when payment received
5. Reminders auto-fire at T+7 / T+14 / T+30 to CC parties only (not the client)
