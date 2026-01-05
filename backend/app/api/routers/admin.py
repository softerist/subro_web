# backend/app/api/routers/admin.py
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select  # For SQLAlchemy 1.4+ style select
from sqlalchemy.orm import selectinload

# Project-specific imports
from app.core.config import settings  # Ensures settings is available
from app.core.users import (
    UserManager,  # For type hinting
    get_current_active_admin_user,
    get_user_manager,
)
from app.db.models.user import User  # For ORM operations and type hinting
from app.db.session import get_async_session
from app.schemas.user import AdminUserUpdate, UserCreate, UserRead  # Pydantic schemas

logger = logging.getLogger(__name__)


admin_router = APIRouter(
    tags=["Admins - Admin Management"],
    dependencies=[Depends(get_current_active_admin_user)],  # Protects all routes in this router
)


# --- Dependency to fetch a user by ID or raise 404 ---
async def get_target_user_or_404(
    user_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)
) -> User:
    """Dependency to fetch a user by ID or raise 404 Not Found."""
    result = await session.execute(
        select(User).options(selectinload(User.api_keys)).where(User.id == user_id)
    )
    user = result.scalars().first()
    if not user:
        logger.warning(f"Admin action attempted on non-existent user_id: {user_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")
    return user


# --- Admin User Management Routes ---


@admin_router.get(
    "/users",
    tags=["Admins - Admin Management"],
    response_model=list[UserRead],
    summary="List all users (Admin/Superuser only)",
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
    summary="Get specific user details (Admin/Superuser only)",
    description="Retrieves details for a specific user by their ID.",
)
async def get_user_by_id_admin(
    target_user: User = Depends(get_target_user_or_404),
):
    """Retrieves details for a specific user by their ID."""
    logger.info(f"Admin retrieved details for user_id: {target_user.id}")
    return target_user


@admin_router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user (Admin/Superuser only)",
    description="Creates a new user with specified role and attributes. Only Superusers can create other Superusers.",
)
async def create_user_admin(
    user_create: UserCreate,
    user_manager: UserManager = Depends(get_user_manager),
    current_user: User = Depends(get_current_active_admin_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Creates a new user.
    """
    # Guard: Only superusers can create superusers
    if user_create.is_superuser and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Superusers can create other Superusers.",
        )

    # Ensure consistency between role and is_superuser
    if user_create.role == "admin":
        user_create.is_superuser = True
    elif user_create.is_superuser:
        user_create.role = "admin"

    try:
        created_user = await user_manager.create(user_create, safe=False)

        # Audit Log
        from app.services import audit_service

        await audit_service.log_event(
            session,
            category="auth",
            action="auth.user_created_by_admin",
            severity="info",
            actor_user_id=current_user.id,
            target_user_id=created_user.id,
            details={"role": created_user.role, "email": created_user.email},
        )
        await session.commit()
        return created_user
    except Exception as e:
        logger.error(f"Error creating user by admin: {e}", exc_info=True)
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"USER_CREATION_FAILED: {e!s}",
        ) from e


@admin_router.patch(
    "/users/{user_id}",
    response_model=UserRead,
    summary="Update user details (Admin/Superuser only)",
    description=(
        "Updates a user's details. Admins can update Standard users. "
        "Only Superusers can update other Superusers."
    ),
)
async def update_user_by_id_admin(  # noqa: C901
    update_data: AdminUserUpdate,
    target_user: User = Depends(get_target_user_or_404),
    current_user: User = Depends(get_current_active_admin_user),
    user_manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Updates a user's details. Enforces hierarchy: Admin cannot update Superuser.
    """
    # Guard Warning: Hierarchy Check
    if target_user.is_superuser and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot modify Superuser accounts.",
        )
    update_data_dict = update_data.model_dump(exclude_unset=True)
    made_changes = False

    if not update_data_dict:
        logger.debug(f"Admin update attempt for user {target_user.id} with no data.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="NO_UPDATE_DATA_PROVIDED"
        )

    if "role" in update_data_dict:
        update_data_dict["is_superuser"] = update_data_dict["role"] == "admin"
    elif "is_superuser" in update_data_dict:
        update_data_dict["role"] = "admin" if update_data_dict["is_superuser"] else "standard"

    # Handle password field specially (User model has 'hashed_password', not 'password')
    if "password" in update_data_dict:
        password_value = update_data_dict.pop("password")
        if password_value:
            new_hashed_password = user_manager.password_helper.hash(password_value)
            if target_user.hashed_password != new_hashed_password:
                target_user.hashed_password = new_hashed_password
                made_changes = True
                logger.info(f"Admin reset password for user {target_user.id}")

    for key, value in update_data_dict.items():
        if hasattr(target_user, key):
            current_value = getattr(target_user, key)
            if key == "mfa_enabled" and value is False:
                # Explicit logic to disable MFA and clear secrets
                if target_user.mfa_enabled:
                    target_user.mfa_enabled = False
                    target_user.mfa_secret = None
                    target_user.mfa_backup_codes = None
                    made_changes = True
                    logger.info(f"Admin disabled MFA for user {target_user.id}")

                    # Audit Log: MFA Reset
                    from app.services import audit_service

                    await audit_service.log_event(
                        session,
                        category="auth",
                        action="auth.mfa_reset_by_admin",
                        severity="warning",
                        actor_user_id=current_user.id,
                        target_user_id=target_user.id,
                        impersonator_id=current_user.id,
                        details={"reason": "admin_reset"},
                    )

            elif current_value != value:
                # Audit specific security changes before applying
                from app.services import audit_service

                if key == "status":
                    # Status change (active <-> suspended/banned)
                    # Note: We use 'ip_ban_removed' as proxy for unban, or add 'auth.account_unlocked'
                    # Better names:
                    action_name = "auth.account_suspended"
                    if value == "active" and current_value in ["suspended", "banned"]:
                        action_name = "auth.account_unlocked"  # or unbanned

                    await audit_service.log_event(
                        session,
                        category="auth",
                        action=action_name,
                        severity="warning" if value != "active" else "info",
                        actor_user_id=current_user.id,
                        target_user_id=target_user.id,
                        details={"old_status": current_value, "new_status": value},
                    )

                if key == "locked_until" and value is None and current_value is not None:
                    # Unlock
                    await audit_service.log_event(
                        session,
                        category="auth",
                        action="auth.account_unlocked",
                        severity="info",
                        actor_user_id=current_user.id,
                        target_user_id=target_user.id,
                        details={"reason": "admin_unlock"},
                    )

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
    current_user: User = Depends(get_current_active_admin_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Permanently deletes a user account.
    WARNING: This is a destructive operation.
    """
    # Guard Warning: Hierarchy Check
    if target_user.is_superuser and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot delete Superuser accounts.",
        )
    user_id_to_delete = target_user.id
    user_email_to_delete = target_user.email

    try:
        await session.delete(target_user)

        # Audit Log
        from app.services import audit_service

        await audit_service.log_event(
            session,
            category="auth",
            action="auth.user_deleted_by_admin",
            severity="critical",
            actor_user_id=current_user.id,
            target_user_id=user_id_to_delete,  # user object is deleted, but ID persists in audit log props
            details={"email": user_email_to_delete},
        )

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
