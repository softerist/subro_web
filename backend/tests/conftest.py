# backend/tests/conftest.py
import asyncio
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.models.user import Base

# MODIFIED LINE: Import get_async_session instead of get_db_session
from app.db.session import get_async_session
from app.main import app as fastapi_app

# Ensure TEST_DATABASE_URL is correctly defined, using your ASYNC_DATABASE_URI from settings
# It seems ASYNC_DATABASE_URI should be ASYNC_SQLALCHEMY_DATABASE_URL based on your session.py
# Or ensure ASYNC_DATABASE_URI is defined in your settings correctly.
# For consistency with your session.py, let's assume it's ASYNC_SQLALCHEMY_DATABASE_URL
if not settings.ASYNC_SQLALCHEMY_DATABASE_URL:
    raise ValueError(
        "Test database URL (ASYNC_SQLALCHEMY_DATABASE_URL) is not configured in settings for tests."
    )
TEST_DATABASE_URL = str(settings.ASYNC_SQLALCHEMY_DATABASE_URL)  # Make sure it's a string


@pytest.fixture(scope="session")
def event_loop(
    _request: pytest.FixtureRequest,
) -> Generator[
    asyncio.AbstractEventLoop, None, None
]:  # Changed request to _request and added type hint
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Creates/Disposes an async engine FOR EACH TEST FUNCTION."""
    # Use TEST_DATABASE_URL which should be derived from settings.ASYNC_SQLALCHEMY_DATABASE_URL
    engine = create_async_engine(
        TEST_DATABASE_URL, echo=getattr(settings, "DB_ECHO_TESTS", False)
    )  # Allow specific test echo
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(
    test_engine,
) -> AsyncGenerator[AsyncSession, None]:
    """Yields a database session per function, using the function-scoped engine."""
    TestSessionFactory = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with TestSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture(scope="function")
async def test_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Creates an httpx AsyncClient using ASGITransport for testing the FastAPI app.
    Injects the function-scoped test database session.
    """

    async def override_get_async_session_for_test() -> (
        AsyncGenerator[AsyncSession, None]
    ):  # Changed name for clarity
        """Dependency override to use the test db session."""
        try:
            yield db_session
        finally:
            pass  # db_session fixture handles its own closure

    # MODIFIED LINE: Use the imported get_async_session
    fastapi_app.dependency_overrides[get_async_session] = override_get_async_session_for_test

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        yield client

    fastapi_app.dependency_overrides.clear()
