# backend/app/api/routers/passkey.py
"""
Passkey (WebAuthn) API endpoints for passwordless authentication.

Provides endpoints for:
- Registering new passkeys (requires authentication)
- Authenticating with passkeys (public, like login)
- Managing passkeys (list, rename, delete)
"""

import logging
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn.helpers import (
    parse_authentication_credential_json,
    parse_registration_credential_json,
)

from app.core.auth_dependencies import require_recent_auth
from app.core.log_utils import sanitize_for_log as _sanitize_for_log
from app.core.rate_limit import get_real_client_ip, limiter
from app.core.security import current_active_user
from app.core.security_logger import security_log
from app.core.users import cookie_transport, get_access_token_jwt_strategy
from app.db.models.user import User
from app.db.session import get_async_session
from app.services import passkey_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/passkey", tags=["Passkey - WebAuthn Authentication"])


# --- Redis Dependency ---
async def get_redis() -> "AsyncGenerator[Redis, None]":
    """Get Redis client for challenge storage."""
    from app.core.config import settings

    redis = Redis.from_url(
        f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/3",
        decode_responses=False,
    )
    try:
        yield redis
    finally:
        await redis.aclose()


# --- Schemas ---


class RegistrationOptionsResponse(BaseModel):
    """WebAuthn registration options to pass to browser."""

    rp: dict
    user: dict
    challenge: str
    pubKeyCredParams: list[dict]
    timeout: int
    excludeCredentials: list[dict]
    authenticatorSelection: dict
    attestation: str


class RegistrationVerifyRequest(BaseModel):
    """Request to verify a registration response."""

    credential: dict = Field(..., description="Credential from navigator.credentials.create()")
    device_name: str | None = Field(None, max_length=255, description="User-friendly name")


class AuthenticationOptionsRequest(BaseModel):
    """Request for authentication options."""

    email: str | None = Field(None, description="Email for non-discoverable flow (optional)")


class AuthenticationOptionsResponse(BaseModel):
    """WebAuthn authentication options to pass to browser."""

    challenge: str
    timeout: int
    rpId: str
    allowCredentials: list[dict]
    userVerification: str


class AuthenticationVerifyRequest(BaseModel):
    """Request to verify an authentication response."""

    credential: dict = Field(..., description="Credential from navigator.credentials.get()")


class PasskeyResponse(BaseModel):
    """Passkey information for display."""

    id: str
    device_name: str | None
    created_at: str | None
    last_used_at: str | None
    backup_eligible: bool
    backup_state: bool


class PasskeyStatusResponse(BaseModel):
    """Passkey status for user."""

    passkey_count: int
    passkeys: list[PasskeyResponse]


class RenameRequest(BaseModel):
    """Request to rename a passkey."""

    name: str = Field(..., min_length=1, max_length=255)


# --- Registration Endpoints (Authenticated) ---


