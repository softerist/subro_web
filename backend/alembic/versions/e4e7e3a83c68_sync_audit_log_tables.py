"""sync_audit_log_tables

Revision ID: e4e7e3a83c68
Revises: 543c77da11a6
Create Date: 2026-01-05 13:52:09.658578

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4e7e3a83c68"
down_revision: str | None = "543c77da11a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Register the models but don't drop existing partitions.
    # The background maintenance task handles partitions.

    # Upgrade schema
    # Use inspector to check if index exists to avoid errors on retry
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("audit_logs"):
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), primary_key=True, nullable=False),
            sa.Column("category", sa.String(length=50), nullable=False),
            sa.Column("action", sa.String(length=100), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False, server_default="info"),
            sa.Column("success", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("actor_email", sa.String(length=255), nullable=True),
            sa.Column("actor_type", sa.String(length=20), nullable=False, server_default="user"),
            sa.Column("request_id", sa.String(length=64), nullable=True),
            sa.Column("session_id", sa.String(length=64), nullable=True),
            sa.Column("source", sa.String(length=20), nullable=False, server_default="web"),
            sa.Column("ip_address", sa.String(length=45), nullable=False),
            sa.Column("forwarded_for", sa.Text(), nullable=True),
            sa.Column("user_agent", sa.String(length=512), nullable=True),
            sa.Column("resource_type", sa.String(length=50), nullable=True),
            sa.Column("resource_id", sa.String(length=255), nullable=True),
            sa.Column("target_user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("error_code", sa.String(length=100), nullable=True),
            sa.Column("http_status", sa.SmallInteger(), nullable=True),
            sa.Column("details", postgresql.JSONB(), nullable=True),
            sa.Column("schema_version", sa.SmallInteger(), nullable=False, server_default="1"),
            sa.Column("prev_hash", sa.String(length=64), nullable=True),
            sa.Column("event_hash", sa.String(length=64), nullable=True),
            postgresql_partition_by="RANGE (timestamp)",
        )

    if not insp.has_table("audit_outbox"):
        op.create_table(
            "audit_outbox",
            sa.Column("id", sa.BigInteger(), primary_key=True),
            sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("event_data", postgresql.JSONB(), nullable=False),
            sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("failed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )

    indexes = insp.get_indexes("audit_outbox")
    has_pending_index = any(i["name"] == "ix_outbox_pending" for i in indexes)

    with op.batch_alter_table("audit_outbox", schema=None) as batch_op:
        if has_pending_index:
            batch_op.drop_index("ix_outbox_pending")

        batch_op.create_index(batch_op.f("ix_audit_outbox_failed"), ["failed"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_audit_outbox_next_attempt_at"), ["next_attempt_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_audit_outbox_processed"), ["processed"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("audit_outbox", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_outbox_processed"))
        batch_op.drop_index(batch_op.f("ix_audit_outbox_next_attempt_at"))
        batch_op.drop_index(batch_op.f("ix_audit_outbox_failed"))
        batch_op.create_index(
            "ix_outbox_pending",
            ["next_attempt_at"],
            unique=False,
            postgresql_where="((processed = false) AND (failed = false))",
        )
