# backend/tests/api/test_api_keys.py
from pathlib import Path

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import jobs as jobs_router
from app.core.api_key_auth import get_api_key_last4, get_api_key_prefix, hash_api_key
from app.core.config import settings
from app.db.models.api_key import ApiKey

from ..factories.user_factory import UserFactory

API_PREFIX = settings.API_V1_STR


async def login_user(client: AsyncClient, email: str, password: str) -> dict:
    """Log in and return auth headers for the user."""
    response = await client.post(
        f"{API_PREFIX}/auth/login", data={"username": email, "password": password}
    )
    assert response.status_code == status.HTTP_200_OK, f"Login failed for {email}: {response.text}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_api_key_lifecycle_allows_job_access(
    test_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    if not settings.API_KEY_PEPPER:
        pytest.skip("API_KEY_PEPPER not configured for API key tests.")

    admin = UserFactory.create_admin(
        session=db_session,
        email="api_key_admin@example.com",
        password="password123",
    )
    user = UserFactory.create_user(
        session=db_session,
        email="api_key_user@example.com",
        password="password123",
    )
    await db_session.flush()

    admin_headers = await login_user(test_client, admin.email, "password123")
    job_dir = tmp_path / "api_key_job"
    job_dir.mkdir()

    allow_response = await test_client.post(
        f"{API_PREFIX}/storage-paths/",
        json={"path": str(job_dir), "label": "API key test"},
        headers=admin_headers,
    )
    assert allow_response.status_code == status.HTTP_201_CREATED, allow_response.text

    user_headers = await login_user(test_client, user.email, "password123")
    key_response = await test_client.post(f"{API_PREFIX}/users/me/api-key", headers=user_headers)
    assert key_response.status_code == status.HTTP_200_OK, key_response.text

    key_data = key_response.json()
    api_key = key_data["api_key"]
    assert key_data["preview"] == f"{api_key[:8]}...{api_key[-4:]}"

    result = await db_session.execute(
        select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None))
    )
    api_key_record = result.scalars().first()
    assert api_key_record is not None
    assert api_key_record.prefix == get_api_key_prefix(api_key)
    assert api_key_record.last4 == get_api_key_last4(api_key)
    assert api_key_record.hashed_key == hash_api_key(api_key)

    monkeypatch.setattr(jobs_router.celery_app, "send_task", lambda *_args, **_kwargs: None)

    job_payload = {"folder_path": str(job_dir)}
    job_response = await test_client.post(
        f"{API_PREFIX}/jobs/",
        json=job_payload,
        headers={"X-API-Key": api_key},
    )
    assert job_response.status_code == status.HTTP_201_CREATED, job_response.text
    job_data = job_response.json()
    assert job_data["folder_path"] == str(job_dir)
    assert job_data["user_id"] == str(user.id)

    regen_response = await test_client.post(f"{API_PREFIX}/users/me/api-key", headers=user_headers)
    assert regen_response.status_code == status.HTTP_200_OK, regen_response.text
    new_key = regen_response.json()["api_key"]
    assert new_key != api_key

    old_key_response = await test_client.post(
        f"{API_PREFIX}/jobs/",
        json=job_payload,
        headers={"X-API-Key": api_key},
    )
    assert old_key_response.status_code == status.HTTP_401_UNAUTHORIZED
    assert old_key_response.json()["detail"] == "Invalid API Key"

    new_key_response = await test_client.post(
        f"{API_PREFIX}/jobs/",
        json=job_payload,
        headers={"X-API-Key": new_key},
    )
    assert new_key_response.status_code == status.HTTP_201_CREATED, new_key_response.text

    revoke_response = await test_client.delete(
        f"{API_PREFIX}/users/me/api-key", headers=user_headers
    )
    assert revoke_response.status_code == status.HTTP_200_OK, revoke_response.text
    assert revoke_response.json()["revoked"] is True

    revoked_key_response = await test_client.post(
        f"{API_PREFIX}/jobs/",
        json=job_payload,
        headers={"X-API-Key": new_key},
    )
    assert revoked_key_response.status_code == status.HTTP_401_UNAUTHORIZED
    assert revoked_key_response.json()["detail"] == "Invalid API Key"
