# VHC Platform — AWS → Hostinger Migration Runbook

**Decision:** Migrate from AWS EC2 `t3.large` ($90/mo total) to Hostinger KVM Mumbai (~$15/mo total).
**Cutover window:** Sunday night, hours OK.
**Rollback strategy:** Kill AWS immediately after Hostinger verified. No 7-day overlap.
**DNS strategy:** Cloudflare A-record swap.

> ⚠️ **IMPORTANT — Savings Plan caveat:** The $12/mo AWS Savings Plan is a 1-year commitment.
> You **CANNOT cancel it** when you leave AWS. You'll keep paying $12/mo until the term ends.
> Confirm the end date in **AWS Console → Billing → Savings Plans** before cutover. Until then,
> your post-migration AWS bill is **~$12/mo** (the Savings Plan), not zero.

---

## Plan size recommendation

| Hostinger Plan | Spec | Promo / Renew | Verdict |
|---|---|---|---|
| **KVM 2** | 2 vCPU, 8 GB, 100 GB NVMe, 8 TB BW | ₹799 / ₹1199 | **Matches current t3.large exactly.** Risk: zero CPU headroom during clustering/backfills. |
| **KVM 4** (recommended) | 4 vCPU, 16 GB, 200 GB NVMe, 16 TB BW | ₹1099 / ₹2399 | **+$3/mo promo, +$15/mo at renew.** 2× CPU + RAM. Eliminates the clustering OOM risk completely. |

Recommend **KVM 4**. The extra $3/mo (promo period) buys real headroom — the clustering job alone spiked workers to 3.3 GB recently. With KVM 2 you'll be one bad batch away from OOM crashes.

---

# PHASE 1 — PREP (any weekday, 2-3 hours, ZERO downtime)

## 1.1 — Provision the Hostinger VPS

1. Sign up: https://hostinger.com → VPS hosting
2. Choose **KVM 4** (or KVM 2)
3. Region: **Mumbai (India)**
4. OS: **Ubuntu 24.04 LTS** (clean, no panel)
5. Set a **root password** + **SSH key** during setup
6. Note down: `IP`, `root` SSH access

## 1.2 — Initial server hardening (10 min)

```bash
ssh root@<NEW_HOSTINGER_IP>

# Update
apt update && apt upgrade -y

# Create ubuntu user (mirror AWS layout)
adduser --disabled-password --gecos "" ubuntu
usermod -aG sudo ubuntu
mkdir -p /home/ubuntu/.ssh
cp ~/.ssh/authorized_keys /home/ubuntu/.ssh/
chown -R ubuntu:ubuntu /home/ubuntu/.ssh
chmod 700 /home/ubuntu/.ssh
chmod 600 /home/ubuntu/.ssh/authorized_keys

# Sudo without password (matches AWS convention; harden later if you want)
echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu

# Disable root SSH (after confirming ubuntu user works in a NEW terminal)
# sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
# systemctl restart ssh

# Firewall
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

## 1.3 — Install all dependencies

```bash
ssh ubuntu@<NEW_HOSTINGER_IP>

# System packages
sudo apt install -y \
  python3 python3-pip python3-venv python3-dev \
  build-essential libssl-dev libffi-dev \
  nginx git curl wget \
  libjemalloc2 \
  certbot python3-certbot-nginx \
  rsync htop iotop net-tools \
  pkg-config

# Node 20 + yarn (for frontend build)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt install -y nodejs
sudo npm install -g yarn

# Verify
python3 --version  # 3.12.x
node --version     # v20.x
yarn --version
```

## 1.4 — Clone the repo + setup backend venv

```bash
cd /home/ubuntu

# If your repo has a deploy key already, copy it. Otherwise:
ssh-keygen -t ed25519 -C "hostinger-deploy" -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub
# → Copy this public key into GitHub repo → Settings → Deploy keys → Add (read-only is enough)

cat >> ~/.ssh/config <<EOF
Host github.com
  IdentityFile ~/.ssh/github_deploy
  IdentitiesOnly yes
EOF

git clone git@github.com:VenturesOS/VHCOS.git vhc-platform
cd vhc-platform

# Backend venv
cd backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
deactivate
cd ..
```

## 1.5 — BGE sidecar setup

```bash
sudo mkdir -p /opt/bge-sidecar
sudo chown ubuntu:ubuntu /opt/bge-sidecar
cd /opt/bge-sidecar

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip wheel
pip install \
  "fastapi==0.115.*" "uvicorn[standard]==0.30.*" \
  "sentence-transformers==3.0.1" \
  "transformers==4.44.2" \
  "torch==2.2.2+cpu" --index-url https://download.pytorch.org/whl/cpu \
  "numpy<2" "scipy<1.14" "pydantic>=2.7,<3"

