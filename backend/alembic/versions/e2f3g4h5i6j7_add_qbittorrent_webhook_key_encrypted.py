"""Add qbittorrent_webhook_key_encrypted column.

Revision ID: e2f3g4h5i6j7
Revises: d1e2f3g4h5i6
Create Date: 2026-01-17 13:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2f3g4h5i6j7"
down_revision: str | None = "d1e2f3g4h5i6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add qbittorrent_webhook_key_encrypted column to app_settings table."""
    op.add_column(
        "app_settings",
        sa.Column("qbittorrent_webhook_key_encrypted", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove qbittorrent_webhook_key_encrypted column."""
    op.drop_column("app_settings", "qbittorrent_webhook_key_encrypted")
