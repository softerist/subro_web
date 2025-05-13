import asyncio
import logging
import sys
from logging.config import fileConfig  # Moved up: Standard library related
from pathlib import Path  # Ensure Path is imported before first use

# Third-party imports (not dependent on local app path modification)
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# --- BEGIN EARLY PATH MODIFICATION ---
# This block ensures that the 'app' module (containing core.config, db.base, db.models)
# is findable by Python when Alembic runs this script.
# It assumes 'env.py' is in 'project_root/alembic/' and 'app' is in 'project_root/app/'.
# 'project_root_for_app_module' will thus point to 'project_root'.

# alembic_dir is the directory containing this env.py file
alembic_dir = Path(__file__).resolve().parent
# project_root_for_app_module is the parent of alembic_dir (e.g., your project's root)
project_root_for_app_module = alembic_dir.parent

if str(project_root_for_app_module) not in sys.path:
    sys.path.insert(0, str(project_root_for_app_module))
    # Optional: print for debugging path setup
    # print(f"DEBUG [env.py early path mod]: Added {project_root_for_app_module} to sys.path.")
    # print(f"DEBUG [env.py early path mod]: sys.path is now: {sys.path}")
# --- END EARLY PATH MODIFICATION ---

# Application imports - these should now work due to path modification
# is used because these imports must happen after sys.path is modified.
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402

# --- Model Imports for Debugging (Optional but helpful) ---
# These are kept separate as they are for debugging and might cause circular deps if not handled carefully
try:
    from app.db.models.user import User as UserModelForDebug
except ImportError:
    UserModelForDebug = None
try:
    from app.db.models.job import Job as JobModelForDebug
    from app.db.models.job import JobStatus as JobStatusForDebug
except ImportError:
    JobModelForDebug = None
    JobStatusForDebug = None

# --- Setup Logger ---
logger = logging.getLogger("alembic.env")
# Basic logging setup if not configured by alembic.ini or fileConfig
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)  # Default to INFO if no handlers
    logger.setLevel(logging.INFO)

# --- Alembic Config Object ---
config = context.config

# Interpret the config file for Python logging (if specified in alembic.ini)
# This line uses fileConfig which was imported at the top.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
    logger.info(f"Logging configured from: {config.config_file_name}")
else:
    logger.info(
        "No config_file_name in Alembic config for logging, using basicConfig if no handlers were found."
    )


# --- Target Metadata ---
# This is your SQLAlchemy models' metadata, needed for autogenerate.
target_metadata = Base.metadata  # Uses Base imported from app.db.base
logger.debug(f"Target metadata object: {target_metadata}")


# --- Naming Convention (CRUCIAL for op.f() compatibility) ---
# This convention helps Alembic generate consistent constraint names
# like pk_users, fk_jobs_user_id_users, ix_users_email
# which match your target migration file's op.f() calls.
naming_convention = {
    "ix": "ix_%(table_name)s_%(column_0_label)s",  # Index names
    "uq": "uq_%(table_name)s_%(column_0_name)s",  # Unique constraint names
    "ck": "ck_%(table_name)s_%(constraint_name)s",  # Check constraint names (can also use column names)
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",  # Foreign key names
    "pk": "pk_%(table_name)s",  # Primary key names
}
logger.debug(f"Using naming convention: {naming_convention}")

# --- Database URI Construction (From your settings) ---
MANUALLY_CONSTRUCTED_ASYNC_URI: str
try:
    # Uses settings imported from app.core.config
    db_user = settings.POSTGRES_USER
    db_password = settings.POSTGRES_PASSWORD
    db_server = settings.POSTGRES_SERVER
    db_port = settings.POSTGRES_PORT
    db_name = settings.POSTGRES_DB

    if not all(
        [db_user, db_password, db_server, db_name is not None]
    ):  # db_port can be int 0 but db_name must exist
        missing_components = [
            comp
            for comp, val in [
                ("POSTGRES_USER", db_user),
                ("POSTGRES_PASSWORD", db_password),
                ("POSTGRES_SERVER", db_server),
                ("POSTGRES_DB", db_name),
            ]
            if not val and comp != "POSTGRES_DB" or (comp == "POSTGRES_DB" and val is None)
        ]
        raise ValueError(
            f"PostgreSQL connection components missing from settings: {missing_components}"
        )

    MANUALLY_CONSTRUCTED_ASYNC_URI = (
        f"postgresql+asyncpg://{db_user}:{db_password}@{db_server}:{db_port}/{db_name}"
    )
    logger.info(
        f"Successfully constructed ASYNC_URI for Alembic: {MANUALLY_CONSTRUCTED_ASYNC_URI.replace(db_password, '****') if db_password else MANUALLY_CONSTRUCTED_ASYNC_URI}"
    )

except Exception as e:
    logger.error(
        f"FATAL: Failed to construct database URI in env.py from settings: {e}", exc_info=True
    )
    # B904: raise ... from e is good practice for explicit re-raise
    raise SystemExit(f"FATAL: Database URI construction failed: {e}") from e


