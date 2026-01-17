# backend/app/api/routers/audit.py
"""
Audit log API endpoints (admin-only).

Provides:
- List audit logs with cursor pagination and filtering
- Get single audit entry
- Export logs (async job)
- Aggregate statistics
- Verify integrity (hash chain)
"""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.users import get_current_active_admin_user
from app.db.models.audit_log import AuditLog
from app.db.models.user import User
from app.db.session import get_async_session
from app.services import audit_service
from app.tasks.audit_export import EXPORT_DIR, run_audit_export
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

audit_router = APIRouter(
    prefix="/admin/audit",
    tags=["Admin - Audit Logs"],
    dependencies=[Depends(get_current_active_admin_user)],
)


def _audit_uuid_filter(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name} format") from err


def _audit_cursor_condition(cursor: str) -> ColumnElement[bool]:
    try:
        ts_part, id_part = cursor.split("_")
        cursor_ts = datetime.fromisoformat(ts_part)
        cursor_id = int(id_part)
    except (ValueError, IndexError) as err:
        raise HTTPException(status_code=400, detail="Invalid cursor format") from err

    return and_(
        AuditLog.timestamp <= cursor_ts,
        and_((AuditLog.timestamp < cursor_ts) | (AuditLog.id < cursor_id)),
    )


def _build_audit_conditions(
    *,
    category: str | None,
    action: str | None,
    severity: str | None,
    actor_user_id: str | None,
    actor_email: str | None,
    target_user_id: str | None,
    resource_type: str | None,
    resource_id: str | None,
    ip_address: str | None,
    success: bool | None,
    start_date: date | None,
    end_date: date | None,
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []

    eq_filters = [
        (category, AuditLog.category),
        (severity, AuditLog.severity),
        (resource_type, AuditLog.resource_type),
        (resource_id, AuditLog.resource_id),
        (ip_address, AuditLog.ip_address),
    ]
    for value, column in eq_filters:
        if value:
            conditions.append(column == value)

    # Action filter uses LIKE for partial matching
    if action:
        conditions.append(AuditLog.action.ilike(f"%{action}%"))

    # Actor email filter uses LIKE for partial matching
    if actor_email:
        conditions.append(AuditLog.actor_email.ilike(f"%{actor_email}%"))

    if actor_user_id:
        conditions.append(
            AuditLog.actor_user_id == _audit_uuid_filter(actor_user_id, "actor_user_id")
        )
    if target_user_id:
        conditions.append(
            AuditLog.target_user_id == _audit_uuid_filter(target_user_id, "target_user_id")
        )
    if success is not None:
        conditions.append(AuditLog.success == success)
    if start_date:
        conditions.append(AuditLog.timestamp >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        conditions.append(
            AuditLog.timestamp < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        )

    return conditions


# --- Schemas ---


class AuditLogRead(BaseModel):
    """Response schema for audit log entries."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: uuid.UUID | str
    timestamp: datetime
    category: str
    action: str
    severity: str
    success: bool

    actor_user_id: uuid.UUID | str | None
    actor_email: str | None
    actor_type: str

    request_id: str | None
    source: str

    ip_address: str
    user_agent: str | None

    resource_type: str | None
    resource_id: str | None
    target_user_id: uuid.UUID | str | None

    error_code: str | None
    http_status: int | None
    details: dict[str, Any] | None


class AuditLogListResponse(BaseModel):
    """Paginated list response with cursor."""

    items: list[AuditLogRead]
    next_cursor: str | None
    total_count: int | None = None


class AuditStatsResponse(BaseModel):
    """Aggregate statistics response."""

    total_events: int
    events_by_category: dict[str, int]
    events_by_severity: dict[str, int]
    events_last_24h: int
    failed_logins_24h: int
    critical_events_24h: int


class AuditExportRequest(BaseModel):
    """Filter schema for export request."""

    category: str | None = None
    action: str | None = None
    severity: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class AuditExportResponse(BaseModel):
    """Job ID response."""

    job_id: str


class AuditExportStatus(BaseModel):
    """Status response for export job."""

    status: str
    progress: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class AuditVerifyResponse(BaseModel):
    """Integrity verification response."""

    verified: bool
    details: dict[str, Any]


# --- Endpoints ---


@audit_router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(get_current_active_admin_user)],
    cursor: str | None = Query(None, description="Filter for pagination"),
    limit: int = Query(50, ge=1, le=100, description="Max items to return"),
    category: str | None = Query(None, description="Filter by category"),
    action: str | None = Query(None, description="Filter by action"),
    severity: str | None = Query(None, description="Filter by severity"),
    actor_user_id: str | None = Query(None, description="Filter by actor user ID"),
    actor_email: str | None = Query(None, description="Filter by actor email"),
    target_user_id: str | None = Query(None, description="Filter by target user ID"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    resource_id: str | None = Query(None, description="Filter by resource ID"),
    ip_address: str | None = Query(None, description="Filter by IP address"),
    success: bool | None = Query(None, description="Filter by success status"),
    start_date: date | None = Query(None, description="Filter from date"),
    end_date: date | None = Query(None, description="Filter to date"),
    include_count: bool = Query(False, description="Include total count (slow)"),
) -> AuditLogListResponse:
    """List audit logs with cursor-based pagination and filters."""
    # Log the audit access
    await audit_service.log_event(
        db,
        category="admin",
        action="admin.audit.view",
        details={"filter_used": bool(category or action or actor_user_id)},
    )

    query = select(AuditLog).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())

    conditions = _build_audit_conditions(
        category=category,
        action=action,
        severity=severity,
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        target_user_id=target_user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        success=success,
        start_date=start_date,
        end_date=end_date,
    )

    # Cursor pagination logic
    if cursor:
        conditions.append(_audit_cursor_condition(cursor))

    if conditions:
        query = query.where(and_(*conditions))

    # Total count (optional, can be slow)
    total_count = None
    if include_count:
        count_query = select(func.count()).select_from(AuditLog)
        if conditions:
            count_query = count_query.where(and_(*conditions))
        total_count = (await db.execute(count_query)).scalar()

    # Execute
    result = await db.execute(query.limit(limit + 1))
    items = list(result.scalars().all())

    # Get next cursor
    next_cursor = None
    if len(items) > limit:
        next_item = items.pop()
        next_cursor = f"{next_item.timestamp.isoformat()}_{next_item.id}"

    return AuditLogListResponse(
        items=[AuditLogRead.model_validate(i) for i in items],
        next_cursor=next_cursor,
        total_count=total_count,
    )


@audit_router.get("/stats", response_model=AuditStatsResponse)
async def get_audit_stats(
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> AuditStatsResponse:
    """Get aggregate audit statistics."""
    now = datetime.now(UTC)
    last_24h = now - timedelta(hours=24)

    # Basic counts
    total_stmt = select(func.count(AuditLog.id))
    total_count = (await db.execute(total_stmt)).scalar() or 0

    last_24h_stmt = select(func.count(AuditLog.id)).where(AuditLog.timestamp >= last_24h)
    last_24h_count = (await db.execute(last_24h_stmt)).scalar() or 0

    # Grouped stats
    cat_stmt = select(AuditLog.category, func.count(AuditLog.id)).group_by(AuditLog.category)
    cat_res = await db.execute(cat_stmt)
    by_category: dict[str, int] = {row[0]: row[1] for row in cat_res.all()}

    sev_stmt = select(AuditLog.severity, func.count(AuditLog.id)).group_by(AuditLog.severity)
    sev_res = await db.execute(sev_stmt)
    by_severity: dict[str, int] = {row[0]: row[1] for row in sev_res.all()}

    # Specific security stats
    failed_logins_stmt = select(func.count(AuditLog.id)).where(
        and_(
            AuditLog.action == "auth.login",
            AuditLog.success.is_(False),
            AuditLog.timestamp >= last_24h,
        )
    )
    failed_logins_24h = (await db.execute(failed_logins_stmt)).scalar() or 0

    critical_stmt = select(func.count(AuditLog.id)).where(
        and_(AuditLog.severity == "critical", AuditLog.timestamp >= last_24h)
    )
    critical_events_24h = (await db.execute(critical_stmt)).scalar() or 0

    return AuditStatsResponse(
        total_events=total_count,
        events_by_category=by_category,
        events_by_severity=by_severity,
        events_last_24h=last_24h_count,
        failed_logins_24h=failed_logins_24h,
        critical_events_24h=critical_events_24h,
    )


@audit_router.post("/export", response_model=AuditExportResponse)
async def export_audit_logs(
    filters: AuditExportRequest,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(get_current_active_admin_user)],
) -> AuditExportResponse:
    """Start an asynchronous audit log export."""
    # Audit Log: Export Initiation
    await audit_service.log_event(
        db,
        category="admin",
        action="admin.audit.export",
        details=filters.model_dump(exclude_none=True),
    )

    filters_dict = filters.model_dump(exclude_none=True, mode="json")
    task = run_audit_export.delay(filters_dict, str(current_user.id))
    return AuditExportResponse(job_id=task.id)


@audit_router.get("/export/status/{job_id}", response_model=AuditExportStatus)
async def get_export_status(job_id: str) -> AuditExportStatus:
    """Get the status of an export job."""
    res = celery_app.AsyncResult(job_id)
    if res.state == "PENDING":
        return AuditExportStatus(status="PENDING")
    elif res.state == "PROGRESS":
        return AuditExportStatus(status="PROCESSING", progress=res.info)
    elif res.state == "SUCCESS":
        return AuditExportStatus(status="COMPLETED", result=res.result)
    elif res.state == "FAILURE":
        return AuditExportStatus(status="FAILED", result={"error": str(res.info)})
    return AuditExportStatus(status=res.state)


@audit_router.get("/export/download/{filename}")
async def download_audit_export(filename: str) -> FileResponse:
    """Download a completed audit log export file."""
    # Basic path traversal protection
    if ".." in filename or filename.startswith("/"):
        raise HTTPException(status_code=403, detail="Invalid filename")

    filepath = EXPORT_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path=filepath, filename=filename, media_type="application/json")


@audit_router.post("/verify", response_model=AuditVerifyResponse)
async def verify_audit_integrity(
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> AuditVerifyResponse:
    """Verify the cryptographic integrity of the audit log hash chain."""
    logger.info("Admin initiated audit log integrity verification.")

    result = await audit_service.verify_log_integrity(db, limit=1000)

    # Audit the verification action itself
    await audit_service.log_event(
        db,
        category="admin",
        action="admin.audit.verify",
        success=result["verified"],
        details={
            "checked_count": result["checked_count"],
            "corrupted_count": len(result["issues"]),
        },
    )
    await db.commit()

    return AuditVerifyResponse(
        verified=result["verified"],
        details={
            "checked_count": result["checked_count"],
            "corrupted_count": len(result["issues"]),
            "issues": result["issues"][:10],  # Return first 10 for display
        },
    )


@audit_router.get("/{event_id}", response_model=AuditLogRead)
async def get_audit_log(
    event_id: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> AuditLogRead:
    """Get a single audit log entry by event_id."""
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid event_id format",
        ) from err

    result = await db.execute(select(AuditLog).where(AuditLog.event_id == event_uuid))
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit log entry not found",
        )

    return AuditLogRead.model_validate(item)
