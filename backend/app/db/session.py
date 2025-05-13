# backend/app/db/session.py
import logging  # For logging warnings
from collections.abc import AsyncGenerator, Generator  # Added Generator for sync part

from fastapi import Depends
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session as SyncSession
from sqlalchemy.orm import sessionmaker  # Alias Session

from app.core.config import settings

from .models.user import User  # Assuming User model is in .models.user

logger = logging.getLogger(__name__)

# 1. Create the async engine
# Ensure ASYNC_DATABASE_URI from settings is a string representation of the DSN.
# The settings.ASYNC_DATABASE_URI property should already be a PostgresDsn,
# which stringifies correctly.
async_engine = create_async_engine(
    str(settings.ASYNC_DATABASE_URI),
    pool_pre_ping=True,
    echo=settings.DB_ECHO,
)

# 2. Create a configured "AsyncSessionLocal" factory
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # Important for async to prevent issues with detached objects
    class_=AsyncSession,
)


# 3. Dependency to get an Async DB session
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get an asynchronous database session.
    The `async with` statement ensures the session is closed automatically.
    Rolls back the session on any exception during its use.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            # If the route handler using this session needs to commit,
            # it should call `await session.commit()` explicitly.
        except Exception:
            await session.rollback()
            raise
        # No explicit `await session.close()` needed here;
        # `async with AsyncSessionLocal() as session:` handles closing.


# --- fastapi-users Database Adapter Setup ---
async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    """
    Dependency to get the SQLAlchemyUserDatabase adapter for FastAPI-Users.
    """
    yield SQLAlchemyUserDatabase(session, User)


# --- Synchronous Session for Alembic or Scripts (Optional) ---
# This section is useful if you need synchronous database access,
# for example, for Alembic migrations or standalone scripts.

sync_engine = None
SyncSessionLocal = None

if settings.SYNC_DATABASE_URI:
    try:
        sync_engine = create_engine(
            str(settings.SYNC_DATABASE_URI),
            echo=settings.DB_ECHO,  # Can share echo setting
            pool_pre_ping=True,  # Good practice for sync engine too
        )
        SyncSessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=sync_engine,
            class_=SyncSession,  # Use the aliased SyncSession
        )
        logger.info("Synchronous database engine and session maker configured.")
    except Exception as e:
        logger.error(f"Failed to configure synchronous database engine: {e}", exc_info=True)
        sync_engine = None
        SyncSessionLocal = None

else:
    logger.warning(
        "SYNC_DATABASE_URI not configured in settings. "
        "Synchronous database session utilities (e.g., for Alembic if not configured separately) will not be available via SyncSessionLocal."
    )


def get_sync_db_session() -> Generator[SyncSession, None, None]:
    """
    Provides a synchronous database session.
    Intended for use in synchronous contexts like scripts or Alembic (if not using engine directly).
    The session must be closed by the caller or via the context manager pattern.
    """
    if SyncSessionLocal is None:
        raise RuntimeError(
            "Synchronous session factory (SyncSessionLocal) is not initialized. "
            "Ensure SYNC_DATABASE_URI is configured correctly."
        )

    db: SyncSession = SyncSessionLocal()
    try:
        yield db
        # db.commit() # Commits should be handled by the code using the session
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# Example of how Alembic's env.py might use the sync_engine:
#
# from app.db.session import sync_engine # Assuming Alembic can import this
# ...
# def run_migrations_online():
#     """Run migrations in 'online' mode.
#     In this scenario we need to create an Engine
#     and associate a connection with the context.
#     """
#     if sync_engine is None:
#         raise Exception("Alembic migrations require sync_engine to be configured.")
#
#     connectable = sync_engine
#     with connectable.connect() as connection:
#         context.configure(
#             connection=connection, target_metadata=target_metadata
#         )
#         with context.begin_transaction():
#             context.run_migrations()
