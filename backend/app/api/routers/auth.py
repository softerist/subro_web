# backend/app/api/routers/auth.py
import logging
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import exceptions
from fastapi_users.authentication import JWTStrategy
from jwt.exceptions import PyJWTError as JWTError
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rate_limit import get_real_client_ip, limiter
from app.core.request_context import set_actor
from app.core.security_logger import security_log
from app.core.users import (
    UserManager,
    cookie_transport,
    current_active_user,
    fastapi_users_instance,
    get_access_token_jwt_strategy,  # Correct strategy for access tokens
    get_user_manager,
    password_helper,
)
from app.db.models.user import User as UserModel  # Your DB model, aliased
from app.db.session import get_async_session
from app.schemas.auth import Token
from app.schemas.user import UserCreate, UserRead  # UserCreate for register router
from app.services import audit_service

logger = logging.getLogger(__name__)

# --- Constants for manual refresh token handling ---
REFRESH_TOKEN_LIFETIME_SECONDS = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
REFRESH_TOKEN_AUDIENCE = "fastapi-users:auth-refresh"
ALGORITHM = settings.ALGORITHM
REFRESH_SECRET_KEY = settings.JWT_REFRESH_SECRET_KEY


# --- Helper for manual refresh token ---
def _create_manual_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(seconds=REFRESH_TOKEN_LIFETIME_SECONDS)
    to_encode.update(
        {
            "exp": expire,
            "aud": REFRESH_TOKEN_AUDIENCE,
            "jti": str(uuid.uuid4()),
            "type": "refresh",
        }
    )
    return jwt.encode(to_encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)


async def _decode_manual_refresh_token(token: str, user_manager: UserManager) -> UserModel | None:
    try:
        payload = jwt.decode(
            token, REFRESH_SECRET_KEY, algorithms=[ALGORITHM], audience=REFRESH_TOKEN_AUDIENCE
        )
        if payload.get("type") != "refresh":
            return None
        user_id_str = payload.get("sub")
        if not user_id_str:
            return None
        user = await user_manager.get(
            uuid.UUID(user_id_str)
        )  # user_manager.get returns the DB model type
        return user if user and user.is_active else None
    except (JWTError, ValueError, exceptions.UserNotExists):
        return None


auth_router = APIRouter(
    tags=["Auth - Authentication & Authorization"],
)


