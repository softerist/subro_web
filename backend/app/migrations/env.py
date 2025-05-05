# backend/migrations/env.py
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import Settings  # Import your Pydantic settings

# --- Customizations Start ---
# Import your Base model and application settings
# Adjust the import path based on your project structure if needed
# Assume alembic is run from the 'backend' directory
from app.db.models.user import Base  # Import your Base from where models are defined

# Instantiate settings to access the database URL
app_settings = Settings()

# Set the target metadata for 'autogenerate' support
# Make sure all your models are imported indirectly or directly before Base is used
target_metadata = Base.metadata


# Function to modify the config URL for Alembic's sync operations
def get_sync_database_url() -> str:
    """Returns the database URL suitable for synchronous Alembic operations."""
    db_url = app_settings.ASYNC_DATABASE_URI  # Start with the configured async URL
    # Alembic typically works best with the sync version of the URL
    # Replace +asyncpg with the standard driver if present
    sync_url = db_url.replace("+asyncpg", "")
    # Ensure it starts with postgresql://
    if not sync_url.startswith("postgresql://"):
        # Handle case where DATABASE_URL might already be sync format but needs prefix
        if "://" in sync_url:
            driver, rest = sync_url.split("://", 1)
            sync_url = f"postgresql://{rest}"
        else:  # Assume it's a relative path or malformed - less likely with PostgresDsn
            raise ValueError(f"Unexpected database URL format for sync operations: {sync_url}")

    # Set the environment variable expected by alembic.ini IF not already set directly
    # Alembic's ini interpolation takes precedence if already set in env
    # Also update the live Alembic config object
    os.environ.setdefault("DATABASE_URL", sync_url)
    config.set_main_option("sqlalchemy.url", sync_url)
    return sync_url


# --- Customizations End ---

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Configure the base URL from settings before running migrations
sync_url = get_sync_database_url()

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    # url = config.get_main_option("sqlalchemy.url") # URL is now set globally above
    context.configure(
        url=sync_url,  # Use the derived sync_url
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Add compare_type for detecting type changes
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # engine_from_config expects the URL to be already set in the config object
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        # Ensure the URL from settings is used if not overridden by ini
        # url=sync_url # This usually isn't needed as config object is updated
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Add compare_type for detecting type changes
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
