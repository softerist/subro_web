# backend/app/api/routers/mfa.py
"""
MFA (Multi-Factor Authentication) API endpoints.

Provides endpoints for:
- Setting up TOTP MFA
- Verifying TOTP codes
- Managing trusted devices
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import current_active_user
from app.core.users import UserManager, get_user_manager
from app.db.models.user import User
from app.db.session import get_async_session
from app.services import mfa_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/mfa", tags=["MFA - Multi-Factor Authentication"])

# Cookie name for trusted device token
TRUSTED_DEVICE_COOKIE = "subTrustedDevice"
TRUSTED_DEVICE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days in seconds


# --- Schemas ---


class MfaSetupResponse(BaseModel):
    """Response from MFA setup initiation."""

    secret: str = Field(..., description="TOTP secret for manual entry")
    qr_code: str = Field(..., description="Base64-encoded QR code PNG")
    backup_codes: list[str] = Field(..., description="Backup codes for recovery")


class MfaVerifySetupRequest(BaseModel):
    """Request to verify and enable MFA."""

    secret: str = Field(..., description="The secret from setup")
    code: str = Field(..., min_length=6, max_length=8, description="TOTP code from authenticator")
    backup_codes: list[str] = Field(..., description="Backup codes to store")


class MfaVerifyRequest(BaseModel):
    """Request to verify MFA during login."""

    code: str = Field(..., min_length=6, max_length=12, description="TOTP or backup code")
    trust_device: bool = Field(default=False, description="Remember this device for 30 days")


class MfaDisableRequest(BaseModel):
    """Request to disable MFA."""

    password: str = Field(..., min_length=1, description="Current password for verification")


class MfaStatusResponse(BaseModel):
    """MFA status for current user."""

    mfa_enabled: bool
    trusted_devices_count: int


class TrustedDeviceResponse(BaseModel):
    """Information about a trusted device."""

    id: str
    device_name: str | None
    ip_address: str | None
    created_at: str
    last_used_at: str | None
    expires_at: str
    is_expired: bool


# --- Endpoints ---


@router.get("/status", response_model=MfaStatusResponse, summary="Get MFA status")
async def get_mfa_status(
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> MfaStatusResponse:
    """Get the current MFA status for the authenticated user."""
    devices = await mfa_service.get_user_trusted_devices(db, current_user)
    active_devices = [d for d in devices if not d["is_expired"]]

    return MfaStatusResponse(
        mfa_enabled=current_user.mfa_enabled,
        trusted_devices_count=len(active_devices),
    )


@router.post("/setup", response_model=MfaSetupResponse, summary="Initialize MFA setup")
async def setup_mfa(
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> MfaSetupResponse:
    """
    Initialize MFA setup for the current user.

    Returns a QR code and backup codes. The user should:
    1. Scan the QR code with an authenticator app
    2. Enter the 6-digit code to verify
    3. Save the backup codes securely
    """
    if current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled. Disable it first to reconfigure.",
        )

    setup_data = await mfa_service.setup_mfa(db, current_user)

    return MfaSetupResponse(
        secret=setup_data["secret"],
        qr_code=setup_data["qr_code"],
        backup_codes=setup_data["backup_codes"],
    )


@router.post("/verify-setup", response_model=MfaStatusResponse, summary="Verify and enable MFA")
async def verify_mfa_setup(
    request_data: MfaVerifySetupRequest,
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> MfaStatusResponse:
    """
    Verify the TOTP code and enable MFA.

    This confirms the user has successfully configured their authenticator app.
    """
    success = await mfa_service.enable_mfa(
        db,
        current_user,
        request_data.secret,
        request_data.code,
        request_data.backup_codes,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code. Please try again.",
        )

    return MfaStatusResponse(
        mfa_enabled=True,
        trusted_devices_count=0,
    )


@router.post("/verify", summary="Verify MFA during login")
async def verify_mfa_login(
    request: Request,
    response: Response,
    request_data: MfaVerifyRequest,
    mfa_user_id: Annotated[str | None, Cookie()] = None,
    db: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager),
):
    """
    Verify MFA code during login flow.

    This endpoint is called after successful password authentication
    when the user has MFA enabled.

    The mfa_user_id cookie should be set by the login endpoint.
    """
    from app.api.routers.auth import _create_manual_refresh_token
    from app.core.users import cookie_transport, get_access_token_jwt_strategy

    if not mfa_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA session not found. Please start login again.",
        )

    # Get user
    try:
        user = await user_manager.get(mfa_user_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA session.",
        ) from e

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found or inactive.",
        )

    # Verify MFA code
    is_valid = await mfa_service.verify_mfa(db, user, request_data.code)

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code.",
        )

    # Clear MFA session cookie
    response.delete_cookie("mfa_user_id")

    # Handle trusted device
    if request_data.trust_device:
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("User-Agent", "Unknown device")
        device_name = user_agent[:100] if user_agent else None

        token = await mfa_service.trust_device(db, user, device_name, client_ip)

        response.set_cookie(
            key=TRUSTED_DEVICE_COOKIE,
            value=token,
            max_age=TRUSTED_DEVICE_MAX_AGE,
            httponly=True,
            secure=True,
            samesite="strict",
        )

    # Generate tokens (same as login endpoint)
    access_token_strategy = get_access_token_jwt_strategy()
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

    logger.info(f"MFA verification successful for user: {user.email}")

    return {"access_token": access_token, "token_type": "bearer"}


@router.delete("", summary="Disable MFA")
async def disable_mfa(
    request_data: MfaDisableRequest,
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user_manager: UserManager = Depends(get_user_manager),
) -> MfaStatusResponse:
    """
    Disable MFA for the current user.

    Requires password verification for security.
    """
    if not current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled.",
        )

    # Verify password

    class FakeCredentials:
        def __init__(self, username: str, password: str):
            self.username = username
            self.password = password

    credentials = FakeCredentials(current_user.email, request_data.password)
    verified_user = await user_manager.authenticate(credentials)

    if not verified_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password.",
        )

    await mfa_service.disable_mfa(db, current_user)

    return MfaStatusResponse(
        mfa_enabled=False,
        trusted_devices_count=0,
    )


@router.get("/devices", response_model=list[TrustedDeviceResponse], summary="List trusted devices")
async def list_trusted_devices(
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[TrustedDeviceResponse]:
    """Get all trusted devices for the current user."""
    devices = await mfa_service.get_user_trusted_devices(db, current_user)
    return [TrustedDeviceResponse(**d) for d in devices]


@router.delete("/devices/{device_id}", summary="Revoke a trusted device")
async def revoke_trusted_device(
    device_id: str,
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict:
    """Remove trust from a specific device."""
    success = await mfa_service.revoke_trusted_device(db, current_user, device_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found.",
        )

    return {"status": "revoked"}
