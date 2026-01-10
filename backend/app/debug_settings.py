import asyncio
import logging

from app.crud.crud_app_settings import crud_app_settings
from app.db.session import FastAPISessionLocal, _initialize_fastapi_db_resources_sync

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def debug_settings() -> None:
    _initialize_fastapi_db_resources_sync()
    if FastAPISessionLocal is None:
        raise RuntimeError("FastAPISessionLocal is not initialized.")
    async with FastAPISessionLocal() as db:
        settings = await crud_app_settings.to_read_schema(db)
        print(f"DeepL Keys Count: {len(settings.deepl_api_keys)}")
        print(f"DeepL Keys: {settings.deepl_api_keys}")
        print(f"Usage Stats Count: {len(settings.deepl_usage)}")
        print(f"Usage Stats: {settings.deepl_usage}")


if __name__ == "__main__":
    asyncio.run(debug_settings())
