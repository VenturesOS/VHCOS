# VHC Talent OS — AWS Migration Blueprint
# Complete Technical Audit & Migration Guide
# Generated: March 2, 2026

---

## 1. ENVIRONMENT VARIABLES

### Core Application
| Variable | Purpose | Required |
|---|---|---|
| `MONGO_URL` | MongoDB Atlas connection URI | YES |
| `DB_NAME` | Database name (`vhc_talent_os`) | YES |
| `JWT_SECRET_KEY` | JWT token signing secret | YES |
| `JWT_ALGORITHM` | JWT algorithm (`HS256`) | YES |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token TTL in minutes (`1440` = 24h) | YES |
| `ADMIN_EMAIL` | Default admin email (`admin@vhc.in`) | YES |
| `ADMIN_PASSWORD` | Default admin password (first-run seeding) | YES |
| `CORS_ORIGINS` | Comma-separated allowed origins | YES |
| `FRONTEND_URL` | Frontend URL for email links | YES |
| `APP_URL` | Backend API URL | NO (used for self-reference) |
| `APP_ENV` | Environment name | NO (auto-detected) |

### AI / LLM
| Variable | Purpose | Required |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key (GPT-4o-mini) for AI extraction, resume enhancement | YES |
| `EMERGENT_LLM_KEY` | Emergent platform LLM proxy key — **SEE MIGRATION NOTE** | YES* |
| `LLM_DEFAULT_MODEL` | Default OpenAI model (`gpt-4o-mini`) | NO |
| `BLOG_LLM_MAX_TOKENS` | Blog AI token limit | NO |
| `BLOG_LLM_TEMPERATURE` | Blog AI temperature | NO |

### Email (Resend)
| Variable | Purpose | Required |
|---|---|---|
| `RESEND_API_KEY` | Resend.com API key for transactional emails | YES |
| `SENDER_EMAIL` | From address (`noreply@ventureshrd.com`) | YES |

### Object Storage (Cloudflare R2)
| Variable | Purpose | Required |
|---|---|---|
| `R2_ACCOUNT_ID` | Cloudflare account ID | YES |
| `R2_ACCESS_KEY_ID` | R2 access key | YES |
| `R2_SECRET_ACCESS_KEY` | R2 secret key | YES |
| `R2_BUCKET_NAME` | Storage bucket (`vhc-talent-os-storage`) | YES |
| `R2_ENDPOINT` | Custom endpoint (auto-generated if empty) | NO |

### Caching (Upstash Redis)
| Variable | Purpose | Required |
|---|---|---|
| `UPSTASH_REDIS_REST_URL` | Redis REST endpoint | RECOMMENDED |
| `UPSTASH_REDIS_REST_TOKEN` | Redis auth token | RECOMMENDED |

*Note: App falls back to in-memory caching if Redis is unavailable. But multi-worker deployments NEED Redis for shared state.*

### LinkedIn Integration
| Variable | Purpose | Required |
|---|---|---|
| `LINKEDIN_CLIENT_ID` | LinkedIn OAuth app ID | NO (feature disabled) |
| `LINKEDIN_CLIENT_SECRET` | LinkedIn OAuth secret | NO |
| `LINKEDIN_REDIRECT_URI` | OAuth callback URL | NO |

### Cloudflare Security
| Variable | Purpose | Required |
|---|---|---|
| `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile CAPTCHA server key | YES |
| `TURNSTILE_SITE_KEY` | Turnstile client-side key | YES |
| `CF_ACCESS_TEAM_DOMAIN` | Zero Trust team domain | NO (disabled) |
| `CF_ACCESS_AUD` | Zero Trust audience tag | NO (disabled) |
| `CF_ACCESS_ENFORCE` | Enable Zero Trust (`false`) | NO |

### WhatsApp (Optional, not configured)
| Variable | Purpose | Required |
|---|---|---|
| `TWILIO_ACCOUNT_SID` | Twilio account | NO |
| `TWILIO_AUTH_TOKEN` | Twilio auth | NO |
| `TWILIO_WHATSAPP_NUMBER` | WhatsApp sender | NO |

### ClamAV (Optional, not configured)
| Variable | Purpose | Required |
|---|---|---|
| `CLAMAV_HOST` | ClamAV daemon host | NO |
| `CLAMAV_PORT` | ClamAV port (`3310`) | NO |
| `CLAMAV_ENABLED` | Enable antivirus scan (`false`) | NO |

### Frontend
| Variable | Purpose | Required |
|---|---|---|
| `REACT_APP_BACKEND_URL` | API base URL (e.g. `https://api.ventureshrd.com`) | YES |
| `REACT_APP_TURNSTILE_SITE_KEY` | Turnstile client key | YES |

