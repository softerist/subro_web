# backend/app/crud/crud_app_settings.py
"""
CRUD operations for AppSettings.
Implements singleton pattern - there is only ever one row in app_settings table.
"""

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_value, encrypt_value, mask_sensitive_value
from app.db.models.app_settings import AppSettings
from app.db.models.deepl_usage import DeepLUsage
from app.schemas.app_settings import SettingsRead, SettingsUpdate

logger = logging.getLogger(__name__)

# Fields that should be encrypted in the database
ENCRYPTED_FIELDS = {
    "tmdb_api_key",
    "omdb_api_key",
    "opensubtitles_api_key",
    "opensubtitles_username",
    "opensubtitles_password",
    "deepl_api_keys",  # JSON array, entire string is encrypted
    "qbittorrent_password",
    "google_cloud_credentials",  # Full service account JSON
}

# Fields stored as JSON arrays
JSON_ARRAY_FIELDS = {
    "allowed_media_folders",
    "deepl_api_keys",
}


class CRUDAppSettings:
    """
    CRUD operations for the singleton AppSettings row.
    """

    async def get(self, db: AsyncSession) -> AppSettings:
        """
        Get the singleton AppSettings row.
        Creates it with defaults if it doesn't exist.
        """
        result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
        settings = result.scalar_one_or_none()

        if settings is None:
            logger.info("AppSettings row not found. Creating with defaults.")
            settings = AppSettings(id=1, setup_completed=False)
            db.add(settings)
            await db.commit()
            await db.refresh(settings)

        return settings

    async def get_setup_completed(self, db: AsyncSession) -> bool:
        """Quick check if setup is completed."""
        settings = await self.get(db)
        return settings.setup_completed

    async def update(self, db: AsyncSession, *, obj_in: SettingsUpdate) -> AppSettings:
        """
        Update settings. Encrypts sensitive fields before storage.
        Preserves existing values for masked fields passed back unchanged.
        """
        settings = await self.get(db)
        update_data = obj_in.model_dump(exclude_unset=True)

        if "deepl_api_keys" in update_data and isinstance(update_data["deepl_api_keys"], list):
            db_has_keys = settings.deepl_api_keys is not None and settings.deepl_api_keys != ""

            restored_keys = self._restore_deepl_keys(settings, update_data["deepl_api_keys"])
            if not restored_keys:
                if db_has_keys:
                    update_data["deepl_api_keys"] = ""
                else:
                    del update_data["deepl_api_keys"]
            else:
                update_data["deepl_api_keys"] = restored_keys

        # Apply updates
        for field, value in update_data.items():
            if value is None:
                continue

            # Strip string values to prevent saving whitespace
            if isinstance(value, str):
                value = value.strip()

            processed_value = self._process_field_for_update(field, value)
            setattr(settings, field, processed_value)

        await db.commit()
        await db.refresh(settings)
        return settings

    def _restore_deepl_keys(self, settings: AppSettings, new_keys: list[str]) -> list[str]:
        """Restore original values for masked keys in the update payload."""
        # Use _get_effective_list to get currently active keys (DB or Env), unmasked
        from app.core.config import settings as env_settings

        # We need unmasked keys to be able to restore the values
        existing_keys_list = self._get_effective_list(
            settings, env_settings, "deepl_api_keys", "DEEPL_API_KEYS", do_mask=False
        )

        # Create masked versions for comparison
        existing_masked_list = [
            mask_sensitive_value(k, visible_chars=8) for k in existing_keys_list
        ]

        restored_value = []
        logger.info(f"Restoring keys. Input: {new_keys}")
        logger.info(f"Existing masked references: {existing_masked_list}")

        for i, item in enumerate(new_keys):
            # Check if this looks like a masked key (contains *** or •)
            if "***" in item or "•" in item:
                # Try positional match first (most reliable for edits if order preserved)
                if i < len(existing_masked_list) and item == existing_masked_list[i]:
                    restored_value.append(existing_keys_list[i])
                    logger.info(f"Restored index {i} via position.")
                else:
                    # Try to find it anywhere in the list by exact match
                    try:
                        idx = existing_masked_list.index(item)
                        restored_value.append(existing_keys_list[idx])
                        logger.info(f"Restored index {i} via search (found at old index {idx}).")
                    except ValueError:
                        restored_value.append(item)
                        logger.warning(f"Failed to restore masked key at index {i}: {item}")
            else:
                restored_value.append(item)
        return restored_value

    def _process_field_for_update(self, field: str, value: Any) -> Any:
        """Process a field value for database storage (encryption and JSON serialization)."""
        # Handle JSON array fields
        if field in JSON_ARRAY_FIELDS:
            if isinstance(value, list):
                json_str = json.dumps(value)
                if field in ENCRYPTED_FIELDS:
                    return encrypt_value(json_str)
                return json_str

        # Handle other encrypted fields
        if field in ENCRYPTED_FIELDS and value:
            return encrypt_value(value)

        return value

    async def mark_setup_completed(self, db: AsyncSession) -> AppSettings:
        """Mark setup as completed."""
        settings = await self.get(db)
        settings.setup_completed = True
        await db.commit()
        await db.refresh(settings)
        return settings

    async def populate_from_env_defaults(self, db: AsyncSession) -> AppSettings:
        """
        Populate empty DB fields with values from environment variables.
        Called during setup to ensure DB becomes the complete source of truth.
        """
        from app.core.config import settings as env_settings

        settings = await self.get(db)

        # Mapping: DB field -> env attribute name
        env_mapping = {
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

        populated_fields = []

        for db_field, env_attr in env_mapping.items():
            # Only populate if DB field is empty
            current_value = getattr(settings, db_field, None)
            if current_value is not None:
                continue

            # Get value from environment
            env_value = getattr(env_settings, env_attr, None)
            if env_value is None:
                continue

            # Process and encrypt as needed
            processed_value = self._process_field_for_update(db_field, env_value)
            setattr(settings, db_field, processed_value)
            populated_fields.append(db_field)

        # Special handling for Google Cloud Credentials
        if not settings.google_cloud_credentials and getattr(
            env_settings, "GOOGLE_CREDENTIALS_PATH", None
        ):
            cred_path_str = env_settings.GOOGLE_CREDENTIALS_PATH
            try:
                from pathlib import Path

                cred_path = Path(cred_path_str)
                if cred_path.exists():
                    cred_content = cred_path.read_text(encoding="utf-8")
                    # Validate JSON
                    json.loads(cred_content)
                    settings.google_cloud_credentials = encrypt_value(cred_content)
                    populated_fields.append("google_cloud_credentials")
                    logger.info(f"Loaded Google Credentials from file: {cred_path}")
                else:
                    logger.warning(
                        f"GOOGLE_CREDENTIALS_PATH set to {cred_path} but file not found."
                    )
            except Exception as e:
                logger.error(f"Failed to load Google Credentials from path {cred_path_str}: {e}")

        if not settings.google_cloud_project_id and getattr(
            env_settings, "GOOGLE_PROJECT_ID", None
        ):
            settings.google_cloud_project_id = env_settings.GOOGLE_PROJECT_ID
            populated_fields.append("google_cloud_project_id")

        if populated_fields:
            await db.commit()
            await db.refresh(settings)
            logger.info(f"Populated DB with env defaults for: {populated_fields}")

        return settings

    async def get_decrypted_value(  # noqa: C901
        self, db: AsyncSession, field: str
    ) -> str | list[str] | None:
        """
        Get a single decrypted setting value.
        Checks DB first, then falls back to Environment variables.
        Returns None if both are empty.
        """

        settings = await self.get(db)
        raw_value = getattr(settings, field, None)

        # 1. Try DB Value (treat empty string as explicit override)
        if raw_value is not None:
            # If explicit empty string, return it (override env)
            if raw_value == "":
                return ""

            # Decrypt if needed
            if field in ENCRYPTED_FIELDS:
                try:
                    decrypted = decrypt_value(raw_value)
                except ValueError:
                    logger.warning(f"Failed to decrypt field {field}. Returning None.")
                    return None

                # Parse JSON if it's an array field
                if field in JSON_ARRAY_FIELDS:
                    try:
                        return json.loads(decrypted)
                    except json.JSONDecodeError:
                        return []
                return decrypted

            # Non-encrypted JSON array
            if field in JSON_ARRAY_FIELDS:
                try:
                    return json.loads(raw_value)
                except json.JSONDecodeError:
                    return []

            return raw_value

        # 2. Fall back to environment variable for known list fields
        from app.core.config import settings as env_settings

        env_mapping = self._get_db_to_env_map()
        if field in env_mapping:
            env_attr = env_mapping[field]
            env_value = getattr(env_settings, env_attr, None)
            if env_value is not None:
                # For list fields, return the list directly
                if field in JSON_ARRAY_FIELDS and isinstance(env_value, list):
                    return env_value
                return env_value

        return None

    async def to_read_schema(self, db: AsyncSession) -> SettingsRead:
        """
        Convert AppSettings to SettingsRead with masked effective values.
        """
        from app.core.config import settings as env_settings

        db_settings = await self.get(db)

        # Get raw DeepL keys for validation check
        active_deepl_keys_plain = self._get_effective_list(
            db_settings, env_settings, "deepl_api_keys", "DEEPL_API_KEYS", do_mask=False
        )

        # Get usage stats
        deepl_usage = await self._get_deepl_usage_stats(db, active_deepl_keys_plain)

        # Process keys: mask if valid, plaintext if invalid
        active_deepl_keys = []
        for key in active_deepl_keys_plain:
            if not key:
                continue

            # Find corresponding usage
            identifier = key[-8:] if len(key) >= 8 else key
            usage = next((u for u in deepl_usage if u["key_alias"].endswith(identifier)), None)

            # Mask if valid (or if status is unknown/True default, to be safe? No, user wants invalid unmasked)
            # If usage is found and valid is False -> Unmasked.
            # Else (Valid or Unknown) -> Masked.
            if usage and usage["valid"] is False:
                active_deepl_keys.append(key)
            else:
                active_deepl_keys.append(mask_sensitive_value(key, visible_chars=8))

        return SettingsRead(
            tmdb_api_key=self._get_effective_and_mask(db_settings, env_settings, "tmdb_api_key"),
            omdb_api_key=self._get_effective_and_mask(db_settings, env_settings, "omdb_api_key"),
            opensubtitles_api_key=self._get_effective_and_mask(
                db_settings, env_settings, "opensubtitles_api_key"
            ),
            opensubtitles_username=self._get_effective_and_mask(
                db_settings, env_settings, "opensubtitles_username"
            ),
            opensubtitles_password=self._get_effective_and_mask(
                db_settings, env_settings, "opensubtitles_password"
            ),
            deepl_api_keys=active_deepl_keys,
            deepl_usage=deepl_usage,
            qbittorrent_host=self._get_effective_plain(
                db_settings, env_settings, "qbittorrent_host"
            )
            or "",
            qbittorrent_port=self._get_effective_plain(
                db_settings, env_settings, "qbittorrent_port"
            ),
            qbittorrent_username=self._get_effective_plain(
                db_settings, env_settings, "qbittorrent_username"
            )
            or "",
            qbittorrent_password=self._get_effective_and_mask(
                db_settings, env_settings, "qbittorrent_password"
            ),
            allowed_media_folders=self._get_effective_list(
                db_settings, env_settings, "allowed_media_folders", "ALLOWED_MEDIA_FOLDERS"
            ),
            setup_completed=db_settings.setup_completed,
            # Validation status from DB cache
            tmdb_valid=db_settings.tmdb_valid,
            omdb_valid=db_settings.omdb_valid,
            opensubtitles_valid=db_settings.opensubtitles_valid,
            opensubtitles_key_valid=db_settings.opensubtitles_key_valid,
            # Google Cloud status - check DB first, then env path
            # Logic: If DB has value (even empty string), use it. If DB is None, check Env.
            google_cloud_configured=bool(
                db_settings.google_cloud_credentials
                if db_settings.google_cloud_credentials is not None
                else getattr(env_settings, "GOOGLE_CREDENTIALS_PATH", None)
            ),
            google_cloud_project_id=(
                mask_sensitive_value(db_settings.google_cloud_project_id, visible_chars=8)
                if db_settings.google_cloud_project_id
                else (
                    mask_sensitive_value(env_settings.GOOGLE_PROJECT_ID, visible_chars=8)
                    if getattr(env_settings, "GOOGLE_PROJECT_ID", None)
                    and db_settings.google_cloud_credentials is None
                    else None
                )
            ),
            google_cloud_valid=(
                db_settings.google_cloud_valid
                if db_settings.google_cloud_credentials
                else (
                    True
                    if getattr(env_settings, "GOOGLE_CREDENTIALS_PATH", None)
                    and db_settings.google_cloud_credentials is None
                    else None
                )
            ),
        )

    def _get_db_to_env_map(self) -> dict[str, str]:
        return {
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

    def _get_effective_and_mask(
        self, db_settings: AppSettings, _env_settings: Any, field_name: str
    ) -> str:
        """Get effective value (DB > env) and mask it."""
        raw = getattr(db_settings, field_name, None)

        # If DB value exists (including explicit empty string), use it
        if raw is not None:
            if raw == "":
                return ""
            if field_name in ENCRYPTED_FIELDS:
                try:
                    decrypted = decrypt_value(raw)
                    return mask_sensitive_value(decrypted)
                except ValueError:
                    return "[decryption failed]"
            return mask_sensitive_value(str(raw))

        return ""

    def _get_effective_plain(
        self, db_settings: AppSettings, _env_settings: Any, field_name: str
    ) -> str | int | None:
        """Get effective value (DB > env) without masking."""
        raw = getattr(db_settings, field_name, None)

        # If DB value exists (including explicit empty string), use it
        if raw is not None:
            return raw

        return None

    def _get_effective_list(  # noqa: C901
        self,
        db_settings: AppSettings,
        env_settings: Any,
        field_name: str,
        env_attr: str,
        do_mask: bool = True,
    ) -> list[str]:
        """Get effective list value (DB > env)."""
        raw = getattr(db_settings, field_name, None)
        if raw is not None:
            # Empty string means "explicitly cleared" - return empty list
            if raw == "":
                return []
            try:
                decrypted = decrypt_value(raw) if field_name in ENCRYPTED_FIELDS else raw
                items = json.loads(decrypted)
                # Return DB value even if empty - empty list means "explicitly cleared"
                # Only fallback to env if raw is None (not configured in DB)
                if isinstance(items, list):
                    if items and field_name in ENCRYPTED_FIELDS and do_mask:
                        if field_name == "deepl_api_keys":
                            return [
                                mask_sensitive_value(str(item), visible_chars=8) for item in items
                            ]
                        return [mask_sensitive_value(str(item)) for item in items]
                    return items  # Return empty list if user cleared all keys
            except (ValueError, json.JSONDecodeError):
                pass

        # Fall back to environment variable
        env_value = getattr(env_settings, env_attr, None)
        if env_value and isinstance(env_value, list):
            if field_name in ENCRYPTED_FIELDS and do_mask:
                if field_name == "deepl_api_keys":
                    return [mask_sensitive_value(str(item), visible_chars=8) for item in env_value]
                return [mask_sensitive_value(str(item)) for item in env_value]
            return env_value

        # Additional fallback for DEEPL_API_KEYS if it's a JSON string
        if env_attr == "DEEPL_API_KEYS" and env_value and isinstance(env_value, str):
            try:
                items = json.loads(env_value)
                if isinstance(items, list):
                    if field_name in ENCRYPTED_FIELDS and do_mask:
                        return [mask_sensitive_value(str(item), visible_chars=8) for item in items]
                    return items
            except json.JSONDecodeError:
                pass

        return []

    async def _get_deepl_usage_stats(
        self, db: AsyncSession, configured_keys: list[str]
    ) -> list[dict]:
        """Read DeepL usage stats from Database and merge with configured keys."""
        # Fetch all usage records from DB
        result = await db.execute(select(DeepLUsage))
        usage_records = result.scalars().all()

        usage_map = {
            record.key_identifier: {
                "key_alias": f"...{record.key_identifier}",
                "character_count": record.character_count,
                "character_limit": record.character_limit,
                "valid": record.valid,
            }
            for record in usage_records
        }

        import hashlib

        # Check for missing keys and trigger background validation
        missing_keys = []
        for key_str in configured_keys:
            key_hash = hashlib.sha256(key_str.strip().encode()).hexdigest()
            if key_hash not in usage_map:
                missing_keys.append(key_str)

        if missing_keys:
            try:
                import asyncio

                from app.db.session import FastAPISessionLocal
                from app.services.api_validation import validate_deepl_keys_background

                # Trigger background validation task
                if FastAPISessionLocal:
                    asyncio.create_task(  # noqa: RUF006
                        validate_deepl_keys_background(missing_keys, FastAPISessionLocal)
                    )
                else:
                    logger.error(
                        "FastAPISessionLocal is None, cannot trigger background validation."
                    )
            except Exception as e:
                logger.error(f"Failed to trigger background DeepL validation: {e}")

        final_stats = []
        for key_str in configured_keys:
            # Look up by hash
            key_hash = hashlib.sha256(key_str.strip().encode()).hexdigest()
            suffix = key_str[-8:] if len(key_str) >= 8 else key_str

            if key_hash in usage_map:
                # Found record (by hash)
                stat = usage_map[key_hash].copy()
                stat["key_alias"] = f"...{suffix}"
                final_stats.append(stat)
            else:
                # Fallback if validation hasn't completed yet
                final_stats.append(
                    {
                        "key_alias": f"...{suffix}",
                        "key_masked": suffix,
                        "character_count": 0,
                        "character_limit": 500000,
                        "valid": None,  # Indicates "Validating..." in UI
                    }
                )
        return final_stats


# Singleton instance
crud_app_settings = CRUDAppSettings()
