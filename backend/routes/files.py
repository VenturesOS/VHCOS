"""
VHC Talent OS - File Serving Routes
Handles file uploads, downloads, and serving with R2/local fallback.
"""
import io
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse

# Import configuration
from config import db, R2_ENABLED, UPLOAD_DIR

# Import services
from services import get_r2_signed_url, get_file_from_r2


# Create router for file endpoints
files_router = APIRouter(prefix="/api", tags=["Files"])


@files_router.get("/uploads/{filename}")
async def get_upload(filename: str, redirect: bool = True):
    """
    Serve uploaded files. Checks R2 first, then local storage.
    If redirect=True and file is in R2, returns a redirect to signed URL.
    If redirect=False or file is local, streams the file content.
    """
    # First, check if we have R2 metadata for this file in MongoDB
    # Look in applications, candidate_bank collections for r2_key
    if R2_ENABLED:
        # Try to find R2 key from stored metadata
        # Check applications collection
        app_doc = await db.applications.find_one(
            {"$or": [
                {"resume_url": {"$regex": filename}},
                {"r2_metadata.filename": filename}
            ]},
            {"r2_metadata": 1, "_id": 0}
        )
        if app_doc and app_doc.get("r2_metadata", {}).get("r2_key"):
            r2_key = app_doc["r2_metadata"]["r2_key"]
            if redirect:
                signed_url = get_r2_signed_url(r2_key)
                if signed_url:
                    return RedirectResponse(url=signed_url, status_code=307)
            else:
                content = await get_file_from_r2(r2_key)
                if content:
                    return StreamingResponse(io.BytesIO(content), media_type="application/octet-stream")
        
        # Check candidate_bank collection
        candidate_doc = await db.candidate_bank.find_one(
            {"$or": [
                {"resume_url": {"$regex": filename}},
                {"r2_metadata.filename": filename}
            ]},
            {"r2_metadata": 1, "_id": 0}
        )
        if candidate_doc and candidate_doc.get("r2_metadata", {}).get("r2_key"):
            r2_key = candidate_doc["r2_metadata"]["r2_key"]
            if redirect:
                signed_url = get_r2_signed_url(r2_key)
                if signed_url:
                    return RedirectResponse(url=signed_url, status_code=307)
            else:
                content = await get_file_from_r2(r2_key)
                if content:
                    return StreamingResponse(io.BytesIO(content), media_type="application/octet-stream")
    
    # Fallback to local storage
    # Check both possible upload locations
    # Primary location: /app/uploads (used by public apply)
    primary_dir = Path("/app/uploads")
    primary_path = primary_dir / filename
    
    # Secondary location: /app/backend/uploads (used by internal uploads)
    secondary_path = UPLOAD_DIR / filename
    
    if primary_path.exists():
        return FileResponse(primary_path)
    elif secondary_path.exists():
        return FileResponse(secondary_path)
    else:
        raise HTTPException(status_code=404, detail="File not found")


@files_router.get("/download/naukri-extension")
async def download_naukri_extension():
    """
    Download the VHC Naukri Auto-Capture browser extension.
    Returns the extension ZIP file for installation in Chrome/Edge.
    """
    extension_path = UPLOAD_DIR / "vhc-naukri-extension.zip"
    
    if not extension_path.exists():
        raise HTTPException(status_code=404, detail="Extension file not found")
    
    import time
    response = FileResponse(
        path=extension_path,
        filename="vhc-naukri-extension.zip",
        media_type="application/zip",
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Extension-Version"] = "3.6.2"
    return response
