"""merge webhook heads

Revision ID: 1be63a1e948c
Revises: a1b2c3d4e5f6, cf2d4e6f8g0h
Create Date: 2026-01-11 12:40:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "1be63a1e948c"
down_revision: str | Sequence[str] | None = ("a1b2c3d4e5f6", "cf2d4e6f8g0h")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge heads."""
    pass


def downgrade() -> None:
    """Downgrade merge head (no-op)."""
    pass
