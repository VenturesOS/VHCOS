"""
Groq Batch Enrichment Service — Cost-optimized candidate enrichment with Emergent LLM fallback.
Uses Groq Llama 3.3 70B → Emergent LLM → Raw text save for resilience.

Cost: $0.59/M input + $0.79/M output (cheaper output than Claude Haiku)
Speed: ~2 seconds per candidate
Quality: Excellent for structured extraction

Note: This replaces Anthropic Batch API (which was async but complex).
Groq is fast enough for sync processing at similar cost.
"""

import os
import json
import logging
from datetime import datetime, timezone
from pymongo import MongoClient

logger = logging.getLogger(__name__)

# Configuration (Groq + Emergent LLM fallback)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
BATCH_THRESHOLD = 20       # Process when queue reaches this count
MAX_BATCH_SIZE = 100       # Max candidates to process in one batch


def _get_sync_db():
    """Get sync pymongo connection (for use in background threads)."""
    mongo_url = os.environ.get("MONGO_URL", "")
    db_name = os.environ.get("DB_NAME", "vhc_talent_os")
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)
    return client[db_name]


def _build_system_prompt():
    """Same extraction prompt used by bedrock_service.extract_full_profile."""
    return """You are an expert recruitment data extraction system. You will receive raw text scraped from a Naukri.com candidate profile page which may ALSO include embedded CV/resume text from an iframe.

Your task: Extract EVERY piece of candidate information available. This is for a talent management system — completeness is critical.

CRITICAL RULES:
- The text contains BOTH the Naukri profile page text AND possibly the candidate's CV text.
- PRIORITY: The Naukri PROFILE HEADER data (at the top of the text) is the MOST CURRENT and AUTHORITATIVE source.
- CTC/Salary: Use the CTC shown in the Naukri profile header section. Convert ALL values to integer INR.
- Notice Period: Use the notice period from the profile header, NOT from the CV text.
- Phone: Indian mobile = 10 digits starting with 6-9. IGNORE the recruiter's phone.
- Email: Only the candidate's personal/work email.
- Experience: Convert to decimal years (e.g., 5 years 6 months = 5.5).
- Work history: Capture EVERY role with FULL descriptions.

Return ONLY a valid JSON object with these exact keys (use null for missing):
{
  "candidate_phone": "10-digit number or null",
  "candidate_email": "email or null",
  "candidate_name": "full name or null",
  "current_designation": "current job title or null",
  "current_employer": "current company or null",
  "current_department": "department or null",
  "current_industry": "industry or null",
  "location": "current city or null",
  "headline": "resume headline or null",
  "profile_summary": "full profile summary text or null",
  "current_ctc": integer in INR or null,
  "expected_ctc": integer in INR or null,
  "notice_period": "e.g. 1 Month, 2 Months, Immediate, or null",
  "notice_period_days": integer or null,
  "experience_years": decimal number or null,
  "key_skills": ["skill1", "skill2"],
  "work_experience": [
    {
      "company": "company name",
      "designation": "job title",
      "from_date": "start date or null",
      "to_date": "end date or null",
      "is_current": true/false,
      "description": "FULL role description"
    }
  ],
  "education": [
    {"degree": "degree", "institution": "college/university", "year": "year or null", "specialization": "field or null"}
  ],
  "certifications": ["cert1", "cert2"],
  "languages": ["language1", "language2"],
  "preferred_locations": ["city1", "city2"],
  "confidence": "high/medium/low",
  "phone_source": "where phone was found or null"
}

Do NOT include any explanation — just the JSON."""


def queue_for_batch(candidate_id: str, candidate_name: str,
                    raw_text: str, recruiter_phone: str = None,
                    recruiter_email: str = None):
    """Add a candidate to the batch enrichment queue."""
    try:
        sdb = _get_sync_db()
        sdb.batch_enrichment_queue.insert_one({
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
            "raw_text": raw_text[:15000],
            "recruiter_phone": recruiter_phone,
            "recruiter_email": recruiter_email,
            "status": "queued",
            "queued_at": datetime.now(timezone.utc),
            "batch_id": None,
        })
        count = sdb.batch_enrichment_queue.count_documents({"status": "queued"})
        logger.info(f"[BatchAPI] Queued {candidate_name} for batch enrichment. Queue size: {count}")

        # Auto-submit if threshold reached
        if count >= BATCH_THRESHOLD:
            logger.info(f"[BatchAPI] Queue threshold ({BATCH_THRESHOLD}) reached — submitting batch")
            submit_batch()
    except Exception as e:
        logger.error(f"[BatchAPI] Failed to queue {candidate_name}: {e}")


