"""
Blog Digest Routes — Admin digest management, email sending, preview, and public unsubscribe.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from config import db
from utils import require_role
from services.blog_digest import generate_weekly_digest
from services.digest_email_service import (
    build_digest_email_html,
    send_digest_to_segments,
    get_segmented_recipients,
    get_subscription_stats,
    verify_unsubscribe_token,
)

router = APIRouter(tags=["blog-digest"])
logger = logging.getLogger(__name__)

VALID_SEGMENTS = ["admin", "employer", "recruiter", "candidate", "candidate_bank"]


class DigestSendRequest(BaseModel):
    segments: List[str]
    week_key: Optional[str] = None


# ── Admin: Trigger digest generation ──

@router.post("/api/admin/blog-digest/trigger")
async def admin_trigger_digest(current_user: dict = Depends(require_role(["admin"]))):
    """Admin: Manually trigger weekly digest generation."""
    result = await generate_weekly_digest()
    return result


# ── Admin: List all digests ──

@router.get("/api/admin/blog-digests")
async def admin_list_digests(current_user: dict = Depends(require_role(["admin"]))):
    """Admin: List all generated digests with send status."""
    digests = await db.blog_digests.find({}, {"_id": 0}).sort("generated_at", -1).to_list(50)

    # Enrich with send log info
    for d in digests:
        wk = d.get("week_key")
        send_log = await db.digest_send_logs.find_one(
            {"digest_week_key": wk, "status": "completed"},
            {"_id": 0, "id": 1, "total_recipients": 1, "success_count": 1,
             "failure_count": 1, "segments": 1, "completed_at": 1}
        )
        d["send_log"] = send_log

    return {"digests": digests}


# ── Admin: Preview digest email ──

@router.get("/api/admin/blog-digest/preview")
async def admin_preview_digest(
    week_key: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin: Preview digest email HTML. Uses latest digest if no week_key."""
    if week_key:
        digest = await db.blog_digests.find_one({"week_key": week_key}, {"_id": 0})
    else:
        digest = await db.blog_digests.find_one({}, {"_id": 0}, sort=[("generated_at", -1)])

    if not digest:
        raise HTTPException(status_code=404, detail="No digest found")

    # Build preview with admin as recipient
    preview_recipient = {
        "id": current_user["id"],
        "name": current_user.get("name", "Admin"),
        "email": current_user.get("email", "admin@vhc.in"),
        "role": "admin",
    }
    html = build_digest_email_html(digest, preview_recipient)
    return {"week_key": digest["week_key"], "title": digest.get("title"), "html": html}


# ── Admin: Send digest to segments ──

@router.post("/api/admin/blog-digest/send")
async def admin_send_digest(
    req: DigestSendRequest,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin: Send latest digest to selected user segments."""
    # Validate segments
    invalid = [s for s in req.segments if s not in VALID_SEGMENTS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid segments: {invalid}")
    if not req.segments:
        raise HTTPException(status_code=400, detail="At least one segment required")

    # Get digest
    if req.week_key:
        digest = await db.blog_digests.find_one({"week_key": req.week_key}, {"_id": 0})
    else:
        digest = await db.blog_digests.find_one({}, {"_id": 0}, sort=[("generated_at", -1)])

    if not digest:
        raise HTTPException(status_code=404, detail="No digest found. Generate one first.")

    result = await send_digest_to_segments(
        digest=digest,
        segments=req.segments,
        triggered_by=current_user["id"],
    )
    return result


# ── Admin: Recipient preview (who would receive) ──

@router.get("/api/admin/blog-digest/recipients")
async def admin_preview_recipients(
    segments: str = Query(..., description="Comma-separated segments"),
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin: Preview recipient list for given segments (without sending)."""
    seg_list = [s.strip() for s in segments.split(",") if s.strip() in VALID_SEGMENTS]
    if not seg_list:
        raise HTTPException(status_code=400, detail="No valid segments provided")

    recipients = await get_segmented_recipients(seg_list)
    return {
        "segments": seg_list,
        "total": len(recipients),
        "recipients": [
            {"name": r.get("name", ""), "email": r["email"], "role": r["role"]}
            for r in recipients
        ],
    }


# ── Admin: Send logs ──

@router.get("/api/admin/blog-digest/send-logs")
async def admin_get_send_logs(current_user: dict = Depends(require_role(["admin"]))):
    """Admin: Get all digest send logs."""
    logs = await db.digest_send_logs.find(
        {}, {"_id": 0, "send_results": 0}
    ).sort("completed_at", -1).to_list(50)
    return {"logs": logs}


# ── Admin: Subscription stats ──

@router.get("/api/admin/blog-digest/subscription-stats")
async def admin_subscription_stats(current_user: dict = Depends(require_role(["admin"]))):
    """Admin: Get email subscription/unsubscription statistics."""
    stats = await get_subscription_stats()
    return stats


# ── Public: Unsubscribe ──

@router.get("/api/unsubscribe/{token}")
async def unsubscribe(token: str):
    """Public: Unsubscribe from blog digest emails. Supports platform users and candidate bank entries."""
    user_id = verify_unsubscribe_token(token)
    if not user_id:
        return HTMLResponse(
            content=_unsub_page("Invalid Link", "This unsubscribe link is invalid or expired.", False),
            status_code=400,
        )

    # Look up in users collection first, then candidate bank
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "email": 1, "name": 1, "role": 1})
    role = user.get("role", "unknown") if user else "candidate_bank"
    if not user:
        user = await db.candidate_bank.find_one({"id": user_id}, {"_id": 0, "email": 1, "name": 1})
    if not user:
        return HTMLResponse(
            content=_unsub_page("User Not Found", "We couldn't find your account.", False),
            status_code=404,
        )

    # Upsert unsubscribe record
    now = datetime.now(timezone.utc).isoformat()
    await db.email_subscriptions.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "email": user["email"],
            "role": role,
            "subscribed": False,
            "unsubscribed_at": now,
            "updated_at": now,
        }},
        upsert=True,
    )

    logger.info(f"[Unsubscribe] {user['email']} (role={role}) unsubscribed from digest emails")
    return HTMLResponse(
        content=_unsub_page(
            "Unsubscribed Successfully",
            f"You ({user['email']}) have been unsubscribed from Ventures HRD Centre Pvt Ltd weekly digest emails.",
            True,
            user_id=user_id,
            token=token,
        ),
    )


