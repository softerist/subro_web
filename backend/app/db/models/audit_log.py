"""
Audit log models for tracking security, admin, and data events.

Implements:
- AuditLog: Main audit table (partitioned by month)
- AuditOutbox: Transactional outbox for reliable logging
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class AuditLog(Base):
    """
    Immutable audit log for security, admin, and data events.

    This table is partitioned by month on 'timestamp' for efficient
    retention and query performance.
    """

    __tablename__ = "audit_logs"

    # Core identifiers
    # For partitioning, we need to include 'timestamp' in the primary key
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,  # Part of composite PK for partitioning
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )

    # Classification
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="info"
    )  # info|warning|error|critical
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Actor (who performed the action)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="user"
    )  # user|system|api_key
    impersonator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    # Request context
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    request_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="web"
    )  # web|api|cli|system

    # Network information
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    forwarded_for: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Target (what was affected)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    # Outcome details
    outcome: Mapped[str] = mapped_column(
        String(20), nullable=False, default="success"
    )  # success|failure|attempt
    reason_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    http_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Metadata / Environment
    service_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Integrity
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        # Ensure action starts with category
        CheckConstraint(
            "action LIKE category || '.%'",
            name="chk_audit_category_action",
        ),
        # Unique constraint including partition key
        UniqueConstraint("event_id", "timestamp", name="uq_audit_logs_event_id_timestamp"),
        # Composite indexes for common query patterns
        Index("ix_audit_category_ts", "category", "timestamp"),
        Index("ix_audit_action_ts", "action", "timestamp"),
        Index("ix_audit_resource", "resource_type", "resource_id", "timestamp"),
        Index("ix_audit_details", "details", postgresql_using="gin"),
        # Enhanced Plan Indexes
        Index("ix_audit_outcome", "outcome", postgresql_where=outcome == "failure"),
        Index("ix_audit_session_id", "session_id", postgresql_where=session_id.isnot(None)),
        Index(
            "ix_audit_security_analysis",
            "ip_address",
            "action",
            "outcome",
            "timestamp",
            postgresql_where=severity.in_(["warning", "critical"]),
        ),
        Index("ix_audit_reason_code", "reason_code", postgresql_where=reason_code.isnot(None)),
        # Postgres Partitioning Clause (SQLAlchemy notation)
        {
            "postgresql_partition_by": "RANGE (timestamp)",
        },
    )

    def __repr__(self) -> str:
        return f"<AuditLog({self.event_id}, {self.action}, {self.actor_email})>"


class AuditOutbox(Base):
    """
    Transactional outbox for reliable audit logging.

    Events are written here in the same transaction as the main action,
    then a background worker moves them to AuditLog with hash chaining.
    """

    __tablename__ = "audit_outbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    event_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Status tracking for the worker
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    failed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    def __repr__(self) -> str:
        return f"<AuditOutbox({self.event_id}, {self.processed})>"
