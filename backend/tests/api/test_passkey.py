# backend/tests/api/test_passkey.py
"""
API integration tests for passkey endpoints.

Tests the full HTTP flow for passkey registration, authentication, and management.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from tests.factories.user_factory import UserFactory

API_PREFIX = settings.API_V1_STR


async def login_user(client: AsyncClient, email: str, password: str) -> dict:
    """Logs in a user and returns auth headers."""
    login_data = {"username": email, "password": password}
    response = await client.post(f"{API_PREFIX}/auth/login", data=login_data)
    assert response.status_code == status.HTTP_200_OK, f"Login failed for {email}: {response.text}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_registration_options_requires_auth(test_client: AsyncClient) -> None:
    """Test that getting registration options requires authentication."""
    response = await test_client.post(f"{API_PREFIX}/auth/passkey/register/options")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_registration_options_success(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that authenticated user can get registration options."""
    # Create and login user
    user = UserFactory.create_user(session=db_session, email="passkey_reg@example.com", password="password")
    headers = await login_user(test_client, user.email, "password")

    # Mock Redis for challenge storage
    with patch("app.api.routers.passkey.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value.__aenter__.return_value = mock_redis

        # Get registration options
        response = await test_client.post(
            f"{API_PREFIX}/auth/passkey/register/options", headers=headers
        )

    # Verify response
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "challenge" in data
    assert "user" in data
    assert data["user"]["name"] == user.email
    assert "pubKeyCredParams" in data
    assert data["authenticatorSelection"]["residentKey"] == "required"


@pytest.mark.asyncio
async def test_verify_registration_requires_auth(test_client: AsyncClient) -> None:
    """Test that verifying registration requires authentication."""
    response = await test_client.post(
        f"{API_PREFIX}/auth/passkey/register/verify", json={"credential": {}, "device_name": "Test"}
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_list_passkeys_requires_auth(test_client: AsyncClient) -> None:
    """Test that listing passkeys requires authentication."""
    response = await test_client.get(f"{API_PREFIX}/auth/passkey/list")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_list_passkeys_empty(test_client: AsyncClient, db_session: AsyncSession) -> None:
    """Test listing passkeys when user has none."""
    # Create and login user
    user = UserFactory.create_user(session=db_session, email="no_passkeys@example.com", password="password")
    headers = await login_user(test_client, user.email, "password")

    # List passkeys
    response = await test_client.get(f"{API_PREFIX}/auth/passkey/list", headers=headers)

    # Verify response
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["passkey_count"] == 0
    assert data["passkeys"] == []


@pytest.mark.asyncio
async def test_rename_passkey_requires_auth(test_client: AsyncClient) -> None:
    """Test that renaming a passkey requires authentication."""
    passkey_id = str(uuid4())
    response = await test_client.put(
        f"{API_PREFIX}/auth/passkey/{passkey_id}/name", json={"name": "New Name"}
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_rename_nonexistent_passkey(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test renaming a passkey that doesn't exist."""
    # Create and login user
    user = UserFactory.create_user(session=db_session, email="rename_test@example.com", password="password")
    headers = await login_user(test_client, user.email, "password")

    # Try to rename non-existent passkey
    fake_id = str(uuid4())
    response = await test_client.put(
        f"{API_PREFIX}/auth/passkey/{fake_id}/name", headers=headers, json={"name": "New Name"}
    )

    # Should return 404
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_delete_passkey_requires_auth(test_client: AsyncClient) -> None:
    """Test that deleting a passkey requires authentication."""
    passkey_id = str(uuid4())
    response = await test_client.delete(f"{API_PREFIX}/auth/passkey/{passkey_id}")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_delete_nonexistent_passkey(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test deleting a passkey that doesn't exist."""
    # Create and login user
    user = UserFactory.create_user(session=db_session, email="delete_test@example.com", password="password")
    headers = await login_user(test_client, user.email, "password")

    # Try to delete non-existent passkey
    fake_id = str(uuid4())
    response = await test_client.delete(f"{API_PREFIX}/auth/passkey/{fake_id}", headers=headers)

    # Should return 404
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_get_authentication_options_public(test_client: AsyncClient) -> None:
    """Test that getting authentication options is public (no auth required)."""
    # Mock Redis for challenge storage
    with patch("app.api.routers.passkey.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value.__aenter__.return_value = mock_redis

        # Get auth options without login
        response = await test_client.post(f"{API_PREFIX}/auth/passkey/login/options")

    # Should succeed even without auth
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "challenge" in data
    assert "rpId" in data
    assert data["userVerification"] == "preferred"


@pytest.mark.asyncio
async def test_get_authentication_options_with_email(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test getting authentication options for a specific user."""
    # Create user
    user = UserFactory.create_user(session=db_session, email="auth_opt@example.com")
    await db_session.commit()

    # Mock Redis
    with patch("app.api.routers.passkey.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value.__aenter__.return_value = mock_redis

        # Get auth options with email
        response = await test_client.post(
            f"{API_PREFIX}/auth/passkey/login/options", json={"email": user.email}
        )

    # Should succeed
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "challenge" in data


@pytest.mark.asyncio
async def test_verify_authentication_public(test_client: AsyncClient) -> None:
    """Test that verifying authentication is public (like login)."""
    # Mock Redis and authentication service
    with patch("app.api.routers.passkey.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value.__aenter__.return_value = mock_redis
        mock_redis.get.return_value = None  # No challenge (will fail)

        # Try to verify authentication with invalid credential
        response = await test_client.post(
            f"{API_PREFIX}/auth/passkey/login/verify",
            json={
                "credential": {
                    "id": "fake",
                    "rawId": "fake",
                    "response": {"clientDataJSON": "e30=", "authenticatorData": "AA==", "signature": "AA==", "userHandle": ""},
                    "type": "public-key",
                }
            },
        )

    # Should return 400 (bad request) not 401 (unauthorized)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_passkey_registration_flow_mocked(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test the full registration flow with mocked WebAuthn."""
    from sqlalchemy import select

    from app.db.models.passkey import Passkey

    # Create and login user
    user = UserFactory.create_user(session=db_session, email="reg_flow@example.com", password="password")
    headers = await login_user(test_client, user.email, "password")

    # Mock Redis and WebAuthn verification
    with (
        patch("app.api.routers.passkey.get_redis") as mock_get_redis,
        patch("app.services.passkey_service.verify_registration_response") as mock_verify,
    ):
        # Setup mocks
        mock_redis = AsyncMock()
        mock_get_redis.return_value.__aenter__.return_value = mock_redis

        # Mock WebAuthn verification
        mock_verification = MagicMock()
        mock_verification.credential_id = b"test_credential_id"
        mock_verification.credential_public_key = b"test_public_key"
        mock_verification.sign_count = 0
        mock_verification.aaguid = uuid4()
        mock_verification.credential_backed_up = True
        mock_verify.return_value = mock_verification

        # Step 1: Get registration options
        response = await test_client.post(
            f"{API_PREFIX}/auth/passkey/register/options", headers=headers
        )
        assert response.status_code == status.HTTP_200_OK

        # Step 2: Verify registration with mock credential
        mock_credential = {
            "id": "test_id",
            "rawId": "test_raw_id",
            "response": {
                "clientDataJSON": "test_client_data",
                "attestationObject": "test_attestation",
            },
            "type": "public-key",
            "transports": ["internal", "usb"],
        }

        response = await test_client.post(
            f"{API_PREFIX}/auth/passkey/register/verify",
            headers=headers,
            json={"credential": mock_credential, "device_name": "Test Passkey"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["device_name"] == "Test Passkey"

        # Verify passkey was created in database
        await db_session.commit()
        result = await db_session.execute(select(Passkey).where(Passkey.user_id == user.id))
        passkey = result.scalar_one_or_none()
        assert passkey is not None
        assert passkey.device_name == "Test Passkey"
        assert passkey.credential_id == b"test_credential_id"


@pytest.mark.asyncio
async def test_rename_and_delete_passkey_flow(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test renaming and deleting a passkey."""
    from app.db.models.passkey import Passkey

    # Create user with a passkey
    user = UserFactory.create_user(session=db_session, email="crud_flow@example.com", password="password")
    passkey = Passkey(
        user_id=user.id,
        credential_id=b"test_cred",
        public_key=b"test_key",
        sign_count=0,
        device_name="Original Name",
    )
    db_session.add(passkey)
    await db_session.commit()
    await db_session.refresh(passkey)
    passkey_id = str(passkey.id)

    # Login
    headers = await login_user(test_client, user.email, "password")

    # List passkeys
    response = await test_client.get(f"{API_PREFIX}/auth/passkey/list", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["passkey_count"] == 1
    assert data["passkeys"][0]["device_name"] == "Original Name"

    # Rename passkey
    response = await test_client.put(
        f"{API_PREFIX}/auth/passkey/{passkey_id}/name", headers=headers, json={"name": "New Name"}
    )
    assert response.status_code == status.HTTP_200_OK

    # Verify rename
    response = await test_client.get(f"{API_PREFIX}/auth/passkey/list", headers=headers)
    data = response.json()
    assert data["passkeys"][0]["device_name"] == "New Name"

    # Delete passkey
    response = await test_client.delete(f"{API_PREFIX}/auth/passkey/{passkey_id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    # Verify deletion
    response = await test_client.get(f"{API_PREFIX}/auth/passkey/list", headers=headers)
    data = response.json()
    assert data["passkey_count"] == 0
