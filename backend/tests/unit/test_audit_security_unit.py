import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.audit_service import AuditRateLimiter, anonymize_audit_actor, sanitize_details


@pytest.mark.asyncio
async def test_audit_rate_limiter_acquire():
    # Test strict limit
    limiter = AuditRateLimiter(max_concurrent=2)
    assert await limiter.acquire() is True
    assert await limiter.acquire() is True
    assert await limiter.acquire() is False  # Should fail immediately

    limiter.release()
    assert await limiter.acquire() is True


@pytest.mark.asyncio
async def test_audit_rate_limiter_release_error_safe():
    limiter = AuditRateLimiter(max_concurrent=1)
    # Releasing without acquiring shouldn't crash (ValueError ignored)
    try:
        limiter.release()
    except Exception as e:
        pytest.fail(f"release() raised exception: {e}")


def test_sanitize_details_allowlist():
    details = {"status": "active", "unexpected_key": "some_value", "reason": "user_action"}
    # status and reason are now allowed. unexpected_key is not.
    sanitized = sanitize_details(details)
    assert sanitized is not None
    assert "status" in sanitized
    assert "reason" in sanitized
    assert "unexpected_key" not in sanitized


def test_sanitize_details_pii_masking():
    details = {
        "status": "active",
        "access_token": "secret_token_value",  # Not allowed, will be dropped
        "api_key": "sk-12345",  # Not allowed, dropped
        # We need a key that IS allowed but matches sensitive pattern?
        # Or checking that sensitive keys ARE dropped is enough?
        # The code drops keys NOT in allowlist.
        # So "access_token" is dropped. Safety achieved.
        # Let's verify dropping.
    }
    sanitized = sanitize_details(details)
    # If access_token is dropped, it's None or missing key
    assert "access_token" not in sanitized

    # Check key_id (allowed) is NOT redacted (regex fix)
    details2 = {"key_id": "12345"}
    sanitized2 = sanitize_details(details2)
    assert sanitized2["key_id"] == "12345"


def test_sanitize_details_truncation():
    # Create huge details
    # We need a key that is allowed
    huge_val = "x" * (33 * 1024)  # > 32KB
    details = {
        "reason": "test",
        "email": huge_val,  # email is allowed
    }
    sanitized = sanitize_details(details)

    # Logic should remove largest key until it fits
    assert "_truncated" in sanitized
    assert sanitized["_truncated"] is True
    assert "reason" in sanitized
    assert "email" not in sanitized


@pytest.mark.asyncio
async def test_anonymize_audit_actor():
    mock_db = AsyncMock()
    user_id = uuid.uuid4()

    # Mock execute result
    mock_result = MagicMock()
    mock_result.rowcount = 5
    mock_db.execute.return_value = mock_result

    count = await anonymize_audit_actor(mock_db, user_id)

    # It executes twice (once for actor, once for target)
    assert mock_db.execute.call_count == 2
    assert count == 10  # 5 + 5
