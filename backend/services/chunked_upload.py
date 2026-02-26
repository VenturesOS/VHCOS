"""
Chunked File Upload Service
Handles large file uploads by splitting them into smaller chunks.
Bypasses proxy limits and provides progress tracking.

FIXED:
- Upload sessions stored in Redis (via CacheService) instead of a
  module-level dict — process-safe across all Gunicorn workers.
- Any worker can handle any chunk regardless of which worker started
  the session.
- Graceful degradation: if Redis is unavailable, falls back to a
  module-level dict with a warning (single-worker environments only).
"""
import os
import uuid
import shutil
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

CHUNK_SIZE            = 512 * 1024        # 512 KB — safe for most proxies
MAX_FILE_SIZE         = 100 * 1024 * 1024 # 100 MB
UPLOAD_TIMEOUT_MINUTES = 30
UPLOAD_SESSION_TTL    = UPLOAD_TIMEOUT_MINUTES * 60  # seconds
TEMP_UPLOAD_DIR       = Path("/tmp/chunked_uploads")

TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class ChunkedUpload(BaseModel):
    """Represents an in-progress chunked upload."""
    upload_id:       str
    filename:        str
    total_size:      int
    total_chunks:    int
    chunks_received: int   = 0
    chunks_uploaded: list  = []
    created_at:      str
    created_by:      str
    status:          str   = "in_progress"
    file_path:       Optional[str] = None


# ---------------------------------------------------------------------------
# Session storage backend — Redis-first, dict fallback
# ---------------------------------------------------------------------------

# Fallback in-memory store (only used when Redis is unavailable).
# WARN: this is NOT process-safe under multi-worker deployments.
_fallback_store: Dict[str, Dict] = {}


def _session_key(upload_id: str) -> str:
    return f"chunked_upload:{upload_id}"


def _session_get(upload_id: str) -> Optional[ChunkedUpload]:
    key = _session_key(upload_id)
    try:
        from services.cache import cache
        if cache.enabled:
            data = cache.get(key)
            if data:
                return ChunkedUpload(**data)
            return None
    except Exception:
        pass
    # Fallback to in-memory dict
    data = _fallback_store.get(key)
    if data:
        return ChunkedUpload(**data)
    return None


def _session_set(upload: ChunkedUpload) -> None:
    key = _session_key(upload.upload_id)
    try:
        from services.cache import cache
        if cache.enabled:
            cache.set(key, upload.model_dump(), ttl=UPLOAD_SESSION_TTL)
            return
    except Exception:
        pass
    # Fallback — warn once per process start
    if key not in _fallback_store:
        logger.warning(
            "Redis unavailable — chunked upload sessions stored in-memory. "
            "Multi-worker deployments will break. Configure UPSTASH_REDIS_REST_URL."
        )
    _fallback_store[key] = upload.model_dump()


def _session_delete(upload_id: str) -> None:
    key = _session_key(upload_id)
    try:
        from services.cache import cache
        if cache.enabled:
            cache.delete(key)
            return
    except Exception:
        pass
    _fallback_store.pop(key, None)


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------