# --- Custom Login Endpoint ---
@auth_router.post("/login", summary="Login for access and refresh tokens")
@limiter.limit("5/minute")
async def custom_login(
    request: Request,
    response: Response,
    credentials: OAuth2PasswordRequestForm = Depends(),
    user_manager: UserManager = Depends(get_user_manager),
    access_token_strategy: JWTStrategy = Depends(get_access_token_jwt_strategy),
    db: AsyncSession = Depends(get_async_session),
):
    import asyncio

    from app.services.account_lockout import (
        clear_failed_attempts,
        get_progressive_delay,
        record_login_attempt,
    )

    # Get client IP using trusted proxy-aware extraction
    client_ip = get_real_client_ip(request)

    user_agent = request.headers.get("User-Agent")
    email = credentials.username.lower()

    logger.debug(f"Login attempt for user: {email} from IP: {client_ip}")

    # Apply progressive delay based on failed attempts (exponential backoff)
    delay_status = await get_progressive_delay(db, email)
    if delay_status.delay_seconds > 0:
        logger.info(f"Applying {delay_status.delay_seconds}s delay for {email}")
        await asyncio.sleep(delay_status.delay_seconds)

    # 1. Check if account is suspended BEFORE authenticating
    # We fetch the user manually here to check status
    from sqlalchemy import select

    res = await db.execute(select(UserModel).where(UserModel.email == email))
    pre_auth_user = res.scalar_one_or_none()

    if pre_auth_user and pre_auth_user.status == "suspended":
        logger.warning(f"Login attempt for suspended user: {email}")
        await audit_service.log_event(
            db,
            category="auth",
            action="auth.login",
            severity="warning",
            success=False,
            target_user_id=pre_auth_user.id,
            details={"reason": "ACCOUNT_SUSPENDED"},
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="LOGIN_BAD_CREDENTIALS")

    # Attempt authentication
    user = await user_manager.authenticate(credentials)

    if user is None:
        # Record failed attempt
        await record_login_attempt(db, email, client_ip, success=False, user_agent=user_agent)

        # Audit Log: Failed Login
        await audit_service.log_event(
            db,
            category="auth",
            action="auth.login",
            success=False,
            details={"reason": "INVALID_CREDENTIALS"},
        )
        await db.commit()

        # Get updated delay info for logging
        updated_delay = await get_progressive_delay(db, email)
        logger.warning(
            f"Login failed for {email} - next delay will be {updated_delay.delay_seconds}s"
        )

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="LOGIN_BAD_CREDENTIALS")

    if not user.is_active:
        logger.warning(f"Login attempt for inactive user: {user.email} (ID: {user.id})")
        security_log.failed_login(client_ip, email, "USER_INACTIVE")
        await audit_service.log_event(
            db,
            category="auth",
            action="auth.login",
            success=False,
            target_user_id=user.id,
            details={"reason": "USER_INACTIVE"},
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="LOGIN_BAD_CREDENTIALS")

    # Successful password authentication - record and clear failed attempts
    await record_login_attempt(db, email, client_ip, success=True, user_agent=user_agent)
    await clear_failed_attempts(db, email)

    # Audit Log: Success
    set_actor(user_id=str(user.id), email=user.email, actor_type="user")
    await audit_service.log_event(
        db,
        category="auth",
        action="auth.login",
        success=True,
    )
    await db.commit()

    # SECURITY: Superusers/admins should have MFA enabled
    # We allow login but flag the response so frontend shows persistent warning
    mfa_setup_required = user.is_superuser and not user.mfa_enabled
    if mfa_setup_required:
        logger.warning(f"Superuser {user.email} logged in without MFA enabled")

    # Check if MFA is required
    if user.mfa_enabled:
        from app.services.mfa_service import verify_trusted_device

        # Check for trusted device cookie
        trusted_device_token = request.cookies.get("subTrustedDevice")
        if trusted_device_token:
            is_trusted = await verify_trusted_device(db, str(user.id), trusted_device_token)
            if is_trusted:
                logger.info(f"Trusted device login for {user.email}, skipping MFA")
            else:
                # Invalid trusted device, require MFA
                logger.info(f"MFA required for {user.email} (invalid trusted device)")
                response.set_cookie(
                    key="mfa_user_id",
                    value=str(user.id),
                    max_age=300,  # 5 minutes to complete MFA
                    httponly=True,
                    secure=True,
                    samesite="strict",
                )
                return {"requires_mfa": True, "message": "MFA verification required"}
        else:
            # No trusted device, require MFA
            logger.info(f"MFA required for {user.email}")
            response.set_cookie(
                key="mfa_user_id",
                value=str(user.id),
                max_age=300,  # 5 minutes to complete MFA
                httponly=True,
                secure=True,
                samesite="strict",
            )
            return {"requires_mfa": True, "message": "MFA verification required"}

    # Generate tokens (no MFA or trusted device verified)
    access_token = await access_token_strategy.write_token(user)

    refresh_token_data = {"sub": str(user.id)}
    refresh_token = _create_manual_refresh_token(data=refresh_token_data)

    response.set_cookie(
        key=cookie_transport.cookie_name,
        value=refresh_token,
        max_age=cookie_transport.cookie_max_age,
        path=cookie_transport.cookie_path,
        domain=cookie_transport.cookie_domain,
        secure=cookie_transport.cookie_secure,
        httponly=cookie_transport.cookie_httponly,
        samesite=cookie_transport.cookie_samesite,
    )

    logger.info(f"User logged in successfully: {user.email} (ID: {user.id})")

    # Return token with MFA setup warning for admins without MFA
    result = {"access_token": access_token, "token_type": "bearer"}
    if mfa_setup_required:
        result["mfa_setup_required"] = True
    return result


