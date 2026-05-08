# Chrome Web Store Submission — VHC Talent OS Extension

**Account to use:** `siddharth@vhc.in`
**Visibility:** Unlisted
**One-time fee:** $5 USD (Google Developer Program)

---

## Step 1 — Pay the developer fee (5 minutes)

1. Sign in to **siddharth@vhc.in** at: https://chrome.google.com/webstore/devconsole/
2. You'll be prompted to register as a developer → **Pay $5 USD** (one-time).
3. Fill in publisher info:
   - **Publisher name:** Ventures HRD
   - **Publisher email:** siddharth@vhc.in
   - **Website:** https://ventureshrd.com
4. Verify the email if Google asks (link in inbox).

---

## Step 2 — Create the listing (10 minutes)

In the dev console click **"+ New item"** → upload the production ZIP:

📦 **File to upload:** `vhc-naukri-extension-webstore-v5.3.1.zip`
(located at `/app/backend/static/extensions/` — also downloadable from `https://api.ventureshrd.com/api/extension/download.crx?v=webstore`)

After upload, fill in the listing fields below. Copy-paste each block as-is.

---

### Store Listing → Product details

**Title** (max 45 chars)
```
VHC Talent OS — Recruiter Capture
```

**Summary** (max 132 chars)
```
One-click capture of candidate profiles from Naukri, LinkedIn & Foundit into your VHC Talent OS pipeline. AI-extracted, instantly searchable.
```

**Description** (max 16,000 chars — paste everything below)
```
VHC Talent OS — Recruiter Capture

Stop copy-pasting candidate details. With one click on any Naukri Resdex, LinkedIn, or Foundit profile, this extension captures the complete candidate record — name, contact, current company, designation, experience, CTC, notice period, skills, education and full work history — and pipes it directly into your Ventures HRD Talent OS pipeline.

Built for recruiting teams who source 50+ profiles a day.

━━━━━━━━━━━━━━━━━━━━
WHAT IT DOES
━━━━━━━━━━━━━━━━━━━━

• One-click profile capture from Naukri Resdex, LinkedIn, Foundit, and Monster
• Auto-extracts 20+ fields including CTC, notice period, skills, work history
• Reveals & captures contact info (email + phone) when you click "View Contact"
• Reads attached CV/resume content from the candidate's profile iframe
• Auto-shortlists captured candidates to the active job mandate you have open
• Bulk capture: scrape an entire Naukri search-results page in one go (up to 100 profiles)
• Offline queue: captures persist if internet drops mid-session
• Multi-source cross-validation pipeline ensures the data sent to your pipeline is recruiter-clean — no duplicate phones, no recruiter contact contamination

━━━━━━━━━━━━━━━━━━━━
HOW IT WORKS
━━━━━━━━━━━━━━━━━━━━

1. Install + log in once with your VHC Talent OS credentials (popup icon → Sign in)
2. Open any Naukri Resdex / LinkedIn / Foundit profile
3. The extension auto-captures the profile or shows a floating "Capture" button
4. Captured candidates appear instantly in your Talent OS Candidate Bank, parsed and ready to shortlist

━━━━━━━━━━━━━━━━━━━━
WHO IT'S FOR
━━━━━━━━━━━━━━━━━━━━

This is a private extension for Ventures HRD recruiters and authorized partner teams. You need an active VHC Talent OS account at https://ventureshrd.com to log in. Without an account, the extension cannot send data anywhere.

━━━━━━━━━━━━━━━━━━━━
PRIVACY
━━━━━━━━━━━━━━━━━━━━

The extension only activates on Naukri, LinkedIn, Foundit, and Monster recruiter pages. It captures publicly-visible candidate data shown in the recruiter's own logged-in session and sends it to api.ventureshrd.com (the recruiter's own VHC Talent OS account). No data is sold, shared, or stored outside your VHC account.

For full privacy policy, see: https://ventureshrd.com/privacy

━━━━━━━━━━━━━━━━━━━━
SUPPORT
━━━━━━━━━━━━━━━━━━━━

Questions? Contact siddharth@vhc.in or your VHC account manager.
```

**Category:** *Workflow & Planning*
**Language:** *English (United States)*

---

### Store Listing → Graphic assets

**Icon 128×128** — already in the ZIP under `icons/icon128.png` (auto-detected)

