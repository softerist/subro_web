import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.job import Job, JobStatus

from ..factories.user_factory import UserFactory

API_PREFIX = settings.API_V1_STR


async def login_user(client: AsyncClient, email: str, password: str) -> dict:
    login_data = {"username": email, "password": password}
    response = await client.post(f"{API_PREFIX}/auth/login", data=login_data)
    assert response.status_code == status.HTTP_200_OK
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_jobs_empty(test_client: AsyncClient, db_session: AsyncSession) -> None:
    user = UserFactory.create_user(session=db_session, email="job_user@example.com")
    await db_session.flush()
    headers = await login_user(test_client, user.email, "password123")

    response = await test_client.get(f"{API_PREFIX}/jobs/", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


@pytest.mark.asyncio
@patch("app.api.routers.jobs.celery_app")
async def test_create_job_success(
    mock_celery, test_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Mocking Path.resolve to avoid needing real directories
    with patch("app.api.routers.jobs.Path") as mock_path:
        # Setup admin user (can auto-add paths)
        admin = UserFactory.create_user(
            session=db_session, email="admin_jobs@example.com", is_superuser=True
        )
        await db_session.flush()
        headers = await login_user(test_client, admin.email, "password123")

        path_str = "/media/test"
        mock_resolved = MagicMock()
        mock_resolved.__str__.return_value = path_str
        mock_resolved.parents = []
        mock_path.return_value.resolve.return_value = mock_resolved

        # Mock _is_path_allowed as True for admin auto-add simulation or just bypass
        with patch(
            "app.api.routers.jobs._is_path_allowed", return_value=False
        ):  # Admin auto-adds if False
            job_in = {"folder_path": path_str, "language": "en", "log_level": "INFO"}

            response = await test_client.post(f"{API_PREFIX}/jobs/", json=job_in, headers=headers)

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["folder_path"] == path_str
            assert data["status"].upper() == "PENDING"

            # Verify Celery task sent
            mock_celery.send_task.assert_called_once()

            # Verify Job created in DB
            db_job = await db_session.get(Job, uuid.UUID(data["id"]))
            assert db_job is not None
            assert db_job.folder_path == path_str


@pytest.mark.asyncio
async def test_get_job_details(test_client: AsyncClient, db_session: AsyncSession) -> None:
    user = UserFactory.create_user(session=db_session, email="owner@example.com")
    await db_session.flush()

    job = Job(
        folder_path="/media/movies",
        language="en",
        log_level="INFO",
        user_id=user.id,
        status=JobStatus.PENDING,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    headers = await login_user(test_client, user.email, "password123")
    response = await test_client.get(f"{API_PREFIX}/jobs/{job.id}", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == str(job.id)


@pytest.mark.asyncio
async def test_get_job_details_forbidden(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = UserFactory.create_user(session=db_session, email="owner_priv@example.com")
    other_user = UserFactory.create_user(session=db_session, email="other@example.com")
    await db_session.flush()

    job = Job(
        folder_path="/media/movies", language="en", user_id=owner.id, status=JobStatus.PENDING
    )
    db_session.add(job)
    await db_session.commit()

    headers = await login_user(test_client, other_user.email, "password123")
    response = await test_client.get(f"{API_PREFIX}/jobs/{job.id}", headers=headers)

    assert response.status_code == status.HTTP_403_FORBIDDEN
