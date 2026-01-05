"""merge_heads_lockout_and_main

Revision ID: 543c77da11a6
Revises: 72c9ef3a9782, 9999abcdef01
Create Date: 2026-01-05 13:48:43.226711

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "543c77da11a6"
down_revision: str | None = ("72c9ef3a9782", "9999abcdef01")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
