from unittest.mock import patch

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

from ..factories.user_factory import UserFactory

API_PREFIX = settings.API_V1_STR


async def login_user(client: AsyncClient, email: str, password: str) -> dict:
    login_data = {"username": email, "password": password}
    response = await client.post(f"{API_PREFIX}/auth/login", data=login_data)
    assert response.status_code == status.HTTP_200_OK
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_settings_admin(test_client: AsyncClient, db_session: AsyncSession) -> None:
    admin = UserFactory.create_user(
        session=db_session, email="admin_settings@example.com", is_superuser=True
    )
    await db_session.flush()
    headers = await login_user(test_client, admin.email, "password123")

    response = await test_client.get(f"{API_PREFIX}/settings", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    # Check for some expected keys in SettingsRead
    assert "tmdb_api_key" in data
    assert "deepl_api_keys" in data
    assert "webhook_secret" in data


@pytest.mark.asyncio
async def test_update_settings_admin(test_client: AsyncClient, db_session: AsyncSession) -> None:
    admin = UserFactory.create_user(
        session=db_session, email="admin_set_update@example.com", is_superuser=True
    )
    await db_session.flush()
    headers = await login_user(test_client, admin.email, "password123")

    # Mock validate_all_settings to avoid external calls
    with patch("app.api.routers.settings.validate_all_settings") as mock_val:
        update_data = {"tmdb_api_key": "new_tmdb_key", "log_level": "DEBUG"}
        response = await test_client.put(
            f"{API_PREFIX}/settings", json=update_data, headers=headers
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["tmdb_api_key"].startswith("********")
        mock_val.assert_called_once()


@pytest.mark.asyncio
async def test_update_qbittorrent_host_admin(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = UserFactory.create_user(
        session=db_session, email="admin_qb_update@example.com", is_superuser=True
    )
    await db_session.flush()
    headers = await login_user(test_client, admin.email, "password123")

    with patch("app.api.routers.settings.validate_all_settings"):
        update_data = {"qbittorrent_host": "192.168.1.100"}
        response = await test_client.put(
            f"{API_PREFIX}/settings", json=update_data, headers=headers
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["qbittorrent_host"] == "192.168.1.100"


@pytest.mark.asyncio
async def test_get_raw_setting_admin(test_client: AsyncClient, db_session: AsyncSession) -> None:
    admin = UserFactory.create_user(
        session=db_session, email="admin_raw@example.com", is_superuser=True
    )
    await db_session.flush()
    headers = await login_user(test_client, admin.email, "password123")

    # This is an internal endpoint (include_in_schema=False) but accessible by admins
    response = await test_client.get(f"{API_PREFIX}/settings/raw/tmdb_api_key", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["field"] == "tmdb_api_key"


@pytest.mark.asyncio
async def test_settings_forbidden_for_standard_user(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = UserFactory.create_user(session=db_session, email="standard_settings@example.com")
    await db_session.flush()
    headers = await login_user(test_client, user.email, "password123")

    response = await test_client.get(f"{API_PREFIX}/settings", headers=headers)
    assert response.status_code == status.HTTP_403_FORBIDDEN
