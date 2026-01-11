"""ghost migration to fix production out of sync

Revision ID: 1be63a1e948c
Revises: cf2d4e6f8g0h
Create Date: 2026-01-11 19:15:00.000000
"""

# revision identifiers, used by Alembic.
revision = "1be63a1e948c"
down_revision = "cf2d4e6f8g0h"
branch_labels = None
depends_on = None


def upgrade():
    # This migration is a ghost used to synchronize a database that already
    # applied a revision which was subsequently removed from the codebase.
    pass


def downgrade():
    pass
