import pathlib
import re

EXT = pathlib.Path("/app/extension")
p = EXT / "background.js"
s = p.read_text()

for b in (
    """  if (request.action === 'setActiveJob') {
    chrome.storage.local.set({ vhc_active_job: request.data }, () => {
      sendResponse({ success: true });
      notifyPopup({ action: 'activeJobUpdated', job: request.data });
    });
    return true;
  }

  if (request.action === 'clearActiveJob') {
    chrome.storage.local.remove(['vhc_active_job'], () => {
      sendResponse({ success: true });
      notifyPopup({ action: 'activeJobUpdated', job: null });
    });
    return true;
  }

  if (request.action === 'getActiveJob') {
    chrome.storage.local.get(['vhc_active_job'], (r) => {
      sendResponse({ job: r.vhc_active_job || null });
    });
    return true;
  }

""",
    """    // ── Step 6: Job shortlist (if recruiter has an active job open) ──
    if (candidateId && item.active_job_id && captureResult.action !== 'exists') {
      shortlistCandidate(candidateId, item.active_job_id, auth).catch(err => {
        console.warn(`[VHC BG v${VERSION}] Shortlist failed for ${finalName}:`, err.message);
      });
    }

""",
):
    assert b in s, b[:60]
    s = s.replace(b, "")

lines = s.splitlines(keepends=True)


def cut(header: str, stop: str):
    """Drop from the banner above `header` up to the line before `stop`."""
    i = next(n for n, line in enumerate(lines) if line.strip() == header)
    i -= 1  # the ═ banner line above
    j = next(n for n, line in enumerate(lines[i:], i) if line.startswith(stop))
    print(f"  cut {i + 1}-{j}: {header}")
    del lines[i:j]


cut("// JOB BINDING — detect active job from VHC dashboard tab", "// ─── Message Router")
cut("// JOB SHORTLIST", "/**\n * Pick up to")
s = "".join(lines)

s = s.replace(
    """chrome.runtime.onStartup.addListener(() => {
  console.log(`[VHC BG v${VERSION}] Startup — ensuring alarms`);""",
    """chrome.runtime.onStartup.addListener(() => {
  console.log(`[VHC BG v${VERSION}] Startup — ensuring alarms`);
  // v7.1: the auto-shortlist job binding is gone. Drop whatever an older
  // build left behind, or the popup keeps showing a stale "Active job".
  chrome.storage.local.remove(['vhc_active_job']);""",
)
p.write_text(s)
print("background.js cleaned")

c = EXT / "content.js"
t = c.read_text()
t, n = re.subn(r"  async function getActiveJob\(\) \{.*?\n  \}\n\n", "", t, flags=re.S)
assert n == 1, n
c.write_text(t)
print("content.js cleaned")
