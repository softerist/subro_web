# backend/app/api/routers/auth.py
import uuid
import logging
from typing import Optional
# Add necessary imports for manual JWT handling
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError

from fastapi import Request, APIRouter, Depends, Response, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users.authentication import JWTStrategy
from fastapi_users.exceptions import UserNotExists, InvalidPasswordException

from app.db.models.user import User
from app.core.security import (
    auth_backend,
    cookie_transport,
    fastapi_users,
    get_jwt_strategy,
    get_user_manager,
    UserManager
)
from app.schemas.user import UserRead, UserCreate, UserUpdate
from app.core.config import settings

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/auth", tags=["Auth"])
users_router = APIRouter(prefix="/users", tags=["Users"])

# --- Constants for manual refresh token handling ---
# Ensure REFRESH_TOKEN_EXPIRE_DAYS is defined in settings
REFRESH_TOKEN_LIFETIME = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
REFRESH_TOKEN_AUDIENCE = "fastapi-users:refresh" # Standard audience
ALGORITHM = settings.ALGORITHM # Use same algorithm as access token
SECRET_KEY = settings.SECRET_KEY # Use same secret key

# --- Helper functions for manual refresh token handling ---
def create_refresh_token(
    data: dict, expires_delta: timedelta = REFRESH_TOKEN_LIFETIME
) -> str:
    """Creates a JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    # Add 'jti' (JWT ID) claim for uniqueness
    to_encode.update({
        "exp": expire,
        "aud": REFRESH_TOKEN_AUDIENCE,
        "jti": str(uuid.uuid4()) # <--- ADD THIS LINE
    })
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def decode_refresh_token(token: str, user_manager: UserManager) -> Optional[User]:
    """Decodes refresh token, validates audience, gets user."""
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=REFRESH_TOKEN_AUDIENCE # Validate audience
        )
        # Check standard 'sub' claim for user ID
        user_id_str = payload.get("sub")
        if user_id_str is None:
            logger.warning("Refresh token missing 'sub' claim.")
            return None

        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
             logger.warning(f"Invalid UUID in refresh token 'sub' claim: {user_id_str}")
             return None

        # Fetch the user from the database
        user = await user_manager.get(user_id)
        return user

    except JWTError as e:
        logger.warning(f"Invalid refresh token: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error decoding refresh token or fetching user: {e}", exc_info=True)
        return None


# --- Custom Login Endpoint (Manual Refresh Token, Reverted Cookie Handling) ---
@auth_router.post("/login")
async def custom_login(
    response: Response,
    credentials: OAuth2PasswordRequestForm = Depends(),
    user_manager: UserManager = Depends(get_user_manager),
    strategy: JWTStrategy = Depends(get_jwt_strategy)
):
    """
    Custom login endpoint: authenticates, checks active status,
    generates tokens, sets cookie, returns access token.
    (Handles None return from authenticate for older fastapi-users versions).
    """
    authenticated_user: Optional[User] = None

    try:
        logger.debug(f"Attempting authentication for user: {credentials.username}")
        authenticated_user = await user_manager.authenticate(credentials)
        logger.debug(f"Authentication result for {credentials.username}: {type(authenticated_user)}")

    except Exception as e:
        logger.error(f"Unexpected exception during user authentication call for {credentials.username}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_SERVER_ERROR",
        )

    # Check the result of authentication
    if authenticated_user is None:
        # Failure case (UserNotFound or InvalidPassword)
        logger.debug(f"Login failed: Invalid credentials or user not found - {credentials.username}")
        # --- REMOVE the get_by_email check ---
        # existing_user = await user_manager.get_by_email(credentials.username) # REMOVE/COMMENT OUT
        # if existing_user is None:
        #      logger.debug(f"Login failed: User not found - {credentials.username}")
        # else:
        #      logger.debug(f"Login failed: Invalid credentials or inactive user - {credentials.username}")
        # --- End of removal ---
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LOGIN_BAD_CREDENTIALS", # Keep generic
        )

    user = authenticated_user

    if not user.is_active:
        logger.warning(f"Login attempt for inactive user: {credentials.username} (ID: {user.id})")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LOGIN_USER_INACTIVE",
        )

    # --- Token Generation (Remains the same) ---
    try:
        access_token = await strategy.write_token(user)
        refresh_token_data = {"sub": str(user.id)}
        refresh_token = create_refresh_token(data=refresh_token_data)
    except Exception as e:
        logger.error(f"Error writing tokens for user {user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TOKEN_GENERATION_ERROR",
        )

    # --- Set Cookie (Remains the same) ---
    response.set_cookie(
        key=cookie_transport.cookie_name, value=refresh_token,
        max_age=cookie_transport.cookie_max_age, path=cookie_transport.cookie_path,
        domain=cookie_transport.cookie_domain, secure=cookie_transport.cookie_secure,
        httponly=cookie_transport.cookie_httponly, samesite=cookie_transport.cookie_samesite,
    )

    logger.info(f"User logged in successfully: {credentials.username} (ID: {user.id})")
    return {"access_token": access_token, "token_type": "bearer"}


# --- Custom Refresh Token Endpoint (Manual Refresh Token Handling, Reverted Cookie Handling) ---
@auth_router.post("/refresh")
async def refresh_jwt(
    response: Response,
    request: Request,
    user_manager: UserManager = Depends(get_user_manager),
    strategy: JWTStrategy = Depends(get_jwt_strategy), # Still use for new access token
):
    """ Refreshes token using cookie, generates new tokens, sets new cookie. """
    # Get cookie MANUALLY (reverting helper usage)
    refresh_token = request.cookies.get(cookie_transport.cookie_name)
    if not refresh_token:
        logger.debug("Refresh attempt without refresh token cookie.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token cookie"
        )

    # Decode refresh token MANUALLY and get user
    user = await decode_refresh_token(refresh_token, user_manager)

    if not user or not user.is_active:
        detail = "Invalid or expired refresh token"
        logger.warning(f"{detail} or inactive user attempt: user_id={user.id if user else 'None'}")
        # Delete cookie MANUALLY (reverting helper usage)
        response.delete_cookie(
            key=cookie_transport.cookie_name, path=cookie_transport.cookie_path,
            domain=cookie_transport.cookie_domain, secure=cookie_transport.cookie_secure,
            httponly=cookie_transport.cookie_httponly, samesite=cookie_transport.cookie_samesite,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    try:
        # Generate *new* access token using standard strategy
        new_access_token = await strategy.write_token(user)
        # Generate *new* refresh token MANUALLY
        refresh_token_data = {"sub": str(user.id)}
        new_refresh_token = create_refresh_token(data=refresh_token_data)
    except Exception as e:
        logger.error(f"Error generating new tokens during refresh for user {user.id}: {e}", exc_info=True)
        # Delete cookie MANUALLY on error
        response.delete_cookie(
            key=cookie_transport.cookie_name, path=cookie_transport.cookie_path,
            domain=cookie_transport.cookie_domain, secure=cookie_transport.cookie_secure,
            httponly=cookie_transport.cookie_httponly, samesite=cookie_transport.cookie_samesite,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TOKEN_GENERATION_ERROR",
        )


    # Set the *new* cookie MANUALLY (reverting helper usage)
    response.set_cookie(
        key=cookie_transport.cookie_name, value=new_refresh_token,
        max_age=cookie_transport.cookie_max_age, path=cookie_transport.cookie_path,
        domain=cookie_transport.cookie_domain, secure=cookie_transport.cookie_secure,
        httponly=cookie_transport.cookie_httponly, samesite=cookie_transport.cookie_samesite,
    )

    logger.info(f"Token refreshed for user: {user.email} (ID: {user.id})")
    return {"access_token": new_access_token, "token_type": "bearer"}


# --- Custom Logout Endpoint (Reverted Cookie Handling) ---
@auth_router.post("/logout")
async def custom_logout(response: Response):
    """ Logs out the user by deleting the refresh token cookie. """
    # Delete cookie MANUALLY (reverting helper usage)
    response.delete_cookie(
        key=cookie_transport.cookie_name,
        path=cookie_transport.cookie_path,
        domain=cookie_transport.cookie_domain,
        secure=cookie_transport.cookie_secure,
        httponly=cookie_transport.cookie_httponly,
        samesite=cookie_transport.cookie_samesite,
    )
    logger.info("User logged out.")
    return {"status": "logged out"}

# --- Included Routers (Keep as is) ---
# ... (register, reset password, users routers) ...
if settings.OPEN_SIGNUP:
    register_router = fastapi_users.get_register_router(UserRead, UserCreate)
    auth_router.include_router(register_router)
else:
    print("INFO:     User self-registration is disabled (OPEN_SIGNUP=False)")

auth_router.include_router(fastapi_users.get_reset_password_router())

users_router.include_router(fastapi_users.get_users_router(UserRead, UserUpdate, requires_verification=False))
