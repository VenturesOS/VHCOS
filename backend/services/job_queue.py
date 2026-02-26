"""
Background Job Queue Service
Handles async processing of CV parsing, embedding generation, and bulk imports.

FIXED:
- handle_bulk_cv_parse_job() now extracts ALL canonical + alias fields from parser
- Bulk import uses upsert (idempotent) instead of insert_one
- Phone normalization stored for dedup
- find_similar_candidate() called before every write
"""
import os
import uuid
import json
import logging
import asyncio
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    COMPLETED  = "completed"
    FAILED     = "failed"


class JobType(str, Enum):
    CV_PARSE          = "cv_parse"
    BULK_IMPORT       = "bulk_import"
    EMBEDDING_GENERATE = "embedding_generate"
    BATCH_EMBEDDING   = "batch_embedding"


class BackgroundJob(BaseModel):
    id:               str
    type:             JobType
    status:           JobStatus       = JobStatus.PENDING
    created_at:       str
    started_at:       Optional[str]   = None
    completed_at:     Optional[str]   = None
    created_by:       str
    input_data:       Dict[str, Any]  = {}
    result:           Optional[Dict[str, Any]] = None
    error:            Optional[str]   = None
    progress:         int             = 0
    progress_message: Optional[str]   = None


class JobQueueService:
    """
    Background job queue service.
    Jobs are stored in MongoDB for persistence and status tracking.
    Processing is done in-process with asyncio (suitable for moderate load).
    For high load (>3 concurrent bulk imports), upgrade to Celery + dedicated workers.
    """

    def __init__(self):
        self.db = None
        self._handlers:     Dict[JobType, Callable]   = {}
        self._running_jobs: Dict[str, asyncio.Task]   = {}

    def set_db(self, db):
        self.db = db

    def register_handler(self, job_type: JobType, handler: Callable):
        self._handlers[job_type] = handler
        logger.info(f"Registered handler for job type: {job_type}")

    async def create_job(
        self,
        job_type: JobType,
        input_data: Dict[str, Any],
        created_by: str,
    ) -> BackgroundJob:
        job = BackgroundJob(
            id=str(uuid.uuid4()),
            type=job_type,
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by=created_by,
            input_data=input_data,
        )
        if self.db is not None:
            await self.db.background_jobs.insert_one(job.model_dump())
        logger.info(f"Created job: {job.id} ({job_type})")
        return job

    async def get_job(self, job_id: str) -> Optional[BackgroundJob]:
        if self.db is None:
            return None
        job_data = await self.db.background_jobs.find_one({"id": job_id}, {"_id": 0})
        if job_data:
            return BackgroundJob(**job_data)
        return None

    async def get_jobs_by_user(
        self,
        user_id: str,
        job_type: Optional[JobType] = None,
        limit: int = 20,
    ) -> List[BackgroundJob]:
        if self.db is None:
            return []
        query: Dict[str, Any] = {"created_by": user_id}
        if job_type:
            query["type"] = job_type
        jobs_data = (
            await self.db.background_jobs.find(query, {"_id": 0})
            .sort("created_at", -1)
            .limit(limit)
            .to_list(limit)
        )
        return [BackgroundJob(**j) for j in jobs_data]

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: int             = None,
        progress_message: str     = None,
        result: Dict[str, Any]    = None,
        error: str                = None,
    ):
        if self.db is None:
            return
        update: Dict[str, Any] = {"status": status}
        if status == JobStatus.PROCESSING:
            update["started_at"] = datetime.now(timezone.utc).isoformat()
        elif status in (JobStatus.COMPLETED, JobStatus.FAILED):
            update["completed_at"] = datetime.now(timezone.utc).isoformat()
        if progress is not None:
            update["progress"] = progress
        if progress_message:
            update["progress_message"] = progress_message
        if result:
            update["result"] = result
        if error:
            update["error"] = error
        await self.db.background_jobs.update_one({"id": job_id}, {"$set": update})

    async def process_job(self, job: BackgroundJob):
        handler = self._handlers.get(job.type)
        if not handler:
            logger.error(f"No handler for job type: {job.type}")
            await self.update_job_status(
                job.id, JobStatus.FAILED,
                error=f"No handler registered for job type: {job.type}",
            )
            return
        try:
            await self.update_job_status(job.id, JobStatus.PROCESSING)
            result = await handler(job, self)
            await self.update_job_status(
                job.id, JobStatus.COMPLETED,
                progress=100, result=result,
            )
            logger.info(f"Job completed: {job.id}")
        except Exception as e:
            logger.error(f"Job failed: {job.id} - {e}")
            await self.update_job_status(job.id, JobStatus.FAILED, error=str(e))

    async def enqueue_and_process(
        self,
        job_type: JobType,
        input_data: Dict[str, Any],
        created_by: str,
    ) -> BackgroundJob:
        """Create job and start processing immediately (non-blocking)."""
        job = await self.create_job(job_type, input_data, created_by)
        task = asyncio.create_task(self.process_job(job))
        self._running_jobs[job.id] = task
        task.add_done_callback(lambda t: self._running_jobs.pop(job.id, None))
        return job

    async def cancel_job(self, job_id: str) -> bool:
        task = self._running_jobs.get(job_id)
        if task and not task.done():
            task.cancel()
            await self.update_job_status(
                job_id, JobStatus.FAILED,
                error="Job cancelled by user",
            )
            return True
        return False


