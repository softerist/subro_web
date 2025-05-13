"""

Revision ID: 1ee98b12246a
Revises: 324d2b7e04ef
Create Date: 2025-05-09 07:27:20.287468

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "1ee98b12246a"
down_revision: str | None = "324d2b7e04ef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