---

## 2. DATABASE CONFIGURATION

### Connection Logic (config.py)

The application connects to MongoDB via this priority chain:

```
1. Try to import mongo_production_override.py
   → If file exists AND URI contains "cluster0.vuhdiod.mongodb.net"
   → Use override URI (sets _override_active = True)

2. Fall back to environment variables:
   → MONGO_URL (primary)
   → MONGODB_URI (fallback)
   → MONGODB_URL (fallback)

3. If nothing found: log CRITICAL error, use placeholder (server starts but DB ops fail)
```

### For AWS Migration:
- **DELETE `mongo_production_override.py`** — it was created specifically to bypass Emergent's .env overwrite
- Set `MONGO_URL` directly in your AWS environment / `.env` file
- The override file is no longer needed when you control the environment

### Pool Configuration:
```
maxPoolSize: 50
minPoolSize: 5
maxIdleTimeMS: 45000
waitQueueTimeoutMS: 20000
serverSelectionTimeoutMS: 20000
connectTimeoutMS: 15000
socketTimeoutMS: 45000
retryWrites: True
retryReads: True
maxConnecting: 4
TLS: True (via certifi CA bundle)
```

### Does Emergent inject its own Mongo URI?
**YES.** Emergent overwrites `backend/.env` during deployment, replacing `MONGO_URL` with its own managed local MongoDB. That's why `mongo_production_override.py` exists — it's a Python file that survives the `.env` overwrite.

**On AWS: this is not needed.** Just set `MONGO_URL` in your systemd environment or `.env`.

---

## 3. EXTERNAL SERVICES

### 1. OpenAI (GPT-4o-mini)
- **Purpose:** AI profile extraction (extension), resume enhancement, blog generation
- **Env vars:** `OPENAI_API_KEY`
- **SDK:** `httpx` (direct HTTP calls to `api.openai.com/v1/chat/completions`)
- **Files:** `services/llm_service.py`

### 2. Emergent LLM Proxy ⚠️ MIGRATION REQUIRED
- **Purpose:** Job description parsing, industry detection, candidate-job matching
- **Env vars:** `EMERGENT_LLM_KEY`
- **SDK:** `emergentintegrations` (Emergent-specific library)
- **Files:** `routes/jobs.py`, `routes/bulk_import.py`, `services/matching_engine.py`
- **Install:** `pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/`
- **⚠️ NOTE:** This library proxies LLM calls through Emergent's infrastructure. It will continue to work on AWS as long as:
  1. The package is installed from the special pip index above
  2. `EMERGENT_LLM_KEY` is set in the environment
  3. The server can reach `https://integrations.emergentagent.com`
- **Alternative:** Replace these 3 files to use direct OpenAI calls via `llm_service.py` instead

### 3. Cloudflare R2 (Object Storage)
- **Purpose:** Resume/CV file storage, profile photos
- **Env vars:** `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`
- **SDK:** `boto3` (S3-compatible API)
- **Files:** `config.py` (client init), `services/storage.py`

### 4. Resend (Email)
- **Purpose:** Transactional emails (notifications, password reset, digests)
- **Env vars:** `RESEND_API_KEY`, `SENDER_EMAIL`
- **SDK:** `resend` Python package
- **Files:** `services/email_service.py`, `services/digest_email_service.py`

### 5. Upstash Redis (Caching)
- **Purpose:** Rate limiting, response caching, session dedup
- **Env vars:** `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`
- **SDK:** `upstash-redis` Python package
- **Files:** `services/cache.py`, `services/rate_limiter.py`
- **Note:** Falls back to in-memory dict if Redis unavailable. Multi-worker deployments need Redis.

### 6. Cloudflare Turnstile (CAPTCHA)
- **Purpose:** Bot protection on public forms (apply, register)
- **Env vars:** `TURNSTILE_SECRET_KEY` (backend), `REACT_APP_TURNSTILE_SITE_KEY` (frontend)
- **SDK:** Direct HTTP call to `challenges.cloudflare.com/turnstile/v0/siteverify`
- **Files:** `services/security_service.py`

### 7. LinkedIn OAuth (Blocked)
- **Purpose:** Social login, auto-posting (blocked pending LinkedIn scope approval)
- **Env vars:** `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`, `LINKEDIN_REDIRECT_URI`
- **SDK:** `httpx`
- **Files:** `routes/linkedin.py`, `services/linkedin_service.py`

---

## 4. BACKGROUND JOBS / SCHEDULERS

All schedulers run **in-process** via APScheduler (no separate worker needed). They start automatically in the `@app.on_event("startup")` handler in `server.py`.

### Blog Auto-Publisher
| Job ID | Schedule | Timezone | File |
|---|---|---|---|
| `employer_blog` | Mon, Wed, Fri @ 03:30 | UTC | `services/blog_scheduler.py` |
| `candidate_blog` | Tue, Thu @ 04:30 | UTC | `services/blog_scheduler.py` |

### Attendance System
| Job ID | Schedule | Timezone | File |
|---|---|---|---|
| `attendance_reminder` | Daily @ 04:30 | UTC (10:00 IST) | `services/attendance_cron_service.py` |
| `auto_absent` | Daily @ 13:00 | UTC (18:30 IST) | `services/attendance_cron_service.py` |

### Weekly Digest
| Job ID | Schedule | Timezone | File |
|---|---|---|---|
| `weekly_blog_digest` | Monday @ 09:00 | IST | `services/scheduler.py` |

### Health Monitor & Maintenance Bot
- `services/health_monitor.py` — runs periodic health checks (CPU, memory, DB connectivity)
- `services/maintenance_bot.py` — background loop every 5 minutes, manages stress mode

### Cron Lock Mechanism
- Uses `cron_job_locks` MongoDB collection with unique index on `job_name`
- Ensures only one instance runs a scheduled job (safe for multi-replica deployments)

### For AWS:
- With **Gunicorn multi-worker**, APScheduler will run in EACH worker. Use `--preload` or configure a single scheduler worker to avoid duplicate job execution.
- Alternatively: extract scheduled jobs to a separate process or use a dedicated task runner.

---

## 5. STATIC ASSETS / FRONTEND

### Build System
- **Framework:** React (Create React App)
- **Build command:** `yarn build` (outputs to `frontend/build/`)
- **Package manager:** Yarn

### How Emergent Serves Frontend:
- `yarn start` on port 3000 (development server with hot reload)
- Nginx proxies: `/api/*` → port 8001 (backend), everything else → port 3000 (frontend)

### For AWS Production:
```bash
cd frontend && yarn install && yarn build
```
- Serve `frontend/build/` as static files via Nginx
- Do NOT run `yarn start` in production — use the built static files

### Frontend Environment Variables:
```bash
# Set BEFORE building (baked into the JS bundle at build time)
REACT_APP_BACKEND_URL=https://api.ventureshrd.com
REACT_APP_TURNSTILE_SITE_KEY=0x4AAAAAACgOPnW4zAm8nURa
```

---

## 6. RUNTIME CONFIGURATION

### Versions
- **Python:** 3.11.x
- **Node.js:** 20.x (for frontend build only)
- **MongoDB:** Atlas (cloud) — no local instance needed

### Required System Packages
```bash
# None strictly required — all deps are pure Python
# PyMuPDF (fitz) ships its own binaries via pip
# No pdflatex/texlive needed — fpdf2 handles PDF generation
```

### Python Dependencies
174 packages total. Key ones:
```
fastapi==0.110.1
uvicorn==0.25.0
motor==3.4.0          # Async MongoDB driver
PyMuPDF==1.26.7       # PDF text extraction
fpdf2==2.8.7          # PDF generation
boto3==1.42.21        # R2 storage
httpx==0.28.1         # HTTP client (OpenAI, LinkedIn)
resend==2.19.0        # Email
upstash-redis==1.6.0  # Caching
apscheduler==3.10.4   # Scheduled jobs
bcrypt==4.1.3         # Password hashing
PyJWT==2.8.0          # JWT tokens
python-dotenv==1.2.1  # .env loading
certifi==2026.1.4     # TLS CA certificates
psutil==7.2.2         # System health monitoring
emergentintegrations==0.1.0  # ⚠️ Emergent LLM proxy
```

### Emergent Startup Command:
```bash
uvicorn server:app --host 0.0.0.0 --port 8001 --workers 1 --reload
```

### Recommended AWS Startup Command:
```bash
gunicorn server:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8001 --timeout 120 --graceful-timeout 30
```

---

## 7. NETWORK & ROUTING

### Emergent Internal Routing:
```
Client → Kubernetes Ingress → Nginx
  /api/*  → 127.0.0.1:8001 (FastAPI backend)
  /*      → 127.0.0.1:3000 (React dev server)
```

### AWS Nginx Config (Recommended):
```nginx
server {
    listen 443 ssl;
    server_name ventureshrd.com www.ventureshrd.com;

    # Frontend (static build)
    root /path/to/frontend/build;
    index index.html;

    # API proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        client_max_body_size 50M;
    }

    # Frontend SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

### CORS Configuration:
Hardcoded origins in `server.py`:
```python
"https://ventureshrd.com"
"https://www.ventureshrd.com"
```
Plus any values from `CORS_ORIGINS` env var. **Add `https://api.ventureshrd.com` if API and frontend are on different subdomains.**

### Webhook Endpoints:
- `POST /api/extension/capture` — Browser extension profile capture
- `POST /api/extension/ai-extract` — AI-powered profile extraction

---

## 8. REQUIRED SECRETS

| Secret | Variable Name | Purpose |
|---|---|---|
| JWT Signing Key | `JWT_SECRET_KEY` | Signs/verifies all auth tokens |
| OpenAI API Key | `OPENAI_API_KEY` | AI features (extraction, enhancement) |
| Emergent LLM Key | `EMERGENT_LLM_KEY` | LLM proxy for matching/parsing |
| Resend API Key | `RESEND_API_KEY` | Transactional email delivery |
| R2 Access Key | `R2_ACCESS_KEY_ID` | Object storage auth |
| R2 Secret Key | `R2_SECRET_ACCESS_KEY` | Object storage auth |
| Upstash Redis Token | `UPSTASH_REDIS_REST_TOKEN` | Cache/rate limit auth |
| Turnstile Secret | `TURNSTILE_SECRET_KEY` | CAPTCHA verification |
| LinkedIn Secret | `LINKEDIN_CLIENT_SECRET` | OAuth (if enabled) |
| Admin Password | `ADMIN_PASSWORD` | First-run admin seeding |

---

## 9. PRODUCTION STARTUP COMMANDS

### Backend
```bash
# Install dependencies
cd backend
pip install -r requirements.txt
pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/

# Start with Gunicorn
gunicorn server:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8001 \
  --timeout 120 \
  --graceful-timeout 30 \
  --access-logfile - \
  --error-logfile -
```

### Frontend (Build Once)
```bash
cd frontend
yarn install
REACT_APP_BACKEND_URL=https://api.ventureshrd.com \
REACT_APP_TURNSTILE_SITE_KEY=0x4AAAAAACgOPnW4zAm8nURa \
yarn build
# Serve frontend/build/ via Nginx
```

---

## 10. MIGRATION CHECKLIST

### Pre-Migration
- [ ] AWS EC2 instance provisioned (recommended: t3.xlarge or larger for 1000 users)
- [ ] Python 3.11.x installed
- [ ] Node.js 20.x installed (for frontend build)
- [ ] Nginx installed and configured with SSL
- [ ] MongoDB Atlas IP whitelist includes AWS EC2 IP
- [ ] DNS records point to AWS (after testing)

### Environment Setup
- [ ] Create `/opt/vhc-backend/.env` with ALL variables from Section 1
- [ ] Set `MONGO_URL` to your Atlas URI directly (no override file needed)
- [ ] Set `CORS_ORIGINS` to include `https://ventureshrd.com,https://www.ventureshrd.com,https://api.ventureshrd.com`
- [ ] Set `FRONTEND_URL=https://ventureshrd.com`
- [ ] Set `APP_URL=https://api.ventureshrd.com`
- [ ] Verify `OPENAI_API_KEY` is valid
- [ ] Verify `RESEND_API_KEY` is valid
- [ ] Verify `R2_*` credentials are valid

