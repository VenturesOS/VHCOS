"""
VHC Talent OS — File Upload Validation (H-05)
Magic-byte content-type detection for uploaded files.
Prevents disguised file uploads (e.g., .exe renamed to .pdf).
"""
import logging
from fastapi import HTTPException, UploadFile

logger = logging.getLogger(__name__)

ALLOWED_RESUME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/msword",  # .doc
    "text/plain",
}

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


def detect_content_type(content: bytes) -> str:
    """Detect actual content type from file magic bytes."""
    try:
        import magic
        return magic.from_buffer(content[:2048], mime=True)
    except Exception as e:
        logger.warning(f"[FileValidation] Magic detection failed: {e}")
        return "application/octet-stream"


async def validate_upload(file: UploadFile, allowed_types: set, max_size_mb: int = 10) -> bytes:
    """
    Read, validate size, and verify magic bytes for an uploaded file.
    Returns file content bytes if valid; raises HTTPException otherwise.
    """
    content = await file.read()

    # Size check
    if len(content) > max_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {max_size_mb}MB."
        )

    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    # Magic-byte content type detection
    actual_type = detect_content_type(content)
    if actual_type not in allowed_types:
        logger.warning(
            f"[FileValidation] Rejected upload: declared={file.content_type}, "
            f"actual={actual_type}, filename={file.filename}"
        )
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {actual_type}. Allowed: {', '.join(sorted(allowed_types))}"
        )

    # Reset file position for downstream consumers
    await file.seek(0)
    return content
