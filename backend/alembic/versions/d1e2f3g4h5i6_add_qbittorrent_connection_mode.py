"""Add qbittorrent_connection_mode column.

Revision ID: d1e2f3g4h5i6
Revises: cf2d4e6f8g0h
Create Date: 2026-01-17 12:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e2f3g4h5i6"
down_revision: str | Sequence[str] | None = ("cf2d4e6f8g0h", "c99eeec3cda8", "1be63a1e948c")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add qbittorrent_connection_mode column to app_settings table."""
    op.add_column(
        "app_settings",
        sa.Column(
            "qbittorrent_connection_mode",
            sa.String(length=50),
            nullable=True,
            server_default="direct",
        ),
    )


def downgrade() -> None:
    """Remove qbittorrent_connection_mode column."""
    op.drop_column("app_settings", "qbittorrent_connection_mode")
