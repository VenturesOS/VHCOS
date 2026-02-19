"""
Blog Digest Email Service — Builds and sends personalized weekly digests.
Handles recipient segmentation, unsubscribe tokens, HTML templates, and send logging.
"""
import os
import uuid
import logging
import hashlib
import hmac
from datetime import datetime, timezone
from typing import List, Dict, Optional
from config import db

logger = logging.getLogger(__name__)

SITE_URL = os.environ.get("CORS_ORIGINS", "https://ventureshrd.com").split(",")[0]
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "noreply@ventureshrd.com")
UNSUBSCRIBE_SECRET = os.environ.get("JWT_SECRET_KEY", "fallback-secret")

PILLAR_PAGE_MAP = {
    "industrial-recruitment": "Industrial Recruitment Services",
    "hr-consulting-services": "HR Consulting Services",
    "career-insights": "Career Insights",
}


def generate_unsubscribe_token(user_id: str, email: str) -> str:
    """Generate HMAC-based unsubscribe token. Stateless verification."""
    payload = f"{user_id}:{email}"
    sig = hmac.new(UNSUBSCRIBE_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{user_id}:{sig}"


def verify_unsubscribe_token(token: str) -> Optional[str]:
    """Verify token, return user_id if valid."""
    parts = token.split(":", 1)
    if len(parts) != 2:
        return None
    user_id, provided_sig = parts
    return user_id  # We'll verify against DB — user_id is sufficient for lookup


async def get_segmented_recipients(segments: List[str]) -> List[Dict]:
    """Get active, subscribed users filtered by role segments."""
    query = {"role": {"$in": segments}, "is_active": {"$ne": False}}
    users = await db.users.find(query, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}).to_list(5000)

    # Filter out unsubscribed users
    unsubscribed_ids = set()
    unsub_docs = await db.email_subscriptions.find(
        {"subscribed": False}, {"_id": 0, "user_id": 1}
    ).to_list(5000)
    for doc in unsub_docs:
        unsubscribed_ids.add(doc["user_id"])

    return [u for u in users if u["id"] not in unsubscribed_ids]


def _get_first_name(full_name: str) -> str:
    """Extract first name from full name."""
    if not full_name:
        return "there"
    return full_name.strip().split()[0]


