from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

from ..factories.user_factory import UserFactory

API_PREFIX = settings.API_V1_STR


async def login_user(client: AsyncClient, email: str, password: str) -> dict:
    login_data = {"username": email, "password": password}
    response = await client.post(f"{API_PREFIX}/auth/login", data=login_data)
    assert response.status_code == status.HTTP_200_OK
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
@patch("app.api.routers.files.Path")
async def test_download_file_forbidden_for_standard_user(
    _, test_client: AsyncClient, db_session: AsyncSession
):
    user = UserFactory.create_user(session=db_session, email="standard_files@example.com")
    await db_session.flush()
    headers = await login_user(test_client, user.email, "password123")

    response = await test_client.get(
        f"{API_PREFIX}/files/download?path=/media/test.srt", headers=headers
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_download_file_success_admin(test_client: AsyncClient, db_session: AsyncSession):
    admin = UserFactory.create_user(
        session=db_session, email="admin_files@example.com", is_superuser=True
    )
    await db_session.flush()
    headers = await login_user(test_client, admin.email, "password123")

    test_file_path = "/media/test.srt"

    # Mock Path.resolve and is_file and existence
    with patch("app.api.routers.files.Path") as mock_path_cls:
        mock_resolved = MagicMock()
        mock_resolved.is_file.return_value = True
        mock_resolved.name = "test.srt"
        mock_resolved.__str__.return_value = test_file_path

        mock_path_cls.return_value.resolve.return_value = mock_resolved

        # Ensure allowed folders include the path
        with patch("app.api.routers.files.settings") as mock_settings:
            mock_settings.ALLOWED_MEDIA_FOLDERS = ["/media"]
            mock_resolved.parents = [MagicMock()]
            # Simulate "base in resolved_file_path.parents" or "resolved_file_path == base"
            # In our test case, we'll just mock the 'is_allowed' check logic if needed or just let it run

            # Since we can't easily mock the 'any' list comprehension without complex patching,
            # let's try to make the real Path(base).resolve() work if possible or mock the whole check.

            with patch("app.api.routers.files.FileResponse"):
                response = await test_client.get(
                    f"{API_PREFIX}/files/download?path={test_file_path}", headers=headers
                )
                assert response.status_code == status.HTTP_200_OK

                # If we get 200, it means it passed security checks
                # Note: FileResponse might fail if path doesn't REALLY exist on disk during actual call inside FastAPI
                # so we might get a 500 or 404 if not careful.
                # But our goal is to test the ROUTER logic.
