# backend/app/db/session.py
# backend/app/db/session.py
import logging
from collections.abc import AsyncGenerator, Generator

from fastapi import Depends
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session as SyncSessionORM
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models.user import User

logger = logging.getLogger(__name__)

# --- Asynchronous Engine and Session Setup ---
try:
    async_engine = create_async_engine(
        str(settings.ASYNC_DATABASE_URI),
        pool_pre_ping=True,
        echo=settings.DB_ECHO,
    )
    AsyncSessionLocal = async_sessionmaker(
        bind=async_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    logger.info("Asynchronous database engine and session maker configured successfully.")
except Exception as e:
    logger.critical(
        f"CRITICAL: Failed to initialize asynchronous database engine: {e}", exc_info=True
    )
    raise RuntimeError(f"Failed to initialize asynchronous database engine: {e}") from e


# MODIFICATION 1: Rename this function
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:  # Formerly get_async_db
    """
    Dependency to get an asynchronous database session.
    Ensures the session is closed and rolled back on exception.
    """
    if AsyncSessionLocal is None:
        logger.critical(
            "AsyncSessionLocal is not initialized. DB connection cannot be established."
        )
        raise RuntimeError("AsyncSessionLocal is not initialized.")

    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            logger.error("Async DB session rolled back due to an exception.", exc_info=True)
            raise


# --- fastapi-users Database Adapter Setup ---
async def get_user_db(
    # MODIFICATION 2: Update the dependency to use the new name
    session: AsyncSession = Depends(get_async_session),  # Formerly Depends(get_async_db)
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    yield SQLAlchemyUserDatabase(session, User)


if settings.SYNC_DATABASE_URI:
    try:
        sync_engine = create_engine(
            str(settings.SYNC_DATABASE_URI),
            echo=settings.DB_ECHO,
            pool_pre_ping=True,
        )
        SyncSessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=sync_engine,
            class_=SyncSessionORM,
        )
        logger.info("Synchronous database engine and session maker configured successfully.")
    except Exception as e:
        logger.error(f"Failed to configure synchronous database engine: {e}", exc_info=True)
        sync_engine = None
        SyncSessionLocal = None
else:
    logger.warning(
        "SYNC_DATABASE_URI not configured. "
        "Synchronous DB utilities (e.g., for Alembic directly via engine or SyncSessionLocal) will be unavailable."
    )


def get_sync_db_session() -> Generator[SyncSessionORM, None, None]:
    if SyncSessionLocal is None:
        raise RuntimeError(
            "Synchronous session factory (SyncSessionLocal) is not initialized. "
            "Ensure SYNC_DATABASE_URI is configured."
        )
    db: SyncSessionORM = SyncSessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        logger.error("Sync DB session rolled back due to an exception.", exc_info=True)
        raise
    finally:
        db.close()


# Example usage for Alembic's env.py (if it imports sync_engine):
# from app.db.session import sync_engine
# target_metadata = Base.metadata
# def run_migrations_online():
#     if sync_engine is None:
#         raise Exception("Alembic online migrations require sync_engine.")
#     connectable = sync_engine
#     with connectable.connect() as connection:
#         # ... context configuration ...
