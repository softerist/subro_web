# backend/tests/auth/test_force_password_change.py

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

from ..factories import UserFactory

API_PREFIX = settings.API_V1_STR


@pytest.mark.asyncio
async def test_force_password_change_flag_returned_on_login(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that force_password_change is returned in /users/me response."""
    user_email = "force_pw_user@example.com"
    user_password = "Password123"
    _user = UserFactory.create_user(
        session=db_session,
        email=user_email,
        password=user_password,
        force_password_change=True,
    )
    await db_session.flush()

    # Login
    login_data = {"username": user_email, "password": user_password}
    login_response = await test_client.post(f"{API_PREFIX}/auth/login", data=login_data)
    assert login_response.status_code == status.HTTP_200_OK
    access_token = login_response.json()["access_token"]

    # Check /users/me returns force_password_change=True
    headers = {"Authorization": f"Bearer {access_token}"}
    me_response = await test_client.get(f"{API_PREFIX}/users/me", headers=headers)
    assert me_response.status_code == status.HTTP_200_OK
    assert me_response.json()["force_password_change"] is True


@pytest.mark.asyncio
async def test_password_change_clears_force_flag(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that changing password clears the force_password_change flag."""
    user_email = "clear_force_pw@example.com"
    user_password = "OldPassword123"
    new_password = "NewPassword456"
    _user = UserFactory.create_user(
        session=db_session,
        email=user_email,
        password=user_password,
        force_password_change=True,
    )
    await db_session.flush()

    # Login
    login_data = {"username": user_email, "password": user_password}
    login_response = await test_client.post(f"{API_PREFIX}/auth/login", data=login_data)
    assert login_response.status_code == status.HTTP_200_OK
    access_token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # Verify flag is True before change
    me_response = await test_client.get(f"{API_PREFIX}/users/me", headers=headers)
    assert me_response.json()["force_password_change"] is True

    # Change password
    change_response = await test_client.patch(
        f"{API_PREFIX}/auth/password",
        json={"current_password": user_password, "new_password": new_password},
        headers=headers,
    )
    assert change_response.status_code == status.HTTP_200_OK

    # Use new password to login and verify flag is now False
    login_data_new = {"username": user_email, "password": new_password}
    login_response_new = await test_client.post(f"{API_PREFIX}/auth/login", data=login_data_new)
    assert login_response_new.status_code == status.HTTP_200_OK
    new_access_token = login_response_new.json()["access_token"]
    headers_new = {"Authorization": f"Bearer {new_access_token}"}

    me_response_after = await test_client.get(f"{API_PREFIX}/users/me", headers=headers_new)
    assert me_response_after.status_code == status.HTTP_200_OK
    assert me_response_after.json()["force_password_change"] is False
