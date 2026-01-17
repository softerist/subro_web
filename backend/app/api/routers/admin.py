# backend/app/api/routers/admin.py
import logging
import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select  # For SQLAlchemy 1.4+ style select
from sqlalchemy.orm import selectinload

# Project-specific imports
from app.core.config import settings  # Ensures settings is available
from app.core.log_utils import sanitize_for_log as _sanitize_for_log
from app.core.users import (
    UserManager,  # For type hinting
    current_active_superuser,
    get_current_active_admin_user,
    get_user_manager,
)
from app.db.models.app_settings import AppSettings
from app.db.models.user import User  # For ORM operations and type hinting
from app.db.session import get_async_session
from app.schemas.user import AdminUserUpdate, UserCreate, UserRead, UserRole  # Pydantic schemas

logger = logging.getLogger(__name__)


# --- Pydantic Schemas for Settings ---
class OpenSignupResponse(BaseModel):
    open_signup: bool


class OpenSignupUpdate(BaseModel):
    open_signup: bool


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
        logger.warning("Admin action attempted on non-existent user_id: %s", user_id)
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
) -> Sequence[User]:
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
    # nosemgrep: python.fastapi.db.generic-sql-fastapi.generic-sql-fastapi, python.tars.fastapi.sql.aiosqlite.fastapi-without-url-path-aiosqlite-sqli - SQLAlchemy ORM uses bound parameters; skip/limit are validated ints
    result = await session.execute(stmt)
    users = result.scalars().all()
    logger.info("Admin listed %d users (skip=%d, limit=%d).", len(users), skip, limit)
    return users


@admin_router.get(
    "/users/{user_id}",
    response_model=UserRead,
    summary="Get specific user details (Admin/Superuser only)",
    description="Retrieves details for a specific user by their ID.",
)
async def get_user_by_id_admin(
    target_user: User = Depends(get_target_user_or_404),
) -> User:
    """Retrieves details for a specific user by their ID."""
    logger.info("Admin retrieved details for user_id: %s", target_user.id)
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
) -> User:
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
    if user_create.role == UserRole.ADMIN:
        user_create.is_superuser = True
    elif user_create.is_superuser:
        user_create.role = UserRole.ADMIN

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
        logger.error("Error creating user by admin: %s", e, exc_info=True)
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
) -> User:
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
        logger.debug("Admin update attempt for user %s with no data.", target_user.id)
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
                # nosemgrep: python-logger-credential-disclosure - logs action, not actual credentials
                logger.info("Admin reset password for user %s", target_user.id)

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
                    logger.info("Admin disabled MFA for user %s", target_user.id)

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
                    "Admin changing '%s' for user %s from '%s' to '%s'",
                    key,
                    target_user.id,
                    current_value,
                    value,
                )
        else:
            logger.warning(
                "Admin attempt to update non-existent attribute '%s' on user %s",
                key,
                target_user.id,
            )

    if made_changes:
        try:
            session.add(target_user)
            await session.commit()
            await session.refresh(target_user)
            logger.info(
                "Admin successfully updated user_id: %s. Changes: %s",
                target_user.id,
                list(update_data_dict.keys()),
            )
        except Exception as e:  # Catching a general Exception here
            await session.rollback()
            logger.error(
                "Database error updating user %s by admin: %s",
                target_user.id,
                e,
                exc_info=True,
            )
            # This is where B904 applies
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,  # Or 500 if truly an internal DB issue not resolvable by client
                detail="UPDATE_USER_FAILED_DATABASE_ERROR",  # More specific detail
            ) from e  # Preserve original exception context
    else:
        logger.info(
            "Admin initiated update for user_id: %s, but no actual changes were made to tracked fields.",
            target_user.id,
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
) -> None:
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
            "Admin permanently deleted user: %s (ID: %s)",
            _sanitize_for_log(user_email_to_delete),
            user_id_to_delete,
        )
    except Exception as e:  # Catching a general Exception here
        await session.rollback()
        logger.error(
            "Error deleting user %s (ID: %s) by admin: %s",
            _sanitize_for_log(user_email_to_delete),
            user_id_to_delete,
            e,
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


# --- Open Signup Settings (Superuser Only) ---


@admin_router.get(
    "/settings/open-signup",
    response_model=OpenSignupResponse,
    summary="Get open signup setting (Superuser only)",
    description="Returns whether open user registration is enabled.",
    dependencies=[Depends(current_active_superuser)],
)
async def get_open_signup_setting(
    session: AsyncSession = Depends(get_async_session),
) -> OpenSignupResponse:
    """Get the current open signup setting."""
    try:
        result = await session.execute(select(AppSettings).where(AppSettings.id == 1))
        app_settings = result.scalar_one_or_none()

        if not app_settings:
            # Return default if settings don't exist yet
            return OpenSignupResponse(open_signup=False)

        return OpenSignupResponse(open_signup=app_settings.open_signup)
    except Exception as e:
        logger.error(f"Error retrieving open signup setting: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve setting: {e!s}",
        ) from e


@admin_router.patch(
    "/settings/open-signup",
    response_model=OpenSignupResponse,
    summary="Update open signup setting (Superuser only)",
    description="Enable or disable open user registration.",
    dependencies=[Depends(current_active_superuser)],
)
async def update_open_signup_setting(
    update_data: OpenSignupUpdate,
    current_user: User = Depends(current_active_superuser),
    session: AsyncSession = Depends(get_async_session),
) -> OpenSignupResponse:
    """Update the open signup setting. Only superusers can change this."""
    result = await session.execute(select(AppSettings).where(AppSettings.id == 1))
    app_settings = result.scalar_one_or_none()

    if not app_settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="App settings not initialized. Please complete setup first.",
        )

    old_value = app_settings.open_signup
    app_settings.open_signup = update_data.open_signup

    # Audit Log
    from app.services import audit_service

    await audit_service.log_event(
        session,
        category="admin",
        action="admin.open_signup_changed",
        severity="warning",
        actor_user_id=current_user.id,
        details={
            "old_value": old_value,
            "new_value": update_data.open_signup,
        },
    )

    await session.commit()
    logger.info(
        "Superuser %s changed open_signup from %s to %s",
        _sanitize_for_log(current_user.email),
        old_value,
        update_data.open_signup,
    )

    return OpenSignupResponse(open_signup=app_settings.open_signup)
