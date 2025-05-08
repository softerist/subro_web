# backend/app/db/session.py
from collections.abc import AsyncGenerator  # For precise type hinting of the generator

from fastapi import Depends
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings  # Your Pydantic settings instance

from .models.user import User  # Assuming User model is in .models.user

# 1. Create the async engine
async_engine = create_async_engine(
    str(settings.ASYNC_DATABASE_URI),  # Ensure ASYNC_DATABASE_URI is a string
    pool_pre_ping=True,
    echo=settings.DB_ECHO,  # Control SQL echoing via settings (e.g., settings.DEBUG)
)

# 2. Create a configured "AsyncSessionLocal" factory
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # Good practice for async, prevents issues with detached objects
    class_=AsyncSession,  # Explicitly specify the class, though often inferred
)


# 3. Dependency to get an Async DB session
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get an asynchronous database session.
    Ensures the session is closed and rolled back on error.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            # No explicit commit here, route handlers should manage commits.
        except Exception:
            await session.rollback()
            raise
        finally:
            # The 'async with' context manager handles closing the session.
            # An explicit session.close() is generally not needed here with async_sessionmaker context manager.
            # However, if you were not using 'async with AsyncSessionLocal() as session:',
            # then await session.close() would be crucial.
            # For consistency and explicitness, keeping it doesn't harm,
            # but it's good to understand the context manager handles it.
            await session.close()  # Often redundant with `async with`, but ensures closure.


# --- fastapi-users Database Adapter Setup ---
async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    """
    Dependency to get the SQLAlchemyUserDatabase adapter for FastAPI-Users.
    """
    yield SQLAlchemyUserDatabase(session, User)


# --- Synchronous Session for Alembic or Scripts (Optional) ---
# Keep this section if you need synchronous sessions for tasks outside FastAPI (e.g., Alembic migrations, standalone scripts).
# Ensure SYNC_DATABASE_URI is configured in your settings if you use this.
#
# from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionmaker, Session as SyncSession # Alias Session to avoid name clash
#
# if settings.SYNC_DATABASE_URI: # Conditionally create if configured
#     sync_engine = create_engine(
#         str(settings.SYNC_DATABASE_URI),
#         echo=settings.DB_ECHO, # Can use the same echo setting
#     )
#     SyncSessionLocal = sessionmaker(
#         autocommit=False,
#         autoflush=False,
#         bind=sync_engine,
#         class_=SyncSession # Use the aliased SyncSession
#     )
#
#     def get_sync_db_session() -> SyncSession: # Use type hint for clarity
#         """
#         Provides a synchronous database session.
#         Remember to close the session manually or use a context manager.
#         """
#         db = SyncSessionLocal()
#         try:
#             yield db
#         finally:
#             db.close()
# else:
#     sync_engine = None
#     SyncSessionLocal = None
#     get_sync_db_session = None
#     print("Warning: SYNC_DATABASE_URI not configured. Synchronous DB session utilities will not be available.")
