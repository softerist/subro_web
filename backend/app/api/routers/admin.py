# backend/app/api/routers/admin.py
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select  # For SQLAlchemy 1.4+ style select

# Project-specific imports
from app.core.config import settings  # Ensures settings is available
from app.core.users import (
    UserManager,  # For type hinting
    current_active_superuser,
    get_user_manager,
)
from app.db.models.user import User  # For ORM operations and type hinting
from app.db.session import get_async_session
from app.schemas.user import AdminUserUpdate, UserRead  # Pydantic schemas

logger = logging.getLogger(__name__)


admin_router = APIRouter(
    prefix="/admin",
    tags=["Admin - User Management"],
    dependencies=[Depends(current_active_superuser)],  # Protects all routes in this router
)


# --- Dependency to fetch a user by ID or raise 404 ---
async def get_target_user_or_404(
    user_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)
) -> User:
    """Dependency to fetch a user by ID or raise 404 Not Found."""
    user = await session.get(User, user_id)
    if not user:
        logger.warning(f"Admin action attempted on non-existent user_id: {user_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")
    return user


# --- Admin User Management Routes ---


@admin_router.get(
    "/users",
    response_model=list[UserRead],
    summary="List all users (Admin only)",
    description="Retrieves a paginated list of all users, ordered by creation date (descending).",
)
async def list_users_admin(
    session: AsyncSession = Depends(get_async_session),
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination."),
    limit: int = Query(
        100,
        ge=1,
        le=settings.DEFAULT_PAGINATION_LIMIT_MAX,
        description="Maximum number of records to return.",
    ),
):
    """Retrieves a list of all users with pagination, ordered by creation date."""
    # Assuming User.created_at exists and is a DateTime field
    # Ensure User.created_at exists or change the order_by clause
    # For example, if User model doesn't have created_at directly, use User.id or another sortable field.
    # If User.created_at does exist and is correctly typed, this is fine.
    stmt = (
        select(User)
        .offset(skip)
        .limit(limit)
        .order_by(
            User.created_at.desc() if hasattr(User, "created_at") else User.id.desc()
        )  # Defensive check
    )
    result = await session.execute(stmt)
    users = result.scalars().all()
    logger.info(f"Admin listed {len(users)} users (skip={skip}, limit={limit}).")
    return users


@admin_router.get(
    "/users/{user_id}",
    response_model=UserRead,
    summary="Get specific user details (Admin only)",
    description="Retrieves details for a specific user by their ID.",
)
async def get_user_by_id_admin(
    target_user: User = Depends(get_target_user_or_404),
):
    """Retrieves details for a specific user by their ID."""
    logger.info(f"Admin retrieved details for user_id: {target_user.id}")
    return target_user


@admin_router.patch(
    "/users/{user_id}",
    response_model=UserRead,
    summary="Update user details (Admin only)",
    description=(
        "Updates a user's details such as email, active status, superuser status, or password. "
        "The User model's validation logic (e.g., @validates decorator) should handle "
        "consistency if 'is_superuser' is linked to a 'role' field."
    ),
)
async def update_user_by_id_admin(
    update_data: AdminUserUpdate,
    target_user: User = Depends(get_target_user_or_404),
    user_manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Updates a user's details (e.g., email, active status, superuser status, password) as an administrator.
    """
    update_data_dict = update_data.model_dump(exclude_unset=True)
    made_changes = False

    if not update_data_dict:
        logger.debug(f"Admin update attempt for user {target_user.id} with no data.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="NO_UPDATE_DATA_PROVIDED"
        )

    for key, value in update_data_dict.items():
        if hasattr(target_user, key):
            current_value = getattr(target_user, key)
            if key == "password":
                if value:  # Only hash and update if a new password string is provided
                    new_hashed_password = user_manager.password_helper.hash(value)
                    if target_user.hashed_password != new_hashed_password:
                        target_user.hashed_password = new_hashed_password
                        made_changes = True
                        logger.debug(f"Admin changing password for user {target_user.id}")
            elif current_value != value:
                setattr(target_user, key, value)
                made_changes = True
                logger.debug(
                    f"Admin changing '{key}' for user {target_user.id} from '{current_value}' to '{value}'"
                )
        else:
            logger.warning(
                f"Admin attempt to update non-existent attribute '{key}' on user {target_user.id}"
            )

    if made_changes:
        try:
            session.add(target_user)
            await session.commit()
            await session.refresh(target_user)
            logger.info(
                f"Admin successfully updated user_id: {target_user.id}. Changes: {list(update_data_dict.keys())}"
            )
        except Exception as e:  # Catching a general Exception here
            await session.rollback()
            logger.error(
                f"Database error updating user {target_user.id} by admin: {e}", exc_info=True
            )
            # This is where B904 applies
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,  # Or 500 if truly an internal DB issue not resolvable by client
                detail="UPDATE_USER_FAILED_DATABASE_ERROR",  # More specific detail
            ) from e  # Preserve original exception context
    else:
        logger.info(
            f"Admin initiated update for user_id: {target_user.id}, but no actual changes were made to tracked fields."
        )

    return target_user


@admin_router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete a user (Admin only)",
    description=(
        "Permanently deletes a user account from the database. This is a destructive operation. "
        "Consider deactivating users via a PATCH request for reversible actions."
    ),
    response_class=Response,  # Ensures no response body for 204
)
async def delete_user_by_id_admin(
    target_user: User = Depends(get_target_user_or_404),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Permanently deletes a user account.
    WARNING: This is a destructive operation.
    """
    user_id_to_delete = target_user.id
    user_email_to_delete = target_user.email

    try:
        await session.delete(target_user)
        await session.commit()
        logger.info(
            f"Admin permanently deleted user: {user_email_to_delete} (ID: {user_id_to_delete})"
        )
    except Exception as e:  # Catching a general Exception here
        await session.rollback()
        logger.error(
            f"Error deleting user {user_email_to_delete} (ID: {user_id_to_delete}) by admin: {e}",
            exc_info=True,
        )
        # This is where B904 applies
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DELETE_USER_FAILED_DATABASE_ERROR",
        ) from e  # Preserve original exception context

    # For 204, FastAPI will automatically handle no content if the function returns None
    # or if response_class=Response is set and the function has no explicit return value
    # that would become the body. So, explicitly returning None is good practice.
    return None
