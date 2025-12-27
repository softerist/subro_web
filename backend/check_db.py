import asyncio
import sys
from pathlib import Path

# Add backend to sys.path
backend_path = Path("/home/user/subro_web/backend")
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from sqlalchemy import select  # noqa: E402

from app.db import session as db_session  # noqa: E402
from app.db.models.deepl_usage import DeepLUsage  # noqa: E402
from app.db.models.translation_log import TranslationLog  # noqa: E402


async def check():
    db_session._initialize_fastapi_db_resources_sync()
    if db_session.FastAPISessionLocal is None:
        print("FastAPISessionLocal is None")
        return
    async with db_session.FastAPISessionLocal() as session:
        # Check TranslationLog
        result = await session.execute(select(TranslationLog))
        logs = result.scalars().all()
        print(f"Total translation logs: {len(logs)}")
        for log in logs[:3]:
            print(
                f"  - {log.timestamp}: {log.file_name} ({log.service_used}, {log.characters_billed} chars)"
            )

        # Check DeepLUsage
        result = await session.execute(select(DeepLUsage))
        usages = result.scalars().all()
        print(f"Total DeepL usage records: {len(usages)}")
        for usage in usages:
            print(
                f"  - {usage.key_identifier}: {usage.character_count}/{usage.character_limit} (Valid: {usage.valid})"
            )


if __name__ == "__main__":
    asyncio.run(check())
