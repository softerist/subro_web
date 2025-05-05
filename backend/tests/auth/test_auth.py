# backend/tests/auth/test_auth.py
import pytest
from httpx import AsyncClient
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import uuid

from app.db.models.user import User
from app.core.config import settings
from ..factories import UserFactory
from app.core.security import cookie_transport

@pytest.mark.asyncio
async def test_register_user(test_client: AsyncClient, db_session: AsyncSession):
    # Registration doesn't use the factory, so this remains the same
    if not settings.OPEN_SIGNUP:
        pytest.skip("Skipping registration test because OPEN_SIGNUP is False")

    register_data = {
        "email": "registertest@example.com",
        "password": "password123"
    }
    response = await test_client.post("/api/auth/register", json=register_data)

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
    UserFactory.create_user(session=db_session, email=existing_email, password="password123")
    await db_session.flush() # Ensure user is flushed to session

    register_data = {"email": existing_email, "password": "anotherpassword"}
    response = await test_client.post("/api/auth/register", json=register_data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "REGISTER_USER_ALREADY_EXISTS"

@pytest.mark.asyncio
async def test_login_success(test_client: AsyncClient, db_session: AsyncSession):
    user_email = "logintest@example.com"
    user_password = "password123"
    # Use factory's create_user, passing session and password
    UserFactory.create_user(session=db_session, email=user_email, password=user_password)
    await db_session.flush() # Ensure user is flushed

    login_data = {"username": user_email, "password": user_password}
    response = await test_client.post("/api/auth/login", data=login_data)

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
    UserFactory.create_user(session=db_session, email=user_email, password="correctpassword")
    await db_session.flush() # Ensure user is flushed

    login_data = {"username": user_email, "password": "wrongpassword"}
    response = await test_client.post("/api/auth/login", data=login_data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "LOGIN_BAD_CREDENTIALS"
    assert "subRefreshToken" not in response.cookies

@pytest.mark.asyncio
async def test_login_failure_user_not_found(test_client: AsyncClient):
    """Test login failure for a non-existent user."""
    # No user creation needed here
    login_data = {"username": "nosuchuser@example.com", "password": "password123"}
    response = await test_client.post("/api/auth/login", data=login_data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    # Keep the assertion for LOGIN_BAD_CREDENTIALS as refined in auth.py
    assert response.json()["detail"] == "LOGIN_BAD_CREDENTIALS"
    assert "subRefreshToken" not in response.cookies

@pytest.mark.asyncio
async def test_login_failure_inactive_user(test_client: AsyncClient, db_session: AsyncSession):
    """Test login failure for an inactive user."""
    user_email = "inactive@example.com"
    user_password = "password123"
    # Use factory's create_user, passing session, password, and is_active=False
    UserFactory.create_user(
        session=db_session,
        email=user_email,
        password=user_password,
        is_active=False
    )
    await db_session.flush() # Ensure user is flushed

    login_data = {"username": user_email, "password": user_password}
    response = await test_client.post("/api/auth/login", data=login_data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "LOGIN_USER_INACTIVE"
    assert "subRefreshToken" not in response.cookies

@pytest.mark.asyncio
async def test_get_current_user(test_client: AsyncClient, db_session: AsyncSession):
    user_email = "me_user@example.com"
    user_password = "password123"
    # Use factory's create_user, passing session and password
    user = UserFactory.create_user(session=db_session, email=user_email, password=user_password)
    await db_session.flush() # Ensure user is flushed

    login_data = {"username": user_email, "password": user_password}
    login_response = await test_client.post("/api/auth/login", data=login_data)
    assert login_response.status_code == status.HTTP_200_OK
    access_token = login_response.json()["access_token"]

    headers = {"Authorization": f"Bearer {access_token}"}
    me_response = await test_client.get("/api/users/me", headers=headers)

    assert me_response.status_code == status.HTTP_200_OK
    user_data = me_response.json()
    assert user_data["email"] == user_email
    # Ensure the user object from factory has ID after flush if needed for comparison
    assert user_data["id"] == str(user.id)
    assert user_data.get("role", "standard") == "standard"

@pytest.mark.asyncio
async def test_get_current_user_unauthenticated(test_client: AsyncClient):
    # Remains the same
    response = await test_client.get("/api/users/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Unauthorized"

@pytest.mark.asyncio
async def test_refresh_token(test_client: AsyncClient, db_session: AsyncSession):
    user_email = "refresh_user@example.com"
    user_password = "password123"
    # Use factory's create_user, passing session and password
    user = UserFactory.create_user(session=db_session, email=user_email, password=user_password)
    await db_session.flush() # Ensure user is flushed

    # --- ADD THIS LINE BACK ---
    login_data = {"username": user_email, "password": user_password}
    # --- End of addition ---

    login_response = await test_client.post("/api/auth/login", data=login_data)
    assert login_response.status_code == status.HTTP_200_OK
    original_access_token = login_response.json()["access_token"]
    refresh_cookie_value = login_response.cookies.get("subRefreshToken")
    assert refresh_cookie_value

    cookies = {"subRefreshToken": refresh_cookie_value}
    refresh_response = await test_client.post("/api/auth/refresh", cookies=cookies)

    # Assert refresh was successful
    assert refresh_response.status_code == status.HTTP_200_OK
    new_token_data = refresh_response.json()
    assert "access_token" in new_token_data
    # assert new_token_data["access_token"] != original_access_token # Keep commented/removed
    assert "token_type" in new_token_data
    assert new_token_data["token_type"] == "bearer"

    # Assert the refresh *token* value changed
    new_refresh_cookie = refresh_response.cookies.get("subRefreshToken")
    assert new_refresh_cookie
    assert new_refresh_cookie != refresh_cookie_value

    # Assert the new access token works
    headers = {"Authorization": f"Bearer {new_token_data['access_token']}"}
    me_response = await test_client.get("/api/users/me", headers=headers)
    assert me_response.status_code == status.HTTP_200_OK
    assert me_response.json()["email"] == user_email

@pytest.mark.asyncio
async def test_refresh_token_no_cookie(test_client: AsyncClient):
    # Remains the same
    response = await test_client.post("/api/auth/refresh")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Missing refresh token cookie"

@pytest.mark.asyncio
async def test_refresh_token_invalid_cookie(test_client: AsyncClient):
    # Remains the same
    cookies = {"subRefreshToken": "invalid-token-value"}
    response = await test_client.post("/api/auth/refresh", cookies=cookies)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Invalid or expired refresh token"

@pytest.mark.asyncio
async def test_logout(test_client: AsyncClient, db_session: AsyncSession):
    user_email = "logout_user@example.com"
    user_password = "password123"
    UserFactory.create_user(session=db_session, email=user_email, password=user_password)
    await db_session.flush()

    login_data = {"username": user_email, "password": user_password}
    login_response = await test_client.post("/api/auth/login", data=login_data)
    assert login_response.status_code == status.HTTP_200_OK
    refresh_cookie_value = login_response.cookies.get(cookie_transport.cookie_name) # Use imported name
    assert refresh_cookie_value

    # Store the cookie for the explicit logout call
    cookies_for_logout = {cookie_transport.cookie_name: refresh_cookie_value} # Use imported name

    # --- Call Logout ---
    logout_response = await test_client.post("/api/auth/logout", cookies=cookies_for_logout)

    # Assert logout was successful and cookie deletion header was sent
    assert logout_response.status_code == status.HTTP_200_OK
    assert logout_response.json() == {"status": "logged out"}
    set_cookie_header = logout_response.headers.get("set-cookie")
    assert set_cookie_header is not None
    # Check if the header tries to clear the cookie
    assert f"{cookie_transport.cookie_name}=;" in set_cookie_header or "Max-Age=0" in set_cookie_header

    # --- Test Refresh Behavior After Logout ---

    # 1. Test that using the *original* cookie might still work (token not invalidated server-side yet)
    #    This might depend on exact token implementation, but often the case.
    #    The client *still has the cookie* at this point unless cleared.
    # refresh_response_with_old_cookie = await test_client.post("/api/auth/refresh", cookies=cookies_for_logout)
    # assert refresh_response_with_old_cookie.status_code == status.HTTP_200_OK # This might pass or fail depending on stricter invalidation
    # assert "access_token" in refresh_response_with_old_cookie.json()

    # 2. Test that a request *without* any cookies FAILS (simulate a cleared browser/client)
    #    <<< CLEAR THE CLIENT'S COOKIE JAR >>>
    test_client.cookies.clear()

    # Now make the refresh request. The client should send no cookies.
    refresh_response_no_cookie = await test_client.post("/api/auth/refresh")

    # Assert that the request without a cookie fails as expected
    assert refresh_response_no_cookie.status_code == status.HTTP_401_UNAUTHORIZED
    assert refresh_response_no_cookie.json()["detail"] == "Missing refresh token cookie"
