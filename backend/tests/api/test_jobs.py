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


@pytest.mark.asyncio
@patch("app.api.routers.jobs.celery_app")
async def test_retry_job_success(
    mock_celery, test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that a FAILED job can be retried, creating a new job."""
    user = UserFactory.create_user(session=db_session, email="retry_user@example.com")
    await db_session.flush()

    # Create a FAILED job
    original_job = Job(
        folder_path="/media/movies/test",
        language="en",
        log_level="INFO",
        user_id=user.id,
        status=JobStatus.FAILED,
    )
    db_session.add(original_job)
    await db_session.commit()
    await db_session.refresh(original_job)

    headers = await login_user(test_client, user.email, "password123")
    response = await test_client.post(f"{API_PREFIX}/jobs/{original_job.id}/retry", headers=headers)

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["folder_path"] == original_job.folder_path
    assert data["language"] == original_job.language
    assert data["status"].upper() == "PENDING"
    assert data["id"] != str(original_job.id)  # New job created

    mock_celery.send_task.assert_called_once()


@pytest.mark.asyncio
async def test_retry_job_forbidden_for_running(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that a RUNNING job cannot be retried."""
    user = UserFactory.create_user(session=db_session, email="retry_running@example.com")
    await db_session.flush()

    job = Job(
        folder_path="/media/movies",
        language="en",
        user_id=user.id,
        status=JobStatus.RUNNING,
        celery_task_id="test-celery-id-running",
    )
    db_session.add(job)
    await db_session.commit()

    headers = await login_user(test_client, user.email, "password123")
    response = await test_client.post(f"{API_PREFIX}/jobs/{job.id}/retry", headers=headers)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "JOB_NOT_RETRIABLE" in str(response.json())


@pytest.mark.asyncio
@patch("app.api.routers.jobs.celery_app")
async def test_cancel_job_success(
    mock_celery, test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that a RUNNING job can be cancelled."""
    user = UserFactory.create_user(session=db_session, email="cancel_user@example.com")
    await db_session.flush()

    job = Job(
        folder_path="/media/movies",
        language="en",
        user_id=user.id,
        status=JobStatus.RUNNING,
        celery_task_id="test-celery-id",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    headers = await login_user(test_client, user.email, "password123")
    response = await test_client.post(f"{API_PREFIX}/jobs/{job.id}/cancel", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"].upper() == "CANCELLING"

    mock_celery.control.revoke.assert_called_once_with(
        "test-celery-id", terminate=True, signal="SIGTERM"
    )


@pytest.mark.asyncio
async def test_cancel_job_forbidden_for_completed(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test that a SUCCEEDED job cannot be cancelled."""
    user = UserFactory.create_user(session=db_session, email="cancel_done@example.com")
    await db_session.flush()

    job = Job(
        folder_path="/media/movies",
        language="en",
        user_id=user.id,
        status=JobStatus.SUCCEEDED,
    )
    db_session.add(job)
    await db_session.commit()

    headers = await login_user(test_client, user.email, "password123")
    response = await test_client.post(f"{API_PREFIX}/jobs/{job.id}/cancel", headers=headers)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "JOB_NOT_CANCELLABLE" in str(response.json())


@pytest.mark.asyncio
async def test_get_recent_torrents_success(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = UserFactory.create_user(session=db_session, email="torrent_user@example.com")
    await db_session.flush()
    headers = await login_user(test_client, user.email, "password123")

    # Mock the internal helper that gets the client
    with patch("app.api.routers.jobs._get_qbittorrent_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock the service function that fetches torrents
        with patch(
            "app.modules.subtitle.services.torrent_client.get_completed_torrents"
        ) as mock_get_torrents:
            # Create mock torrent objects
            mock_torrent1 = MagicMock()
            mock_torrent1.name = "Movie 1"
            mock_torrent1.save_path = "/downloads/movie1"
            mock_torrent1.content_path = "/downloads/movie1/Movie 1"
            mock_torrent1.completion_on = 1672531200  # 2023-01-01

            mock_torrent2 = MagicMock()
            mock_torrent2.name = "Movie 2"
            mock_torrent2.save_path = "/downloads/movie2"
            mock_torrent2.content_path = "/downloads/movie2/Movie 2"
            mock_torrent2.completion_on = 1672617600  # 2023-01-02

            # Return them in unsorted order to verify sorting
            mock_get_torrents.return_value = [mock_torrent1, mock_torrent2]

            response = await test_client.get(f"{API_PREFIX}/jobs/recent-torrents", headers=headers)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert len(data) == 2
            # Should be sorted by completion time descending (newest first)
            assert data[0]["name"] == "Movie 2"
            assert data[0]["save_path"] == "/downloads/movie2"
            assert data[0]["content_path"] == "/downloads/movie2/Movie 2"
            assert data[1]["name"] == "Movie 1"
            assert data[1]["content_path"] == "/downloads/movie1/Movie 1"


@pytest.mark.asyncio
async def test_get_recent_torrents_no_client(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = UserFactory.create_user(session=db_session, email="no_client_user@example.com")
    await db_session.flush()
    headers = await login_user(test_client, user.email, "password123")

    with patch("app.api.routers.jobs._get_qbittorrent_client") as mock_get_client:
        mock_get_client.return_value = None

        response = await test_client.get(f"{API_PREFIX}/jobs/recent-torrents", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []
