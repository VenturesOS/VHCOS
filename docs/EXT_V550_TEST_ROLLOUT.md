# Extension v5.5.0 — Admin-Only Test Rollout

**Phase 55.9 / Feb 2026** — testing the new "Already in Database" feature
on `admin@vhc.in` ONLY before public rollout.

## What changed in v5.5.0

**Bug fixes** (you'll get these even without doing anything special):
- Background tab profile captures now work reliably
- DOM-based readiness detection (no more arbitrary delays)
- Consolidated duplicate event listeners
- Memory leak fixes in MutationObservers

**New feature: "Already in Database" indicator** ← THE TESTING TARGET
- Green badge on already-captured candidates in Naukri search results
- Dimmed card (65% opacity)
- Confirmation modal before opening an already-captured profile (saves Naukri view credits)
- Works offline via local cache; uses new `/api/extension/check-existing` API when online

## Backend status

| Component | Status |
|---|---|
| `POST /api/extension/check-existing` endpoint | ✅ Live |
| Allowlist gating | ✅ Live (`EXTENSION_CHECK_EXISTING_ALLOWLIST=admin@vhc.in`) |
| Fuzzy name match (uses existing `_names_are_similar`) | ✅ Live |
| Headline → employer high-confidence boost | ✅ Live |
| `update.xml` auto-update version | 🚫 STILL on v5.3.0 (intentional — no public push) |
| E2E backend tests | ✅ 18/18 passing |

## How admin will test (Chrome on the test machine)

### One-time install

1. Download the v5.5.0 zip from server:
   ```
   https://ventureshrd.com/api/extension/download.crx?v=5.5.0
   ```
   *…wait, that's the CRX endpoint. We're not publishing a CRX yet.
   Use this admin-only direct path instead:*
   
   On the EC2 box, copy the zip out to the admin's machine:
   ```bash
   scp ubuntu@<EC2-IP>:/home/ubuntu/vhc-platform/backend/static/extensions/vhc-naukri-extension-v5.5.0.zip ~/Desktop/
   ```
   Or grab it directly from the dev folder:
   `/app/browser-extension-v5.5.0/` (skip the `.zip` and load the folder).

2. Unzip the file → you get a folder `vhc-naukri-extension-v5.5.0/`.

3. **Chrome**:
   - Go to `chrome://extensions/`
   - Top-right: toggle **Developer mode** ON
   - **Remove** the existing "VHC Talent OS" extension first (this prevents conflicts)
   - Click **Load unpacked** → select the unzipped folder
   - Verify it loads as **v5.5.0**

4. Click the extension icon → log in with **admin@vhc.in / VhcAdmin@2024**

### Testing Part A — Background tab capture fixes

| # | Test | Expected |
|---|---|---|
| A1 | On a Naukri Resdex search page, **Ctrl+Click** 5 candidate profiles to open in background tabs. **Don't switch** to those tabs. | All 5 should auto-capture. Verify in extension popup → History. |
| A2 | Open a profile on Slow 3G (DevTools → Network → Slow 3G). | Capture still succeeds within 15s. |
| A3 | Open a profile in background tab, then close the tab before capture finishes. | No console errors. |
| A4 | Click a profile normally (foreground tab). | Existing capture behavior unchanged. |
| A5 | Open browser console — look for `[VHC v5.5.0]` lines. | Should see: "background tab", "Score 2/4" or "3/4", "DOM quietness wait", "Strategy 2 SUCCESS". |

### Testing Part B — "Already in Database" feature (THE NEW THING)

| # | Test | Expected |
|---|---|---|
| B1 | Capture 3-4 profiles via the extension. Return to the Naukri search page. | Those candidates show a green **"Already in Database"** badge and are dimmed. |
| B2 | Hover over a dimmed card. | Smoothly brightens (65% → 95% opacity). |
| B3 | **Left-click** the name of a badged candidate. | A modal appears: *"Profile Already Saved — Opening this profile again might count against your limited Naukri views."* |
| B4 | Click **"No, Skip Profile"**. | Modal closes; profile does NOT open. ✅ View saved. |
| B5 | Click **"Yes, Open Anyway"**. | Modal closes; profile opens normally. |
| B6 | **Middle-click** (mouse wheel) on a badged candidate. | Same modal appears (doesn't bypass). |
| B7 | Infinite-scroll new candidates into view. | Newly loaded cards also get checked & badged. |
| B8 | Navigate between Naukri pagination pages. | Badges re-apply on each new page. |
| B9 | **Disconnect internet** → reload search page. | Badges still appear (local cache fallback works). |

### Testing Part C — Regression

| # | Test | Expected |
|---|---|---|
| C1 | Extension popup login / logout. | Unchanged. |
| C2 | Manual capture via the floating button on a profile page. | Works as before. |
| C3 | Right-click → "VHC: Capture this profile". | Works as before. |
| C4 | Popup → History tab. | All captures with timestamps. |

### Sanity check from the server side

While admin is testing, watch the backend logs to confirm the API is being called:

```bash
ssh ubuntu@<EC2-IP> 'sudo journalctl -u vhc-backend -f | grep -i "checkexisting"'
```

You should see lines like:
```
[CheckExisting] user=admin@vhc.in batch=24 hits=7
```

If you log in as another user and visit the same search page, you should see:
```
[CheckExisting] user=other@vhc.in not in allowlist — returning all-false (extension falls back to local cache)
```

## Rollout to everyone (when admin says "it works")

Two flips, no code change:

```bash
# On EC2
cd /home/ubuntu/vhc-platform

# 1. Open the allowlist
sed -i 's/^EXTENSION_CHECK_EXISTING_ALLOWLIST=.*/EXTENSION_CHECK_EXISTING_ALLOWLIST=*/' backend/.env

# 2. Bump update.xml to point at a signed CRX of v5.5.0
#    (CRX build is a separate step — let me know when you're ready and
#     I'll guide through signing + publishing. Until then, recruiters stay
#     on v5.3.0 via the existing CRX.)

sudo systemctl restart vhc-backend
```

## Rollback (if anything looks wrong)

```bash
# Revert allowlist to admin-only
sed -i 's/^EXTENSION_CHECK_EXISTING_ALLOWLIST=.*/EXTENSION_CHECK_EXISTING_ALLOWLIST=admin@vhc.in/' backend/.env
sudo systemctl restart vhc-backend
```

Admin removes the unpacked extension from `chrome://extensions/` and falls
back to the prod v5.3.0 (still installed via CRX or webstore).
