from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models.user import User
from app.services import account_lockout


@pytest.mark.asyncio
async def test_lockout_threshold_15min() -> None:
    db = AsyncMock()
    db.add = MagicMock()  # sync
    db.commit = AsyncMock()  # async

    user = User(email="test@example.com", failed_login_count=4, status="active")

    mock_executor = MagicMock()  # sync results
    mock_executor.scalar_one_or_none.return_value = user
    db.execute.return_value = mock_executor

    # 5th failure should trigger 15 min lockout
    await account_lockout.record_login_attempt(db, "test@example.com", "1.2.3.4", success=False)

    assert user.failed_login_count == 5
    assert user.locked_until is not None
    assert user.status == "active"


@pytest.mark.asyncio
async def test_lockout_threshold_suspension() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    user = User(email="test@example.com", failed_login_count=9, status="active")

    mock_executor = MagicMock()
    mock_executor.scalar_one_or_none.return_value = user
    db.execute.return_value = mock_executor

    # 10th failure should trigger suspension
    await account_lockout.record_login_attempt(db, "test@example.com", "1.2.3.4", success=False)

    assert user.failed_login_count == 10
    assert user.status == "suspended"


@pytest.mark.asyncio
async def test_reset_on_success() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    user = User(
        email="test@example.com",
        failed_login_count=5,
        locked_until=datetime.now(UTC),
        status="active",
    )

    mock_executor = MagicMock()
    mock_executor.scalar_one_or_none.return_value = user
    db.execute.return_value = mock_executor

    await account_lockout.record_login_attempt(db, "test@example.com", "1.2.3.4", success=True)

    assert user.failed_login_count == 0
    assert user.locked_until is None
    assert user.first_failed_at is None


@pytest.mark.asyncio
async def test_get_delay_for_locked_user() -> None:
    db = AsyncMock()
    locked_until = datetime.now(UTC) + timedelta(minutes=10)
    user = User(
        email="locked@example.com", failed_login_count=5, locked_until=locked_until, status="active"
    )

    mock_executor = MagicMock()
    mock_executor.scalar_one_or_none.return_value = user
    db.execute.return_value = mock_executor

    status = await account_lockout.get_progressive_delay(db, "locked@example.com")
    assert status.is_locked is True
    assert "locked" in status.message.lower()
