# ============================================================================
# VHC Talent OS — Complete AWS Deployment Guide
# ============================================================================
# Target: Ubuntu EC2 + Nginx + Gunicorn + MongoDB Atlas
# ============================================================================

## 1. PYTHON DEPENDENCIES

### Install Command (run from /opt/vhc-backend/):
```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install all dependencies
pip install -r requirements.txt

# Install Emergent LLM library (special pip index)
pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
```

### Is `emergentintegrations` required?
**YES** — used in 3 places:
- `routes/jobs.py` — Job description AI parsing
- `routes/bulk_import.py` — Industry detection during bulk import
- `services/matching_engine.py` — AI candidate-job matching

Without it, these 3 features fail but the rest of the app works.
Install from: `pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/`

### Key Library Categories:
| Category | Libraries |
|---|---|
| Web Framework | `fastapi==0.110.1`, `uvicorn==0.25.0`, `starlette==0.37.2` |
| Database | `motor==3.4.0`, `pymongo==4.7.3` |
| AI/LLM | `openai==1.99.9`, `httpx==0.28.1`, `emergentintegrations==0.1.0` |
| PDF | `fpdf2==2.8.7`, `PyMuPDF==1.26.7`, `PyPDF2==3.0.1` |
| Email | `resend==2.19.0` |
| Storage | `boto3==1.42.21` |
| Cache | `upstash-redis==1.6.0` |
| Scheduler | `APScheduler==3.11.2` |
| Auth | `bcrypt==4.1.3`, `PyJWT==2.10.1`, `python-jose==3.5.0` |
| Excel | `openpyxl==3.1.5`, `pandas==2.3.3` |
| System | `psutil==7.2.2`, `certifi==2026.1.4` |

---

## 2. BACKEND STARTUP COMMAND

### Production (Gunicorn + Uvicorn workers):
```bash
cd /opt/vhc-backend
source venv/bin/activate

gunicorn server:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8001 \
  --timeout 120 \
  --graceful-timeout 30 \
  --keep-alive 5 \
  --access-logfile /var/log/vhc/access.log \
  --error-logfile /var/log/vhc/error.log \
  --log-level info
```

### Worker Count:
- **4 workers** recommended for t3.xlarge (4 vCPU)
- Formula: `(2 x CPU cores) + 1` for I/O-bound apps
- For 1000 users: 4-8 workers depending on instance size

### Timeout Settings:
- `--timeout 120` — REQUIRED. AI extraction calls can take 30-60 seconds
- `--graceful-timeout 30` — allows in-flight requests to complete on restart

### systemd Service File (`/etc/systemd/system/vhc-backend.service`):
```ini
[Unit]
Description=VHC Talent OS Backend
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/opt/vhc-backend
EnvironmentFile=/opt/vhc-backend/.env
ExecStart=/opt/vhc-backend/venv/bin/gunicorn server:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8001 \
  --timeout 120 \
  --graceful-timeout 30 \
  --access-logfile /var/log/vhc/access.log \
  --error-logfile /var/log/vhc/error.log
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### IMPORTANT: APScheduler + Multiple Workers
APScheduler runs inside each Gunicorn worker. With 4 workers, each cron job would run 4 times.

**The app already handles this** via the `cron_job_locks` MongoDB collection:
- Each job acquires a distributed lock before running
- Only one worker wins the lock; others skip
- Lock has a TTL (10 min) to prevent deadlocks

This means multi-worker is safe with NO extra configuration.

---

## 3. BACKGROUND JOB REQUIREMENTS

### How Jobs Run:
Jobs start **automatically** when FastAPI boots via `@app.on_event("startup")` in `server.py`. No separate worker process needed.

### All Scheduled Jobs:
| Job ID | Schedule | Timezone | Purpose |
|---|---|---|---|
| `employer_blog` | Mon/Wed/Fri 03:30 | UTC | Auto-publish employer blog posts |
| `candidate_blog` | Tue/Thu 04:30 | UTC | Auto-publish candidate blog posts |
| `attendance_reminder` | Daily 04:30 | UTC (10:00 IST) | Send attendance check-in reminders |
| `auto_absent` | Daily 13:00 | UTC (18:30 IST) | Mark absent for missing check-ins |
| `weekly_blog_digest` | Monday 09:00 | IST | Weekly email digest to subscribers |

### Environment Flags:
- No special flags required — jobs start automatically
- `NOTIFICATION_ENABLED=true` must be set for email notifications
- `RESEND_API_KEY` must be valid for email delivery

### Do You Need a Separate Worker?
**NO.** APScheduler runs in-process. The distributed lock via MongoDB ensures only one worker executes each job.

---

## 4. FRONTEND DEPLOYMENT

### Requirements:
- **Node.js:** v20.x (v20.20.0 tested)
- **Package Manager:** Yarn (NOT npm — npm causes breaking changes)
- **Build System:** Create React App (react-scripts)

### Build Commands:
```bash
cd /opt/vhc-frontend

