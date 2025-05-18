# backend/app/db/session.py
import asyncio
import contextlib  # <--- IMPORT THIS
import logging
from collections.abc import AsyncGenerator, Generator

from fastapi import Depends
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy import Engine as SaEngine
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session as SyncSessionORM
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models.user import User

logger = logging.getLogger(__name__)

# --- Asynchronous Engine and Session Setup (for FastAPI) ---
fastapi_async_engine: AsyncEngine | None = None
FastAPISessionLocal: async_sessionmaker[AsyncSession] | None = None


def _initialize_fastapi_db_resources_sync():
    """
    Synchronous function to initialize FastAPI's async database engine and session maker.
    Called by the lifespan manager.
    """
    global fastapi_async_engine, FastAPISessionLocal

    if fastapi_async_engine is not None:
        logger.info("FastAPI: Asynchronous database resources already initialized.")
        return

    logger.info("FastAPI: Initializing asynchronous database engine and session maker.")
    try:
        db_url_fastapi_obj = settings.ASYNC_SQLALCHEMY_DATABASE_URL
        if not db_url_fastapi_obj:
            logger.critical(
                "CRITICAL: FastAPI: ASYNC_SQLALCHEMY_DATABASE_URL computed to None or empty."
            )
            raise ValueError(
                "FastAPI: ASYNC_SQLALCHEMY_DATABASE_URL is empty or None after computation."
            )
        db_url_fastapi_str = str(db_url_fastapi_obj)

        current_engine = create_async_engine(
            db_url_fastapi_str,
            pool_pre_ping=True,
            echo=getattr(settings, "DB_ECHO", False),
        )
        current_session_local = async_sessionmaker(
            bind=current_engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        fastapi_async_engine = current_engine
        FastAPISessionLocal = current_session_local
        logger.info(
            f"FastAPI: Asynchronous database engine ({db_url_fastapi_str.split('@')[0]}@...) and session maker configured successfully."
        )
    except Exception as e:
        logger.critical(
            f"CRITICAL: FastAPI: Failed to initialize asynchronous database engine: {e}",
            exc_info=True,
        )
        fastapi_async_engine = None
        FastAPISessionLocal = None
        raise RuntimeError(
            f"FastAPI: Failed to initialize asynchronous database engine during startup: {e}"
        ) from e


async def _dispose_fastapi_db_resources_async():
    global fastapi_async_engine, FastAPISessionLocal
    if fastapi_async_engine:
        logger.info("FastAPI: Disposing FastAPI asynchronous database engine.")
        await fastapi_async_engine.dispose()
        fastapi_async_engine = None
        FastAPISessionLocal = None
        logger.info("FastAPI: FastAPI asynchronous database engine disposed.")
    else:
        logger.info("FastAPI: No FastAPI asynchronous database engine to dispose.")


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    if FastAPISessionLocal is None:
        logger.critical("FastAPI: FastAPISessionLocal is not initialized.")
        raise RuntimeError(
            "FastAPI: FastAPISessionLocal is not initialized. "
            "Ensure DB resources are initialized via lifespan."
        )
    async with FastAPISessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            logger.error(
                "FastAPI: Async DB session rolled back due to an exception.", exc_info=True
            )
            raise


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase

    yield SQLAlchemyUserDatabase(session, User)


# --- Synchronous Engine and Session Setup (for Alembic, scripts, etc.) ---
sync_engine: SaEngine | None = None
SyncSessionLocal: sessionmaker[SyncSessionORM] | None = None

try:
    sync_db_url_obj = settings.SYNC_SQLALCHEMY_DATABASE_URL
    if not sync_db_url_obj:
        logger.critical("SYNC: SYNC_SQLALCHEMY_DATABASE_URL computed to None or empty.")
        raise ValueError("SYNC: SYNC_SQLALCHEMY_DATABASE_URL is empty or None after computation.")
    sync_db_url_str = str(sync_db_url_obj)

    sync_engine = create_engine(
        sync_db_url_str,
        echo=getattr(settings, "DB_ECHO", False),
        pool_pre_ping=True,
    )
    SyncSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=sync_engine,
        class_=SyncSessionORM,
    )
    logger.info(
        f"SYNC: Synchronous database engine ({sync_db_url_str.split('@')[0]}@...) and session maker configured successfully."
    )
except Exception as e:
    logger.error(
        f"SYNC: Failed to configure synchronous database engine using SYNC_SQLALCHEMY_DATABASE_URL: {e}",
        exc_info=True,
    )
    sync_engine = None
    SyncSessionLocal = None


def get_sync_db_session() -> Generator[SyncSessionORM, None, None]:
    if SyncSessionLocal is None:
        raise RuntimeError(
            "SYNC: Synchronous session factory (SyncSessionLocal) is not initialized. "
            "Ensure SYNC_SQLALCHEMY_DATABASE_URL is configured and engine initialized successfully."
        )
    db: SyncSessionORM = SyncSessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        logger.error("SYNC: Sync DB session rolled back due to an exception.", exc_info=True)
        raise
    finally:
        db.close()


# --- Resources for Celery Worker ---
worker_async_engine: AsyncEngine | None = None
WorkerSessionLocal: async_sessionmaker[AsyncSession] | None = None


