# backend/tests/conftest.py
import asyncio  # Added asyncio import
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.models.user import Base  # Keep User model import
from app.db.session import get_db_session
from app.main import app as fastapi_app

TEST_DATABASE_URL = settings.ASYNC_DATABASE_URI


# Keep event_loop fixture as is
@pytest.fixture(scope="session")
def event_loop(request) -> Generator:  # noqa: ARG001 - Pytest requires 'request' fixture name
    """
    Creates a custom event loop for the test session.
    We're keeping this despite the pytest-asyncio warning because:
    1. We need a session-scoped loop
    2. We have specific requirements for our event loop handling
    NOTE: The 'request' argument is required by pytest even if not used directly.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# @pytest.fixture
# async def test_client(app) -> AsyncClient:
#     """
#     Create a test client using the updated httpx pattern with ASGITransport.
#     This fixes the deprecation warning about the 'app' shortcut.
#     """
#     # Replace direct app usage with ASGITransport
#     async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
#         yield client


# --- Database Fixtures (ALL FUNCTION SCOPED) ---


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Creates/Disposes an async engine FOR EACH TEST FUNCTION."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        # Ensure clean state for each test
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        # Dispose engine after each test function finishes
        await engine.dispose()


# Remove setup_database fixture as setup is now in test_engine


@pytest_asyncio.fixture(scope="function")
async def db_session(
    test_engine,  # Depend on the function-scoped engine
) -> AsyncGenerator[AsyncSession, None]:
    """Yields a database session per function, using the function-scoped engine."""
    TestSessionFactory = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with TestSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()  # Rollback on error within test
            raise
        # No explicit commit needed here if test interactions commit,
        # but adding one ensures state is saved if test doesn't explicitly rollback/commit.
        # If your tests rely on uncommitted state within the session, remove the commit.
        # else:
        #     await session.commit() # Or manage commits/rollbacks within tests


# --- Test Client Fixture (FIXED) ---

# REMOVE the test_client fixture that takes `app` as an argument, as it's likely unused
# and conflicts with the one below.


# Keep test_client fixture as is
@pytest_asyncio.fixture(scope="function")
async def test_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Creates an httpx AsyncClient using ASGITransport for testing the FastAPI app.
    Injects the function-scoped test database session.
    """

    def override_get_db():
        """Dependency override to use the test db session."""
        # Use try/finally to ensure the override is removed even if test fails
        try:
            yield db_session
        finally:
            # Optional: If you want session closed automatically after request using it.
            # Usually not needed as the `db_session` fixture handles closure.
            # await db_session.close()
            pass

    fastapi_app.dependency_overrides[get_db_session] = override_get_db

    # Use ASGITransport instead of the 'app=' shortcut
    # async with AsyncClient(
    #     transport=ASGITransport(app=fastapi_app), base_url="http://test"
    # ) as client:
    #     yield client

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        yield client

    # Clean up the dependency override after the test finishes
    fastapi_app.dependency_overrides.clear()
