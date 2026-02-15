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
