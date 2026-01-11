# backend/app/api/routers/onboarding.py
"""
Public endpoints for initial application setup.

These endpoints are accessible WITHOUT authentication, but are protected
by checking if setup has already been completed OR forced.
"""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi_users.exceptions import UserAlreadyExists, UserNotExists
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_user_manager
from app.core.users import UserManager
from app.crud.crud_app_settings import crud_app_settings
from app.db.models.app_settings import AppSettings
from app.db.session import get_async_session
from app.schemas.app_settings import (
    SetupComplete,
    SetupSkip,
    SetupStatus,
)
from app.schemas.user import UserCreate, UserUpdate
from app.services.api_validation import validate_all_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


def _require_onboarding_token(onboarding_token: str | None) -> None:
    if settings.ENVIRONMENT != "production":
        return
    # If ONBOARDING_TOKEN is not configured, allow onboarding to proceed without token
    # This is intentional for simpler deployments that don't need token protection
    if not settings.ONBOARDING_TOKEN:
        logger.warning("ONBOARDING_TOKEN is not configured. Onboarding endpoints are unprotected.")
        return
    # If ONBOARDING_TOKEN is configured, require it to match
    if not onboarding_token or onboarding_token != settings.ONBOARDING_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid onboarding token.",
        )


def _raise_setup_not_found() -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Not Found",
    )


async def _lock_app_settings_row(db: AsyncSession) -> None:
    await db.execute(select(AppSettings).where(AppSettings.id == 1).with_for_update())


async def _require_setup_state(db: AsyncSession) -> dict[str, bool]:
    await _lock_app_settings_row(db)
    state = await crud_app_settings.get_setup_state(db)
    if not state["setup_required"]:
        _raise_setup_not_found()
    return state


async def _save_setup_settings(db: AsyncSession, setup_data: SetupComplete) -> None:
    if not setup_data.settings:
        return

    try:
        await crud_app_settings.update(db, obj_in=setup_data.settings)
        logger.info("Settings saved during setup wizard.")

        if setup_data.settings.google_cloud_credentials:
            from app.api.routers.settings import _process_google_cloud_credentials

            try:
                await _process_google_cloud_credentials(db, setup_data.settings)
            except Exception as e:
                logger.warning(f"Failed to process Google Cloud credentials during setup: {e}")
    except Exception as e:
        logger.error(f"Failed to save settings during setup: {e}")
        # Don't fail the whole setup if settings save fails


async def _finalize_setup(db: AsyncSession, log_message: str) -> None:
    await crud_app_settings.populate_from_env_defaults(db)
    try:
        logger.info("Triggering initial validation for all settings...")
        await validate_all_settings(db)
    except Exception as e:
        logger.warning(f"Settings validation warnings during setup: {e}")
    await crud_app_settings.mark_setup_completed(db)
    logger.info(log_message)


def _resolve_skip_credentials(skip_data: SetupSkip | None) -> tuple[str | None, str | None]:
    if skip_data:
        has_email = bool(skip_data.admin_email)
        has_password = bool(skip_data.admin_password)
        if has_email != has_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Both email and password are required, or neither.",
            )
        if has_email:
            return skip_data.admin_email, skip_data.admin_password

    if settings.FIRST_SUPERUSER_EMAIL and settings.FIRST_SUPERUSER_PASSWORD:
        logger.info(
            f"Using FIRST_SUPERUSER_EMAIL from environment: {settings.FIRST_SUPERUSER_EMAIL}"
        )
        return settings.FIRST_SUPERUSER_EMAIL, settings.FIRST_SUPERUSER_PASSWORD

    if not settings.OPEN_SIGNUP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin credentials required when OPEN_SIGNUP is disabled. "
            "Provide credentials or set FIRST_SUPERUSER_EMAIL/PASSWORD env vars.",
        )

    return None, None


async def _create_admin_user(
    user_manager: UserManager, admin_email: str, admin_password: str
) -> None:
    admin_user = UserCreate(
        email=admin_email,
        password=admin_password,
        is_superuser=True,
        is_active=True,
        is_verified=True,
        role="admin",
    )
    try:
        created_user = await user_manager.create(admin_user, safe=False)
        logger.info(f"Admin user created via setup wizard: {created_user.email}")
    except UserAlreadyExists as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with email '{admin_email}' already exists.",
        ) from e
    except Exception as e:
        logger.error(f"Failed to create admin user during setup: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create admin user: {e!s}",
        ) from e


