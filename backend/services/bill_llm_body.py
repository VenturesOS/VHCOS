"""LLM-generated mail body for bill / reminder emails — Phase 55.6.

Small wrapper around the approved NVIDIA → Nemotron Super 120B → Emergent chain. We don't want
the full guided-JSON path here — just a plain text completion.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional


logger = logging.getLogger(__name__)


# ── Prompt templates ─────────────────────────────────────────────────
_SYSTEM = (
    "You are a polite, concise B2B billing assistant for Venture HRD Centre, "
    "a placement consultancy in India. Output ONLY the email body in plain "
    "text — no subject, no greetings outside the body, no markdown, no "
    "code-fences. Use 4-7 short paragraphs. Keep it professional and warm. "
    "Always sign off as 'Accounts Team, Venture HRD Centre'."
)

_SEND_TEMPLATE = """Compose a polite invoice covering-email body for the client below.

Client: {client_name}
Invoice no: {bill_number}
Invoice date: {bill_date}
Due date: {due_date}
Amount: ₹{amount}
Candidates billed:
{candidates_block}

Mention that the tax invoice PDF is attached. Politely request payment by the
due date. End with a thank-you and the Accounts Team sign-off.
"""

_REMINDER_TEMPLATE = """Compose a polite payment-reminder email body. This is reminder #{n} for an
unpaid invoice. Recipients are internal cc parties (not the client). Tone:
firm-but-respectful, suitable for sharing with the client if forwarded.

Client: {client_name}
Invoice no: {bill_number}
Invoice date: {bill_date}
Due date: {due_date}
Days since sent: {days_since}
Amount: ₹{amount}

Reference that this is reminder #{n}. State the amount and due date clearly.
Suggest a follow-up call with the client contact. End with the Accounts
Team sign-off.
"""


def _fmt_inr(n: float) -> str:
    try:
        return f"{n:,.2f}"
    except Exception:
        return str(n)


async def _generate_body(prompt: str, max_tokens: int = 600, temperature: float = 0.35) -> Optional[str]:
    from services.llm_service import chat_completion
    try:
        return await chat_completion(_SYSTEM, prompt, temperature=temperature,
                                     max_tokens=max_tokens, timeout=90)
    except Exception as e:  # noqa: BLE001
        logger.warning("[Bill LLM] Providers unavailable: %s — using fallback template", e)
        return None


def _fallback_send_body(ctx: Dict) -> str:
    return (
        f"Dear Sir/Madam,\n\n"
        f"Please find attached the tax invoice {ctx['bill_number']} dated "
        f"{ctx['bill_date']} for placement consultancy services rendered.\n\n"
        f"Amount payable: ₹{ctx['amount']}. Due date: {ctx['due_date']}.\n\n"
        f"Kindly arrange the payment by the due date. Should you have any "
        f"queries on the bill, please reply to this mail or reach out to our "
        f"accounts team.\n\n"
        f"Thank you for your continued partnership.\n\n"
        f"Regards,\nAccounts Team\nVenture HRD Centre"
    )


def _fallback_reminder_body(ctx: Dict) -> str:
    return (
        f"Hello team,\n\n"
        f"Gentle reminder #{ctx['n']}: invoice {ctx['bill_number']} dated "
        f"{ctx['bill_date']} for ₹{ctx['amount']} is currently outstanding "
        f"(due {ctx['due_date']}, sent {ctx['days_since']} days ago).\n\n"
        f"Please follow up with {ctx['client_name']} for status and ETA on "
        f"the payment. Let us know if a call needs to be set up.\n\n"
        f"Regards,\nAccounts Team\nVenture HRD Centre"
    )


async def generate_send_body(bill: Dict) -> str:
    candidates = "; ".join(
        f"{li.get('candidate_name','?')} ({li.get('designation','-')})"
        for li in (bill.get("line_items") or [])
    )
    ctx = {
        "client_name": bill.get("client_legal_name", ""),
        "bill_number": bill.get("bill_number", ""),
        "bill_date": bill.get("bill_date", ""),
        "due_date": bill.get("due_date", "-"),
        "amount": _fmt_inr((bill.get("totals") or {}).get("grand_total", 0)),
        "candidates_block": candidates or "(see attached PDF)",
    }
    prompt = _SEND_TEMPLATE.format(**ctx)
    body = await _generate_body(prompt)
    return body or _fallback_send_body(ctx)


async def generate_reminder_body(bill: Dict, reminder_n: int, days_since: int) -> str:
    ctx = {
        "n": reminder_n,
        "client_name": bill.get("client_legal_name", ""),
        "bill_number": bill.get("bill_number", ""),
        "bill_date": bill.get("bill_date", ""),
        "due_date": bill.get("due_date", "-"),
        "days_since": days_since,
        "amount": _fmt_inr((bill.get("totals") or {}).get("grand_total", 0)),
    }
    prompt = _REMINDER_TEMPLATE.format(**ctx)
    body = await _generate_body(prompt)
    return body or _fallback_reminder_body(ctx)


def plain_to_html(text: str) -> str:
    """Trivial plain→HTML converter for Resend's `html` field."""
    safe = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    paras = [p.strip() for p in safe.split("\n\n") if p.strip()]
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#222;line-height:1.5;max-width:640px">'
        + "".join(f"<p>{p.replace(chr(10), '<br/>')}</p>" for p in paras)
        + "</div>"
    )
