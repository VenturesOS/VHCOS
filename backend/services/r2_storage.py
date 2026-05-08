"""
VHC Talent OS - Cloudflare R2 Storage Service
Handles file upload, download, and signed URL generation for R2 object storage.

C-03 FIX: All boto3 calls wrapped in run_in_executor() to avoid blocking
the async event loop. Each call runs in the default ThreadPoolExecutor.
"""
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timezone
import uuid
import aiofiles

from config import (
    r2_client,
    R2_ENABLED,
    R2_BUCKET_NAME,
    UPLOAD_DIR
)

logger = logging.getLogger(__name__)


async def upload_to_r2(file_content: bytes, object_key: str, content_type: str = "application/octet-stream") -> dict:
    """
    Upload file to Cloudflare R2 (non-blocking).
    Falls back to local storage if R2 is not enabled.
    """
    if not R2_ENABLED:
        local_path = UPLOAD_DIR / object_key.split("/")[-1]
        async with aiofiles.open(local_path, 'wb') as f:
            await f.write(file_content)
        return {
            "storage": "local",
            "r2_key": None,
            "local_path": str(local_path),
            "filename": object_key.split("/")[-1]
        }

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: r2_client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=object_key,
                Body=file_content,
                ContentType=content_type
            )
        )
        return {
            "storage": "r2",
            "r2_key": object_key,
            "local_path": None,
            "filename": object_key.split("/")[-1]
        }
    except Exception as e:
        logger.error(f"R2 upload failed: {e}. Falling back to local storage.")
        local_path = UPLOAD_DIR / object_key.split("/")[-1]
        async with aiofiles.open(local_path, 'wb') as f:
            await f.write(file_content)
        return {
            "storage": "local",
            "r2_key": None,
            "local_path": str(local_path),
            "filename": object_key.split("/")[-1]
        }


def get_r2_signed_url(object_key: str, expires_in: int = 600, download_filename: str = None) -> str:
    """Generate a time-limited signed URL for R2 object (sync — fast, no network).
    Optional download_filename forces Content-Disposition so browsers save with
    the original name instead of the random R2 object key."""
    if not R2_ENABLED or not object_key:
        return None
    try:
        params = {'Bucket': R2_BUCKET_NAME, 'Key': object_key}
        if download_filename:
            safe_name = download_filename.replace('"', '').replace(';', '')
            params['ResponseContentDisposition'] = f'attachment; filename="{safe_name}"'
        return r2_client.generate_presigned_url(
            'get_object',
            Params=params,
            ExpiresIn=expires_in
        )
    except Exception as e:
        logger.error(f"R2 signed URL generation failed: {e}")
        return None


async def get_file_from_r2(object_key: str) -> bytes:
    """Download file content from R2 (non-blocking)."""
    if not R2_ENABLED or not object_key:
        return None
    try:
        loop = asyncio.get_event_loop()

        def _download():
            response = r2_client.get_object(Bucket=R2_BUCKET_NAME, Key=object_key)
            return response['Body'].read()

        return await loop.run_in_executor(None, _download)
    except Exception as e:
        logger.error(f"R2 download failed: {e}")
        return None


def generate_r2_key(category: str, original_filename: str) -> str:
    """Generate R2 object key with organized path structure."""
    now = datetime.now(timezone.utc)
    file_ext = Path(original_filename).suffix.lower() or '.bin'
    file_uuid = str(uuid.uuid4())
    return f"{category}/{now.year}/{now.month:02d}/{file_uuid}{file_ext}"
