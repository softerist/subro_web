# backend/tests/api/test_open_signup.py
"""Tests for the Open Signup toggle feature."""

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.app_settings import AppSettings

from ..factories.user_factory import UserFactory

API_PREFIX = settings.API_V1_STR


async def login_user(client: AsyncClient, email: str, password: str) -> dict:
    """Logs in a user and returns auth headers."""
    login_data = {"username": email, "password": password}
    response = await client.post(f"{API_PREFIX}/auth/login", data=login_data)
    assert response.status_code == status.HTTP_200_OK, f"Login failed for {email}: {response.text}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def get_or_create_app_settings(db_session: AsyncSession) -> AppSettings:
    """Get or create the singleton app settings row."""
    from sqlalchemy import select

    result = await db_session.execute(select(AppSettings))
    app_settings = result.scalars().first()
    if not app_settings:
        app_settings = AppSettings(open_signup=False)
        db_session.add(app_settings)
        await db_session.flush()
    return app_settings


# --- Test GET /admin/settings/open-signup ---


@pytest.mark.asyncio
async def test_get_open_signup_as_superuser(test_client: AsyncClient, db_session: AsyncSession):
    """Test superuser can get open signup status."""
    # Arrange
    superuser = UserFactory.create_user(
        session=db_session,
        email="superuser_get_signup@example.com",
        role="admin",
        is_superuser=True,
    )
    await db_session.flush()

    # Ensure app_settings exists
    app_settings = await get_or_create_app_settings(db_session)
    app_settings.open_signup = True
    await db_session.flush()

    headers = await login_user(test_client, superuser.email, "password123")

    # Act
    response = await test_client.get(f"{API_PREFIX}/admin/settings/open-signup", headers=headers)

    # Assert
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "open_signup" in data
    assert data["open_signup"] is True


@pytest.mark.asyncio
async def test_get_open_signup_as_admin_not_superuser(
    test_client: AsyncClient, db_session: AsyncSession
):
    """Test admin (non-superuser) cannot access open signup endpoint."""
    # Arrange
    admin = UserFactory.create_user(
        session=db_session,
        email="admin_not_super@example.com",
        role="admin",
        is_superuser=False,
    )
    await db_session.flush()
    await get_or_create_app_settings(db_session)

    headers = await login_user(test_client, admin.email, "password123")

    # Act
    response = await test_client.get(f"{API_PREFIX}/admin/settings/open-signup", headers=headers)

    # Assert
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_get_open_signup_as_standard_user(test_client: AsyncClient, db_session: AsyncSession):
    """Test standard user cannot access open signup endpoint."""
    # Arrange
    user = UserFactory.create_user(
        session=db_session,
        email="standard_signup@example.com",
        role="standard",
    )
    await db_session.flush()

    headers = await login_user(test_client, user.email, "password123")

    # Act
    response = await test_client.get(f"{API_PREFIX}/admin/settings/open-signup", headers=headers)

    # Assert
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_get_open_signup_unauthenticated(test_client: AsyncClient):
    """Test unauthenticated user cannot access open signup endpoint."""
    response = await test_client.get(f"{API_PREFIX}/admin/settings/open-signup")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- Test PATCH /admin/settings/open-signup ---


@pytest.mark.asyncio
async def test_set_open_signup_as_superuser(test_client: AsyncClient, db_session: AsyncSession):
    """Test superuser can toggle open signup."""
    # Arrange
    superuser = UserFactory.create_user(
        session=db_session,
        email="superuser_set_signup@example.com",
        role="admin",
        is_superuser=True,
    )
    await db_session.flush()

    app_settings = await get_or_create_app_settings(db_session)
    app_settings.open_signup = False
    await db_session.flush()

    headers = await login_user(test_client, superuser.email, "password123")

    # Act - Enable open signup
    response = await test_client.patch(
        f"{API_PREFIX}/admin/settings/open-signup",
        json={"open_signup": True},
        headers=headers,
    )

    # Assert
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["open_signup"] is True

    # Verify in DB
    await db_session.refresh(app_settings)
    assert app_settings.open_signup is True


@pytest.mark.asyncio
async def test_set_open_signup_disable(test_client: AsyncClient, db_session: AsyncSession):
    """Test superuser can disable open signup."""
    # Arrange
    superuser = UserFactory.create_user(
        session=db_session,
        email="superuser_disable_signup@example.com",
        role="admin",
        is_superuser=True,
    )
    await db_session.flush()

    app_settings = await get_or_create_app_settings(db_session)
    app_settings.open_signup = True
    await db_session.flush()

    headers = await login_user(test_client, superuser.email, "password123")

    # Act - Disable open signup
    response = await test_client.patch(
        f"{API_PREFIX}/admin/settings/open-signup",
        json={"open_signup": False},
        headers=headers,
    )

    # Assert
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["open_signup"] is False


@pytest.mark.asyncio
async def test_set_open_signup_as_non_superuser(test_client: AsyncClient, db_session: AsyncSession):
    """Test non-superuser cannot toggle open signup."""
    # Arrange
    admin = UserFactory.create_user(
        session=db_session,
        email="admin_cant_set_signup@example.com",
        role="admin",
        is_superuser=False,
    )
    await db_session.flush()
    await get_or_create_app_settings(db_session)

    headers = await login_user(test_client, admin.email, "password123")

    # Act
    response = await test_client.patch(
        f"{API_PREFIX}/admin/settings/open-signup",
        json={"open_signup": True},
        headers=headers,
    )

    # Assert
    assert response.status_code == status.HTTP_403_FORBIDDEN


# --- Test Registration with Dynamic Open Signup ---


@pytest.mark.asyncio
async def test_registration_when_open_signup_enabled(
    test_client: AsyncClient, db_session: AsyncSession
):
    """Test registration works when open signup is enabled."""
    # Arrange - Enable open signup
    app_settings = await get_or_create_app_settings(db_session)
    app_settings.open_signup = True
    await db_session.flush()

    # Act
    register_data = {"email": "newuser_open@example.com", "password": "SecurePass123"}
    response = await test_client.post(f"{API_PREFIX}/auth/register", json=register_data)

    # Assert
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["email"] == register_data["email"]


@pytest.mark.asyncio
async def test_registration_when_open_signup_disabled(
    test_client: AsyncClient, db_session: AsyncSession
):
    """Test registration is blocked when open signup is disabled."""
    # Arrange - Disable open signup
    app_settings = await get_or_create_app_settings(db_session)
    app_settings.open_signup = False
    await db_session.flush()

    # Act
    register_data = {"email": "newuser_closed@example.com", "password": "SecurePass123"}
    response = await test_client.post(f"{API_PREFIX}/auth/register", json=register_data)

    # Assert
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "disabled" in response.json()["detail"].lower()
