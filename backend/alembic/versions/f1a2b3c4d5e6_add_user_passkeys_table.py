# backend/alembic/versions/f1a2b3c4d5e6_add_user_passkeys_table.py
"""Add user_passkeys table for WebAuthn/Passkey support.

Revision ID: f1a2b3c4d5e6
Revises: e4e7e3a83c68
Create Date: 2026-01-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e4e7e3a83c68"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create user_passkeys table for WebAuthn credentials."""
    # Make migration idempotent - check if table exists first
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "user_passkeys" in inspector.get_table_names():
        # Table already exists, skip creation
        return

    op.create_table(
        "user_passkeys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # WebAuthn credential identifier - unique bytes from authenticator
        sa.Column("credential_id", sa.LargeBinary(), nullable=False, unique=True, index=True),
        # COSE-encoded public key
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        # Signature counter for replay attack detection
        sa.Column("sign_count", sa.Integer(), nullable=False, default=0),
        # Transport hints (JSON array: ["usb", "internal", "hybrid", "ble"])
        sa.Column("transports", postgresql.JSON(), nullable=True),
        # Authenticator AAGUID (identifies authenticator model)
        sa.Column("aaguid", sa.String(36), nullable=True),
        # User-friendly device name
        sa.Column("device_name", sa.String(255), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        # Backup flags for synced passkeys
        sa.Column("backup_eligible", sa.Boolean(), nullable=False, default=False),
        sa.Column("backup_state", sa.Boolean(), nullable=False, default=False),
    )

    # Create indexes for performance
    op.create_index(
        "ix_user_passkeys_user_id_credential_id",
        "user_passkeys",
        ["user_id", "credential_id"],
        unique=True,
    )


def downgrade() -> None:
    """Drop user_passkeys table."""
    op.drop_index("ix_user_passkeys_user_id_credential_id", table_name="user_passkeys")
    op.drop_table("user_passkeys")
