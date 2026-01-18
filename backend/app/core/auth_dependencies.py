# backend/app/core/auth_dependencies.py
"""
Authentication dependencies for step-up authentication.

This module provides dependencies for enforcing recent authentication
for sensitive operations like passkey management.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt.exceptions import InvalidTokenError

from app.core.config import settings
from app.core.users import current_active_user
from app.db.models.user import User

# Maximum age for step-up authentication (5 minutes)
MAX_AUTH_AGE_SECONDS = 300


def get_auth_time_from_token(request: Request) -> float | None:
    """
    Extract auth_time from the JWT token in the Authorization header.

    Returns:
        Timestamp of when user last authenticated interactively, or None if not found
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header.replace("Bearer ", "")

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={
                "verify_exp": False,
                "verify_aud": False,
            },  # Don't verify expiry or aud, just read claims
        )
        # auth_time is set when user performs interactive login
        auth_time = payload.get("auth_time")
        if isinstance(auth_time, (int, float)):
            return float(auth_time)
        return None
    except InvalidTokenError:
        return None


def require_recent_auth(
    max_age: int = MAX_AUTH_AGE_SECONDS,
) -> Callable[[User, Request], Awaitable[User]]:
    """
    Dependency factory for step-up authentication.

    Enforces that the user authenticated within the last `max_age` seconds.
    Raises 401 with REAUTH_REQUIRED if authentication is too old.

    Args:
        max_age: Maximum age in seconds since last interactive authentication

    Returns:
        Dependency function that validates auth recency

    Example:
        @router.post("/sensitive-endpoint")
        async def sensitive_op(
            user: User = Depends(current_active_user),
            _: None = Depends(require_recent_auth(300))
        ):
            # This code only runs if auth is < 5 minutes old
            ...
    """

    async def dependency(
        user: Annotated[User, Depends(current_active_user)], request: Request
    ) -> User:
        auth_time = get_auth_time_from_token(request)

        if auth_time is None:
            # No auth_time in token - this is a legacy token or misconfigured
            # For safety, require reauth
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "REAUTH_REQUIRED",
                    "message": "Please verify your identity to perform this action",
                    "reason": "auth_time_missing",
                },
            )

        now = datetime.now(UTC)
        auth_datetime = datetime.fromtimestamp(auth_time, tz=UTC)
        age_seconds = (now - auth_datetime).total_seconds()

        if age_seconds > max_age:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "REAUTH_REQUIRED",
                    "message": "Please verify your identity to perform this action",
                    "auth_age_seconds": int(age_seconds),
                    "max_age_seconds": max_age,
                },
            )

        return user

    return dependency
