# backend/tests/api/test_user_name_fields.py
"""Tests for the User Name fields feature (first_name/last_name)."""

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
    """Get or create app settings to enable registration."""
    from sqlalchemy import select

    result = await db_session.execute(select(AppSettings))
    app_settings = result.scalars().first()
    if not app_settings:
        app_settings = AppSettings(open_signup=True)
        db_session.add(app_settings)
        await db_session.flush()
    return app_settings


# --- Test User Creation with Name Fields ---


@pytest.mark.asyncio
async def test_create_user_with_name_fields(test_client: AsyncClient, db_session: AsyncSession):
    """Test admin can create user with first_name and last_name."""
    # Arrange
    admin = UserFactory.create_user(
        session=db_session,
        email="admin_create_name@example.com",
        role="admin",
        is_superuser=True,
    )
    await db_session.flush()

    headers = await login_user(test_client, admin.email, "password123")

    # Act
    user_data = {
        "email": "nameduser@example.com",
        "password": "SecurePass123",
        "first_name": "John",
        "last_name": "Doe",
        "role": "standard",
    }
    response = await test_client.post(
        f"{API_PREFIX}/admin/users",
        json=user_data,
        headers=headers,
    )

    # Assert
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["email"] == user_data["email"]
    assert data["first_name"] == "John"
    assert data["last_name"] == "Doe"


@pytest.mark.asyncio
async def test_create_user_without_name_fields(test_client: AsyncClient, db_session: AsyncSession):
    """Test admin can create user without name fields (they are optional)."""
    # Arrange
    admin = UserFactory.create_user(
        session=db_session,
        email="admin_create_noname@example.com",
        role="admin",
        is_superuser=True,
    )
    await db_session.flush()

    headers = await login_user(test_client, admin.email, "password123")

    # Act
    user_data = {
        "email": "noname_user@example.com",
        "password": "SecurePass123",
        "role": "standard",
    }
    response = await test_client.post(
        f"{API_PREFIX}/admin/users",
        json=user_data,
        headers=headers,
    )

    # Assert
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["email"] == user_data["email"]
    assert data.get("first_name") is None
    assert data.get("last_name") is None


# --- Test User Update with Name Fields ---


@pytest.mark.asyncio
async def test_update_user_name_fields(test_client: AsyncClient, db_session: AsyncSession):
    """Test admin can update user's first_name and last_name."""
    # Arrange
    admin = UserFactory.create_user(
        session=db_session,
        email="admin_update_name@example.com",
        role="admin",
        is_superuser=True,
    )
    target_user = UserFactory.create_user(
        session=db_session,
        email="target_update_name@example.com",
        role="standard",
    )
    await db_session.flush()
    target_user_id = target_user.id

    headers = await login_user(test_client, admin.email, "password123")

    # Act - Update name fields
    update_payload = {
        "first_name": "Jane",
        "last_name": "Smith",
    }
    response = await test_client.patch(
        f"{API_PREFIX}/admin/users/{target_user_id}",
        json=update_payload,
        headers=headers,
    )

    # Assert
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["first_name"] == "Jane"
    assert data["last_name"] == "Smith"

    # Verify in DB
    await db_session.refresh(target_user)
    assert target_user.first_name == "Jane"
    assert target_user.last_name == "Smith"


@pytest.mark.asyncio
async def test_update_user_clear_name_fields(test_client: AsyncClient, db_session: AsyncSession):
    """Test admin can clear user's name fields by setting to null."""
    # Arrange
    admin = UserFactory.create_user(
        session=db_session,
        email="admin_clear_name@example.com",
        role="admin",
        is_superuser=True,
    )
    target_user = UserFactory.create_user(
        session=db_session,
        email="target_clear_name@example.com",
        role="standard",
    )
    # Set initial name values directly on the model
    target_user.first_name = "OriginalFirst"
    target_user.last_name = "OriginalLast"
    await db_session.flush()
    target_user_id = target_user.id

    headers = await login_user(test_client, admin.email, "password123")

    # Act - Clear name fields
    update_payload = {
        "first_name": None,
        "last_name": None,
    }
    response = await test_client.patch(
        f"{API_PREFIX}/admin/users/{target_user_id}",
        json=update_payload,
        headers=headers,
    )

    # Assert
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["first_name"] is None
    assert data["last_name"] is None


# --- Test User Read with Name Fields ---


@pytest.mark.asyncio
async def test_get_user_includes_name_fields(test_client: AsyncClient, db_session: AsyncSession):
    """Test getting a user includes first_name and last_name."""
    # Arrange
    admin = UserFactory.create_user(
        session=db_session,
        email="admin_get_named@example.com",
        role="admin",
        is_superuser=True,
    )
    target_user = UserFactory.create_user(
        session=db_session,
        email="target_get_named@example.com",
        role="standard",
    )
    target_user.first_name = "ReadFirst"
    target_user.last_name = "ReadLast"
    await db_session.flush()
    target_user_id = target_user.id

    headers = await login_user(test_client, admin.email, "password123")

    # Act
    response = await test_client.get(
        f"{API_PREFIX}/admin/users/{target_user_id}",
        headers=headers,
    )

    # Assert
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["first_name"] == "ReadFirst"
    assert data["last_name"] == "ReadLast"


@pytest.mark.asyncio
async def test_list_users_includes_name_fields(test_client: AsyncClient, db_session: AsyncSession):
    """Test listing users includes first_name and last_name."""
    # Arrange
    admin = UserFactory.create_user(
        session=db_session,
        email="admin_list_named@example.com",
        role="admin",
        is_superuser=True,
    )
    user1 = UserFactory.create_user(
        session=db_session,
        email="user1_list_named@example.com",
    )
    user1.first_name = "User1First"
    user1.last_name = "User1Last"
    await db_session.flush()

    headers = await login_user(test_client, admin.email, "password123")

    # Act
    response = await test_client.get(f"{API_PREFIX}/admin/users", headers=headers)

    # Assert
    assert response.status_code == status.HTTP_200_OK
    user_list = response.json()
    user1_data = next((u for u in user_list if u["email"] == "user1_list_named@example.com"), None)
    assert user1_data is not None
    assert user1_data["first_name"] == "User1First"
    assert user1_data["last_name"] == "User1Last"


# --- Test Registration with Name Fields (when enabled) ---


@pytest.mark.asyncio
async def test_register_with_name_fields(test_client: AsyncClient, db_session: AsyncSession):
    """Test user registration includes name fields when open signup is enabled."""
    # Arrange - Enable open signup
    app_settings = await get_or_create_app_settings(db_session)
    app_settings.open_signup = True
    await db_session.flush()

    # Act
    register_data = {
        "email": "register_named@example.com",
        "password": "SecurePass123",
        "first_name": "RegisterFirst",
        "last_name": "RegisterLast",
    }
    response = await test_client.post(f"{API_PREFIX}/auth/register", json=register_data)

    # Assert
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["email"] == register_data["email"]
    assert data["first_name"] == "RegisterFirst"
    assert data["last_name"] == "RegisterLast"
