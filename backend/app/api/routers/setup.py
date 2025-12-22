# backend/app/api/routers/setup.py
"""
Public endpoints for initial application setup.

These endpoints are accessible WITHOUT authentication, but are protected
by checking if setup has already been completed.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_user_manager
from app.core.users import UserManager
from app.crud.crud_app_settings import crud_app_settings
from app.db.session import get_async_session
from app.schemas.app_settings import (
    SetupComplete,
    SetupSkip,
    SetupStatus,
)
from app.schemas.user import UserCreate
from app.services.api_validation import validate_all_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/setup", tags=["Setup"])


@router.get(
    "/status",
    response_model=SetupStatus,
    summary="Check if initial setup is completed",
    description="Public endpoint to check if the application has been configured.",
)
async def get_setup_status(
    db: AsyncSession = Depends(get_async_session),
) -> SetupStatus:
    """
    Check if the initial setup wizard has been completed.

    This endpoint is PUBLIC and used by the frontend to determine
    whether to show the setup wizard or the login page.
    """
    is_completed = await crud_app_settings.get_setup_completed(db)
    return SetupStatus(setup_completed=is_completed)


@router.post(
    "/complete",
    response_model=SetupStatus,
    summary="Complete the initial setup",
    description="Create admin user and save settings. Only works if setup not completed.",
)
async def complete_setup(
    setup_data: SetupComplete,
    db: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager),
) -> SetupStatus:
    """
    Complete the initial setup wizard.

    This endpoint:
    1. Checks if setup is already completed (blocks if true)
    2. Creates the admin user
    3. Saves any provided settings
    4. Marks setup as completed

    Security: This endpoint is PUBLIC but can only be called ONCE
    (when setup_completed is False).
    """
    # Security check: Only allow if setup not completed
    is_completed = await crud_app_settings.get_setup_completed(db)
    if is_completed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup has already been completed. Use /settings endpoints to modify configuration.",
        )

    # Create admin user
    try:
        admin_user = UserCreate(
            email=setup_data.admin_email,
            password=setup_data.admin_password,
            is_superuser=True,
            is_active=True,
            is_verified=True,
            role="admin",
        )
        created_user = await user_manager.create(admin_user, safe=False)
        logger.info(f"Admin user created via setup wizard: {created_user.email}")
    except Exception as e:
        logger.error(f"Failed to create admin user during setup: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create admin user: {e!s}",
        ) from e

    # Save settings if provided
    if setup_data.settings:
        try:
            await crud_app_settings.update(db, obj_in=setup_data.settings)
            logger.info("Settings saved during setup wizard.")
        except Exception as e:
            logger.error(f"Failed to save settings during setup: {e}")
            # Don't fail the whole setup if settings save fails
            # Admin can update settings later

    # Populate any empty fields with env var defaults
    await crud_app_settings.populate_from_env_defaults(db)

    # Validate settings (including defaults if not provided)
    await validate_all_settings(db)

    # Mark setup as completed
    await crud_app_settings.mark_setup_completed(db)
    logger.info("Setup wizard completed successfully.")

    return SetupStatus(setup_completed=True)


@router.post(
    "/skip",
    response_model=SetupStatus,
    summary="Skip the setup wizard",
    description="Mark setup as complete without configuring settings (uses env defaults).",
)
async def skip_setup(
    skip_data: SetupSkip | None = None,
    db: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager),
) -> SetupStatus:
    """
    Skip the setup wizard and use environment variable defaults.

    Optionally creates an admin user if credentials are provided.
    Otherwise, the system will rely on initial_data.py bootstrap.

    Security: This endpoint is PUBLIC but can only be called ONCE.
    """
    # Security check
    is_completed = await crud_app_settings.get_setup_completed(db)
    if is_completed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup has already been completed.",
        )

    # Optionally create admin user
    if skip_data and skip_data.admin_email and skip_data.admin_password:
        try:
            admin_user = UserCreate(
                email=skip_data.admin_email,
                password=skip_data.admin_password,
                is_superuser=True,
                is_active=True,
                is_verified=True,
                role="admin",
            )
            created_user = await user_manager.create(admin_user, safe=False)
            logger.info(f"Admin user created during skip: {created_user.email}")
        except Exception as e:
            logger.warning(f"Failed to create admin during skip (may already exist): {e}")

    # Mark setup as completed (settings remain empty, system uses env defaults)
    await crud_app_settings.mark_setup_completed(db)

    # Populate any empty fields with env var defaults
    await crud_app_settings.populate_from_env_defaults(db)

    # Validate defaults from environment
    await validate_all_settings(db)

    logger.info("Setup skipped. System will use environment variable defaults.")

    return SetupStatus(setup_completed=True)
