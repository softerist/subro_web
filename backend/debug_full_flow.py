import asyncio
import logging
import sys

import app.db.session as session_module
from app.api.routers.settings import _validate_omdb, _validate_opensubtitles, _validate_tmdb
from app.crud.crud_app_settings import crud_app_settings
from app.db.session import (
    _initialize_fastapi_db_resources_sync,
)
from app.schemas.app_settings import SettingsUpdate

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# Test Credentials provided by user
TMDB_KEY = "8a31e670984b1a2c3cc53a9a8da0fb7e"
OMDB_KEY = "3bcb6c7b"
OS_KEY = "a4zU1bWcOiK6yNVKpK1xP0OdAvyZs6eY"
OS_USER = "softerist"
OS_PASS = "codein"


async def main():
    print("--- Starting Full Flow Debug ---")

    # Initialize DB
    _initialize_fastapi_db_resources_sync()
    if session_module.FastAPISessionLocal is None:
        print("Failed to init DB session")
        return

    async with session_module.FastAPISessionLocal() as db:
        print("1. Updating Settings...")
        payload = SettingsUpdate(
            tmdb_api_key=TMDB_KEY,
            omdb_api_key=OMDB_KEY,
            opensubtitles_api_key=OS_KEY,
            opensubtitles_username=OS_USER,
            opensubtitles_password=OS_PASS,
        )

        await crud_app_settings.update(db, obj_in=payload)

        print("2. Validating Credentials...")
        settings_row = await crud_app_settings.get(db)

        # Get decrypted values
        tmdb_key = await crud_app_settings.get_decrypted_value(db, "tmdb_api_key")
        omdb_key = await crud_app_settings.get_decrypted_value(db, "omdb_api_key")
        os_api_key = await crud_app_settings.get_decrypted_value(db, "opensubtitles_api_key")
        os_username = await crud_app_settings.get_decrypted_value(db, "opensubtitles_username")
        os_password = await crud_app_settings.get_decrypted_value(db, "opensubtitles_password")

        print(f"   Decrypted TMDB: {tmdb_key[:5]}...")

        # Validate - verifying manual validation flow
        tmdb_valid = await _validate_tmdb(tmdb_key) if tmdb_key else False
        omdb_valid = await _validate_omdb(omdb_key) if omdb_key else False
        os_valid = await _validate_opensubtitles(os_api_key, os_username, os_password)

        print(f"   Validation Results: TMDB={tmdb_valid}, OMDB={omdb_valid}, OS={os_valid}")

        # Update DB
        settings_row.tmdb_valid = tmdb_valid
        settings_row.omdb_valid = omdb_valid
        settings_row.opensubtitles_valid = os_valid

        await db.commit()
        print("3. Committed Validation Status.")

        print("4. Reading Schema (simulating response)...")
        # Force a fresh get to ensure we see what endpoint sees
        await db.refresh(settings_row)

        result = await crud_app_settings.to_read_schema(db)
        print(
            f"   Schema Result: TMDB={result.tmdb_valid}, OMDB={result.omdb_valid}, OS={result.opensubtitles_valid}"
        )


if __name__ == "__main__":
    asyncio.run(main())
