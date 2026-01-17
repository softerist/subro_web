"""Add webhook_secret column to app_settings

Revision ID: a1b2c3d4e5f6
Revises: c2a670635b4d
Create Date: 2026-01-10 03:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "c99eeec3cda8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add webhook_secret column for automated webhook authentication."""
    op.add_column(
        "app_settings",
        sa.Column("webhook_secret", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove webhook_secret column."""
    op.drop_column("app_settings", "webhook_secret")
