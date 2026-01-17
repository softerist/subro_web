"""Tests for secure webhook key retrieval endpoint."""

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import settings
from app.core.security import encrypt_value
from app.crud.crud_app_settings import crud_app_settings

from ..factories.user_factory import UserFactory

API_PREFIX = settings.API_V1_STR


async def login_user(client: AsyncClient, email: str, password: str) -> dict:
    login_data = {"username": email, "password": password}
    response = await client.post(f"{API_PREFIX}/auth/login", data=login_data)
    assert response.status_code == status.HTTP_200_OK
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_current_key_localhost_allowed(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that key retrieval succeeds from localhost."""
    # Setup: Store an encrypted key in app_settings
    app_settings = await crud_app_settings.get(db_session)
    test_key = "test_webhook_key_12345678901234567890"
    app_settings.qbittorrent_webhook_key_encrypted = encrypt_value(test_key)
    await db_session.commit()

    # Request from test client (localhost by default)
    response = await test_client.get(f"{API_PREFIX}/settings/webhook-key/current-key")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "key" in data
    assert data["key"] == test_key


@pytest.mark.asyncio
async def test_get_current_key_no_key_configured(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that 404 is returned when no webhook key is configured."""
    # Ensure no key is set
    app_settings = await crud_app_settings.get(db_session)
    app_settings.qbittorrent_webhook_key_encrypted = None
    await db_session.commit()

    response = await test_client.get(f"{API_PREFIX}/settings/webhook-key/current-key")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "No webhook key" in response.json()["detail"]


@pytest.mark.asyncio
async def test_configure_stores_encrypted_key(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that configure endpoint stores encrypted key in app_settings."""

    # Create admin user
    admin = UserFactory.create_user(
        session=db_session, email="admin_encrypt@example.com", is_superuser=True
    )
    await db_session.flush()
    headers = await login_user(test_client, admin.email, "password123")

    # Setup qBittorrent settings (required for configure)
    app_settings = await crud_app_settings.get(db_session)
    app_settings.qbittorrent_host = "host.docker.internal"
    app_settings.qbittorrent_port = 8080
    app_settings.qbittorrent_username = "admin"
    app_settings.qbittorrent_password = encrypt_value("password")
    await db_session.commit()

    # Mock qBittorrent connection
    with patch(
        "app.modules.subtitle.services.torrent_client.login_to_qbittorrent_with_settings"
    ) as mock_login:
        mock_client = type("MockClient", (), {"is_logged_in": True})()
        mock_login.return_value = mock_client

        with patch(
            "app.modules.subtitle.services.torrent_client.configure_webhook_autorun"
        ) as mock_autorun:
            mock_autorun.return_value = True

            response = await test_client.post(
                f"{API_PREFIX}/settings/webhook-key/configure-qbittorrent",
                headers=headers,
            )

    # Verify success
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True

    # Verify encrypted key was stored
    await db_session.refresh(app_settings)
    assert app_settings.qbittorrent_webhook_key_encrypted is not None
    assert len(app_settings.qbittorrent_webhook_key_encrypted) > 50  # Encrypted value


@pytest.mark.asyncio
async def test_configure_command_has_no_api_key(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that qBittorrent command doesn't include --api-key."""

    # Create admin user
    admin = UserFactory.create_user(
        session=db_session, email="admin_nokey@example.com", is_superuser=True
    )
    await db_session.flush()
    headers = await login_user(test_client, admin.email, "password123")

    # Setup qBittorrent settings
    app_settings = await crud_app_settings.get(db_session)
    app_settings.qbittorrent_host = "host.docker.internal"
    app_settings.qbittorrent_port = 8080
    app_settings.qbittorrent_username = "admin"
    app_settings.qbittorrent_password = encrypt_value("password")
    await db_session.commit()

    captured_command = None

    def capture_autorun(_client, script_path):
        nonlocal captured_command
        captured_command = script_path
        return True

    with patch(
        "app.modules.subtitle.services.torrent_client.login_to_qbittorrent_with_settings"
    ) as mock_login:
        mock_client = MagicMock()
        mock_client.is_logged_in = True
        mock_login.return_value = mock_client

        with patch(
            "app.modules.subtitle.services.torrent_client.configure_webhook_autorun",
            side_effect=capture_autorun,
        ):
            response = await test_client.post(
                f"{API_PREFIX}/settings/webhook-key/configure-qbittorrent",
                headers=headers,
            )

    assert response.status_code == status.HTTP_200_OK
    # Verify no api_key was passed (function signature changed)
    assert captured_command is not None
    assert "--api-key" not in str(captured_command)
