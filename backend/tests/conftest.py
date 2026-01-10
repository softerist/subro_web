# backend/tests/conftest.py
import logging  # Added to configure logging
import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

# Need to load .env before importing app.core.config
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

project_root = Path(__file__).resolve().parents[2]
load_dotenv(project_root / ".env")

# Load test env values AND override existing env vars (ensure test settings take precedence).
load_dotenv(Path(__file__).resolve().parents[1] / ".env.test", override=True)

# Keep log output clean
logging.getLogger("faker").setLevel(logging.WARNING)


from app.core.config import settings  # noqa: E402 clean
from app.core.rate_limit import limiter  # noqa: E402
from app.db.base import Base  # noqa: E402

# MODIFIED LINE: Import get_async_session instead of get_db_session
from app.db.session import get_async_session  # noqa: E402

# Ensure TEST_DATABASE_URL is correctly defined, using your ASYNC_DATABASE_URI from settings
# It seems ASYNC_DATABASE_URI should be ASYNC_SQLALCHEMY_DATABASE_URL based on your session.py
# Or ensure ASYNC_DATABASE_URI is defined in your settings correctly.
# For consistency with your session.py, let's assume it's ASYNC_SQLALCHEMY_DATABASE_URL
if not settings.ASYNC_SQLALCHEMY_DATABASE_URL:
    raise ValueError(
        "Test database URL (ASYNC_SQLALCHEMY_DATABASE_URL) is not configured in settings for tests."
    )
raw_test_db_url = str(settings.ASYNC_SQLALCHEMY_DATABASE_URL)
override_test_db_url = os.getenv("TEST_DATABASE_URL")

if override_test_db_url:
    url = make_url(override_test_db_url)
    if Path("/.dockerenv").exists() and url.host in {"localhost", "127.0.0.1"}:
        docker_host = os.getenv("TEST_DATABASE_HOST", "db_test")
        docker_port = int(os.getenv("TEST_DATABASE_PORT", "5432"))
        url = url.set(host=docker_host, port=docker_port)
    TEST_DATABASE_URL = url.render_as_string(hide_password=False)
else:
    url = make_url(raw_test_db_url)
    if Path("/.dockerenv").exists() and url.host in {"localhost", "127.0.0.1"}:
        docker_host = os.getenv("TEST_DATABASE_HOST", "db_test")
        docker_port = int(os.getenv("TEST_DATABASE_PORT", "5432"))
        url = url.set(host=docker_host, port=docker_port)
    TEST_DATABASE_URL = url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def event_loop(request: pytest.FixtureRequest) -> Generator:  # noqa: ARG001
    """Create an instance of the default event loop for each test session."""
    import asyncio

    loop = asyncio.get_event_loop_policy().new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine() -> AsyncGenerator:
    """Ensures a clean database state for each test function."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=getattr(settings, "DB_ECHO_TESTS", False))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from sqlalchemy import text

        # Fast way to clean all tables: TRUNCATE
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(
    test_engine: Any,
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

    from app.main import app as fastapi_app

    # MODIFIED LINE: Use the imported get_async_session
    fastapi_app.dependency_overrides[get_async_session] = override_get_async_session_for_test

    limiter_enabled = limiter.enabled
    limiter.enabled = False
    try:
        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            yield client
    finally:
        limiter.enabled = limiter_enabled
        fastapi_app.dependency_overrides.clear()
