"""
VHC Talent OS - Settings & Alerts Routes
Handles all settings, job alerts preferences, notification channels,
and system configuration endpoints.
"""
import uuid
import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends

# Import configuration
from config import db

# Import models
from models import (
    JobAlertPreferences, JobAlertCreate, WhatsAppOptIn
)

# Import utilities
from utils import get_current_user, require_role

# Import notification services
from services.notification_service import send_alert_confirmation_email
from services.whatsapp_service import validate_phone_number, is_whatsapp_enabled

# Create router for settings endpoints
settings_router = APIRouter(prefix="/api", tags=["Settings & Alerts"])


# ============== GLOBAL SETTINGS (Admin Only) ==============

@settings_router.get("/settings")
async def get_settings(current_user: dict = Depends(require_role(["admin"]))):
    """Get global system settings (Admin only)"""
    settings = await db.settings.find_one({"type": "global"}, {"_id": 0})
    if not settings:
        settings = {
            "type": "global",
            "ai_parsing_enabled": True,
            "email_notifications": True,
            "max_applications_per_job": 100,
            "resume_size_limit_mb": 5
        }
        await db.settings.insert_one(settings)
        settings.pop("_id", None)
    return settings


@settings_router.put("/settings")
async def update_settings(settings_data: dict, current_user: dict = Depends(require_role(["admin"]))):
    """Update global system settings (Admin only)"""
    await db.settings.update_one(
        {"type": "global"},
        {"$set": settings_data},
        upsert=True
    )
    return {"message": "Settings updated successfully"}


# ============== JOB ALERTS PREFERENCES ==============

@settings_router.get("/alerts/preferences", response_model=JobAlertPreferences)
async def get_alert_preferences(current_user: dict = Depends(require_role(["candidate"]))):
    """Get candidate's job alert preferences"""
    prefs = await db.job_alerts.find_one({"candidate_id": current_user["id"]}, {"_id": 0})
    
    if not prefs:
        # Get candidate profile to populate default skills
        profile = await db.candidate_profiles.find_one({"user_id": current_user["id"]}, {"_id": 0})
        default_skills = profile.get("skills", []) if profile else []
        
        # Also check candidate_bank for skills
        if not default_skills:
            bank_record = await db.candidate_bank.find_one(
                {"$or": [{"linked_user_id": current_user["id"]}, {"email": current_user["email"]}]},
                {"_id": 0}
            )
            if bank_record:
                default_skills = bank_record.get("skills", [])
        
        # Create default preferences
        now = datetime.now(timezone.utc).isoformat()
        prefs = {
            "id": str(uuid.uuid4()),
            "candidate_id": current_user["id"],
            "candidate_email": current_user["email"],
            "is_active": False,  # Not active until explicitly enabled
            "email_enabled": True,
            "skills": default_skills[:10],  # Limit to 10 skills
            "location_preference": None,
            "experience_min": None,
            "experience_max": None,
            "job_types": [],
            "frequency": "instant",
            "whatsapp_opt_in": False,
            "whatsapp_number": None,
            "whatsapp_opt_in_timestamp": None,
            "notification_channels": ["email"],
            "created_at": now,
            "updated_at": now
        }
        await db.job_alerts.insert_one(prefs)
    
    return JobAlertPreferences(**prefs)


