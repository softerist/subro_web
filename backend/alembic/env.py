# /backend/alembic/env.py
import asyncio
import logging
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine  # For async engine

from alembic import context

# --- BEGIN PATH MODIFICATION ---
alembic_dir = Path(__file__).resolve().parent
project_root = alembic_dir.parent

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
# --- END PATH MODIFICATION ---

# --- Alembic Config ---
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# --- Application Imports ---
# --- Application Imports ---
try:
    from app.core.config import settings
    from app.db.base_class import Base

    # Line 33: Import Job model. Add noqa: F401 to suppress unused import warning.
    # Its side-effect (registering with Base.metadata) is the reason for import.
    from app.db.models.job import Job as JobModel  # noqa: F401

    # Import all models that should be managed by Alembic
    # Line 36: Import User model. Add noqa: F401 to suppress unused import warning.
    # Its side-effect (registering with Base.metadata) is the reason for import.
    from app.db.models.user import User as UserModel  # noqa: F401

    # ... import other models ...
    # It's good practice to also add # to other similar model imports
    # if they are solely for metadata registration.

    logger.info("Successfully imported application settings, Base, and models.")
except ImportError as e:
    logger.error(f"Failed to import application modules. Error: {e}", exc_info=True)
    raise

# --- Target Metadata ---
target_metadata = Base.metadata
logger.debug("Target metadata object successfully set.")

# --- Naming Convention ---
naming_convention = {
    "ix": "ix_%(table_name)s_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
logger.debug(f"Using naming convention: {naming_convention}")

# --- Database URI for ASYNC Alembic execution ---
# This will be used for the 'online' mode with an async engine.
try:
    # *** THIS IS THE KEY CHANGE: Use the correct attribute name from your settings ***
    db_url_for_alembic_async = str(settings.ASYNC_SQLALCHEMY_DATABASE_URL)

    log_db_url = db_url_for_alembic_async
    # Obfuscate password for logging
    if hasattr(settings, "POSTGRES_PASSWORD") and settings.POSTGRES_PASSWORD:
        log_db_url = db_url_for_alembic_async.replace(settings.POSTGRES_PASSWORD, "****")
    logger.info(f"Database URI for Alembic ONLINE (async) mode: {log_db_url}")
except AttributeError as e:
    logger.error(
        f"Failed to get ASYNC_SQLALCHEMY_DATABASE_URL from settings. Error: {e}. "
        "Ensure it's defined in app.core.config.Settings and computed correctly.",
        exc_info=True,
    )
    raise
except Exception as e:
    logger.error(f"Unexpected error getting database URI from settings: {e}", exc_info=True)
    raise


def get_sync_sqlalchemy_url_from_settings() -> str:
    """
    Retrieves the SYNCHRONOUS SQLAlchemy URL from settings for offline mode.
    """
    try:
        # *** THIS IS THE KEY CHANGE for OFFLINE mode: Use the SYNC URL ***
        sync_url_obj = settings.SYNC_SQLALCHEMY_DATABASE_URL
        if not sync_url_obj:
            raise ValueError("SYNC_SQLALCHEMY_DATABASE_URL computed to None or empty in settings.")
        return str(sync_url_obj)
    except AttributeError as e:
        logger.error(
            f"Failed to get SYNC_SQLALCHEMY_DATABASE_URL from settings for OFFLINE mode. Error: {e}. "
            "Ensure it's defined in app.core.config.Settings.",
            exc_info=True,
        )
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error getting SYNC database URI for OFFLINE mode: {e}", exc_info=True
        )
        raise


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (uses a synchronous URL)."""
    sync_url = get_sync_sqlalchemy_url_from_settings()
    log_sync_url = sync_url
    if hasattr(settings, "POSTGRES_PASSWORD") and settings.POSTGRES_PASSWORD:
        log_sync_url = sync_url.replace(settings.POSTGRES_PASSWORD, "****")
    logger.info(f"Running migrations in OFFLINE mode using URL: {log_sync_url}")

    context.configure(
        url=sync_url,  # Use the synchronous URL for offline mode
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
        compare_server_default=True,
        naming_convention=naming_convention,
    )

    with context.begin_transaction():
        context.run_migrations()
    logger.info("Offline migrations complete.")


def do_run_migrations(connection: Connection) -> None:
    """Helper function to configure and run migrations in the online context."""
    logger.debug("Configuring context for online migration run.")
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,
        compare_server_default=True,
        naming_convention=naming_convention,
    )
    logger.info("Beginning transaction and running migrations (online)...")
    with context.begin_transaction():
        context.run_migrations()
    logger.info("Online migration run completed within the transaction.")


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an ASYNC engine."""
    # db_url_for_alembic_async is already defined globally from settings
    connectable = create_async_engine(
        db_url_for_alembic_async,  # Use the async URL for the async engine
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        logger.info("Established async connection. Running migrations (online)...")
        await connection.run_sync(
            do_run_migrations
        )  # run_sync executes the sync function in an async context
        logger.info("Synchronous migration execution via run_sync complete.")

    await connectable.dispose()
    logger.info("Async engine disposed. Online migrations fully complete.")


# --- Main Execution Logic ---
if context.is_offline_mode():
    logger.info("Alembic context is in OFFLINE mode.")
    run_migrations_offline()
else:
    logger.info("Alembic context is in ONLINE mode (async).")
    asyncio.run(run_migrations_online())

logger.info("Alembic env.py script execution finished.")