# Copy embed_service.py from /app/backend/static/sidecar/embed_service.py
# (in your repo). Path on Hostinger:
cp /home/ubuntu/vhc-platform/backend/static/sidecar/embed_service.py /opt/bge-sidecar/

deactivate
```

## 1.6 — Transfer the `.env` files (BACKEND + FRONTEND)

**On AWS EC2:**

```bash
# Copy .env files to your local machine (NOT to GitHub):
scp ubuntu@<AWS_IP>:/home/ubuntu/vhc-platform/backend/.env ~/vhc-backend.env
scp ubuntu@<AWS_IP>:/home/ubuntu/vhc-platform/frontend/.env ~/vhc-frontend.env
```

**Push to Hostinger:**

```bash
scp ~/vhc-backend.env  ubuntu@<HOSTINGER_IP>:/home/ubuntu/vhc-platform/backend/.env
scp ~/vhc-frontend.env ubuntu@<HOSTINGER_IP>:/home/ubuntu/vhc-platform/frontend/.env

# Then SHRED the local copies:
shred -u ~/vhc-backend.env ~/vhc-frontend.env
```

**On Hostinger, lock perms:**

```bash
chmod 600 /home/ubuntu/vhc-platform/backend/.env /home/ubuntu/vhc-platform/frontend/.env
```

## 1.7 — Build the frontend

```bash
cd /home/ubuntu/vhc-platform/frontend
yarn install --frozen-lockfile
yarn build
sudo rsync -a --delete build/ /var/www/html/
sudo chown -R www-data:www-data /var/www/html
```

## 1.8 — systemd unit: vhc-backend

Create `/etc/systemd/system/vhc-backend.service`:

```ini
[Unit]
Description=VHC Talent OS FastAPI Backend
After=network.target

[Service]
Type=notify
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/vhc-platform/backend
Environment="LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2"
Environment="MALLOC_CONF=background_thread:true,metadata_thp:auto,dirty_decay_ms:5000,muzzy_decay_ms:5000,narenas:2"
Environment="PATH=/home/ubuntu/vhc-platform/backend/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/ubuntu/vhc-platform/backend/venv/bin/gunicorn server:app \
  --workers 3 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 127.0.0.1:8001 \
  --timeout 120 \
  --graceful-timeout 30 \
  --max-requests 500 \
  --max-requests-jitter 30
Restart=on-failure
RestartSec=5

# Memory limits (matches current AWS override.conf)
MemoryHigh=5G
MemoryMax=6G

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable vhc-backend
# Don't START yet — we'll start at cutover
```

## 1.9 — systemd unit: bge-sidecar

Create `/etc/systemd/system/bge-sidecar.service`:

```ini
[Unit]
Description=VHC BGE Sidecar (CPU embeddings + reranking)
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/bge-sidecar
ExecStart=/opt/bge-sidecar/venv/bin/uvicorn embed_service:app --host 127.0.0.1 --port 8002 --log-level info
Restart=on-failure
RestartSec=5

