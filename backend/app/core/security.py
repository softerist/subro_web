# backend/app/core/security.py

import logging
import uuid

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, exceptions
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    CookieTransport,
    JWTStrategy,
)
from fastapi_users.password import PasswordHelper

# MODIFICATION 1: Import BaseUserCreate for compatibility with older fastapi-users versions
from fastapi_users.schemas import BaseUserCreate  # Or your Pydantic v1 compatible import if needed
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase

from app.core.config import settings
from app.db.models.user import User
from app.db.session import get_user_db

# If you have a custom UserCreate schema, you might prefer to import and use that:
# from app.schemas.user import UserCreate as CustomUserCreateSchema

logger = logging.getLogger(__name__)

# --- Password Hashing ---
password_helper = PasswordHelper()


# START ADDED CODE: Expose password hashing and verification functions
def get_password_hash(password: str) -> str:
    """Hashes a password using the configured password helper."""
    return password_helper.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a hashed password."""
    return password_helper.verify(plain_password, hashed_password)


# END ADDED CODE


# --- User Manager ---
class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = str(settings.SECRET_KEY)
    verification_token_secret = str(settings.SECRET_KEY)

    # In class UserManager
    async def on_after_register(self, user: User, _request: Request | None = None) -> None:
        logger.info(f"User {user.id} with email {user.email} has registered.")

    async def on_after_forgot_password(
        self, user: User, token: str, _request: Request | None = None
    ) -> None:
        # Updated to use logger for consistency
        logger.info(f"User {user.id} has requested a password reset. Token: {token}")

    async def on_after_request_verify(
        self, user: User, token: str, _request: Request | None = None
    ) -> None:
        logger.info(f"Verification requested for user {user.id}. Token: {token}")

    async def create(
        self,
        user_create: BaseUserCreate,  # Or your Pydantic v1 compatible import
        safe: bool = False,
        request: Request | None = None,
    ) -> User:
        await self.validate_password(user_create.password, user_create)

        existing_user_by_email = await self.user_db.get_by_email(user_create.email)
        if existing_user_by_email is not None:
            raise exceptions.UserAlreadyExists()

        user_dict = (
            user_create.create_update_dict() if safe else user_create.create_update_dict_superuser()
        )

        password = user_create.password  # Store original password
        # UserManager uses its own password_helper instance internally,
        # which is typically the one passed during its instantiation.
        # If not specified, it creates its own. Here we ensure it uses the shared one.
        user_dict["hashed_password"] = self.password_helper.hash(password)

        if "password" in user_dict:  # Defensive pop
            user_dict.pop("password")

        # Custom logic for 'role' field
        if hasattr(user_create, "role") and user_create.role is not None:  # type: ignore
            user_dict["role"] = user_create.role  # type: ignore
            if user_create.role == "admin":  # type: ignore
                user_dict["is_superuser"] = True
            # elif user_create.role == "standard": # type: ignore # Redundant, default is False
            #     user_dict["is_superuser"] = False
        elif (
            user_dict.get("is_superuser") is True and "role" not in user_dict
        ):  # Ensure role is set if is_superuser is true
            user_dict["role"] = "admin"
        # If is_superuser is false or not set, and role is not set, it will be default or None

        created_user = await self.user_db.create(user_dict)
        await self.on_after_register(created_user, request)
        return created_user


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    # Pass the module-level password_helper to the UserManager instance
    yield UserManager(user_db, password_helper)


# --- JWT Strategy ---
def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=str(settings.SECRET_KEY),
        lifetime_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        algorithm=settings.ALGORITHM,
        token_audience=[
            "fastapi-users:auth",
            "fastapi-users:verify",
            "fastapi-users:reset-password",
        ],
    )


# --- Authentication Transports ---

bearer_transport = BearerTransport(tokenUrl=f"{settings.API_V1_STR}/auth/login")

cookie_transport = CookieTransport(
    cookie_name=settings.REFRESH_TOKEN_COOKIE_NAME,
    cookie_max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    cookie_path=f"{settings.API_V1_STR}/auth",  # Path for cookie availability
    cookie_secure=settings.COOKIE_SECURE,
    cookie_httponly=True,
    cookie_samesite=settings.COOKIE_SAMESITE,
)

# --- Authentication Backend Instances ---
cookie_auth_backend = AuthenticationBackend(
    name="jwt-cookie",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)
bearer_auth_backend = AuthenticationBackend(
    name="jwt-bearer",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# --- FastAPIUsers Main Instance ---
fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [
        cookie_auth_backend,
        bearer_auth_backend,
    ],
)

# --- Reusable Dependencies ---
current_active_user: User = fastapi_users.current_user(active=True)
current_active_superuser: User = fastapi_users.current_user(active=True, superuser=True)
current_user_optional: User | None = fastapi_users.current_user(optional=True)
current_active_verified_user: User = fastapi_users.current_user(active=True, verified=True)