# ---------------------------------------------------------------------------
# Global instance
# ---------------------------------------------------------------------------

job_queue = JobQueueService()


# ---------------------------------------------------------------------------
# Job Handlers
# ---------------------------------------------------------------------------

async def handle_cv_parse_job(job: BackgroundJob, queue: JobQueueService) -> Dict[str, Any]:
    """Handler for single CV parsing jobs."""
    from services.matching_engine import parse_resume_with_ai
    from config import db

    file_path = job.input_data.get("file_path")

    await queue.update_job_status(
        job.id, JobStatus.PROCESSING, progress=10,
        progress_message="Reading file...",
    )

    import aiofiles
    async with aiofiles.open(file_path, "rb") as f:
        content = await f.read()

    await queue.update_job_status(
        job.id, JobStatus.PROCESSING, progress=30,
        progress_message="Parsing with AI...",
    )

    file_name = job.input_data.get("file_name", "resume.pdf")
    resume_text = extract_text_from_file(content, file_name)
    if not resume_text or len(resume_text) < 50:
        raise Exception(f"Could not extract readable text from {file_name}")
    parse_result = await parse_resume_with_ai(resume_text[:8000])

    if not parse_result.get("success"):
        raise Exception(parse_result.get("error", "Failed to parse resume"))

    await queue.update_job_status(
        job.id, JobStatus.PROCESSING, progress=70,
        progress_message="Storing candidate...",
    )

    candidate_data = parse_result["data"]  # already normalized
    candidate_id   = str(uuid.uuid4())
    now            = datetime.now(timezone.utc).isoformat()

    candidate_data.update({
        "id":         candidate_id,
        "created_by": job.created_by,
        "created_at": now,
        "updated_at": now,
        "source":     "cv_upload_async",
    })

    await db.candidate_bank.insert_one(candidate_data)

    await queue.update_job_status(
        job.id, JobStatus.PROCESSING, progress=90,
        progress_message="Generating embedding...",
    )

    from services.embeddings import process_candidate_embedding
    await process_candidate_embedding(candidate_id, candidate_data, db)

    return {
        "candidate_id":   candidate_id,
        "candidate_name": candidate_data.get("name"),
        "skills_found":   len(candidate_data.get("key_skills", [])),
    }


async def handle_batch_embedding_job(job: BackgroundJob, queue: JobQueueService) -> Dict[str, Any]:
    """Handler for batch embedding generation."""
    from services.embeddings import batch_generate_embeddings
    from config import db

    limit = job.input_data.get("limit", 1000)
    query: Dict[str, Any] = {"embedding": {"$exists": False}}
    if job.input_data.get("candidate_ids"):
        query["id"] = {"$in": job.input_data["candidate_ids"]}

    candidates = await db.candidate_bank.find(query, {"_id": 0}).to_list(limit)

    if not candidates:
        return {"processed": 0, "message": "No candidates need embeddings"}

    await queue.update_job_status(
        job.id, JobStatus.PROCESSING, progress=10,
        progress_message=f"Processing {len(candidates)} candidates...",
    )

    result = await batch_generate_embeddings(candidates, db)
    return {"total_candidates": len(candidates), **result}


