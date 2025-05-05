# backend/app/api/routers/admin.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status  # Added Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import (
    UserManager,
    current_active_superuser,
    get_user_manager,
)
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.user import AdminUserUpdate, UserRead

admin_router = APIRouter(prefix="/admin", tags=["Admin - User Management"])


# Dependency to ensure the target user exists
async def get_user_or_404(
    user_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> User:
    """Dependency to fetch a user by ID or raise 404."""
    user = await session.get(User, user_id)  # Use session.get for primary key lookup
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


# --- Corrected Route Order ---


@admin_router.get(
    "/users",
    response_model=list[UserRead],  # Use List from typing
    dependencies=[Depends(current_active_superuser)],
    summary="List all users (Admin only)",
)
async def list_users(
    session: AsyncSession = Depends(get_db_session),
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(100, ge=1, le=200, description="Maximum number of records to return"),
):
    """Retrieves a list of all users with pagination."""
    result = await session.execute(
        select(User).offset(skip).limit(limit).order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return users


@admin_router.get(
    "/users/{user_id}",
    response_model=UserRead,
    dependencies=[Depends(current_active_superuser)],
    summary="Get specific user details (Admin only)",
)
async def get_user(
    target_user: User = Depends(get_user_or_404),
):
    """Retrieves details for a specific user by their ID."""
    return target_user


@admin_router.patch(
    "/users/{user_id}",
    response_model=UserRead,
    dependencies=[Depends(current_active_superuser)],
    summary="Update user details (Admin only)",
)
async def update_user_admin(
    update_data: AdminUserUpdate,
    target_user: User = Depends(get_user_or_404),
    user_manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Updates a user's details (role, active status, etc.) as an administrator.
    Ensures consistency between 'role' and 'is_superuser'.
    """
    update_data_dict = update_data.model_dump(exclude_unset=True)
    made_changes = False

    # Apply updates directly to the model instance
    for key, value in update_data_dict.items():
        if hasattr(target_user, key) and getattr(target_user, key) != value:
            # Special handling for password
            if key == "password":
                if value:  # Only hash if a new password is provided
                    hashed_password = user_manager.password_helper.hash(value)
                    target_user.hashed_password = hashed_password
                    made_changes = True
            else:
                setattr(target_user, key, value)
                made_changes = True

    # --- Consistency Logic: Role vs is_superuser ---
    # If role was changed, ensure is_superuser matches
    if "role" in update_data_dict:
        new_superuser_status = update_data_dict["role"] == "admin"
        if target_user.is_superuser != new_superuser_status:
            target_user.is_superuser = new_superuser_status
            made_changes = True
    # If is_superuser was changed, ensure role matches
    elif "is_superuser" in update_data_dict:
        new_role = "admin" if update_data_dict["is_superuser"] else "standard"
        if target_user.role != new_role:
            target_user.role = new_role
            made_changes = True
    # --- End Consistency Logic ---

    if made_changes:
        session.add(target_user)
        await session.commit()
        await session.refresh(target_user)

    return target_user


@admin_router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(current_active_superuser)],
    summary="Permanently delete a user (Admin only)",
    # No response body for 204
    response_class=Response,  # Set response_class to Response for 204
)
async def delete_user_admin(
    target_user: User = Depends(get_user_or_404),
    session: AsyncSession = Depends(get_db_session),
    # user_manager: UserManager = Depends(get_user_manager), # Not needed for direct delete
):
    """
    Permanently deletes a user account from the database.
    Consider using soft delete (deactivation) via the PATCH endpoint instead for most cases.
    """
    await session.delete(target_user)
    await session.commit()

    # Return None or an empty Response for 204
    return None  # FastAPI handles returning 204 correctly when status_code is set and body is None


# --- Removed the conflicting deactivate_user_admin DELETE route ---
# Deactivation should be done via PATCH /users/{user_id} by setting is_active=False