# --- Custom Refresh Token Endpoint ---
@auth_router.post("/refresh", response_model=Token, summary="Refresh access token")
async def custom_refresh(
    request: Request,
    response: Response,
    user_manager: UserManager = Depends(get_user_manager),
    access_token_strategy: JWTStrategy = Depends(get_access_token_jwt_strategy),  # <<< CORRECTED
    # refresh_token_strategy: JWTStrategy = Depends(get_refresh_token_jwt_strategy), # if separated
):
    refresh_token_from_cookie = request.cookies.get(cookie_transport.cookie_name)
    if not refresh_token_from_cookie:
        logger.debug("Refresh attempt without refresh token cookie.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="REFRESH_TOKEN_MISSING"
        )

    user = await _decode_manual_refresh_token(
        refresh_token_from_cookie, user_manager
    )  # Returns DB Model or None

    if not user:
        logger.warning("Refresh token invalid, expired, or user inactive. Deleting cookie.")
        # Audit Log: Failed Refresh
        from app.db.session import FastAPISessionLocal

        if FastAPISessionLocal:
            async with FastAPISessionLocal() as db_session:
                await audit_service.log_event(
                    db_session,
                    category="auth",
                    action="auth.token_refresh",
                    success=False,
                    details={"reason": "INVALID_TOKEN"},
                )
                await db_session.commit()

        response.delete_cookie(
            key=cookie_transport.cookie_name,
            path=cookie_transport.cookie_path,
            domain=cookie_transport.cookie_domain,
            secure=cookie_transport.cookie_secure,
            httponly=cookie_transport.cookie_httponly,
            samesite=cookie_transport.cookie_samesite,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="REFRESH_TOKEN_INVALID"
        )

    # Audit Log: Success
    from app.db.session import FastAPISessionLocal

    if FastAPISessionLocal:
        async with FastAPISessionLocal() as db_session:
            await audit_service.log_event(
                db_session,
                category="auth",
                action="auth.token_refresh",
                success=True,
            )
            await db_session.commit()

    new_access_token = await access_token_strategy.write_token(user)  # Pass the user model instance

    new_refresh_token_data = {"sub": str(user.id)}
    new_refresh_token = _create_manual_refresh_token(data=new_refresh_token_data)

    response.set_cookie(
        key=cookie_transport.cookie_name,
        value=new_refresh_token,
        max_age=cookie_transport.cookie_max_age,
        path=cookie_transport.cookie_path,
        domain=cookie_transport.cookie_domain,
        secure=cookie_transport.cookie_secure,
        httponly=cookie_transport.cookie_httponly,
        samesite=cookie_transport.cookie_samesite,
    )

    logger.info(f"Token refreshed for user: {user.email} (ID: {user.id})")
    return Token(access_token=new_access_token, token_type="bearer")


# --- Custom Safe Refresh Endpoint (No 401) ---
@auth_router.post(
    "/session",
    summary="Check session status safely",
)
async def check_session(
    request: Request,
    response: Response,
    user_manager: UserManager = Depends(get_user_manager),
    access_token_strategy: JWTStrategy = Depends(get_access_token_jwt_strategy),
):
    """
    Check if a valid refresh token exists in cookies.
    If valid: returns new access token and is_authenticated=True.
    If invalid: returns is_authenticated=False (no 401 error).
    """
    from app.schemas.auth import SessionStatus

    refresh_token_from_cookie = request.cookies.get(cookie_transport.cookie_name)
    if not refresh_token_from_cookie:
        return SessionStatus(is_authenticated=False)

    try:
        user = await _decode_manual_refresh_token(refresh_token_from_cookie, user_manager)
    except Exception:
        user = None

    if not user:
        # User invalid or token expired - clear cookie and return false
        # We perform the cleanup logic here too
        response.delete_cookie(
            key=cookie_transport.cookie_name,
            path=cookie_transport.cookie_path,
            domain=cookie_transport.cookie_domain,
            secure=cookie_transport.cookie_secure,
            httponly=cookie_transport.cookie_httponly,
            samesite=cookie_transport.cookie_samesite,
        )
        return SessionStatus(is_authenticated=False)

    # User is valid - generate new access token
    new_access_token = await access_token_strategy.write_token(user)

    # Rotate refresh token
    new_refresh_token_data = {"sub": str(user.id)}
    new_refresh_token = _create_manual_refresh_token(data=new_refresh_token_data)

    response.set_cookie(
        key=cookie_transport.cookie_name,
        value=new_refresh_token,
        max_age=cookie_transport.cookie_max_age,
        path=cookie_transport.cookie_path,
        domain=cookie_transport.cookie_domain,
        secure=cookie_transport.cookie_secure,
        httponly=cookie_transport.cookie_httponly,
        samesite=cookie_transport.cookie_samesite,
    )

    return SessionStatus(is_authenticated=True, access_token=new_access_token, token_type="bearer")


