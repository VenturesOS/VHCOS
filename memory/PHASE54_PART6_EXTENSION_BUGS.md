# Phase 54 — Part 6: Recapture Wipes Existing Contact Info (P0 fix)
**Date:** 2026-05-07
**Severity:** P0 (data destruction)
**Status:** ✅ Backend fix shipped — Bug B (URL pattern) DEFERRED per user decision

## Bug A — Recapture wipes existing contact info (P0, data loss) — FIXED
### Symptom (user report)
> "When my team captures a candidate from Naukri sometimes the contact
> is hidden behind 'View Contact'. I correct it by reopening the
> candidate, clicking 'View Contact', and recapturing. Later someone
> recaptures the same candidate WITHOUT clicking 'View Contact' — and
> the previously-saved phone number is wiped from the bank."

### Root Cause
`services/extension_service.py::build_complete_update()` filtered with
`if value is not None` but the extension sends `phone=""` (empty
string, not None) when the contact button isn't pressed. Empty string
is NOT None, so the guard let it through and MongoDB ran
`$set: {phone: ""}` — destroying the previously-saved value. Same
class of bug existed on the `personal` and `career_keys` loops.

### Fix
New helper `_should_overwrite(value)`:
```python
def _should_overwrite(value) -> bool:
    if value is None: return False
    if isinstance(value, str)         and not value.strip(): return False
    if isinstance(value, (list, dict)) and len(value) == 0:  return False
    return True   # KEEPS False booleans + 0 numerics (valid captures)
```
Replaced all three `if value is not None` checks in
`build_complete_update()` with `if _should_overwrite(value)`.

### Tests (10 new, all pass)
`backend/tests/test_extension_preserve_contact.py`
- _should_overwrite primitives (skips None, "", "   ", [], {}; keeps False, 0, "abc")
- Recapture with hidden contact → `phone` NOT in update dict ✅
- Recapture with real contact → `phone="9876543210"` in update ✅
- Personal block: empty strings filtered, real values retained
- Career block: empty `notice_period` skipped, `current_salary=0` KEPT
- `has_resume=False` is a valid capture, kept

```
$ pytest tests/test_extension_preserve_contact.py -v
============== 10 passed in 0.83s ==============
```

## Bug B — Auto-capture silently skips Naukri /candidate/preview/* URLs (P1) — DEFERRED
User reported on 2026-05-07: "I rechecked with the same profile from
the example and it captured this time, so this isn't actually a
problem." The fix (URL regex + diagnostic console.log + version bump
to 5.4.2) was prepared in the workspace but **reverted** before
shipping. Re-investigate when the user can reproduce reliably.

**Reverted files (back to v5.4.1):**
- `browser-extension/content.js` — `isProfilePage()` Naukri block
- `browser-extension/content.js` + `background.js` — VERSION
- `browser-extension/manifest.json` — version

## Files Changed (this commit)
- `backend/services/extension_service.py`
  - new `_should_overwrite()` helper
  - 3 update loops use the new guard
- `backend/tests/test_extension_preserve_contact.py` (new, 10 tests)

## Deploy
### Backend (EC2)
```bash
cd /home/ubuntu/vhc-platform && \
  git pull --rebase origin main && \
  sudo systemctl restart gunicorn && \
  cd backend && python -m pytest tests/test_extension_preserve_contact.py -v
```
Expected: `10 passed in <1s`. No Chrome extension reload needed.