MemoryMax=2400M

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable bge-sidecar
# Don't START yet
```

## 1.10 — nginx config

Pull current nginx config from AWS:

```bash
scp ubuntu@<AWS_IP>:/etc/nginx/sites-available/vhc /tmp/vhc-nginx.conf
scp /tmp/vhc-nginx.conf ubuntu@<HOSTINGER_IP>:/tmp/
ssh ubuntu@<HOSTINGER_IP>
sudo cp /tmp/vhc-nginx.conf /etc/nginx/sites-available/vhc
sudo ln -sf /etc/nginx/sites-available/vhc /etc/nginx/sites-enabled/vhc
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t   # MUST pass before continuing
```

## 1.11 — TLS / SSL cert

You're behind Cloudflare. Two clean options:

**Option A — Cloudflare Origin Certificate (recommended, no renewals):**

1. Cloudflare Dashboard → ventureshrd.com → SSL/TLS → Origin Server → **Create Certificate**
2. Hostname: `ventureshrd.com, *.ventureshrd.com`
3. Validity: 15 years
4. Copy the cert + private key onto Hostinger:

```bash
sudo mkdir -p /etc/ssl/cloudflare
sudo nano /etc/ssl/cloudflare/cert.pem      # paste cert
sudo nano /etc/ssl/cloudflare/key.pem       # paste private key
sudo chmod 600 /etc/ssl/cloudflare/key.pem
```

5. Reference them in `/etc/nginx/sites-available/vhc`:
```
ssl_certificate     /etc/ssl/cloudflare/cert.pem;
ssl_certificate_key /etc/ssl/cloudflare/key.pem;
```

6. Make sure Cloudflare SSL/TLS mode = **Full (strict)**.

**Option B — Let's Encrypt:**

```bash
sudo certbot --nginx -d ventureshrd.com -d www.ventureshrd.com
```

(Needs Cloudflare "DNS only" mode briefly during issuance, then re-proxy. Skip unless you want full LE.)

## 1.12 — Cron jobs

```bash
crontab -e
```

Add (matches current AWS schedule — pull from AWS first via `crontab -l` to be sure):

```cron
*/5 * * * * cd /home/ubuntu/vhc-platform/backend && venv/bin/python scripts/runpod_bge_keeper.py >> /var/log/runpod_keeper.log 2>&1
30 9 * * *  cd /home/ubuntu/vhc-platform/backend && venv/bin/python scripts/run_bill_reminders.py >> /var/log/bill_reminders.log 2>&1
0  3 * * *  cd /home/ubuntu/vhc-platform/backend && venv/bin/python scripts/runpod_schedule.py start >> /var/log/runpod_schedule.log 2>&1
30 18 * * * cd /home/ubuntu/vhc-platform/backend && venv/bin/python scripts/runpod_schedule.py stop  >> /var/log/runpod_schedule.log 2>&1
```

(Cross-check `ssh ubuntu@<AWS_IP> "crontab -l"` to get the exact current set.)

## 1.13 — MongoDB Atlas — whitelist Hostinger IP

1. MongoDB Atlas Dashboard → Network Access → Add IP Address
2. Enter `<HOSTINGER_IP>` (NOT 0.0.0.0/0)
3. Comment: "Hostinger Mumbai - prep"
4. **Do NOT remove AWS IP yet** — keeps fallback open until decom

## 1.14 — Pre-flight test (still pre-cutover!)

```bash
# Start services on Hostinger in TEST mode (Cloudflare not switched yet)
sudo systemctl start bge-sidecar
sleep 30
curl -s http://127.0.0.1:8002/health | jq

sudo systemctl start vhc-backend
sleep 10
curl -s http://127.0.0.1:8001/api/health | jq

# Test from outside by editing your local /etc/hosts:
# Add: <HOSTINGER_IP>  ventureshrd.com
# Then visit https://ventureshrd.com in your browser
# (your machine bypasses Cloudflare, hits Hostinger directly via the cert)

# If everything works → STOP services and wait for cutover:
sudo systemctl stop vhc-backend bge-sidecar
```

---

# PHASE 2 — CUTOVER (Sunday night, 30-60 min)

**Pre-flight checklist (do BEFORE starting):**

- [ ] PHASE 1 done fully
- [ ] Hostinger services boot cleanly (tested in 1.14)
- [ ] Cloudflare Origin cert installed + valid
- [ ] Backups: `mongodump` your most-changed collections (optional, Atlas already does point-in-time)
- [ ] Tell anyone who uses the app: "10–30 min downtime tonight"

## 2.1 — Lower Cloudflare DNS TTL (do 30 min before cutover)

Cloudflare → DNS → ventureshrd.com A record → set **TTL = 5 min** (was probably Auto/300). Save. Wait 5+ min.

## 2.2 — Quiesce AWS

```bash
ssh ubuntu@<AWS_IP>
sudo systemctl stop vhc-backend
# Sidecar can stay running on AWS — Hostinger has its own
```

This rejects new requests with 502 for ~5 minutes. Acceptable per your "hours OK" choice.

## 2.3 — Start Hostinger

```bash
ssh ubuntu@<HOSTINGER_IP>
sudo systemctl start bge-sidecar
sleep 30
curl -s http://127.0.0.1:8002/health   # must return ok:true, both models loaded
sudo systemctl start vhc-backend
sleep 10
curl -s http://127.0.0.1:8001/api/health  # must return 200
```

## 2.4 — Flip Cloudflare DNS

Cloudflare → DNS → ventureshrd.com A record → **change IP to `<HOSTINGER_IP>`** → Save.
With TTL=5min, DNS propagates within 5 min globally.

## 2.5 — Verify production

```bash
# From your laptop (not from server)
curl -s https://ventureshrd.com/api/health | jq
# Should return 200, same as before, but served by Hostinger now.

