# backend/tests/api/test_admin_mfa_reset.py
"""Tests for admin MFA reset and password management functionality."""

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import encrypt_value

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
async def test_admin_can_disable_mfa_for_user(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that admin can disable MFA for a user by setting mfa_enabled=False."""
    # Arrange: Create admin and target user with MFA enabled
    admin = UserFactory.create_user(
        session=db_session,
        email="admin_mfa_reset@example.com",
        role="admin",
        is_superuser=True,
    )
    # Create user with MFA "enabled" (simulated with mfa_secret set and flag)
    target_user = UserFactory.create_user(
        session=db_session,
        email="mfa_user@example.com",
    )
    # Simulate MFA being enabled by setting encrypted secret AND the flag
    target_user.mfa_enabled = True
    target_user.mfa_secret = encrypt_value("TESTSECRET123456")
    target_user.mfa_backup_codes = encrypt_value("code1,code2,code3")
    await db_session.flush()
    target_user_id = target_user.id

    # Verify MFA is "enabled" initially
    assert target_user.mfa_secret is not None
    assert target_user.mfa_backup_codes is not None

    headers = await login_user(test_client, admin.email, "password123")

    # Act: Admin disables MFA
    update_payload = {"mfa_enabled": False}
    response = await test_client.patch(
        f"{API_PREFIX}/admin/users/{target_user_id}",
        json=update_payload,
        headers=headers,
    )

    # Assert: Request succeeded
    assert response.status_code == status.HTTP_200_OK

    # Verify MFA secrets are cleared in DB
    await db_session.refresh(target_user)
    assert target_user.mfa_secret is None
    assert target_user.mfa_backup_codes is None


@pytest.mark.asyncio
async def test_admin_can_force_password_change_via_update(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that admin can set force_password_change=True for a user."""
    # Arrange
    admin = UserFactory.create_user(
        session=db_session,
        email="admin_force_pw@example.com",
        role="admin",
        is_superuser=True,
    )
    target_user = UserFactory.create_user(
        session=db_session,
        email="target_force_pw@example.com",
        force_password_change=False,
    )
    await db_session.flush()
    target_user_id = target_user.id

    headers = await login_user(test_client, admin.email, "password123")

    # Act: Admin forces password change
    update_payload = {"force_password_change": True}
    response = await test_client.patch(
        f"{API_PREFIX}/admin/users/{target_user_id}",
        json=update_payload,
        headers=headers,
    )

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["force_password_change"] is True

    await db_session.refresh(target_user)
    assert target_user.force_password_change is True


@pytest.mark.asyncio
async def test_admin_can_reset_password_for_user(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that admin can reset another user's password."""
    # Arrange
    admin = UserFactory.create_user(
        session=db_session,
        email="admin_reset_pw@example.com",
        role="admin",
        is_superuser=True,
    )
    target_user = UserFactory.create_user(
        session=db_session,
        email="target_reset_pw@example.com",
    )
    await db_session.flush()
    target_user_id = target_user.id

    headers = await login_user(test_client, admin.email, "password123")

    # Act: Admin resets password
    new_password = "NewSecurePassword123"
    update_payload = {"password": new_password}
    response = await test_client.patch(
        f"{API_PREFIX}/admin/users/{target_user_id}",
        json=update_payload,
        headers=headers,
    )

    # Assert: Request succeeded
    assert response.status_code == status.HTTP_200_OK

    # Verify: Target user can login with new password
    login_data = {"username": target_user.email, "password": new_password}
    login_response = await test_client.post(f"{API_PREFIX}/auth/login", data=login_data)
    assert login_response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_admin_cannot_modify_superuser(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that a non-superuser admin cannot modify a superuser."""
    # Arrange: Create a regular admin (not superuser) and a target superuser
    admin = UserFactory.create_user(
        session=db_session,
        email="regular_admin@example.com",
        role="admin",
        is_superuser=False,  # Regular admin, not superuser
    )
    superuser_target = UserFactory.create_user(
        session=db_session,
        email="superuser_target@example.com",
        role="admin",
        is_superuser=True,
    )
    await db_session.flush()
    target_id = superuser_target.id

    headers = await login_user(test_client, admin.email, "password123")

    # Act: Regular admin tries to modify superuser
    update_payload = {"is_active": False}
    response = await test_client.patch(
        f"{API_PREFIX}/admin/users/{target_id}",
        json=update_payload,
        headers=headers,
    )

    # Assert: Should be forbidden
    assert response.status_code == status.HTTP_403_FORBIDDEN