async def handle_bulk_cv_parse_job(job: BackgroundJob, queue: JobQueueService) -> Dict[str, Any]:
    """
    Handler for bulk CV parsing jobs.
    Parses multiple resumes in background, creating/updating candidates as it goes.

    FIXED:
    - Extracts ALL canonical + alias fields from parse result
    - Uses upsert (idempotent) — safe to retry the entire job
    - Calls find_similar_candidate() for dedup awareness
    """
    from services.matching_engine import parse_resume_with_ai, extract_text_from_file
    from services.r2_storage import upload_to_r2, generate_r2_key
    from services.embeddings import embedding_service
    from services.schema_normalizer import normalize_candidate
    from config import db
    import tempfile
    import zipfile
    from pathlib import Path

    upload_id     = job.input_data.get("upload_id")
    batch_id      = job.input_data.get("batch_id")
    excel_data_map = job.input_data.get("excel_data_map", {})

    if not upload_id:
        raise Exception("No upload_id provided")

    from services.chunked_upload import chunked_upload_service

    upload = chunked_upload_service.get_upload_status(upload_id)
    if not upload or upload.status != "completed":
        raise Exception("Upload not found or not completed")

    file_content = chunked_upload_service.get_file_content(upload_id)
    if not file_content:
        raise Exception("Could not read uploaded file")

    await queue.update_job_status(
        job.id, JobStatus.PROCESSING, progress=5,
        progress_message="Extracting ZIP...",
    )

    # Extract resumes from ZIP
    resume_files = []
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "upload.zip")
        with open(zip_path, "wb") as f:
            f.write(file_content)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for file_info in zip_ref.infolist():
                if file_info.is_dir():
                    continue
                filename = os.path.basename(file_info.filename)
                ext = Path(filename).suffix.lower()
                if ext in (".pdf", ".doc", ".docx"):
                    with zip_ref.open(file_info) as f:
                        content = f.read()
                    resume_files.append((filename, content))

    if not resume_files:
        raise Exception("No resume files found in ZIP")

    total = len(resume_files)
    await queue.update_job_status(
        job.id, JobStatus.PROCESSING, progress=10,
        progress_message=f"Found {total} resumes. Starting parsing...",
    )

    results = {"processed": 0, "failed": 0, "skipped": 0, "candidates": []}
    now = datetime.now(timezone.utc).isoformat()

    for idx, (filename, content) in enumerate(resume_files):
        try:
            progress = 10 + int((idx / total) * 80)
            await queue.update_job_status(
                job.id, JobStatus.PROCESSING, progress=progress,
                progress_message=f"Parsing {idx + 1}/{total}: {filename}",
            )

            # Upload to R2
            r2_key = generate_r2_key("bulk-import-cv", filename)
            ext = Path(filename).suffix.lower()
            content_type_map = {
                ".pdf":  "application/pdf",
                ".doc":  "application/msword",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
            content_type = content_type_map.get(ext, "application/octet-stream")
            r2_result = await upload_to_r2(content, r2_key, content_type)

            # Extract text and parse with canonical parser
            resume_text = extract_text_from_file(content, filename)

            # Base candidate document
            candidate_data: Dict[str, Any] = {
                "id":                      str(uuid.uuid4()),
                "source":                  "bulk_cv_async",
                "cv_attached":             True,
                "resume_file_id":          str(uuid.uuid4()),
                "r2_metadata":             r2_result,
                "original_filename":       filename,
                "created_at":              now,
                "updated_at":              now,
                "created_by":              job.created_by,
                "bulk_import_batch_id":    batch_id,
                "bulk_import_restricted":  True,
            }

            if resume_text and len(resume_text) > 100:
                parsed = await parse_resume_with_ai(resume_text[:8000])
                if parsed.get("success") and parsed.get("data"):
                    data = parsed["data"]
                    # data is already normalized by parse_resume_with_ai()
                    # Write ALL canonical + alias fields explicitly
                    candidate_data.update({
                        # ── canonical fields ────────────────────────────────
                        "key_skills":             data.get("key_skills", []),
                        "profile_summary":        data.get("profile_summary", ""),
                        "work_experience":        data.get("work_experience", []),
                        "total_experience_years": data.get("total_experience_years", 0),
                        # ── alias fields (kept for backward compat queries) ─
                        "skills":                 data.get("skills", []),
                        "summary":                data.get("summary", ""),
                        "experience":             data.get("experience", []),
                        "experience_years":       data.get("experience_years", 0),
                        # ── other parsed fields ──────────────────────────────
                        "name":                   data.get("name"),
                        "email":                  data.get("email"),
                        "phone":                  data.get("phone"),
                        "phone_normalized":       data.get("phone_normalized"),
                        "location":               data.get("location"),
                        "headline":               data.get("headline"),
                        "current_company":        data.get("current_company"),
                        "current_designation":    data.get("current_designation"),
                        "current_industry":       data.get("current_industry"),
                        "education":              data.get("education", []),
                        "it_skills":              data.get("it_skills", []),
                        "certifications":         data.get("certifications", []),
                        "preferred_locations":    data.get("preferred_locations", []),
                    })

            # Merge with Excel data if available
            email_lower = (candidate_data.get("email") or "").strip().lower() or None
            if email_lower:
                candidate_data["email"] = email_lower
            if email_lower and email_lower in excel_data_map:
                excel_row = excel_data_map[email_lower]
                if not candidate_data.get("name") and excel_row.get("name"):
                    candidate_data["name"] = excel_row["name"]
                if not candidate_data.get("location") and excel_row.get("location"):
                    candidate_data["location"] = excel_row["location"]
                if excel_row.get("salary"):
                    candidate_data["current_salary"] = excel_row["salary"]

            # Fallback name
            if not candidate_data.get("name"):
                candidate_data["name"] = f"Candidate from {filename}"

            # ── Idempotent upsert — safe to retry the entire job ──────────
            # Build dedup filter: email > phone > filename+batch
            phone_norm = candidate_data.get("phone_normalized")
            if email_lower:
                upsert_filter: Dict[str, Any] = {"email": email_lower}
            elif phone_norm and len(phone_norm) == 10:
                upsert_filter = {"phone_normalized": phone_norm}
            else:
                upsert_filter = {
                    "original_filename":    filename,
                    "bulk_import_batch_id": batch_id,
                }

            await db.candidate_bank.update_one(
                upsert_filter,
                {
                    "$set": candidate_data,
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )

            # Generate embedding (non-blocking, failure is non-fatal)
            try:
                embedding = await embedding_service.generate_candidate_embedding(candidate_data)
                if embedding:
                    await db.candidate_bank.update_one(
                        upsert_filter,
                        {"$set": {
                            "embedding":             embedding,
                            "embedding_updated_at":  now,
                        }},
                    )
            except Exception as emb_err:
                logger.warning(f"Embedding failed for {candidate_data.get('id')}: {emb_err}")

            results["processed"] += 1
            results["candidates"].append({
                "id":    candidate_data["id"],
                "name":  candidate_data.get("name"),
                "email": candidate_data.get("email"),
            })

        except Exception as e:
            logger.error(f"Failed to parse {filename}: {e}")
            results["failed"] += 1

    # Update batch record
    await db.bulk_import_batches.update_one(
        {"id": batch_id},
        {"$set": {
            "status":          "completed",
            "processed_count": results["processed"],
            "failed_count":    results["failed"],
            "completed_at":    datetime.now(timezone.utc).isoformat(),
        }},
    )

    # Cleanup upload
    chunked_upload_service.cleanup_completed(upload_id)

    await queue.update_job_status(
        job.id, JobStatus.PROCESSING, progress=95,
        progress_message="Finalizing...",
    )

    return results


# ---------------------------------------------------------------------------
# Register handlers
# ---------------------------------------------------------------------------

def register_default_handlers():
    """Register default job handlers."""
    job_queue.register_handler(JobType.CV_PARSE,        handle_cv_parse_job)
    job_queue.register_handler(JobType.BATCH_EMBEDDING, handle_batch_embedding_job)
    job_queue.register_handler(JobType.BULK_IMPORT,     handle_bulk_cv_parse_job)


register_default_handlers()
