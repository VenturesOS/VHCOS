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
    generate_job_linkedin_draft,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/linkedin", tags=["LinkedIn"])

LINKEDIN_CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
LINKEDIN_REDIRECT_URI = os.environ.get("LINKEDIN_REDIRECT_URI")
if not LINKEDIN_REDIRECT_URI:
    logger.warning("LINKEDIN_REDIRECT_URI not configured — LinkedIn OAuth will not work")

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
# NOTE: Community Management API does NOT grant OIDC/r_liteprofile scopes,
# and the two products are mutually exclusive on the same LinkedIn app.
# We skip person-profile fetch entirely; posting is always to an org page.
LINKEDIN_PROFILE_URL = ""

SCOPES = "w_member_social w_organization_social rw_organization_admin"


# ── Pydantic Models ──

class LinkedInSettingsRequest(BaseModel):
    auto_post_enabled: Optional[bool] = None
    organization_id: Optional[str] = None


# ── OAuth Endpoints ──

# Access trimmed 2026-09-17: LinkedIn is an admin-only surface now.
LINKEDIN_ROLES = ["admin"]


@router.get("/authorize")
async def linkedin_authorize(user=Depends(require_role(LINKEDIN_ROLES))):
    """Initiate LinkedIn OAuth flow — admin only."""
    if not LINKEDIN_CLIENT_ID:
        raise HTTPException(status_code=500, detail="LINKEDIN_CLIENT_ID not configured")

    from urllib.parse import urlencode
    params = {
        "response_type": "code",
        "client_id": LINKEDIN_CLIENT_ID,
        "redirect_uri": LINKEDIN_REDIRECT_URI,
        "scope": SCOPES,
        "state": "vhc_linkedin_auth",
    }
    auth_url = f"{LINKEDIN_AUTH_URL}?{urlencode(params)}"
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

            # Skip profile fetch — Community Management API doesn't grant profile scopes
            # (OIDC/r_liteprofile are mutually exclusive with Community Management on
            # the same app). Post authorship happens via organizationAcls lookup instead.
            profile = {}

    except httpx.RequestError as e:
        logger.error(f"LinkedIn API request error: {e}")
        raise HTTPException(status_code=502, detail="Failed to connect to LinkedIn API")

    profile_name = ""
    profile_sub = ""
    profile_email = ""

    token_doc = {
        "platform": "linkedin",
        "access_token": access_token,
        "expires_in": expires_in,
        "profile_name": profile_name,
        "profile_sub": profile_sub,
        "profile_email": profile_email,
        "connected_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.social_integrations.update_one(
        {"platform": "linkedin"},
        {"$set": token_doc},
        upsert=True,
    )

    logger.info(f"LinkedIn connected successfully (Community Management token stored)")

    return HTMLResponse(content="""
        <html><body style="font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;background:#111827;">
        <div style="text-align:center;color:white;">
            <div style="width:64px;height:64px;border-radius:50%;background:#9acd32;display:flex;align-items:center;justify-content:center;margin:0 auto 20px;font-size:32px;">&#10003;</div>
            <h2>LinkedIn Connected Successfully</h2>
            <p style="color:#9ca3af;">You can close this window and return to the admin panel.</p>
        </div></body></html>
    """)


@router.get("/status")
async def linkedin_status(user=Depends(require_role(LINKEDIN_ROLES))):
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


@router.get("/organizations")
async def list_admin_organizations(user=Depends(require_role(LINKEDIN_ROLES))):
    """
    List LinkedIn Company Pages the connected user administrates.
    Requires `rw_organization_admin` (Community Management API) — approved for
    VHC Jobs app in Development Tier. The user must re-authorize after the
    scope upgrade for this endpoint to return anything.
    """
    token = await get_linkedin_token()
    if not token:
        raise HTTPException(status_code=400, detail="LinkedIn not connected")

    headers = {
        "Authorization": f"Bearer {token}",
        "LinkedIn-Version": "202402",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    orgs = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # 1) which orgs this user admins. Query without role filter so we
            # catch every page role (ADMINISTRATOR / CONTENT_ADMIN / CURATOR / etc.).
            acl_url = (
                "https://api.linkedin.com/v2/organizationAcls"
                "?q=roleAssignee&count=50"
            )
            acl_res = await client.get(acl_url, headers=headers)
            if acl_res.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"LinkedIn returned {acl_res.status_code} — "
                        "reconnect LinkedIn to grant the new org scopes. "
                        f"Details: {acl_res.text[:200]}"
                    ),
                )
            elements = acl_res.json().get("elements", [])
            # Keep only those in APPROVED state; ignore REVOKED/REJECTED.
            # (LinkedIn returns role + state per assignment.)
            valid = [e for e in elements
                     if e.get("state") in (None, "APPROVED")
                     and e.get("organization")]
            # De-dup by organization URN in case a user has multiple roles on one page
            seen = set()
            org_role_map = {}
            for e in valid:
                urn = e["organization"]
                if urn in seen:
                    continue
                seen.add(urn)
                org_role_map[urn] = e.get("role", "MEMBER")
            org_urns = list(seen)

            # 2) fetch each org's name
            for urn in org_urns:
                org_id = urn.split(":")[-1]
                d = await client.get(
                    f"https://api.linkedin.com/v2/organizations/{org_id}",
                    headers=headers,
                )
                if d.status_code == 200:
                    j = d.json()
                    orgs.append({
                        "urn": urn,
                        "id": org_id,
                        "name": (j.get("localizedName")
                                 or j.get("name", {}).get("localized", {}).get("en_US", "")
                                 or f"Org {org_id}"),
                        "vanity_name": j.get("vanityName", ""),
                        "role": org_role_map.get(urn, ""),
                    })
                else:
                    orgs.append({"urn": urn, "id": org_id,
                                 "name": f"Org {org_id}", "vanity_name": "",
                                 "role": org_role_map.get(urn, "")})
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Connection error: {e}")

    return {"organizations": orgs, "count": len(orgs)}


