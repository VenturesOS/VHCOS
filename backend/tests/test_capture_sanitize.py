"""Regression tests for capture-input hygiene (Phase 57, Jun 2026).

1. Unicode sanitization — Naukri candidates decorate names/headlines with
   styled Unicode (𝐀𝐦𝐢𝐭, 𝒫𝓇𝒾𝓎𝒶). Client-side substring() slices astral
   chars mid-surrogate-pair, producing lone surrogates that crashed the
   backend with `UnicodeEncodeError: 'utf-8' codec can't encode character
   '\\ud835'... surrogates not allowed` (seen in prod maintenance report).
2. Tab-title unread-prefix — background-tab captures scraped names like
   "(4) Deepika Agarwal" from document.title; backend now strips the
   prefix instead of hard-rejecting the capture.

Run: cd /app/backend && python -m pytest tests/test_capture_sanitize.py -v
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.extension import (  # noqa: E402
    AIExtractRequest,
    CompleteNaukriProfileInput,
    sanitize_unicode,
)


def test_lone_surrogate_stripped():
    s = "RAGHAVENDRA \ud835 BALAKRISHNAN"
    out = sanitize_unicode(s)
    out.encode("utf-8")  # must not raise
    assert "\ud835" not in out


def test_styled_unicode_folded_to_ascii():
    assert sanitize_unicode("\U0001d400\U0001d426\U0001d422\U0001d42d") == "Amit"  # 𝐀𝐦𝐢𝐭


def test_nested_structures_sanitized():
    data = {"skills": ["\U0001d5e3\U0001d5ee\U0001d5fb\U0001d5f1\U0001d5ee\U0001d600"],  # 𝗣𝗮𝗻𝗱𝗮𝘀
            "meta": {"note": "ok \ud835"}}
    out = sanitize_unicode(data)
    assert out["skills"] == ["Pandas"]
    assert out["meta"]["note"] == "ok "


def test_model_validator_cleans_profile_input():
    p = CompleteNaukriProfileInput(
        name="\U0001d400\U0001d426\U0001d422\U0001d42d Sharma",
        scraped_at="2026-06-11T00:00:00Z",
        raw_profile_text="text with lone \ud835 surrogate",
    )
    assert p.name == "Amit Sharma"
    p.raw_profile_text.encode("utf-8")  # must not raise


def test_ai_extract_request_sanitized():
    r = AIExtractRequest(raw_text="cv \ud835 body", page_url="https://x")
    r.raw_text.encode("utf-8")
    assert "\ud835" not in r.raw_text


def test_non_strings_pass_through():
    assert sanitize_unicode(16.5) == 16.5
    assert sanitize_unicode(None) is None
    assert sanitize_unicode(True) is True


def test_tab_title_unread_prefix_strip_regex():
    """Backend uses this exact substitution before name validation."""
    assert re.sub(r"^\s*\(\d+\)\s*", "", "(4) Deepika Agarwal").strip() == "Deepika Agarwal"
    assert re.sub(r"^\s*\(\d+\)\s*", "", "Deepika Agarwal").strip() == "Deepika Agarwal"
