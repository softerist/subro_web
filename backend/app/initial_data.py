import asyncio
import logging
import sys
from pathlib import Path

# Third-party imports
from fastapi_users.exceptions import UserNotExists
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

# App imports
# Import app.db.base to ensure all models are registered
import app.db.base  # noqa: F401
from app.core.config import settings
from app.core.users import UserManager
from app.crud.crud_app_settings import crud_app_settings
from app.db import session as db_session
from app.db.models.user import User as UserModel
from app.db.session import _initialize_fastapi_db_resources_sync
from app.schemas.user import UserCreate, UserUpdate

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Verify project root in sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


async def init_db(db: AsyncSession) -> None:
    """
    Initializes the database with necessary data.

    This script implements "Infrastructure as Code" bootstrapping:
    - If FIRST_SUPERUSER_* env vars are set AND no users exist, it auto-creates
      the admin and marks setup_completed=True (skipping the wizard).
    - If setup_completed is False and env vars are set, it creates the user
      and marks setup as complete.
    - If a user already exists, it updates their password to match env vars.
    - Populates settings from environment variables.
    - Creates a default /downloads storage path.
    """
    logger.info("Running initial_data.py initialization...")

    # 1. Populate Settings from Environment
    # We do this first so the system is usable immediately
    from app.services.api_validation import validate_all_settings

    await crud_app_settings.populate_from_env_defaults(db)
    logger.info("Populated app settings from environment variables.")

    # 1.1 Trigger Validation
    try:
        await validate_all_settings(db)
        logger.info("Initial settings validation completed.")
    except Exception as e:
        logger.warning(f"Initial settings validation encountered issues: {e}")

    # 2. Handle Default Storage Paths
    from app.crud.crud_storage_path import storage_path as crud_storage_path
    from app.schemas.storage_path import StoragePathCreate

    default_path = "/downloads"
    if Path(default_path).exists():
        existing_path = await crud_storage_path.get_by_path(db, path=default_path)
        if not existing_path:
            await crud_storage_path.create(
                db, obj_in=StoragePathCreate(path=default_path, label="Default Downloads")
            )
            logger.info(f"Created default storage path: {default_path}")
        else:
            logger.info(f"Default storage path {default_path} already exists.")
    else:
        logger.warning(
            f"Default path {default_path} does not exist in container. Skipping creation."
        )

    # 3. Handle Superuser and Setup Status
    app_settings = await crud_app_settings.get(db)
    setup_completed = app_settings.setup_completed

    # Get the SQLAlchemyUserDatabase adapter
    user_db_adapter = SQLAlchemyUserDatabase(db, UserModel)
    script_user_manager = UserManager(user_db_adapter)

    # Check if superuser credentials are provided in environment
    if not settings.FIRST_SUPERUSER_EMAIL or not settings.FIRST_SUPERUSER_PASSWORD:
        logger.info("No FIRST_SUPERUSER credentials in env. Skipping superuser bootstrap.")
        return

    superuser_email = settings.FIRST_SUPERUSER_EMAIL

    try:
        # Check if user already exists
        user_obj = await script_user_manager.get_by_email(superuser_email)
        logger.info(f"User {superuser_email} already exists. Updating credentials...")

        # Update password and ensuring role is admin
        user_update = UserUpdate(
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
            is_active=True,
            is_verified=True,
        )
        await script_user_manager.update(user_update, user_obj, safe=True)
        # Update role manually as it's not in UserUpdate
        user_obj.role = "admin"
        db.add(user_obj)

        logger.info(f"Superuser {superuser_email} updated successfully.")

        if not setup_completed:
            await crud_app_settings.mark_setup_completed(db)
            logger.info("Marked setup as completed (existing user found).")

    except UserNotExists:
        logger.info(f"Initial superuser {superuser_email} not found. Creating...")

        # Create the superuser
        superuser_in = UserCreate(
            email=settings.FIRST_SUPERUSER_EMAIL,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            role="admin",
            is_active=True,
            is_superuser=True,
            is_verified=True,
        )

        created_user = await script_user_manager.create(superuser_in, safe=False)
        logger.info(
            f"Initial superuser {settings.FIRST_SUPERUSER_EMAIL} (ID: {created_user.id}) created successfully."
        )

        # Mark setup as completed (bootstrapped via env vars)
        if not setup_completed:
            await crud_app_settings.mark_setup_completed(db)
            logger.info("Bootstrapped via Environment Variables. Setup Wizard skipped.")

    await db.commit()
    logger.info("Initial data creation process finished.")


async def main() -> None:
    """Main asynchronous function to set up dependencies and run database initialization."""
    logger.info("Initializing service for initial_data script...")

    # Initialize DB resources
    _initialize_fastapi_db_resources_sync()

    if db_session.FastAPISessionLocal is None:
        raise RuntimeError("FastAPISessionLocal is None after initialization.")

    async with db_session.FastAPISessionLocal() as session:
        try:
            await init_db(session)
            await session.commit()
            logger.info("Database operations committed successfully.")
        except Exception as e:
            await session.rollback()
            logger.error(f"An error occurred during database initialization: {e}", exc_info=True)
            sys.exit(1)

    logger.info("Service initialization for initial_data script finished.")


if __name__ == "__main__":
    logger.info("Running initial_data.py script...")
    asyncio.run(main())
    logger.info("Finished running initial_data.py script.")