async def _upsert_admin_for_complete(
    user_manager: UserManager,
    db: AsyncSession,
    admin_email: str,
    admin_password: str,
    setup_completed: bool,
) -> None:
    try:
        existing_user = await user_manager.get_by_email(admin_email)
    except UserNotExists:
        await _create_admin_user(user_manager, admin_email, admin_password)
        return

    if setup_completed:
        logger.info(f"Forced setup: keeping existing password for {existing_user.email}")
        return

    user_update = UserUpdate(
        password=admin_password,
        is_superuser=True,
        is_active=True,
        is_verified=True,
    )
    await user_manager.update(user_update, existing_user, safe=True)
    existing_user.role = "admin"
    db.add(existing_user)
    logger.info(f"Updated existing admin during setup: {existing_user.email}")


async def _upsert_admin_for_skip(
    user_manager: UserManager,
    db: AsyncSession,
    admin_email: str,
    admin_password: str,
    setup_completed: bool,
) -> None:
    try:
        existing_user = await user_manager.get_by_email(admin_email)
    except UserNotExists:
        try:
            admin_user = UserCreate(
                email=admin_email,
                password=admin_password,
                is_superuser=True,
                is_active=True,
                is_verified=True,
                role="admin",
            )
            created_user = await user_manager.create(admin_user, safe=False)
            logger.info(f"Admin user created during skip: {created_user.email}")
        except UserAlreadyExists:
            logger.warning(f"Admin already exists during skip: {admin_email}")
        except Exception as e:
            logger.warning(f"Failed to create admin during skip: {e}")
        return

    if setup_completed:
        logger.info(f"Forced skip: keeping existing password for {existing_user.email}")
        return

    user_update = UserUpdate(
        password=admin_password,
        is_superuser=True,
        is_active=True,
        is_verified=True,
    )
    await user_manager.update(user_update, existing_user, safe=True)
    existing_user.role = "admin"
    db.add(existing_user)
    logger.info(f"Updated existing admin during skip: {existing_user.email}")


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

    Returns:
        setup_completed: True if wizard was completed
        setup_required: True if wizard should be shown (forced OR not completed)
        setup_forced: True if FORCE_INITIAL_SETUP is set
    """
    try:
        state = await crud_app_settings.get_setup_state(db)
        return SetupStatus(**state)
    except Exception as e:
        logger.error(f"Error retrieving setup status: {e}", exc_info=True)
        # We return a fallback status if DB fails, or raise 500?
        # Raising 500 allows frontend to see specific error if we return it in detail.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check setup status: {e!s}",
        ) from e


@router.post(
    "/complete",
    response_model=SetupStatus,
    summary="Complete the initial setup",
    description="Create admin user and save settings. Only works if setup is required.",
)
async def complete_setup(
    setup_data: SetupComplete,
    db: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager),
    onboarding_token: str | None = Header(default=None, alias="X-Onboarding-Token"),
) -> SetupStatus:
    """
    Complete the initial setup wizard.

    This endpoint:
    1. Checks if setup is required (setup_forced OR not setup_completed)
    2. Uses atomic locking to prevent concurrent completions
    3. Creates or updates the admin user (password update only if not completed)
    4. Saves settings and populates env defaults
    5. Validates settings (warnings only, doesn't block)
    6. Marks setup as completed

    Security: This endpoint is PUBLIC but protected by setup_required state.
    """
    _require_onboarding_token(onboarding_token)

    state = await _require_setup_state(db)
    await _upsert_admin_for_complete(
        user_manager,
        db,
        setup_data.admin_email,
        setup_data.admin_password,
        state["setup_completed"],
    )
    await _save_setup_settings(db, setup_data)
    await _finalize_setup(db, "Setup wizard completed successfully.")

    return SetupStatus(setup_completed=True, setup_required=False, setup_forced=False)


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
    onboarding_token: str | None = Header(default=None, alias="X-Onboarding-Token"),
) -> SetupStatus:
    """
    Skip the setup wizard and use environment variable defaults.

    Optionally creates an admin user if credentials are provided.
    Otherwise, falls back to FIRST_SUPERUSER_* env vars.

    Security: This endpoint is PUBLIC but protected by setup_required state.
    Fail-safe: Returns 400 if no credentials AND OPEN_SIGNUP is disabled.
    """
    _require_onboarding_token(onboarding_token)

    state = await _require_setup_state(db)
    admin_email, admin_password = _resolve_skip_credentials(skip_data)

    if admin_email and admin_password:
        await _upsert_admin_for_skip(
            user_manager,
            db,
            admin_email,
            admin_password,
            state["setup_completed"],
        )
    else:
        logger.warning(
            "No admin credentials provided and FIRST_SUPERUSER env vars not set. "
            "OPEN_SIGNUP is enabled, so skipping without admin."
        )

    await _finalize_setup(db, "Setup skipped. System will use environment variable defaults.")

    return SetupStatus(setup_completed=True, setup_required=False, setup_forced=False)
