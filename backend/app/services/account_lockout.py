# backend/app/services/account_lockout.py
"""
Account lockout service for brute force protection.

Implements:
- Progressive delays (exponential backoff)
- Hard lockout (5 failed attempts -> 15 min wait)
- Account suspension (10 failed attempts -> permanent lockout)
Uses the security columns in the User model.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from app.core.security_logger import security_log
from app.db.models.login_attempt import LoginAttempt
from app.db.models.user import User

logger = logging.getLogger(__name__)

# Constants for lockout
MIN_DELAY_SECONDS = 1
MAX_DELAY_SECONDS = 30
LOCKOUT_THRESHOLD_1 = 5  # 15 min lockout
LOCKOUT_THRESHOLD_2 = 10  # Suspended
LOCKOUT_DURATION_MINS = 15


class DelayStatus(NamedTuple):
    """Result of a delay check."""

    delay_seconds: float
    failed_attempts: int
    is_locked: bool = False
    is_suspended: bool = False
    message: str | None = None


async def get_progressive_delay(
    db: AsyncSession,
    email: str,
) -> DelayStatus:
    """
    Calculate progressive delay and check lockout status.

    Checks User model for:
    1. Account suspension (status='suspended')
    2. Active lockout (locked_until > now)
    3. Progressive delay (based on failed_login_count)
    """
    email = email.lower()
    stmt = select(User).options(noload(User.jobs), noload(User.api_keys)).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        # For non-existent users, we still simulate a small delay to prevent enumeration
        # but don't track state
        return DelayStatus(delay_seconds=0, failed_attempts=0)

    # 1. Check Suspension
    if user.status == "suspended" or user.status == "banned":
        return DelayStatus(
            delay_seconds=0,
            failed_attempts=user.failed_login_count,
            is_suspended=True,
            message="Account is suspended. Please contact support.",
        )

    # 2. Check Active Lockout
    now = datetime.now(UTC)
    if user.locked_until and user.locked_until > now:
        remaining = (user.locked_until - now).total_seconds()
        return DelayStatus(
            delay_seconds=0,
            failed_attempts=user.failed_login_count,
            is_locked=True,
            message=f"Account is locked. Please try again in {int(remaining // 60) + 1} minute(s).",
        )

    # 3. Progressive delay (starts after 2nd failure)
    # 2 fails = 1s, 3 fails = 2s, 4 fails = 4s...
    if user.failed_login_count < 2:
        return DelayStatus(delay_seconds=0, failed_attempts=user.failed_login_count)

    delay = min(MAX_DELAY_SECONDS, MIN_DELAY_SECONDS * (2 ** (user.failed_login_count - 2)))

    return DelayStatus(
        delay_seconds=delay,
        failed_attempts=user.failed_login_count,
        message=f"Please wait {int(delay)} second(s) before trying again.",
    )


async def record_login_attempt(
    db: AsyncSession,
    email: str,
    ip_address: str,
    success: bool,
    user_agent: str | None = None,
) -> None:
    """
    Record an attempt and update User security status.
    """
    email = email.lower()
    now = datetime.now(UTC)

    # 1. Log the attempt for historical audit
    attempt = LoginAttempt(
        email=email,
        ip_address=ip_address,
        success=success,
        user_agent=user_agent[:512] if user_agent else None,
    )
    db.add(attempt)

    # 2. Update User state if user exists
    stmt = select(User).options(noload(User.jobs), noload(User.api_keys)).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        await db.commit()
        return

    if success:
        # Reset state on success
        user.failed_login_count = 0
        user.locked_until = None
        user.first_failed_at = None
        security_log.successful_login(ip_address, email)
    else:
        # Increment failure count
        user.failed_login_count += 1
        if not user.first_failed_at:
            user.first_failed_at = now

        # Check thresholds
        if user.failed_login_count >= LOCKOUT_THRESHOLD_2:
            user.status = "suspended"
            logger.critical(f"ACCOUNT SUSPENDED: {email} after {user.failed_login_count} failures.")
            security_log.failed_login(ip_address, email, "ACCOUNT_SUSPENDED")
        elif user.failed_login_count >= LOCKOUT_THRESHOLD_1:
            user.locked_until = now + timedelta(minutes=LOCKOUT_DURATION_MINS)
            logger.warning(f"ACCOUNT LOCKED: {email} for {LOCKOUT_DURATION_MINS}m.")
            security_log.failed_login(ip_address, email, "ACCOUNT_LOCKED")
        else:
            security_log.failed_login(ip_address, email, "BAD_CREDENTIALS")

    await db.commit()


async def clear_failed_attempts(
    db: AsyncSession,
    email: str,
) -> None:
    """Reset failed login count for an email."""
    email = email.lower()
    stmt = (
        update(User)
        .where(User.email == email)
        .values(failed_login_count=0, locked_until=None, first_failed_at=None)
    )
    await db.execute(stmt)
    await db.commit()
