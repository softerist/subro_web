# --- THIS MUST BE AT THE VERY TOP ---
# import os # No longer needed for path manipulation here
import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path  # Ensure pathlib is imported

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import settings  # Import the instantiated settings object
from app.db.base import Base  # This Base should have User, Job, etc., registered
from app.db.models.job import Job as JobModelForDebug
from app.db.models.job import JobStatus as JobStatusForDebug

# Add the project's 'backend' directory and 'backend/app' directory to Python path
# This assumes env.py is in backend/alembic/
# Path to the 'backend/alembic' directory (where this file is)
alembic_dir = Path(__file__).resolve().parent
# Path to the 'backend' directory (parent of alembic_dir)
backend_dir = alembic_dir.parent
# Path to the 'backend/app' directory
app_dir = backend_dir / "app"

sys.path.insert(0, str(backend_dir))  # Add backend/
sys.path.insert(0, str(app_dir))  # Add backend/app/
# --- END sys.path MODIFICATION ---

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the target metadata for 'autogenerate' support
target_metadata = Base.metadata

# --- DEBUGGING (Optional - can be removed after setup is stable) ---
print("=" * 50)
print("DEBUG [env.py]: Forcing registration check:")
if "JobModelForDebug" in locals() and JobModelForDebug.__table__ in Base.metadata.tables.values():
    print("  JobModelForDebug is in Base.metadata: True")
    print(f"  JobModelForDebug table name: {JobModelForDebug.__tablename__}")
else:
    print("  JobModelForDebug not found in Base.metadata or not defined for this check.")
print(f"  Known tables by Base.metadata: {list(Base.metadata.tables.keys())}")
if "JobStatusForDebug" in locals():
    print(f"  JobStatus enum values: {[item.value for item in JobStatusForDebug]}")
print("=" * 50)
print("DEBUG [env.py]: Alembic target_metadata tables:", list(target_metadata.tables.keys()))
print(f"DEBUG [env.py]: settings.POSTGRES_SERVER = {settings.POSTGRES_SERVER}")
print(f"DEBUG [env.py]: settings.ASYNC_DATABASE_URI = {settings.ASYNC_DATABASE_URI}")
# --- END DEBUGGING ---


def get_sync_sqlalchemy_url() -> str:
    """
    Returns the SQLAlchemy URL suitable for synchronous Alembic operations.
    Removes '+asyncpg' from the async DSN.
    """
    if not settings.ASYNC_DATABASE_URI:  # Check directly from settings
        raise RuntimeError(
            "ASYNC_DATABASE_URI is not set or is empty. "
            "Please check your application settings (app/core/config.py) "
            "and your .env file."
        )
    async_uri_str = str(settings.ASYNC_DATABASE_URI)
    # Replace the asyncpg driver part for sync operations
    return async_uri_str.replace("+asyncpg", "")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.
    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_sync_sqlalchemy_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Helper function to run migrations in the online context."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.
    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    if not settings.ASYNC_DATABASE_URI:  # Check directly from settings
        raise RuntimeError(
            "ASYNC_DATABASE_URI is not set or is empty. "
            "Please check your application settings (app/core/config.py) "
            "and your .env file."
        )
    async_db_url = str(settings.ASYNC_DATABASE_URI)

    connectable = create_async_engine(
        async_db_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


# --- Main Execution Logic ---
if context.is_offline_mode():
    print("INFO [env.py]: Running Alembic in offline mode.")
    run_migrations_offline()
else:
    print("INFO [env.py]: Running Alembic in online mode (async).")
    asyncio.run(run_migrations_online())
