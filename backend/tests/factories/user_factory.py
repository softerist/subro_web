# backend/tests/factories/user_factory.py

import uuid
from typing import Any

import factory
from sqlalchemy.ext.asyncio import AsyncSession  # Import AsyncSession for type hinting

from app.core.security import password_helper  # Use the same password helper as the app
from app.db.models.user import User


class UserFactory(factory.Factory):
    """
    Factory for creating User model instances for testing.

    Note: This factory requires an explicit session to be passed to its
          create_* methods (`create_user`, `create_admin`) and relies on
          the calling test to handle flushing/committing the session.
    """

    class Meta:
        model = User
        # Exclude 'password' from being passed directly to the User model constructor
        # if it doesn't accept it (which it shouldn't, it expects hashed_password)
        exclude = ("password",)

    id: uuid.UUID = factory.LazyFunction(uuid.uuid4)
    email: str = factory.Sequence(lambda n: f"testuser{n}@example.com")
    # Define a raw password attribute for convenience in tests
    # This won't be passed to the model directly due to 'exclude' in Meta
    password: str = "password123"
    # Use the raw password to generate the hashed_password
    hashed_password: str = factory.LazyAttribute(lambda o: password_helper.hash(o.password))
    is_active: bool = True
    is_superuser: bool = False  # Default to standard user
    is_verified: bool = False  # Default to not verified
    role: str = "standard"  # Default role
    force_password_change: bool = False  # Default to False
    # Optional: Add other fields if needed, e.g., first_name, last_name

    @classmethod
    def _create(
        cls: type["UserFactory"], model_class: type[User], *args: Any, **kwargs: Any
    ) -> User:
        """
        Override _create to prevent saving automatically (Factory Boy default).
        We want manual session handling via create_user/create_admin.
        Alternatively, use build() directly in create_user/create_admin.
        Using build() is simpler for this pattern.
        """
        # This method might not be strictly necessary if create_user uses build()
        # but ensures factory.create() won't work unexpectedly without a session.
        raise NotImplementedError("Use create_user or create_admin methods with a session.")

    @classmethod
    def _build(
        cls: type["UserFactory"], model_class: type[User], *args: Any, **kwargs: Any
    ) -> User:
        """
        Override _build just to be explicit about password handling,
        although LazyAttribute handles it.
        """
        raw_password = kwargs.pop("password", None)  # Get raw password if passed
        if raw_password:
            # If a raw password was passed, recalculate hash based on it
            kwargs["hashed_password"] = password_helper.hash(raw_password)
        elif "hashed_password" not in kwargs:
            # If no raw password and no explicit hashed_password, use default hash
            default_hashed_password = password_helper.hash(cls.password)  # Use default raw password
            kwargs["hashed_password"] = default_hashed_password

        return super()._build(model_class, *args, **kwargs)

    @classmethod
    def create_user(cls: type["UserFactory"], session: AsyncSession, **kwargs: Any) -> User:
        """
        Builds a User instance, adds it to the provided session.
        Does NOT commit or flush the session.

        Args:
            session: The SQLAlchemy AsyncSession to add the user to.
            **kwargs: Override attributes for the user (e.g., email, password, is_active).
                      If 'password' is provided, it will be hashed.

        Returns:
            The newly created (but not flushed/committed) User instance.
        """
        # Use build() to create the instance without saving
        user = cls.build(**kwargs)
        session.add(user)
        # Flushing/committing should be handled by the caller (test fixture/function)
        # await session.flush() # DO NOT FLUSH HERE
        return user

    @classmethod
    def create_admin(cls: type["UserFactory"], session: AsyncSession, **kwargs: Any) -> User:
        """
        Builds an admin User instance, adds it to the provided session.
        Does NOT commit or flush the session.

        Args:
            session: The SQLAlchemy AsyncSession to add the user to.
            **kwargs: Override attributes for the user.

        Returns:
            The newly created (but not flushed/committed) admin User instance.
        """
        kwargs.setdefault("is_superuser", True)
        kwargs.setdefault("role", "admin")
        # Use build() to create the instance without saving
        user = cls.build(**kwargs)
        session.add(user)
        # Flushing/committing should be handled by the caller (test fixture/function)
        return user


# Ensure this factory is importable, e.g., via tests/factories/__init__.py:
#
# from .user_factory import UserFactory
#
# __all__ = ["UserFactory"]
#