def submit_batch():
    """
    Process all queued candidates using Groq with Emergent LLM fallback.
    Processes candidates synchronously (Groq is fast enough).
    """
    if not GROQ_API_KEY and not EMERGENT_LLM_KEY:
        logger.warning("[BatchAPI] Neither GROQ_API_KEY nor EMERGENT_LLM_KEY set — skipping batch")
        return None

    try:
        import asyncio
        from services.llm_fallback_service import extract_with_fallback
        
        sdb = _get_sync_db()

        # Fetch queued items
        queued = list(sdb.batch_enrichment_queue.find(
            {"status": "queued"},
            {"_id": 0}
        ).limit(MAX_BATCH_SIZE))

        if not queued:
            logger.info("[BatchAPI] No items in queue — skipping")
            return None

        # Generate batch ID
        from uuid import uuid4
        batch_id = str(uuid4())
        
        logger.info(f"[BatchAPI] Processing batch {batch_id} with {len(queued)} candidates...")

        # Build system prompt
        system_prompt = _build_system_prompt()
        
        success_count = 0
        fail_count = 0
        fallback_count = 0

        # Process each candidate
        for item in queued:
            try:
                candidate_id = item["candidate_id"]
                candidate_name = item.get("candidate_name", "Unknown")
                
                user_msg = (
                    f"Recruiter phone to EXCLUDE: {item.get('recruiter_phone') or 'unknown'}\n"
                    f"Recruiter email to EXCLUDE: {item.get('recruiter_email') or 'unknown'}\n\n"
                    f"--- RAW PAGE + CV TEXT ---\n{item['raw_text']}"
                )
                
                # Use fallback service
                result = asyncio.run(extract_with_fallback(
                    system_prompt=system_prompt,
                    user_prompt=user_msg,
                    temperature=0,
                    max_tokens=3000,
                    context=f"Batch: {candidate_name}"
                ))
                
                if result["success"]:
                    # Apply enrichment
                    _apply_enrichment(sdb, candidate_id, result["data"])
                    success_count += 1
                    
                    if result["source"] == "emergent_llm":
                        fallback_count += 1
                        
                else:
                    # Save raw text for manual review
                    logger.warning(f"[BatchAPI] Failed {candidate_id} — saving raw text")
                    sdb.candidate_bank.update_one(
                        {"id": candidate_id},
                        {"$set": {
                            "ai_enrichment_failed": True,
                            "ai_enrichment_error": result["error"],
                            "raw_text_for_manual_review": result.get("raw_text", ""),
                            "updated_at": datetime.now(timezone.utc)
                        }}
                    )
                    fail_count += 1
                    
            except Exception as item_err:
                logger.error(f"[BatchAPI] Item processing error: {item_err}")
                fail_count += 1

        # Mark items as processed
        candidate_ids = [item["candidate_id"] for item in queued]
        sdb.batch_enrichment_queue.update_many(
            {"candidate_id": {"$in": candidate_ids}, "status": "queued"},
            {"$set": {"status": "completed", "batch_id": batch_id,
                       "completed_at": datetime.now(timezone.utc)}}
        )

        # Track the batch
        sdb.batch_jobs.insert_one({
            "batch_id": batch_id,
            "status": "completed",
            "candidate_count": len(queued),
            "candidate_ids": candidate_ids,
            "submitted_at": datetime.now(timezone.utc),
            "completed_at": datetime.now(timezone.utc),
            "results_processed": True,
            "success_count": success_count,
            "fail_count": fail_count,
            "fallback_used_count": fallback_count,
            "processing_method": "groq_with_emergent_fallback"
        })

        logger.info(f"[BatchAPI] Batch {batch_id}: {success_count} success, {fail_count} failed, {fallback_count} used fallback")
        return batch_id

    except Exception as e:
        logger.error(f"[BatchAPI] Batch submission failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def poll_and_process_batches():
    """
    Legacy function for Anthropic Batch API compatibility.
    Now deprecated — submit_batch() processes synchronously.
    """
    logger.info("[BatchAPI] poll_and_process_batches() deprecated — batches process synchronously now")
    return


def _apply_enrichment(sdb, candidate_id: str, ai: dict):
    """Apply AI-extracted data to candidate record (same logic as _background_full_groq_enrich)."""
    import re as _re

    update_fields = {}

    # Work experience
    work_exp = ai.get("work_experience")
    if work_exp and isinstance(work_exp, list) and len(work_exp) > 0:
        update_fields["work_experience"] = work_exp

    # Education
    education = ai.get("education")
    if education and isinstance(education, list) and len(education) > 0:
        update_fields["education"] = education

    # Key skills
    skills = ai.get("key_skills")
    if skills and isinstance(skills, list) and len(skills) > 0:
        update_fields["key_skills"] = skills

    # Professional fields — always overwrite on enrichment
    for field in ["current_designation", "current_employer", "current_department",
                   "current_industry", "headline", "profile_summary"]:
        val = ai.get(field)
        if val and isinstance(val, str) and val.strip():
            update_fields[field] = val.strip()

    # Location
    loc = ai.get("location")
    if loc and isinstance(loc, str) and "agnostic" not in loc.lower():
        update_fields["current_location"] = loc.strip()

    # Experience
    exp = ai.get("experience_years")
    if exp is not None:
        try:
            update_fields["total_experience_years"] = float(exp)
        except (ValueError, TypeError):
            pass

    # Phone
    phone = ai.get("candidate_phone")
    if phone:
        digits = "".join(filter(str.isdigit, str(phone)))
        if len(digits) >= 10:
            update_fields["phone"] = digits[-10:]

    # Email
    email = ai.get("candidate_email")
    if email and "@" in str(email) and not any(x in str(email).lower() for x in ["naukri", "vhc.in", "noreply"]):
        update_fields["email"] = str(email).strip().lower()

    # Certifications & languages
    for field, key in [("certifications", "certifications"), ("languages", "languages")]:
        val = ai.get(key)
        if val and isinstance(val, list):
            update_fields[field] = val

    if update_fields:
        update_fields["ai_enriched"] = True
        update_fields["ai_enrichment_source"] = "groq_batch_with_fallback"
        update_fields["ai_enriched_at"] = datetime.now(timezone.utc)
        update_fields["updated_at"] = datetime.now(timezone.utc)
        sdb.candidate_bank.update_one(
            {"id": candidate_id},
            {"$set": update_fields}
        )
        logger.info(f"[BatchAPI] Enriched {candidate_id} with {len(update_fields)} fields")


def get_batch_stats():
    """Get batch processing statistics for admin dashboard."""
    try:
        sdb = _get_sync_db()
        queued = sdb.batch_enrichment_queue.count_documents({"status": "queued"})
        submitted = sdb.batch_enrichment_queue.count_documents({"status": "submitted"})
        completed = sdb.batch_enrichment_queue.count_documents({"status": "completed"})
        batches = list(sdb.batch_jobs.find(
            {}, {"_id": 0, "batch_id": 1, "status": 1, "candidate_count": 1,
                 "submitted_at": 1, "completed_at": 1, "success_count": 1, "fail_count": 1}
        ).sort("submitted_at", -1).limit(10))
        # Convert datetime to string for JSON serialization
        for b in batches:
            for k in ["submitted_at", "completed_at"]:
                if b.get(k):
                    b[k] = b[k].isoformat()
        return {
            "queue": {"queued": queued, "submitted": submitted, "completed": completed},
            "recent_batches": batches,
        }
    except Exception as e:
        logger.error(f"[BatchAPI] Stats error: {e}")
        return {"queue": {"queued": 0, "submitted": 0, "completed": 0}, "recent_batches": []}
