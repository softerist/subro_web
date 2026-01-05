"""Add app_version column

Revision ID: 9999abcdef01
Revises: 8ca55a47da71
Create Date: 2026-01-05 02:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9999abcdef01"
down_revision: str | None = "690ef37d906e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("app_settings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("app_version", sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("app_settings", schema=None) as batch_op:
        batch_op.drop_column("app_version")
