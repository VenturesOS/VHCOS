from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime, timezone
import uuid
import logging

from config import db
from utils import get_current_user, require_role

router = APIRouter(tags=["contact"])
logger = logging.getLogger(__name__)


class ContactSubmission(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=200)
    company_name: Optional[str] = Field(None, max_length=200)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=30)
    service_interest: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=5000)


@router.post("/api/contact-submission")
async def submit_contact_form(data: ContactSubmission):
    """Public endpoint - stores contact form submissions in MongoDB."""
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "full_name": data.full_name,
        "company_name": data.company_name,
        "email": data.email,
        "phone": data.phone,
        "service_interest": data.service_interest,
        "message": data.message,
        "status": "new",
        "submitted_at": now,
        "created_at": now,
    }
    await db.contact_submissions.insert_one(doc)
    logger.info(f"Contact form submission from {data.email}")

    # Send email notification to admin
    try:
        from services.email_service import send_email
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@vhc.in")
        await send_email(
            recipient_email=admin_email,
            subject=f"New Contact Lead: {data.full_name} — {data.service_interest}",
            html_content=f"""
            <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;padding:24px;">
              <h2 style="color:#111827;margin-bottom:16px;">New Contact Form Submission</h2>
              <table style="width:100%;border-collapse:collapse;">
                <tr><td style="padding:8px 0;color:#6B7280;width:130px;">Name</td><td style="padding:8px 0;font-weight:600;">{data.full_name}</td></tr>
                <tr><td style="padding:8px 0;color:#6B7280;">Company</td><td style="padding:8px 0;">{data.company_name or '—'}</td></tr>
                <tr><td style="padding:8px 0;color:#6B7280;">Email</td><td style="padding:8px 0;"><a href="mailto:{data.email}">{data.email}</a></td></tr>
                <tr><td style="padding:8px 0;color:#6B7280;">Phone</td><td style="padding:8px 0;">{data.phone or '—'}</td></tr>
                <tr><td style="padding:8px 0;color:#6B7280;">Service</td><td style="padding:8px 0;font-weight:600;">{data.service_interest}</td></tr>
              </table>
              <div style="background:#F9FAFB;border-radius:8px;padding:16px;margin-top:16px;">
                <p style="color:#6B7280;font-size:13px;margin-bottom:4px;">Message:</p>
                <p style="color:#111827;">{data.message}</p>
              </div>
              <hr style="border:none;border-top:1px solid #E5E7EB;margin:24px 0;">
              <p style="color:#9CA3AF;font-size:12px;">VHC Talent OS — Auto-generated notification</p>
            </div>
            """,
        )
    except Exception as e:
        logger.warning(f"Failed to send contact notification email: {e}")

    return {"message": "Thank you! Your message has been received. We'll get back to you within 24 hours."}


@router.get("/api/contact-submissions")
async def get_contact_submissions(
    status: Optional[str] = None,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin only - list all contact form submissions."""
    query = {}
    if status:
        query["status"] = status
    submissions = await db.contact_submissions.find(
        query, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return {"submissions": submissions, "total": len(submissions)}


@router.put("/api/contact-submissions/{submission_id}/status")
async def update_submission_status(
    submission_id: str,
    new_status: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin only - update status (new, reviewed, contacted, closed)."""
    valid_statuses = ["new", "reviewed", "contacted", "closed"]
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {valid_statuses}")
    result = await db.contact_submissions.update_one(
        {"id": submission_id},
        {"$set": {"status": new_status, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": current_user["id"]}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Submission not found")
    return {"message": f"Status updated to {new_status}"}


@router.delete("/api/contact-submissions/{submission_id}")
async def delete_submission(
    submission_id: str,
    current_user: dict = Depends(require_role(["admin"]))
):
    """Admin only - delete a contact submission."""
    result = await db.contact_submissions.delete_one({"id": submission_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Submission not found")
    return {"message": "Submission deleted"}
