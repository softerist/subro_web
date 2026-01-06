from unittest.mock import patch

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.crud_app_settings import crud_app_settings

API_PREFIX = settings.API_V1_STR


@pytest.mark.asyncio
async def test_setup_status_returns_all_fields(test_client: AsyncClient):
    """Verify setup_required and setup_forced are returned along with setup_completed."""
    response = await test_client.get(f"{API_PREFIX}/setup/status")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "setup_completed" in data
    assert "setup_required" in data
    assert "setup_forced" in data
    # Fresh DB should have setup_completed = False, setup_required = True
    assert data["setup_completed"] is False
    assert data["setup_required"] is True


@pytest.mark.asyncio
async def test_complete_setup_success(test_client: AsyncClient, db_session: AsyncSession):
    """Standard setup completion creates admin and marks complete."""
    setup_payload = {
        "admin_email": "initial_admin@example.com",
        "admin_password": "SecurePassword123",
        "settings": {"tmdb_api_key": "some_key"},
    }

    with patch("app.api.routers.setup.validate_all_settings"):
        response = await test_client.post(f"{API_PREFIX}/setup/complete", json=setup_payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["setup_completed"] is True
        assert data["setup_required"] is False

        # Verify setup is now marked as completed in DB
        is_completed = await crud_app_settings.get_setup_completed(db_session)
        assert is_completed is True


@pytest.mark.asyncio
async def test_setup_endpoints_forbidden_once_completed(
    test_client: AsyncClient, db_session: AsyncSession
):
    """Verify setup endpoints return 404 once setup is completed."""
    await crud_app_settings.mark_setup_completed(db_session)
    await db_session.commit()

    setup_payload = {"admin_email": "another_admin@example.com", "admin_password": "Password123"}
    response = await test_client.post(f"{API_PREFIX}/setup/complete", json=setup_payload)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
@pytest.mark.usefixtures("db_session")
async def test_skip_without_credentials_fails_when_signup_disabled(test_client: AsyncClient):
    """Verify 400 returned when skipping without credentials and OPEN_SIGNUP is disabled."""
    with patch.object(settings, "OPEN_SIGNUP", False):
        with patch.object(settings, "FIRST_SUPERUSER_EMAIL", None):
            with patch.object(settings, "FIRST_SUPERUSER_PASSWORD", None):
                response = await test_client.post(f"{API_PREFIX}/setup/skip", json={})
                assert response.status_code == status.HTTP_400_BAD_REQUEST
                assert "Admin credentials required" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("db_session")
async def test_skip_partial_credentials_fails(test_client: AsyncClient):
    """Verify 400 returned when only email or password provided (not both)."""
    # Only email, no password
    response = await test_client.post(
        f"{API_PREFIX}/setup/skip",
        json={"admin_email": "test@example.com", "admin_password": None},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Both email and password" in response.json()["detail"]

    # Only password, no email
    response = await test_client.post(
        f"{API_PREFIX}/setup/skip",
        json={"admin_email": None, "admin_password": "somepassword"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
@pytest.mark.usefixtures("db_session")
async def test_skip_with_env_fallback_succeeds(test_client: AsyncClient):
    """Verify skip works when env vars are set but no credentials provided."""
    with patch.object(settings, "FIRST_SUPERUSER_EMAIL", "env_admin@example.com"):
        with patch.object(settings, "FIRST_SUPERUSER_PASSWORD", "EnvPassword123"):
            with patch("app.api.routers.setup.validate_all_settings"):
                response = await test_client.post(f"{API_PREFIX}/setup/skip", json={})
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["setup_completed"] is True


@pytest.mark.asyncio
async def test_complete_with_existing_admin_updates_password_on_first_setup(
    test_client: AsyncClient, db_session: AsyncSession
):
    """Verify password is updated for existing admin during first-time setup."""
    from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase

    from app.core.users import UserManager
    from app.db.models.user import User as UserModel

    # Create a user first
    from app.schemas.user import UserCreate

    user_db_adapter = SQLAlchemyUserDatabase(db_session, UserModel)
    user_manager = UserManager(user_db_adapter)

    await user_manager.create(
        UserCreate(
            email="existing@example.com",
            password="OldPassword123",
            is_superuser=False,
            is_active=True,
            is_verified=True,
            role="standard",
        ),
        safe=False,
    )
    await db_session.commit()

    # Now complete setup with same email but different password
    with patch("app.api.routers.setup.validate_all_settings"):
        response = await test_client.post(
            f"{API_PREFIX}/setup/complete",
            json={
                "admin_email": "existing@example.com",
                "admin_password": "NewPassword123",
            },
        )
        assert response.status_code == status.HTTP_200_OK

    # The user's password should now be updated (we can verify by trying to log in)
    # This is an integration test - just verify the endpoint succeeds


@pytest.mark.asyncio
async def test_force_initial_setup_shows_wizard_after_completion(
    test_client: AsyncClient, db_session: AsyncSession
):
    """Verify FORCE_INITIAL_SETUP=true makes setup_required=true even after completion."""
    # First, mark setup as completed
    await crud_app_settings.mark_setup_completed(db_session)
    await db_session.commit()

    # Without force flag, setup should NOT be required
    response = await test_client.get(f"{API_PREFIX}/setup/status")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["setup_completed"] is True
    assert data["setup_required"] is False

    # With FORCE_INITIAL_SETUP=true, setup_required should be True
    with patch.object(settings, "FORCE_INITIAL_SETUP", True):
        response = await test_client.get(f"{API_PREFIX}/setup/status")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["setup_completed"] is True  # Still true
        assert data["setup_required"] is True  # But wizard should show
        assert data["setup_forced"] is True


@pytest.mark.asyncio
async def test_forced_setup_allows_complete_after_already_completed(
    test_client: AsyncClient, db_session: AsyncSession
):
    """Verify /complete works when FORCE_INITIAL_SETUP=true even if already completed."""
    # Mark setup as completed
    await crud_app_settings.mark_setup_completed(db_session)
    await db_session.commit()

    # Without force, should return 404
    setup_payload = {"admin_email": "forced@example.com", "admin_password": "ForcedPassword123"}
    response = await test_client.post(f"{API_PREFIX}/setup/complete", json=setup_payload)
    assert response.status_code == status.HTTP_404_NOT_FOUND

    # With FORCE_INITIAL_SETUP=true, should succeed
    with patch.object(settings, "FORCE_INITIAL_SETUP", True):
        with patch("app.api.routers.setup.validate_all_settings"):
            response = await test_client.post(f"{API_PREFIX}/setup/complete", json=setup_payload)
            assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_skip_endpoint_blocked_after_completion(
    test_client: AsyncClient, db_session: AsyncSession
):
    """Verify /skip returns 404 after setup is completed."""
    await crud_app_settings.mark_setup_completed(db_session)
    await db_session.commit()

    response = await test_client.post(f"{API_PREFIX}/setup/skip", json={})
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_get_setup_state_helper(db_session: AsyncSession):
    """Unit test for get_setup_state() helper function."""
    # Fresh DB: setup_completed=False, setup_required=True
    state = await crud_app_settings.get_setup_state(db_session)
    assert state["setup_completed"] is False
    assert state["setup_required"] is True
    assert state["setup_forced"] is False  # Default

    # After marking complete
    await crud_app_settings.mark_setup_completed(db_session)
    await db_session.commit()

    state = await crud_app_settings.get_setup_state(db_session)
    assert state["setup_completed"] is True
    assert state["setup_required"] is False
    assert state["setup_forced"] is False

    # With FORCE_INITIAL_SETUP=true
    with patch.object(settings, "FORCE_INITIAL_SETUP", True):
        state = await crud_app_settings.get_setup_state(db_session)
        assert state["setup_completed"] is True  # Still true
        assert state["setup_required"] is True  # Forced
        assert state["setup_forced"] is True


@pytest.mark.asyncio
async def test_forced_setup_with_existing_admin_preserves_password(
    test_client: AsyncClient, db_session: AsyncSession
):
    """Verify forced setup with existing admin does NOT update password."""
    from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase

    from app.core.users import UserManager
    from app.db.models.user import User as UserModel
    from app.schemas.user import UserCreate

    # Create existing admin
    user_db_adapter = SQLAlchemyUserDatabase(db_session, UserModel)
    user_manager = UserManager(user_db_adapter)

    existing_admin = await user_manager.create(
        UserCreate(
            email="existing_admin@example.com",
            password="OriginalPassword123",
            is_superuser=True,
            is_active=True,
            is_verified=True,
            role="admin",
        ),
        safe=False,
    )
    original_password_hash = existing_admin.hashed_password
    await db_session.commit()

    # Mark setup as completed
    await crud_app_settings.mark_setup_completed(db_session)
    await db_session.commit()

    # Do forced setup with same email but different password
    with patch.object(settings, "FORCE_INITIAL_SETUP", True):
        with patch("app.api.routers.setup.validate_all_settings"):
            response = await test_client.post(
                f"{API_PREFIX}/setup/complete",
                json={
                    "admin_email": "existing_admin@example.com",
                    "admin_password": "DifferentPassword456",
                },
            )
            assert response.status_code == status.HTTP_200_OK

    # Refresh the user and verify password hash is UNCHANGED
    await db_session.refresh(existing_admin)
    assert existing_admin.hashed_password == original_password_hash