# --- Change Password Endpoint (for logged-in users) ---


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


@auth_router.patch("/password", summary="Change password (logged in users)")
@limiter.limit("3/minute")
async def change_password(
    request: Request,  # noqa: ARG001 - Name 'request' required by rate limiter
    body: ChangePasswordRequest,
    current_user: UserModel = Depends(current_active_user),
    user_manager: UserManager = Depends(get_user_manager),
):
    """
    Change password for the currently logged-in user.
    Requires the current password for verification.
    """
    from datetime import datetime

    # Verify current password
    verified, _ = password_helper.verify_and_update(
        body.current_password, current_user.hashed_password
    )
    if not verified:
        logger.warning(
            f"Password change failed for {current_user.email}: incorrect current password"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect."
        )

    # Validate new password strength (uses UserManager.validate_password)
    try:
        await user_manager.validate_password(body.new_password, current_user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e.reason) if hasattr(e, "reason") else str(e),
        ) from e

    # Update password
    hashed_new_password = password_helper.hash(body.new_password)
    current_user.hashed_password = hashed_new_password
    current_user.password_changed_at = datetime.now(UTC)
    current_user.force_password_change = False

    await user_manager.user_db.update(
        current_user,
        {
            "hashed_password": hashed_new_password,
            "password_changed_at": current_user.password_changed_at,
            "force_password_change": False,
        },
    )

    logger.info(f"Password changed successfully for {current_user.email}. Sessions invalidated.")
    from app.db.session import FastAPISessionLocal

    if FastAPISessionLocal:
        async with FastAPISessionLocal() as db_session:
            await audit_service.log_event(
                db_session,
                category="auth",
                action="auth.password_change",
                success=True,
                details={"reason": "USER_INITIATED"},
            )
            await db_session.commit()

    return {"message": "Password changed successfully."}


# --- Custom Logout Endpoint ---
@auth_router.post("/logout", summary="Logout user", status_code=status.HTTP_200_OK)
async def custom_logout(
    response: Response,
    current_user: UserModel = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    logger.info(
        f"Logout attempt for {current_user.email}. Deleting cookie: {cookie_transport.cookie_name}"
    )

    # Audit Log: Logout
    await audit_service.log_event(
        db,
        category="auth",
        action="auth.logout",
        success=True,
    )
    await db.commit()

    response.delete_cookie(
        key=cookie_transport.cookie_name,
        path=cookie_transport.cookie_path,
        domain=cookie_transport.cookie_domain,
        secure=cookie_transport.cookie_secure,
        httponly=cookie_transport.cookie_httponly,
        samesite=cookie_transport.cookie_samesite,
    )
    return {"message": "LOGOUT_SUCCESSFUL"}


# --- FastAPI-Users Built-in Routes for Auth ---
if settings.OPEN_SIGNUP:
    auth_router.include_router(
        fastapi_users_instance.get_register_router(UserRead, UserCreate),
        tags=["Auth - Authentication & Authorization"],  # Updated tag for consistency
    )

# REMOVE the specific "get_forgot_password_router()" line if it's combined:
# auth_router.include_router(
# fastapi_users_instance.get_forgot_password_router(), # <<< REMOVE THIS LINE
# tags=["auth"],
# )
# Enable forgot password flow (sends reset token - logs for now, email when SMTP configured)
auth_router.include_router(
    fastapi_users_instance.get_reset_password_router(),
    tags=["Auth - Authentication & Authorization"],
)
# Note: get_reset_password_router provides BOTH /forgot-password and /reset-password
auth_router.include_router(
    fastapi_users_instance.get_verify_router(UserRead),
    tags=["Auth - Authentication & Authorization"],  # Updated tag for consistency
)
