"""
screening_forms.py — tokenized web-form fallback
================================================
For candidates who stall on WhatsApp (or have no WhatsApp): a signed
link opens a minimal mobile-first HTML form of the *remaining*
questions; submitting it feeds the same answer store and completes the
session through the normal engine path.

Token = HMAC-SHA256(session_id, JWT_SECRET_KEY)[:24] — no DB lookup
needed to verify, no auth cookie required, single-purpose.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import os
from typing import Any, Dict, List


def _secret() -> bytes:
    return (os.environ.get("JWT_SECRET_KEY") or "asha-dev-secret").encode()


def make_token(session_id: str) -> str:
    return hmac.new(_secret(), session_id.encode(), hashlib.sha256).hexdigest()[:24]


def verify_token(session_id: str, token: str) -> bool:
    return hmac.compare_digest(make_token(session_id), token or "")


def form_url(session_id: str) -> str:
    base = os.environ.get("AGENT_FORM_BASE_URL",
                          os.environ.get("PUBLIC_SITE_URL", "https://ventureshrd.com"))
    return f"{base.rstrip('/')}/api/agent/form/{session_id}/{make_token(session_id)}"


def remaining_blocks(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    answers = session.get("answers") or {}
    out = []
    for b in (session.get("blocks") or []):
        if b["kind"] in ("consent", "identity", "doc"):
            continue
        a = answers.get(b["id"])
        if a and a.get("value") is not None:
            continue
        out.append(b)
    return out


def render_form(session: Dict[str, Any]) -> str:
    """Self-contained mobile HTML — no build step, VHC navy/gold."""
    blocks = remaining_blocks(session)
    title = html.escape(session.get("mandate_title") or "Screening")
    name = html.escape((session.get("candidate_name") or "").split(" ")[0] or "")
    fields = []
    for b in blocks:
        q = html.escape(b["en"].replace("{name}", name))
        fields.append(
            f'<label>{q}<input name="{html.escape(b["id"])}" required '
            f'placeholder="Type your answer"></label>')
    body = "\n".join(fields) or "<p>All questions are already answered — thank you!</p>"
    btn = '<button type="submit">Submit answers</button>' if blocks else ""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>{title} — Ventures HRD</title><style>
body{{font-family:system-ui,sans-serif;margin:0;background:#f4f6f9;color:#0F2A4A}}
.card{{max-width:520px;margin:24px auto;background:#fff;border-radius:14px;
box-shadow:0 4px 20px rgba(15,42,74,.08);padding:24px}}
h1{{font-size:1.15rem;margin:0 0 4px}}p.sub{{margin:0 0 18px;color:#54677e;font-size:.9rem}}
label{{display:block;font-size:.9rem;font-weight:600;margin:14px 0 4px}}
input{{width:100%;box-sizing:border-box;padding:11px;border:1px solid #cfd8e3;
border-radius:9px;font-size:1rem;font-weight:400;margin-top:6px}}
button{{margin-top:20px;width:100%;padding:13px;border:0;border-radius:9px;
background:#0F2A4A;color:#fff;font-size:1rem;font-weight:600}}
.gold{{color:#C9A54A;font-weight:700}}</style></head><body><div class="card">
<h1><span class="gold">Ventures HRD</span> — {title}</h1>
<p class="sub">Hi {name or "there"}! A few quick questions to complete your screening.</p>
<form method="post">{body}{btn}</form></div></body></html>"""


THANKYOU_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{font-family:system-ui,sans-serif;background:#f4f6f9;color:#0F2A4A;
display:grid;place-items:center;height:100vh;margin:0}
.card{background:#fff;padding:32px 40px;border-radius:14px;text-align:center;
box-shadow:0 4px 20px rgba(15,42,74,.08)}</style></head><body>
<div class="card"><h2>Thank you! 🙏</h2>
<p>Your answers are in — our team will be in touch.</p></div></body></html>"""
