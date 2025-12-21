# backend/app/api/routers/settings.py
"""
Admin-only endpoints for managing application settings.

These endpoints require authentication and admin privileges.
"""

import logging
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import current_active_superuser
from app.crud.crud_app_settings import crud_app_settings
from app.db.models.deepl_usage import DeepLUsage
from app.db.models.user import User
from app.db.session import get_async_session
from app.schemas.app_settings import SettingsRead, SettingsUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get(
    "",
    response_model=SettingsRead,
    summary="Get current application settings",
    description="Returns all settings with sensitive values masked. Admin only.",
)
async def get_settings(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_superuser),
) -> SettingsRead:
    """
    Get current application settings.

    Sensitive fields (API keys, passwords) are masked in the response.
    To update a sensitive field, you must provide the new value explicitly.

    **Requires admin privileges.**
    """
    logger.debug(f"Settings retrieved by admin user: {current_user.email}")
    return await crud_app_settings.to_read_schema(db)


@router.put(
    "",
    response_model=SettingsRead,
    summary="Update application settings",
    description="Update one or more settings. Values are encrypted before storage.",
)
async def update_settings(
    settings_update: SettingsUpdate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_superuser),
) -> SettingsRead:
    """
    Update application settings.

    Only fields that are explicitly provided will be updated.
    Sensitive fields are encrypted before being stored in the database.

    **Requires admin privileges.**

    Note: Changes take effect immediately. Active Celery tasks will use
    the new settings on their next job.
    """
    try:
        await crud_app_settings.update(db, obj_in=settings_update)
        logger.info(f"Settings updated by admin user: {current_user.email}")
    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update settings: {e!s}",
        ) from e

    # Post-update: Validate DeepL keys and update usage stats
    try:
        from sqlalchemy import select

        # Get the plain text keys to validate
        decrypted_keys = await crud_app_settings.get_decrypted_value(db, "deepl_api_keys")

        if decrypted_keys and isinstance(decrypted_keys, list):
            for key in decrypted_keys:
                if not key or not isinstance(key, str) or not key.strip():
                    continue

                # Validate key with DeepL
                usage_data = await _validate_deepl_key(key)

                # Update Database Record using upsert pattern
                identifier = key[-4:] if len(key) >= 4 else key

                # Check if record exists
                result = await db.execute(
                    select(DeepLUsage).where(DeepLUsage.key_identifier == identifier)
                )
                record = result.scalar_one_or_none()

                if not record:
                    record = DeepLUsage(key_identifier=identifier)
                    db.add(record)
                    await db.flush()  # Flush to catch any constraint errors early

                # Update fields
                if usage_data["valid"]:
                    record.character_count = usage_data["character_count"]
                    record.character_limit = usage_data["character_limit"]
                    record.valid = True
                else:
                    record.valid = False

                record.last_updated = datetime.now(UTC)

            await db.commit()

    except Exception as e:
        # Rollback to clean up the session state
        await db.rollback()
        logger.error(f"Failed to validate DeepL keys after update: {e}")

    return await crud_app_settings.to_read_schema(db)


async def _validate_deepl_key(api_key: str) -> dict:
    """Helper to validate a DeepL key and return usage stats."""
    api_key = api_key.strip()
    is_free_key = ":fx" in api_key
    url = "https://api-free.deepl.com/v2/usage" if is_free_key else "https://api.deepl.com/v2/usage"
    headers = {"Authorization": f"DeepL-Auth-Key {api_key}"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                return {
                    "valid": True,
                    "character_count": data.get("character_count", 0),
                    "character_limit": data.get("character_limit", 0),
                }
            else:
                return {"valid": False, "error": f"Status {response.status_code}"}
        except Exception as e:
            logger.warning(f"DeepL validation error for {api_key[-4:]}: {e}")
            return {"valid": False, "error": str(e)}


@router.get(
    "/raw/{field_name}",
    summary="Get raw (decrypted) value for a single setting",
    description="For internal use. Returns the actual decrypted value.",
    include_in_schema=False,  # Hide from OpenAPI docs
)
async def get_raw_setting(
    field_name: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_superuser),
) -> dict:
    """
    Get the raw (decrypted) value for a specific setting.

    This endpoint is hidden from the API docs and intended for
    debugging or specific internal use cases.

    **Requires admin privileges.**
    """
    value = await crud_app_settings.get_decrypted_value(db, field_name)
    logger.debug(f"Raw setting '{field_name}' accessed by: {current_user.email}")
    return {"field": field_name, "value": value}


# Removed test_deepl_key endpoint as validation is now automatic on save
