# backend/app/api/routers/auth.py
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users.authentication import JWTStrategy  # For type hinting strategy
from jose import JWTError, jwt

from app.core.config import settings
from app.core.users import (  # Updated import path
    UserManager,
    fastapi_users_instance,  # Renamed from 'fastapi_users' for clarity
    get_jwt_strategy,
    get_user_manager,
    refresh_cookie_transport,  # Import the specific refresh_cookie_transport
)
from app.db.models.user import User  # For type hinting User
from app.schemas.user import UserCreate, UserRead  # UserUpdate removed as it's not used here

logger = logging.getLogger(__name__)

auth_router = APIRouter(
    prefix="/auth",
    tags=["Auth - Authentication & Authorization"],  # More descriptive tag
)

# --- Constants for manual refresh token handling ---
REFRESH_TOKEN_LIFETIME = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
REFRESH_TOKEN_AUDIENCE = "fastapi-users:auth-refresh"  # More specific audience
ALGORITHM = settings.ALGORITHM
# SECRET_KEY is used by get_jwt_strategy for access tokens
REFRESH_SECRET_KEY = settings.JWT_REFRESH_SECRET_KEY


# --- Helper functions for manual refresh token handling ---
def create_refresh_token(data: dict, expires_delta: timedelta = REFRESH_TOKEN_LIFETIME) -> str:
    """Creates a JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.now(UTC) + expires_delta
    to_encode.update(
        {
            "exp": expire,
            "aud": REFRESH_TOKEN_AUDIENCE,  # Use the defined audience
            "jti": str(uuid.uuid4()),
            "type": "refresh",  # Optional: add a type claim
        }
    )
    encoded_jwt = jwt.encode(to_encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def decode_refresh_token(token: str, user_manager: UserManager) -> User | None:
    """Decodes refresh token, validates audience and type, gets user."""
    try:
        payload = jwt.decode(
            token,
            REFRESH_SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=REFRESH_TOKEN_AUDIENCE,  # Validate against the defined audience
        )

        # Optional: Validate token type if set during creation
        if payload.get("type") != "refresh":
            logger.warning("Invalid token type in refresh token.")
            return None

        user_id_str = payload.get("sub")
        if user_id_str is None:
            logger.warning("Refresh token missing 'sub' claim.")
            return None

        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            logger.warning(f"Invalid UUID in refresh token 'sub' claim: {user_id_str}")
            return None

        user = await user_manager.get(user_id)
        if user and user.is_active:  # Also ensure user is still active
            return user
        elif user:
            logger.warning(f"Refresh token decoded for inactive user_id: {user_id}")
        else:
            logger.warning(f"User not found for refresh token sub: {user_id}")
        return None  # Return None if user not found or not active

    except JWTError as e:
        logger.warning(f"Invalid refresh token (JWTError): {e}")
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error decoding refresh token or fetching user: {e}", exc_info=True
        )
        return None


# --- Custom Login Endpoint ---
@auth_router.post("/login", summary="Login for access and refresh tokens")
async def custom_login(
    response: Response,
    credentials: OAuth2PasswordRequestForm = Depends(),
    user_manager: UserManager = Depends(get_user_manager),
    access_token_strategy: JWTStrategy = Depends(get_jwt_strategy),  # More specific name
):
    """
    Authenticates a user, generates an access token (JWT) and a refresh token (JWT).
    The refresh token is set as an HttpOnly cookie.
    The access token is returned in the response body.
    """
    logger.debug(f"Login attempt for user: {credentials.username}")
    user = await user_manager.authenticate(credentials)

    if not user:  # Handles both user not found and invalid password
        logger.warning(f"Login failed: Invalid credentials for {credentials.username}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LOGIN_BAD_CREDENTIALS",
        )

    if not user.is_active:
        logger.warning(f"Login attempt for inactive user: {user.email} (ID: {user.id})")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LOGIN_USER_INACTIVE",
        )

    try:
        access_token = await access_token_strategy.write_token(user)
        refresh_token_data = {"sub": str(user.id)}  # 'sub' is standard for subject (user ID)
        refresh_token = create_refresh_token(data=refresh_token_data)
    except Exception as e:
        logger.error(f"Error generating tokens for user {user.id}: {e}", exc_info=True)

    # Use parameters from the imported refresh_cookie_transport
    response.set_cookie(
        key=refresh_cookie_transport.cookie_name,
        value=refresh_token,
        max_age=refresh_cookie_transport.cookie_max_age,
        path=refresh_cookie_transport.cookie_path,
        domain=refresh_cookie_transport.cookie_domain,
        secure=refresh_cookie_transport.cookie_secure,
        httponly=refresh_cookie_transport.cookie_httponly,
        samesite=refresh_cookie_transport.cookie_samesite,
    )

    logger.info(f"User logged in successfully: {user.email} (ID: {user.id})")
    return {"access_token": access_token, "token_type": "bearer"}


# --- Custom Refresh Token Endpoint ---
@auth_router.post("/refresh", summary="Refresh access token using refresh token cookie")
async def refresh_jwt(
    response: Response,
    request: Request,
    user_manager: UserManager = Depends(get_user_manager),
    access_token_strategy: JWTStrategy = Depends(get_jwt_strategy),  # For new access token
):
    """
    Refreshes an access token using the refresh token stored in an HttpOnly cookie.
    Returns a new access token and sets a new refresh token cookie.
    """
    refresh_token = request.cookies.get(refresh_cookie_transport.cookie_name)
    if not refresh_token:
        logger.debug("Refresh attempt without refresh token cookie.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="REFRESH_TOKEN_MISSING"
        )

    user = await decode_refresh_token(refresh_token, user_manager)

    if not user:  # decode_refresh_token now also checks for user.is_active
        detail = "REFRESH_TOKEN_INVALID_OR_EXPIRED"
        logger.warning(f"{detail} or inactive user. Deleting cookie.")
        response.delete_cookie(
            key=refresh_cookie_transport.cookie_name,
            path=refresh_cookie_transport.cookie_path,
            domain=refresh_cookie_transport.cookie_domain,
            secure=refresh_cookie_transport.cookie_secure,
            httponly=refresh_cookie_transport.cookie_httponly,
            samesite=refresh_cookie_transport.cookie_samesite,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    try:
        new_access_token = await access_token_strategy.write_token(user)
        refresh_token_data = {"sub": str(user.id)}
        new_refresh_token = create_refresh_token(data=refresh_token_data)
    except Exception as e:
        logger.error(
            f"Error generating new tokens during refresh for user {user.id}: {e}", exc_info=True
        )
        response.delete_cookie(  # Ensure cookie is deleted on error
            key=refresh_cookie_transport.cookie_name,
            path=refresh_cookie_transport.cookie_path,
            domain=refresh_cookie_transport.cookie_domain,
            secure=refresh_cookie_transport.cookie_secure,
            httponly=refresh_cookie_transport.cookie_httponly,
            samesite=refresh_cookie_transport.cookie_samesite,
        )
        raise HTTPException from e(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TOKEN_GENERATION_ERROR",
        )

    response.set_cookie(
        key=refresh_cookie_transport.cookie_name,
        value=new_refresh_token,
        max_age=refresh_cookie_transport.cookie_max_age,
        path=refresh_cookie_transport.cookie_path,
        domain=refresh_cookie_transport.cookie_domain,
        secure=refresh_cookie_transport.cookie_secure,
        httponly=refresh_cookie_transport.cookie_httponly,
        samesite=refresh_cookie_transport.cookie_samesite,
    )

    logger.info(f"Token refreshed for user: {user.email} (ID: {user.id})")
    return {"access_token": new_access_token, "token_type": "bearer"}


# --- Custom Logout Endpoint ---
@auth_router.post("/logout", summary="Logout user by deleting refresh token cookie")
async def custom_logout(response: Response):
    """Logs out the user by deleting the refresh token cookie."""
    logger.info(f"Logout attempt. Deleting cookie: {refresh_cookie_transport.cookie_name}")
    response.delete_cookie(
        key=refresh_cookie_transport.cookie_name,
        path=refresh_cookie_transport.cookie_path,
        domain=refresh_cookie_transport.cookie_domain,
        secure=refresh_cookie_transport.cookie_secure,
        httponly=refresh_cookie_transport.cookie_httponly,
        samesite=refresh_cookie_transport.cookie_samesite,
    )
    return {"message": "LOGOUT_SUCCESSFUL"}


# --- FastAPI-Users Built-in Routes for Auth ---
# Register Router (conditionally based on settings)
if settings.OPEN_SIGNUP:
    # Uses UserRead for response, UserCreate for request body
    register_router = fastapi_users_instance.get_register_router(UserRead, UserCreate)
    auth_router.include_router(
        register_router,
        # prefix="/register", # No, fastapi-users router already has /register
        tags=["Auth - Registration"],  # Specific tag
    )
    logger.info("User self-registration is ENABLED.")
else:
    logger.info("User self-registration is DISABLED (OPEN_SIGNUP=False).")

# Reset Password Router
auth_router.include_router(
    fastapi_users_instance.get_reset_password_router(),
    # No prefix, already part of fastapi-users router
    tags=["Auth - Password Management"],  # Specific tag
)

# Verify Email Routers (if you implement email verification)
# if settings.EMAIL_VERIFICATION_ENABLED: # Example setting
#     auth_router.include_router(
#         fastapi_users_instance.get_verify_router(UserRead),
#         tags=["Auth - Email Verification"]
#     )
#     logger.info("Email verification routes ENABLED.")


# Note: The standard user management routes (GET /users/me, PATCH /users/me, etc.)
# are now correctly handled by `app.api.routers.users.py` and should NOT be included here.