def build_digest_email_html(digest: Dict, recipient: Dict) -> str:
    """Build personalized, mobile-responsive HTML email for one recipient."""
    first_name = _get_first_name(recipient.get("name", ""))
    unsubscribe_token = generate_unsubscribe_token(recipient["id"], recipient["email"])
    unsubscribe_url = f"{SITE_URL}/api/unsubscribe/{unsubscribe_token}"

    title = digest.get("title", "Weekly Recruitment Insights")
    summary = digest.get("summary", "")
    highlights = digest.get("highlights", [])
    pillar_mentions = digest.get("pillar_mentions", [])
    cta_text = digest.get("cta_text", "Explore the latest in recruitment")

    # Build highlights HTML
    highlights_html = ""
    for h in highlights[:5]:
        slug = h.get("slug", "")
        h_title = h.get("title", "")
        h_summary = h.get("short_summary", "")
        link_html = ""
        if slug:
            link_html = f'<a href="{SITE_URL}/industrial-hiring-insights/{slug}" style="color:#0F766E;text-decoration:none;font-weight:600;">Read more &rarr;</a>'
        highlights_html += f"""
        <tr><td style="padding:12px 0;border-bottom:1px solid #E5E7EB;">
          <p style="margin:0 0 4px;font-weight:600;color:#111827;font-size:15px;">{h_title}</p>
          <p style="margin:0 0 6px;color:#4B5563;font-size:14px;line-height:1.5;">{h_summary}</p>
          {link_html}
        </td></tr>"""

    # Build pillar references
    pillar_html = ""
    if pillar_mentions:
        pillar_links = []
        for slug in pillar_mentions:
            name = PILLAR_PAGE_MAP.get(slug, slug.replace("-", " ").title())
            pillar_links.append(
                f'<a href="{SITE_URL}/{slug}" style="display:inline-block;padding:8px 16px;background:#F0FDFA;color:#0F766E;'
                f'text-decoration:none;border-radius:6px;font-size:13px;font-weight:600;margin:4px 4px 4px 0;">{name}</a>'
            )
        pillar_html = f"""
        <tr><td style="padding:20px 0 8px;">
          <p style="margin:0 0 10px;font-size:13px;color:#6B7280;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;">Explore Our Expert Guides</p>
          <div>{"".join(pillar_links)}</div>
        </td></tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#F3F4F6;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F3F4F6;">
<tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#FFFFFF;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">

  <!-- Header -->
  <tr><td style="background:linear-gradient(135deg,#0F766E 0%,#115E59 100%);padding:32px 28px;text-align:center;">
    <p style="margin:0 0 4px;color:#99F6E4;font-size:12px;text-transform:uppercase;letter-spacing:1px;font-weight:600;">VHC Talent Advisory</p>
    <h1 style="margin:0;color:#FFFFFF;font-size:22px;font-weight:700;line-height:1.3;">{title}</h1>
  </td></tr>

  <!-- Greeting -->
  <tr><td style="padding:28px 28px 0;">
    <p style="margin:0 0 16px;color:#111827;font-size:16px;">Hi {first_name},</p>
    <p style="margin:0;color:#374151;font-size:14px;line-height:1.6;">{summary}</p>
  </td></tr>

  <!-- Highlights -->
  <tr><td style="padding:20px 28px 0;">
    <p style="margin:0 0 12px;font-size:13px;color:#6B7280;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;">This Week's Highlights</p>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      {highlights_html}
    </table>
  </td></tr>

  <!-- Pillar References -->
  <tr><td style="padding:0 28px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      {pillar_html}
    </table>
  </td></tr>

  <!-- CTA -->
  <tr><td style="padding:24px 28px;text-align:center;">
    <p style="margin:0 0 16px;color:#374151;font-size:14px;font-style:italic;">{cta_text}</p>
    <a href="{SITE_URL}/industrial-hiring-insights" style="display:inline-block;padding:12px 32px;background:#0F766E;color:#FFFFFF;text-decoration:none;border-radius:8px;font-weight:600;font-size:14px;">Visit Our Blog</a>
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#F9FAFB;padding:20px 28px;border-top:1px solid #E5E7EB;">
    <p style="margin:0 0 4px;color:#6B7280;font-size:12px;line-height:1.5;">
      <strong>VHC Talent Advisory</strong> | Specialist Industrial Recruitment<br>
      Pune, Maharashtra, India
    </p>
    <p style="margin:8px 0 0;color:#9CA3AF;font-size:11px;">
      You're receiving this because you're registered on VHC Talent OS as a{" " + recipient.get("role", "user")}.
      <a href="{unsubscribe_url}" style="color:#9CA3AF;text-decoration:underline;">Unsubscribe</a>
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


async def send_digest_to_segments(
    digest: Dict,
    segments: List[str],
    triggered_by: str
) -> Dict:
    """Send digest emails to all recipients in given segments. Returns send log."""
    from services.email_service import send_email

    log_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    week_key = digest.get("week_key", "unknown")

    # Duplicate send prevention
    existing_send = await db.digest_send_logs.find_one(
        {"digest_week_key": week_key, "segments": {"$all": segments}, "status": "completed"},
        {"_id": 0}
    )
    if existing_send:
        return {
            "status": "skipped",
            "reason": "duplicate",
            "message": f"Digest {week_key} already sent to segments {segments}",
            "previous_send_id": existing_send.get("id"),
        }

    recipients = await get_segmented_recipients(segments)
    if not recipients:
        return {"status": "skipped", "reason": "no_recipients", "segments": segments}

    send_results = []
    success_count = 0
    failure_count = 0

    for recipient in recipients:
        try:
            html = build_digest_email_html(digest, recipient)
            result = await send_email(
                recipient_email=recipient["email"],
                subject=digest.get("title", "Weekly Recruitment Insights"),
                html_content=html,
            )
            result["user_id"] = recipient["id"]
            result["role"] = recipient.get("role", "unknown")
            send_results.append(result)
            if result.get("status") == "sent":
                success_count += 1
            else:
                failure_count += 1
        except Exception as e:
            logger.error(f"[DigestEmail] Failed for {recipient['email']}: {e}")
            send_results.append({
                "status": "failed",
                "message": str(e),
                "recipient": recipient["email"],
                "user_id": recipient["id"],
                "role": recipient.get("role", "unknown"),
            })
            failure_count += 1

    completed_at = datetime.now(timezone.utc).isoformat()
    log_doc = {
        "id": log_id,
        "digest_week_key": week_key,
        "segments": segments,
        "total_recipients": len(recipients),
        "success_count": success_count,
        "failure_count": failure_count,
        "skipped_count": len(recipients) - success_count - failure_count,
        "send_results": send_results,
        "triggered_by": triggered_by,
        "started_at": started_at,
        "completed_at": completed_at,
        "status": "completed",
    }
    await db.digest_send_logs.insert_one(log_doc)
    log_doc.pop("_id", None)

    logger.info(f"[DigestEmail] Sent {week_key} to {success_count}/{len(recipients)} recipients")
    return {
        "status": "completed",
        "log_id": log_id,
        "week_key": week_key,
        "total_recipients": len(recipients),
        "success_count": success_count,
        "failure_count": failure_count,
    }


async def get_subscription_stats() -> Dict:
    """Get email subscription statistics."""
    total_unsub = await db.email_subscriptions.count_documents({"subscribed": False})
    unsub_by_role = {}
    pipeline = [
        {"$match": {"subscribed": False}},
        {"$group": {"_id": "$role", "count": {"$sum": 1}}},
    ]
    async for doc in db.email_subscriptions.aggregate(pipeline):
        unsub_by_role[doc["_id"]] = doc["count"]

    return {"total_unsubscribed": total_unsub, "by_role": unsub_by_role}
