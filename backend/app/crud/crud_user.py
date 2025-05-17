# backend/app/crud/crud_user.py
import logging
from typing import Any
from uuid import UUID  # Ensure UUID is imported

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, verify_password
from app.crud.base import CRUDBase
from app.db.models.user import User  # Your User SQLAlchemy model
from app.schemas.user import (  # Your Pydantic schemas for User
    AdminUserUpdate,  # For admin updates
    UserCreate,
    UserRole,  # Import UserRole if it's used for role updates
    UserUpdate,
)

logger = logging.getLogger(__name__)


class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
    async def get_by_email(self, db: AsyncSession, *, email: str) -> User | None:
        """
        Get a user by email.
        """
        logger.debug(f"Attempting to retrieve user by email: {email}")
        result = await db.execute(select(self.model).filter(self.model.email == email))
        user = result.scalars().first()
        if user:
            logger.debug(f"User found by email: {email} (ID: {user.id})")
        else:
            logger.debug(f"No user found with email: {email}")
        return user

    async def get_by_id(self, db: AsyncSession, *, user_id: UUID) -> User | None:
        """
        Get a user by ID. Overrides base to ensure UUID type.
        """
        logger.debug(f"Attempting to retrieve user by ID: {user_id}")
        return await super().get(db, id=user_id)

    async def create(self, db: AsyncSession, *, obj_in: UserCreate) -> User:
        """
        Create a new user.
        - Hashes the password before storing.
        - Sets the role (and is_superuser based on role) if provided, otherwise defaults.
        """
        logger.info(f"Creating new user with email: {obj_in.email}, role: {obj_in.role}")

        hashed_password = get_password_hash(obj_in.password)

        # Prepare data for User model, excluding the plain password
        user_data = obj_in.model_dump(exclude={"password"})
        user_data["hashed_password"] = hashed_password

        # Ensure role is handled correctly and is_superuser is synced
        if obj_in.role:  # If role is explicitly provided in UserCreate
            user_data["role"] = obj_in.role
            user_data["is_superuser"] = obj_in.role == UserRole.ADMIN
        else:  # Default role if not provided (assuming your UserCreate has a default or User model does)
            # If UserCreate doesn't have a default role, the User model's default will apply
            # but we might want to explicitly set is_superuser based on a default role assumption
            # For now, let's assume User model default handles this or UserCreate requires role.
            # If your UserCreate allows role to be None, you might set a default here.
            # e.g., user_data["role"] = UserRole.STANDARD
            # user_data["is_superuser"] = False
            pass  # Rely on SQLAlchemy model default for role if not in UserCreate

        db_obj = self.model(**user_data)

        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        logger.info(f"User {db_obj.email} (ID: {db_obj.id}) created successfully.")
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: User,
        obj_in: UserUpdate | AdminUserUpdate | dict[str, Any],
    ) -> User:
        """
        Update a user.
        - If password is in obj_in, it will be hashed.
        - If role is in obj_in (from AdminUserUpdate), is_superuser will be synced.
        """
        logger.info(f"Updating user: {db_obj.email} (ID: {db_obj.id})")

        update_data = {}
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)

        if update_data.get("password"):
            logger.debug(f"Password update requested for user {db_obj.email}.")
            hashed_password = get_password_hash(update_data["password"])
            db_obj.hashed_password = hashed_password
            del update_data["password"]  # Remove plain password from further processing
            logger.debug(f"Password hashed for user {db_obj.email}.")

        if "role" in update_data:
            # This typically comes from AdminUserUpdate
            new_role = update_data["role"]
            if isinstance(new_role, str):  # Convert string to Enum if necessary
                try:
                    new_role = UserRole(new_role.lower())
                except ValueError:
                    logger.warning(f"Invalid role value '{update_data['role']}' for user update.")
                    # Decide: raise error or ignore? For now, let setattr handle it or Pydantic validation catch it.

            db_obj.role = new_role  # type: ignore
            db_obj.is_superuser = new_role == UserRole.ADMIN
            logger.debug(
                f"Role updated to {db_obj.role}, is_superuser set to {db_obj.is_superuser} for user {db_obj.email}."
            )
            # del update_data["role"] # No, let it be set by setattr if not handled above

        # Apply other updates
        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
            else:
                logger.warning(f"Attempted to update non-existent field '{field}' on User model.")

        db.add(db_obj)  # db_obj is already in session, this marks it as dirty
        await db.commit()
        await db.refresh(db_obj)
        logger.info(f"User {db_obj.email} (ID: {db_obj.id}) updated successfully.")
        return db_obj

    async def authenticate(self, db: AsyncSession, *, email: str, password: str) -> User | None:
        """
        Authenticate a user by email and password.
        Returns the user object if authentication is successful, None otherwise.
        Note: fastapi-users UserManager.authenticate handles this robustly.
              This is a simplified version if needed directly.
        """
        logger.debug(f"Attempting to authenticate user with email: {email}")
        user = await self.get_by_email(db, email=email)
        if not user:
            logger.debug(f"Authentication failed: No user found with email {email}.")
            return None
        if not user.is_active:  # Assuming User model has an is_active field
            logger.debug(f"Authentication failed: User {email} is inactive.")
            return None
        if not verify_password(password, user.hashed_password):
            logger.debug(f"Authentication failed: Incorrect password for user {email}.")
            return None

        logger.info(f"User {email} authenticated successfully.")
        return user

    async def is_active(self, user: User) -> bool:
        return user.is_active

    async def is_superuser(self, user: User) -> bool:
        # Directly use the model's attribute, which should be synced with role
        return user.is_superuser

    async def is_verified(self, user: User) -> bool:
        # Directly use the model's attribute
        return user.is_verified  # Assuming User model has an is_verified field


# Create an instance of the CRUDUser class for User model
user = CRUDUser(User)