def initialize_worker_db_resources():
    global worker_async_engine, WorkerSessionLocal
    if worker_async_engine is None:
        logger.info("CELERY_WORKER: Initializing database engine and session factory.")
        try:
            db_url_worker_obj = settings.ASYNC_SQLALCHEMY_DATABASE_URL_WORKER
            if not db_url_worker_obj:
                logger.critical(
                    "CELERY_WORKER: ASYNC_SQLALCHEMY_DATABASE_URL_WORKER computed to None or empty."
                )
                raise ValueError(
                    "Database URI for Celery worker (ASYNC_SQLALCHEMY_DATABASE_URL_WORKER) is empty or None."
                )
            db_url_worker_str = str(db_url_worker_obj)

            current_worker_engine = create_async_engine(
                db_url_worker_str,
                pool_pre_ping=True,
                echo=getattr(settings, "DB_ECHO_WORKER", getattr(settings, "DB_ECHO", False)),
            )
            current_worker_session_local = async_sessionmaker(
                bind=current_worker_engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autocommit=False,
                autoflush=False,
            )
            worker_async_engine = current_worker_engine
            WorkerSessionLocal = current_worker_session_local
            logger.info(
                f"CELERY_WORKER: Database engine ({db_url_worker_str.split('@')[0]}@...) and session factory initialized."
            )
        except Exception as e:
            logger.critical(
                f"CRITICAL: CELERY_WORKER: Failed to initialize database engine: {e}", exc_info=True
            )
            worker_async_engine = None
            WorkerSessionLocal = None
            raise RuntimeError(f"CELERY_WORKER: Failed to initialize database engine: {e}") from e
    else:
        logger.info(
            "CELERY_WORKER: Database engine and session factory already initialized for this process."
        )


def dispose_worker_db_resources_sync():
    global worker_async_engine, WorkerSessionLocal
    if worker_async_engine:
        logger.info("CELERY_WORKER: Disposing database engine (sync call).")
        try:
            asyncio.run(worker_async_engine.dispose())
        except RuntimeError as e:
            logger.warning(
                f"CELERY_WORKER: asyncio.run() failed during dispose: {e}. Common during shutdown."
            )
        except Exception as e:
            logger.error(
                f"CELERY_WORKER: Unexpected exception during worker_async_engine.dispose(): {e}",
                exc_info=True,
            )
        finally:
            worker_async_engine = None
            WorkerSessionLocal = None
            logger.info("CELERY_WORKER: Database engine disposal process completed (or attempted).")
    else:
        logger.info("CELERY_WORKER: No database engine to dispose for this worker process.")


@contextlib.asynccontextmanager  # <--- ADD THIS DECORATOR
async def get_worker_db_session() -> AsyncGenerator[AsyncSession, None]:
    if WorkerSessionLocal is None:
        logger.critical(
            "CELERY_WORKER: WorkerSessionLocal not initialized! DB init failed or signal not handled."
        )
        raise RuntimeError(
            "Database session factory (WorkerSessionLocal) not initialized for Celery worker."
        )

    # The WorkerSessionLocal() call returns an AsyncSession instance.
    # AsyncSession itself is an asynchronous context manager.
    async with WorkerSessionLocal() as session:  # session: AsyncSession
        try:
            # Yield the session to the `async with get_worker_db_session() as db:` block
            yield session
            # If the `with` block in the task completes without error, execution resumes here.
            # Note: AsyncSession's context manager does not auto-commit by default.
            # Commits should be explicit in the code using the session.
        except Exception:
            # If an exception occurs in the code using the yielded session,
            # it's caught here. The `async with WorkerSessionLocal() as session:`
            # context manager will also see this exception (as it propagates)
            # and will ensure `session.rollback()` and `session.close()` are called.
            # Logging here can be useful for context.
            logger.error(
                "CELERY_WORKER: Exception occurred in user code of get_worker_db_session. "
                "Session rollback and close will be handled by AsyncSession's context manager.",
                exc_info=True,
            )
            raise  # Re-raise the exception to be handled by the caller and the outer context manager.


# --- FastAPI Lifespan Event Handler Integration ---
async def lifespan_db_manager(_app_instance, event_type: str):
    lifespan_logger = logging.getLogger("app.db.lifespan")

    if event_type == "startup":
        lifespan_logger.info("FastAPI Lifespan: Startup event - Initializing DB resources.")
        _initialize_fastapi_db_resources_sync()

        if fastapi_async_engine:
            lifespan_logger.info("FastAPI Lifespan: Testing DB connection.")
            try:
                async with fastapi_async_engine.connect() as connection:
                    await connection.run_sync(lambda conn: conn.execute(text("SELECT 1")))
                lifespan_logger.info("FastAPI Lifespan: Database connection successful on startup.")
            except Exception as e:
                lifespan_logger.error(
                    f"FastAPI Lifespan: Database connection test failed: {e}", exc_info=True
                )
                await _dispose_fastapi_db_resources_async()
                raise RuntimeError(
                    f"FastAPI: Database connection test failed on startup: {e}"
                ) from e
        else:
            lifespan_logger.critical(
                "FastAPI Lifespan: fastapi_async_engine is None after initialization attempt."
            )
            raise RuntimeError(
                "FastAPI engine failed to initialize during startup and did not raise."
            )

    elif event_type == "shutdown":
        lifespan_logger.info("FastAPI Lifespan: Shutdown event - Disposing DB resources.")
        await _dispose_fastapi_db_resources_async()
