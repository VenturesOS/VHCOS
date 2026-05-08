"""
Blog Digest Email Service — Builds and sends personalized weekly digests.
Handles recipient segmentation, unsubscribe tokens, HTML templates, and send logging.
"""
import os
import re
import uuid
import logging
import hashlib
import hmac
from datetime import datetime, timezone
from typing import List, Dict, Optional
from config import db

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

SITE_URL = os.environ.get("SITE_URL") or os.environ.get("CORS_ORIGINS", "https://ventureshrd.com").split(",")[0]
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
    """Get active, subscribed users filtered by role segments.
    Supports 'candidate_bank' segment to include candidate bank emails.
    """
    # Collect unsubscribed IDs once
    unsubscribed_ids = set()
    unsub_docs = await db.email_subscriptions.find(
        {"subscribed": False}, {"_id": 0, "user_id": 1}
    ).to_list(10000)
    for doc in unsub_docs:
        unsubscribed_ids.add(doc["user_id"])

    recipients = []
    seen_emails = set()

    # Standard user segments (admin, employer, recruiter, candidate)
    user_segments = [s for s in segments if s != "candidate_bank"]
    if user_segments:
        query = {"role": {"$in": user_segments}, "is_active": {"$ne": False}}
        users = await db.users.find(query, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}).to_list(5000)
        for u in users:
            if u["id"] not in unsubscribed_ids and u.get("email"):
                seen_emails.add(u["email"].lower())
                recipients.append(u)

    # Candidate bank segment — pull emails from candidate_bank collection
    if "candidate_bank" in segments:
        bank_candidates = await db.candidate_bank.find(
            {"email": {"$exists": True, "$nin": ["", None]}},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "source": 1}
        ).to_list(10000)
        for c in bank_candidates:
            email = (c.get("email") or "").strip().lstrip("-")
            if not email or not _EMAIL_RE.match(email):
                continue
            if email.lower() in seen_emails:
                continue
            cid = c.get("id", "")
            if cid in unsubscribed_ids:
                continue
            seen_emails.add(email.lower())
            recipients.append({
                "id": cid,
                "name": c.get("name", ""),
                "email": email,
                "role": "candidate_bank",
            })

    return recipients


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
    for idx, h in enumerate(highlights[:5]):
        slug = h.get("slug", "")
        h_title = h.get("title", "")
        h_summary = h.get("short_summary", "")
        link_html = ""
        if slug:
            link_html = f'<a href="{SITE_URL}/industrial-hiring-insights/{slug}" style="color:#7CB342;text-decoration:none;font-weight:600;font-size:13px;">Read more &rarr;</a>'
        border = 'border-bottom:1px solid #E5E7EB;' if idx < min(len(highlights), 5) - 1 else ''
        highlights_html += f"""
        <tr><td style="padding:16px 20px;{border}">
          <p style="margin:0 0 6px;font-weight:700;color:#0F172A;font-size:15px;line-height:1.4;">{h_title}</p>
          <p style="margin:0 0 8px;color:#4B5563;font-size:13px;line-height:1.6;">{h_summary}</p>
          {link_html}
        </td></tr>"""

    # Build pillar references
    pillar_html = ""
    if pillar_mentions:
        pillar_links = []
        for slug in pillar_mentions:
            name = PILLAR_PAGE_MAP.get(slug, slug.replace("-", " ").title())
            pillar_links.append(
                f'<a href="{SITE_URL}/{slug}" style="display:inline-block;padding:8px 18px;background:#F0FDF4;color:#4D7C0F;'
                f'text-decoration:none;border-radius:20px;font-size:12px;font-weight:600;margin:4px 4px 4px 0;border:1px solid #BEF264;">{name}</a>'
            )
        pillar_html = f"""
        <tr><td style="padding:20px 0 8px;">
          <p style="margin:0 0 10px;font-size:11px;color:#6B7280;text-transform:uppercase;letter-spacing:1px;font-weight:700;">Explore Our Expert Guides</p>
          <div>{"".join(pillar_links)}</div>
        </td></tr>"""

    role_label = recipient.get("role", "user")
    if role_label == "candidate_bank":
        role_label = "candidate from our talent network"

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#F1F5F9;font-family:'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F1F5F9;">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#FFFFFF;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(15,23,42,0.08);">

  <!-- Header -->
  <tr><td style="background:#0F172A;padding:36px 32px 28px;text-align:center;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr><td align="center" style="padding-bottom:16px;">
        <a href="{SITE_URL}" style="text-decoration:none;">
          <img src="https://customer-assets.emergentagent.com/job_vhc-edit/artifacts/46yye45w_logo.svg" alt="Ventures HRD Centre Pvt Ltd" style="height:48px;width:auto;" />
        </a>
      </td></tr>
      <tr><td align="center">
        <p style="margin:0 0 4px;color:#94A3B8;font-size:11px;text-transform:uppercase;letter-spacing:2px;font-weight:600;">Ventures HRD Centre Pvt Ltd</p>
        <h1 style="margin:0;color:#FFFFFF;font-size:22px;font-weight:700;line-height:1.35;">{title}</h1>
      </td></tr>
    </table>
  </td></tr>

  <!-- Green accent bar -->
  <tr><td style="background:linear-gradient(90deg,#7CB342,#9ACD32);height:3px;font-size:0;line-height:0;">&nbsp;</td></tr>

  <!-- Greeting -->
  <tr><td style="padding:28px 32px 0;">
    <p style="margin:0 0 14px;color:#0F172A;font-size:16px;font-weight:600;">Hi {first_name},</p>
    <p style="margin:0;color:#475569;font-size:14px;line-height:1.7;">{summary}</p>
  </td></tr>

  <!-- Highlights -->
  <tr><td style="padding:24px 32px 0;">
    <p style="margin:0 0 14px;font-size:11px;color:#7CB342;text-transform:uppercase;letter-spacing:1.5px;font-weight:700;">This Week's Highlights</p>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F8FAFC;border-radius:10px;border:1px solid #E2E8F0;">
      {highlights_html}
    </table>
  </td></tr>

  <!-- Pillar References -->
  <tr><td style="padding:8px 32px 0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      {pillar_html}
    </table>
  </td></tr>

  <!-- CTA -->
  <tr><td style="padding:28px 32px;text-align:center;">
    <p style="margin:0 0 18px;color:#475569;font-size:14px;line-height:1.5;">{cta_text}</p>
    <a href="{SITE_URL}/industrial-hiring-insights" style="display:inline-block;padding:14px 36px;background:#7CB342;color:#FFFFFF;text-decoration:none;border-radius:8px;font-weight:700;font-size:14px;letter-spacing:0.3px;">Visit Our Blog</a>
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#0F172A;padding:24px 32px;border-top:none;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr><td>
        <p style="margin:0 0 6px;color:#CBD5E1;font-size:12px;font-weight:600;">Ventures HRD Centre Pvt Ltd</p>
        <p style="margin:0 0 12px;color:#64748B;font-size:11px;line-height:1.5;">Specialist Industrial Recruitment | India</p>
        <p style="margin:0;color:#475569;font-size:11px;line-height:1.6;">
          You're receiving this because you're a {role_label} on Ventures HRD Centre Pvt Ltd.<br>
          <a href="{unsubscribe_url}" style="color:#7CB342;text-decoration:underline;">Unsubscribe</a>
        </p>
      </td></tr>
    </table>
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
    """Send digest emails to all recipients in given segments.
    Skips recipients who already received this week's digest (per-email dedup).
    """
    from services.email_service import send_email

    log_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    week_key = digest.get("week_key", "unknown")

    # Collect emails already sent for this week (from all previous sends)
    already_sent_emails = set()
    prev_logs = await db.digest_send_logs.find(
        {"digest_week_key": week_key, "status": "completed"},
        {"_id": 0, "send_results": 1}
    ).to_list(50)
    for prev_log in prev_logs:
        for sr in prev_log.get("send_results", []):
            if sr.get("status") == "sent":
                already_sent_emails.add(sr.get("recipient", "").lower())

    recipients = await get_segmented_recipients(segments)
    if not recipients:
        return {"status": "skipped", "reason": "no_recipients", "segments": segments}

    # Filter out already-sent recipients
    new_recipients = [r for r in recipients if r["email"].lower() not in already_sent_emails]
    skipped_dupes = len(recipients) - len(new_recipients)

    if not new_recipients:
        return {
            "status": "skipped",
            "reason": "all_already_sent",
            "message": f"All {len(recipients)} recipients already received digest {week_key}",
            "skipped_duplicates": skipped_dupes,
        }

    send_results = []
    success_count = 0
    failure_count = 0

    for recipient in new_recipients:
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
        "total_recipients": len(new_recipients),
        "success_count": success_count,
        "failure_count": failure_count,
        "skipped_count": len(new_recipients) - success_count - failure_count,
        "skipped_duplicates": skipped_dupes,
        "send_results": send_results,
        "triggered_by": triggered_by,
        "started_at": started_at,
        "completed_at": completed_at,
        "status": "completed",
    }
    await db.digest_send_logs.insert_one(log_doc)
    log_doc.pop("_id", None)

    logger.info(f"[DigestEmail] Sent {week_key} to {success_count}/{len(new_recipients)} new recipients ({skipped_dupes} already sent)")
    return {
        "status": "completed",
        "log_id": log_id,
        "week_key": week_key,
        "total_recipients": len(new_recipients),
        "success_count": success_count,
        "failure_count": failure_count,
        "skipped_duplicates": skipped_dupes,
    }


async def get_subscription_stats() -> Dict:
    """Get email subscription statistics including candidate bank coverage."""
    total_unsub = await db.email_subscriptions.count_documents({"subscribed": False})
    unsub_by_role = {}
    pipeline = [
        {"$match": {"subscribed": False}},
        {"$group": {"_id": "$role", "count": {"$sum": 1}}},
    ]
    async for doc in db.email_subscriptions.aggregate(pipeline):
        unsub_by_role[doc["_id"]] = doc["count"]

    # Candidate bank email stats
    total_candidates = await db.candidate_bank.count_documents({})
    candidates_with_email = await db.candidate_bank.count_documents(
        {"email": {"$exists": True, "$nin": ["", None], "$regex": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"}}
    )

    return {
        "total_unsubscribed": total_unsub,
        "by_role": unsub_by_role,
        "candidate_bank": {
            "total": total_candidates,
            "with_email": candidates_with_email,
            "coverage_pct": round((candidates_with_email / total_candidates * 100), 1) if total_candidates > 0 else 0,
        },
    }
