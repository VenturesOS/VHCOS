"""
Chunked File Upload Service
Handles large file uploads by splitting them into smaller chunks.
Bypasses proxy limits and provides progress tracking.
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

# Configuration
CHUNK_SIZE = 512 * 1024  # 512KB chunks (safe for most proxies)
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB max total file size
UPLOAD_TIMEOUT_MINUTES = 30  # Auto-cleanup incomplete uploads after 30 min
TEMP_UPLOAD_DIR = Path("/tmp/chunked_uploads")

# Ensure temp directory exists
TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class ChunkedUpload(BaseModel):
    """Represents an in-progress chunked upload."""
    upload_id: str
    filename: str
    total_size: int
    total_chunks: int
    chunks_received: int = 0
    chunks_uploaded: list = []
    created_at: str
    created_by: str
    status: str = "in_progress"  # in_progress, completed, failed, expired
    file_path: Optional[str] = None


# In-memory store for active uploads (use Redis in production for multi-instance)
_active_uploads: Dict[str, ChunkedUpload] = {}


class ChunkedUploadService:
    """Service for managing chunked file uploads."""
    
    def __init__(self):
        self.uploads = _active_uploads
        self.temp_dir = TEMP_UPLOAD_DIR
    
    def initiate_upload(
        self,
        filename: str,
        total_size: int,
        total_chunks: int,
        created_by: str
    ) -> ChunkedUpload:
        """
        Initialize a new chunked upload session.
        Returns upload_id to use for subsequent chunk uploads.
        """
        # Validate file size
        if total_size > MAX_FILE_SIZE:
            raise ValueError(f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB")
        
        upload_id = str(uuid.uuid4())
        
        # Create directory for this upload's chunks
        upload_dir = self.temp_dir / upload_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        upload = ChunkedUpload(
            upload_id=upload_id,
            filename=filename,
            total_size=total_size,
            total_chunks=total_chunks,
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by=created_by
        )
        
        self.uploads[upload_id] = upload
        logger.info(f"[CHUNKED UPLOAD] Initiated: {upload_id} - {filename} ({total_size} bytes, {total_chunks} chunks)")
        
        return upload
    
    async def upload_chunk(
        self,
        upload_id: str,
        chunk_index: int,
        chunk_data: bytes
    ) -> Dict[str, Any]:
        """
        Upload a single chunk of the file.
        Returns progress information.
        """
        if upload_id not in self.uploads:
            raise ValueError("Upload session not found or expired")
        
        upload = self.uploads[upload_id]
        
        if upload.status != "in_progress":
            raise ValueError(f"Upload is {upload.status}, cannot add chunks")
        
        if chunk_index in upload.chunks_uploaded:
            # Chunk already uploaded (retry), skip
            return {
                "chunk_index": chunk_index,
                "chunks_received": upload.chunks_received,
                "total_chunks": upload.total_chunks,
                "progress": round(upload.chunks_received / upload.total_chunks * 100, 1),
                "status": "already_uploaded"
            }
        
        # Save chunk to disk
        chunk_path = self.temp_dir / upload_id / f"chunk_{chunk_index:06d}"
        with open(chunk_path, 'wb') as f:
            f.write(chunk_data)
        
        upload.chunks_uploaded.append(chunk_index)
        upload.chunks_received = len(upload.chunks_uploaded)
        
        progress = round(upload.chunks_received / upload.total_chunks * 100, 1)
        logger.debug(f"[CHUNKED UPLOAD] {upload_id} - Chunk {chunk_index + 1}/{upload.total_chunks} ({progress}%)")
        
        return {
            "chunk_index": chunk_index,
            "chunks_received": upload.chunks_received,
            "total_chunks": upload.total_chunks,
            "progress": progress,
            "status": "uploaded"
        }
    
    async def complete_upload(self, upload_id: str) -> Dict[str, Any]:
        """
        Complete the upload by combining all chunks.
        Returns the path to the assembled file.
        """
        if upload_id not in self.uploads:
            raise ValueError("Upload session not found or expired")
        
        upload = self.uploads[upload_id]
        
        # Verify all chunks received
        if upload.chunks_received < upload.total_chunks:
            missing = upload.total_chunks - upload.chunks_received
            raise ValueError(f"Upload incomplete. Missing {missing} chunks")
        
        # Combine chunks into final file
        upload_dir = self.temp_dir / upload_id
        final_path = self.temp_dir / f"{upload_id}_{upload.filename}"
        
        try:
            with open(final_path, 'wb') as outfile:
                for i in range(upload.total_chunks):
                    chunk_path = upload_dir / f"chunk_{i:06d}"
                    if not chunk_path.exists():
                        raise ValueError(f"Chunk {i} missing during assembly")
                    with open(chunk_path, 'rb') as chunk_file:
                        outfile.write(chunk_file.read())
            
            # Verify final file size
            actual_size = final_path.stat().st_size
            if actual_size != upload.total_size:
                logger.warning(f"[CHUNKED UPLOAD] Size mismatch: expected {upload.total_size}, got {actual_size}")
            
            # Update upload status
            upload.status = "completed"
            upload.file_path = str(final_path)
            
            # Cleanup chunk directory
            shutil.rmtree(upload_dir, ignore_errors=True)
            
            logger.info(f"[CHUNKED UPLOAD] Completed: {upload_id} - {upload.filename} ({actual_size} bytes)")
            
            return {
                "upload_id": upload_id,
                "filename": upload.filename,
                "file_path": str(final_path),
                "size": actual_size,
                "status": "completed"
            }
            
        except Exception as e:
            upload.status = "failed"
            logger.error(f"[CHUNKED UPLOAD] Failed to assemble {upload_id}: {e}")
            raise ValueError(f"Failed to assemble file: {str(e)}")
    
    def get_upload_status(self, upload_id: str) -> Optional[ChunkedUpload]:
        """Get the current status of an upload."""
        return self.uploads.get(upload_id)
    
    def cancel_upload(self, upload_id: str) -> bool:
        """Cancel and cleanup an upload."""
        if upload_id not in self.uploads:
            return False
        
        upload = self.uploads[upload_id]
        upload.status = "cancelled"
        
        # Cleanup files
        upload_dir = self.temp_dir / upload_id
        if upload_dir.exists():
            shutil.rmtree(upload_dir, ignore_errors=True)
        
        if upload.file_path and Path(upload.file_path).exists():
            Path(upload.file_path).unlink(missing_ok=True)
        
        del self.uploads[upload_id]
        logger.info(f"[CHUNKED UPLOAD] Cancelled: {upload_id}")
        return True
    
    def cleanup_expired(self) -> int:
        """Remove expired uploads. Call periodically."""
        expired_count = 0
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=UPLOAD_TIMEOUT_MINUTES)
        
        expired_ids = []
        for upload_id, upload in self.uploads.items():
            created = datetime.fromisoformat(upload.created_at.replace('Z', '+00:00'))
            if created < cutoff and upload.status == "in_progress":
                expired_ids.append(upload_id)
        
        for upload_id in expired_ids:
            self.cancel_upload(upload_id)
            expired_count += 1
        
        if expired_count > 0:
            logger.info(f"[CHUNKED UPLOAD] Cleaned up {expired_count} expired uploads")
        
        return expired_count
    
    def get_file_content(self, upload_id: str) -> Optional[bytes]:
        """Read the completed file content."""
        upload = self.uploads.get(upload_id)
        if not upload or upload.status != "completed" or not upload.file_path:
            return None
        
        file_path = Path(upload.file_path)
        if not file_path.exists():
            return None
        
        with open(file_path, 'rb') as f:
            return f.read()
    
    def cleanup_completed(self, upload_id: str):
        """Cleanup a completed upload after processing."""
        upload = self.uploads.get(upload_id)
        if upload and upload.file_path:
            Path(upload.file_path).unlink(missing_ok=True)
        if upload_id in self.uploads:
            del self.uploads[upload_id]


# Global instance
chunked_upload_service = ChunkedUploadService()
