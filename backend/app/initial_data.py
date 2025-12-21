import asyncio
import logging
import sys
from pathlib import Path

# Third-party imports
from fastapi_users.exceptions import UserNotExists
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

# App imports
# Import app.db.base to ensure all models are registered (especially Job before User relationship resolution)
import app.db.base  # noqa: F401
from app.core.config import settings
from app.core.users import UserManager
from app.db import session as db_session

# Use simplified Job string in User model, but explicit imports help validation if needed
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
    """Initializes the database with necessary data, such as a superuser."""
    logger.info("Creating initial data...")

    # Get the SQLAlchemyUserDatabase adapter
    user_db_adapter = SQLAlchemyUserDatabase(db, UserModel)
    # Instantiate UserManager
    script_user_manager = UserManager(user_db_adapter)

    # Check if superuser credentials are provided in settings
    if settings.FIRST_SUPERUSER_EMAIL and settings.FIRST_SUPERUSER_PASSWORD:
        superuser_email = settings.FIRST_SUPERUSER_EMAIL

        try:
            # Check if user already exists
            user_obj = await script_user_manager.get_by_email(superuser_email)
            logger.info(
                f"User {superuser_email} already exists. Updating password to verify credentials..."
            )

            # Update password using UserUpdate schema
            user_update = UserUpdate(
                password=settings.FIRST_SUPERUSER_PASSWORD,
                is_superuser=True,
                is_active=True,
                is_verified=True,
            )
            # safe=True avoids errors if checking against restricted fields, or ensures standard validation
            await script_user_manager.update(user_update, user_obj, safe=True)
            logger.info(f"Superuser {superuser_email} password updated successfully.")

        except UserNotExists:
            logger.info(f"User {superuser_email} does not exist. Creating new superuser...")
            superuser_in = UserCreate(
                email=settings.FIRST_SUPERUSER_EMAIL,
                password=settings.FIRST_SUPERUSER_PASSWORD,
                role="admin",  # Will be UserRole.ADMIN due to Pydantic coercion
                is_active=True,
                is_superuser=True,
                is_verified=True,
            )

            created_user = await script_user_manager.create(superuser_in, safe=True)
            logger.info(
                f"Initial superuser {settings.FIRST_SUPERUSER_EMAIL} (ID: {created_user.id}) created successfully."
            )

        await db.commit()

    logger.info("Initial data creation process finished.")


async def main() -> None:
    """Main asynchronous function to set up dependencies and run database initialization."""
    logger.info("Initializing service for initial_data script...")

    # Initialize DB resources
    _initialize_fastapi_db_resources_sync()

    # Use a context manager for the session
    if db_session.FastAPISessionLocal is None:
        raise RuntimeError("FastAPISessionLocal is None after initialization.")

    async with db_session.FastAPISessionLocal() as session:
        try:
            await init_db(session)  # Pass the session to init_db
            await session.commit()  # Commit transactions made within init_db
            logger.info("Database operations committed successfully.")
        except Exception as e:
            await session.rollback()  # Rollback on error
            logger.error(f"An error occurred during database initialization: {e}", exc_info=True)
        # Session is automatically closed by the context manager

    logger.info("Service initialization for initial_data script finished.")


if __name__ == "__main__":
    logger.info("Running initial_data.py script...")
    asyncio.run(main())
    logger.info("Finished running initial_data.py script.")
