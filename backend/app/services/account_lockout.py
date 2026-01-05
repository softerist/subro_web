# backend/app/services/account_lockout.py
"""
Account lockout service for brute force protection.

Implements progressive delays based on failed login attempts.
Uses exponential backoff instead of hard lockouts.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security_logger import security_log
from app.db.models.login_attempt import LoginAttempt

logger = logging.getLogger(__name__)

# Constants for progressive delay
MIN_DELAY_SECONDS = 1
MAX_DELAY_SECONDS = 30


class DelayStatus(NamedTuple):
    """Result of a delay check."""

    delay_seconds: float
    failed_attempts: int
    message: str | None


async def get_progressive_delay(
    db: AsyncSession,
    email: str,
) -> DelayStatus:
    """
    Calculate progressive delay based on recent failed attempts.

    Uses exponential backoff: 0, 1, 2, 4, 8, 16, 30 seconds (capped)

    Args:
        db: Database session
        email: The email being attempted

    Returns:
        DelayStatus with delay in seconds and attempt count
    """
    window_start = datetime.now(UTC) - timedelta(minutes=settings.LOGIN_ATTEMPT_WINDOW_MINUTES)

    # Count recent failed attempts for this email
    stmt = select(func.count()).where(
        LoginAttempt.email == email.lower(),
        LoginAttempt.success == False,  # noqa: E712
        LoginAttempt.attempted_at >= window_start,
    )
    result = await db.execute(stmt)
    failed_count = result.scalar() or 0

    if failed_count <= 1:
        # No delay for first attempt or first failure
        return DelayStatus(
            delay_seconds=0,
            failed_attempts=failed_count,
            message=None,
        )

    # Exponential backoff: 2^(n-2) seconds, capped at MAX_DELAY_SECONDS
    # 2 fails = 1s, 3 fails = 2s, 4 fails = 4s, 5 fails = 8s, etc.
    delay = min(MAX_DELAY_SECONDS, MIN_DELAY_SECONDS * (2 ** (failed_count - 2)))

    logger.info(f"Progressive delay for {email}: {delay}s after {failed_count} failed attempts")

    return DelayStatus(
        delay_seconds=delay,
        failed_attempts=failed_count,
        message=f"Please wait {int(delay)} second(s) before trying again." if delay > 0 else None,
    )


async def record_login_attempt(
    db: AsyncSession,
    email: str,
    ip_address: str,
    success: bool,
    user_agent: str | None = None,
) -> None:
    """
    Record a login attempt (successful or failed).

    Args:
        db: Database session
        email: The email that was attempted
        ip_address: Source IP address
        success: Whether the login succeeded
        user_agent: Optional user agent string
    """
    attempt = LoginAttempt(
        email=email.lower(),
        ip_address=ip_address,
        success=success,
        user_agent=user_agent[:512] if user_agent else None,
    )
    db.add(attempt)
    await db.commit()

    if success:
        logger.info(f"Successful login recorded for {email} from {ip_address}")
        security_log.successful_login(ip_address, email)
    else:
        logger.warning(f"Failed login attempt for {email} from {ip_address}")
        # Log to security log for fail2ban
        security_log.failed_login(ip_address, email, "BAD_CREDENTIALS")


async def clear_failed_attempts(
    db: AsyncSession,
    email: str,
) -> int:
    """
    Clear failed login attempts for an email after successful login.
    This resets the delay counter.

    Returns the number of cleared records.
    """
    stmt = delete(LoginAttempt).where(
        LoginAttempt.email == email.lower(),
        LoginAttempt.success == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    await db.commit()

    cleared = result.rowcount or 0
    if cleared > 0:
        logger.info(f"Cleared {cleared} failed login attempts for {email}")

    return cleared


async def cleanup_old_attempts(
    db: AsyncSession,
    older_than_days: int = 30,
) -> int:
    """
    Remove old login attempt records for database hygiene.
    Called periodically or via scheduled task.

    Returns the number of deleted records.
    """
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)

    stmt = delete(LoginAttempt).where(LoginAttempt.attempted_at < cutoff)
    result = await db.execute(stmt)
    await db.commit()

    deleted = result.rowcount or 0
    if deleted > 0:
        logger.info(f"Cleaned up {deleted} old login attempt records")

    return deleted
