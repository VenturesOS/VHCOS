"""
VHC Talent OS - Authentication Routes
Handles user registration, login, and password management.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

# Import configuration
from config import db, client

# Import models
from models import (
    UserCreate, UserLogin, UserResponse, PasswordReset, TokenResponse
)

# Import utilities
from utils import (
    hash_password, verify_password, create_access_token, get_current_user,
    create_refresh_token, store_refresh_token, validate_refresh_token
)

import re as _re

# Import rate limiter
from services.rate_limiter import rate_limiter

# Import environment resolver (with fallback)
try:
    from utils.environment import normalize_email, ENV_NAME, DB_NAME
except ImportError:
    def normalize_email(e): return e.strip().lower() if e else ""
    ENV_NAME = "unknown"
    DB_NAME = "vhc_talent_os"

logger = logging.getLogger(__name__)


def _validate_password_strength(password: str) -> str | None:
    """Return error message if password is weak, else None."""
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if not _re.search(r'[A-Z]', password):
        return "Password must contain at least 1 uppercase letter"
    if not _re.search(r'[0-9]', password):
        return "Password must contain at least 1 digit"
    if not _re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>?/\\|`~]', password):
        return "Password must contain at least 1 special character"
    return None


# Create router for auth endpoints
auth_router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@auth_router.post("/register", response_model=TokenResponse)
async def register(user_data: UserCreate, request: Request):
    # Rate limit registration
    rate_limiter.check_rate_limit(request, "auth")

    # Turnstile CAPTCHA verification
    from services.security_service import verify_turnstile
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()
    if not await verify_turnstile(user_data.turnstile_token or "", client_ip):
        raise HTTPException(status_code=403, detail="CAPTCHA verification failed. Please try again.")

    # Only candidate self-registration is allowed; employer/recruiter/admin created by admin
    if user_data.role != "candidate":
        raise HTTPException(status_code=403, detail="Only candidate registration is allowed. Employer and Recruiter accounts are created by admin.")

    email = normalize_email(user_data.email)

    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Validate password strength
    pwd_err = _validate_password_strength(user_data.password)
    if pwd_err:
        raise HTTPException(status_code=400, detail=pwd_err)
    
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    user_doc = {
        "id": user_id,
        "email": email,
        "name": user_data.name,
        "role": user_data.role,
        "password": hash_password(user_data.password),
        "phone": None,
        "company_id": None,
        "is_active": True,
        "requires_password_reset": False,
        "token_version": 0,
        "created_at": now
    }
    
    # Atomic multi-document write (CRIT-4: prevents orphaned docs on partial failure)
    try:
        async with await client.start_session() as session:
            async with session.start_transaction():
                await db.users.insert_one(user_doc, session=session)
                logger.info("[USER_CREATED] env=%s db=%s id=%s email=%s role=%s", ENV_NAME, DB_NAME, user_id, email, user_data.role)
                
                if user_data.role == "candidate":
                    profile_doc = {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "name": user_data.name,
                        "email": email,
                        "phone": None,
                        "headline": None,
                        "summary": None,
                        "skills": [],
                        "experience": [],
                        "education": [],
                        "resume_url": None,
                        "notice_period": user_data.notice_period,
                        "current_ctc": user_data.current_ctc,
                        "expected_ctc": user_data.expected_ctc,
                        "created_at": now,
                        "updated_at": now
                    }
                    await db.candidate_profiles.insert_one(profile_doc, session=session)

                    bank_doc = {
                        "id": str(uuid.uuid4()),
                        "name": user_data.name,
                        "email": email,
                        "notice_period": user_data.notice_period,
                        "current_salary": user_data.current_ctc,
                        "expected_salary": user_data.expected_ctc,
                        "source": "self_registered",
                        "skills": [],
                        "experience": [],
                        "education": [],
                        "created_at": now,
                        "updated_at": now
                    }
                    await db.candidate_bank.insert_one(bank_doc, session=session)
    except Exception as txn_err:
        logger.error(f"[REGISTER] Transaction failed for {email}: {txn_err}")
        raise HTTPException(status_code=500, detail="Registration failed. Please try again.")
    
    access_token = create_access_token({"sub": user_id, "role": user_data.role, "tv": 0})
    
    user_response = UserResponse(
        id=user_id,
        email=email,
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
    
    email = normalize_email(credentials.email)

    # ── Brute-force lockout (SEC-2): 5 failed attempts → 15 min lock ──
    lockout_doc = await db.login_attempts.find_one({"email": email}, {"_id": 0})
    if lockout_doc and lockout_doc.get("locked_until"):
        lock_until = datetime.fromisoformat(lockout_doc["locked_until"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) < lock_until:
            remaining = int((lock_until - datetime.now(timezone.utc)).total_seconds() / 60) + 1
            raise HTTPException(status_code=429, detail=f"Account locked due to too many failed attempts. Try again in {remaining} minutes.")
        else:
            # Lock expired, reset
            await db.login_attempts.delete_one({"email": email})

    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not verify_password(credentials.password, user["password"]):
        # Track failed attempt
        if user:
            attempts = (lockout_doc.get("count", 0) if lockout_doc else 0) + 1
            update = {"$set": {"email": email, "count": attempts, "last_attempt": datetime.now(timezone.utc).isoformat()}}
            if attempts >= 5:
                lock_until = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
                update["$set"]["locked_until"] = lock_until
                logger.warning(f"[AUTH] Account locked for {email} after {attempts} failed attempts")
            await db.login_attempts.update_one({"email": email}, update, upsert=True)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Successful login — clear failed attempts
    await db.login_attempts.delete_one({"email": email})

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is disabled")
    
    requires_reset = user.get("requires_password_reset", False)
    
    access_token = create_access_token({"sub": user["id"], "role": user["role"], "tv": user.get("token_version", 0)})
    
    # M-03: Issue refresh token (single-use, 7-day expiry)
    refresh_token = create_refresh_token()
    await store_refresh_token(user["id"], refresh_token, user.get("token_version", 0))
    
    user_response = UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        role=user["role"],
        company_id=user.get("company_id"),
        phone=user.get("phone"),
        created_at=user["created_at"],
        requires_password_reset=requires_reset,
        is_account_manager=user.get("is_account_manager", False),
        assigned_companies=user.get("assigned_companies")
    )
    
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, user=user_response, requires_password_reset=requires_reset)


@auth_router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(**current_user)


@auth_router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """Invalidate all existing tokens by incrementing token_version."""
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$inc": {"token_version": 1}}
    )
    # Also clear all refresh tokens for this user
    await db.refresh_tokens.delete_many({"user_id": current_user["id"]})
    return {"message": "Logged out successfully. All sessions invalidated."}


class RefreshRequest(BaseModel):
    refresh_token: str


@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(req: RefreshRequest):
    """
    M-03: Refresh token rotation — exchange a valid refresh token for a new
    access + refresh token pair. The old refresh token is consumed (single-use).
    """
    user = await validate_refresh_token(req.refresh_token)
    
    # Issue new token pair
    new_access = create_access_token({"sub": user["id"], "role": user["role"], "tv": user.get("token_version", 0)})
    new_refresh = create_refresh_token()
    await store_refresh_token(user["id"], new_refresh, user.get("token_version", 0))
    
    user_response = UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        role=user["role"],
        company_id=user.get("company_id"),
        phone=user.get("phone"),
        created_at=user["created_at"],
        requires_password_reset=user.get("requires_password_reset", False),
        is_account_manager=user.get("is_account_manager", False),
        assigned_companies=user.get("assigned_companies")
    )
    
    return TokenResponse(access_token=new_access, refresh_token=new_refresh, user=user_response)


@auth_router.post("/reset-password")
async def reset_password(reset_data: PasswordReset, current_user: dict = Depends(get_current_user)):
    """Reset password - validates current password and sets new one"""
    user = await db.users.find_one({"id": current_user["id"]}, {"_id": 0})
    
    if not verify_password(reset_data.current_password, user["password"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    pwd_err = _validate_password_strength(reset_data.new_password)
    if pwd_err:
        raise HTTPException(status_code=400, detail=pwd_err)
    
    if reset_data.current_password == reset_data.new_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")
    
    # Update password, clear reset flag, and revoke existing tokens
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {
            "password": hash_password(reset_data.new_password),
            "requires_password_reset": False,
        }, "$inc": {"token_version": 1}}
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
    user = await db.users.find_one({"email": normalize_email(req.email)}, {"_id": 0, "id": 1, "name": 1, "email": 1})
    # Always return success to prevent email enumeration
    if not user:
        return {"message": "If an account with that email exists, a reset link has been sent."}

    import secrets
    import hashlib
    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(hours=1)

    await db.password_reset_tokens.delete_many({"user_id": user["id"]})
    await db.password_reset_tokens.insert_one({
        "user_id": user["id"],
        "token_hash": token_hash,
        "expires_at": expires.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    import os
    frontend_url = os.environ.get("FRONTEND_URL") or os.environ.get("SITE_URL", "https://ventureshrd.com")
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

    import hashlib
    import secrets as _secrets
    token_hash = hashlib.sha256(req.token.encode()).hexdigest()
    record = await db.password_reset_tokens.find_one({"token_hash": token_hash})
    # Also check legacy plain-text tokens for backwards compat
    if not record:
        record = await db.password_reset_tokens.find_one({"token": req.token})
    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    expires = datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires:
        await db.password_reset_tokens.delete_one({"_id": record["_id"]})
        raise HTTPException(status_code=400, detail="Reset link has expired. Please request a new one.")

    pwd_err = _validate_password_strength(req.new_password)
    if pwd_err:
        raise HTTPException(status_code=400, detail=pwd_err)

    await db.users.update_one(
        {"id": record["user_id"]},
        {"$set": {
            "password": hash_password(req.new_password),
            "requires_password_reset": False,
        }, "$inc": {"token_version": 1}},
    )
    await db.password_reset_tokens.delete_many({"user_id": record["user_id"]})

    return {"message": "Password has been reset successfully. You can now log in."}
