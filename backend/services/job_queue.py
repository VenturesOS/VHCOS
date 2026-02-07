"""
Background Job Queue Service
Handles async processing of CV parsing, embedding generation, and bulk imports.
Uses Redis Queue (RQ) pattern with Upstash Redis.
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
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobType(str, Enum):
    CV_PARSE = "cv_parse"
    BULK_IMPORT = "bulk_import"
    EMBEDDING_GENERATE = "embedding_generate"
    BATCH_EMBEDDING = "batch_embedding"


class BackgroundJob(BaseModel):
    """Background job model."""
    id: str
    type: JobType
    status: JobStatus = JobStatus.PENDING
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_by: str
    input_data: Dict[str, Any] = {}
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    progress: int = 0  # 0-100
    progress_message: Optional[str] = None


class JobQueueService:
    """
    Background job queue service.
    Jobs are stored in MongoDB for persistence and status tracking.
    Processing is done in-process with asyncio (suitable for moderate load).
    For high load, upgrade to Celery or dedicated workers.
    """
    
    def __init__(self):
        self.db = None
        self._handlers: Dict[JobType, Callable] = {}
        self._running_jobs: Dict[str, asyncio.Task] = {}
    
    def set_db(self, db):
        """Set database connection."""
        self.db = db
    
    def register_handler(self, job_type: JobType, handler: Callable):
        """Register a handler for a job type."""
        self._handlers[job_type] = handler
        logger.info(f"Registered handler for job type: {job_type}")
    
    async def create_job(
        self,
        job_type: JobType,
        input_data: Dict[str, Any],
        created_by: str
    ) -> BackgroundJob:
        """Create a new background job."""
        job = BackgroundJob(
            id=str(uuid.uuid4()),
            type=job_type,
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by=created_by,
            input_data=input_data
        )
        
        # Store in database
        if self.db is not None:
            await self.db.background_jobs.insert_one(job.model_dump())
        
        logger.info(f"Created job: {job.id} ({job_type})")
        return job
    
    async def get_job(self, job_id: str) -> Optional[BackgroundJob]:
        """Get job by ID."""
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
        limit: int = 20
    ) -> List[BackgroundJob]:
        """Get jobs created by a user."""
        if self.db is None:
            return []
        
        query = {"created_by": user_id}
        if job_type:
            query["type"] = job_type
        
        jobs_data = await self.db.background_jobs.find(
            query, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)
        
        return [BackgroundJob(**j) for j in jobs_data]
    
    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: int = None,
        progress_message: str = None,
        result: Dict[str, Any] = None,
        error: str = None
    ):
        """Update job status."""
        if self.db is None:
            return
        
        update = {"status": status}
        
        if status == JobStatus.PROCESSING:
            update["started_at"] = datetime.now(timezone.utc).isoformat()
        elif status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            update["completed_at"] = datetime.now(timezone.utc).isoformat()
        
        if progress is not None:
            update["progress"] = progress
        if progress_message:
            update["progress_message"] = progress_message
        if result:
            update["result"] = result
        if error:
            update["error"] = error
        
        await self.db.background_jobs.update_one(
            {"id": job_id},
            {"$set": update}
        )
    
    async def process_job(self, job: BackgroundJob):
        """Process a single job."""
        handler = self._handlers.get(job.type)
        
        if not handler:
            logger.error(f"No handler for job type: {job.type}")
            await self.update_job_status(
                job.id,
                JobStatus.FAILED,
                error=f"No handler registered for job type: {job.type}"
            )
            return
        
        try:
            await self.update_job_status(job.id, JobStatus.PROCESSING)
            
            # Execute handler
            result = await handler(job, self)
            
            await self.update_job_status(
                job.id,
                JobStatus.COMPLETED,
                progress=100,
                result=result
            )
            logger.info(f"Job completed: {job.id}")
            
        except Exception as e:
            logger.error(f"Job failed: {job.id} - {e}")
            await self.update_job_status(
                job.id,
                JobStatus.FAILED,
                error=str(e)
            )
    
    async def enqueue_and_process(
        self,
        job_type: JobType,
        input_data: Dict[str, Any],
        created_by: str
    ) -> BackgroundJob:
        """Create job and start processing immediately (non-blocking)."""
        job = await self.create_job(job_type, input_data, created_by)
        
        # Start processing in background
        task = asyncio.create_task(self.process_job(job))
        self._running_jobs[job.id] = task
        
        # Cleanup when done
        task.add_done_callback(lambda t: self._running_jobs.pop(job.id, None))
        
        return job
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job."""
        task = self._running_jobs.get(job_id)
        if task and not task.done():
            task.cancel()
            await self.update_job_status(
                job_id,
                JobStatus.FAILED,
                error="Job cancelled by user"
            )
            return True
        return False


