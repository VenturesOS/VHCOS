"""
Notification Service for VHC Talent OS
Orchestrates email and WhatsApp notifications for job matches
"""
import os
import asyncio
import logging
from typing import Optional, Dict, List
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

from services.email_service import send_email, send_batch_emails
from services.whatsapp_service import send_whatsapp_message, is_whatsapp_enabled, validate_phone_number
from services.notification_templates import (
    render_email_template, 
    render_whatsapp_template,
    get_job_list_html,
    get_job_list_text
)

logger = logging.getLogger(__name__)

# Configuration
JOB_MATCH_THRESHOLD = int(os.environ.get('JOB_MATCH_THRESHOLD', '60'))
NOTIFICATION_ENABLED = os.environ.get('NOTIFICATION_ENABLED', 'true').lower() == 'true'
APP_BASE_URL = os.environ.get('APP_BASE_URL', 'https://vhc-recruit.preview.emergentagent.com')


async def log_notification(
    db: AsyncIOMotorDatabase,
    notification_type: str,
    recipient_id: str,
    recipient_email: str,
    channel: str,
    job_id: Optional[str],
    status: str,
    details: Dict
) -> str:
    """
    Log notification event for audit and deduplication.
    Returns notification_id.
    """
    import uuid
    notification_id = str(uuid.uuid4())
    
    log_entry = {
        "id": notification_id,
        "type": notification_type,
        "recipient_id": recipient_id,
        "recipient_email": recipient_email,
        "channel": channel,
        "job_id": job_id,
        "status": status,
        "details": details,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.notification_logs.insert_one(log_entry)
    return notification_id


async def has_notification_been_sent(
    db: AsyncIOMotorDatabase,
    recipient_id: str,
    job_id: str,
    channel: str
) -> bool:
    """
    Check if notification for this job has already been sent to this candidate.
    Prevents duplicate notifications.
    """
    existing = await db.notification_logs.find_one({
        "recipient_id": recipient_id,
        "job_id": job_id,
        "channel": channel,
        "status": {"$in": ["sent", "skipped"]}
    })
    return existing is not None


async def get_candidate_notification_preferences(
    db: AsyncIOMotorDatabase,
    candidate_id: str
) -> Optional[Dict]:
    """
    Get candidate's notification/alert preferences.
    """
    prefs = await db.job_alerts.find_one({"candidate_id": candidate_id}, {"_id": 0})
    return prefs


async def notify_candidate_of_job_match(
    db: AsyncIOMotorDatabase,
    candidate: Dict,
    job: Dict,
    match_result: Dict,
    company_name: str
) -> Dict:
    """
    Send job match notification to a single candidate via their preferred channels.
    Respects consent and prevents duplicates.
    
    Args:
        db: Database instance
        candidate: Candidate data from candidate_bank
        job: Job data
        match_result: Result from AI matching engine with score, explanation etc.
        company_name: Name of the company posting the job
    
    Returns:
        Dict with notification results
    """
    if not NOTIFICATION_ENABLED:
        return {"status": "disabled", "message": "Notifications are disabled"}
    
    candidate_id = candidate.get("id") or candidate.get("linked_user_id")
    candidate_email = candidate.get("email")
    candidate_name = candidate.get("name", "Candidate")
    
    if not candidate_email:
        return {"status": "skipped", "message": "No email address"}
    
    # Get notification preferences
    prefs = await get_candidate_notification_preferences(db, candidate_id)
    
    # Default: email enabled, WhatsApp disabled
    email_enabled = True
    whatsapp_enabled = False
    
    if prefs:
        email_enabled = prefs.get("email_enabled", True) and prefs.get("is_active", True)
        whatsapp_enabled = (
            prefs.get("whatsapp_opt_in", False) and 
            prefs.get("is_active", True) and
            is_whatsapp_enabled()
        )
    
    job_id = job.get("id")
    job_title = job.get("title", "Job Opportunity")
    job_location = job.get("location", "Not specified")
    match_score = match_result.get("score", 0)
    match_explanation = match_result.get("explanation", "Your skills match this job's requirements.")
    
    results = {
        "candidate_id": candidate_id,
        "job_id": job_id,
        "channels": {}
    }
    
    # Prepare template variables
    template_vars = {
        "candidate_name": candidate_name,
        "job_title": job_title,
        "company_name": company_name,
        "job_location": job_location,
        "match_score": str(match_score),
        "match_explanation": match_explanation,
        "apply_link": f"{APP_BASE_URL}/candidate/jobs/{job_id}",
        "unsubscribe_link": f"{APP_BASE_URL}/candidate/settings/notifications"
    }
    
    # Send Email
    if email_enabled:
        # Check for duplicate
        if await has_notification_been_sent(db, candidate_id, job_id, "email"):
            results["channels"]["email"] = {"status": "skipped", "reason": "already_sent"}
        else:
            rendered = render_email_template("job_match_notification", template_vars)
            if rendered:
                email_result = await send_email(
                    recipient_email=candidate_email,
                    subject=rendered["subject"],
                    html_content=rendered["html"],
                    text_content=rendered["text"]
                )
                results["channels"]["email"] = email_result
                
                # Log notification
                await log_notification(
                    db=db,
                    notification_type="job_match",
                    recipient_id=candidate_id,
                    recipient_email=candidate_email,
                    channel="email",
                    job_id=job_id,
                    status=email_result.get("status", "unknown"),
                    details=email_result
                )
    
    # Send WhatsApp (if opted in)
    if whatsapp_enabled and prefs:
        whatsapp_number = prefs.get("whatsapp_number")
        if whatsapp_number:
            # Check for duplicate
            if await has_notification_been_sent(db, candidate_id, job_id, "whatsapp"):
                results["channels"]["whatsapp"] = {"status": "skipped", "reason": "already_sent"}
            else:
                rendered_wa = render_whatsapp_template("job_match_notification", template_vars)
                if rendered_wa:
                    wa_result = await send_whatsapp_message(
                        recipient_phone=whatsapp_number,
                        message_body=rendered_wa["body"]
                    )
                    results["channels"]["whatsapp"] = wa_result
                    
                    # Log notification
                    await log_notification(
                        db=db,
                        notification_type="job_match",
                        recipient_id=candidate_id,
                        recipient_email=candidate_email,
                        channel="whatsapp",
                        job_id=job_id,
                        status=wa_result.get("status", "unknown"),
                        details=wa_result
                    )
    
    return results


async def process_job_notifications(
    db: AsyncIOMotorDatabase,
    job: Dict,
    company_name: str,
    matching_candidates: List[Dict]
) -> Dict:
    """
    Process notifications for all matching candidates when a job is posted/updated.
    Runs asynchronously in background.
    
    Args:
        db: Database instance
        job: Job data
        company_name: Company name
        matching_candidates: List of candidates with match results
    
    Returns:
        Summary of notification results
    """
    if not NOTIFICATION_ENABLED:
        return {"status": "disabled", "total": 0}
    
    job_id = job.get("id")
    logger.info(f"[NOTIFY] Processing notifications for job {job_id}, {len(matching_candidates)} candidates")
    
    results = {
        "job_id": job_id,
        "total_candidates": len(matching_candidates),
        "notifications_sent": 0,
        "notifications_skipped": 0,
        "notifications_failed": 0,
        "details": []
    }
    
    # Filter candidates with score >= threshold
    qualified_candidates = [
        c for c in matching_candidates 
        if c.get("match_result", {}).get("score", 0) >= JOB_MATCH_THRESHOLD
    ]
    
    logger.info(f"[NOTIFY] {len(qualified_candidates)} candidates meet threshold ({JOB_MATCH_THRESHOLD}%)")
    
    # Process notifications concurrently
    tasks = []
    for candidate_match in qualified_candidates:
        candidate = candidate_match.get("candidate", {})
        match_result = candidate_match.get("match_result", {})
        
        tasks.append(notify_candidate_of_job_match(
            db=db,
            candidate=candidate,
            job=job,
            match_result=match_result,
            company_name=company_name
        ))
    
    if tasks:
        notification_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in notification_results:
            if isinstance(result, Exception):
                results["notifications_failed"] += 1
                logger.error(f"[NOTIFY] Notification error: {result}")
            elif isinstance(result, dict):
                channels = result.get("channels", {})
                if any(ch.get("status") == "sent" for ch in channels.values()):
                    results["notifications_sent"] += 1
                elif any(ch.get("status") == "skipped" for ch in channels.values()):
                    results["notifications_skipped"] += 1
                else:
                    results["notifications_failed"] += 1
    
    logger.info(f"[NOTIFY] Job {job_id}: sent={results['notifications_sent']}, skipped={results['notifications_skipped']}, failed={results['notifications_failed']}")
    
    return results


async def trigger_job_notifications_background(
    db: AsyncIOMotorDatabase,
    job_id: str
):
    """
    Background task to find matching candidates and send notifications.
    Called when a job is created or updated.
    """
    from services.matching_engine import parse_job_description_with_ai, calculate_candidate_job_match
    
    logger.info(f"[NOTIFY-BG] Starting background notification task for job {job_id}")
    
    # Get job details
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        logger.error(f"[NOTIFY-BG] Job {job_id} not found")
        return
    
    # Get company name
    company = None
    if job.get("company_id"):
        company = await db.companies.find_one({"id": job["company_id"]}, {"_id": 0})
    company_name = company.get("name", "Company") if company else "Company"
    
    # Parse job description
    jd_text = f"{job.get('title', '')} {job.get('description', '')} {job.get('requirements', '')}"
    jd_result = await parse_job_description_with_ai(jd_text)
    
    if not jd_result.get("success"):
        logger.error(f"[NOTIFY-BG] Failed to parse JD for job {job_id}")
        return
    
    job_parsed = jd_result.get("data", {})
    
    # Get all candidates from data bank who have alerts enabled
    candidates_with_alerts = []
    async for alert in db.job_alerts.find({"is_active": True, "email_enabled": True}, {"_id": 0}):
        # Try to find candidate by multiple criteria
        candidate = await db.candidate_bank.find_one({
            "$or": [
                {"id": alert["candidate_id"]},
                {"linked_user_id": alert["candidate_id"]},
                {"email": alert.get("candidate_email")}
            ]
        }, {"_id": 0})
        
        if candidate:
            candidates_with_alerts.append({
                "candidate": candidate,
                "alert": alert
            })
        else:
            logger.debug(f"[NOTIFY-BG] No candidate bank record for alert subscriber: {alert.get('candidate_email')}")
    
    if not candidates_with_alerts:
        logger.info("[NOTIFY-BG] No candidates with active alerts")
        return
    
    # Match each candidate against the job
    matching_candidates = []
    for item in candidates_with_alerts:
        candidate = item["candidate"]
        
        # Build candidate data for matching
        candidate_data = {
            "skills": candidate.get("skills", []),
            "experience_years": candidate.get("experience_years", 0),
            "education": candidate.get("education", []),
            "location": candidate.get("location"),
            "summary": candidate.get("summary")
        }
        
        # Calculate match
        match_result = await calculate_candidate_job_match(candidate_data, job_parsed)
        
        if match_result.get("score", 0) >= JOB_MATCH_THRESHOLD:
            matching_candidates.append({
                "candidate": candidate,
                "match_result": match_result
            })
    
    logger.info(f"[NOTIFY-BG] Found {len(matching_candidates)} matching candidates for job {job_id}")
    
    # Send notifications
    if matching_candidates:
        await process_job_notifications(db, job, company_name, matching_candidates)


async def send_alert_confirmation_email(
    db: AsyncIOMotorDatabase,
    candidate_email: str,
    candidate_name: str,
    preferences: Dict
) -> Dict:
    """
    Send confirmation email when candidate sets up job alerts.
    """
    template_vars = {
        "candidate_name": candidate_name,
        "skills_list": ", ".join(preferences.get("skills", [])) or "Any",
        "location_pref": preferences.get("location_preference") or "Any",
        "experience_range": f"{preferences.get('experience_min', 0)}-{preferences.get('experience_max', 'Any')} years",
        "frequency": preferences.get("frequency", "instant").title(),
        "manage_link": f"{APP_BASE_URL}/candidate/settings/notifications"
    }
    
    rendered = render_email_template("alert_subscription_confirmed", template_vars)
    if rendered:
        return await send_email(
            recipient_email=candidate_email,
            subject=rendered["subject"],
            html_content=rendered["html"],
            text_content=rendered["text"]
        )
    
    return {"status": "failed", "message": "Template rendering failed"}
