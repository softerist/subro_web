"""remove legacy webhook secret column

Revision ID: cf2d4e6f8g0h
Revises: b1c2d3e4f5g6
Create Date: 2026-01-10 17:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cf2d4e6f8g0h"
down_revision: str | None = "b1c2d3e4f5g6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the legacy webhook_secret column from app_settings."""
    op.drop_column("app_settings", "webhook_secret")


def downgrade() -> None:
    """Add the legacy webhook_secret column back to app_settings."""
    op.add_column("app_settings", sa.Column("webhook_secret", sa.Text(), nullable=True))
