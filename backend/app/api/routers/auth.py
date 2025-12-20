# backend/app/api/routers/auth.py
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users.authentication import JWTStrategy
from jose import JWTError, jwt

from app.core.config import settings
from app.core.rate_limit import limiter  # Import limiter
from app.core.users import (
    UserManager,
    cookie_transport,
    fastapi_users_instance,
    get_access_token_jwt_strategy,  # Correct strategy for access tokens
    get_user_manager,
)
from app.db.models.user import User as UserModel  # Your DB model, aliased
from app.schemas.auth import Token
from app.schemas.user import UserCreate, UserRead  # UserCreate for register router

logger = logging.getLogger(__name__)

# --- Constants for manual refresh token handling ---
REFRESH_TOKEN_LIFETIME_SECONDS = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
REFRESH_TOKEN_AUDIENCE = "fastapi-users:auth-refresh"
ALGORITHM = settings.ALGORITHM
REFRESH_SECRET_KEY = settings.JWT_REFRESH_SECRET_KEY


# --- Helper for manual refresh token ---
def _create_manual_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(seconds=REFRESH_TOKEN_LIFETIME_SECONDS)
    to_encode.update(
        {
            "exp": expire,
            "aud": REFRESH_TOKEN_AUDIENCE,
            "jti": str(uuid.uuid4()),
            "type": "refresh",
        }
    )
    return jwt.encode(to_encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)


async def _decode_manual_refresh_token(token: str, user_manager: UserManager) -> UserModel | None:
    try:
        payload = jwt.decode(
            token, REFRESH_SECRET_KEY, algorithms=[ALGORITHM], audience=REFRESH_TOKEN_AUDIENCE
        )
        if payload.get("type") != "refresh":
            return None
        user_id_str = payload.get("sub")
        if not user_id_str:
            return None
        user = await user_manager.get(
            uuid.UUID(user_id_str)
        )  # user_manager.get returns the DB model type
        return user if user and user.is_active else None
    except (JWTError, ValueError):
        return None


auth_router = APIRouter(
    tags=["Auth - Authentication & Authorization"],
)


# --- Custom Login Endpoint ---
@auth_router.post("/login", response_model=Token, summary="Login for access and refresh tokens")
@limiter.limit("5/minute")
async def custom_login(
    response: Response,
    credentials: OAuth2PasswordRequestForm = Depends(),
    user_manager: UserManager = Depends(get_user_manager),
    # Use the specific JWTStrategy intended for access tokens
    access_token_strategy: JWTStrategy = Depends(get_access_token_jwt_strategy),  # <<< CORRECTED
    # If you created a separate refresh token strategy:
    # refresh_token_strategy: JWTStrategy = Depends(get_refresh_token_jwt_strategy),
    request: Request = None,  # Required for SlowAPI  # noqa: ARG001
):
    logger.debug(f"Login attempt for user: {credentials.username}")
    user = await user_manager.authenticate(credentials)  # Returns DB Model instance or None

    if user is None:
        logger.warning(f"Login failed: Invalid credentials for {credentials.username}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="LOGIN_BAD_CREDENTIALS")
    if not user.is_active:
        logger.warning(f"Login attempt for inactive user: {user.email} (ID: {user.id})")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="LOGIN_USER_INACTIVE")

    access_token = await access_token_strategy.write_token(user)  # Pass the user model instance

    refresh_token_data = {"sub": str(user.id)}
    refresh_token = _create_manual_refresh_token(data=refresh_token_data)

    response.set_cookie(
        key=cookie_transport.cookie_name,
        value=refresh_token,
        max_age=cookie_transport.cookie_max_age,
        path=cookie_transport.cookie_path,
        domain=cookie_transport.cookie_domain,
        secure=cookie_transport.cookie_secure,
        httponly=cookie_transport.cookie_httponly,
        samesite=cookie_transport.cookie_samesite,
    )

    logger.info(f"User logged in successfully: {user.email} (ID: {user.id})")
    return Token(access_token=access_token, token_type="bearer")


# --- Custom Refresh Token Endpoint ---
@auth_router.post("/refresh", response_model=Token, summary="Refresh access token")
async def custom_refresh(
    request: Request,
    response: Response,
    user_manager: UserManager = Depends(get_user_manager),
    access_token_strategy: JWTStrategy = Depends(get_access_token_jwt_strategy),  # <<< CORRECTED
    # refresh_token_strategy: JWTStrategy = Depends(get_refresh_token_jwt_strategy), # if separated
):
    refresh_token_from_cookie = request.cookies.get(cookie_transport.cookie_name)
    if not refresh_token_from_cookie:
        logger.debug("Refresh attempt without refresh token cookie.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="REFRESH_TOKEN_MISSING"
        )

    user = await _decode_manual_refresh_token(
        refresh_token_from_cookie, user_manager
    )  # Returns DB Model or None

    if not user:
        logger.warning("Refresh token invalid, expired, or user inactive. Deleting cookie.")
        response.delete_cookie(
            key=cookie_transport.cookie_name,
            path=cookie_transport.cookie_path,
            domain=cookie_transport.cookie_domain,
            secure=cookie_transport.cookie_secure,
            httponly=cookie_transport.cookie_httponly,
            samesite=cookie_transport.cookie_samesite,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="REFRESH_TOKEN_INVALID"
        )

    new_access_token = await access_token_strategy.write_token(user)  # Pass the user model instance

    new_refresh_token_data = {"sub": str(user.id)}
    new_refresh_token = _create_manual_refresh_token(data=new_refresh_token_data)

    response.set_cookie(
        key=cookie_transport.cookie_name,
        value=new_refresh_token,
        max_age=cookie_transport.cookie_max_age,
        path=cookie_transport.cookie_path,
        domain=cookie_transport.cookie_domain,
        secure=cookie_transport.cookie_secure,
        httponly=cookie_transport.cookie_httponly,
        samesite=cookie_transport.cookie_samesite,
    )

    logger.info(f"Token refreshed for user: {user.email} (ID: {user.id})")
    return Token(access_token=new_access_token, token_type="bearer")


# --- Custom Logout Endpoint ---
@auth_router.post("/logout", summary="Logout user", status_code=status.HTTP_200_OK)
async def custom_logout(response: Response):
    logger.info(f"Logout attempt. Deleting cookie: {cookie_transport.cookie_name}")
    response.delete_cookie(
        key=cookie_transport.cookie_name,
        path=cookie_transport.cookie_path,
        domain=cookie_transport.cookie_domain,
        secure=cookie_transport.cookie_secure,
        httponly=cookie_transport.cookie_httponly,
        samesite=cookie_transport.cookie_samesite,
    )
    return {"message": "LOGOUT_SUCCESSFUL"}


# --- FastAPI-Users Built-in Routes for Auth ---
if settings.OPEN_SIGNUP:
    auth_router.include_router(
        fastapi_users_instance.get_register_router(UserRead, UserCreate),
        tags=["Auth - Authentication & Authorization"],  # Updated tag for consistency
    )

# REMOVE the specific "get_forgot_password_router()" line if it's combined:
# auth_router.include_router(
# fastapi_users_instance.get_forgot_password_router(), # <<< REMOVE THIS LINE
# tags=["auth"],
# )
auth_router.include_router(
    fastapi_users_instance.get_reset_password_router(),
    tags=["Auth - Authentication & Authorization"],  # Updated tag for consistency
)
auth_router.include_router(
    fastapi_users_instance.get_verify_router(UserRead),
    tags=["Auth - Authentication & Authorization"],  # Updated tag for consistency
)
