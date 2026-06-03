# VHC Extension v5.5.10 — Admin-only install guide

**Status:** Admin (admin@vhc.in) gets v5.5.10 manually. Team auto-update is **NOT touched** — they stay on v5.5.8 until you validate.

---

## What's in v5.5.10

1. **Async capture** — `POST /capture/async` returns 202 + job_id instantly; extension polls status until done. Fixes the orphaned "Processing" UI + 502 errors caused by Chrome MV3 30s service-worker kills + Cloudflare 100s edge timeouts.
2. **`/v3/simcv` skip** — extension now does nothing on Naukri's "Recruiters also viewed" overlay page (no auto-capture, no bulk button, no badge logic).
3. **ResDex overlay handling** — when a profile preview opens on top of a search results page, the profile capture fires correctly (was previously misdetected as a list page).

---

## Step 1 — Deploy backend on AWS

```bash
cd /home/ubuntu/vhc-platform
git pull origin main
sudo systemctl restart vhc-backend
curl -s https://api.ventureshrd.com/api/extension/capture/status/test 2>&1 | head -c 200
```

Expect `{"detail":"Not authenticated"}` (403) or `{"detail":"Capture job not found"}` (404 with token) — confirms the new endpoints are live.

**Do NOT update update.xml.** Leave it pointing at v5.5.8. Verify:
```bash
curl -s https://api.ventureshrd.com/api/extension/update.xml | grep version=
```
Should still print `version='5.5.8'`.

---

## Step 2 — Install v5.5.10 unpacked on admin's Chrome

1. Download the zip (must be logged in as admin@vhc.in):
   `https://api.ventureshrd.com/api/extension/download-zip?v=5.5.10`
   (or scp from AWS: `/home/ubuntu/vhc-platform/backend/static/extensions/vhc-naukri-extension-v5.5.10.zip`)

2. Unzip to a stable folder on your machine, e.g. `~/Documents/vhc-extension-v5.5.10/`. **Don't delete the folder later** — unpacked extensions reference the original folder, not a copy.

3. Open `chrome://extensions`.

4. **First**, find the existing VHC extension and click **Remove** (or just disable it via the toggle — either is fine).

5. Toggle **Developer mode** (top-right).

6. Click **Load unpacked** → pick the unzipped `vhc-extension-v5.5.10` folder.

7. Confirm it loads — you should see `VHC Talent OS - Multi-Platform Capture` version **5.5.10**.

8. Click the extension icon → log in with `admin@vhc.in` if prompted.

---

## Step 3 — Validate

### A. Async capture works
- Open any Naukri profile (`/v3/preview?tabKey=profile&...`).
- Open DevTools → background service-worker console (`chrome://extensions` → "service worker" link under the extension).
- Look for:
  - `[VHC BG v5.5.10] ...`
  - Network tab on the service worker should show `POST /api/extension/capture/async` returning 202, followed by repeated `GET /api/extension/capture/status/<job_id>` 200s.
- The popup should show the capture moving from queued → done as before.

### B. simcv is skipped
- Open a `/v3/simcv?uniqueId=...` page (click any "Recruiters also viewed" item).
- Page console (NOT service worker) should print:
  ```
  [VHC v5.5.10] Excluded Naukri page (/v3/simcv) — extension idle (no auto-capture, no bulk button)
  ```
- Floating "Capture" button should not appear. No DOM scrape logs.

### C. Team is unaffected
- On a teammate's Chrome (still v5.5.8), open `chrome://extensions` and confirm the version is `5.5.8`. Their capture flow should still work normally (sync `/capture` endpoint is untouched).

---

## Step 4 — Promote to team (later, only when you're confident)

When you're happy with v5.5.10 on admin:

```bash
cd /home/ubuntu/vhc-platform/backend
source venv/bin/activate
python scripts/build_extension_crx.py \
    --source /home/ubuntu/vhc-platform/browser-extension-v5.5.10 \
    --key /home/ubuntu/vhc-platform/backend/secrets/extension_key.pem \
    --out /home/ubuntu/vhc-platform/backend/static/extensions \
    --version auto
deactivate
sudo systemctl reload nginx
curl -s https://api.ventureshrd.com/api/extension/update.xml | grep version=
```

`update.xml` will now report `version='5.5.10'`. Chrome polls every ~5 hours; teammates can also force an update via `chrome://extensions` → "Update".

---

## Rollback

If anything goes wrong on admin's Chrome:
1. `chrome://extensions` → Remove v5.5.10
2. Click the install link from your team docs (re-installs v5.5.8 from `update.xml`)

Backend rollback (if `/capture/async` causes issues):
- The new endpoints are additive. To disable, simply don't use v5.5.10. The old sync `/capture` is untouched.
- If you ever want to remove the endpoints, revert the `# ASYNC CAPTURE — v5.5.10` block in `backend/routes/extension.py`.
