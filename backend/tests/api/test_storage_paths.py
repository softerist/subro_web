# backend/tests/api/test_storage_paths.py
"""Tests for storage path management and subdirectory restrictions."""

import os
from pathlib import Path

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
async def test_superuser_cannot_add_nonexistent_path(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that invalid filesystem paths are rejected before persistence."""
    superuser = UserFactory.create_user(
        session=db_session,
        email="superuser_invalid_path@example.com",
        role="admin",
        is_superuser=True,
    )
    await db_session.flush()

    headers = await login_user(test_client, superuser.email, "password123")

    response = await test_client.post(
        f"{API_PREFIX}/storage-paths/",
        json={"path": "/tmp/definitely-missing-storage-path"},
        headers=headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "does not exist or is not a directory" in response.json()["detail"]
    assert (
        await crud.storage_path.get_by_path(db_session, path="/tmp/definitely-missing-storage-path")
        is None
    )


@pytest.mark.asyncio
async def test_superuser_cannot_add_file_path(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that existing files are rejected because only directories are valid."""
    superuser = UserFactory.create_user(
        session=db_session,
        email="superuser_file_path@example.com",
        role="admin",
        is_superuser=True,
    )
    await db_session.flush()

    headers = await login_user(test_client, superuser.email, "password123")
    file_path = str(Path(__file__).resolve())

    response = await test_client.post(
        f"{API_PREFIX}/storage-paths/",
        json={"path": file_path},
        headers=headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "does not exist or is not a directory" in response.json()["detail"]
    assert await crud.storage_path.get_by_path(db_session, path=file_path) is None


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


@pytest.mark.asyncio
async def test_user_can_update_path_label_without_sending_path(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    path = await crud.storage_path.create(
        db_session, obj_in=StoragePathCreate(path="/tmp", label="Old Label")
    )
    await db_session.flush()

    user = UserFactory.create_user(
        session=db_session,
        email="update_label_only_user@example.com",
        role="standard",
    )
    await db_session.flush()

    headers = await login_user(test_client, user.email, "password123")

    response = await test_client.patch(
        f"{API_PREFIX}/storage-paths/{path.id}",
        json={"label": "Label Only Update"},
        headers=headers,
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["label"] == "Label Only Update"
    assert response.json()["path"] == "/tmp"


@pytest.mark.asyncio
async def test_update_storage_path_rejects_empty_payload(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    path = await crud.storage_path.create(
        db_session, obj_in=StoragePathCreate(path="/tmp", label="Old Label")
    )
    await db_session.flush()

    user = UserFactory.create_user(
        session=db_session,
        email="update_empty_payload_user@example.com",
        role="standard",
    )
    await db_session.flush()

    headers = await login_user(test_client, user.email, "password123")

    response = await test_client.patch(
        f"{API_PREFIX}/storage-paths/{path.id}",
        json={},
        headers=headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "updatable field" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_storage_path_rejects_path_only_payload(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    path = await crud.storage_path.create(
        db_session, obj_in=StoragePathCreate(path="/tmp", label="Old Label")
    )
    await db_session.flush()

    user = UserFactory.create_user(
        session=db_session,
        email="update_path_only_user@example.com",
        role="standard",
    )
    await db_session.flush()

    headers = await login_user(test_client, user.email, "password123")

    response = await test_client.patch(
        f"{API_PREFIX}/storage-paths/{path.id}",
        json={"path": "/var"},
        headers=headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "updatable field" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_browse_storage_roots_returns_allowed_paths(
    test_client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    allowed_root = tmp_path / "media"
    allowed_root.mkdir()
    await crud.storage_path.create(db_session, obj_in=StoragePathCreate(path=str(allowed_root)))
    await db_session.flush()

    user = UserFactory.create_user(
        session=db_session,
        email="browse_roots_user@example.com",
        role="standard",
    )
    await db_session.flush()
    headers = await login_user(test_client, user.email, "password123")

    response = await test_client.get(f"{API_PREFIX}/storage-paths/browse", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    assert any(entry["path"] == str(allowed_root.resolve()) for entry in response.json())


@pytest.mark.asyncio
async def test_browse_storage_path_returns_direct_child_directories(
    test_client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    allowed_root = tmp_path / "library"
    allowed_root.mkdir()
    movie_dir = allowed_root / "Movies"
    movie_dir.mkdir()
    (movie_dir / "Nested").mkdir()
    (allowed_root / "readme.txt").write_text("ignore me", encoding="utf-8")

    await crud.storage_path.create(db_session, obj_in=StoragePathCreate(path=str(allowed_root)))
    await db_session.flush()

    user = UserFactory.create_user(
        session=db_session,
        email="browse_children_user@example.com",
        role="standard",
    )
    await db_session.flush()
    headers = await login_user(test_client, user.email, "password123")

    response = await test_client.get(
        f"{API_PREFIX}/storage-paths/browse",
        params={"path": str(allowed_root)},
        headers=headers,
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        {
            "name": "Movies",
            "path": str(movie_dir.resolve()),
            "has_children": True,
        }
    ]


@pytest.mark.asyncio
async def test_browse_storage_path_rejects_paths_outside_allowed_roots(
    test_client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    forbidden_root = tmp_path / "forbidden"
    forbidden_root.mkdir()

    await crud.storage_path.create(db_session, obj_in=StoragePathCreate(path=str(allowed_root)))
    await db_session.flush()

    user = UserFactory.create_user(
        session=db_session,
        email="browse_forbidden_user@example.com",
        role="standard",
    )
    await db_session.flush()
    headers = await login_user(test_client, user.email, "password123")

    response = await test_client.get(
        f"{API_PREFIX}/storage-paths/browse",
        params={"path": str(forbidden_root)},
        headers=headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_browse_storage_path_returns_not_found_for_missing_path(
    test_client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    missing_path = allowed_root / "missing"

    await crud.storage_path.create(db_session, obj_in=StoragePathCreate(path=str(allowed_root)))
    await db_session.flush()

    user = UserFactory.create_user(
        session=db_session,
        email="browse_missing_user@example.com",
        role="standard",
    )
    await db_session.flush()
    headers = await login_user(test_client, user.email, "password123")

    response = await test_client.get(
        f"{API_PREFIX}/storage-paths/browse",
        params={"path": str(missing_path)},
        headers=headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_browse_storage_path_excludes_symlinks_outside_allowed_roots(
    test_client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    outside_root = tmp_path / "outside"
    outside_root.mkdir()

    linked_dir = allowed_root / "escape"
    try:
        linked_dir.symlink_to(outside_root, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlinks are not supported in this environment: {exc}")

    await crud.storage_path.create(db_session, obj_in=StoragePathCreate(path=str(allowed_root)))
    await db_session.flush()

    user = UserFactory.create_user(
        session=db_session,
        email="browse_symlink_user@example.com",
        role="standard",
    )
    await db_session.flush()
    headers = await login_user(test_client, user.email, "password123")

    response = await test_client.get(
        f"{API_PREFIX}/storage-paths/browse",
        params={"path": str(allowed_root)},
        headers=headers,
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


@pytest.mark.asyncio
async def test_browse_system_roots_requires_superuser(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = UserFactory.create_user(
        session=db_session,
        email="browse_system_admin@example.com",
        role="admin",
        is_superuser=False,
    )
    await db_session.flush()
    headers = await login_user(test_client, admin.email, "password123")

    response = await test_client.get(
        f"{API_PREFIX}/storage-paths/browse-system",
        headers=headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_browse_system_roots_returns_filesystem_roots_for_superuser(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    superuser = UserFactory.create_user(
        session=db_session,
        email="browse_system_superuser@example.com",
        role="admin",
        is_superuser=True,
    )
    await db_session.flush()
    headers = await login_user(test_client, superuser.email, "password123")

    response = await test_client.get(
        f"{API_PREFIX}/storage-paths/browse-system",
        headers=headers,
    )

    assert response.status_code == status.HTTP_200_OK

    payload = response.json()
    assert payload
    if os.name != "nt":
        assert any(entry["path"] == str(Path("/").resolve()) for entry in payload)


@pytest.mark.asyncio
async def test_browse_system_path_returns_sorted_directories_only(
    test_client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    browse_root = tmp_path / "system-browse"
    browse_root.mkdir()
    (browse_root / "Zulu").mkdir()
    (browse_root / "alpha").mkdir()
    (browse_root / "Beta").mkdir()
    (browse_root / "ignored.txt").write_text("ignore", encoding="utf-8")

    superuser = UserFactory.create_user(
        session=db_session,
        email="browse_system_sorted@example.com",
        role="admin",
        is_superuser=True,
    )
    await db_session.flush()
    headers = await login_user(test_client, superuser.email, "password123")

    response = await test_client.get(
        f"{API_PREFIX}/storage-paths/browse-system",
        params={"path": str(browse_root)},
        headers=headers,
    )

    assert response.status_code == status.HTTP_200_OK
    assert [entry["name"] for entry in response.json()] == ["alpha", "Beta", "Zulu"]


@pytest.mark.asyncio
async def test_browse_system_path_skips_broken_symlinks(
    test_client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    browse_root = tmp_path / "broken-link-root"
    browse_root.mkdir()
    valid_dir = browse_root / "valid"
    valid_dir.mkdir()
    broken_link = browse_root / "broken"

    try:
        broken_link.symlink_to(browse_root / "missing", target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlinks are not supported in this environment: {exc}")

    superuser = UserFactory.create_user(
        session=db_session,
        email="browse_system_broken@example.com",
        role="admin",
        is_superuser=True,
    )
    await db_session.flush()
    headers = await login_user(test_client, superuser.email, "password123")

    response = await test_client.get(
        f"{API_PREFIX}/storage-paths/browse-system",
        params={"path": str(browse_root)},
        headers=headers,
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        {
            "name": "valid",
            "path": str(valid_dir.resolve()),
            "has_children": False,
        }
    ]


@pytest.mark.asyncio
async def test_create_storage_path_duplicate_returns_structured_detail(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    superuser = UserFactory.create_user(
        session=db_session,
        email="duplicate_storage_path@example.com",
        role="admin",
        is_superuser=True,
    )
    await db_session.flush()
    headers = await login_user(test_client, superuser.email, "password123")

    first_response = await test_client.post(
        f"{API_PREFIX}/storage-paths/",
        json={"path": "/tmp"},
        headers=headers,
    )
    assert first_response.status_code == status.HTTP_201_CREATED

    duplicate_response = await test_client.post(
        f"{API_PREFIX}/storage-paths/",
        json={"path": "/tmp"},
        headers=headers,
    )

    assert duplicate_response.status_code == status.HTTP_400_BAD_REQUEST
    assert duplicate_response.json()["detail"] == {
        "code": "PATH_ALREADY_EXISTS",
        "message": "Storage path already exists.",
    }
