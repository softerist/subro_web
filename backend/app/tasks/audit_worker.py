# backend/app/tasks/audit_worker.py
"""
Background worker for processing the audit outbox.

Polls the audit_outbox table, computes hash chains, and moves events
to the immutable audit_logs table. Uses SKIP LOCKED for concurrency safety.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session as db_session  # Import module, not variable
from app.db.models.audit_log import AuditLog, AuditOutbox
from app.services.audit_service import compute_event_hash, get_last_hash
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.audit_worker_batch")
def audit_worker_batch_task(batch_size: int = 100):
    """Celery task wrapper for outbox processing."""

    async def _run():
        db_session.initialize_worker_db_resources()
        if db_session.WorkerSessionLocal is None:
            raise RuntimeError("WorkerSessionLocal not initialized")
        async with db_session.WorkerSessionLocal() as db:
            return await process_outbox_batch(db, batch_size)

    return asyncio.run(_run())


async def process_outbox_batch(db: AsyncSession, batch_size: int = 100) -> int:
    """
    Process a batch of outbox events.

    Returns:
        Number of events processed.
    """
    # Select candidate rows with SKIP LOCKED
    now = datetime.now(UTC)

    query = (
        select(AuditOutbox)
        .where(
            AuditOutbox.processed == False,  # noqa: E712
            AuditOutbox.failed == False,  # noqa: E712
            (AuditOutbox.next_attempt_at.is_(None) | (AuditOutbox.next_attempt_at <= now)),
        )
        .order_by(AuditOutbox.created_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )

    result = await db.execute(query)
    outbox_rows = result.scalars().all()

    if not outbox_rows:
        return 0

    processed_count = 0

    for row in outbox_rows:
        try:
            event_data = row.event_data

            # Get previous hash for chaining
            prev_hash_row = await get_last_hash(db, row.created_at)

            # Calculate new hash
            event_hash = compute_event_hash(
                event_id=str(row.event_id),
                timestamp=event_data["timestamp"],
                action=event_data["action"],
                actor_user_id=event_data.get("actor_user_id"),
                target_user_id=event_data.get("target_user_id"),
                resource_type=event_data.get("resource_type"),
                resource_id=event_data.get("resource_id"),
                success=event_data["success"],
                http_status=event_data.get("http_status"),
                details=event_data.get("details"),
                prev_hash=prev_hash_row,
            )

            # Create AuditLog entry
            audit_log = AuditLog(
                event_id=row.event_id,
                timestamp=datetime.fromisoformat(event_data["timestamp"]),
                category=event_data["category"],
                action=event_data["action"],
                severity=event_data["severity"],
                success=event_data["success"],
                actor_user_id=event_data.get("actor_user_id"),
                actor_email=event_data.get("actor_email"),
                actor_type=event_data.get("actor_type", "user"),
                request_id=event_data.get("request_id"),
                session_id=event_data.get("session_id"),
                source=event_data.get("source", "web"),
                ip_address=event_data.get("ip_address"),
                forwarded_for=event_data.get("forwarded_for"),
                user_agent=event_data.get("user_agent"),
                resource_type=event_data.get("resource_type"),
                resource_id=event_data.get("resource_id"),
                target_user_id=event_data.get("target_user_id"),
                error_code=event_data.get("error_code"),
                http_status=event_data.get("http_status"),
                details=event_data.get("details"),
                schema_version=1,
                prev_hash=prev_hash_row,
                event_hash=event_hash,
            )

            db.add(audit_log)

            # Mark outbox as processed
            row.processed = True
            row.processed_at = datetime.now(UTC)
            processed_count += 1

        except Exception as e:
            logger.error(f"Error processing audit outbox event {row.event_id}: {e}", exc_info=True)
            row.attempts += 1
            row.last_error = str(e)

            if row.attempts >= 5:
                row.failed = True
            else:
                # Exponential backoff: 5s, 25s, 125s...
                backoff_seconds = 5**row.attempts
                row.next_attempt_at = now + timedelta(seconds=backoff_seconds)

    await db.commit()
    return processed_count