@settings_router.post("/alerts/preferences", response_model=JobAlertPreferences)
async def create_or_update_alert_preferences(
    prefs_data: JobAlertCreate,
    current_user: dict = Depends(require_role(["candidate"]))
):
    """Create or update job alert preferences (opt-in to alerts)"""
    now = datetime.now(timezone.utc).isoformat()
    
    existing = await db.job_alerts.find_one({"candidate_id": current_user["id"]}, {"_id": 0})
    
    update_dict = {k: v for k, v in prefs_data.model_dump().items() if v is not None}
    update_dict["updated_at"] = now
    update_dict["is_active"] = True  # Activating alerts
    
    if existing:
        await db.job_alerts.update_one(
            {"candidate_id": current_user["id"]},
            {"$set": update_dict}
        )
        prefs = await db.job_alerts.find_one({"candidate_id": current_user["id"]}, {"_id": 0})
    else:
        # Get default skills from profile
        profile = await db.candidate_profiles.find_one({"user_id": current_user["id"]}, {"_id": 0})
        default_skills = profile.get("skills", []) if profile else []
        
        prefs = {
            "id": str(uuid.uuid4()),
            "candidate_id": current_user["id"],
            "candidate_email": current_user["email"],
            "is_active": True,
            "email_enabled": update_dict.get("email_enabled", True),
            "skills": update_dict.get("skills", default_skills[:10]),
            "location_preference": update_dict.get("location_preference"),
            "experience_min": update_dict.get("experience_min"),
            "experience_max": update_dict.get("experience_max"),
            "job_types": update_dict.get("job_types", []),
            "frequency": update_dict.get("frequency", "instant"),
            "whatsapp_opt_in": False,
            "whatsapp_number": None,
            "whatsapp_opt_in_timestamp": None,
            "notification_channels": ["email"],
            "created_at": now,
            "updated_at": now
        }
        await db.job_alerts.insert_one(prefs)
    
    # Send confirmation email
    asyncio.create_task(send_alert_confirmation_email(
        db=db,
        candidate_email=current_user["email"],
        candidate_name=current_user.get("name", "Candidate"),
        preferences=prefs
    ))
    
    return JobAlertPreferences(**prefs)


@settings_router.put("/alerts/preferences", response_model=JobAlertPreferences)
async def update_alert_preferences(
    prefs_data: JobAlertCreate,
    current_user: dict = Depends(require_role(["candidate"]))
):
    """Update existing job alert preferences"""
    existing = await db.job_alerts.find_one({"candidate_id": current_user["id"]})
    if not existing:
        raise HTTPException(status_code=404, detail="Alert preferences not found. Create them first.")
    
    update_dict = {k: v for k, v in prefs_data.model_dump().items() if v is not None}
    update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.job_alerts.update_one(
        {"candidate_id": current_user["id"]},
        {"$set": update_dict}
    )
    
    prefs = await db.job_alerts.find_one({"candidate_id": current_user["id"]}, {"_id": 0})
    return JobAlertPreferences(**prefs)


