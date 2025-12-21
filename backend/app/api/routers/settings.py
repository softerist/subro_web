# backend/app/api/routers/settings.py
"""
Admin-only endpoints for managing application settings.

These endpoints require authentication and admin privileges.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import current_active_superuser
from app.crud.crud_app_settings import crud_app_settings
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

    return await crud_app_settings.to_read_schema(db)


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


@router.post(
    "/test-deepl-key",
    summary="Test a DeepL API key",
    description="Validates a DeepL API key by checking usage quota. Returns key info if valid.",
)
async def test_deepl_key(
    request: dict,
    current_user: User = Depends(current_active_superuser),
) -> dict:
    """
    Test if a DeepL API key is valid.

    Makes a request to DeepL's usage endpoint to verify the key.
    Returns usage information if valid, error message if not.

    **Requires admin privileges.**
    """
    import httpx

    api_key = request.get("api_key", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key is required",
        )

    # Determine if free or pro key
    is_free_key = ":fx" in api_key
    url = "https://api-free.deepl.com/v2/usage" if is_free_key else "https://api.deepl.com/v2/usage"
    headers = {"Authorization": f"DeepL-Auth-Key {api_key}"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)

            if response.status_code == 200:
                data = response.json()
                character_count = data.get("character_count", 0)
                character_limit = data.get("character_limit", 0)
                remaining = max(0, character_limit - character_count)

                logger.info(f"DeepL key validated by {current_user.email}: ...{api_key[-4:]}")
                return {
                    "valid": True,
                    "key_type": "free" if is_free_key else "pro",
                    "character_count": character_count,
                    "character_limit": character_limit,
                    "remaining": remaining,
                    "usage_percent": round((character_count / character_limit * 100), 1)
                    if character_limit > 0
                    else 0,
                }
            elif response.status_code == 403:
                return {"valid": False, "error": "Invalid API key or unauthorized"}
            elif response.status_code == 456:
                return {"valid": False, "error": "Quota exceeded for this key"}
            else:
                return {"valid": False, "error": f"Unexpected response: {response.status_code}"}

        except httpx.TimeoutException:
            return {"valid": False, "error": "Request timed out"}
        except httpx.RequestError as e:
            logger.error(f"Error testing DeepL key: {e}")
            return {"valid": False, "error": f"Connection error: {e!s}"}
