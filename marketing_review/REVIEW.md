# Marketing Site — Review Notes
**Status:** Staged in `/app/marketing_review/` — NOT deployed.

## What's in the zip you uploaded

| Item | Verdict | Notes |
|---|---|---|
| `website/` (8 HTML pages, logos, CSS, JS) | ✅ Good | Clean static site, SEO ready, role-aware nav |
| `website_backup_20260122_090327/` | ❌ Skip | Older duplicate of `website/`, discarded |
| `app-android.apk` (24 MB) | ⏸ Held | Moved to `backend/_private_data/`. Pending your decision on public download |
| `missing_phone_candidates.csv` (212 KB) | ⚠️ Sensitive | Moved to `backend/_private_data/` (server-side, never served) |
| Root `index.html`, `manifest.json`, `service-worker.js` | ⏭ Skip | These are the React app's PWA shell — already in `frontend/public/` |

## Quality assessment (the `website/` folder)

| Aspect | Assessment |
|---|---|
| SEO | ✅ Proper `<title>`, meta description, canonical, Open Graph |
| Analytics | ✅ GTM (`GTM-TBQDQB77`) + GA4 (`G-MY1EXKECH6`) wired |
| Tracking pixels | ✅ Cloudflare Turnstile on careers form |
| Backend wiring | ✅ Careers page calls **existing live endpoints**: `/api/public/jobs`, `/api/public/parse-resume`, `/api/public/apply`, `/api/public/upload-resume` — all verified in `routes/public.py` |
| Login integration | ✅ Nav links to `/login?role=employer\|recruiter\|candidate` (matches portal routing) |
| Responsive | ✅ Mobile menu, viewport meta, lazy-loaded images |
| Visual identity | ✅ 49 client logos for social proof, consistent green (#7CB342 / #9acd32) theme |
| Pages | 8 — Home, About, Services, Industries, Careers, Contact, Global Hiring, Recruitment Expertise |

## Changes I made in the review staging

1. **Stripped the dead contact form** from `contact.html` (it had `<form>` with no submit handler — replaced with email + phone CTA).
2. Nothing else touched — files are otherwise as you sent them.

## Cleanup checklist before deploying (when you green-light)

- [ ] Decide if Android APK should be downloadable; if yes, where (footer? `/download`?)
- [ ] Verify `API_BASE = 'https://ventureshrd.com'` in `careers.html` is correct for prod
- [ ] Confirm phone number `+91-99999-99999` placeholder in stripped `contact.html` — replace with real number
- [ ] Decide canonical: `ventureshrd.com` or `www.ventureshrd.com` (Index.html uses non-www)

## Deployment path (when you say "go")

We won't deploy until you ask, but the path is short:

1. Move `marketing_review/website/` → `frontend/public/website/` (so `yarn build` copies it to `/var/www/html/website/`)
2. Add an Nginx server block (will be drafted in `docs/MARKETING_NGINX.md`) that maps:
   - `/` → `/website/Index.html`
   - `/about`, `/services`, `/industries`, `/careers`, `/contact`, `/global-hiring`, `/recruitment-expertise` → corresponding `.html`
   - `/website/style.css`, `/website/logos/...` → static
   - Everything else falls through to the React SPA (`/login`, `/admin`, etc.)
3. Run `./scripts/deploy.sh` and verify
4. Update `sitemap.xml`, submit to Google Search Console

**Estimated effort to deploy: ~45 min** including Nginx tweak and smoke testing.
