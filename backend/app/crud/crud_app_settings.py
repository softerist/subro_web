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

        # Restore masked DeepL keys if they're being updated
        if "deepl_api_keys" in update_data and isinstance(update_data["deepl_api_keys"], list):
            update_data["deepl_api_keys"] = self._restore_deepl_keys(
                settings, update_data["deepl_api_keys"]
            )

        # Apply updates
        for field, value in update_data.items():
            if value is None:
                continue

            processed_value = self._process_field_for_update(field, value)
            setattr(settings, field, processed_value)

        await db.commit()
        await db.refresh(settings)
        return settings

    def _restore_deepl_keys(self, settings: AppSettings, new_keys: list[str]) -> list[str]:
        """Restore original values for masked keys in the update payload."""
        current_raw = getattr(settings, "deepl_api_keys", None)
        if not current_raw:
            return new_keys

        try:
            current_decrypted_json = decrypt_value(current_raw)
            existing_keys_list = json.loads(current_decrypted_json)
            existing_masked_list = [mask_sensitive_value(k) for k in existing_keys_list]
        except Exception:
            return new_keys

        restored_value = []
        for i, item in enumerate(new_keys):
            # Check if this looks like a masked key (contains *** or •)
            if "***" in item or "•" in item:
                # Try positional match first (most reliable for edits)
                if i < len(existing_masked_list) and item == existing_masked_list[i]:
                    restored_value.append(existing_keys_list[i])
                else:
                    # Try to find it anywhere in the list by exact match
                    try:
                        idx = existing_masked_list.index(item)
                        restored_value.append(existing_keys_list[idx])
                    except ValueError:
                        restored_value.append(item)
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
            if current_value:
                continue

            # Get value from environment
            env_value = getattr(env_settings, env_attr, None)
            if env_value is None:
                continue

            # Process and encrypt as needed
            processed_value = self._process_field_for_update(db_field, env_value)
            setattr(settings, db_field, processed_value)
            populated_fields.append(db_field)

        if populated_fields:
            await db.commit()
            await db.refresh(settings)
            logger.info(f"Populated DB with env defaults for: {populated_fields}")

        return settings

    async def get_decrypted_value(self, db: AsyncSession, field: str) -> str | list[str] | None:
        """
        Get a single decrypted setting value.
        Returns None if the field is empty.
        """
        settings = await self.get(db)
        raw_value = getattr(settings, field, None)

        if not raw_value:
            return None

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

    async def to_read_schema(self, db: AsyncSession) -> SettingsRead:
        """
        Convert AppSettings to SettingsRead with masked effective values.
        """
        from app.core.config import settings as env_settings

        db_settings = await self.get(db)

        active_deepl_keys = self._get_effective_list(
            db_settings, env_settings, "deepl_api_keys", "DEEPL_API_KEYS"
        )

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
            deepl_usage=await self._get_deepl_usage_stats(db, active_deepl_keys),
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
        )

    def _get_db_to_env_map(self) -> dict[str, str]:
        return {
            "tmdb_api_key": "TMDB_API_KEY",
            "omdb_api_key": "OMDB_API_KEY",
            "opensubtitles_api_key": "OPENSUBTITLES_API_KEY",
            "opensubtitles_username": "OPENSUBTITLES_USERNAME",
            "opensubtitles_password": "OPENSUBTITLES_PASSWORD",
            "qbittorrent_host": "QBITTORRENT_HOST",
            "qbittorrent_port": "QBITTORRENT_PORT",
            "qbittorrent_username": "QBITTORRENT_USERNAME",
            "qbittorrent_password": "QBITTORRENT_PASSWORD",
        }

    def _get_effective_and_mask(
        self, db_settings: AppSettings, env_settings: Any, field_name: str
    ) -> str:
        """Get effective value (DB > env) and mask it."""
        raw = getattr(db_settings, field_name, None)
        if raw:
            if field_name in ENCRYPTED_FIELDS:
                try:
                    decrypted = decrypt_value(raw)
                    return mask_sensitive_value(decrypted)
                except ValueError:
                    return "[decryption failed]"
            return mask_sensitive_value(str(raw))

        env_attr = self._get_db_to_env_map().get(field_name)
        if env_attr:
            env_val = getattr(env_settings, env_attr, None)
            if env_val:
                return mask_sensitive_value(str(env_val))
        return ""

    def _get_effective_plain(
        self, db_settings: AppSettings, env_settings: Any, field_name: str
    ) -> str | int | None:
        """Get effective value (DB > env) without masking."""
        raw = getattr(db_settings, field_name, None)
        if raw is not None and raw != "":
            return raw
        env_attr = self._get_db_to_env_map().get(field_name)
        if env_attr:
            return getattr(env_settings, env_attr, None)
        return None

    def _get_effective_list(
        self, db_settings: AppSettings, env_settings: Any, field_name: str, env_attr: str
    ) -> list[str]:
        """Get effective list value (DB > env)."""
        raw = getattr(db_settings, field_name, None)
        if raw:
            try:
                decrypted = decrypt_value(raw) if field_name in ENCRYPTED_FIELDS else raw
                items = json.loads(decrypted)
                if field_name in ENCRYPTED_FIELDS:
                    if field_name == "deepl_api_keys":
                        return [mask_sensitive_value(str(item), visible_chars=8) for item in items]
                    return [mask_sensitive_value(str(item)) for item in items]
                return items
            except (ValueError, json.JSONDecodeError):
                pass
        env_val = getattr(env_settings, env_attr, None)
        if env_val:
            return env_val if isinstance(env_val, list) else [str(env_val)]
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

        final_stats = []
        for key_str in configured_keys:
            # We use the suffix as the identifier - Updated to 8 chars
            suffix = key_str[-8:] if len(key_str) >= 8 else key_str
            if suffix in usage_map:
                final_stats.append(usage_map[suffix])
            else:
                final_stats.append(
                    {
                        "key_alias": f"...{suffix}",
                        "character_count": 0,
                        "character_limit": 500000,
                        "valid": True,
                    }
                )
        return final_stats


# Singleton instance
crud_app_settings = CRUDAppSettings()