@settings_router.delete("/alerts/preferences")
async def delete_alert_preferences(current_user: dict = Depends(require_role(["candidate"]))):
    """Unsubscribe from all job alerts (soft delete - sets is_active to false)"""
    result = await db.job_alerts.update_one(
        {"candidate_id": current_user["id"]},
        {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Alert preferences not found")
    
    return {"message": "Successfully unsubscribed from job alerts"}


@settings_router.post("/alerts/pause")
async def pause_alerts(current_user: dict = Depends(require_role(["candidate"]))):
    """Temporarily pause job alerts"""
    await db.job_alerts.update_one(
        {"candidate_id": current_user["id"]},
        {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"message": "Job alerts paused"}


@settings_router.post("/alerts/resume")
async def resume_alerts(current_user: dict = Depends(require_role(["candidate"]))):
    """Resume paused job alerts"""
    await db.job_alerts.update_one(
        {"candidate_id": current_user["id"]},
        {"$set": {"is_active": True, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"message": "Job alerts resumed"}


# ============== WHATSAPP OPT-IN/OUT ==============

@settings_router.post("/alerts/whatsapp/opt-in", response_model=JobAlertPreferences)
async def whatsapp_opt_in(
    opt_in_data: WhatsAppOptIn,
    current_user: dict = Depends(require_role(["candidate"]))
):
    """
    Opt-in to WhatsApp notifications.
    REQUIRES explicit consent and valid phone number.
    """
    if not is_whatsapp_enabled():
        raise HTTPException(
            status_code=400, 
            detail="WhatsApp notifications are not configured on this system"
        )
    
    # Validate phone number
    validated_phone = validate_phone_number(opt_in_data.whatsapp_number)
    if not validated_phone:
        raise HTTPException(status_code=400, detail="Invalid phone number format. Use E.164 format (e.g., +919876543210)")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Ensure alert preferences exist
    existing = await db.job_alerts.find_one({"candidate_id": current_user["id"]})
    if not existing:
        # Create default preferences first
        prefs = {
            "id": str(uuid.uuid4()),
            "candidate_id": current_user["id"],
            "candidate_email": current_user["email"],
            "is_active": True,
            "email_enabled": True,
            "skills": [],
            "location_preference": None,
            "experience_min": None,
            "experience_max": None,
            "job_types": [],
            "frequency": "instant",
            "whatsapp_opt_in": True,
            "whatsapp_number": validated_phone,
            "whatsapp_opt_in_timestamp": now,
            "notification_channels": ["email", "whatsapp"],
            "created_at": now,
            "updated_at": now
        }
        await db.job_alerts.insert_one(prefs)
    else:
        # Update existing with WhatsApp opt-in
        update_data = {
            "whatsapp_opt_in": True,
            "whatsapp_number": validated_phone,
            "whatsapp_opt_in_timestamp": now,
            "notification_channels": list(set(existing.get("notification_channels", []) + ["whatsapp"])),
            "updated_at": now
        }
        await db.job_alerts.update_one(
            {"candidate_id": current_user["id"]},
            {"$set": update_data}
        )
    
    prefs = await db.job_alerts.find_one({"candidate_id": current_user["id"]}, {"_id": 0})
    return JobAlertPreferences(**prefs)


@settings_router.post("/alerts/whatsapp/opt-out")
async def whatsapp_opt_out(current_user: dict = Depends(require_role(["candidate"]))):
    """
    Opt-out of WhatsApp notifications.
    Email notifications remain unaffected.
    """
    now = datetime.now(timezone.utc).isoformat()
    
    existing = await db.job_alerts.find_one({"candidate_id": current_user["id"]})
    if existing:
        channels = existing.get("notification_channels", ["email"])
        if "whatsapp" in channels:
            channels.remove("whatsapp")
        
        await db.job_alerts.update_one(
            {"candidate_id": current_user["id"]},
            {"$set": {
                "whatsapp_opt_in": False,
                "notification_channels": channels,
                "updated_at": now
            }}
        )
    
    return {"message": "Successfully opted out of WhatsApp notifications"}


@settings_router.put("/alerts/whatsapp/number")
async def update_whatsapp_number(
    opt_in_data: WhatsAppOptIn,
    current_user: dict = Depends(require_role(["candidate"]))
):
    """Update WhatsApp phone number (must already be opted in)"""
    existing = await db.job_alerts.find_one({"candidate_id": current_user["id"]})
    if not existing or not existing.get("whatsapp_opt_in"):
        raise HTTPException(status_code=400, detail="Please opt-in to WhatsApp first")
    
    validated_phone = validate_phone_number(opt_in_data.whatsapp_number)
    if not validated_phone:
        raise HTTPException(status_code=400, detail="Invalid phone number format")
    
    await db.job_alerts.update_one(
        {"candidate_id": current_user["id"]},
        {"$set": {
            "whatsapp_number": validated_phone,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"message": "WhatsApp number updated", "number": validated_phone}


# ============== NOTIFICATION HISTORY ==============

@settings_router.get("/notifications/history")
async def get_notification_history(
    limit: int = 20,
    current_user: dict = Depends(require_role(["candidate"]))
):
    """Get notification history for current candidate"""
    notifications = await db.notification_logs.find(
        {"recipient_id": current_user["id"]},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    return notifications


@settings_router.get("/admin/notifications/stats")
async def get_notification_stats(current_user: dict = Depends(require_role(["admin"]))):
    """Get notification statistics (admin only)"""
    # Total notifications sent
    total_sent = await db.notification_logs.count_documents({"status": "sent"})
    total_failed = await db.notification_logs.count_documents({"status": "failed"})
    total_skipped = await db.notification_logs.count_documents({"status": "skipped"})
    
    # By channel
    email_sent = await db.notification_logs.count_documents({"channel": "email", "status": "sent"})
    whatsapp_sent = await db.notification_logs.count_documents({"channel": "whatsapp", "status": "sent"})
    
    # Active alert subscribers
    active_subscribers = await db.job_alerts.count_documents({"is_active": True})
    whatsapp_opted_in = await db.job_alerts.count_documents({"whatsapp_opt_in": True})
    
    return {
        "total_sent": total_sent,
        "total_failed": total_failed,
        "total_skipped": total_skipped,
        "email_sent": email_sent,
        "whatsapp_sent": whatsapp_sent,
        "active_subscribers": active_subscribers,
        "whatsapp_opted_in": whatsapp_opted_in
    }
