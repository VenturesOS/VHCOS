# AWS Migration — Quick Fix Guide
## Generated: March 2026

This guide addresses ALL known migration blockers when moving VHC Talent OS from Emergent to AWS.

---

## 1. CAPTCHA (Cloudflare Turnstile) — Fixes 403 on `/api/public/apply`

**Root Cause:** The Turnstile secret key is domain-bound. When switching domains, Cloudflare rejects the token.

**Fix Options (pick one):**

### Option A: Update Turnstile widget (recommended for production)
1. Go to [Cloudflare Dashboard → Turnstile](https://dash.cloudflare.com)
2. Select your widget
3. Under "Domains", add your new AWS domain (e.g., `api.yourdomain.com`, `yourdomain.com`)
4. Save

### Option B: Temporarily disable Turnstile
In your `.env` file:
```
TURNSTILE_SECRET_KEY=DISABLED
```
This bypasses CAPTCHA verification entirely. Use during testing only.

### Option C: Create a new Turnstile widget
1. Create a new widget on Cloudflare with your AWS domain
2. Update both `.env` variables:
   ```
   TURNSTILE_SECRET_KEY=your_new_secret_key
   TURNSTILE_SITE_KEY=your_new_site_key
   ```
3. Update the frontend `.env`:
   ```
   REACT_APP_TURNSTILE_SITE_KEY=your_new_site_key
   ```

---

## 2. AI Features (LLM) — Resume Parsing, JD Parsing, AI Matching

**Root Cause:** The app used Emergent's proprietary `emergentintegrations` library which requires `EMERGENT_LLM_KEY`.

**What Changed:** The codebase now has an automatic fallback:
- If `emergentintegrations` is installed AND `EMERGENT_LLM_KEY` is set → Uses Emergent LLM
- Otherwise → Falls back to direct OpenAI API via `OPENAI_API_KEY`

**For AWS:** Just set a valid OpenAI API key in `.env`:
```
OPENAI_API_KEY=sk-proj-your-openai-key-here
EMERGENT_LLM_KEY=
```

If you want to use the Emergent library on AWS:
```bash
pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
```
Then set `EMERGENT_LLM_KEY` in your `.env`.

---

## 3. Hardcoded URLs — Now Configurable via `SITE_URL`

**Root Cause:** URLs like `https://ventureshrd.com` were hardcoded in sitemap, RSS, emails, etc.

**Fix:** Add `SITE_URL` to your `.env`:
```
SITE_URL=https://ventureshrd.com
```

This is now used by:
- Sitemap XML generation
- RSS feeds
- Password reset email links
- Blog URLs in LinkedIn posts
- Email digest links
- CORS origin auto-inclusion

---

## 4. Chrome Extension MIME Type Error — Nginx Config

**Root Cause:** Nginx on AWS is not serving `.js` files with the correct `Content-Type` header.

**Fix:** Add these MIME types to your Nginx config:

```nginx
# /etc/nginx/nginx.conf or /etc/nginx/conf.d/vhc.conf

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    # Ensure JavaScript files are served with correct MIME type
    types {
        application/javascript  js mjs;
        text/css                css;
        application/json        json;
    }

    server {
        listen 443 ssl;
        server_name yourdomain.com;

        # Frontend (React static files)
        location / {
            root /opt/vhc-frontend/build;
            try_files $uri /index.html;

            # Ensure correct MIME types for static assets
            location ~* \.(js|mjs)$ {
                add_header Content-Type application/javascript;
            }
        }

        # Backend API proxy
        location /api/ {
            proxy_pass http://127.0.0.1:8001;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 120s;
            client_max_body_size 50M;
        }

        # Browser extension static files
        location /extension/ {
            alias /opt/vhc-extension/;
            add_header Content-Type application/javascript;
        }
    }
}
```

After editing, reload Nginx:
```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## 5. Complete `.env` Checklist for AWS

Copy `.env.production.template` and verify these critical variables:

| Variable | Purpose | Required? |
|----------|---------|-----------|
| `MONGO_URL` | MongoDB Atlas connection | YES |
| `DB_NAME` | Database name | YES |
| `OPENAI_API_KEY` | AI features (fallback) | YES |
| `JWT_SECRET_KEY` | Auth token signing | YES |
| `SITE_URL` | Base URL for links/SEO | YES |
| `CORS_ORIGINS` | Allowed origins | YES |
| `RESEND_API_KEY` | Email sending | YES |
| `R2_ACCOUNT_ID` | File storage | YES |
| `R2_ACCESS_KEY_ID` | File storage | YES |
| `R2_SECRET_ACCESS_KEY` | File storage | YES |
| `TURNSTILE_SECRET_KEY` | CAPTCHA (`DISABLED` to skip) | CONFIGURABLE |
| `EMERGENT_LLM_KEY` | Emergent AI (empty = use OpenAI) | OPTIONAL |

---

## 6. `mongo_production_override.py` — No Longer Needed on AWS

This file was a workaround for Emergent's platform overwriting `.env` during deployment.
On AWS, you control your own `.env`, so you can safely:
1. Remove `mongo_production_override.py` from the backend directory
2. Or leave it — the app will prefer it if present, fall back to `.env` if not

---

## 7. DNS & Email (Resend)

Ensure your domain's DNS records include SPF and DKIM for Resend:
- Follow Resend's domain verification at https://resend.com/domains
- Verify `noreply@ventureshrd.com` can send emails

---

## 8. Services That Work Without Changes

These services are already portable and just need credentials in `.env`:
- **Cloudflare R2** — Standard S3-compatible API, works from any server
- **Upstash Redis** — REST-based, works from any server
- **MongoDB Atlas** — Cloud database, works from any IP (ensure AWS IP is in Atlas whitelist)
