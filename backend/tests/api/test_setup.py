from unittest.mock import patch

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.crud_app_settings import crud_app_settings

API_PREFIX = settings.API_V1_STR


@pytest.mark.asyncio
async def test_setup_status_no_users(test_client: AsyncClient):
    # Fresh DB should have setup_completed = False (if not initialized by factories)
    response = await test_client.get(f"{API_PREFIX}/setup/status")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["setup_completed"] is False


@pytest.mark.asyncio
async def test_complete_setup_success(test_client: AsyncClient, db_session: AsyncSession):
    setup_payload = {
        "admin_email": "initial_admin@example.com",
        "admin_password": "securepassword123",
        "settings": {"tmdb_api_key": "some_key"},
    }

    # Mock validate_all_settings
    with patch("app.api.routers.setup.validate_all_settings"):
        response = await test_client.post(f"{API_PREFIX}/setup/complete", json=setup_payload)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["setup_completed"] is True

        # Verify setup is now marked as completed in DB
        is_completed = await crud_app_settings.get_setup_completed(db_session)
        assert is_completed is True


@pytest.mark.asyncio
async def test_setup_endpoints_forbidden_once_completed(
    test_client: AsyncClient, db_session: AsyncSession
):
    # Mark setup as completed directly
    await crud_app_settings.mark_setup_completed(db_session)
    await db_session.commit()

    setup_payload = {"admin_email": "another_admin@example.com", "admin_password": "password"}
    response = await test_client.post(f"{API_PREFIX}/setup/complete", json=setup_payload)
    # The routers returns 404 NOT FOUND for setup endpoints once completed (security by obscurity/denial)
    assert response.status_code == status.HTTP_404_NOT_FOUND
