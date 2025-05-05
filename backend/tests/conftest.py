# backend/tests/conftest.py
import asyncio  # Added asyncio import
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.models.user import Base  # Keep User model import
from app.db.session import get_db_session
from app.main import app as fastapi_app

TEST_DATABASE_URL = settings.ASYNC_DATABASE_URI


# Keep event_loop fixture as is
@pytest.fixture(scope="session")
def event_loop(request) -> Generator:
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# --- Database Fixtures (ALL FUNCTION SCOPED) ---


@pytest_asyncio.fixture(scope="function")  # Changed to function scope
async def test_engine():
    """Creates/Disposes an async engine FOR EACH TEST FUNCTION."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    # Setup schema for each test function
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()  # Dispose after each function


# Remove setup_database fixture as setup is now in test_engine


@pytest_asyncio.fixture(scope="function")
async def db_session(
    test_engine,
) -> AsyncGenerator[AsyncSession, None]:  # Removed setup_database dependency
    """Yields a database session per function."""
    TestSessionFactory = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with TestSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()


# Keep test_client fixture as is
@pytest_asyncio.fixture(scope="function")
async def test_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Creates an httpx AsyncClient for testing the FastAPI app."""

    def override_get_db():
        """Dependency override to use the test db session."""
        yield db_session  # Provide the function-scoped session

    fastapi_app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(app=fastapi_app, base_url="http://test") as client:
        yield client

    fastapi_app.dependency_overrides.clear()
