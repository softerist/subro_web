"""Tests for webhook endpoint functionality."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.webhook_keys import _hash_webhook_key
from app.core.config import settings
from app.db.models.job import Job
from app.db.models.webhook_key import WebhookKey

from ..factories.user_factory import UserFactory

API_PREFIX = settings.API_V1_STR


@pytest.fixture
async def setup_webhook_key(db_session: AsyncSession) -> str:
    """Set up a webhook key and return the raw key."""
    raw_key = "test-webhook-key-67890"
    hashed_key = _hash_webhook_key(raw_key)

    webhook_key = WebhookKey(
        name="Test Webhook Key",
        prefix=raw_key[:8],
        last4=raw_key[-4:],
        hashed_key=hashed_key,
        scopes=["jobs:create"],
        is_active=True,
    )
    db_session.add(webhook_key)
    await db_session.commit()
    return raw_key


@pytest.fixture
async def admin_user(db_session: AsyncSession):
    """Create an admin user for webhook job attribution."""
    admin = UserFactory.create_user(
        session=db_session,
        email="webhook_admin@example.com",
        is_superuser=True,
    )
    await db_session.flush()
    return admin


@pytest.mark.asyncio
async def test_webhook_missing_key_header(
    test_client: AsyncClient,
    db_session: AsyncSession,  # noqa: ARG001
) -> None:
    """Test that webhook endpoint rejects requests without X-Webhook-Key header."""
    job_in = {"folder_path": "/media/test", "log_level": "INFO"}

    response = await test_client.post(f"{API_PREFIX}/jobs/webhook", json=job_in)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Missing X-Webhook-Key" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_invalid_key(
    test_client: AsyncClient,
    db_session: AsyncSession,  # noqa: ARG001
    setup_webhook_key: str,  # noqa: ARG001
) -> None:
    """Test that webhook endpoint rejects requests with wrong key."""
    job_in = {"folder_path": "/media/test", "log_level": "INFO"}
    headers = {"X-Webhook-Key": "wrong-key"}

    response = await test_client.post(f"{API_PREFIX}/jobs/webhook", json=job_in, headers=headers)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid webhook key" in response.json()["detail"]


@pytest.mark.asyncio
@patch("app.api.routers.jobs.celery_app")
async def test_webhook_success(
    mock_celery,
    test_client: AsyncClient,
    db_session: AsyncSession,
    setup_webhook_key: str,
    admin_user,
) -> None:
    """Test successful job creation via webhook endpoint."""
    with patch("app.api.routers.jobs.Path") as mock_path:
        path_str = "/media/webhook_test"
        mock_resolved = MagicMock()
        mock_resolved.__str__.return_value = path_str
        mock_resolved.parents = []
        mock_path.return_value.resolve.return_value = mock_resolved

        with patch("app.api.routers.jobs._is_path_allowed", return_value=True):
            job_in = {"folder_path": path_str, "language": "en", "log_level": "INFO"}
            headers = {"X-Webhook-Key": setup_webhook_key}

            response = await test_client.post(
                f"{API_PREFIX}/jobs/webhook", json=job_in, headers=headers
            )

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["folder_path"] == path_str
            assert data["status"].upper() == "PENDING"

            # Verify job attributed to admin user
            assert data["user_id"] == str(admin_user.id)

            # Verify Celery task sent
            mock_celery.send_task.assert_called_once()

            # Verify Job created in DB
            db_job = await db_session.get(Job, uuid.UUID(data["id"]))
            assert db_job is not None
            assert db_job.folder_path == path_str
            assert db_job.user_id == admin_user.id
