# VHC Talent OS — Production Security Activation Checklist

## Quick Overview
All security layers are implemented as **opt-in** via environment variables.  
Zero code changes needed — just set the variables and restart.

---

## 1. Cloudflare Turnstile (CAPTCHA)

### What it protects
- Candidate registration (`/register`)
- Resume upload (`/api/public/parse-resume`)
- Job applications (`/api/public/apply`)

### Activation Steps
1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com) → **Turnstile** → **Add Site**
2. Configure:
   - **Site name:** `VHC Talent OS`
   - **Domain:** `ventureshrd.com`
   - **Widget mode:** Managed (recommended)
3. Copy the **Site Key** and **Secret Key**
4. Set environment variables:

**Backend** (`/app/backend/.env`):
```
TURNSTILE_SECRET_KEY=<your-secret-key>
TURNSTILE_SITE_KEY=<your-site-key>
```

**Frontend** (`/app/frontend/.env`):
```
REACT_APP_TURNSTILE_SITE_KEY=<your-site-key>
```

5. Restart both services

### Verification
```bash
curl -X POST https://ventureshrd.com/api/system-health/security-validation \
  -H "Authorization: Bearer <admin-token>"
# Check: turnstile.status = "PASS"
```

---

## 2. Cloudflare Zero Trust Access

### What it protects
- All admin routes (`/admin/*`, `/api/admin/*`)
- Requires Cloudflare Access authentication before reaching the app

### Activation Steps
1. Go to [Cloudflare Zero Trust](https://one.dash.cloudflare.com) → **Access** → **Applications**
2. Create a **Self-hosted** application:
   - **Domain:** `ventureshrd.com`
   - **Path:** `/admin`
3. Add an access policy (e.g., allow `@vhc.in` emails)
4. Copy the **Application Audience (AUD) Tag** from application settings
5. Note your **Team domain** (from the Zero Trust dashboard URL)
6. Set environment variables:

**Backend** (`/app/backend/.env`):
```
CF_ACCESS_TEAM_DOMAIN=<your-team-name>
CF_ACCESS_AUD=<your-application-aud-tag>
```

7. Restart backend

### Detailed Setup
See `/app/docs/ZERO_TRUST_SETUP.md` for comprehensive instructions.

### Verification
```bash
curl -X POST https://ventureshrd.com/api/system-health/security-validation \
  -H "Authorization: Bearer <admin-token>"
# Check: zero_trust.status = "PASS"
```

---

## 3. ClamAV Virus Scanner

### What it protects
- All file uploads (resume parsing, job applications, CV uploads)
- Scans for viruses, trojans, and malware before file processing

### Infrastructure Setup
**Option A: Docker (Recommended)**
```bash
docker run -d --name clamav -p 3310:3310 clamav/clamav:latest
```

**Option B: System Package**
```bash
sudo apt-get install clamav clamav-daemon
sudo systemctl start clamav-daemon
```

### Activation Steps
1. Ensure ClamAV daemon is running and accessible
2. Set environment variables:

**Backend** (`/app/backend/.env`):
```
CLAMAV_HOST=<clamav-host-ip>
CLAMAV_PORT=3310
CLAMAV_ENABLED=true
```

3. Restart backend

### Verification
```bash
curl -X POST https://ventureshrd.com/api/system-health/security-validation \
  -H "Authorization: Bearer <admin-token>"
# Check: clamav.status = "PASS"
```

---

## 4. All Environment Variables Summary

| Variable | Location | Purpose |
|----------|----------|---------|
| `TURNSTILE_SECRET_KEY` | backend/.env | Turnstile server-side verification |
| `TURNSTILE_SITE_KEY` | backend/.env | Reference (optional) |
| `REACT_APP_TURNSTILE_SITE_KEY` | frontend/.env | Turnstile widget rendering |
| `CF_ACCESS_TEAM_DOMAIN` | backend/.env | Zero Trust team identifier |
| `CF_ACCESS_AUD` | backend/.env | Zero Trust audience tag |
| `CLAMAV_HOST` | backend/.env | ClamAV daemon hostname/IP |
| `CLAMAV_PORT` | backend/.env | ClamAV daemon port (default: 3310) |
| `CLAMAV_ENABLED` | backend/.env | Enable/disable ClamAV scanning |

---

## 5. Post-Activation Verification

### Quick Check (API)
```bash
# Get admin token
TOKEN=$(curl -s -X POST https://ventureshrd.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@vhc.in","password":"VhcAdmin@2024"}' | jq -r '.access_token')

# Run security validation
curl -s https://ventureshrd.com/api/system-health/security-validation \
  -H "Authorization: Bearer $TOKEN" | jq .
```

### Expected Output (All Active)
```json
{
  "overall": "PASS",
  "score": 100,
  "layers": {
    "turnstile": { "status": "PASS", "detail": "Enabled" },
    "zero_trust": { "status": "PASS", "detail": "Enabled" },
    "clamav": { "status": "PASS", "detail": "Connected" },
    "rate_limiting": { "status": "PASS", "detail": "Active" },
    "file_validation": { "status": "PASS", "detail": "Active" },
    "security_logging": { "status": "PASS", "detail": "Active" },
    "xss_prevention": { "status": "PASS", "detail": "Active" }
  }
}
```

### Dashboard Check
1. Login as admin → System Health → Check all 11 service cards are green
2. Navigate to Security Audit Dashboard → Verify posture score is 100
3. Download Maintenance Report → Section 8 should show ClamAV status

---

## Rollback
To disable any layer, simply empty its env variables and restart:
```bash
TURNSTILE_SECRET_KEY=
CF_ACCESS_TEAM_DOMAIN=
CLAMAV_ENABLED=false
```