**Screenshots** — upload **3 to 5** (1280×800 PNG)
- Capture these from your live Naukri Resdex with the extension active:
  1. Floating "VHC Capture" badge on a Resdex profile + green progress toast
  2. Captured candidate card showing in `https://ventureshrd.com/recruiter/candidate-bank` with all 20+ fields filled
  3. The popup window with Sign-In / job binding view
  4. (Optional) Bulk capture button on Naukri search-results page
  5. (Optional) Admin → Extension Versions dashboard with telemetry

**Promo tile (small) 440×280** — optional, skip if no time

---

### Privacy practices (REQUIRED — Web Store reviewers always check this)

**Single purpose description:**
```
This extension lets authorized Ventures HRD recruiters capture candidate profiles they are already viewing on Naukri Resdex, LinkedIn, and Foundit, and send them to their own logged-in VHC Talent OS account at api.ventureshrd.com for downstream recruiting workflow.
```

**Permission justifications** — copy these word-for-word:

| Permission | Justification |
|---|---|
| `storage` | Stores the recruiter's auth token + active job binding so the extension knows where to send captured profiles |
| `tabs` | Detects when the user navigates to a candidate profile page so the capture UI can be injected at the right moment |
| `notifications` | Shows a desktop toast confirming a candidate was successfully captured |
| `alarms` | Periodic background flush of the offline-queue when a capture happened during connection loss |
| Host: `naukri.com / linkedin.com / foundit.in / foundit.sg / foundit.my / monster.com` | Required to inject the capture button on candidate profile pages on each supported job portal |
| Host: `vhc.in / ventureshrd.com` | The extension's own backend — sends captured profiles + auth |

**Remote code:** `No, I am not using remote code` (we ship all logic in the bundle — no eval, no remote scripts).

**Data usage** (check every applicable):
- ☑ Personally identifiable information — *yes (recruiter's email, captured candidate names/emails/phones)*
- ☑ Authentication information — *yes (recruiter's JWT token in chrome.storage)*
- ☐ Financial info — no
- ☐ Health info — no
- ☐ Personal communications — no
- ☐ Location — no
- ☐ Web history — no
- ☐ User activity — no
- ☐ Website content — no (we only read profile data the recruiter is already viewing)

**3 disclosure attestations** — check ALL THREE:
- ☑ I do NOT sell or transfer user data to third parties outside of approved use cases
- ☑ I do NOT use or transfer user data for purposes unrelated to my single purpose
- ☑ I do NOT use or transfer user data to determine creditworthiness or for lending purposes

**Privacy policy URL:**
```
https://ventureshrd.com/privacy-policy
```
*(NOTE: this page already exists on the live site — verify before submitting.)*

---

### Distribution → Visibility & regions

- **Visibility: Unlisted** ← important, otherwise your extension shows up in public search
- **Regions: All regions** (or restrict to India only if you want)

---

## Step 3 — Verify your privacy policy is live

The Web Store reviewer WILL hit `https://ventureshrd.com/privacy-policy`. The page already exists on the live site — open it once in incognito to confirm it loads. If the existing copy is generic, optionally replace its content with `/app/PRIVACY_POLICY.md` from this commit (which is tailored for the Extension's data practices).

---

## Step 4 — Submit for review

Click **"Submit for review"** in the dev console. Google says 1-3 business days; in practice for unlisted extensions it's usually under 24 hours.

You'll get an email at siddharth@vhc.in when:
- Approved → extension goes live at the share URL
- Rejected → reasons listed; common rejections + fixes:
  - *"Use of <all_urls>"* → already removed in our zip ✅
  - *"Privacy policy unreachable"* → fix Step 3
  - *"Permission justification too vague"* → use the table above
  - *"Single purpose unclear"* → use the description above

---

## Step 5 — After approval

Google gives you a permanent install URL like `https://chromewebstore.google.com/detail/<your-extension-id>`.
Send that URL to your recruiters. Future updates auto-install silently within 5 hours of you uploading a new ZIP — no more `.reg` files or "Load Unpacked".

To push an update:
1. Bump version in `browser-extension/manifest.json` (e.g. 5.3.1 → 5.3.2)
2. Run `python3 backend/scripts/build_webstore_zip.py` on your machine or in CI
3. Upload the new zip in the dev console → **Save draft** → **Submit for review**

---

## Files created in this commit

| File | Purpose |
|---|---|
| `backend/scripts/build_webstore_zip.py` | Builds a Web Store-compliant zip (strips `<all_urls>` + `update_url`) |
| `WEBSTORE_SUBMISSION.md` (this file) | Step-by-step submission instructions |
| `PRIVACY_POLICY.md` | Boilerplate privacy text — paste at `https://ventureshrd.com/privacy` |
