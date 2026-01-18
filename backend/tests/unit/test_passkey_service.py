# backend/tests/unit/test_passkey_service.py
"""
Unit tests for passkey service.

Tests core WebAuthn operations without requiring a full HTTP stack.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.db.models.passkey import Passkey
from app.db.models.user import User
from app.services import passkey_service


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing challenge storage."""
    redis = AsyncMock()
    redis.set = AsyncMock()
    redis.get = AsyncMock()
    redis.delete = AsyncMock()
    return redis


@pytest.fixture
def sample_user():
    """Sample user for testing."""
    user = User(
        id=uuid4(),
        email="test@example.com",
        hashed_password="hashed_password",
        is_active=True,
        is_verified=True,
    )
    return user


@pytest.mark.asyncio
async def test_store_and_retrieve_challenge(mock_redis):
    """Test that challenges are stored and retrieved correctly."""
    user_id = str(uuid4())
    challenge = b"test_challenge_bytes"

    # Store challenge
    await passkey_service.store_challenge(mock_redis, user_id, challenge, "registration")

    # Verify Redis.set was called with correct params
    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args
    assert call_args[0][0] == f"webauthn:challenge:registration:{user_id}"
    assert call_args[0][1] == challenge
    assert call_args[1]["ex"] == 300  # 5 minutes TTL

    # Retrieve challenge
    mock_redis.get.return_value = challenge
    retrieved = await passkey_service.retrieve_challenge(mock_redis, user_id, "registration")

    # Verify challenge was retrieved and deleted
    assert retrieved == challenge
    mock_redis.get.assert_called_once()
    mock_redis.delete.assert_called_once()


@pytest.mark.asyncio
async def test_retrieve_nonexistent_challenge(mock_redis):
    """Test retrieving a challenge that doesn't exist returns None."""
    user_id = str(uuid4())
    mock_redis.get.return_value = None

    retrieved = await passkey_service.retrieve_challenge(mock_redis, user_id, "registration")

    assert retrieved is None
    mock_redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_get_rp_id_from_setting():
    """Test that RP ID is taken from settings when set."""
    with patch("app.services.passkey_service.settings") as mock_settings:
        mock_settings.WEBAUTHN_RP_ID = "example.com"

        rp_id = passkey_service._get_rp_id()

        assert rp_id == "example.com"


@pytest.mark.asyncio
async def test_get_rp_id_from_frontend_url():
    """Test that RP ID is derived from FRONTEND_URL when not explicitly set."""
    with patch("app.services.passkey_service.settings") as mock_settings:
        mock_settings.WEBAUTHN_RP_ID = None
        mock_settings.FRONTEND_URL = "https://app.example.com:8443"

        rp_id = passkey_service._get_rp_id()

        assert rp_id == "app.example.com"


@pytest.mark.asyncio
async def test_get_origin_from_setting():
    """Test that origin is taken from settings when set."""
    with patch("app.services.passkey_service.settings") as mock_settings:
        mock_settings.WEBAUTHN_ORIGIN = "https://custom.example.com"

        origin = passkey_service._get_origin()

        assert origin == "https://custom.example.com"


@pytest.mark.asyncio
async def test_get_origin_from_frontend_url():
    """Test that origin defaults to FRONTEND_URL."""
    with patch("app.services.passkey_service.settings") as mock_settings:
        mock_settings.WEBAUTHN_ORIGIN = None
        mock_settings.FRONTEND_URL = "https://app.example.com"

        origin = passkey_service._get_origin()

        assert origin == "https://app.example.com"


@pytest.mark.asyncio
async def test_list_user_passkeys(sample_user):
    """Test listing user's passkeys."""
    from sqlalchemy.ext.asyncio import AsyncSession

    # Mock database session
    db = AsyncMock(spec=AsyncSession)

    # Create mock passkeys
    passkey1 = Passkey(
        id=uuid4(),
        user_id=sample_user.id,
        credential_id=b"credential_1",
        public_key=b"public_key_1",
        sign_count=0,
        device_name="Device 1",
        transports=["usb", "internal"],
        backup_eligible=True,
        backup_state=False,
    )
    passkey2 = Passkey(
        id=uuid4(),
        user_id=sample_user.id,
        credential_id=b"credential_2",
        public_key=b"public_key_2",
        sign_count=5,
        device_name="Device 2",
        transports=["internal"],
        backup_eligible=True,
        backup_state=True,
    )

    # Mock database query result
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [passkey1, passkey2]
    db.execute = AsyncMock(return_value=mock_result)

    # Get passkeys
    passkeys = await passkey_service.list_user_passkeys(db, sample_user)

    # Verify results
    assert len(passkeys) == 2
    assert passkeys[0]["device_name"] == "Device 1"
    assert passkeys[0]["backup_state"] is False
    assert passkeys[1]["device_name"] == "Device 2"
    assert passkeys[1]["backup_state"] is True


@pytest.mark.asyncio
async def test_rename_passkey(sample_user):
    """Test renaming a passkey."""
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    passkey_id = str(uuid4())
    new_name = "My Updated Passkey"

    # Mock successful update
    mock_result = MagicMock()
    mock_result.rowcount = 1
    db.execute = AsyncMock(return_value=mock_result)
    db.commit = AsyncMock()

    # Rename passkey
    success = await passkey_service.rename_passkey(db, sample_user, passkey_id, new_name)

    # Verify success
    assert success is True
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_rename_nonexistent_passkey(sample_user):
    """Test renaming a passkey that doesn't exist."""
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    passkey_id = str(uuid4())

    # Mock no rows updated
    mock_result = MagicMock()
    mock_result.rowcount = 0
    db.execute = AsyncMock(return_value=mock_result)
    db.commit = AsyncMock()

    # Try to rename
    success = await passkey_service.rename_passkey(db, sample_user, passkey_id, "New Name")

    # Verify failure
    assert success is False


@pytest.mark.asyncio
async def test_delete_passkey(sample_user):
    """Test deleting a passkey."""
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    passkey_id = str(uuid4())

    # Mock successful deletion
    mock_result = MagicMock()
    mock_result.rowcount = 1
    db.execute = AsyncMock(return_value=mock_result)
    db.commit = AsyncMock()

    # Mock audit service
    with patch("app.services.passkey_service.audit_service.log_event", new=AsyncMock()):
        # Delete passkey
        success = await passkey_service.delete_passkey(db, sample_user, passkey_id)

    # Verify success
    assert success is True
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_get_passkey_count(sample_user):
    """Test getting count of user's passkeys."""
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)

    # Mock count result
    mock_result = MagicMock()
    mock_result.scalar.return_value = 3
    db.execute = AsyncMock(return_value=mock_result)

    # Get count
    count = await passkey_service.get_passkey_count(db, sample_user.id)

    # Verify
    assert count == 3