# Install dependencies
yarn install

# Create production .env (BEFORE building)
cat > .env << 'EOF'
REACT_APP_BACKEND_URL=https://api.ventureshrd.com
REACT_APP_TURNSTILE_SITE_KEY=0x4AAAAAACgOPnW4zAm8nURa
GENERATE_SOURCEMAP=false
DISABLE_ESLINT_PLUGIN=true
EOF

# Build
yarn build
```

### Output Directory:
`/opt/vhc-frontend/build/` — this is the directory Nginx serves as static files.

### Nginx Configuration for Frontend:
```nginx
server {
    listen 443 ssl http2;
    server_name ventureshrd.com www.ventureshrd.com;

    ssl_certificate /etc/letsencrypt/live/ventureshrd.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ventureshrd.com/privkey.pem;

    # Frontend static files
    root /opt/vhc-frontend/build;
    index index.html;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
    gzip_min_length 1000;

    # API proxy to backend
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
        client_max_body_size 50M;
    }

    # Static asset caching
    location /static/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # SPA fallback — all non-API, non-static routes serve index.html
    location / {
        try_files $uri $uri/ /index.html;
    }
}

# HTTP → HTTPS redirect
server {
    listen 80;
    server_name ventureshrd.com www.ventureshrd.com;
    return 301 https://$host$request_uri;
}
```

---

## 5. STATIC ASSET & STORAGE REQUIREMENTS

### Cloudflare R2:
- **YES, required** — all uploaded resumes, CVs, profile photos are stored in R2
- R2 uses S3-compatible API via `boto3`
- No CDN configuration needed — files are served via signed URLs generated by the backend

### No Additional CDN Needed:
- Frontend static assets are served directly by Nginx
- R2 handles file storage with pre-signed URLs for downloads
- No separate CDN layer required

---

## 6. AI SERVICE CONFIGURATION

### Features Using OpenAI (via `OPENAI_API_KEY`):
| Feature | Model | File |
|---|---|---|
| Extension AI profile extraction | gpt-4o-mini | `services/llm_service.py` |
| Resume AI enhancement | gpt-4o-mini | `services/llm_service.py` |
| Blog auto-generation | gpt-4o-mini | `services/llm_service.py` |
| ATS CV generation | gpt-4o-mini | `services/llm_service.py` |

### Features Using Emergent LLM (via `EMERGENT_LLM_KEY`):
| Feature | File |
|---|---|
| Job description parsing | `routes/jobs.py` |
| Industry detection (bulk import) | `routes/bulk_import.py` |
| AI candidate-job matching | `services/matching_engine.py` |

### Can the System Run Using Only OpenAI?
**YES, with minor code changes.** The 3 Emergent LLM features can be rewritten to use the existing `llm_service.py` (which calls OpenAI directly). The Emergent library is essentially a wrapper around OpenAI/Gemini/Claude — it's not providing any unique AI capability.

To remove the Emergent dependency entirely:
1. Replace `LlmChat` calls in `routes/jobs.py`, `routes/bulk_import.py`, `services/matching_engine.py`
2. Use `call_llm()` from `services/llm_service.py` instead
3. Remove `emergentintegrations` from `requirements.txt`
4. Remove `EMERGENT_LLM_KEY` from `.env`

---

## 7. HEALTH CHECK ENDPOINTS

### GET /api/health
**Expected response (healthy):**
```json
{"status": "ok", "import_failures": 0}
```
- `import_failures > 0` means some route modules failed to load — check error logs

### GET /api/health/diagnostics
**Expected response:**
```json
{
    "env_openai_key": "sk-proj-...LlcA",
    "override_openai_key": "sk-proj-...LlcA",
    "keys_match": true,
    "mongo_override_active": false,
    "db_name": "vhc_talent_os",
    "import_failures": 0
}
```
- On AWS: `mongo_override_active` should be `false` (using env var directly)
- `keys_match` will show `null` if override file is deleted (expected)
- `import_failures` must be `0`

---

## 8. FINAL AWS DEPLOYMENT CHECKLIST

### Pre-Flight
```bash
# 1. Verify .env is complete
grep -c "REPLACE\|your_" /opt/vhc-backend/.env
# Expected: 0 (all placeholders replaced)