# Global job queue instance
job_queue = JobQueueService()


# ============== Job Handlers ==============

async def handle_cv_parse_job(job: BackgroundJob, queue: JobQueueService) -> Dict[str, Any]:
    """Handler for CV parsing jobs."""
    from services.matching_engine import parse_resume_with_ai
    from config import db
    
    file_path = job.input_data.get("file_path")
    file_name = job.input_data.get("file_name")
    
    await queue.update_job_status(job.id, JobStatus.PROCESSING, progress=10, progress_message="Reading file...")
    
    # Read file content
    import aiofiles
    async with aiofiles.open(file_path, 'rb') as f:
        content = await f.read()
    
    await queue.update_job_status(job.id, JobStatus.PROCESSING, progress=30, progress_message="Parsing with AI...")
    
    # Parse resume
    parse_result = await parse_resume_with_ai(content, file_name)
    
    if not parse_result.get("success"):
        raise Exception(parse_result.get("error", "Failed to parse resume"))
    
    await queue.update_job_status(job.id, JobStatus.PROCESSING, progress=70, progress_message="Storing candidate...")
    
    # Store candidate
    candidate_data = parse_result["data"]
    candidate_id = str(uuid.uuid4())
    candidate_data["id"] = candidate_id
    candidate_data["created_by"] = job.created_by
    candidate_data["created_at"] = datetime.now(timezone.utc).isoformat()
    candidate_data["source"] = "cv_upload_async"
    
    await db.candidate_bank.insert_one(candidate_data)
    
    await queue.update_job_status(job.id, JobStatus.PROCESSING, progress=90, progress_message="Generating embedding...")
    
    # Generate embedding
    from services.embeddings import process_candidate_embedding
    await process_candidate_embedding(candidate_id, candidate_data, db)
    
    return {
        "candidate_id": candidate_id,
        "candidate_name": candidate_data.get("name"),
        "skills_found": len(candidate_data.get("skills", []))
    }


async def handle_batch_embedding_job(job: BackgroundJob, queue: JobQueueService) -> Dict[str, Any]:
    """Handler for batch embedding generation."""
    from services.embeddings import batch_generate_embeddings
    from config import db
    
    # Get candidates without embeddings
    limit = job.input_data.get("limit", 1000)
    query = {"embedding": {"$exists": False}}
    if job.input_data.get("candidate_ids"):
        query["id"] = {"$in": job.input_data["candidate_ids"]}
    
    candidates = await db.candidate_bank.find(query, {"_id": 0}).to_list(limit)
    
    if not candidates:
        return {"processed": 0, "message": "No candidates need embeddings"}
    
    await queue.update_job_status(
        job.id, JobStatus.PROCESSING,
        progress=10,
        progress_message=f"Processing {len(candidates)} candidates..."
    )
    
    result = await batch_generate_embeddings(candidates, db)
    
    return {
        "total_candidates": len(candidates),
        **result
    }


