#!/usr/bin/env python3
"""
Sync Database Version from Config

This script updates the app_settings.app_version field in the database
to match the APP_VERSION from the application config.

Designed to run during deployment after migrations complete.
"""

import sys
from pathlib import Path

# Ensure backend path is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import settings  # noqa: E402


def sync_db_version() -> bool:
    """Sync database version to match config APP_VERSION."""
    try:
        # Use sync engine for script
        db_url = (
            str(settings.PRIMARY_DATABASE_URL_ENV or "")
            .replace("+asyncpg", "")
            .replace("postgresql://", "postgresql+psycopg2://")
        )
        if not db_url or "None" in db_url:
            # Fallback to reconstructed URL if env var is missing
            db_url = f"postgresql+psycopg2://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"

        # Create a localized sync engine
        engine = create_engine(db_url)

        with engine.connect() as conn:
            # Update the singleton row (id=1)
            sql = text("UPDATE app_settings SET app_version = :ver WHERE id = 1")
            result = conn.execute(sql, {"ver": settings.APP_VERSION})
            conn.commit()

            if result.rowcount == 0:
                print("WARNING: No row found in app_settings (id=1). Version not saved to DB.")
                return False
            else:
                print(f"✓ Updated Database app_version to {settings.APP_VERSION}")
                return True

    except Exception as e:
        print(f"ERROR: Database version sync failed: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    success = sync_db_version()
    sys.exit(0 if success else 1)
