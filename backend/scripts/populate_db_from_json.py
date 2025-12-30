import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add backend to sys.path to allow imports from app
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from sqlalchemy import select  # noqa: E402

from app.db import session as db_session  # noqa: E402
from app.db.models.deepl_usage import DeepLUsage  # noqa: E402
from app.db.models.translation_log import TranslationLog  # noqa: E402

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Detect environment and set log path
if Path("/app/logs/translation_log.json").exists():
    JSON_LOG_PATH = Path("/app/logs/translation_log.json")
else:
    # Host path for fallback (not used inside container if volume is mounted)
    JSON_LOG_PATH = Path("/home/user/subro_web/logs/translation_log.json")


def parse_isoformat(dt_str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        logger.error(f"Failed to parse timestamp: {dt_str}")
        return None


async def populate_db(data, refresh_timestamps=False):
    logger.info(f"Populating database with {len(data.get('jobs', []))} jobs...")

    db_session._initialize_fastapi_db_resources_sync()
    if db_session.FastAPISessionLocal is None:
        logger.error("FastAPISessionLocal not initialized")
        return

    async with db_session.FastAPISessionLocal() as session:
        # Import DeepL Usage
        deepl_snapshots = data.get("deepl_keys_snapshot", {})
        logger.info(f"Processing {len(deepl_snapshots)} DeepL key snapshots...")
        for key_id, snapshot in deepl_snapshots.items():
            # Check if exists
            result = await session.execute(
                select(DeepLUsage).where(DeepLUsage.key_identifier == key_id)
            )
            existing = result.scalar_one_or_none()

            last_updated = parse_isoformat(snapshot.get("snapshot_timestamp_utc"))

            if existing:
                logger.info(f"Updating DeepL usage for {key_id}")
                existing.character_count = snapshot.get("count", 0)
                existing.character_limit = snapshot.get("limit", 500000)
                existing.valid = snapshot.get("valid", True)
                existing.last_updated = last_updated or datetime.now(UTC)
            else:
                logger.info(f"Creating DeepL usage for {key_id}")
                new_usage = DeepLUsage(
                    key_identifier=key_id,
                    character_count=snapshot.get("count", 0),
                    character_limit=snapshot.get("limit", 500000),
                    valid=snapshot.get("valid", True),
                    last_updated=last_updated or datetime.now(UTC),
                )
                session.add(new_usage)

        # Import Jobs
        jobs = data.get("jobs", [])
        logger.info(f"Processing {len(jobs)} jobs...")
        new_jobs_count = 0
        skipped_jobs_count = 0

        for job_data in jobs:
            timestamp = parse_isoformat(job_data.get("timestamp_utc"))
            file_name = job_data.get("file_basename")

            # Check for duplicate (by timestamp and filename)
            result = await session.execute(
                select(TranslationLog).where(
                    TranslationLog.timestamp == timestamp, TranslationLog.file_name == file_name
                )
            )
            if result.scalar_one_or_none():
                skipped_jobs_count += 1
                continue

            billed_chars = job_data.get("billed_chars", {})

            # Determine mapping for service_used and status
            # JSON overall_status: "google", "deepl", "failed"
            # Model service_used: "deepl", "google", "mixed", "failed"
            # Model status: "success", "partial_failure", "failed"

            overall_status = job_data.get("overall_status", "failed")
            service_used = (
                overall_status if overall_status in ["deepl", "google", "failed"] else "mixed"
            )
            status = "success" if overall_status != "failed" else "failed"

            # If timestamp is very old (e.g. from a different year or many months ago),
            # it might not show up in 'last 30 days' stats.
            # We check if it's older than 30 days and optionally use now() if desired,
            # but for a migration we usually want to keep history.
            # However, if the user "cannot see them", it's likely due to the 30-day filter.
            now = datetime.now(UTC)
            if refresh_timestamps:
                timestamp = now
            elif timestamp and timestamp < now - timedelta(days=60):
                logger.warning(
                    f"Job {file_name} has old timestamp {timestamp}. Keeping it as is, but it won't show in 30-day stats."
                )

            new_log = TranslationLog(
                timestamp=timestamp or now,
                file_name=file_name,
                target_language="unknown",  # Not explicitly in JSON jobs list, but required in model
                service_used=service_used,
                characters_billed=billed_chars.get("total", 0),
                deepl_characters=billed_chars.get("deepl", 0),
                google_characters=billed_chars.get("google", 0),
                status=status,
            )
            session.add(new_log)
            new_jobs_count += 1

        await session.commit()
        logger.info("Migration completed successfully.")
        logger.info(f"DeepL keys updated/created: {len(deepl_snapshots)}")
        logger.info(f"Jobs imported: {new_jobs_count}")
        logger.info(f"Jobs skipped (already existed): {skipped_jobs_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Populate database from translation_log.json")
    parser.add_argument(
        "--json-path",
        type=Path,
        default=JSON_LOG_PATH,
        help=f"Path to translation_log.json (default: {JSON_LOG_PATH})",
    )
    parser.add_argument(
        "--refresh-timestamps",
        action="store_true",
        help="Use current time for all imported jobs (useful for visible stats)",
    )
    args = parser.parse_args()

    logger.info(f"Loading data from {args.json_path}")
    if not args.json_path.exists():
        logger.error(f"File not found: {args.json_path}")
        sys.exit(1)

    try:
        with args.json_path.open() as f:
            data = json.load(f)
        asyncio.run(populate_db(data, refresh_timestamps=args.refresh_timestamps))
    except Exception as e:
        logger.error(f"Failed to populate database: {e}")
        sys.exit(1)
