# backend/tests/api/test_admin.py
import uuid

import pytest
from fastapi import status
from httpx import AsyncClient  # Import ASGITransport is not needed here, but in conftest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User

from ..factories.user_factory import UserFactory  # Relative import


# FIX: Modify login_user to set cookies on the client and return only headers
async def login_user(client: AsyncClient, email: str, password: str) -> dict:  # Return only headers
    """Logs in a user, sets cookies on the client, and returns auth headers."""
    login_data = {"username": email, "password": password}
    response = await client.post("/api/auth/login", data=login_data)
    assert response.status_code == status.HTTP_200_OK, f"Login failed for {email}: {response.text}"
    token = response.json()["access_token"]

    # Cookies are now implicitly set on the client instance by httpx after the response
    # No need to extract or pass them separately if we reuse the SAME client instance

    headers = {"Authorization": f"Bearer {token}"}
    return headers  # Only return headers


# --- Tests for Admin User Management ---


@pytest.mark.asyncio
async def test_list_users_as_admin(test_client: AsyncClient, db_session: AsyncSession):
    """Test listing users successfully as an admin."""
    # Arrange: Create an admin user and some standard users
    admin = UserFactory.create_user(
        session=db_session, email="admin_list@example.com", role="admin", is_superuser=True
    )
    user1 = UserFactory.create_user(session=db_session, email="user1_list@example.com")
    user2 = UserFactory.create_user(session=db_session, email="user2_list@example.com")
    await db_session.flush()  # Ensure users have IDs before login

    headers = await login_user(
        test_client, admin.email, "password123"
    )  # Get headers, cookies are on test_client

    # Act
    # FIX: Remove cookies parameter
    response = await test_client.get("/api/admin/users", headers=headers)

    # Assert
    assert response.status_code == status.HTTP_200_OK  # Expect 200 OK for list
    user_list = response.json()
    assert isinstance(user_list, list)
    # Check count carefully - depends if other tests left users (shouldn't with proper isolation)
    # Let's check presence instead of exact count initially
    emails_in_response = {u["email"] for u in user_list}
    assert admin.email in emails_in_response
    assert user1.email in emails_in_response
    assert user2.email in emails_in_response
    assert len(user_list) >= 3  # Check at least the created users are present


@pytest.mark.asyncio
async def test_list_users_as_standard_user(test_client: AsyncClient, db_session: AsyncSession):
    """Test standard user cannot list users."""
    # Arrange: Create a standard user
    user = UserFactory.create_user(session=db_session, email="standard_cant_list@example.com")
    await db_session.flush()

    headers = await login_user(test_client, user.email, "password123")

    # Act
    # FIX: Remove cookies parameter
    response = await test_client.get("/api/admin/users", headers=headers)

    # Assert
    # Check the error code provided by fastapi-users for forbidden access
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_list_users_unauthenticated(test_client: AsyncClient):
    """Test unauthenticated user cannot list users."""
    response = await test_client.get("/api/admin/users")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_specific_user_as_admin(test_client: AsyncClient, db_session: AsyncSession):
    """Test admin can get details of a specific user."""
    # Arrange
    admin = UserFactory.create_user(
        session=db_session, email="admin_get@example.com", role="admin", is_superuser=True
    )
    target_user = UserFactory.create_user(session=db_session, email="target_get@example.com")
    await db_session.flush()
    target_user_id = target_user.id  # Get ID after flush

    headers = await login_user(test_client, admin.email, "password123")

    # Act
    # FIX: Remove cookies parameter
    response = await test_client.get(f"/api/admin/users/{target_user_id}", headers=headers)

    # Assert
    assert response.status_code == status.HTTP_200_OK
    user_data = response.json()
    assert user_data["email"] == target_user.email
    assert user_data["id"] == str(target_user_id)


