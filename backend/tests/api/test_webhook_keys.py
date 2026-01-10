"""Tests for webhook key management endpoints."""

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.users import get_current_active_admin_user
from app.db.models.user import User

from ..factories.user_factory import UserFactory

API_PREFIX = settings.API_V1_STR


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create an admin user for management operations."""
    admin = UserFactory.create_user(
        session=db_session,
        email="admin_keys@example.com",
        is_superuser=True,
    )
    await db_session.flush()
    return admin


@pytest.fixture
def admin_token(admin_user: User) -> str:  # noqa: ARG001
    """Generate a JWT token for the admin user."""
    # In a real test, we would use the login endpoint, but here we can mock or use internal tools
    # For simplicity, we'll assume the test_client handles auth or we use a helper
    return "mock-token"  # This will be overridden by dependency injection in test_client


@pytest.mark.asyncio
async def test_generate_webhook_key(
    test_client: AsyncClient,
    admin_user: User,
) -> None:
    """Test generating a new webhook key."""
    # We need to be logged in as admin
    # The test_client fixture in conftest doesn't help with login state by default
    # But we can use dependency_overrides or a custom header
    from app.main import app

    app.dependency_overrides[get_current_active_admin_user] = lambda: admin_user

    try:
        response = await test_client.post(f"{API_PREFIX}/settings/webhook-key")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "raw_key" in data
        assert data["name"] == "qBittorrent Webhook"
        assert data["is_active"] is True
        assert "preview" in data
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_webhook_key_status(
    test_client: AsyncClient,
    admin_user: User,
) -> None:
    """Test getting webhook key status."""
    from app.main import app

    app.dependency_overrides[get_current_active_admin_user] = lambda: admin_user

    try:
        # 1. Check with no key
        response = await test_client.get(f"{API_PREFIX}/settings/webhook-key/status")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["configured"] is False

        # 2. Generate a key
        await test_client.post(f"{API_PREFIX}/settings/webhook-key")

        # 3. Check again
        response = await test_client.get(f"{API_PREFIX}/settings/webhook-key/status")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["configured"] is True
        assert response.json()["preview"] is not None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_revoke_webhook_key(
    test_client: AsyncClient,
    admin_user: User,
) -> None:
    """Test revoking a webhook key."""
    from app.main import app

    app.dependency_overrides[get_current_active_admin_user] = lambda: admin_user

    try:
        # Generate
        await test_client.post(f"{API_PREFIX}/settings/webhook-key")

        # Revoke
        response = await test_client.delete(f"{API_PREFIX}/settings/webhook-key")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["revoked"] is True

        # Check status
        response = await test_client.get(f"{API_PREFIX}/settings/webhook-key/status")
        assert response.json()["configured"] is False
    finally:
        app.dependency_overrides.clear()