# 2. Verify Python version
python3 --version
# Expected: Python 3.11.x

# 3. Verify Node version
node --version
# Expected: v20.x.x
```

### Backend Verification
```bash
# 4. Health check
curl -s https://api.ventureshrd.com/api/health
# Expected: {"status":"ok","import_failures":0}

# 5. Diagnostics
curl -s https://api.ventureshrd.com/api/health/diagnostics
# Expected: db_name=vhc_talent_os, import_failures=0

# 6. Admin login
curl -s -X POST https://api.ventureshrd.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@vhc.in","password":"YOUR_ADMIN_PASSWORD"}'
# Expected: {"access_token":"eyJ..."}

# 7. Database connectivity (candidate count)
TOKEN="eyJ..."  # from step 6
curl -s "https://api.ventureshrd.com/api/candidate-bank?page=1&page_size=1" \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"total":2032+, ...}
```

### AI Service Verification
```bash
# 8. OpenAI (test via AI extract)
curl -s -X POST https://api.ventureshrd.com/api/extension/ai-extract \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"html":"<div>John Doe - 5 years Python - john@test.com</div>"}'
# Expected: 200 OK with extracted profile data (NOT 401)

# 9. Check backend logs for LLM key info
sudo journalctl -u vhc-backend --no-pager | grep "API key loaded"
# Expected: [LLM] API key loaded from env: sk-proj-...
```

### Scheduler Verification
```bash
# 10. Check scheduler is running
sudo journalctl -u vhc-backend --no-pager | grep -i "scheduler"
# Expected: [BlogScheduler] Auto-publish scheduler started
#           [AttendanceScheduler] Cron jobs started
```

### Frontend Verification
```bash
# 11. Frontend loads
curl -s -o /dev/null -w "%{http_code}" https://ventureshrd.com
# Expected: 200

# 12. Frontend can reach API
curl -s https://ventureshrd.com/api/health
# Expected: {"status":"ok","import_failures":0}
```

### Email Verification
```bash
# 13. Trigger a test (e.g., password reset)
curl -s -X POST https://api.ventureshrd.com/api/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@vhc.in"}'
# Expected: 200 OK + email received
```

### Storage Verification
```bash
# 14. Upload a test file
curl -s -X POST https://api.ventureshrd.com/api/candidate-bank/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test_resume.pdf"
# Expected: 200 OK with candidate_id
```

### Service Connectivity Summary
| Service | Test Command | Expected |
|---|---|---|
| MongoDB Atlas | `/api/health` | `{"status":"ok"}` |
| OpenAI | `/api/extension/ai-extract` | 200 (not 401) |
| Cloudflare R2 | Upload a file | 200 |
| Resend | Password reset email | Email received |
| Upstash Redis | Check backend logs | `Redis client initialized` |
| Turnstile | Submit public form | CAPTCHA validates |

---

## CLEANUP: Remove Emergent-Specific Files

After verifying everything works on AWS:
```bash
# Optional: remove the override file (no longer needed)
rm /opt/vhc-backend/mongo_production_override.py

# Optional: clean up Emergent-specific deployment artifacts
rm -rf /opt/vhc-backend/.emergent/
```

The application is now fully independent of Emergent infrastructure.