@pytest.mark.asyncio
async def test_get_specific_user_not_found_admin(
    test_client: AsyncClient, db_session: AsyncSession
):
    """Test getting a non-existent user returns 404."""
    # Arrange
    admin = UserFactory.create_user(
        session=db_session, email="admin_get_404@example.com", role="admin", is_superuser=True
    )
    await db_session.flush()

    headers = await login_user(test_client, admin.email, "password123")
    non_existent_uuid = uuid.uuid4()

    # Act
    # FIX: Remove cookies parameter
    response = await test_client.get(f"/api/admin/users/{non_existent_uuid}", headers=headers)

    # Assert
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_update_user_role_as_admin(test_client: AsyncClient, db_session: AsyncSession):
    """Test admin can update another user's role and is_superuser syncs."""
    # Arrange
    admin = UserFactory.create_user(
        session=db_session, email="admin_update@example.com", role="admin", is_superuser=True
    )
    target_user = UserFactory.create_user(
        session=db_session, email="target_update@example.com", role="standard"
    )
    await db_session.flush()
    target_user_id = target_user.id

    # Verify initial state
    assert target_user.role == "standard"
    assert target_user.is_superuser is False

    headers = await login_user(test_client, admin.email, "password123")
    update_payload = {"role": "admin"}  # Payload using AdminUserUpdate schema field

    # Act
    # FIX: Remove cookies parameter
    response = await test_client.patch(
        f"/api/admin/users/{target_user_id}", json=update_payload, headers=headers
    )

    # Assert response
    assert response.status_code == status.HTTP_200_OK
    updated_user_data = response.json()
    assert updated_user_data["email"] == target_user.email
    assert updated_user_data["role"] == "admin"  # Role should be updated
    assert updated_user_data["is_superuser"] is True  # is_superuser should sync based on API logic

    # Verify in DB (refresh object after API call committed)
    await db_session.refresh(target_user)
    assert target_user.role == "admin"
    assert target_user.is_superuser is True


@pytest.mark.asyncio
async def test_update_user_is_active_as_admin(test_client: AsyncClient, db_session: AsyncSession):
    """Test admin can update another user's active status."""
    # Arrange
    admin = UserFactory.create_user(
        session=db_session, email="admin_activate@example.com", role="admin", is_superuser=True
    )
    target_user = UserFactory.create_user(
        session=db_session, email="target_activate@example.com", is_active=True
    )
    await db_session.flush()
    target_user_id = target_user.id

    headers = await login_user(test_client, admin.email, "password123")
    update_payload = {"is_active": False}

    # Act
    # FIX: Remove cookies parameter
    response = await test_client.patch(
        f"/api/admin/users/{target_user_id}", json=update_payload, headers=headers
    )

    # Assert response
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["is_active"] is False

    # Verify in DB
    await db_session.refresh(target_user)
    assert target_user.is_active is False


@pytest.mark.asyncio
async def test_update_user_as_standard_user(test_client: AsyncClient, db_session: AsyncSession):
    """Test standard user cannot use admin update endpoint."""
    # Arrange
    user = UserFactory.create_user(session=db_session, email="standard_cant_update@example.com")
    target_user = UserFactory.create_user(
        session=db_session, email="target_by_standard@example.com"
    )
    await db_session.flush()
    target_user_id = target_user.id

    headers = await login_user(test_client, user.email, "password123")
    update_payload = {"role": "admin"}

    # Act
    # FIX: Remove cookies parameter
    response = await test_client.patch(
        f"/api/admin/users/{target_user_id}", json=update_payload, headers=headers
    )

    # Assert
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_delete_user_as_admin(test_client: AsyncClient, db_session: AsyncSession):
    """Test admin can delete a user."""
    # Arrange
    admin = UserFactory.create_user(
        session=db_session, email="admin_delete@example.com", role="admin", is_superuser=True
    )
    target_user = UserFactory.create_user(session=db_session, email="target_delete@example.com")
    await db_session.flush()
    target_user_id = target_user.id  # Store ID after flush

    headers = await login_user(test_client, admin.email, "password123")

    # Act
    response = await test_client.delete(f"/api/admin/users/{target_user_id}", headers=headers)

    # Assert
    assert response.status_code == status.HTTP_204_NO_CONTENT  # Expect 204 No Content

    # Verify user is gone from DB
    # Need to expire/refresh session state or query again
    # FIX: Remove await from expire_all() as it's not a coroutine
    db_session.expire_all()
    # The .get() method IS awaitable
    user_in_db = await db_session.get(User, target_user_id)
    assert user_in_db is None


@pytest.mark.asyncio
async def test_delete_user_as_standard_user(test_client: AsyncClient, db_session: AsyncSession):
    """Test standard user cannot delete users."""
    # Arrange
    user = UserFactory.create_user(session=db_session, email="standard_cant_delete@example.com")
    target_user = UserFactory.create_user(
        session=db_session, email="target_by_standard_del@example.com"
    )
    await db_session.flush()
    target_user_id = target_user.id

    headers = await login_user(test_client, user.email, "password123")

    # Act
    # FIX: Remove cookies parameter
    response = await test_client.delete(f"/api/admin/users/{target_user_id}", headers=headers)

    # Assert
    assert response.status_code == status.HTTP_403_FORBIDDEN
