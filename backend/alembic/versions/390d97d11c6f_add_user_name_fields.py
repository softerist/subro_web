"""add_user_name_fields

Revision ID: 390d97d11c6f
Revises: 2088913c5852
Create Date: 2026-01-05 21:32:10.319165

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "390d97d11c6f"
down_revision: str | None = "2088913c5852"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add first_name and last_name columns to users table."""
    op.add_column("users", sa.Column("first_name", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(length=100), nullable=True))


def downgrade() -> None:
    """Remove first_name and last_name columns from users table."""
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
