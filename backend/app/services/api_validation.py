import hashlib
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.crud_app_settings import crud_app_settings
from app.db.models.deepl_usage import DeepLUsage
from app.services import audit_service

logger = logging.getLogger(__name__)


async def validate_tmdb(api_key: str) -> dict:
    """
    Validate TMDB API key by making a test request.
    Returns: dict with 'valid' (True/False/None) and 'rate_limited' (bool)
    """
    result = {"valid": None, "rate_limited": False}

    if not api_key or not api_key.strip():
        # Empty key, consider it not configured/None
        return result

    api_key = api_key.strip()
    url = f"https://api.themoviedb.org/3/configuration?api_key={api_key}"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=5.0)
            if response.status_code == 200:
                result["valid"] = True
                return result

            if response.status_code == 429:
                # Rate limit exceeded
                result["valid"] = False  # Or keep True if we consider it "valid but throttled"?
                # Standard practice: if rate limited, the key is structurally valid (auth worked enough to count quota),
                # but for usage purposes it's currently failing.
                # However, returning valid=False matches OMDB logic where usable=False.
                # The rate_limited flag adds the context.
                result["rate_limited"] = True
                result["valid"] = False
                return result

            if response.status_code in (401, 403):
                result["valid"] = False
                return result

            return result
        except httpx.TransportError as e:
            logger.warning(f"TMDB connection error: {e}")
            return result
        except Exception as e:
            logger.warning(f"TMDB validation error: {e}")
            return result


async def validate_omdb(api_key: str) -> dict:
    """
    Validate OMDB API key.
    Returns: dict with 'valid' (True/False/None) and 'rate_limited' (bool)
    """
    result = {"valid": None, "rate_limited": False}

    if not api_key or not api_key.strip():
        return result

    api_key = api_key.strip()
    url = f"http://www.omdbapi.com/?apikey={api_key}&t=test"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=5.0)
            if response.status_code in (200, 401, 403):
                try:
                    data = response.json()
                except ValueError:
                    # Not JSON
                    result["valid"] = False
                    return result

                error_msg = data.get("Error", "")

                if data.get("Response") == "False":
                    # Check for rate limit error
                    if "Request limit" in error_msg or "limit reached" in error_msg.lower():
                        result["valid"] = False
                        result["rate_limited"] = True
                    # Check for invalid key
                    elif "Invalid API" in error_msg:
                        result["valid"] = False
                        result["rate_limited"] = False
                    else:
                        # Some other error, default to invalid
                        result["valid"] = False
                else:
                    # Success
                    result["valid"] = True
                    result["rate_limited"] = False
                return result

            # Other status codes
            return result
            return result
        except httpx.TransportError as e:
            logger.warning(f"OMDB connection error: {e}")
            return result
        except Exception as e:
            logger.warning(f"OMDB validation error: {e}")
            return result


