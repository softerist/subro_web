import pytest
from httpx import AsyncClient

from app.services import audit_service
from app.tasks.audit_worker import process_outbox_batch


@pytest.mark.usefixtures("override_auth_dependencies")
@pytest.mark.asyncio
async def test_get_audit_stats(test_client: AsyncClient, audit_admin_headers: dict, db_session):
    # Ensure some data exists
    await audit_service.log_event(db_session, category="auth", action="auth.login", success=True)
    await audit_service.log_event(
        db_session, category="security", action="security.failed_login", success=False
    )
    await db_session.commit()

    # Process outbox
    await process_outbox_batch(db_session)

    response = await test_client.get("/api/v1/admin/audit/stats", headers=audit_admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_events"] >= 2
    assert "auth" in data["events_by_category"]


@pytest.mark.usefixtures("override_auth_dependencies")
@pytest.mark.asyncio
async def test_audit_list_pagination(
    test_client: AsyncClient, audit_admin_headers: dict, db_session
):
    # Create 10 events
    for i in range(10):
        await audit_service.log_event(db_session, category="test", action=f"test.action.{i}")
    await db_session.commit()

    # Process outbox
    await process_outbox_batch(db_session)

    # Get first 5
    response = await test_client.get("/api/v1/admin/audit?limit=5", headers=audit_admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    # Pagination might be reversed
    assert data["next_cursor"] is not None


@pytest.mark.usefixtures("override_auth_dependencies")
@pytest.mark.asyncio
async def test_audit_verify_integrity(
    test_client: AsyncClient, audit_admin_headers: dict, db_session
):
    # Create a small chain
    await audit_service.log_event(db_session, category="admin", action="admin.audit.view")
    await audit_service.log_event(db_session, category="admin", action="admin.audit.verify")
    await db_session.commit()

    # Process outbox
    await process_outbox_batch(db_session)

    response = await test_client.post("/api/v1/admin/audit/verify", headers=audit_admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["verified"] is True


@pytest.mark.usefixtures("override_auth_dependencies")
@pytest.mark.asyncio
async def test_audit_forbidden_for_non_admin(test_client: AsyncClient, audit_user_headers: dict):
    response = await test_client.get("/api/v1/admin/audit", headers=audit_user_headers)
    assert response.status_code == 403
