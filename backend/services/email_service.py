"""
Email Service for VHC Talent OS
Uses Resend API for transactional email delivery
"""
import os
import asyncio
import logging
import resend
from typing import Optional, Dict, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Initialize Resend
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'notifications@vhctalent.com')

if RESEND_API_KEY and RESEND_API_KEY != 're_placeholder_key':
    resend.api_key = RESEND_API_KEY


async def send_email(
    recipient_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
    attachments: Optional[List[Dict]] = None,
) -> Dict:
    """
    Send email asynchronously using Resend API.
    Non-blocking - runs sync SDK in thread pool.

    attachments: list of dicts with keys 'filename' (str) and 'content' (bytes).
                 Content will be base64-encoded before sending to Resend.
    """
    if not RESEND_API_KEY or RESEND_API_KEY == 're_placeholder_key':
        logger.warning(f"[EMAIL] Resend API key not configured. Would send to: {recipient_email}")
        return {
            "status": "skipped",
            "message": "Email service not configured",
            "recipient": recipient_email,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    try:
        params = {
            "from": SENDER_EMAIL,
            "to": [recipient_email],
            "subject": subject,
            "html": html_content
        }

        if text_content:
            params["text"] = text_content

        if attachments:
            import base64
            params["attachments"] = [
                {
                    "filename": a["filename"],
                    "content": base64.b64encode(a["content"]).decode("utf-8"),
                }
                for a in attachments
            ]

        # Run sync SDK in thread to keep FastAPI non-blocking
        email_response = await asyncio.to_thread(resend.Emails.send, params)

        logger.info(f"[EMAIL] Sent to {recipient_email}: {subject}" + (f" (with {len(attachments)} attachments)" if attachments else ""))
        return {
            "status": "sent",
            "message": f"Email sent to {recipient_email}",
            "email_id": email_response.get("id"),
            "recipient": recipient_email,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"[EMAIL] Failed to send to {recipient_email}: {str(e)}")
        return {
            "status": "failed",
            "message": str(e),
            "recipient": recipient_email,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


async def send_batch_emails(emails: List[Dict]) -> List[Dict]:
    """
    Send multiple emails concurrently.
    Each email dict should have: recipient_email, subject, html_content
    """
    tasks = [
        send_email(
            recipient_email=email["recipient_email"],
            subject=email["subject"],
            html_content=email["html_content"],
            text_content=email.get("text_content")
        )
        for email in emails
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append({
                "status": "failed",
                "message": str(result),
                "recipient": emails[i]["recipient_email"]
            })
        else:
            processed_results.append(result)
    
    return processed_results