async def validate_opensubtitles(  # noqa: C901
    api_key: str, username: str | None, password: str | None
) -> dict:
    """
    Validate OpenSubtitles credentials.
    Returns a dict with:
    - key_valid: bool | None
    - login_valid: bool | None
    - rate_limited: bool
    - level: str | None (subscription level e.g. "VIP Member")
    - vip: bool | None
    - allowed_downloads: int | None
    """
    result = {
        "key_valid": None,
        "login_valid": None,
        "rate_limited": False,
        "level": None,
        "vip": None,
        "allowed_downloads": None,
    }

    if not api_key:
        return result

    api_key = api_key.strip()
    if username:
        username = username.strip()
    if password:
        password = password.strip()

    # If we have full credentials, try login
    if username and password:
        login_url = "https://api.opensubtitles.com/api/v1/login"
        logout_url = "https://api.opensubtitles.com/api/v1/logout"

        headers = {
            "Api-Key": api_key,
            "Content-Type": "application/json",
            "User-Agent": f"{settings.USER_AGENT_APP_NAME} v{settings.USER_AGENT_APP_VERSION}",
        }
        payload = {"username": username, "password": password}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(login_url, headers=headers, json=payload, timeout=10.0)
                if response.status_code == 200:
                    data = response.json()
                    token = data.get("token")
                    user = data.get("user", {})

                    # Extract subscription info
                    result["level"] = user.get("level")
                    result["vip"] = user.get("vip")
                    result["allowed_downloads"] = user.get("allowed_downloads")

                    if token:
                        # Logout
                        logout_headers = {
                            "Api-Key": api_key,
                            "Authorization": f"Bearer {token}",
                            "User-Agent": f"{settings.USER_AGENT_APP_NAME} v{settings.USER_AGENT_APP_VERSION}",
                        }
                        try:
                            await client.delete(logout_url, headers=logout_headers, timeout=5.0)
                        except Exception:
                            pass
                        result["key_valid"] = True
                        result["login_valid"] = True
                        return result
                    return result

                if response.status_code == 429:
                    # Rate limited - daily quota exceeded
                    logger.warning("OpenSubtitles rate limit exceeded (429)")
                    result["key_valid"] = True
                    result["login_valid"] = True
                    result["rate_limited"] = True
                    return result

                if response.status_code == 403:
                    result["key_valid"] = False
                    return result

                if response.status_code == 401:
                    result["key_valid"] = True
                    result["login_valid"] = False
                    return result

                return result
            except httpx.TransportError as e:
                logger.warning(f"OpenSubtitles connection error: {e}")
                return result
            except Exception as e:
                logger.warning(f"OpenSubtitles validation error: {e}")
                return result

    # Fallback: Validate Key Only (if missing login details)
    check_url = "https://api.opensubtitles.com/api/v1/infos/formats"
    headers = {
        "Api-Key": api_key,
        "User-Agent": f"{settings.USER_AGENT_APP_NAME} v{settings.USER_AGENT_APP_VERSION}",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(check_url, headers=headers, timeout=5.0)
            if response.status_code == 200:
                result["key_valid"] = True
                return result
            if response.status_code == 429:
                logger.warning("OpenSubtitles rate limit exceeded (429)")
                result["key_valid"] = True
                result["rate_limited"] = True
                return result
            if response.status_code == 403:
                result["key_valid"] = False
                return result
            return result
        except Exception as e:
            logger.warning(f"OpenSubtitles key check error: {e}")
            return result


async def validate_deepl(api_key: str) -> dict:
    """Helper to validate a DeepL key and return usage stats."""
    api_key = api_key.strip()
    is_free_key = ":fx" in api_key
    url = "https://api-free.deepl.com/v2/usage" if is_free_key else "https://api.deepl.com/v2/usage"
    headers = {"Authorization": f"DeepL-Auth-Key {api_key}"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            status_code = response.status_code
            if status_code == 200:
                data = response.json()
                return {
                    "valid": True,
                    "character_count": data.get("character_count", 0),
                    "character_limit": data.get("character_limit", 0),
                    "status_code": status_code,
                }
            if status_code == 429:
                return {
                    "valid": False,
                    "rate_limited": True,
                    "error": "Rate limit exceeded (429)",
                    "retry_after": int(response.headers.get("Retry-After", 1)),
                    "status_code": status_code,
                }
            else:
                return {
                    "valid": False,
                    "error": f"Status {status_code}: {response.text}",
                    "status_code": status_code,
                }
        except Exception as e:
            return {"valid": False, "error": str(e), "status_code": None}


async def validate_google_cloud(creds_json: str) -> tuple[bool | None, str | None, str | None]:
    """
    Validate Google Cloud JSON credentials.
    Returns: (is_valid, project_id, error_message)
    """
    import json

    if not creds_json or not creds_json.strip():
        return None, None, None

    try:
        creds = json.loads(creds_json)
    except json.JSONDecodeError as e:
        return False, None, f"Invalid JSON: {e}"

    required_fields = ["type", "project_id", "private_key", "client_email"]
    missing = [f for f in required_fields if f not in creds]
    if missing:
        return False, creds.get("project_id"), f"Missing required fields: {', '.join(missing)}"

    if creds.get("type") != "service_account":
        return (
            False,
            creds.get("project_id"),
            f"Invalid type: {creds.get('type')} (expected 'service_account')",
        )

    project_id = creds.get("project_id")

    # Live validation
    try:
        from google.cloud import translate_v3 as translate
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_info(creds)
        client = translate.TranslationServiceClient(credentials=credentials)

        # Make a lightweight API call to verify access
        parent = f"projects/{project_id}/locations/global"
        client.get_supported_languages(parent=parent, display_language_code="en")

        return True, project_id, None

    except ImportError:
        logger.warning("Google Cloud libraries not installed, skipping live validation")
        return True, project_id, None
    except Exception as e:
        logger.warning(f"Google Cloud live validation failed: {e}")
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
            error_msg = "Validation Failed: Unable to verify credentials with Google Cloud. Please check your Project ID and permissions."
        return False, project_id, error_msg


async def validate_deepl_keys_background(  # noqa: C901
    keys: list[str], db_session_factory
) -> None:
    """
    Background task to validate a list of DeepL keys.
    Uses its own DB session since it runs in the background.
    Respects rate limits.
    """
    import asyncio

    logger.info(f"Starting background validation for {len(keys)} DeepL keys.")

    # Use a new session
    async with db_session_factory() as db:
        for i, key in enumerate(keys):
            if not key or not isinstance(key, str) or not key.strip():
                continue

            # Check if key is already valid/recently updated to avoid redundant work?
            # ideally yes, but force-check is better for consistency if requested.

            logger.info(f"Validating key: {key[:5]}...")
            usage_data = await validate_deepl(key)

            # Handle rate limiting retry
            if not usage_data["valid"] and "Rate limit" in str(usage_data.get("error")):
                retry_after = usage_data.get("retry_after", 1) + 1
                logger.warning(f"Rate limit 429 for key {key[:8]}... Waiting {retry_after}s.")
                await asyncio.sleep(retry_after)
                # Retry once
                usage_data = await validate_deepl(key)

            key_hash = hashlib.sha256(key.strip().encode()).hexdigest()

            # Upsert
            result = await db.execute(
                select(DeepLUsage).where(DeepLUsage.key_identifier == key_hash)
            )
            record = result.scalar_one_or_none()

            status_code = usage_data.get("status_code")
            if usage_data.get("valid"):
                if not record:
                    record = DeepLUsage(key_identifier=key_hash)
                    db.add(record)
                record.character_count = usage_data["character_count"]
                record.character_limit = usage_data["character_limit"]
                record.valid = True
            elif usage_data.get("rate_limited"):
                if not record:
                    record = DeepLUsage(key_identifier=key_hash)
                    db.add(record)
                # Treat rate limiting as transient; keep key valid and preserve counts if possible.
                if record.character_limit == 0:
                    record.character_limit = 500000
                record.valid = True
            else:
                # Only mark invalid for hard failures; otherwise leave existing state.
                if status_code in {403, 456}:
                    if not record:
                        record = DeepLUsage(key_identifier=key_hash)
                        db.add(record)
                    record.character_count = 0
                    record.character_limit = 0
                    record.valid = False
                else:
                    logger.warning(
                        "DeepL validation failed for key %s due to transient error (%s); preserving existing status.",
                        key[:8],
                        usage_data.get("error"),
                    )
                    continue

            record.last_updated = datetime.now(UTC)

            try:
                await db.commit()
            except Exception as e:
                await db.rollback()
                # Check for IntegrityError (race condition on insert)
                if "IntegrityError" in str(type(e)) or "UniqueViolationError" in str(e):
                    logger.warning(f"Race condition saving key {key[:8]}... Retrying update.")
                    # Retry logic: Fetch existing, update, commit
                    result = await db.execute(
                        select(DeepLUsage).where(DeepLUsage.key_identifier == key_hash)
                    )
                    record = result.scalar_one_or_none()
                    if record:
                        if usage_data["valid"]:
                            record.character_count = usage_data["character_count"]
                            record.character_limit = usage_data["character_limit"]
                            record.valid = True
                        else:
                            record.character_count = 0
                            record.character_limit = 0
                            record.valid = False

                        record.last_updated = datetime.now(UTC)
                        try:
                            await db.commit()
                        except Exception as retry_e:
                            logger.error(
                                f"Failed to retry save usage for key {key[:8]}...: {retry_e}"
                            )
                else:
                    logger.error(f"Failed to save usage for key {key[:8]}...: {e}")

            # Avoid hitting rate limits between keys
            if i < len(keys) - 1:
                await asyncio.sleep(0.2)

    logger.info("Background DeepL validation completed.")


async def validate_all_settings(db: AsyncSession) -> None:
    """
    Fetch current settings, validate configured credentials, and update validation status in DB.
    For DeepL keys, triggers a background validation task instead of blocking.
    """
    try:
        settings_row = await crud_app_settings.get(db)

        # Get decrypted values
        tmdb_key = await crud_app_settings.get_decrypted_value(db, "tmdb_api_key")
        omdb_key = await crud_app_settings.get_decrypted_value(db, "omdb_api_key")
        os_api_key = await crud_app_settings.get_decrypted_value(db, "opensubtitles_api_key")
        os_username = await crud_app_settings.get_decrypted_value(db, "opensubtitles_username")
        os_password = await crud_app_settings.get_decrypted_value(db, "opensubtitles_password")

        # 1. Validate General API keys (fast)
        if tmdb_key:
            tmdb_result = await validate_tmdb(tmdb_key)
            settings_row.tmdb_valid = tmdb_result["valid"]
            settings_row.tmdb_rate_limited = tmdb_result["rate_limited"]
        else:
            settings_row.tmdb_valid = None
            settings_row.tmdb_rate_limited = None

        # OMDB validation with direct rate limit detection
        if omdb_key:
            omdb_result = await validate_omdb(omdb_key)
            settings_row.omdb_valid = omdb_result["valid"]
            settings_row.omdb_rate_limited = omdb_result["rate_limited"]
        else:
            settings_row.omdb_valid = None
            settings_row.omdb_rate_limited = None

        if os_api_key:
            u_arg = str(os_username) if os_username else None
            p_arg = str(os_password) if os_password else None

            os_result = await validate_opensubtitles(str(os_api_key), u_arg, p_arg)
            settings_row.opensubtitles_key_valid = os_result["key_valid"]
            settings_row.opensubtitles_valid = os_result["login_valid"]
            settings_row.opensubtitles_rate_limited = os_result["rate_limited"]
            settings_row.opensubtitles_level = os_result["level"]
            settings_row.opensubtitles_vip = os_result["vip"]
            settings_row.opensubtitles_allowed_downloads = os_result["allowed_downloads"]
        else:
            settings_row.opensubtitles_key_valid = None
            settings_row.opensubtitles_valid = None
            settings_row.opensubtitles_rate_limited = None
            settings_row.opensubtitles_level = None
            settings_row.opensubtitles_vip = None
            settings_row.opensubtitles_allowed_downloads = None

        # 2. Validate Google Cloud Translation
        google_creds = await crud_app_settings.get_decrypted_value(db, "google_cloud_credentials")
        if google_creds:
            is_valid, project_id, _error_msg = await validate_google_cloud(google_creds)
            settings_row.google_cloud_valid = is_valid
            settings_row.google_cloud_project_id = project_id
        else:
            # Check env fallback if DB is empty
            from app.core.config import settings as env_settings

            if getattr(env_settings, "GOOGLE_CREDENTIALS_PATH", None):
                # We don't perform live validation for env file path here to avoid blocking
                # but we mark as potentially valid if it exists.
                # Actually, better to leave as None or True based on config presence.
                # SettingsRead.google_cloud_valid handles the display logic for env.
                pass

        # --- Audit Log Enhancements ---
        await audit_service.log_event(
            db,
            category="security",
            action="security.api_validation",
            severity="info" if getattr(settings_row, "tmdb_valid", False) else "warning",
            details={
                "tmdb_valid": getattr(settings_row, "tmdb_valid", None),
                "omdb_valid": getattr(settings_row, "omdb_valid", None),
                "opensubtitles_valid": getattr(settings_row, "opensubtitles_valid", None),
                "google_cloud_valid": getattr(settings_row, "google_cloud_valid", None),
            },
        )

        await db.commit()

        # 3. Trigger DeepL Validation in Background
        # We need to get the keys first
        deepl_keys = await crud_app_settings.get_decrypted_value(db, "deepl_api_keys")
        logger.info(
            f"DeepL keys retrieved for validation: {type(deepl_keys)} - count: {len(deepl_keys) if isinstance(deepl_keys, list) else 'N/A'}"
        )

        if deepl_keys and isinstance(deepl_keys, list):
            # We need to pass the session maker, not the current session.
            import asyncio

            from app.db.session import FastAPISessionLocal

            if FastAPISessionLocal:
                logger.info(
                    f"Creating background task for {len(deepl_keys)} DeepL keys validation..."
                )
                asyncio.create_task(  # noqa: RUF006
                    validate_deepl_keys_background(deepl_keys, FastAPISessionLocal)
                )
                logger.info("Background task created successfully for DeepL validation.")
            else:
                logger.error(
                    "FastAPISessionLocal is None, cannot trigger DeepL background validation!"
                )
        else:
            logger.warning(f"No DeepL keys found to validate. deepl_keys = {deepl_keys}")

        logger.info(
            f"Validation status updated: TMDB={settings_row.tmdb_valid}, "
            f"OMDB={settings_row.omdb_valid}, "
            f"OS_Key={settings_row.opensubtitles_key_valid}, "
            f"OS_Login={settings_row.opensubtitles_valid}."
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to validate settings: {e}")
