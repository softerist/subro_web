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
from app.services.api_validation import validate_all_settings

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
async def update_settings(  # noqa: C901
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
        # Pre-process masked DeepL keys to resolve them to original values
        if settings_update.deepl_api_keys is not None:
            existing_keys = await crud_app_settings.get_decrypted_value(db, "deepl_api_keys")
            if existing_keys and isinstance(existing_keys, list):
                resolved_keys = []
                for key in settings_update.deepl_api_keys:
                    if isinstance(key, str) and "***" in key:
                        # Attempt to resolve masked key
                        # Extract suffix (assuming standard masking of last 8 chars)
                        clean_key = key.replace("*", "")
                        suffix = clean_key if len(clean_key) >= 4 else key[-8:]

                        found_key = next(
                            (k for k in existing_keys if str(k).endswith(suffix)), None
                        )
                        resolved_keys.append(found_key if found_key else key)
                    else:
                        resolved_keys.append(key)
                settings_update.deepl_api_keys = resolved_keys

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
                # We use SHA256 hash of the key as identifier to avoid collisions (e.g. same suffix)
                import hashlib

                key_hash = hashlib.sha256(key.strip().encode()).hexdigest()

                # Check if record exists
                result = await db.execute(
                    select(DeepLUsage).where(DeepLUsage.key_identifier == key_hash)
                )
                record = result.scalar_one_or_none()

                if not record:
                    record = DeepLUsage(key_identifier=key_hash)
                    db.add(record)
                    await db.flush()  # Flush to catch any constraint errors early

                # Update fields
                if usage_data["valid"]:
                    record.character_count = usage_data["character_count"]
                    record.character_limit = usage_data["character_limit"]
                    record.valid = True
                else:
                    record.character_count = 0
                    record.character_limit = 0
                    record.valid = False

                record.last_updated = datetime.now(UTC)

            await db.commit()

    except Exception as e:
        # Rollback to clean up the session state
        await db.rollback()
        logger.error(f"Failed to validate DeepL keys after update: {e}")

    # Post-update: Validate TMDB, OMDB, and OpenSubtitles credentials
    try:
        await validate_all_settings(db)
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to validate API credentials after update: {e}")

    # Post-update: Process Google Cloud credentials if provided
    google_error = None
    try:
        google_error = await _process_google_cloud_credentials(db, settings_update)
    except Exception as e:
        logger.error(f"Failed to process Google Cloud credentials: {e}")

    response = await crud_app_settings.to_read_schema(db)
    if google_error:
        response.google_cloud_error = google_error
    return response


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
            logger.warning(f"DeepL validation error for ...{api_key[-8:]}: {e}")
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


async def _process_google_cloud_credentials(  # noqa: C901
    db: AsyncSession, settings_update: SettingsUpdate
) -> str | None:
    """Process and validate Google Cloud credentials if provided. Returns error message if failed."""
    import json

    from sqlalchemy import select

    from app.db.models.app_settings import AppSettings

    creds_json = settings_update.google_cloud_credentials

    # If explicitly set to empty string, clear the credentials
    if creds_json == "":
        result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
        settings = result.scalar_one_or_none()
        if settings:
            settings.google_cloud_credentials = None
            settings.google_cloud_project_id = None
            settings.google_cloud_valid = None
            await db.commit()
            logger.info("Google Cloud credentials removed")
            await db.commit()
            logger.info("Google Cloud credentials removed")
        return None

    if not creds_json:
        return None

    # Parse JSON and validate structure
    try:
        creds = json.loads(creds_json)
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid Google Cloud credentials JSON: {e}")
        return f"Invalid JSON: {e}"

    # Check required fields
    required_fields = ["type", "project_id", "private_key", "client_email"]
    missing = [f for f in required_fields if f not in creds]
    if missing:
        logger.warning(f"Google Cloud credentials missing required fields: {missing}")
        # Still save but mark as invalid
        result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
        settings = result.scalar_one_or_none()
        if settings:
            settings.google_cloud_valid = False
            settings.google_cloud_project_id = creds.get("project_id")
            await db.commit()
        if settings:
            settings.google_cloud_valid = False
            settings.google_cloud_project_id = creds.get("project_id")
            await db.commit()
        return f"Missing required fields: {', '.join(missing)}"

    # Validate type is service_account
    if creds.get("type") != "service_account":
        logger.warning(f"Google Cloud credentials type is not service_account: {creds.get('type')}")
        result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
        settings = result.scalar_one_or_none()
        if settings:
            settings.google_cloud_valid = False
            settings.google_cloud_project_id = creds.get("project_id")
            await db.commit()
        if settings:
            settings.google_cloud_valid = False
            settings.google_cloud_project_id = creds.get("project_id")
            await db.commit()
        return f"Invalid type: {creds.get('type')} (expected 'service_account')"

    # Extract and save project_id
    project_id = creds.get("project_id")
    result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
    settings = result.scalar_one_or_none()

    if settings:
        settings.google_cloud_project_id = project_id

        # Perform live validation check
        try:
            from google.cloud import translate_v3 as translate
            from google.oauth2 import service_account

            # Create credentials and client
            credentials = service_account.Credentials.from_service_account_info(creds)
            client = translate.TranslationServiceClient(credentials=credentials)

            # Make a lightweight API call to verify access
            parent = f"projects/{project_id}/locations/global"
            client.get_supported_languages(parent=parent, display_language_code="en")

            settings.google_cloud_valid = True
            logger.info(
                f"Google Cloud credentials validated successfully for project: {project_id}"
            )

        except ImportError:
            logger.warning("Google Cloud libraries not installed, skipping live validation")
            # Fallback to structural validity if libraries missing
            settings.google_cloud_valid = True
        except Exception as e:
            logger.error(f"Google Cloud live validation failed: {e}")
            settings.google_cloud_valid = False

            # Map common errors to friendly messages
            raw_error = str(e)
            if "401" in raw_error and "invalid authentication credentials" in raw_error:
                error_msg = (
                    "Authentication Failed: The provided Service Account key is invalid or expired."
                )
            elif "Cloud Translation API" in raw_error and "not enabled" in raw_error:
                error_msg = "API Not Enabled: The Cloud Translation API is not enabled for this project. Please enable it in the Google Cloud Console."
            elif "404" in raw_error and ("Project" in raw_error or "project" in raw_error):
                error_msg = "Project Not Found: The specified Project ID does not exist or the Service Account lacks access to it."
            else:
                # Fallback generic message to prevent leaking details/IDs
                error_msg = "Validation Failed: Unable to verify credentials with Google Cloud. Please check your Project ID and permissions."

        await db.commit()
        logger.info(f"Google Cloud credentials saved for project: {creds.get('project_id')}")
        return error_msg if "error_msg" in locals() else None