# ── Public: Re-subscribe ──

@router.get("/api/resubscribe/{token}")
async def resubscribe(token: str):
    """Public: Re-subscribe to blog digest emails. Supports users and candidate bank entries."""
    user_id = verify_unsubscribe_token(token)
    if not user_id:
        return HTMLResponse(
            content=_unsub_page("Invalid Link", "This link is invalid.", False),
            status_code=400,
        )

    now = datetime.now(timezone.utc).isoformat()
    result = await db.email_subscriptions.update_one(
        {"user_id": user_id},
        {"$set": {"subscribed": True, "subscribed_at": now, "updated_at": now}},
    )

    if result.matched_count == 0:
        return HTMLResponse(
            content=_unsub_page("Already Subscribed", "You are already subscribed.", False),
        )

    logger.info(f"[Resubscribe] {user_id} re-subscribed")
    return HTMLResponse(
        content=_unsub_page("Re-subscribed!", "You have been re-subscribed to Ventures HRD Centre Pvt Ltd weekly digest emails.", False),
    )


def _unsub_page(title: str, message: str, show_resub: bool, user_id: str = "", token: str = "") -> str:
    """Simple HTML page for unsubscribe/resubscribe confirmation."""
    resub_html = ""
    if show_resub and token:
        resub_html = f"""
        <p style="margin-top:20px;">
          <a href="/api/resubscribe/{token}" style="color:#7CB342;text-decoration:underline;font-size:14px;">
            Changed your mind? Re-subscribe
          </a>
        </p>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title} — Ventures HRD Centre Pvt Ltd</title></head>
<body style="margin:0;padding:40px 16px;background:#F1F5F9;font-family:'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
<div style="max-width:480px;margin:0 auto;background:#FFF;border-radius:16px;padding:40px 32px;text-align:center;box-shadow:0 4px 24px rgba(15,23,42,0.08);">
  <div style="margin-bottom:16px;">
    <img src="https://customer-assets.emergentagent.com/job_vhc-edit/artifacts/46yye45w_logo.svg" alt="Ventures HRD Centre Pvt Ltd" style="height:44px;width:auto;" />
  </div>
  <h1 style="margin:0 0 12px;color:#0F172A;font-size:22px;">{title}</h1>
  <p style="margin:0;color:#475569;font-size:15px;line-height:1.6;">{message}</p>
  {resub_html}
  <hr style="border:none;border-top:1px solid #E2E8F0;margin:28px 0 16px;">
  <p style="margin:0;color:#94A3B8;font-size:12px;">Ventures HRD Centre Pvt Ltd | India</p>
</div>
</body></html>"""
