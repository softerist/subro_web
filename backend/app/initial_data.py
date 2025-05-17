# backend/app/initial_data.py
import asyncio
import logging
import sys
from pathlib import Path

# Third-party imports (fastapi_users, sqlalchemy)
from fastapi_users.exceptions import UserAlreadyExists
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

# Your application imports (app.core, app.db, app.schemas)
from app.core.config import settings
from app.core.users import UserManager
from app.db.models.user import User as UserModel
from app.db.session import AsyncSessionLocal
from app.schemas.user import UserCreate

# --- BEGIN EARLY PATH MODIFICATION ---
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
# --- END EARLY PATH MODIFICATION ---

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_user_with_usermanager(
    user_manager_instance: UserManager, user_in: UserCreate
) -> None:
    """
    Creates a user using the provided UserManager instance.
    Checks if the user already exists by email before attempting creation.
    """
    email_to_check = getattr(user_in, "email", None)
    if not email_to_check:
        logger.error("UserCreate object missing email. Cannot proceed with user creation.")
        return

    try:
        # UserManager.create already handles checking for existing users
        # and raises UserAlreadyExists if the user exists.
        # It also handles password hashing.
        # safe=True is the default and recommended for UserCreate which has plain password.
        created_user = await user_manager_instance.create(user_in, safe=True)
        logger.info(f"User {created_user.email} (ID: {created_user.id}) created successfully.")

        if getattr(created_user, "is_superuser", False):  # Check the created_user object
            logger.info(f"User {created_user.email} has been created as a superuser.")

    except UserAlreadyExists:
        logger.info(f"User with email {email_to_check} already exists. Skipping creation.")
    except Exception as e:
        logger.error(
            f"An unexpected error occurred while creating user {email_to_check}: {e}",
            exc_info=True,  # Use exc_info for full traceback in logs
        )


async def init_db(db: AsyncSession) -> None:  # Pass AsyncSession directly
    """Initializes the database with necessary data, such as a superuser."""
    logger.info("Creating initial data...")

    # Get the SQLAlchemyUserDatabase adapter
    user_db_adapter = SQLAlchemyUserDatabase(db, UserModel)
    # Instantiate UserManager
    script_user_manager = UserManager(
        user_db_adapter
    )  # password_helper is part of UserManager's defaults

    # Check if superuser credentials are provided in settings
    if settings.FIRST_SUPERUSER_EMAIL and settings.FIRST_SUPERUSER_PASSWORD:
        superuser_in = UserCreate(
            email=settings.FIRST_SUPERUSER_EMAIL,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            role="admin",  # Will be UserRole.ADMIN due to Pydantic coercion
            is_active=True,
            is_superuser=True,
            is_verified=True,
        )
        logger.info(
            f"LIFESPAN PRE-CREATE: superuser_in Pydantic model: {superuser_in.model_dump_json(indent=2)}"
        )  # <<< ADD THIS

        # Ensure script_user_manager is correctly getting your user_db that uses CRUDUser
        # or that SQLAlchemyUserDatabase itself works as expected
        created_user = await script_user_manager.create(superuser_in, safe=True)
        await db.commit()  # Changed from session to db

        logger.info(
            f"LIFESPAN POST-CREATE: created_user object: id={created_user.id}, email={created_user.email}, role={getattr(created_user, 'role', 'N/A')}, is_superuser={getattr(created_user, 'is_superuser', 'N/A')}, is_verified={getattr(created_user, 'is_verified', 'N/A')}"
        )  # <<< ADD THIS
        logger.info(
            f"Initial superuser {settings.FIRST_SUPERUSER_EMAIL} (ID: {created_user.id}) created successfully (according to user_manager)."
        )

    # Placeholder for creating other initial data
    # logger.info("Creating other initial data if necessary...")

    logger.info("Initial data creation process finished.")


async def main() -> None:
    """Main asynchronous function to set up dependencies and run database initialization."""
    logger.info("Initializing service for initial_data script...")

    # Use a context manager for the session
    async with AsyncSessionLocal() as session:
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
