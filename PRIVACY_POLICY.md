# Privacy Policy — VHC Talent OS Recruiter Capture Extension

**Effective date:** 24 April 2026
**Last updated:** 24 April 2026

This Privacy Policy describes how the **VHC Talent OS — Multi-Platform Capture** Chrome extension ("the Extension") collects, uses, and protects information when used by authorized Ventures HRD recruiters and partner teams.

---

## 1. Who we are

The Extension is published by **Ventures HRD ("Ventures HRD", "we", "us")**.

- Website: https://ventureshrd.com
- Contact: siddharth@vhc.in
- Address: Available on request

---

## 2. Single Purpose

The Extension exists for one purpose only: to allow authorized recruiters who already use Ventures HRD's Talent Operating System to capture candidate profile information from job portals where they are already logged in (Naukri, LinkedIn, Foundit, Monster) and securely transmit that information to their own VHC Talent OS account at `api.ventureshrd.com`.

The Extension does NOT operate on any website outside of those job portals and the Ventures HRD backend.

---

## 3. What data the Extension handles

When the recruiter triggers a capture on a candidate profile, the Extension reads:

**Candidate profile data shown to the recruiter on the job portal**, including (where visible):
- Name
- Email address
- Phone number
- Current and past employer / designation / duration
- Salary (current CTC and expected CTC)
- Notice period
- Location and preferred locations
- Skills and education
- Free-text profile summary
- The candidate's attached CV/resume content

**Recruiter authentication context:**
- The recruiter's VHC Talent OS authentication token (stored in `chrome.storage`)
- The recruiter's email and (optionally) phone number, used solely to **exclude the recruiter's own contact details** from being mis-attributed to a captured candidate

**Technical metadata:**
- Extension version
- Browser user-agent (to detect SPA navigation timing)

The Extension does **not** capture or read:
- Browsing history outside of the supported job portals
- Form data outside of candidate profile pages
- Any content on websites other than those listed in `host_permissions`
- Keystrokes
- Mouse movement
- Screen contents

---

## 4. How data is used

Captured candidate data is transmitted **only** to the recruiter's own VHC Talent OS backend at `https://api.ventureshrd.com` over HTTPS. There it is stored in the recruiter's organization's private candidate database for the sole purpose of recruiting workflow (shortlisting, AI matching, communication).

We do not:
- Sell candidate data to third parties
- Share candidate data with parties outside Ventures HRD's contracted clients
- Use captured data for advertising, profiling for unrelated purposes, or training public models
- Use the data for credit-scoring or lending decisions

---

## 5. Data security

- All data is transmitted over TLS 1.2+
- The recruiter's auth token is stored in Chrome's encrypted `chrome.storage.sync` and rotates per login
- VHC Talent OS backend access is gated by JWT auth + role-based access control
- The recruiter alone controls who in their organization can view the captured candidate

---

## 6. Data retention

Candidate profiles captured through the Extension are retained in the recruiter's VHC Talent OS database according to the data-retention policy of the recruiter's organization (typically active for the lifetime of the contract; deleted on request).

The Extension itself stores **only** the recruiter's auth token locally; this is cleared on logout or extension uninstall.

---

## 7. Your rights

If you are a candidate whose profile was captured into a Ventures HRD client database and you want it removed, contact `privacy@ventureshrd.com` with proof of identity. We will remove your record from the relevant client account within 30 days.

If you are a recruiter using the Extension and want to revoke its access:
1. Sign out from the Extension popup, or
2. Remove the Extension from `chrome://extensions`

---

## 8. Children's data

The Extension is for professional B2B recruiting only and is not directed at users under 18. We do not knowingly process children's data.

---

## 9. Changes to this policy

We will update this page if our data practices change and notify the publisher email on file (`siddharth@vhc.in`).

---

## 10. Contact

Questions, requests, or complaints:

📧 **siddharth@vhc.in**
🌐 https://ventureshrd.com
