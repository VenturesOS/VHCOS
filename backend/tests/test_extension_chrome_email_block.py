"""
Regression test for the Sachin/ajit@searchpartner.in bug (extension v6.0.2).

Scenario: a VHC user (Sachin, with VHC email like sachin@vhc.in) is logged
into Naukri under a different shared account (ajit@searchpartner.in).
On first capture the Naukri-header login email leaked into the candidate
email field via the BEFORE-snapshot fallback inside mergeContacts().

Fix (v6.0.2) added a `snapshotChromeEmails()` helper + per-capture
"chrome blocklist" that mergeContacts() honours. We also restricted the
BEFORE-snapshot fallback so it only trusts emails that also appear inside
the candidate-profile root.

This test guards the SHAPE of the fix so a future refactor cannot remove
the blocklist plumbing silently.
"""
import re
from pathlib import Path

EXT = Path(__file__).resolve().parents[2] / "browser-extension"
CONTENT_JS = (EXT / "content.js").read_text()
MANIFEST = (EXT / "manifest.json").read_text()


def test_version_bumped_to_6_0_2():
    assert '"version": "6.0.2"' in MANIFEST, "manifest.json must be bumped to 6.0.2"
    assert "const VERSION = '6.0.2'" in CONTENT_JS, "content.js VERSION constant must be 6.0.2"


def test_snapshot_chrome_emails_defined():
    """snapshotChromeEmails() must exist — it scans Naukri header for the
    session-login email so it can be excluded from candidate extraction."""
    assert "function snapshotChromeEmails(" in CONTENT_JS


def test_snapshot_chrome_emails_invoked_in_capture():
    """performCapture must populate recruiterCreds.chromeEmails BEFORE
    mergeContacts runs so the blocklist is non-empty on first capture."""
    assert "recruiterCreds.chromeEmails = snapshotChromeEmails()" in CONTENT_JS


def test_merge_contacts_consumes_chrome_blocklist():
    """mergeContacts() must honour recruiterCreds.chromeEmails so the
    Naukri-login email cannot become the candidate's email."""
    # The fix introduces a chromeBlock Set inside mergeContacts.
    block_decl = re.search(
        r"const\s+chromeBlock\s*=\s*recruiterCreds\.chromeEmails\s+instanceof\s+Set",
        CONTENT_JS,
    )
    assert block_decl, "mergeContacts must declare chromeBlock from recruiterCreds.chromeEmails"
    assert "chromeBlock.has(lower)" in CONTENT_JS, (
        "isRecruiterEmail must consult chromeBlock so chrome-only emails are blocked"
    )


def test_before_snapshot_fallback_restricted_to_candidate_root():
    """The BEFORE-snapshot fallback must verify the email appears inside the
    candidate profile root — emails that exist on the page but NOT in the
    candidate root are page chrome (Naukri header) and must be rejected."""
    # Look for the candidate-root check pattern inside the BEFORE-snapshot loop.
    assert "BEFORE-snapshot email" in CONTENT_JS
    assert "rootTextLower" in CONTENT_JS
    assert "treating as page chrome" in CONTENT_JS


def test_changelog_mentions_session_login_leak_fix():
    """Backend /api/extension/version must surface the v6.0.2 fix in the
    changelog so deployed extensions update with a meaningful note."""
    ext_route = (
        Path(__file__).resolve().parents[1] / "routes" / "extension.py"
    ).read_text()
    assert "v6.0.2" in ext_route
    assert "Session-login email leak fix" in ext_route
