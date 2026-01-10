# backend/tests/api/test_translation_stats.py
"""Tests for translation statistics access control."""

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

from ..factories.user_factory import UserFactory

API_PREFIX = settings.API_V1_STR


async def login_user(client: AsyncClient, email: str, password: str) -> dict:
    """Logs in a user and returns auth headers."""
    login_data = {"username": email, "password": password}
    response = await client.post(f"{API_PREFIX}/auth/login", data=login_data)
    assert response.status_code == status.HTTP_200_OK, f"Login failed for {email}: {response.text}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_standard_user_can_access_translation_stats(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that standard users can access translation statistics."""
    # Arrange
    user = UserFactory.create_user(
        session=db_session,
        email="standard_stats@example.com",
        role="standard",
        is_superuser=False,
    )
    await db_session.flush()

    headers = await login_user(test_client, user.email, "password123")

    # Act
    response = await test_client.get(
        f"{API_PREFIX}/translation-stats",
        headers=headers,
    )

    # Assert
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "all_time" in data
    assert "last_30_days" in data
    assert "last_7_days" in data


@pytest.mark.asyncio
async def test_admin_user_can_access_translation_stats(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that admin users can access translation statistics."""
    # Arrange
    admin = UserFactory.create_user(
        session=db_session,
        email="admin_stats@example.com",
        role="admin",
        is_superuser=True,
    )
    await db_session.flush()

    headers = await login_user(test_client, admin.email, "password123")

    # Act
    response = await test_client.get(
        f"{API_PREFIX}/translation-stats",
        headers=headers,
    )

    # Assert
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_unauthenticated_cannot_access_translation_stats(
    test_client: AsyncClient,
) -> None:
    """Test that unauthenticated users cannot access translation statistics."""
    # Act
    response = await test_client.get(f"{API_PREFIX}/translation-stats")

    # Assert
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_standard_user_can_access_translation_history(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that standard users can access translation history."""
    # Arrange
    user = UserFactory.create_user(
        session=db_session,
        email="standard_history@example.com",
        role="standard",
        is_superuser=False,
    )
    await db_session.flush()

    headers = await login_user(test_client, user.email, "password123")

    # Act
    response = await test_client.get(
        f"{API_PREFIX}/translation-stats/history",
        headers=headers,
    )

    # Assert
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data


@pytest.mark.asyncio
async def test_translation_stats_response_format(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that translation stats response has correct format."""
    # Arrange
    user = UserFactory.create_user(
        session=db_session,
        email="stats_format@example.com",
    )
    await db_session.flush()

    headers = await login_user(test_client, user.email, "password123")

    # Act
    response = await test_client.get(
        f"{API_PREFIX}/translation-stats",
        headers=headers,
    )

    # Assert
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Verify structure of each time period
    for period in ["all_time", "last_30_days", "last_7_days"]:
        assert period in data
        period_data = data[period]
        assert "total_translations" in period_data
        assert "total_characters" in period_data
        assert "deepl_characters" in period_data
        assert "google_characters" in period_data
        assert "success_count" in period_data
        assert "failure_count" in period_data
