# Phase 54.9 — Naukri location capture wrong field bug
**Date:** 2026-05-09
**Severity:** P0 (data quality / wrong field captured)
**Status:** ✅ Fixed — pending Chrome extension reload

## Symptom (user report)
> "I just checked a candidate whose location in the top card is **Patna**
> but the process captured it as **Kolkata** from preferred locations.
> Need a quality check on this and ensure data is captured correctly."

DB-side display showed `s Kolkata` (note the leaked "s " prefix).

## Root Cause
`browser-extension/content.js` had a greedy CSS selector at line 2582:
```js
const locationSelectors = [
  '[class*="location"]', '[class*="Location"]',  // ← matches FIRST
  '[class*="currentCity"]', '[class*="current-city"]',
  ...
];
for (const sel of locationSelectors) {
  const el = document.querySelector(sel);   // ← stops on first match
  if (el) { /* capture */ break; }
}
```
Naukri's modern profile DOM has **`<div class="prefLocations">`**
appearing in the document **before** the current-city element. The
greedy `[class*="location"]` selector matches `prefLocations` first,
so `querySelector()` returns the preferred-locations div whose text
content is `"Pref. locations Kolkata, Ahmedabad, Noida, Mumbai, ..."`.
After the prefix-stripping regex partially matched "Pref. **location**",
the leftover "s Kolkata" got truncated by the 80-char cap and stored.

The same greedy selector existed in `extractCleanProfileText()`
(line 1702) which feeds the LLM, so the AI also saw "Location: Kolkata"
in the prompt.

## Fix
1. **Reorder selectors** — most-specific first:
   ```js
   const locationSelectors = [
     '[class*="currentCity"]', '[class*="current-city"]',
     '[class*="currentLocation"]', '[class*="current-location"]',
     'i.naukri-icon-location', 'i.naukri-icon-pin',
     // Generic LAST + :not() exclusions for pref containers
     '[class*="location"]:not([class*="pref" i] *):not([class*="Pref"] *)...',
   ];
   ```

2. **Defensive ancestor check** — even if `:not()` misses something,
   walk up: `if (el.closest('[class*="pref" i]')) continue;`

3. **Reject list-of-cities** (post-extraction guard):
   ```js
   const commaCount      = (text.match(/,/g) || []).length;
   const capitalisedWords = (text.match(/\b[A-Z][a-z]+/g) || []).length;
   if (commaCount >= 1 && capitalisedWords >= 2) continue;  // pref list
   ```

4. **Stronger prefix strip** — added `pref(?:erred|\.)?\s*locations?`
   so any leakage is fully cleaned:
   ```js
   text = text.replace(
     /^(?:pref(?:erred|\.)?\s*locations?|location|city|current\s*location)\s*[:\-]?\s*/i,
     ''
   ).trim();
   ```

Same fix mirrored in `extractCleanProfileText()` so the LLM-fed text
is also clean.

## Test (logic simulation)
```
✅ "Kolkata, Ahmedabad, Noida, Mumbai, Bengaluru" → rejected (pref list)
✅ "Kolkata, Ahmedabad"                            → rejected (pref list)
✅ "Patna"                                         → kept (single city)
✅ "Bangalore"                                     → kept
✅ "New Delhi"                                     → kept (no comma)
✅ "Mumbai"                                        → kept
```

## Files Changed
- `browser-extension/content.js` — 2 location blocks rewritten + VERSION
- `browser-extension/background.js` — VERSION
- `browser-extension/manifest.json` — version

Extension bumped **v5.4.1 → v5.4.2**.

## Deploy
Backend unchanged — extension-only fix. Each team member must:
1. Save-to-GitHub (you do)
2. Pull the new extension folder to their laptop
3. `chrome://extensions` → toggle Developer Mode ON → click **Update**
4. Verify popup shows v5.4.2
5. Open a Naukri profile whose current city ≠ first preferred city,
   capture, verify the bank shows the correct current city

## Backlog (data hygiene)
A subset of already-captured candidates have wrong locations sourced
from this bug. Two options:
- **Manual recapture** of suspect profiles (cheapest, slowest)
- **One-off cleanup script** (`scripts/fix_pref_loc_leaked_into_current.py`)
  that finds candidates whose `current_location` ∈ their
  `preferred_locations` AND looks like a pref-list leak (commas,
  multi-cities), and clears the field for next recapture
- Decide together when ready
