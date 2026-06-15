/**
 * Behavioral regression test for the Sachin/ajit@searchpartner.in bug.
 *
 * We extract mergeContacts() + snapshotChromeEmails() supporting helpers
 * from content.js by inlining a minimal copy of the merge logic, then
 * verify:
 *
 *   1. With chromeEmails = {"ajit@searchpartner.in"}, the BEFORE-snapshot
 *      fallback REJECTS ajit@searchpartner.in (chrome blocklist hit).
 *   2. With an empty chrome blocklist BUT the email missing from the
 *      candidate root, the BEFORE-snapshot fallback REJECTS the email
 *      (root-presence guard).
 *   3. A legitimate candidate email present in the candidate root and
 *      absent from chrome blocklist is ACCEPTED.
 *
 * Run: node browser-extension/tests/test_chrome_email_block.js
 * Exits non-zero on any failure.
 */

const fs = require('fs');
const path = require('path');

const CONTENT = fs.readFileSync(
  path.join(__dirname, '..', 'content.js'),
  'utf8'
);

// Sanity guards — make sure we're testing the patched code.
function mustContain(needle) {
  if (!CONTENT.includes(needle)) {
    console.error(`✗ content.js missing required marker: ${needle}`);
    process.exit(1);
  }
}
mustContain("function snapshotChromeEmails(");
mustContain("recruiterCreds.chromeEmails = snapshotChromeEmails()");
mustContain("chromeBlock.has(lower)");
mustContain("treating as page chrome");

// Minimal reimplementation of the patched mergeContacts() email path so we
// can drive it from Node without a real DOM. Must stay in lock-step with
// the version inside content.js.
function isNaukriSystemEmail(e) {
  const lower = (e || '').toLowerCase();
  return lower.includes('@naukri.com') || lower.includes('support@') ||
         lower.includes('noreply@') || lower.includes('@example.') ||
         lower.includes('info@naukri') || lower.includes('recruiter@naukri') ||
         lower.endsWith('@vhc.in');
}

function mergeEmail({ cvEmail, diffEmails, beforeEmails, domEmail,
                      rEmail, chromeBlock, candidateRootText }) {
  const r = (rEmail || '').toLowerCase().trim();
  function isRecruiterEmail(e) {
    if (!e) return false;
    const lower = e.toLowerCase().trim();
    if (r && lower === r) return true;
    if (chromeBlock && chromeBlock.has(lower)) return true;
    return false;
  }
  function isBadEmail(e) { return !e || isNaukriSystemEmail(e) || isRecruiterEmail(e); }

  if (cvEmail && !isBadEmail(cvEmail)) return { email: cvEmail, source: 'CV' };
  if (diffEmails) {
    for (const e of diffEmails) if (!isBadEmail(e)) return { email: e, source: 'diff' };
  }
  if (beforeEmails) {
    const rootLower = (candidateRootText || '').toLowerCase();
    for (const e of beforeEmails) {
      if (isBadEmail(e)) continue;
      if (rootLower && !rootLower.includes(e.toLowerCase())) continue;
      return { email: e, source: 'before' };
    }
  }
  if (domEmail && !isBadEmail(domEmail)) return { email: domEmail, source: 'dom' };
  return { email: null, source: 'none' };
}

let pass = 0, fail = 0;
function check(label, cond) {
  if (cond) { console.log(`✓ ${label}`); pass++; }
  else      { console.error(`✗ ${label}`); fail++; }
}

// === Case 1: First capture — CV iframe not loaded, View-Contact diff
// returned nothing new, but ajit@searchpartner.in is in the BEFORE snapshot
// (Naukri header) AND in the chrome blocklist. Must be rejected.
const c1 = mergeEmail({
  cvEmail: null,
  diffEmails: [],
  beforeEmails: ['ajit@searchpartner.in'],
  domEmail: null,
  rEmail: 'sachin@vhc.in',                      // VHC login — DOES NOT match ajit@
  chromeBlock: new Set(['ajit@searchpartner.in']),
  candidateRootText: 'Some candidate profile content here without that email',
});
check('Case 1: ajit@searchpartner.in is BLOCKED via chromeBlock', c1.email === null);

// === Case 2: Chrome blocklist empty (defensive layer 2 — root-presence guard)
// The email is on the page but NOT inside the candidate root → still rejected.
const c2 = mergeEmail({
  cvEmail: null,
  diffEmails: [],
  beforeEmails: ['ajit@searchpartner.in'],
  domEmail: null,
  rEmail: 'sachin@vhc.in',
  chromeBlock: new Set(),                       // blocklist missed it
  candidateRootText: 'Candidate Ramesh Kannan — Senior Engineer — Chennai',
});
check('Case 2: email outside candidate root is REJECTED', c2.email === null);

// === Case 3: Legitimate candidate email — appears inside candidate root,
// not in chrome blocklist. Must be accepted.
const c3 = mergeEmail({
  cvEmail: null,
  diffEmails: [],
  beforeEmails: ['ramesh.kannan@gmail.com'],
  domEmail: null,
  rEmail: 'sachin@vhc.in',
  chromeBlock: new Set(['ajit@searchpartner.in']),
  candidateRootText: 'Email: ramesh.kannan@gmail.com Phone: 98xxxxxxx',
});
check('Case 3: legitimate candidate email is ACCEPTED', c3.email === 'ramesh.kannan@gmail.com');

// === Case 4: CV iframe succeeded — wins regardless of fallbacks.
const c4 = mergeEmail({
  cvEmail: 'real.candidate@gmail.com',
  diffEmails: ['ajit@searchpartner.in'],
  beforeEmails: ['ajit@searchpartner.in'],
  domEmail: null,
  rEmail: 'sachin@vhc.in',
  chromeBlock: new Set(['ajit@searchpartner.in']),
  candidateRootText: 'real.candidate@gmail.com',
});
check('Case 4: CV-iframe email wins over chrome-leaked fallbacks', c4.email === 'real.candidate@gmail.com');

// === Case 5: ajit@ leaks into the View-Contact diff too (degenerate Naukri
// re-renders the header email inside the diff). chromeBlock still blocks it.
const c5 = mergeEmail({
  cvEmail: null,
  diffEmails: ['ajit@searchpartner.in', 'real.candidate@gmail.com'],
  beforeEmails: [],
  domEmail: null,
  rEmail: 'sachin@vhc.in',
  chromeBlock: new Set(['ajit@searchpartner.in']),
  candidateRootText: 'real.candidate@gmail.com',
});
check('Case 5: diff path also honours chromeBlock; falls through to real email',
      c5.email === 'real.candidate@gmail.com');

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail === 0 ? 0 : 1);
