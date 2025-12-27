# backend/app/api/routers/users.py
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Import the configured fastapi_users instance and schemas
from app.core.api_key_auth import generate_api_key
from app.core.security import current_active_user
from app.core.users import fastapi_users_instance  # FastAPIUsers[User, uuid.UUID]
from app.db.models.user import User
from app.db.session import get_async_session
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
    response_model=UserRead,
    summary="Generate or Regenerate API Key",
    description="Generates a new API key for the current user. Invalidates any previous key.",
)
async def regenerate_api_key(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(current_active_user)],
) -> User:
    new_key = generate_api_key()

    # Update user with new key
    current_user.api_key = new_key
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    return current_user


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
