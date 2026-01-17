import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.request_context import set_actor
from app.core.security import fastapi_users
from app.db.models.api_key import ApiKey
from app.db.models.user import User
from app.db.session import get_async_session

logger = logging.getLogger(__name__)

# Define the API Key header scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Helper specific to standard users logic
current_user_jwt = fastapi_users.current_user(active=True)


API_KEY_PREFIX_LEN = 8


def generate_api_key() -> str:
    """Generate a secure, random API key."""
    # 32 bytes of randomness results in a ~43 character URL-safe string
    return secrets.token_urlsafe(32)


def get_api_key_prefix(raw_key: str) -> str:
    return raw_key[:API_KEY_PREFIX_LEN]


def get_api_key_last4(raw_key: str) -> str:
    return raw_key[-4:] if len(raw_key) >= 4 else raw_key


def hash_api_key(raw_key: str) -> str:
    if not settings.API_KEY_PEPPER:
        raise RuntimeError("API_KEY_PEPPER is not configured.")
    return hmac.new(
        settings.API_KEY_PEPPER.encode(),
        raw_key.encode(),
        hashlib.sha256,
    ).hexdigest()


async def _migrate_legacy_api_key(
    db: AsyncSession,
    user: User,
    api_key: str,
    hashed_key: str,
    now: datetime,
) -> User | None:
    api_key_record = ApiKey(
        user_id=user.id,
        name="Legacy",
        scopes=None,
        prefix=get_api_key_prefix(api_key),
        last4=get_api_key_last4(api_key),
        hashed_key=hashed_key,
        created_at=now,
        last_used_at=now,
        use_count=1,
    )
    user.api_key = None
    db.add(api_key_record)
    db.add(user)
    try:
        await db.commit()
        return user
    except IntegrityError:
        await db.rollback()
        result = await db.execute(
            select(ApiKey).where(ApiKey.hashed_key == hashed_key).options(selectinload(ApiKey.user))
        )
        existing = result.scalars().first()
        if existing:
            return existing.user
        logger.warning(  # nosemgrep
            "Legacy API key migration failed for user_id=%s; duplicate key but no record found.",
            user.id,
        )
        return None


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

    if not settings.API_KEY_PEPPER:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key authentication is not configured.",
        )

    prefix = get_api_key_prefix(api_key)
    now = datetime.now(UTC)

    query = (
        select(ApiKey)
        .where(
            ApiKey.prefix == prefix,
            ApiKey.revoked_at.is_(None),
            (ApiKey.expires_at.is_(None) | (ApiKey.expires_at > now)),
        )
        .options(selectinload(ApiKey.user))
    )
    hashed = hash_api_key(api_key)
    result = await db.execute(query)
    candidates = result.scalars().all()
    for candidate in candidates:
        if hmac.compare_digest(candidate.hashed_key, hashed):
            candidate.last_used_at = now
            candidate.use_count = (candidate.use_count or 0) + 1
            db.add(candidate)
            await db.commit()
            return candidate.user

    legacy_result = await db.execute(select(User).where(User.api_key == api_key))
    legacy_user = legacy_result.scalars().first()
    if legacy_user:
        migrated_user = await _migrate_legacy_api_key(db, legacy_user, api_key, hashed, now)
        if migrated_user:
            return migrated_user

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
        user = await get_user_by_api_key(api_key, db)
        if user:
            set_actor(user_id=str(user.id), email=user.email, actor_type="api_key")
            return user

        # Audit Log: Suspicious Token (Invalid API Key)
        from app.services import audit_service

        key_prefix = get_api_key_prefix(api_key)
        await audit_service.log_event(
            db,
            category="security",
            action="security.suspicious_token",
            severity="critical",
            success=False,
            details={"type": "invalid_api_key", "prefix": key_prefix},
        )
        await db.commit()

        # If API Key provided but invalid -> 401
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )

    # 2. Check JWT (Optional was used, so it's None if not found/valid)
    if user_jwt:
        set_actor(user_id=str(user_jwt.id), email=user_jwt.email, actor_type="user")
        return user_jwt

    # 3. Neither found
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated (Missing API Key or valid Session)",
    )
