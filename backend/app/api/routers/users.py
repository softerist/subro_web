# backend/app/api/routers/users.py
from fastapi import APIRouter

# Import the configured fastapi_users instance and schemas
from app.core.users import fastapi_users_instance  # FastAPIUsers[User, uuid.UUID]
from app.schemas.user import UserRead, UserUpdate  # Pydantic schemas for User

# from app.db.models.user import User # Not strictly needed here for router definition
# from app.core.users import current_active_user # Not strictly needed here unless defining custom routes

router = APIRouter(
    prefix="/users",  # All routes here will be under /api/users/... (when combined with main app's /api prefix)
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
    fastapi_users_instance.get_users_router(UserRead, UserUpdate, requires_verification=False)
    # No additional prefix here, as the routes like "/me" and "/{id}" are relative to this router's prefix.
    # Tags can be inherited or overridden if needed, but the router's tag is usually sufficient.
)

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