# --- Debugging Model Registration (Optional: Your existing debugging can go here) ---
logger.debug("=" * 50)
logger.debug("DEBUG [env.py]: Model Registration & Metadata Check:")
if (
    UserModelForDebug
    and hasattr(UserModelForDebug, "__table__")
    and UserModelForDebug.__table__ in target_metadata.tables.values()
):
    logger.debug(f"  UserModel '{UserModelForDebug.__tablename__}' is IN target_metadata.")
else:
    logger.warning("  UserModel NOT FOUND in target_metadata or not a valid SQLAlchemy model.")
if (
    JobModelForDebug
    and hasattr(JobModelForDebug, "__table__")
    and JobModelForDebug.__table__ in target_metadata.tables.values()
):
    logger.debug(f"  JobModel '{JobModelForDebug.__tablename__}' is IN target_metadata.")
else:
    logger.warning("  JobModel NOT FOUND in target_metadata or not a valid SQLAlchemy model.")

logger.debug(f"  Known tables by target_metadata: {list(target_metadata.tables.keys())}")

if JobStatusForDebug and hasattr(JobStatusForDebug, "__members__"):
    logger.debug(
        f"  JobStatus enum values (from debug import): {[item.value for item in JobStatusForDebug]}"
    )
else:
    logger.debug("  JobStatusForDebug enum not found or not imported correctly.")
logger.debug("=" * 50)


# --- Alembic Migration Functions ---
def get_sync_sqlalchemy_url() -> str:
    """Returns the SQLAlchemy URL suitable for synchronous Alembic operations."""
    if not MANUALLY_CONSTRUCTED_ASYNC_URI:
        # This should ideally not happen if the URI construction above is successful or raises SystemExit
        logger.error(
            "MANUALLY_CONSTRUCTED_ASYNC_URI was not set before calling get_sync_sqlalchemy_url!"
        )
        raise RuntimeError("MANUALLY_CONSTRUCTED_ASYNC_URI was not set!")
    # Replace the asyncpg part for a sync driver (psycopg2 will be inferred by SQLAlchemy)
    sync_url = MANUALLY_CONSTRUCTED_ASYNC_URI.replace("+asyncpg", "")
    # Uses settings imported from app.core.config for password redaction
    logger.debug(
        f"get_sync_sqlalchemy_url: Returning sync_url = {sync_url.replace(settings.POSTGRES_PASSWORD, '****') if settings.POSTGRES_PASSWORD else sync_url}"
    )
    return sync_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_sync_sqlalchemy_url()
    # Uses settings imported from app.core.config for password redaction
    logger.info(
        f"Running migrations in offline mode using URL: {url.replace(settings.POSTGRES_PASSWORD, '****') if settings.POSTGRES_PASSWORD else url}"
    )
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,  # Useful for SQL script generation
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # Detect column type changes
        render_as_batch=True,  # Essential for op.batch_alter_table and some DBs like SQLite
        compare_server_default=True,  # Compare server default values
        naming_convention=naming_convention,  # Apply the defined naming convention
    )
    with context.begin_transaction():
        context.run_migrations()
    logger.info("Offline migrations complete.")


def do_run_migrations(connection: Connection) -> None:
    """Helper function to run migrations in the online context."""
    logger.debug("Configuring context for online migration run.")
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # Detect column type changes
        render_as_batch=True,  # Essential for op.batch_alter_table
        compare_server_default=True,  # Compare server default values
        naming_convention=naming_convention,  # Apply the defined naming convention
        # Additional options if needed:
        # include_schemas=True, # If you use multiple schemas and want Alembic to manage them
        # process_revision_directives=your_directive_processor, # For custom migration generation logic
    )
    logger.info("Beginning transaction and running migrations...")
    with context.begin_transaction():
        context.run_migrations()
    logger.info("Online migration step complete.")


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    if not MANUALLY_CONSTRUCTED_ASYNC_URI:
        # This should ideally not happen
        logger.error(
            "MANUALLY_CONSTRUCTED_ASYNC_URI was not set before calling run_migrations_online!"
        )
        raise RuntimeError("MANUALLY_CONSTRUCTED_ASYNC_URI was not set!")

    async_db_url = MANUALLY_CONSTRUCTED_ASYNC_URI
    # Uses settings imported from app.core.config for password redaction
    logger.info(
        f"Running migrations in online (async) mode. Connecting to: {async_db_url.replace(settings.POSTGRES_PASSWORD, '****') if settings.POSTGRES_PASSWORD else async_db_url}"
    )

    connectable = create_async_engine(  # Uses create_async_engine imported at the top
        async_db_url,
        poolclass=pool.NullPool,  # Use NullPool for Alembic, as it makes single connections. Uses pool imported at the top.
    )

    async with connectable.connect() as connection:
        logger.info(
            "Established async connection. Running migrations synchronously within transaction."
        )
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()
    logger.info("Async connection disposed. Online migrations complete.")

    # Optional: Print tables found by metadata after run for debugging
    # logger.debug("Target Metadata Tables (after online run):")
    # for table_name in target_metadata.tables:
    #     logger.debug(f"- {table_name}")


# --- Main Execution Logic ---
if context.is_offline_mode():  # Uses context imported at the top
    logger.info("Alembic context is in offline mode.")
    run_migrations_offline()
else:
    logger.info("Alembic context is in online mode (async).")
    asyncio.run(run_migrations_online())  # Uses asyncio imported at the top

logger.info("Alembic env.py script execution finished.")
