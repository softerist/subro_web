"""merge_heads

Revision ID: 50c5b9471d51
Revises: e2f3g4h5i6j7, f1a2b3c4d5e6
Create Date: 2026-01-18 14:08:27.671962

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "50c5b9471d51"
down_revision: str | None = ("e2f3g4h5i6j7", "f1a2b3c4d5e6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
