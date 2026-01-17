# backend/app/core/effective_settings.py
"""
Helper module for retrieving effective settings.
Priority: Database values > Environment variables

This module provides functions to get configuration values with proper
fallback logic, used primarily by the Celery worker tasks.
"""

import json
import logging
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as env_settings
from app.core.security import decrypt_value
from app.crud.crud_app_settings import ENCRYPTED_FIELDS, JSON_ARRAY_FIELDS
from app.db.models.app_settings import AppSettings

logger = logging.getLogger(__name__)


# Mapping from DB field names to environment variable attribute names
DB_TO_ENV_MAPPING = {
    "tmdb_api_key": "TMDB_API_KEY",
    "omdb_api_key": "OMDB_API_KEY",
    "opensubtitles_api_key": "OPENSUBTITLES_API_KEY",
    "opensubtitles_username": "OPENSUBTITLES_USERNAME",
    "opensubtitles_password": "OPENSUBTITLES_PASSWORD",
    "deepl_api_keys": "DEEPL_API_KEYS",
    "qbittorrent_host": "QBITTORRENT_HOST",
    "qbittorrent_port": "QBITTORRENT_PORT",
    "qbittorrent_username": "QBITTORRENT_USERNAME",
    "qbittorrent_password": "QBITTORRENT_PASSWORD",
    "allowed_media_folders": "ALLOWED_MEDIA_FOLDERS",
}


async def _get_db_settings(db: AsyncSession) -> AppSettings | None:
    """Fetch AppSettings from database without creating if missing."""
    from sqlalchemy import select

    result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
    return result.scalar_one_or_none()


def _get_env_value(env_attr: str) -> str | int | list[str] | None:
    """Get a value from environment settings."""
    return cast(str | int | list[str] | None, getattr(env_settings, env_attr, None))


async def get_effective_setting(db: AsyncSession, field: str) -> str | int | list[str] | None:  # noqa: C901
    """
    Get a single effective setting value.

    Priority: DB (decrypted) > Environment variable

    Args:
        db: Database session
        field: Field name (e.g., "tmdb_api_key")

    Returns:
        The effective value, or None if not set anywhere
    """
    db_settings = await _get_db_settings(db)

    if db_settings:
        raw_value = getattr(db_settings, field, None)

        if raw_value:
            # Decrypt if needed
            if field in ENCRYPTED_FIELDS:
                try:
                    decrypted = decrypt_value(raw_value)
                    # Parse JSON arrays
                    if field in JSON_ARRAY_FIELDS:
                        try:
                            parsed = json.loads(decrypted)
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse JSON for {field}")
                            return []
                        if isinstance(parsed, list) and all(
                            isinstance(item, str) for item in parsed
                        ):
                            return parsed
                        logger.warning(f"Unexpected JSON format for {field}")
                        return []
                    return decrypted
                except ValueError:
                    logger.warning(f"Failed to decrypt {field}, falling back to env")
            elif field in JSON_ARRAY_FIELDS:
                # Non-encrypted JSON array
                try:
                    parsed = json.loads(raw_value)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON for {field}")
                    return []
                if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
                    return parsed
                logger.warning(f"Unexpected JSON format for {field}")
                return []
            else:
                return cast(str | int | list[str] | None, raw_value)

    # Fallback to environment
    env_attr = DB_TO_ENV_MAPPING.get(field)
    if env_attr:
        return _get_env_value(env_attr)

    return None


async def get_effective_settings_dict(db: AsyncSession) -> dict[str, Any]:
    """
    Get all effective settings as a dictionary.

    Used primarily for logging (with masking) or passing to subprocesses.

    Returns:
        Dictionary with all setting values (DB > Env fallback)
    """
    result = {}

    for db_field in DB_TO_ENV_MAPPING:
        value = await get_effective_setting(db, db_field)
        if value is not None:
            result[db_field] = value

    return result


async def build_subprocess_env(db: AsyncSession) -> dict[str, str]:
    """
    Build environment variables dict for subprocess execution.

    Merges os.environ with effective settings from DB.
    DB settings take precedence over container environment.

    Returns:
        Dictionary suitable for asyncio.create_subprocess_exec(env=...)
    """
    import os

    # Start with current environment
    env_vars = os.environ.copy()

    # Override with DB settings
    db_settings = await _get_db_settings(db)

    if db_settings:
        for db_field, env_name in DB_TO_ENV_MAPPING.items():
            raw_value = getattr(db_settings, db_field, None)

            if not raw_value:
                continue

            try:
                # Decrypt if needed
                if db_field in ENCRYPTED_FIELDS:
                    value = decrypt_value(raw_value)
                else:
                    value = raw_value

                # Convert lists to JSON strings for env vars
                if db_field in JSON_ARRAY_FIELDS:
                    if isinstance(value, str):
                        # Already JSON string (from non-encrypted field)
                        env_vars[env_name] = value
                    else:
                        # List that needs to be JSON serialized
                        env_vars[env_name] = json.dumps(value)
                elif isinstance(value, int):
                    env_vars[env_name] = str(value)
                else:
                    env_vars[env_name] = value

            except (ValueError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to process {db_field} for subprocess env: {e}")
                # Keep the original env value if decryption/parsing fails
                continue

    return env_vars
