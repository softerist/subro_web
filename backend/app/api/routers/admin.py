# backend/app/api/routers/admin.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import (  # Corrected import
    UserManager,  # Import UserManager type hint
    current_active_superuser,
    get_user_manager,
)
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.user import AdminUserUpdate, UserRead  # Use the admin schema for updates

admin_router = APIRouter(prefix="/admin", tags=["Admin - User Management"])


# Dependency to ensure the target user exists
async def get_user_or_404(
    user_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> User:
    """Dependency to fetch a user by ID or raise 404."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


@admin_router.get(
    "/users",
    response_model=list[UserRead],
    dependencies=[Depends(current_active_superuser)],  # Protect endpoint
    summary="List all users (Admin only)",
)
@admin_router.delete(
    "/users/{user_id}",
    # Consider changing response model if you want to return the updated user
    response_model=UserRead,  # Let's return the deactivated user state
    dependencies=[Depends(current_active_superuser)],  # Protect endpoint
    summary="Deactivate a user (Admin only)",  # Changed summary
)
async def deactivate_user_admin(  # Renamed function for clarity
    target_user: User = Depends(get_user_or_404),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Deactivates a user account by setting is_active=False.
    This prevents login but preserves the user record and history.
    """
    if not target_user.is_active:
        # Optional: Avoid redundant updates or return a specific status
        # raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already inactive.")
        return target_user  # Return current state if already inactive

    target_user.is_active = False
    session.add(target_user)
    await session.commit()
    await session.refresh(target_user)

    # Log the deactivation action (optional but good practice)
    # logger.info(f"Admin user {requesting_admin.id} deactivated user {target_user.id}")

    return target_user  # Return the updated user object


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
    dependencies=[Depends(current_active_superuser)],  # Protect endpoint
    summary="Get specific user details (Admin only)",
)
async def get_user(
    target_user: User = Depends(get_user_or_404),  # Use dependency to get user
):
    """Retrieves details for a specific user by their ID."""
    return target_user


@admin_router.patch(
    "/users/{user_id}",
    response_model=UserRead,
    dependencies=[Depends(current_active_superuser)],  # Protect endpoint
    summary="Update user details (Admin only)",
)
async def update_user_admin(
    update_data: AdminUserUpdate,  # Use the specific admin update schema
    target_user: User = Depends(get_user_or_404),
    user_manager: UserManager = Depends(get_user_manager),  # Get user manager
    session: AsyncSession = Depends(get_db_session),  # Session for saving
):
    """
    Updates a user's details (role, active status, etc.) as an administrator.
    """
    # Use the user_manager.update method - it handles password hashing if needed
    # and other potential logic. We need to ensure it doesn't reject valid admin updates.
    # The default `fastapi-users` update might have restrictions.
    # A safer approach might be to update fields directly and save.

    # Direct update approach:
    update_data_dict = update_data.model_dump(exclude_unset=True)

    # --- Consistency Logic: Role vs is_superuser ---
    # Ensure 'is_superuser' reflects the 'admin' role
    if "role" in update_data_dict:
        target_user.is_superuser = update_data_dict["role"] == "admin"
        # If you only want role, you might remove is_superuser from the model/schema later
    elif "is_superuser" in update_data_dict:
        # If only is_superuser is set, sync role accordingly
        target_user.role = "admin" if update_data_dict["is_superuser"] else "standard"
    # --- End Consistency Logic ---

    # Update fields on the target_user object
    for key, value in update_data_dict.items():
        # Avoid overwriting is_superuser if role was the primary driver
        if key == "is_superuser" and "role" in update_data_dict:
            continue
        setattr(target_user, key, value)

    # Special handling for password if included (though unusual for admin update)
    if update_data_dict.get("password"):
        hashed_password = user_manager.password_helper.hash(update_data_dict["password"])
        target_user.hashed_password = hashed_password

    session.add(target_user)
    await session.commit()
    await session.refresh(target_user)

    return target_user


@admin_router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(current_active_superuser)],  # Protect endpoint
    summary="Delete a user (Admin only)",
)
async def delete_user_admin(
    target_user: User = Depends(get_user_or_404),
    user_manager: UserManager = Depends(
        get_user_manager
    ),  # Might be needed if using manager.delete
    session: AsyncSession = Depends(get_db_session),
):
    """
    Deletes a user account. Consider implementing soft delete instead for safety.
    """
    # Option 1: Hard Delete (using session) - Be careful!
    await session.delete(target_user)
    await session.commit()

    # Option 2: Hard Delete (using user_manager) - Check if it exists/works as expected
    # await user_manager.delete(target_user)

    # Option 3: Soft Delete (Recommended)
    # Requires adding an 'is_deleted' flag or similar to the User model
    # target_user.is_active = False
    # target_user.is_deleted = True # Assuming flag exists
    # session.add(target_user)
    # await session.commit()

    return None  # Return None for 204 status code
