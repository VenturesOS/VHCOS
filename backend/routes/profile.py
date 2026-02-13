"""
Candidate Profile & Messaging Routes
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from config import db
from utils import require_role

profile_router = APIRouter(prefix="/api", tags=["Profile & Messages"])


# --- Profile Routes ---

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    skills: Optional[list] = None
    experience: Optional[str] = None
    current_company: Optional[str] = None
    current_designation: Optional[str] = None
    summary: Optional[str] = None


@profile_router.get("/profile")
async def get_profile(current_user: dict = Depends(require_role(["candidate"]))):
    user = await db.users.find_one({"id": current_user["id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Profile not found")
    user.pop("password", None)
    return user


@profile_router.put("/profile")
async def update_profile(data: ProfileUpdate, current_user: dict = Depends(require_role(["candidate"]))):
    update_fields = {k: v for k, v in data.dict().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"id": current_user["id"]}, {"$set": update_fields})
    user = await db.users.find_one({"id": current_user["id"]}, {"_id": 0, "password": 0})
    return user


@profile_router.post("/profile/resume")
async def upload_resume(file: UploadFile = File(...), current_user: dict = Depends(require_role(["candidate"]))):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    content = await file.read()
    resume_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await db.resumes.insert_one({
        "id": resume_id,
        "user_id": current_user["id"],
        "filename": file.filename,
        "content_type": file.content_type,
        "data": content,
        "uploaded_at": now
    })

    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"resume_id": resume_id, "resume_filename": file.filename, "updated_at": now}}
    )

    return {"message": "Resume uploaded successfully", "resume_id": resume_id, "filename": file.filename}


# --- Message Routes ---

class MessageCreate(BaseModel):
    to_user_id: str
    subject: str
    body: str


@profile_router.get("/messages")
async def get_messages(sent: bool = False, current_user: dict = Depends(require_role(["candidate", "employer", "recruiter", "admin"]))):
    if sent:
        query = {"from_user_id": current_user["id"]}
    else:
        query = {"to_user_id": current_user["id"]}

    messages = await db.messages.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return messages


@profile_router.post("/messages")
async def send_message(data: MessageCreate, current_user: dict = Depends(require_role(["candidate", "employer", "recruiter", "admin"]))):
    msg_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    message_doc = {
        "id": msg_id,
        "from_user_id": current_user["id"],
        "from_name": current_user.get("name", ""),
        "from_email": current_user.get("email", ""),
        "to_user_id": data.to_user_id,
        "subject": data.subject,
        "body": data.body,
        "is_read": False,
        "created_at": now
    }

    await db.messages.insert_one(message_doc)
    message_doc.pop("_id", None)
    return message_doc


@profile_router.put("/messages/{message_id}/read")
async def mark_message_read(message_id: str, current_user: dict = Depends(require_role(["candidate", "employer", "recruiter", "admin"]))):
    result = await db.messages.update_one(
        {"id": message_id, "to_user_id": current_user["id"]},
        {"$set": {"is_read": True}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"message": "Marked as read"}