# Verify in browser:
# 1. Open https://ventureshrd.com in incognito
# 2. Login as admin@vhc.in
# 3. Check candidate-bank loads
# 4. Try one Naukri capture via extension → confirm green-badge + capture works
# 5. Check /admin/clusters → cluster cards still load
```

## 2.6 — Monitor for 1 hour

```bash
ssh ubuntu@<HOSTINGER_IP>
sudo journalctl -u vhc-backend -f | grep -iE "error|exception|timeout"
# In another tab:
htop  # watch memory, CPU
```

**Watch for:**
- Worker RSS climbing past 1 GB → memory issue
- Repeated 500s on captures → DB connection issue (check Atlas IP whitelist)
- Slow responses → CPU saturation (KVM 2 might need upgrade to KVM 4)

If anything's badly wrong **within first 30 min**: roll back (PHASE 2.7).
After 1 hour clean traffic → proceed to PHASE 3.

## 2.7 — ROLLBACK procedure (only if Hostinger fails)

1. Cloudflare DNS → change A record back to `<AWS_IP>`
2. `ssh ubuntu@<AWS_IP> && sudo systemctl start vhc-backend`
3. Wait 5 min for DNS to converge
4. App back on AWS. Hostinger debugging happens during the week.

---

# PHASE 3 — DECOMMISSION AWS (the morning after, 15 min)

> Per your decision: **kill immediately after verification**. Do this only if Phase 2 was clean for 1+ hour.

## 3.1 — Final checks

```bash
# Verify Hostinger is actually serving prod traffic (not Cloudflare cache)
curl -sI https://ventureshrd.com | grep -i "server\|cf-ray"
# Also check from a clean network (mobile data) to be sure
```

## 3.2 — Snapshot AWS as last-resort rollback (optional but recommended)

```
AWS Console → EC2 → Instances → vhc-backend
Right-click → Image and templates → Create image
Name: "vhc-backend-pre-decom-YYYY-MM-DD"
```

Cost: ~$5/mo for the snapshot. Keep it 30 days as insurance. Delete after.

## 3.3 — Stop + terminate

```
AWS Console → EC2 → Instances → Stop instance
Wait 1 min → confirm Hostinger still serving fine
EC2 → Instances → Terminate instance (DANGER — irreversible if no AMI snapshot)
```

## 3.4 — Clean up

```
AWS Console → EC2 → Elastic IPs → Release (saves $3.60/mo if reserved but unused)
AWS Console → EC2 → Volumes → Delete unattached EBS volumes (saves $6/mo)
AWS Console → EC2 → Snapshots → Delete old ones (NOT the one from 3.2)
```

## 3.5 — MongoDB Atlas — remove AWS IP

After 24h of clean Hostinger traffic:
Atlas → Network Access → delete the AWS IP entry. Keep only Hostinger.

## 3.6 — Cloudflare — restore normal TTL

DNS → ventureshrd.com A record → TTL: **Auto**

## 3.7 — Cancel Savings Plan? You CANNOT

The Savings Plan is a 1-year contract. You **continue paying $12/mo** for the remainder of its term. Check the end date in **Billing → Savings Plans**. After it expires (no auto-renewal — confirm "do not renew" is set), AWS billing goes to $0.

---

# Expected final state

| Item | Before | After |
|---|---|---|
| **Monthly bill** | $90 | **$15** (Hostinger) **+ $12** (residual Savings Plan, ends in X months) |
| **Specs** | 2 vCPU, 8 GB | 4 vCPU, 16 GB (KVM 4) — 2× upgrade |
| **Bandwidth incl.** | 0 (metered $0.01/GB) | **16 TB/month included** |
| **Disk** | 60 GB gp3 | 200 GB NVMe (faster) |
| **Reliability SLA** | 99.99% | 99.9% (Hostinger) |
| **Auto-failover** | Yes | No (manual recovery needed if VPS dies) |
| **Annual savings** | — | **~$900** after Savings Plan expires |

---

# Post-migration follow-ups (within 1 week)

1. Verify Mongo Atlas backups still running (no change needed, but confirm)
2. Set up daily snapshot via Hostinger panel → instance settings → Snapshots
3. Add Hostinger IP to any external service whitelists (Naukri ATS, etc — none currently)
4. Update README / docs to reflect new IP + provider
5. Watch the first 7 days of `journalctl` for any cron failures (the RunPod keeper SSH key must be at `/home/ubuntu/.ssh/runpod_bge` on Hostinger — copy it from AWS during PHASE 1)

---

# Files you'll need ready on Sunday

Local laptop / encrypted folder:
- `vhc-backend.env` (from AWS scp)
- `vhc-frontend.env` (from AWS scp)
- AWS IP, Hostinger IP, Cloudflare API token
- AWS instance ID (for snapshot/termination)
- Cloudflare origin cert + key (PEM blocks)
- The SSH private key for RunPod (`/home/ubuntu/.ssh/runpod_bge` on AWS)
- This runbook printed/PDF'd
