from unittest.mock import patch

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.api_key import ApiKey

from ..factories.user_factory import UserFactory

API_PREFIX = settings.API_V1_STR


async def login_user(client: AsyncClient, email: str, password: str) -> dict:
    login_data = {"username": email, "password": password}
    response = await client.post(f"{API_PREFIX}/auth/login", data=login_data)
    assert response.status_code == status.HTTP_200_OK
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_current_user_me(test_client: AsyncClient, db_session: AsyncSession) -> None:
    user = UserFactory.create_user(session=db_session, email="me@example.com")
    await db_session.flush()
    headers = await login_user(test_client, user.email, "password123")

    # /users/me is common but users router in users.py might have it included differently
    # Main app usually includes it at /api/v1/users
    response = await test_client.get(f"{API_PREFIX}/users/me", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["email"] == "me@example.com"


@pytest.mark.asyncio
async def test_regenerate_api_key_success(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = UserFactory.create_user(session=db_session, email="apikey_user@example.com")
    await db_session.flush()
    headers = await login_user(test_client, user.email, "password123")

    with patch("app.api.routers.users.settings") as mock_settings:
        mock_settings.API_KEY_PEPPER = "testpepper"

        response = await test_client.post(f"{API_PREFIX}/users/me/api-key", headers=headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "api_key" in data
        assert "..." in data["preview"]
        assert len(data["preview"]) >= 12  # 8 prefix + 4 last4 + some dots

        # Verify in DB
        from sqlalchemy import select

        stmt = select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None))
        result = await db_session.execute(stmt)
        key_record = result.scalar_one_or_none()
        assert key_record is not None


@pytest.mark.asyncio
async def test_revoke_api_key_success(test_client: AsyncClient, db_session: AsyncSession) -> None:
    user = UserFactory.create_user(session=db_session, email="revoke_user@example.com")
    await db_session.flush()
    headers = await login_user(test_client, user.email, "password123")

    # Create a key first
    from datetime import UTC, datetime

    key_record = ApiKey(
        user_id=user.id,
        name="Default",
        prefix="sub_test",
        last4="1234",
        hashed_key="hashed",
        created_at=datetime.now(UTC),
    )
    db_session.add(key_record)
    await db_session.commit()

    response = await test_client.delete(f"{API_PREFIX}/users/me/api-key", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["revoked"] is True
