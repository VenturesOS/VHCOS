"""
VHC Talent OS - Authentication Routes
Handles user registration, login, and password management.
"""
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

# Import configuration
from config import db

# Import models
from models import (
    UserCreate, UserLogin, UserResponse, PasswordReset, TokenResponse
)

# Import utilities
from utils import (
    hash_password, verify_password, create_access_token, get_current_user
)

# Import rate limiter
from services.rate_limiter import rate_limiter


# Create router for auth endpoints
auth_router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@auth_router.post("/register", response_model=TokenResponse)
async def register(user_data: UserCreate, request: Request):
    # Rate limit registration
    rate_limiter.check_rate_limit(request, "auth")

    # Only candidate self-registration is allowed; employer/recruiter/admin created by admin
    if user_data.role != "candidate":
        raise HTTPException(status_code=403, detail="Only candidate registration is allowed. Employer and Recruiter accounts are created by admin.")

    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Validate password strength
    if len(user_data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    user_doc = {
        "id": user_id,
        "email": user_data.email,
        "name": user_data.name,
        "role": user_data.role,
        "password": hash_password(user_data.password),
        "phone": None,
        "company_id": None,
        "is_active": True,
        "requires_password_reset": False,
        "created_at": now
    }
    
    await db.users.insert_one(user_doc)
    
    # Create candidate profile if role is candidate
    if user_data.role == "candidate":
        profile_doc = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": user_data.name,
            "email": user_data.email,
            "phone": None,
            "headline": None,
            "summary": None,
            "skills": [],
            "experience": [],
            "education": [],
            "resume_url": None,
            "created_at": now,
            "updated_at": now
        }
        await db.candidate_profiles.insert_one(profile_doc)
    
    access_token = create_access_token({"sub": user_id, "role": user_data.role})
    
    user_response = UserResponse(
        id=user_id,
        email=user_data.email,
        name=user_data.name,
        role=user_data.role,
        created_at=now,
        requires_password_reset=False
    )
    
    return TokenResponse(access_token=access_token, user=user_response, requires_password_reset=False)


@auth_router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, request: Request):
    # Rate limit login attempts
    rate_limiter.check_rate_limit(request, "auth")
    
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user or not verify_password(credentials.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is disabled")
    
    requires_reset = user.get("requires_password_reset", False)
    
    access_token = create_access_token({"sub": user["id"], "role": user["role"]})
    
    user_response = UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        role=user["role"],
        company_id=user.get("company_id"),
        phone=user.get("phone"),
        created_at=user["created_at"],
        requires_password_reset=requires_reset
    )
    
    return TokenResponse(access_token=access_token, user=user_response, requires_password_reset=requires_reset)


@auth_router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(**current_user)


@auth_router.post("/reset-password")
async def reset_password(reset_data: PasswordReset, current_user: dict = Depends(get_current_user)):
    """Reset password - validates current password and sets new one"""
    # Get user with password
    user = await db.users.find_one({"id": current_user["id"]}, {"_id": 0})
    
    if not verify_password(reset_data.current_password, user["password"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    if len(reset_data.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    
    if reset_data.current_password == reset_data.new_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")
    
    # Update password and clear reset flag
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {
            "password": hash_password(reset_data.new_password),
            "requires_password_reset": False
        }}
    )
    
    return {"message": "Password reset successfully"}


# ── Forgot Password (No Auth) ──

class ForgotPasswordRequest(BaseModel):
    email: str

class ForgotPasswordResetRequest(BaseModel):
    token: str
    new_password: str


@auth_router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, request: Request):
    """Public: send a password reset link to the user's email."""
    rate_limiter.check_rate_limit(request, "auth")
    user = await db.users.find_one({"email": req.email}, {"_id": 0, "id": 1, "name": 1, "email": 1})
    # Always return success to prevent email enumeration
    if not user:
        return {"message": "If an account with that email exists, a reset link has been sent."}

    import secrets
    token = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(hours=1)

    await db.password_reset_tokens.delete_many({"user_id": user["id"]})
    await db.password_reset_tokens.insert_one({
        "user_id": user["id"],
        "token": token,
        "expires_at": expires.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    import os
    frontend_url = os.environ.get("FRONTEND_URL", "https://ventureshrd.com")
    reset_link = f"{frontend_url}/forgot-password?token={token}"

    from services.email_service import send_email
    await send_email(
        recipient_email=user["email"],
        subject="Reset Your Password — Ventures HRD",
        html_content=f"""
        <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;padding:32px;">
          <h2 style="color:#111827;">Password Reset</h2>
          <p>Hi {user.get('name', '')},</p>
          <p>We received a request to reset your password. Click the button below to set a new one. This link expires in 1 hour.</p>
          <a href="{reset_link}" style="display:inline-block;background:#7CB342;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;margin:16px 0;">Reset Password</a>
          <p style="color:#6B7280;font-size:13px;">If you didn't request this, you can safely ignore this email.</p>
          <hr style="border:none;border-top:1px solid #E5E7EB;margin:24px 0;">
          <p style="color:#9CA3AF;font-size:12px;">Ventures HRD Centre Pvt Ltd</p>
        </div>
        """,
    )

    return {"message": "If an account with that email exists, a reset link has been sent."}


@auth_router.post("/forgot-password/reset")
async def forgot_password_reset(req: ForgotPasswordResetRequest, request: Request):
    """Public: reset password using the emailed token."""
    rate_limiter.check_rate_limit(request, "auth")

    record = await db.password_reset_tokens.find_one({"token": req.token})
    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    expires = datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires:
        await db.password_reset_tokens.delete_one({"token": req.token})
        raise HTTPException(status_code=400, detail="Reset link has expired. Please request a new one.")

    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    await db.users.update_one(
        {"id": record["user_id"]},
        {"$set": {
            "password": hash_password(req.new_password),
            "requires_password_reset": False,
        }},
    )
    await db.password_reset_tokens.delete_many({"user_id": record["user_id"]})

    return {"message": "Password has been reset successfully. You can now log in."}
