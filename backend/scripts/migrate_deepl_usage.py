# backend/scripts/migrate_deepl_usage.py
import json
import logging
import sys
from pathlib import Path

# Add app to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.security import decrypt_value
from app.db.models.app_settings import AppSettings
from app.db.models.deepl_usage import DeepLUsage
from app.db.session import SyncSessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():  # noqa: C901
    # 1. Find the log file
    log_paths = [
        Path("logs/translation_log.json"),
        Path("app/logs/translation_log.json"),
        Path(__file__).resolve().parent.parent / "logs" / "translation_log.json",
        Path(__file__).resolve().parent.parent / "app" / "logs" / "translation_log.json",
    ]
    log_file = next((p for p in log_paths if p.exists()), None)

    if not log_file:
        logger.error("Could not find translation_log.json")
        return

    logger.info(f"Using log file: {log_file}")

    try:
        with log_file.open(encoding="utf-8") as f:
            log_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read log file: {e}")
        return

    snapshot = log_data.get("deepl_keys_snapshot", {})
    if not snapshot:
        logger.info("No DeepL usage snapshot found in log file.")
        return

    # 2. Get configured keys to match indices to suffixes
    configured_keys = []
    with SyncSessionLocal() as db:
        try:
            settings = db.query(AppSettings).first()
            if settings and settings.deepl_api_keys:
                decrypted_val = decrypt_value(settings.deepl_api_keys)
                configured_keys = json.loads(decrypted_val)
                logger.info(f"Found {len(configured_keys)} configured DeepL keys.")
        except Exception as e:
            logger.error(f"Error reading app settings: {e}")

    # 3. Perform migration per record to avoid transaction failure cascade
    for key_alias, info in snapshot.items():
        identifier = None
        try:
            if key_alias.startswith("key_"):
                idx = int(key_alias.replace("key_", "")) - 1
                if 0 <= idx < len(configured_keys):
                    real_key = configured_keys[idx]
                    identifier = real_key[-4:] if len(real_key) >= 4 else real_key
                else:
                    identifier = key_alias
            else:
                identifier = key_alias

            if not identifier:
                continue

            with SyncSessionLocal() as db:
                usage = db.query(DeepLUsage).filter(DeepLUsage.key_identifier == identifier).first()
                if not usage:
                    usage = DeepLUsage(
                        key_identifier=identifier,
                        character_count=info.get("count", 0),
                        character_limit=info.get("limit", 500000),
                        valid=info.get("valid", True),
                    )
                    db.add(usage)
                    logger.info(f"Adding record for: {identifier}")
                else:
                    logger.info(
                        f"Record for {identifier} already exists. Incrementing if needed (skipped for safety in migration)."
                    )
                db.commit()

        except Exception as e:
            logger.error(f"Failed to migrate {key_alias} (identifier={identifier}): {e}")

    logger.info("One-time migration script finished.")


if __name__ == "__main__":
    migrate()
