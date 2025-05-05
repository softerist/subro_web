# backend/app/db/session.py
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# Create the async engine
engine = create_async_engine(
    settings.ASYNC_DATABASE_URI,
    pool_pre_ping=True,  # Check connection before use
    echo=settings.DEBUG,  # Log SQL queries if in debug mode
)

# Create a configured "Session" class
AsyncSessionFactory = async_sessionmaker(
    engine,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


# Dependency to get a DB session
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides an async database session."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# --- fastapi-users Database Adapter Setup ---
# Import necessary components here to avoid circular imports later
from fastapi import Depends
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase

from .models.user import User  # Import your User model


async def get_user_db(session: AsyncSession = Depends(get_db_session)):
    """FastAPI dependency for fastapi-users database adapter."""
    yield SQLAlchemyUserDatabase(session, User)
