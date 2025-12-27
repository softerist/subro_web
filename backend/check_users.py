import asyncio
import sys
from pathlib import Path

# Add backend to sys.path
backend_path = Path("/app")
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from sqlalchemy import select  # noqa: E402

from app.db import session as db_session  # noqa: E402
from app.db.models.user import User  # noqa: E402


async def check():
    db_session._initialize_fastapi_db_resources_sync()
    if db_session.FastAPISessionLocal is None:
        print("FastAPISessionLocal is None")
        return
    async with db_session.FastAPISessionLocal() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        for u in users:
            print(
                f"{u.email}: super={u.is_superuser}, active={u.is_active}, role={getattr(u, 'role', 'N/A')}"
            )


if __name__ == "__main__":
    asyncio.run(check())