async def handle_bulk_cv_parse_job(job: BackgroundJob, queue: JobQueueService) -> Dict[str, Any]:
    """
    Handler for bulk CV parsing jobs.
    Parses multiple resumes in background, creating candidates as it goes.
    """
    from services.matching_engine import parse_resume_with_ai, extract_text_from_file
    from services.r2_storage import upload_to_r2, generate_r2_key
    from services.embeddings import embedding_service
    from config import db
    import tempfile
    import zipfile
    from pathlib import Path
    
    upload_id = job.input_data.get("upload_id")
    batch_id = job.input_data.get("batch_id")
    excel_data_map = job.input_data.get("excel_data_map", {})
    
    if not upload_id:
        raise Exception("No upload_id provided")
    
    # Get the uploaded file
    from services.chunked_upload import chunked_upload_service
    
    upload = chunked_upload_service.get_upload_status(upload_id)
    if not upload or upload.status != "completed":
        raise Exception("Upload not found or not completed")
    
    file_content = chunked_upload_service.get_file_content(upload_id)
    if not file_content:
        raise Exception("Could not read uploaded file")
    
    await queue.update_job_status(job.id, JobStatus.PROCESSING, progress=5, progress_message="Extracting ZIP...")
    
    # Extract resumes from ZIP
    resume_files = []
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "upload.zip")
        with open(zip_path, 'wb') as f:
            f.write(file_content)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for file_info in zip_ref.infolist():
                if file_info.is_dir():
                    continue
                filename = os.path.basename(file_info.filename)
                ext = Path(filename).suffix.lower()
                if ext in ['.pdf', '.doc', '.docx']:
                    with zip_ref.open(file_info) as f:
                        content = f.read()
                    resume_files.append((filename, content))
    
    if not resume_files:
        raise Exception("No resume files found in ZIP")
    
    total = len(resume_files)
    await queue.update_job_status(job.id, JobStatus.PROCESSING, progress=10, 
                                   progress_message=f"Found {total} resumes. Starting parsing...")
    
    # Process each resume
    results = {"processed": 0, "failed": 0, "candidates": []}
    now = datetime.now(timezone.utc).isoformat()
    
    for idx, (filename, content) in enumerate(resume_files):
        try:
            progress = 10 + int((idx / total) * 80)
            await queue.update_job_status(
                job.id, JobStatus.PROCESSING, progress=progress,
                progress_message=f"Parsing {idx + 1}/{total}: {filename}"
            )
            
            # Upload to R2
            r2_key = generate_r2_key("bulk-import-cv", filename)
            ext = Path(filename).suffix.lower()
            content_type_map = {
                '.pdf': 'application/pdf',
                '.doc': 'application/msword',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            }
            content_type = content_type_map.get(ext, 'application/octet-stream')
            r2_result = await upload_to_r2(content, r2_key, content_type)
            
            # Extract text and parse
            resume_text = extract_text_from_file(content, filename)
            
            candidate_data = {
                "id": str(uuid.uuid4()),
                "source": "bulk_cv_async",
                "cv_attached": True,
                "resume_file_id": str(uuid.uuid4()),
                "r2_metadata": r2_result,
                "original_filename": filename,
                "created_at": now,
                "updated_at": now,
                "created_by": job.created_by,
                "bulk_import_batch_id": batch_id,
                "bulk_import_restricted": True
            }
            
            if resume_text and len(resume_text) > 100:
                parsed = await parse_resume_with_ai(resume_text[:8000])
                if parsed.get('success') and parsed.get('data'):
                    data = parsed['data']
                    candidate_data.update({
                        "name": data.get('name'),
                        "email": data.get('email'),
                        "phone": data.get('phone'),
                        "location": data.get('location'),
                        "experience_years": data.get('experience_years', 0) or 0,
                        "skills": data.get('skills', []),
                        "headline": data.get('headline'),
                        "summary": data.get('summary'),
                        "experience": data.get('experience', []),
                        "education": data.get('education', [])
                    })
            
            # Merge with Excel data if available
            email = candidate_data.get("email", "").lower() if candidate_data.get("email") else None
            if email and email in excel_data_map:
                excel_row = excel_data_map[email]
                if not candidate_data.get("name") and excel_row.get("name"):
                    candidate_data["name"] = excel_row["name"]
                if not candidate_data.get("location") and excel_row.get("location"):
                    candidate_data["location"] = excel_row["location"]
                if excel_row.get("salary"):
                    candidate_data["current_salary"] = excel_row["salary"]
            
            # Validate
            if not candidate_data.get("name"):
                candidate_data["name"] = f"Candidate from {filename}"
            
            # Save to database
            await db.candidate_bank.insert_one(candidate_data)
            
            # Generate embedding (non-blocking)
            try:
                embedding = await embedding_service.generate_candidate_embedding(candidate_data)
                if embedding:
                    await db.candidate_bank.update_one(
                        {"id": candidate_data["id"]},
                        {"$set": {"embedding": embedding, "embedding_updated_at": now}}
                    )
            except Exception as emb_err:
                logger.warning(f"Embedding failed for {candidate_data['id']}: {emb_err}")
            
            results["processed"] += 1
            results["candidates"].append({
                "id": candidate_data["id"],
                "name": candidate_data.get("name"),
                "email": candidate_data.get("email")
            })
            
        except Exception as e:
            logger.error(f"Failed to parse {filename}: {e}")
            results["failed"] += 1
    
    # Update batch record
    await db.bulk_import_batches.update_one(
        {"id": batch_id},
        {"$set": {
            "status": "completed",
            "processed_count": results["processed"],
            "failed_count": results["failed"],
            "completed_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Cleanup upload
    chunked_upload_service.cleanup_completed(upload_id)
    
    await queue.update_job_status(job.id, JobStatus.PROCESSING, progress=95,
                                   progress_message="Finalizing...")
    
    return results


# Register handlers when module is imported
def register_default_handlers():
    """Register default job handlers."""
    job_queue.register_handler(JobType.CV_PARSE, handle_cv_parse_job)
    job_queue.register_handler(JobType.BATCH_EMBEDDING, handle_batch_embedding_job)
    job_queue.register_handler(JobType.BULK_IMPORT, handle_bulk_cv_parse_job)


# Auto-register on import
register_default_handlers()
