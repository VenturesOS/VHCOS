"""
LinkedIn OAuth & Auto-Posting Routes
- OAuth flow for connecting LinkedIn
- Settings for auto-posting configuration
- Test post and post history
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
import httpx
import os
import logging

from config import db
from utils import require_role
from services.linkedin_service import (
    get_linkedin_settings,
    save_linkedin_settings,
    post_blog_to_linkedin,
    get_linkedin_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/linkedin", tags=["LinkedIn"])

LINKEDIN_CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
LINKEDIN_REDIRECT_URI = os.environ.get("LINKEDIN_REDIRECT_URI", "https://ventureshrd.com/api/linkedin/callback")

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_PROFILE_URL = "https://api.linkedin.com/v2/userinfo"

SCOPES = "openid profile email w_member_social"


# ── Pydantic Models ──

class LinkedInSettingsRequest(BaseModel):
    auto_post_enabled: Optional[bool] = None
    organization_id: Optional[str] = None


# ── OAuth Endpoints ──

@router.get("/authorize")
async def linkedin_authorize(user=Depends(require_role("admin"))):
    """Initiate LinkedIn OAuth flow — admin only."""
    if not LINKEDIN_CLIENT_ID:
        raise HTTPException(status_code=500, detail="LINKEDIN_CLIENT_ID not configured")

    auth_url = (
        f"{LINKEDIN_AUTH_URL}"
        f"?response_type=code"
        f"&client_id={LINKEDIN_CLIENT_ID}"
        f"&redirect_uri={LINKEDIN_REDIRECT_URI}"
        f"&scope={SCOPES}"
        f"&state=vhc_linkedin_auth"
    )
    return {"authorization_url": auth_url}


@router.get("/callback")
async def linkedin_callback(code: str = None, state: str = None, error: str = None, error_description: str = None):
    """LinkedIn OAuth callback — exchanges code for access token and stores it."""
    if error:
        logger.error(f"LinkedIn OAuth error: {error} — {error_description}")
        return HTMLResponse(content=f"""
            <html><body style="font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;background:#111827;">
            <div style="text-align:center;color:white;">
                <h2 style="color:#ef4444;">LinkedIn Authorization Failed</h2>
                <p>{error_description or error}</p>
                <p style="color:#9ca3af;margin-top:20px;">You can close this window.</p>
            </div></body></html>
        """, status_code=400)

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    if not LINKEDIN_CLIENT_ID or not LINKEDIN_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="LinkedIn credentials not configured")

    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                LINKEDIN_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": LINKEDIN_REDIRECT_URI,
                    "client_id": LINKEDIN_CLIENT_ID,
                    "client_secret": LINKEDIN_CLIENT_SECRET,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if token_response.status_code != 200:
                logger.error(f"LinkedIn token exchange failed: {token_response.text}")
                raise HTTPException(status_code=502, detail="Failed to exchange authorization code")

            token_data = token_response.json()
            access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 5184000)

            if not access_token:
                raise HTTPException(status_code=502, detail="No access token received")

            profile_response = await client.get(
                LINKEDIN_PROFILE_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            profile = profile_response.json() if profile_response.status_code == 200 else {}

    except httpx.RequestError as e:
        logger.error(f"LinkedIn API request error: {e}")
        raise HTTPException(status_code=502, detail="Failed to connect to LinkedIn API")

    token_doc = {
        "platform": "linkedin",
        "access_token": access_token,
        "expires_in": expires_in,
        "profile_name": profile.get("name", ""),
        "profile_email": profile.get("email", ""),
        "connected_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.social_integrations.update_one(
        {"platform": "linkedin"},
        {"$set": token_doc},
        upsert=True,
    )

    logger.info(f"LinkedIn connected successfully for {profile.get('name', 'unknown')}")

    return HTMLResponse(content="""
        <html><body style="font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;background:#111827;">
        <div style="text-align:center;color:white;">
            <div style="width:64px;height:64px;border-radius:50%;background:#9acd32;display:flex;align-items:center;justify-content:center;margin:0 auto 20px;font-size:32px;">&#10003;</div>
            <h2>LinkedIn Connected Successfully</h2>
            <p style="color:#9ca3af;">You can close this window and return to the admin panel.</p>
        </div></body></html>
    """)


@router.get("/status")
async def linkedin_status(user=Depends(require_role("admin"))):
    """Check if LinkedIn is connected and token is valid."""
    integration = await db.social_integrations.find_one(
        {"platform": "linkedin"}, {"_id": 0}
    )
    if not integration or not integration.get("access_token"):
        return {"connected": False}

    return {
        "connected": True,
        "profile_name": integration.get("profile_name", ""),
        "profile_email": integration.get("profile_email", ""),
        "connected_at": integration.get("connected_at", ""),
    }


# ── Settings Endpoints ──

@router.get("/settings")
async def get_settings(user=Depends(require_role("admin"))):
    """Get LinkedIn auto-posting settings."""
    settings = await get_linkedin_settings()
    status = await linkedin_status(user)
    return {**settings, "connection": status}


@router.put("/settings")
async def update_settings(req: LinkedInSettingsRequest, user=Depends(require_role("admin"))):
    """Update LinkedIn auto-posting settings."""
    current = await get_linkedin_settings()
    updates = {}
    if req.auto_post_enabled is not None:
        updates["auto_post_enabled"] = req.auto_post_enabled
    if req.organization_id is not None:
        updates["organization_id"] = req.organization_id.strip()
    if updates:
        current.update(updates)
        await save_linkedin_settings(current)
    return {"message": "Settings updated", **current}


# ── Test Post & History ──

@router.post("/test-post")
async def test_post(user=Depends(require_role("admin"))):
    """Send a test post to LinkedIn to verify the connection works."""
    token = await get_linkedin_token()
    if not token:
        raise HTTPException(status_code=400, detail="LinkedIn not connected. Please authorize first.")

    settings = await get_linkedin_settings()
    if not settings.get("organization_id"):
        raise HTTPException(status_code=400, detail="Organization ID not configured")

    test_blog = {
        "id": "test-post",
        "title": "VHC Talent Advisory Blog - Connection Test",
        "slug": "",
        "blog_type": "employer",
        "meta_description": "This is a test post to verify LinkedIn auto-posting is working correctly.",
    }

    result = await post_blog_to_linkedin(test_blog, is_test=True)
    if not result["success"]:
        raise HTTPException(status_code=502, detail=result["error"])

    return {"message": "Test post sent successfully", **result}


@router.get("/post-history")
async def get_post_history(limit: int = 20, user=Depends(require_role("admin"))):
    """Get LinkedIn auto-posting history."""
    posts = await db.linkedin_post_history.find(
        {}, {"_id": 0}
    ).sort("posted_at", -1).limit(limit).to_list(limit)
    return {"posts": posts, "total": len(posts)}


@router.delete("/disconnect")
async def disconnect_linkedin(user=Depends(require_role("admin"))):
    """Disconnect LinkedIn integration."""
    await db.social_integrations.delete_one({"platform": "linkedin"})
    return {"message": "LinkedIn disconnected"}