# ── Settings Endpoints ──

@router.get("/settings")
async def get_settings(user=Depends(require_role(LINKEDIN_ROLES))):
    """Get LinkedIn auto-posting settings."""
    settings = await get_linkedin_settings()
    status = await linkedin_status(user)
    return {**settings, "connection": status}


@router.put("/settings")
async def update_settings(req: LinkedInSettingsRequest, user=Depends(require_role(LINKEDIN_ROLES))):
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
async def test_post(user=Depends(require_role(LINKEDIN_ROLES))):
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
async def get_post_history(limit: int = 20, user=Depends(require_role(LINKEDIN_ROLES))):
    """Get LinkedIn auto-posting history."""
    posts = await db.linkedin_post_history.find(
        {}, {"_id": 0}
    ).sort("posted_at", -1).limit(limit).to_list(limit)
    return {"posts": posts, "total": len(posts)}


@router.delete("/disconnect")
async def disconnect_linkedin(user=Depends(require_role(LINKEDIN_ROLES))):
    """Disconnect LinkedIn integration."""
    await db.social_integrations.delete_one({"platform": "linkedin"})
    return {"message": "LinkedIn disconnected"}


# ── Job → LinkedIn Draft endpoints ─────────────────────────────────────────
# Stopgap manual-copy flow. Once `w_organization_social` is approved by
# LinkedIn Marketing Developer Platform we can wire these drafts into an
# auto-post path — the template and endpoint contract stay identical.

@router.get("/job-drafts")
async def list_job_drafts(
    status: str = "unposted",   # "unposted" | "posted" | "all"
    q: Optional[str] = None,
    limit: int = 20,
    skip: int = 0,
    user=Depends(require_role(LINKEDIN_ROLES)),
):
    """List LinkedIn draft posts for active jobs.

    Uses the same visibility rule as the public /careers page so recruiters
    only see drafts for roles that are actually live on the site (avoids
    accidentally sharing internal / removed mandates).
    """
    query = {
        "status": "active",
        "career_page_status": {"$ne": "removed"},
    }
    if status == "unposted":
        query["linkedin_posted_at"] = {"$in": [None, ""]}
    elif status == "posted":
        query["linkedin_posted_at"] = {"$nin": [None, ""]}
    if q:
        query["$or"] = [
            {"title":    {"$regex": q, "$options": "i"}},
            {"function": {"$regex": q, "$options": "i"}},
            {"location": {"$regex": q, "$options": "i"}},
        ]

    proj = {
        "_id": 0,
        "id": 1, "title": 1, "location": 1, "industry": 1,
        "function": 1, "seniority": 1,
        "experience_min": 1, "experience_max": 1,
        "salary_min": 1, "salary_max": 1, "salary_currency": 1,
        "description": 1, "job_description": 1, "summary": 1,
        "requirements": 1, "qualifications": 1,
        "skills": 1, "key_skills": 1,
        "key_responsibilities": 1, "responsibilities": 1,
        "employment_type": 1, "department": 1,
        "company_name": 1, "client_name": 1, "public_company_alias": 1,
        "job_public_id": 1, "updated_at": 1,
        "linkedin_posted_at": 1,
    }

    total = await db.jobs.count_documents(query)
    cursor = db.jobs.find(query, proj).sort("updated_at", -1).skip(skip).limit(limit)
    jobs = await cursor.to_list(limit)

    return {
        "total":  total,
        "count":  len(jobs),
        "skip":   skip,
        "limit":  limit,
        "drafts": [generate_job_linkedin_draft(j) for j in jobs],
    }


@router.get("/job-drafts/{job_id}")
async def get_single_job_draft(
    job_id: str,
    user=Depends(require_role(LINKEDIN_ROLES)),
):
    """Fetch a single job's LinkedIn draft — used when the admin regenerates
    or previews before pasting."""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return generate_job_linkedin_draft(job)


class TogglePostedRequest(BaseModel):
    posted: bool


@router.post("/job-drafts/{job_id}/toggle-posted")
async def toggle_job_draft_posted(
    job_id: str,
    req: TogglePostedRequest,
    user=Depends(require_role(LINKEDIN_ROLES)),
):
    """Mark a job's LinkedIn draft as posted (or un-posted).

    Persists `linkedin_posted_at` on the job document so the admin UI can
    filter drafts they've already shared. This is bookkeeping only — we do
    not verify LinkedIn actually received the post (user-driven copy/paste).
    """
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0, "id": 1})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    now_iso = datetime.now(timezone.utc).isoformat() if req.posted else None
    await db.jobs.update_one(
        {"id": job_id},
        {"$set": {"linkedin_posted_at": now_iso}},
    )
    return {"job_id": job_id, "linkedin_posted_at": now_iso}

