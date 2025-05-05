import uuid
from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    CookieTransport,
    JWTStrategy,
)
from fastapi_users.password import PasswordHelper
from typing import Optional

from app.core.config import settings
from app.db.models.user import User
from app.db.session import get_user_db
from app.schemas.user import UserRead, UserCreate, UserUpdate # Keep all schema imports

# --- Password Hashing ---
password_helper = PasswordHelper()

# --- User Manager ---
class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.SECRET_KEY
    verification_token_secret = settings.SECRET_KEY

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        print(f"User {user.id} has registered.")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        print(f"User {user.id} has requested a password reset. Token: {token}")

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        print(f"Verification requested for user {user.id}. Token: {token}")

    # <<< REMOVE THE validate_password METHOD OVERRIDE ENTIRELY >>>
    # async def validate_password(self, password: str, user: User) -> bool:
    #     # This method should NOT be overridden for standard password verification
    #     # BaseUserManager.authenticate handles this internally using password_helper
    #     # return password_helper.verify(password, user.hashed_password) # <-- Incorrect
    #     pass # Or just remove the method definition

    # Keep the hash_password override as it IS required
    async def hash_password(self, password: str) -> str:
        return password_helper.hash(password)

async def get_user_manager(user_db = Depends(get_user_db)):
    yield UserManager(user_db, password_helper=password_helper) # Pass helper here

# --- JWT Strategy ---
# --- JWT Strategy ---
def get_jwt_strategy() -> JWTStrategy:
    """Returns the JWT strategy configured with secrets and lifetimes."""
    refresh_lifetime_seconds = cookie_transport.cookie_max_age # Use cookie max age
    if refresh_lifetime_seconds is None:
        # Provide a default if cookie_max_age is None (shouldn't happen with current setup)
        refresh_lifetime_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60

    return JWTStrategy(
        secret=settings.SECRET_KEY,
        lifetime_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        #refresh_lifetime_seconds=refresh_lifetime_seconds, # <--- ADD THIS
        algorithm=settings.ALGORITHM,
    )

# --- Authentication Transports ---
bearer_transport = BearerTransport(tokenUrl="/api/auth/login")
cookie_transport = CookieTransport(
    cookie_name="subRefreshToken",
    cookie_max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    cookie_path="/api/auth",
    cookie_secure=False, # TODO: Set to True in production
    cookie_httponly=True,
    cookie_samesite="lax",
 )

# --- Authentication Backend Instance ---
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# --- FastAPIUsers Main Instance ---
fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend],
)
# --- Reusable Dependencies ---
current_active_user = fastapi_users.current_user(active=True)
current_active_superuser = fastapi_users.current_user(active=True, superuser=True)
current_user_optional = fastapi_users.current_user(optional=True)
