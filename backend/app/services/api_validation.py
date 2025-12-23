import hashlib
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_app_settings import crud_app_settings
from app.db.models.deepl_usage import DeepLUsage

logger = logging.getLogger(__name__)


async def validate_tmdb(api_key: str) -> bool | None:
    """
    Validate TMDB API key by making a test request.
    Returns:
        True: Valid
        False: Invalid (401/403)
        None: Network error / Unknown
    """
    if not api_key or not api_key.strip():
        return None  # Changed from False to None if empty? No, keep behavior consistent.
        # If user explicitly clears it, it's "Not Configured" -> None.

    api_key = api_key.strip()
    url = f"https://api.themoviedb.org/3/configuration?api_key={api_key}"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=5.0)
            if response.status_code == 200:
                return True
            if response.status_code in (401, 403):
                return False
            return None
        except httpx.TransportError as e:
            logger.warning(f"TMDB connection error: {e}")
            return None
        except Exception as e:
            logger.warning(f"TMDB validation error: {e}")
            return None


async def validate_omdb(api_key: str) -> bool | None:
    """
    Validate OMDB API key.
    Returns: True/False/None
    """
    if not api_key or not api_key.strip():
        return None

    api_key = api_key.strip()
    url = f"http://www.omdbapi.com/?apikey={api_key}&t=test"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                if data.get("Response") == "False" and "Invalid API" in data.get("Error", ""):
                    return False
                return True
            if response.status_code in (401, 403):
                return False
            return None
        except httpx.TransportError as e:
            logger.warning(f"OMDB connection error: {e}")
            return None
        except Exception as e:
            logger.warning(f"OMDB validation error: {e}")
            return None


async def validate_opensubtitles(  # noqa: C901
    api_key: str, username: str | None, password: str | None
) -> tuple[bool | None, bool | None]:
    """
    Validate OpenSubtitles credentials.
    Returns: (key_valid, login_valid)
    """
    if not api_key:
        return (None, None)

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
            "User-Agent": "SubtitleDownloader v1.0",
        }
        payload = {"username": username, "password": password}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(login_url, headers=headers, json=payload, timeout=10.0)
                if response.status_code == 200:
                    data = response.json()
                    token = data.get("token")
                    if token:
                        # Logout
                        logout_headers = {
                            "Api-Key": api_key,
                            "Authorization": f"Bearer {token}",
                            "User-Agent": "SubtitleDownloader v1.0",
                        }
                        try:
                            await client.delete(logout_url, headers=logout_headers, timeout=5.0)
                        except Exception:
                            pass
                        return (True, True)
                    return (None, None)

                if response.status_code == 403:
                    return (False, None)

                if response.status_code == 401:
                    return (True, False)

                return (None, None)
            except httpx.TransportError as e:
                logger.warning(f"OpenSubtitles connection error: {e}")
                return (None, None)
            except Exception as e:
                logger.warning(f"OpenSubtitles validation error: {e}")
                return (None, None)

    # Fallback: Validate Key Only (if missing login details)
    check_url = "https://api.opensubtitles.com/api/v1/infos/formats"
    headers = {
        "Api-Key": api_key,
        "User-Agent": "SubtitleDownloader v1.0",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(check_url, headers=headers, timeout=5.0)
            if response.status_code == 200:
                return (True, None)
            if response.status_code == 403:
                return (False, None)
            return (None, None)
        except Exception as e:
            logger.warning(f"OpenSubtitles key check error: {e}")
            return (None, None)


async def validate_deepl(api_key: str) -> dict:
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
                logger.error(
                    f"DeepL API validation failed. Status: {response.status_code}, Body: {response.text}"
                )
                return {"valid": False, "error": f"Status {response.status_code}"}
        except Exception as e:
            logger.warning(f"DeepL validation error for ...{api_key[-8:]}: {e}")
            return {"valid": False, "error": str(e)}


async def validate_all_settings(db: AsyncSession) -> None:
    """
    Fetch current settings, validate configured credentials, and update validation status in DB.
    Also validates DeepL keys and updates/creates usage records.
    """
    try:
        settings_row = await crud_app_settings.get(db)

        # Get decrypted values
        tmdb_key = await crud_app_settings.get_decrypted_value(db, "tmdb_api_key")
        omdb_key = await crud_app_settings.get_decrypted_value(db, "omdb_api_key")
        os_api_key = await crud_app_settings.get_decrypted_value(db, "opensubtitles_api_key")
        os_username = await crud_app_settings.get_decrypted_value(db, "opensubtitles_username")
        os_password = await crud_app_settings.get_decrypted_value(db, "opensubtitles_password")

        # 1. Validate General API keys
        settings_row.tmdb_valid = await validate_tmdb(tmdb_key) if tmdb_key else None
        settings_row.omdb_valid = await validate_omdb(omdb_key) if omdb_key else None

        if os_api_key:
            u_arg = str(os_username) if os_username else None
            p_arg = str(os_password) if os_password else None

            key_valid, login_valid = await validate_opensubtitles(str(os_api_key), u_arg, p_arg)
            settings_row.opensubtitles_key_valid = key_valid
            settings_row.opensubtitles_valid = login_valid
        else:
            settings_row.opensubtitles_key_valid = None
            settings_row.opensubtitles_valid = None

        # 2. Validate DeepL Keys
        deepl_keys = await crud_app_settings.get_decrypted_value(db, "deepl_api_keys")
        if deepl_keys and isinstance(deepl_keys, list):
            for key in deepl_keys:
                if not key or not isinstance(key, str) or not key.strip():
                    continue

                # Validate key using helper
                usage_data = await validate_deepl(key)

                # Upsert usage record
                key_hash = hashlib.sha256(key.strip().encode()).hexdigest()

                result = await db.execute(
                    select(DeepLUsage).where(DeepLUsage.key_identifier == key_hash)
                )
                record = result.scalar_one_or_none()

                if not record:
                    record = DeepLUsage(key_identifier=key_hash)
                    db.add(record)
                    await db.flush()

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
        logger.info(
            f"Validation status updated: TMDB={settings_row.tmdb_valid}, "
            f"OMDB={settings_row.omdb_valid}, "
            f"OS_Key={settings_row.opensubtitles_key_valid}, "
            f"OS_Login={settings_row.opensubtitles_valid}, "
            f"DeepL keys processed."
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to validate settings: {e}")
