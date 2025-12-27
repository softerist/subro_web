import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import fastapi_users
from app.db.models.user import User
from app.db.session import get_async_session

# Define the API Key header scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Helper specific to standard users logic
current_user_jwt = fastapi_users.current_user(active=True)


def generate_api_key() -> str:
    """Generate a secure, random API key."""
    # 32 bytes of randomness results in a ~43 character URL-safe string
    return secrets.token_urlsafe(32)


async def get_user_by_api_key(
    api_key: Annotated[str | None, Security(api_key_header)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> User | None:
    """
    Authenticate a user via API Key.
    Returns the user if key is valid, None otherwise.
    """
    if not api_key:
        return None

    # Query user by API key
    # Note: In a production system with high traffic, you might want to hash this key
    # or cache the result. For this personal app, direct lookup is acceptable.
    query = select(User).where(User.api_key == api_key)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if user:
        return user

    # If key provided but invalid, we could return None to let it fall back
    # or raise 401. Let's return None to allow the composite dependency to decide.
    return None


async def get_current_user_with_api_key(
    api_key_user: Annotated[User | None, Depends(get_user_by_api_key)],
    # We use Depends(current_active_user) manually if api_key fails
) -> User | None:
    """
    Dependency that returns a user if authenticated via API Key.
    Used for composition.
    """
    return api_key_user


async def get_current_user_with_api_key_or_jwt(
    api_key: Annotated[str | None, Security(api_key_header)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    # We accept nullable token to avoid auto-error
    # But current_user_jwt raises 401 if missing.
    # So we need to use 'optional' user for JWT, and then check.
    user_jwt: Annotated[
        User | None, Depends(fastapi_users.current_user(active=True, optional=True))
    ],
) -> User:
    # 1. Check API Key
    if api_key:
        query = select(User).where(User.api_key == api_key)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        if user:
            return user
        # If API Key provided but invalid -> 401
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )

    # 2. Check JWT (Optional was used, so it's None if not found/valid)
    if user_jwt:
        return user_jwt

    # 3. Neither found
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated (Missing API Key or valid Session)",
    )