### Code Changes for AWS
- [ ] **REMOVE** `mongo_production_override.py` (or leave it — config.py falls back to env vars)
- [ ] **UPDATE** `config.py` line 48: change env var priority to `MONGO_URL` first:
  ```python
  _env_uri = os.environ.get("MONGO_URL") or os.environ.get("MONGODB_URI") or os.environ.get("MONGODB_URL")
  ```
- [ ] **UPDATE** `CORS_ORIGINS` in `.env` to include your AWS domain
- [ ] **INSTALL** `emergentintegrations` from special pip index (or replace with direct OpenAI calls)

### Backend Deployment
- [ ] Clone repo from GitHub
- [ ] `cd backend && pip install -r requirements.txt`
- [ ] `pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/`
- [ ] Test: `python -c "from config import db; print('DB OK')"` 
- [ ] Create systemd service for Gunicorn
- [ ] Start service, verify `/api/health` returns `{"status":"ok"}`

### Frontend Deployment
- [ ] `cd frontend && yarn install`
- [ ] Set `REACT_APP_BACKEND_URL=https://api.ventureshrd.com` in build environment
- [ ] `yarn build`
- [ ] Copy `build/` to Nginx document root
- [ ] Configure Nginx with API proxy + SPA fallback
- [ ] Test: access `https://ventureshrd.com` in browser

### Verification
- [ ] `/api/health` returns `{"status":"ok","import_failures":0}`
- [ ] `/api/health/diagnostics` shows correct Atlas cluster and matching API keys
- [ ] Admin login works: `admin@vhc.in`
- [ ] Candidate bank returns 2000+ candidates
- [ ] Extension capture works (POST `/api/extension/capture`)
- [ ] AI extract works (POST `/api/extension/ai-extract`)
- [ ] File upload works (POST `/api/candidate-bank/upload`)
- [ ] Email notifications send (check Resend dashboard)
- [ ] Blog RSS feed loads (`/api/blog/rss`)

### Ports
| Service | Port | Protocol |
|---|---|---|
| Nginx | 443 | HTTPS |
| Nginx | 80 | HTTP (redirect to 443) |
| Gunicorn/FastAPI | 8001 | HTTP (internal only) |

### Required Outbound Connections
| Service | Endpoint | Port |
|---|---|---|
| MongoDB Atlas | `cluster0.vuhdiod.mongodb.net` | 27017 |
| OpenAI API | `api.openai.com` | 443 |
| Emergent LLM Proxy | `integrations.emergentagent.com` | 443 |
| Cloudflare R2 | `*.r2.cloudflarestorage.com` | 443 |
| Resend Email | `api.resend.com` | 443 |
| Upstash Redis | `*.upstash.io` | 443 |
| Cloudflare Turnstile | `challenges.cloudflare.com` | 443 |

### systemd Service File (Reference)
```ini
[Unit]
Description=VHC Talent OS Backend
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/vhc-backend
EnvironmentFile=/opt/vhc-backend/.env
ExecStart=/opt/vhc-backend/venv/bin/gunicorn server:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8001 --timeout 120
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## EMERGENT-SPECIFIC DEPENDENCIES SUMMARY

| Item | What It Does | AWS Action |
|---|---|---|
| `mongo_production_override.py` | Overrides Emergent's injected MongoDB URI | DELETE or ignore — set MONGO_URL in .env |
| `EMERGENT_LLM_KEY` + `emergentintegrations` | Proxies LLM calls through Emergent | Keep (install from special pip index) OR replace with direct OpenAI |
| `INTEGRATION_PROXY_URL` env var | Emergent injects this in supervisor | Not needed on AWS — ignore |
| `APP_URL` with `preview.emergentagent.com` | Emergent injects this in supervisor | Set to `https://api.ventureshrd.com` |
| `WDS_SOCKET_PORT=443` | React dev server WebSocket config | Not needed — you serve static build |
| `utils/environment.py` detection | Checks for "emergent" in URL for env detection | Will auto-detect as non-Emergent — safe |

---

*This blueprint covers everything needed to run VHC Talent OS on AWS without any Emergent infrastructure dependency.*
