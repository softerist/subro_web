"""Tests for qBittorrent auto-configuration endpoint."""

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.users import get_current_active_admin_user
from app.db.models.user import User

# Import the dependency to override
from app.db.session import get_async_session
from app.main import app

API_PREFIX = settings.API_V1_STR


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = MagicMock()
    # Mock execute/scalars/all chain
    # execute() is awaited, so it must return a coroutine or be an AsyncMock
    session.execute = AsyncMock()

    mock_result = MagicMock()
    # Return empty list when iterating or calling all()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    # Also mock commit and rollback as async
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()

    return session


@pytest.fixture
async def client_with_mock_db(mock_db_session):
    """Create a test client with mocked DB dependency and mocked lifespan."""

    # Override the get_async_session dependency
    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_async_session] = override_get_db

    # Patch socket.getaddrinfo ONLY for these tests to avoid gaierror in restricted environments
    original_getaddrinfo = socket.getaddrinfo

    def mocked_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        try:
            return original_getaddrinfo(host, port, family, type, proto, flags)
        except socket.gaierror:
            # Return a dummy local address for any host that doesn't resolve
            return [
                (
                    socket.AddressFamily.AF_INET,
                    socket.SocketKind.SOCK_STREAM,
                    6,
                    "",
                    ("127.0.0.1", port or 0),
                )
            ]

    # Mock the database engine initialization in the app lifecycle
    with patch("app.main.lifespan_db_manager") as mock_lifespan:
        # Mocking it as an async function that does nothing
        async def side_effect(*_args, **_kwargs):
            return None

        mock_lifespan.side_effect = side_effect

        # Also ensure the session factory is None in app.db.session
        with patch("app.db.session.FastAPISessionLocal", None):
            with patch("app.db.session.fastapi_async_engine", None):
                # Apply the socket patch during the client lifecycle
                with patch("socket.getaddrinfo", side_effect=mocked_getaddrinfo):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def admin_user():
    """Create a mock admin user."""
    user = User(
        id=1, email="admin_autoconfig@example.com", is_superuser=True, is_active=True, role="admin"
    )
    return user


@pytest.mark.asyncio
async def test_configure_qbittorrent_missing_host(
    client_with_mock_db: AsyncClient,
    admin_user: User,
) -> None:
    """Test response when qBittorrent host is not configured in settings."""
    app.dependency_overrides[get_current_active_admin_user] = lambda: admin_user

    try:
        # Mock settings to return empty qbittorrent_host
        with patch("app.crud.crud_app_settings.crud_app_settings.get") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.qbittorrent_host = None
            mock_get_settings.return_value = mock_settings

            response = await client_with_mock_db.post(
                f"{API_PREFIX}/settings/webhook-key/configure-qbittorrent"
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is False
            assert "host not configured" in data["message"]
            assert data["details"]["step"] == "validate_credentials"
    finally:
        pass


@pytest.mark.asyncio
async def test_configure_qbittorrent_connection_failure(
    client_with_mock_db: AsyncClient,
    admin_user: User,
) -> None:
    """Test response when connection to qBittorrent fails."""
    app.dependency_overrides[get_current_active_admin_user] = lambda: admin_user

    try:
        with patch("app.crud.crud_app_settings.crud_app_settings.get") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.qbittorrent_host = "192.168.1.100"
            mock_get_settings.return_value = mock_settings

            # Mock login failure
            # Patch the SOURCE module where login_to_qbittorrent is defined
            with patch(
                "app.modules.subtitle.services.torrent_client.login_to_qbittorrent",
                return_value=None,
            ) as mock_login:
                # Mock file writing to avoid side effects
                with patch(
                    "app.api.routers.webhook_keys._write_key_to_env_file", return_value=True
                ):
                    response = await client_with_mock_db.post(
                        f"{API_PREFIX}/settings/webhook-key/configure-qbittorrent"
                    )

                    assert response.status_code == status.HTTP_200_OK
                    data = response.json()
                    assert data["success"] is False
                    assert "Failed to connect" in data["message"]
                    assert data["webhook_key_generated"] is True
                    assert data["qbittorrent_configured"] is False
                    assert data["details"]["step"] == "connect_qbittorrent"
                    mock_login.assert_called_once()
    finally:
        pass


@pytest.mark.asyncio
async def test_configure_qbittorrent_autorun_failure(
    client_with_mock_db: AsyncClient,
    admin_user: User,
) -> None:
    """Test response when login succeeds but autorun configuration fails."""
    app.dependency_overrides[get_current_active_admin_user] = lambda: admin_user

    try:
        with patch("app.crud.crud_app_settings.crud_app_settings.get") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.qbittorrent_host = "192.168.1.100"
            mock_get_settings.return_value = mock_settings

            # Mock login success
            mock_qb_client = MagicMock()
            # Patch the SOURCE module
            with patch(
                "app.modules.subtitle.services.torrent_client.login_to_qbittorrent",
                return_value=mock_qb_client,
            ):
                # Mock autorun config failure - Patch the SOURCE module
                with patch(
                    "app.modules.subtitle.services.torrent_client.configure_webhook_autorun",
                    return_value=False,
                ) as mock_config:
                    with patch(
                        "app.api.routers.webhook_keys._write_key_to_env_file", return_value=True
                    ):
                        response = await client_with_mock_db.post(
                            f"{API_PREFIX}/settings/webhook-key/configure-qbittorrent"
                        )

                        assert response.status_code == status.HTTP_200_OK
                        data = response.json()
                        assert data["success"] is False
                        assert "failed to configure autorun" in data["message"]
                        assert data["details"]["step"] == "configure_autorun"
                        mock_config.assert_called_once()
    finally:
        pass


@pytest.mark.asyncio
async def test_configure_qbittorrent_success(
    client_with_mock_db: AsyncClient,
    admin_user: User,
) -> None:
    """Test successful auto-configuration."""
    app.dependency_overrides[get_current_active_admin_user] = lambda: admin_user

    try:
        with patch("app.crud.crud_app_settings.crud_app_settings.get") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.qbittorrent_host = "192.168.1.100"
            mock_get_settings.return_value = mock_settings

            # Mock login success
            mock_qb_client = MagicMock()
            # Patch the SOURCE module
            with patch(
                "app.modules.subtitle.services.torrent_client.login_to_qbittorrent",
                return_value=mock_qb_client,
            ):
                # Mock autorun config success - Patch the SOURCE module
                with patch(
                    "app.modules.subtitle.services.torrent_client.configure_webhook_autorun",
                    return_value=True,
                ) as mock_config:
                    with patch(
                        "app.api.routers.webhook_keys._write_key_to_env_file", return_value=True
                    ) as mock_write:
                        response = await client_with_mock_db.post(
                            f"{API_PREFIX}/settings/webhook-key/configure-qbittorrent"
                        )

                        assert response.status_code == status.HTTP_200_OK
                        data = response.json()
                        assert data["success"] is True
                        assert "configured successfully" in data["message"]
                        assert data["webhook_key_generated"] is True
                        assert data["qbittorrent_configured"] is True

                        mock_write.assert_called_once()
                        mock_config.assert_called_once()

    finally:
        app.dependency_overrides.clear()
