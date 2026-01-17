# backend/app/tasks/audit_export.py
"""
Audit log export task (GZIP JSONL).

Fetches audit logs based on filters, streaming them into a temporary file,
compressing, and storing for admin download.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from celery import Task
from sqlalchemy import and_, select
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import settings
from app.db import session as db_session  # Import module, not variable
from app.db.models.audit_log import AuditLog
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

EXPORT_DIR = Path("/app/exports/audit")


def _make_export_filename(job_id: str) -> str:
    return f"audit_export_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{job_id[:8]}.json"


def _build_export_conditions(filters: dict[str, str]) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []

    eq_filters = [
        ("category", AuditLog.category),
        ("action", AuditLog.action),
        ("severity", AuditLog.severity),
    ]
    for key, column in eq_filters:
        if filters.get(key):
            conditions.append(column == filters[key])

    if filters.get("start_date"):
        conditions.append(AuditLog.timestamp >= datetime.fromisoformat(filters["start_date"]))
    if filters.get("end_date"):
        conditions.append(AuditLog.timestamp <= datetime.fromisoformat(filters["end_date"]))

    return conditions


def _build_export_query(filters: dict[str, str]) -> Select[tuple[AuditLog]]:
    query = select(AuditLog).order_by(AuditLog.timestamp.desc())
    conditions = _build_export_conditions(filters)
    if conditions:
        query = query.where(and_(*conditions))
    return query


def _serialize_audit_row(row: AuditLog) -> dict[str, Any]:
    return {
        "event_id": str(row.event_id),
        "timestamp": row.timestamp.isoformat(),
        "category": row.category,
        "action": row.action,
        "severity": row.severity,
        "success": row.success,
        "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
        "actor_email": row.actor_email,
        "actor_type": row.actor_type,
        "ip_address": row.ip_address,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "http_status": row.http_status,
        "details": row.details,
    }


async def _run_audit_export_task(
    task: Task, filters: dict[str, str], actor_user_id: str
) -> dict[str, Any]:
    db_session.initialize_worker_db_resources()
    if db_session.WorkerSessionLocal is None:
        raise RuntimeError("WorkerSessionLocal not initialized")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    job_id = task.request.id
    filename = _make_export_filename(job_id)
    filepath = EXPORT_DIR / filename

    async with db_session.WorkerSessionLocal() as db:
        result = await db.execute(_build_export_query(filters))
        count = 0
        with filepath.open("w", encoding="utf-8") as f:
            for row in result.scalars():
                f.write(json.dumps(_serialize_audit_row(row)) + "\n")
                count += 1
                if count % 100 == 0:
                    task.update_state(
                        state="PROGRESS",
                        meta={"count": count, "actor_user_id": actor_user_id},
                    )

    logger.info(
        "Audit export complete: %s records -> %s (actor_user_id=%s)",
        count,
        filepath,
        actor_user_id,
    )
    return {
        "status": "COMPLETED",
        "count": count,
        "filename": filename,
        "filepath": str(filepath),
        "actor_user_id": actor_user_id,
        "download_url": f"{settings.API_V1_STR}/admin/audit/export/download/{filename}",
    }


@celery_app.task(name="app.tasks.audit.run_audit_export", bind=True)
def run_audit_export(self: Task, filters: dict[str, str], actor_user_id: str) -> dict[str, Any]:
    """
    Celery task to export audit logs.

    Args:
        filters: Dictionary of filters (category, action, severity, start_date, end_date)
        actor_user_id: The admin who initiated the export
    """
    import asyncio

    try:
        return asyncio.run(_run_audit_export_task(self, filters, actor_user_id))
    except Exception as exc:
        logger.error("Audit export failed", exc_info=exc)
        self.update_state(state="FAILURE", meta={"error": str(exc), "actor_user_id": actor_user_id})
        raise
