import logging
import uuid
from datetime import UTC

from fastapi import (
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi_users import (
    BaseUserManager,
    FastAPIUsers,
    UUIDIDMixin,
)
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    CookieTransport,
    JWTStrategy,
)
from fastapi_users.password import PasswordHelper
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase

# Project-specific imports
from app.core.config import settings
from app.db.models.user import User

# Import the definitive get_user_db adapter factory from db.session
from app.db.session import get_user_db as get_user_db_adapter_from_session

# --- Logger Setup ---
logger = logging.getLogger(__name__)

# Strong references to background tasks to prevent GC
_background_tasks = set()

# --- Password Helper ---
password_helper = PasswordHelper()


# User Manager
class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.SECRET_KEY
    verification_token_secret = settings.SECRET_KEY

    async def on_after_register(self, user: User, _request: Request | None = None):
        logger.info(f"User {user.id} ({user.email}) has registered.")

    async def on_after_forgot_password(
        self,
        user: User,
        token: str,
        _request: Request | None = None,
    ):
        logger.info("User %s (%s) requested a password reset.", user.id, user.email)
        # Send password reset email
        import asyncio

        from app.services.email_service import send_password_reset_email

        task = asyncio.create_task(send_password_reset_email(user.email, token))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    async def on_after_request_verify(
        self, user: User, _token: str, _request: Request | None = None
    ):
        logger.info("Verification requested for user %s (%s).", user.id, user.email)
        # Implement actual email sending logic here.

    async def on_after_verify(self, user: User, _token: str, _request: Request | None = None):
        logger.info(f"User {user.id} ({user.email}) has been verified.")

    async def on_after_login(
        self,
        user: User,
        _request: Request | None = None,
        _response: Response | None = None,
    ) -> None:
        logger.info(f"User {user.id} ({user.email}) logged in successfully.")

    async def on_after_logout(
        self,
        user: User,
        _request: Request | None = None,
        _response: Response | None = None,
    ) -> None:
        logger.info(f"User {user.id} ({user.email}) logged out successfully.")

    async def validate_password(self, password: str, user: User | None = None) -> None:
        """
        Validate password strength.
        Requirements:
        - Minimum 8 characters
        - At least 1 uppercase letter
        - At least 1 lowercase letter
        - At least 1 number
        """
        import re

        from fastapi_users.exceptions import InvalidPasswordException

        if len(password) < 8:
            raise InvalidPasswordException(reason="Password must be at least 8 characters long.")
        if not re.search(r"[A-Z]", password):
            raise InvalidPasswordException(
                reason="Password must contain at least one uppercase letter."
            )
        if not re.search(r"[a-z]", password):
            raise InvalidPasswordException(
                reason="Password must contain at least one lowercase letter."
            )
        if not re.search(r"\d", password):
            raise InvalidPasswordException(reason="Password must contain at least one number.")
        # Check if password contains email (common weak pattern)
        if user and user.email and user.email.split("@")[0].lower() in password.lower():
            raise InvalidPasswordException(reason="Password should not contain your email address.")

    async def on_after_reset_password(self, user: User, _request: Request | None = None) -> None:
        """Update password_changed_at to invalidate old sessions."""
        from datetime import datetime

        user.password_changed_at = datetime.now(UTC)
        await self.user_db.update(user, {"password_changed_at": user.password_changed_at})
        logger.info(
            f"Password reset for user {user.id} ({user.email}). All previous sessions invalidated."
        )


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db_adapter_from_session),
):
    """Dependency to get the UserManager instance."""
    yield UserManager(user_db)


# --- JWT Strategies ---
def get_access_token_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=settings.SECRET_KEY,
        lifetime_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        algorithm=settings.ALGORITHM,
    )


def get_refresh_token_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=settings.JWT_REFRESH_SECRET_KEY,
        lifetime_seconds=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        algorithm=settings.ALGORITHM,
    )


# --- Authentication Transports ---
bearer_transport = BearerTransport(tokenUrl=f"{settings.API_V1_STR}/auth/login")
cookie_transport = CookieTransport(
    cookie_name=settings.REFRESH_TOKEN_COOKIE_NAME,
    cookie_max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    cookie_path=f"{settings.API_V1_STR}/auth",
    cookie_secure=settings.COOKIE_SECURE,
    cookie_httponly=True,
    cookie_samesite=settings.COOKIE_SAMESITE,
)

# --- Authentication Backend Instances ---
bearer_auth_backend = AuthenticationBackend(
    name="jwt-bearer-access",
    transport=bearer_transport,
    get_strategy=get_access_token_jwt_strategy,
)

cookie_auth_backend = AuthenticationBackend(
    name="jwt-cookie-refresh",
    transport=cookie_transport,
    get_strategy=get_refresh_token_jwt_strategy,
)


# --- FastAPIUsers Main Instance ---
fastapi_users_instance = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [
        bearer_auth_backend,
        cookie_auth_backend,
    ],
)

# --- Standard Current User Dependencies ---
current_active_user = fastapi_users_instance.current_user(active=True)
current_active_verified_user = fastapi_users_instance.current_user(active=True, verified=True)
current_active_superuser = fastapi_users_instance.current_user(active=True, superuser=True)


# --- Custom Role-Based Dependencies ---
async def get_current_active_admin_user(
    user: User = Depends(current_active_user),
) -> User:
    # Allow if superuser OR if role is admin
    if user.is_superuser:
        return user
    if user.role == "admin":
        return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="The user does not have admin privileges.",
    )


async def get_current_active_standard_user(user: User = Depends(current_active_user)) -> User:
    if user.role != "standard":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user is not a standard user.",
        )
    return user
