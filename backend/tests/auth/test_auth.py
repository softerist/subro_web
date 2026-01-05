# backend/tests/auth/test_auth.py

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.security import cookie_transport
from app.db.models.user import User

from ..factories import UserFactory

API_PREFIX = settings.API_V1_STR


@pytest.mark.asyncio
async def test_register_user(test_client: AsyncClient, db_session: AsyncSession):
    # Registration doesn't use the factory, so this remains the same
    if not settings.OPEN_SIGNUP:
        pytest.skip("Skipping registration test because OPEN_SIGNUP is False")

    register_data = {"email": "registertest@example.com", "password": "Password123"}
    response = await test_client.post(f"{API_PREFIX}/auth/register", json=register_data)

    assert response.status_code == status.HTTP_201_CREATED
    # ... rest of assertions ...
    user_data = response.json()
    assert user_data["email"] == register_data["email"]
    assert user_data["is_active"] is True
    assert user_data.get("role", "standard") == "standard"
    assert "id" in user_data

    result = await db_session.execute(select(User).where(User.email == register_data["email"]))
    user_in_db = result.scalars().first()
    assert user_in_db is not None


@pytest.mark.asyncio
async def test_register_user_already_exists(test_client: AsyncClient, db_session: AsyncSession):
    if not settings.OPEN_SIGNUP:
        pytest.skip("Skipping registration test because OPEN_SIGNUP is False")

    existing_email = "existing@example.com"
    # Use the factory's create_user method, passing the session
    # No await needed for the factory method itself
    UserFactory.create_user(session=db_session, email=existing_email, password="Password123")
    await db_session.flush()  # Ensure user is flushed to session

    register_data = {"email": existing_email, "password": "AnotherPass123"}
    response = await test_client.post(f"{API_PREFIX}/auth/register", json=register_data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "REGISTER_USER_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_login_success(test_client: AsyncClient, db_session: AsyncSession):
    user_email = "logintest@example.com"
    user_password = "Password123"
    # Use factory's create_user, passing session and password
    UserFactory.create_user(session=db_session, email=user_email, password=user_password)
    await db_session.flush()  # Ensure user is flushed

    login_data = {"username": user_email, "password": user_password}
    response = await test_client.post(f"{API_PREFIX}/auth/login", data=login_data)

    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.json()
    assert "token_type" in response.json()
    assert response.json()["token_type"] == "bearer"
    assert "subRefreshToken" in response.cookies
    assert response.cookies["subRefreshToken"]


@pytest.mark.asyncio
async def test_login_failure_wrong_password(test_client: AsyncClient, db_session: AsyncSession):
    user_email = "wrongpass@example.com"
    # Use factory's create_user, passing session and correct password
    UserFactory.create_user(session=db_session, email=user_email, password="CorrectPass123")
    await db_session.flush()  # Ensure user is flushed

    login_data = {"username": user_email, "password": "WrongPass123"}
    response = await test_client.post(f"{API_PREFIX}/auth/login", data=login_data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "LOGIN_BAD_CREDENTIALS"
    assert "subRefreshToken" not in response.cookies


@pytest.mark.asyncio
async def test_login_failure_user_not_found(test_client: AsyncClient):
    """Test login failure for a non-existent user."""
    # No user creation needed here
    login_data = {"username": "nosuchuser@example.com", "password": "Password123"}
    response = await test_client.post(f"{API_PREFIX}/auth/login", data=login_data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    # Keep the assertion for LOGIN_BAD_CREDENTIALS as refined in auth.py
    assert response.json()["detail"] == "LOGIN_BAD_CREDENTIALS"
    assert "subRefreshToken" not in response.cookies


@pytest.mark.asyncio
async def test_login_failure_inactive_user(test_client: AsyncClient, db_session: AsyncSession):
    """Test login failure for an inactive user."""
    user_email = "inactive@example.com"
    user_password = "Password123"
    # Use factory's create_user, passing session, password, and is_active=False
    UserFactory.create_user(
        session=db_session, email=user_email, password=user_password, is_active=False
    )
    await db_session.flush()  # Ensure user is flushed

    login_data = {"username": user_email, "password": user_password}
    response = await test_client.post(f"{API_PREFIX}/auth/login", data=login_data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "LOGIN_BAD_CREDENTIALS"
    assert "subRefreshToken" not in response.cookies


@pytest.mark.asyncio
async def test_get_current_user(test_client: AsyncClient, db_session: AsyncSession):
    user_email = "me_user@example.com"
    user_password = "Password123"
    # Use factory's create_user, passing session and password
    user = UserFactory.create_user(session=db_session, email=user_email, password=user_password)
    await db_session.flush()  # Ensure user is flushed

    login_data = {"username": user_email, "password": user_password}
    login_response = await test_client.post(f"{API_PREFIX}/auth/login", data=login_data)
    assert login_response.status_code == status.HTTP_200_OK
    access_token = login_response.json()["access_token"]

    headers = {"Authorization": f"Bearer {access_token}"}
    me_response = await test_client.get(f"{API_PREFIX}/users/me", headers=headers)

    assert me_response.status_code == status.HTTP_200_OK
    user_data = me_response.json()
    assert user_data["email"] == user_email
    # Ensure the user object from factory has ID after flush if needed for comparison
    assert user_data["id"] == str(user.id)
    assert user_data.get("role", "standard") == "standard"


@pytest.mark.asyncio
async def test_get_current_user_unauthenticated(test_client: AsyncClient):
    # Remains the same
    response = await test_client.get(f"{API_PREFIX}/users/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Unauthorized"


@pytest.mark.asyncio
async def test_refresh_token(test_client: AsyncClient, db_session: AsyncSession):
    user_email = "refresh_user@example.com"
    user_password = "Password123"
    # Use factory's create_user, passing session and password
    _user = UserFactory.create_user(session=db_session, email=user_email, password=user_password)
    await db_session.flush()  # Ensure user is flushed

    login_data = {"username": user_email, "password": user_password}
    login_response = await test_client.post(f"{API_PREFIX}/auth/login", data=login_data)
    assert login_response.status_code == status.HTTP_200_OK
    _original_access_token = login_response.json()["access_token"]
    refresh_cookie_value = login_response.cookies.get("subRefreshToken")
    assert refresh_cookie_value

    # FIX: Set cookie on the client instead of passing in the request
    test_client.cookies.set("subRefreshToken", refresh_cookie_value)

    # Make the request without the cookies parameter
    refresh_response = await test_client.post(f"{API_PREFIX}/auth/refresh")

    # Assert refresh was successful
    assert refresh_response.status_code == status.HTTP_200_OK
    new_token_data = refresh_response.json()
    assert "access_token" in new_token_data
    assert "token_type" in new_token_data
    assert new_token_data["token_type"] == "bearer"

    # Assert the refresh *token* value changed
    new_refresh_cookie = refresh_response.cookies.get("subRefreshToken")
    assert new_refresh_cookie
    assert new_refresh_cookie != refresh_cookie_value

    # Assert the new access token works
    headers = {"Authorization": f"Bearer {new_token_data['access_token']}"}
    me_response = await test_client.get(f"{API_PREFIX}/users/me", headers=headers)
    assert me_response.status_code == status.HTTP_200_OK
    assert me_response.json()["email"] == user_email


@pytest.mark.asyncio
async def test_refresh_token_no_cookie(test_client: AsyncClient):
    # Remains the same
    response = await test_client.post(f"{API_PREFIX}/auth/refresh")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "REFRESH_TOKEN_MISSING"


@pytest.mark.asyncio
async def test_refresh_token_invalid_cookie(test_client: AsyncClient):
    # FIX: Set cookie on the client instead of passing in the request
    test_client.cookies.set("subRefreshToken", "invalid-token-value")

    # Make the request without the cookies parameter
    response = await test_client.post(f"{API_PREFIX}/auth/refresh")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "REFRESH_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_logout(test_client: AsyncClient, db_session: AsyncSession):
    user_email = "logout_user@example.com"
    user_password = "Password123"
    UserFactory.create_user(session=db_session, email=user_email, password=user_password)
    await db_session.flush()

    login_data = {"username": user_email, "password": user_password}
    login_response = await test_client.post(f"{API_PREFIX}/auth/login", data=login_data)
    assert login_response.status_code == status.HTTP_200_OK
    refresh_cookie_value = login_response.cookies.get(cookie_transport.cookie_name)
    assert refresh_cookie_value

    access_token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # FIX: Set cookie on the client instead of passing in the request
    test_client.cookies.set(cookie_transport.cookie_name, refresh_cookie_value)

    # Call logout with headers
    logout_response = await test_client.post(f"{API_PREFIX}/auth/logout", headers=headers)

    # Assert logout was successful and cookie deletion header was sent
    assert logout_response.status_code == status.HTTP_200_OK
    assert logout_response.json() == {"message": "LOGOUT_SUCCESSFUL"}
    set_cookie_header = logout_response.headers.get("set-cookie")
    assert set_cookie_header is not None
    # Check if the header tries to clear the cookie
    assert (
        f"{cookie_transport.cookie_name}=;" in set_cookie_header or "Max-Age=0" in set_cookie_header
    )

    # Test refresh behavior after logout
    # Clear client cookies to simulate browser clearing cookies
    test_client.cookies.clear()

    # Now make the refresh request. The client should send no cookies.
    refresh_response_no_cookie = await test_client.post(f"{API_PREFIX}/auth/refresh")

    # Assert that the request without a cookie fails as expected
    assert refresh_response_no_cookie.status_code == status.HTTP_401_UNAUTHORIZED
    assert refresh_response_no_cookie.json()["detail"] == "REFRESH_TOKEN_MISSING"
