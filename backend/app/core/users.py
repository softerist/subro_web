# backend/app/core/users.py
import logging  # <--- ADDED: Import logging
import uuid

from fastapi import Depends, Request, Response  # <--- ADDED: Response for type hint
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    CookieTransport,
    JWTStrategy,
)

# from fastapi_users.db import SQLAlchemyUserDatabase # Required for type hint in get_user_manager
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase  # Correct for newer versions

# Project-specific imports
from app.core.config import settings
from app.db.models.user import User

# Import the definitive get_user_db adapter factory from db.session
from app.db.session import get_user_db as get_user_db_adapter_from_session

# --- Logger Setup ---
# Use __name__ for module-specific logger, or settings.LOGGER_NAME for a global app logger if defined
logger = logging.getLogger(__name__)  # <--- ADDED: Define logger


# User Manager
class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.SECRET_KEY
    verification_token_secret = settings.SECRET_KEY

    async def on_after_register(
        self, user: User, _request: Request | None = None
    ):  # <--- MODIFIED: _request
        logger.info(f"User {user.id} ({user.email}) has registered.")

    async def on_after_forgot_password(
        self,
        user: User,
        token: str,
        _request: Request | None = None,  # <--- MODIFIED: _request
    ):
        logger.info(
            f"User {user.id} ({user.email}) has requested a password reset. Token: {token[:8]}..."
        )
        # Implement actual email sending logic here.

    async def on_after_request_verify(
        self, user: User, token: str, _request: Request | None = None
    ):  # <--- MODIFIED: _request
        logger.info(
            f"Verification requested for user {user.id} ({user.email}). Token: {token[:8]}..."
        )
        # Implement actual email sending logic here.

    async def on_after_verify(
        self, user: User, _token: str, _request: Request | None = None
    ):  # <--- MODIFIED: _token, _request
        # Assuming token is not used in this specific hook for logging purposes
        logger.info(f"User {user.id} ({user.email}) has been verified.")

    # Added from your fastapi-users setup for custom login/logout
    async def on_after_login(
        self,
        user: User,
        _request: Request | None = None,  # <--- MODIFIED: _request
        _response: Response
        | None = None,  # <--- ADDED & MODIFIED: _response (if response is provided by hook)
    ) -> None:
        logger.info(f"User {user.id} ({user.email}) logged in successfully.")

    async def on_after_logout(
        self,
        user: User,
        _request: Request | None = None,  # <--- MODIFIED: _request
        _response: Response | None = None,  # <--- ADDED & MODIFIED: _response
    ) -> None:
        logger.info(f"User {user.id} ({user.email}) logged out successfully.")


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db_adapter_from_session),
):
    """Dependency to get the UserManager instance."""
    yield UserManager(user_db)


# This get_user_db is defined in db.session.py and imported as get_user_db_adapter_from_session
# So, the one below is redundant if you're using the one from db.session.
# If you intend to keep this one, ensure it's used consistently or remove it.
# For now, I'll comment it out, assuming get_user_db_adapter_from_session is primary.
# async def get_user_db(
#     session: AsyncSession = Depends(get_async_session),
# ) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
#     """
#     Dependency to get the SQLAlchemyUserDatabase adapter for FastAPI-Users.
#     """
#     yield SQLAlchemyUserDatabase(session, User)


# --- Authentication Transports ---
# Bearer token for access tokens (passed in Authorization header)
bearer_transport = BearerTransport(tokenUrl=f"{settings.API_V1_STR}/auth/login")

# Cookie transport for refresh tokens (HttpOnly cookie)
refresh_cookie_transport = CookieTransport(
    cookie_name=settings.REFRESH_TOKEN_COOKIE_NAME,
    cookie_max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    cookie_path=f"{settings.API_V1_STR}/auth",
    cookie_secure=settings.COOKIE_SECURE,
    cookie_httponly=True,
    cookie_samesite=settings.COOKIE_SAMESITE,
)


# --- JWT Strategies ---
def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=settings.SECRET_KEY,
        lifetime_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def get_refresh_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=settings.JWT_REFRESH_SECRET_KEY,
        lifetime_seconds=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )


# --- Authentication Backends ---
auth_backend_access = AuthenticationBackend(
    name="jwt-access",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

auth_backend_refresh = AuthenticationBackend(
    name="jwt-refresh",
    transport=refresh_cookie_transport,
    get_strategy=get_refresh_jwt_strategy,
)

fastapi_users_instance = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend_access],
)

# --- Current User Dependencies ---
current_active_user = fastapi_users_instance.current_user(active=True)
current_active_verified_user = fastapi_users_instance.current_user(active=True, verified=True)
current_active_superuser = fastapi_users_instance.current_user(active=True, superuser=True)