class ChunkedUploadService:
    """Service for managing chunked file uploads."""

    def __init__(self):
        self.temp_dir = TEMP_UPLOAD_DIR

    # ── Public API ────────────────────────────────────────────────────────

    def initiate_upload(
        self,
        filename:     str,
        total_size:   int,
        total_chunks: int,
        created_by:   str,
    ) -> ChunkedUpload:
        """
        Initialize a new chunked upload session.
        Returns upload_id to use for subsequent chunk uploads.
        Session stored in Redis (process-safe).
        """
        if total_size > MAX_FILE_SIZE:
            raise ValueError(
                f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)} MB"
            )

        upload_id  = str(uuid.uuid4())
        upload_dir = self.temp_dir / upload_id
        upload_dir.mkdir(parents=True, exist_ok=True)

        upload = ChunkedUpload(
            upload_id=upload_id,
            filename=filename,
            total_size=total_size,
            total_chunks=total_chunks,
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by=created_by,
        )
        _session_set(upload)
        logger.info(
            f"[CHUNKED UPLOAD] Initiated: {upload_id} — {filename} "
            f"({total_size} bytes, {total_chunks} chunks)"
        )
        return upload

    async def upload_chunk(
        self,
        upload_id:   str,
        chunk_index: int,
        chunk_data:  bytes,
    ) -> Dict[str, Any]:
        """
        Upload a single chunk.
        Idempotent: re-uploading the same chunk_index is safe.
        Any worker can handle any chunk (session is in Redis).
        """
        upload = _session_get(upload_id)
        if not upload:
            raise ValueError("Upload session not found or expired")
        if upload.status != "in_progress":
            raise ValueError(f"Upload is {upload.status}, cannot add chunks")

        if chunk_index in upload.chunks_uploaded:
            return {
                "chunk_index":     chunk_index,
                "chunks_received": upload.chunks_received,
                "total_chunks":    upload.total_chunks,
                "progress":        round(upload.chunks_received / upload.total_chunks * 100, 1),
                "status":          "already_uploaded",
            }

        # Write chunk to temp file
        chunk_path = self.temp_dir / upload_id / f"chunk_{chunk_index:06d}"
        with open(chunk_path, "wb") as f:
            f.write(chunk_data)

        upload.chunks_uploaded.append(chunk_index)
        upload.chunks_received = len(upload.chunks_uploaded)
        _session_set(upload)  # persist updated state

        progress = round(upload.chunks_received / upload.total_chunks * 100, 1)
        logger.debug(
            f"[CHUNKED UPLOAD] {upload_id} — "
            f"Chunk {chunk_index + 1}/{upload.total_chunks} ({progress}%)"
        )
        return {
            "chunk_index":     chunk_index,
            "chunks_received": upload.chunks_received,
            "total_chunks":    upload.total_chunks,
            "progress":        progress,
            "status":          "uploaded",
        }

    async def complete_upload(self, upload_id: str) -> Dict[str, Any]:
        """
        Complete the upload by assembling all chunks into the final file.
        Returns path to the assembled file.
        """
        upload = _session_get(upload_id)
        if not upload:
            raise ValueError("Upload session not found or expired")

        if upload.chunks_received < upload.total_chunks:
            missing = upload.total_chunks - upload.chunks_received
            raise ValueError(f"Upload incomplete. Missing {missing} chunks")

        upload_dir = self.temp_dir / upload_id
        final_path = self.temp_dir / f"{upload_id}_{upload.filename}"

        try:
            with open(final_path, "wb") as outfile:
                for i in range(upload.total_chunks):
                    chunk_path = upload_dir / f"chunk_{i:06d}"
                    if not chunk_path.exists():
                        raise ValueError(f"Chunk {i} missing during assembly")
                    outfile.write(chunk_path.read_bytes())

            actual_size = final_path.stat().st_size
            if actual_size != upload.total_size:
                logger.warning(
                    f"[CHUNKED UPLOAD] Size mismatch: "
                    f"expected {upload.total_size}, got {actual_size}"
                )

            upload.status    = "completed"
            upload.file_path = str(final_path)
            _session_set(upload)

            shutil.rmtree(upload_dir, ignore_errors=True)

            logger.info(
                f"[CHUNKED UPLOAD] Completed: {upload_id} — "
                f"{upload.filename} ({actual_size} bytes)"
            )
            return {
                "upload_id": upload_id,
                "filename":  upload.filename,
                "file_path": str(final_path),
                "size":      actual_size,
                "status":    "completed",
            }

        except Exception as e:
            upload.status = "failed"
            _session_set(upload)
            logger.error(f"[CHUNKED UPLOAD] Assembly failed {upload_id}: {e}")
            raise ValueError(f"Failed to assemble file: {str(e)}")

    def get_upload_status(self, upload_id: str) -> Optional[ChunkedUpload]:
        """Get the current status of an upload."""
        return _session_get(upload_id)

    def cancel_upload(self, upload_id: str) -> bool:
        """Cancel and clean up an upload."""
        upload = _session_get(upload_id)
        if not upload:
            return False

        # Cleanup temp files
        upload_dir = self.temp_dir / upload_id
        if upload_dir.exists():
            shutil.rmtree(upload_dir, ignore_errors=True)
        if upload.file_path:
            Path(upload.file_path).unlink(missing_ok=True)

        _session_delete(upload_id)
        logger.info(f"[CHUNKED UPLOAD] Cancelled: {upload_id}")
        return True

    def get_file_content(self, upload_id: str) -> Optional[bytes]:
        """Read the completed file content."""
        upload = _session_get(upload_id)
        if not upload or upload.status != "completed" or not upload.file_path:
            return None
        fp = Path(upload.file_path)
        return fp.read_bytes() if fp.exists() else None

    def cleanup_completed(self, upload_id: str) -> None:
        """Clean up a completed upload after processing."""
        upload = _session_get(upload_id)
        if upload and upload.file_path:
            Path(upload.file_path).unlink(missing_ok=True)
        _session_delete(upload_id)

    def cleanup_expired(self) -> int:
        """
        Remove expired in-progress uploads from fallback store.
        Redis entries expire automatically via TTL.
        Call periodically for the fallback path.
        """
        expired_count = 0
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=UPLOAD_TIMEOUT_MINUTES)
        expired_ids = []

        for key, data in list(_fallback_store.items()):
            try:
                created = datetime.fromisoformat(
                    data["created_at"].replace("Z", "+00:00")
                )
                if created < cutoff and data.get("status") == "in_progress":
                    upload_id = data.get("upload_id", "")
                    expired_ids.append(upload_id)
            except Exception:
                pass

        for upload_id in expired_ids:
            self.cancel_upload(upload_id)
            expired_count += 1

        if expired_count > 0:
            logger.info(f"[CHUNKED UPLOAD] Cleaned up {expired_count} expired uploads")

        return expired_count


# Global instance
chunked_upload_service = ChunkedUploadService()
