"""Add full_logs column to jobs table

Revision ID: 0dd875e71ee0
Revises: 14ce5e28840f
Create Date: 2025-12-24 00:07:21.794617

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0dd875e71ee0"
down_revision: str | None = "14ce5e28840f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("jobs", sa.Column("full_logs", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("jobs", "full_logs")