@router.post(
    "/register/options",
    response_model=RegistrationOptionsResponse,
    summary="Get passkey registration options",
)
@limiter.limit("5/minute")
async def get_registration_options(
    request: Request,  # noqa: ARG001
    current_user: Annotated[User, Depends(current_active_user)],
    _step_up: Annotated[User, Depends(require_recent_auth(300))],  # Step-up auth required
    db: Annotated[AsyncSession, Depends(get_async_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict:
    """
    Get WebAuthn registration options.

    Returns options to be passed to navigator.credentials.create() in the browser.
    Requires authentication.
    """
    options = await passkey_service.get_registration_options(db, redis, current_user)
    return options


@router.post(
    "/register/verify",
    response_model=PasskeyResponse,
    summary="Verify and complete passkey registration",
)
@limiter.limit("5/minute")
async def verify_registration(
    request: Request,
    body: RegistrationVerifyRequest,
    current_user: Annotated[User, Depends(current_active_user)],
    _step_up: Annotated[User, Depends(require_recent_auth(300))],  # Step-up auth required
    db: Annotated[AsyncSession, Depends(get_async_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict:
    """
    Verify the registration response and store the passkey.

    Call this after navigator.credentials.create() returns successfully.
    """
    try:
        # Parse credential from dict
        credential = parse_registration_credential_json(body.credential)

        passkey = await passkey_service.verify_registration(
            db=db,
            redis=redis,
            user=current_user,
            credential=credential,
            device_name=body.device_name,
        )

        logger.info(
            "Passkey registered for user %s from %s",
            _sanitize_for_log(current_user.email),
            get_real_client_ip(request),
        )

        return {
            "id": str(passkey.id),
            "device_name": passkey.device_name,
            "created_at": passkey.created_at.isoformat() if passkey.created_at else None,
            "last_used_at": None,
            "backup_eligible": passkey.backup_eligible,
            "backup_state": passkey.backup_state,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.exception("Passkey registration failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed. Please try again.",
        ) from e


# --- Authentication Endpoints (Public) ---


@router.post(
    "/login/options",
    response_model=AuthenticationOptionsResponse,
    summary="Get passkey authentication options",
)
@limiter.limit("10/minute")
async def get_authentication_options(
    request: Request,  # noqa: ARG001 - Required by rate limiter
    db: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis),
) -> dict:
    """
    Get WebAuthn authentication options for discoverable credentials.

    SECURITY HARDENING:
    - No email/user lookup (constant-time response)
    - Always returns empty allowCredentials
    - Prevents timing attacks and user enumeration

    Returns options to be passed to navigator.credentials.get() in the browser.
    The browser/authenticator will find matching credentials by RP ID.
    """
    options = await passkey_service.get_authentication_options(db, redis)
    return options


@router.post(
    "/login/verify",
    summary="Verify passkey authentication and login",
)
@limiter.limit("5/minute")
async def verify_authentication(
    request: Request,
    response: Response,
    body: AuthenticationVerifyRequest,
    db: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis),
) -> dict:
    """
    Verify the authentication response and return tokens.

    Call this after navigator.credentials.get() returns successfully.
    Returns access token on success.
    """
    from app.api.routers.auth import _create_manual_refresh_token

    try:
        # Parse credential from dict
        credential = parse_authentication_credential_json(body.credential)

        user = await passkey_service.verify_authentication(
            db=db,
            redis=redis,
            credential=credential,
        )

        # Generate tokens (same as password login)
        access_token_strategy = get_access_token_jwt_strategy()
        access_token = await access_token_strategy.write_token(user)

        refresh_token_data = {"sub": str(user.id)}
        refresh_token = _create_manual_refresh_token(data=refresh_token_data)

        # Set refresh token cookie
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

        # Log successful passkey login
        client_ip = get_real_client_ip(request)
        security_log.login_success(client_ip, str(user.id), method="passkey")

        logger.info(
            "Passkey login successful for user %s from %s",
            _sanitize_for_log(user.email),
            _sanitize_for_log(client_ip),
        )

        return {"access_token": access_token, "token_type": "bearer"}

    except ValueError as e:
        client_ip = get_real_client_ip(request)
        security_log.passkey_failed(client_ip)
        logger.warning(
            "Passkey authentication failed from %s: %s",
            _sanitize_for_log(client_ip),
            str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.exception("Passkey authentication error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed. Please try again.",
        ) from e


# --- Management Endpoints (Authenticated) ---


@router.get(
    "/list",
    response_model=PasskeyStatusResponse,
    summary="List user's passkeys",
)
async def list_passkeys(
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict:
    """Get all passkeys for the current user."""
    passkeys = await passkey_service.list_user_passkeys(db, current_user)

    return {
        "passkey_count": len(passkeys),
        "passkeys": [
            {
                "id": pk["id"],
                "device_name": pk["device_name"],
                "created_at": pk["created_at"],
                "last_used_at": pk["last_used_at"],
                "backup_eligible": pk["backup_eligible"],
                "backup_state": pk["backup_state"],
            }
            for pk in passkeys
        ],
    }


@router.put(
    "/{passkey_id}/name",
    summary="Rename a passkey",
)
async def rename_passkey(
    passkey_id: str,
    body: RenameRequest,
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict:
    """Rename a passkey to a new user-friendly name."""
    success = await passkey_service.rename_passkey(db, current_user, passkey_id, body.name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Passkey not found.",
        )

    return {"status": "renamed", "name": body.name}


@router.delete(
    "/{passkey_id}",
    summary="Delete a passkey",
)
async def delete_passkey(
    passkey_id: str,
    current_user: Annotated[User, Depends(current_active_user)],
    _step_up: Annotated[User, Depends(require_recent_auth(300))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict:
    """
    Delete a passkey.

    Note: Users can delete all passkeys since passwords remain as fallback.
    """
    success = await passkey_service.delete_passkey(db, current_user, passkey_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Passkey not found.",
        )

    return {"status": "deleted"}
