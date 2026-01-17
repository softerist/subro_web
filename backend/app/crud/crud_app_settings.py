# backend/app/crud/crud_app_settings.py
"""
CRUD operations for AppSettings.
Implements singleton pattern - there is only ever one row in app_settings table.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_value, encrypt_value, mask_sensitive_value
from app.db.models.app_settings import AppSettings
from app.db.models.deepl_usage import DeepLUsage
from app.schemas.app_settings import SettingsRead, SettingsUpdate

logger = logging.getLogger(__name__)

_DEEPL_REVALIDATION_COOLDOWN = timedelta(seconds=30)
_deepl_revalidation_requested: dict[str, datetime] = {}

_OS_REVALIDATION_COOLDOWN = timedelta(minutes=1)
_os_revalidation_last_requested: datetime | None = None
_background_tasks: set[asyncio.Task] = set()


def _should_schedule_deepl_revalidation(key_hash: str, now: datetime) -> bool:
    last_requested = _deepl_revalidation_requested.get(key_hash)
    if last_requested and now - last_requested < _DEEPL_REVALIDATION_COOLDOWN:
        return False
    _deepl_revalidation_requested[key_hash] = now
    if len(_deepl_revalidation_requested) > 500:
        cutoff = now - timedelta(minutes=10)
        for existing_key, timestamp in list(_deepl_revalidation_requested.items()):
            if timestamp < cutoff:
                del _deepl_revalidation_requested[existing_key]
    return True


def _should_schedule_os_revalidation(now: datetime) -> bool:
    global _os_revalidation_last_requested
    if (
        _os_revalidation_last_requested
        and now - _os_revalidation_last_requested < _OS_REVALIDATION_COOLDOWN
    ):
        return False
    _os_revalidation_last_requested = now
    return True


# Fields that should be encrypted in the database
ENCRYPTED_FIELDS = {
    "tmdb_api_key",
    "omdb_api_key",
    "opensubtitles_api_key",
    "opensubtitles_username",
    "opensubtitles_password",
    "deepl_api_keys",
    "qbittorrent_password",
    "google_cloud_credentials",
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
            try:
                await db.execute(
                    insert(AppSettings)
                    .values(id=1, setup_completed=False)
                    .on_conflict_do_nothing(index_elements=[AppSettings.id])
                )
                await db.commit()
            except IntegrityError:
                # Another process created the singleton row first.
                await db.rollback()
            result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
            settings = result.scalar_one()

        return settings

    async def get_setup_completed(self, db: AsyncSession) -> bool:
        """Quick check if setup is completed."""
        settings = await self.get(db)
        return settings.setup_completed

    async def get_setup_state(self, db: AsyncSession) -> dict:
        """
        Get unified setup state for routing decisions.

        Returns:
            setup_completed: True if wizard was completed
            setup_required: True if wizard should be shown (forced OR not completed)
            setup_forced: True if FORCE_INITIAL_SETUP is set
        """
        from app.core.config import settings as config

        setup_completed = await self.get_setup_completed(db)
        setup_forced = config.FORCE_INITIAL_SETUP
        setup_required = setup_forced or not setup_completed

        return {
            "setup_completed": setup_completed,
            "setup_required": setup_required,
            "setup_forced": setup_forced,
        }

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
            assert cred_path_str is not None
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
                        parsed = json.loads(decrypted)
                    except json.JSONDecodeError:
                        return []
                    if isinstance(parsed, list):
                        return [str(item) for item in parsed]
                    return []
                return decrypted

            # Non-encrypted JSON array
            if field in JSON_ARRAY_FIELDS:
                try:
                    parsed = json.loads(raw_value)
                except json.JSONDecodeError:
                    return []
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
                return []

            return cast(str | list[str] | None, raw_value)

        # 2. Fall back to environment variable for known list fields
        from app.core.config import settings as env_settings

        env_mapping = self._get_db_to_env_map()
        if field in env_mapping:
            env_attr = env_mapping[field]
            env_value = getattr(env_settings, env_attr, None)
            if env_value is not None:
                # For list fields, return the list directly
                if field in JSON_ARRAY_FIELDS:
                    if isinstance(env_value, list):
                        return [str(item) for item in env_value]
                    if isinstance(env_value, str):
                        try:
                            parsed = json.loads(env_value)
                        except json.JSONDecodeError:
                            return []
                        if isinstance(parsed, list):
                            return [str(item) for item in parsed]
                        return []
                return cast(str | list[str], env_value)

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

        # Check for OpenSubtitles re-validation if rate limited
        await self._check_and_trigger_os_revalidation(db_settings)

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
            qbittorrent_connection_mode=db_settings.qbittorrent_connection_mode or "direct",
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
            allowed_media_folders=await self._get_combined_allowed_folders(
                db, db_settings, env_settings
            ),
            setup_completed=db_settings.setup_completed,
            # Validation status from DB cache
            tmdb_valid=self._convert_tmdb_status(
                db_settings.tmdb_valid, db_settings.tmdb_rate_limited
            ),
            omdb_valid=self._convert_omdb_status(
                db_settings.omdb_valid, db_settings.omdb_rate_limited
            ),
            opensubtitles_valid=db_settings.opensubtitles_valid,
            opensubtitles_key_valid=db_settings.opensubtitles_key_valid,
            opensubtitles_level=db_settings.opensubtitles_level,
            opensubtitles_vip=db_settings.opensubtitles_vip,
            opensubtitles_allowed_downloads=db_settings.opensubtitles_allowed_downloads,
            opensubtitles_rate_limited=db_settings.opensubtitles_rate_limited,
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
            google_usage=await self._get_google_usage_stats(db),
        )

    async def _check_and_trigger_os_revalidation(self, db_settings: AppSettings) -> None:
        """Trigger background OpenSubtitles validation if rate limited and cooldown passed."""
        if not db_settings.opensubtitles_rate_limited:
            return

        now = datetime.now(UTC)
        if _should_schedule_os_revalidation(now):
            try:
                import asyncio

                from app.db.session import FastAPISessionLocal
                from app.services.api_validation import validate_all_settings

                async def _background_task(factory: Callable[[], AsyncSession]) -> None:
                    async with factory() as session:
                        await validate_all_settings(session)

                if FastAPISessionLocal:
                    task = asyncio.create_task(_background_task(FastAPISessionLocal))
                    _background_tasks.add(task)
                    task.add_done_callback(_background_tasks.discard)
            except Exception as e:
                logger.error(f"Failed to trigger background OpenSubtitles validation: {e}")

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

    def _convert_tmdb_status(
        self, db_valid: bool | None, db_rate_limited: bool | None = None
    ) -> str | None:
        """
        Convert TMDB boolean validation status to string.
        Returns: 'valid', 'invalid', 'limit_reached', or None
        """
        if db_valid is None:
            return None
        if db_valid is True:
            return "valid"
        # False - check if it's due to rate limiting or genuinely invalid
        if db_rate_limited is True:
            return "limit_reached"
        return "invalid"

    def _convert_omdb_status(
        self, db_valid: bool | None, db_rate_limited: bool | None = None
    ) -> str | None:
        """
        Convert OMDB boolean validation status to string.
        Returns: 'valid', 'invalid', 'limit_reached', or None
        Note: 'limit_reached' is detected in the validation layer based on
        whether a previously valid key starts failing. The rate_limited flag
        indicates this scenario.
        """
        if db_valid is None:
            return None
        if db_valid is True:
            return "valid"
        # False - check if it's due to rate limiting or genuinely invalid
        if db_rate_limited is True:
            return "limit_reached"
        return "invalid"

    def _get_effective_plain(
        self, db_settings: AppSettings, _env_settings: Any, field_name: str
    ) -> str | int | None:
        """Get effective value (DB > env) without masking."""
        raw = getattr(db_settings, field_name, None)

        # If DB value exists (including explicit empty string), use it
        if raw is not None and isinstance(raw, str | int):
            return cast(str | int, raw)

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
                    return [
                        str(item) for item in items
                    ]  # Return empty list if user cleared all keys
            except (ValueError, json.JSONDecodeError):
                pass

        # Fall back to environment variable
        env_value = getattr(env_settings, env_attr, None)
        if env_value and isinstance(env_value, list):
            if field_name in ENCRYPTED_FIELDS and do_mask:
                if field_name == "deepl_api_keys":
                    return [mask_sensitive_value(str(item), visible_chars=8) for item in env_value]
                return [mask_sensitive_value(str(item)) for item in env_value]
            return [str(item) for item in env_value]

        # Additional fallback for DEEPL_API_KEYS if it's a JSON string
        if env_attr == "DEEPL_API_KEYS" and env_value and isinstance(env_value, str):
            try:
                items = json.loads(env_value)
                if isinstance(items, list):
                    if field_name in ENCRYPTED_FIELDS and do_mask:
                        return [mask_sensitive_value(str(item), visible_chars=8) for item in items]
                    return [str(item) for item in items]
            except json.JSONDecodeError:
                pass

        return []

    async def _get_combined_allowed_folders(
        self, db: AsyncSession, db_settings: AppSettings, env_settings: Any
    ) -> list[str]:
        """Combine allowed folders from AppSettings (legacy/env) and StoragePaths (auto-added)."""
        # 1. Get from AppSettings/Env
        settings_paths = self._get_effective_list(
            db_settings, env_settings, "allowed_media_folders", "ALLOWED_MEDIA_FOLDERS"
        )

        # 2. Get from StoragePath table
        # Avoid circular import at module level
        from app.crud.crud_storage_path import storage_path as crud_storage_path

        db_paths_objs = await crud_storage_path.get_multi(db)
        db_paths = [p.path for p in db_paths_objs]

        # 3. Combine and Deduplicate
        combined = set(settings_paths).union(db_paths)
        return sorted(combined)

    async def _get_deepl_usage_stats(  # noqa: C901
        self, db: AsyncSession, configured_keys: list[str]
    ) -> list[dict]:
        """Read DeepL usage stats from Database and merge with configured keys."""
        # Fetch all usage records from DB
        result = await db.execute(select(DeepLUsage))
        usage_records = result.scalars().all()

        import hashlib

        usage_map = {record.key_identifier: record for record in usage_records}
        now = datetime.now(UTC)
        revalidate_invalid_after = timedelta(minutes=5)
        refresh_valid_after = timedelta(hours=24)

        # Check for missing keys and trigger background validation
        missing_keys = []
        missing_hashes: set[str] = set()
        pending_revalidate: set[str] = set()
        for key_str in configured_keys:
            if not key_str or not isinstance(key_str, str) or not key_str.strip():
                continue

            key_hash = hashlib.sha256(key_str.strip().encode()).hexdigest()
            record = usage_map.get(key_hash)
            if not record:
                if key_hash not in missing_hashes:
                    missing_keys.append(key_str)
                    missing_hashes.add(key_hash)
                continue

            last_updated = record.last_updated
            if last_updated and last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=UTC)
            if record.valid is False:
                if not last_updated or now - last_updated >= revalidate_invalid_after:
                    if _should_schedule_deepl_revalidation(key_hash, now):
                        if key_hash not in missing_hashes:
                            missing_keys.append(key_str)
                            missing_hashes.add(key_hash)
                        pending_revalidate.add(key_hash)
            elif last_updated and now - last_updated >= refresh_valid_after:
                if _should_schedule_deepl_revalidation(key_hash, now):
                    if key_hash not in missing_hashes:
                        missing_keys.append(key_str)
                        missing_hashes.add(key_hash)

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
            if not key_str or not isinstance(key_str, str) or not key_str.strip():
                continue
            # Look up by hash
            key_hash = hashlib.sha256(key_str.strip().encode()).hexdigest()
            suffix = key_str[-8:] if len(key_str) >= 8 else key_str

            record = usage_map.get(key_hash)
            if record:
                stat = {
                    "key_alias": f"...{suffix}",
                    "character_count": record.character_count,
                    "character_limit": record.character_limit,
                    "valid": record.valid,
                }
                if key_hash in pending_revalidate:
                    stat["valid"] = None
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

    async def _get_google_usage_stats(self, db: AsyncSession) -> dict | None:
        """
        Get Google Translate usage stats from Google Cloud Monitoring API only.

        Returns None if Cloud Monitoring is not available - local stats are on the Statistics page.
        """
        # Try to get real-time usage from Google Cloud Monitoring API (which handles persistence/fallback)
        return await self._get_google_cloud_monitoring_usage(db)

    async def _get_google_cloud_monitoring_usage(self, db: AsyncSession) -> dict | None:  # noqa: C901
        """
        Fetch Google Translate API usage from Google Cloud Monitoring API.

        Returns dict with 'success' and 'data' or 'error' keys.
        Only attempts to fetch if Google Cloud is properly configured and validated.
        """
        import asyncio
        from datetime import UTC, datetime

        try:
            from google.cloud import monitoring_v3
        except ImportError:
            logger.debug("google-cloud-monitoring library not installed")
            return None  # Silently skip if library not installed

        # Get credentials and project ID from settings
        db_settings = await self.get(db)

        # Only attempt if Google Cloud is configured and validated
        if not db_settings.google_cloud_valid:
            return None  # Google Cloud not validated, skip silently

        project_id = db_settings.google_cloud_project_id
        if not project_id:
            return None  # No project ID, skip silently

        if not db_settings.google_cloud_credentials:
            logger.debug("No Google Cloud credentials configured")
            return None  # No credentials, skip silently

        logger.debug(f"Cloud Monitoring API for project: {project_id}")

        try:
            import json
            from datetime import timedelta

            from google.oauth2 import service_account

            from app.core.security import decrypt_value

            # Decrypt the stored credentials JSON
            try:
                creds_json_str = decrypt_value(db_settings.google_cloud_credentials)
                creds_json = json.loads(creds_json_str)
            except Exception as e:
                logger.warning(f"Failed to decrypt Google Cloud credentials: {e}")
                return {"success": False, "error": "Failed to decrypt credentials"}

            # Create credentials from the service account JSON
            try:
                credentials = service_account.Credentials.from_service_account_info(
                    creds_json,
                    scopes=["https://www.googleapis.com/auth/monitoring.read"],
                )
            except Exception as e:
                logger.warning(f"Failed to create credentials from service account: {e}")
                return {"success": False, "error": f"Invalid service account: {e}"}

            # Run in thread pool since the Google client is synchronous
            def fetch_metrics() -> dict[str, Any]:  # noqa: C901
                from google.api_core import exceptions as google_exceptions

                # --- API CALL Logic ---
                try:
                    client = monitoring_v3.MetricServiceClient(credentials=credentials)
                    project_name = f"projects/{project_id}"

                    # Query logic shared between standard and fallback
                    now = datetime.now(UTC)
                    start_time = now - timedelta(days=30)  # Last 30 days
                    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

                    interval = monitoring_v3.TimeInterval()
                    # Use standard datetime objects directly
                    interval.end_time = now
                    interval.start_time = start_time

                    found_chars = None
                    # final_source = "google_cloud_monitoring" # Removed unused

                    # 1. Try Standard Metric (translate.googleapis.com/translation/character_count)
                    try:
                        results = client.list_time_series(
                            request={
                                "name": project_name,
                                "filter": 'metric.type="translate.googleapis.com/translation/character_count"',
                                "interval": interval,
                                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                            }
                        )
                        points_found = False
                        total_chars = 0
                        this_month_chars = 0

                        for series in results:
                            points_found = True
                            for point in series.points:
                                chars = point.value.int64_value
                                total_chars += chars
                                point_time = point.interval.end_time
                                if point_time >= month_start:
                                    this_month_chars += chars

                        if points_found:
                            found_chars = (total_chars, this_month_chars)
                        else:
                            logger.info(
                                "Standard metric returned no data. Trying fallback 'serviceruntime' metric..."
                            )

                    except google_exceptions.NotFound:
                        logger.info(
                            "Standard metric descriptor not found (404). Trying fallback 'serviceruntime' metric..."
                        )

                    # 2. Fallback Metric (serviceruntime.googleapis.com/quota/rate/net_usage)
                    if found_chars is None:
                        # Filter for quota_metric="translate.googleapis.com/default"
                        fallback_filter = (
                            'metric.type="serviceruntime.googleapis.com/quota/rate/net_usage" AND '
                            'metric.label.quota_metric="translate.googleapis.com/default"'
                        )

                        results = client.list_time_series(
                            request={
                                "name": project_name,
                                "filter": fallback_filter,
                                "interval": interval,
                                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                            }
                        )

                        total_chars = 0
                        this_month_chars = 0

                        for series in results:
                            for point in series.points:
                                chars = point.value.int64_value
                                total_chars += chars
                                point_time = point.interval.end_time
                                if point_time >= month_start:
                                    this_month_chars += chars

                        found_chars = (total_chars, this_month_chars)
                        # NOTE: Keep source as standard 'google_cloud_monitoring' even if fallback used?
                        # Or maybe we don't need to distinguish for the UI unless it's cached.
                        # Let's keep it clean.

                    # Check final result
                    if found_chars:
                        total, month = found_chars
                        # --- PERSISTENCE ---
                        # Update DB with latest valid stats
                        logger.info(f"Updated Google usage cache: Total={total}, Month={month}")
                        # Use synchronous update since we are in a thread
                        # But we don't have a session here. We should return the data and let the main loop update?
                        # Or we do it in the async wrapper.
                        # Actually, fetch_metrics is a sync function run in executor. It doesn't have DB access conveniently.
                        # It handles raw API.

                        return {
                            "success": True,
                            "data": {
                                "total_characters": total,
                                "this_month_characters": month,
                                "source": "google_cloud_monitoring",
                            },
                        }
                    else:
                        return {"success": False, "error": "No metrics found."}

                except google_exceptions.PermissionDenied as e:
                    logger.warning(f"Cloud Monitoring permission denied: {e}")
                    return {
                        "success": False,
                        "error": "Permission denied. Add 'Monitoring Viewer' role.",
                    }
                except google_exceptions.NotFound as e:
                    # Treat "Cannot find metric" as 0 only if strictly looking for standard
                    # But we already tried fallback.
                    error_str = str(e)
                    if (
                        "Monitoring API has not been used" in error_str
                        or "is not enabled" in error_str.lower()
                    ):
                        return {
                            "success": False,
                            "error": "Cloud Monitoring API is not enabled.",
                        }
                    if "Cannot find metric" in error_str:
                        return {
                            "success": True,
                            "data": {
                                "total_characters": 0,
                                "this_month_characters": 0,
                                "source": "google_cloud_monitoring_empty",
                            },
                        }
                    return {"success": False, "error": f"Resource not found: {e}"}
                except Exception as e:
                    logger.warning(f"Unexpected error in Cloud Monitoring: {e}")
                    return {"success": False, "error": str(e)}

            # Run synchronous API call in thread pool
            loop = asyncio.get_event_loop()
            result = cast(dict[str, Any], await loop.run_in_executor(None, fetch_metrics))

            # --- POST-FETCH PERSISTENCE & FALLBACK LOGIC ---
            if result.get("success"):
                # Persist to DB
                data = cast(dict[str, Any], result["data"])
                total = data.get("total_characters", 0)
                month = data.get("this_month_characters", 0)

                # Update DB asynchronously
                from sqlalchemy import update

                await db.execute(
                    update(AppSettings)
                    .where(AppSettings.id == 1)
                    .values(
                        google_usage_total_chars=total,
                        google_usage_month_chars=month,
                        google_usage_last_updated=datetime.now(UTC),
                    )
                )
                await db.commit()  # Important
                return data
            else:
                # API Failed or Error
                error_msg = result.get("error", "Unknown error")
                logger.warning(
                    f"Cloud Monitoring failed ({error_msg}). checking for cached data..."
                )

                # Check DB for cached data
                if db_settings.google_usage_total_chars is not None:
                    logger.info("Returning cached Google usage stats.")
                    return {
                        "total_characters": db_settings.google_usage_total_chars,
                        "this_month_characters": db_settings.google_usage_month_chars,
                        "source": "google_cloud_monitoring_cached",
                        "last_updated": db_settings.google_usage_last_updated,
                        "error": error_msg,  # Optional: pass failure reason to UI?
                    }

                # No cache available, return None (or maybe the error if we want the UI to show it)
                # Usually None means "don't show section".
                logger.warning("No cached Google usage data available.")
                return None

        except Exception as e:
            logger.warning(f"Failed to fetch Google Cloud Monitoring data: {e}")
            return {"success": False, "error": str(e)}


# Singleton instance
crud_app_settings = CRUDAppSettings()
