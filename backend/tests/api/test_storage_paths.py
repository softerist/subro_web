# backend/tests/api/test_storage_paths.py
"""Tests for storage path management and subdirectory restrictions."""

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.core.config import settings
from app.schemas.storage_path import StoragePathCreate

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
async def test_superuser_can_add_any_path(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that superuser can add any valid path."""
    # Arrange
    superuser = UserFactory.create_user(
        session=db_session,
        email="superuser_paths@example.com",
        role="admin",
        is_superuser=True,
    )
    await db_session.flush()

    headers = await login_user(test_client, superuser.email, "password123")

    # Act: Superuser adds a root path (using /tmp which exists in container)
    response = await test_client.post(
        f"{API_PREFIX}/storage-paths/",
        json={"path": "/tmp"},
        headers=headers,
    )

    # Assert
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["path"] == "/tmp"


@pytest.mark.asyncio
async def test_standard_user_cannot_add_root_path(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that standard user cannot add a new root path."""
    # Arrange
    user = UserFactory.create_user(
        session=db_session,
        email="standard_paths@example.com",
        role="standard",
        is_superuser=False,
    )
    await db_session.flush()

    headers = await login_user(test_client, user.email, "password123")

    # Act: Standard user tries to add a root path (no existing paths)
    response = await test_client.post(
        f"{API_PREFIX}/storage-paths/",
        json={"path": "/var"},
        headers=headers,
    )

    # Assert: Should be forbidden (no parent path exists)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "subdirectories" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_standard_user_can_add_subdirectory_of_existing_path(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that standard user can add subdirectory of an existing path."""
    # Arrange: First, create an existing root path in DB
    _existing_path = await crud.storage_path.create(
        db_session, obj_in=StoragePathCreate(path="/tmp")
    )
    await db_session.flush()

    user = UserFactory.create_user(
        session=db_session,
        email="standard_subdir@example.com",
        role="standard",
        is_superuser=False,
    )
    await db_session.flush()

    headers = await login_user(test_client, user.email, "password123")

    # Create a subdirectory physically (uses /tmp which should exist)
    from pathlib import Path as TestPath

    subdir_path = TestPath("/tmp/test_subdir_storage")
    subdir_path.mkdir(exist_ok=True)

    try:
        # Act: Standard user adds subdirectory
        response = await test_client.post(
            f"{API_PREFIX}/storage-paths/",
            json={"path": str(subdir_path)},
            headers=headers,
        )

        # Assert: Should succeed
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["path"] == str(subdir_path)
    finally:
        # Cleanup
        subdir_path.rmdir()


@pytest.mark.asyncio
async def test_admin_user_cannot_add_root_path(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that admin (non-superuser) cannot add a new root path."""
    # Arrange
    admin = UserFactory.create_user(
        session=db_session,
        email="admin_paths@example.com",
        role="admin",
        is_superuser=False,
    )
    await db_session.flush()

    headers = await login_user(test_client, admin.email, "password123")

    # Act: Admin tries to add a root path
    response = await test_client.post(
        f"{API_PREFIX}/storage-paths/",
        json={"path": "/opt"},
        headers=headers,
    )

    # Assert: Should be forbidden
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_any_user_can_list_paths(test_client: AsyncClient, db_session: AsyncSession) -> None:
    """Test that any authenticated user can list storage paths."""
    # Arrange
    user = UserFactory.create_user(
        session=db_session,
        email="list_paths_user@example.com",
        role="standard",
    )
    await db_session.flush()

    headers = await login_user(test_client, user.email, "password123")

    # Act
    response = await test_client.get(
        f"{API_PREFIX}/storage-paths/",
        headers=headers,
    )

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_only_superuser_can_delete_path(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that only superuser can delete a storage path."""
    # Arrange: Create a path
    path = await crud.storage_path.create(db_session, obj_in=StoragePathCreate(path="/tmp"))
    await db_session.flush()
    path_id = path.id

    # Create a non-superuser admin
    admin = UserFactory.create_user(
        session=db_session,
        email="admin_delete_path@example.com",
        role="admin",
        is_superuser=False,
    )
    await db_session.flush()

    headers = await login_user(test_client, admin.email, "password123")

    # Act: Admin tries to delete path
    response = await test_client.delete(
        f"{API_PREFIX}/storage-paths/{path_id}",
        headers=headers,
    )

    # Assert: Should be forbidden (requires superuser)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_user_can_update_path_label(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that any authenticated user can update the label of a storage path."""
    # Arrange: Create a path
    path = await crud.storage_path.create(
        db_session, obj_in=StoragePathCreate(path="/tmp", label="Old Label")
    )
    await db_session.flush()
    path_id = path.id

    # Create a standard user
    user = UserFactory.create_user(
        session=db_session,
        email="update_path_user@example.com",
        role="standard",
    )
    await db_session.flush()

    headers = await login_user(test_client, user.email, "password123")

    # Act: Update the label
    response = await test_client.patch(
        f"{API_PREFIX}/storage-paths/{path_id}",
        json={"label": "New Label", "path": "/tmp"},
        headers=headers,
    )

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["label"] == "New Label"
    assert response.json()["path"] == "/tmp"  # Should remain unchanged
