# backend/app/api/routers/users.py
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

# Import the configured fastapi_users instance and schemas
from app.core.api_key_auth import (
    generate_api_key,
    get_api_key_last4,
    get_api_key_prefix,
    hash_api_key,
)
from app.core.config import settings
from app.core.security import current_active_user
from app.core.users import fastapi_users_instance  # FastAPIUsers[User, uuid.UUID]
from app.db.models.api_key import ApiKey
from app.db.models.user import User
from app.db.session import get_async_session
from app.schemas.api_key import ApiKeyCreateResponse, ApiKeyRevokeResponse
from app.schemas.user import UserRead, UserUpdate  # Pydantic schemas for User

# from app.db.models.user import User # Not strictly needed here for router definition
# from app.core.users import current_active_user # Not strictly needed here unless defining custom routes

router = APIRouter(
    # prefix="/users",  # REMOVED: Managed by include_router in main.py to avoid double prefixing (/users/users/...)
    tags=["Users - User Management"],  # Tag for OpenAPI documentation, more specific tag
)


# Include the standard users routes from fastapi-users
# This provides:
# - GET /me: Get current user
# - PATCH /me: Update current user
# - GET /{id}: Get user by id (by default, superuser protected for viewing others)
# - PATCH /{id}: Update user by id (superuser protected)
# - DELETE /{id}: Delete user by id (superuser protected)
#
# We set requires_verification=False assuming email verification is not a hard requirement for now.
# If you implement email verification later and want to enforce it for certain actions,
# you might use a different dependency like `current_active_verified_user` in custom endpoints
# or configure fastapi-users differently if it supports per-route verification requirements.
router.include_router(
    fastapi_users_instance.get_users_router(UserRead, UserUpdate),
    tags=["Users - User Management"],
)
# Custom endpoint to generate/regenerate API key


@router.post(
    "/me/api-key",
    response_model=ApiKeyCreateResponse,
    summary="Generate or Regenerate API Key",
    description="Generates a new API key for the current user and revokes prior keys.",
)
async def regenerate_api_key(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(current_active_user)],
) -> ApiKeyCreateResponse:
    if not settings.API_KEY_PEPPER:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key generation is not configured.",
        )
    new_key = generate_api_key()
    now = datetime.now(UTC)

    # Revoke any existing keys for this user
    await db.execute(
        update(ApiKey)
        .where(ApiKey.user_id == current_user.id, ApiKey.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    current_user.api_key = None

    api_key_record = ApiKey(
        user_id=current_user.id,
        name="Default",
        scopes=None,
        prefix=get_api_key_prefix(new_key),
        last4=get_api_key_last4(new_key),
        hashed_key=hash_api_key(new_key),
        created_at=now,
    )

    db.add(api_key_record)
    db.add(current_user)
    await db.commit()
    await db.refresh(api_key_record)

    new_record_data = ApiKeyCreateResponse(
        id=api_key_record.id,
        api_key=new_key,
        preview=api_key_record.preview,
        created_at=api_key_record.created_at,
    )

    # Audit Log
    from app.services import audit_service

    await audit_service.log_event(
        db,
        category="security",
        action="security.api_key_created",
        severity="warning",
        actor_user_id=current_user.id,
        details={
            "key_id": str(api_key_record.id),
            "prefix": api_key_record.prefix,
            "scopes": api_key_record.scopes,
        },
    )

    return new_record_data


@router.delete(
    "/me/api-key",
    response_model=ApiKeyRevokeResponse,
    summary="Revoke API Key",
    description="Revokes all active API keys for the current user.",
)
async def revoke_api_key(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(current_active_user)],
) -> ApiKeyRevokeResponse:
    now = datetime.now(UTC)
    result = await db.execute(
        update(ApiKey)
        .where(ApiKey.user_id == current_user.id, ApiKey.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    current_user.api_key = None
    db.add(current_user)
    await db.commit()
    rowcount = getattr(result, "rowcount", 0) or 0
    if rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active API keys to revoke.",
        )
    # Audit Log
    from app.services import audit_service

    await audit_service.log_event(
        db,
        category="security",
        action="security.api_key_revoked",
        severity="info",
        actor_user_id=current_user.id,
        details={"reason": "user_requested"},
    )
    return ApiKeyRevokeResponse(revoked=True)


# Example of a custom user-related endpoint (if needed in the future):
# from app.db.models.user import User # Would be needed for type hinting current_user
# from app.core.users import current_active_user # Would be needed for dependency

# @router.get("/me/preferences", summary="Get current user's preferences")
# async def get_my_preferences(current_user: User = Depends(current_active_user)):
#     """
#     Retrieves the preferences for the currently authenticated user.
#     (This is a placeholder example)
#     """
#     # In a real application, you might fetch preferences from the database or another service
#     return {"preferences": {"theme": "dark", "notifications_enabled": True}, "user_id": current_user.id}
