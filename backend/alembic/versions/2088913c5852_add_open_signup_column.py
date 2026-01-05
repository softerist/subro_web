"""add_open_signup_column

Revision ID: 2088913c5852
Revises: c2a670635b4d
Create Date: 2026-01-05 21:28:59.140944

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2088913c5852"
down_revision: str | None = "c2a670635b4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add open_signup column to app_settings."""
    # Add open_signup column with server_default to handle existing rows
    op.add_column(
        "app_settings",
        sa.Column("open_signup", sa.Boolean(), nullable=False, server_default="false"),
    )
    # Remove server_default after column is added
    op.alter_column("app_settings", "open_signup", server_default=None)


def downgrade() -> None:
    """Remove open_signup column from app_settings."""
    op.drop_column("app_settings", "open_signup")
