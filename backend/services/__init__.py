"""
VHC Talent OS - Services Module
"""
from .r2_storage import (
    upload_to_r2,
    get_r2_signed_url,
    get_file_from_r2,
    generate_r2_key
)
from .cache import cache, CacheService
from .embeddings import embedding_service, EmbeddingService
from .job_queue import job_queue, JobQueueService, JobType, JobStatus, BackgroundJob
