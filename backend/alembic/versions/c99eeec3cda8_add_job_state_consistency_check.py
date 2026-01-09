"""add_job_state_consistency_check

Revision ID: c99eeec3cda8
Revises: 390d97d11c6f
Create Date: 2026-01-10 00:24:13.209096

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c99eeec3cda8"
down_revision: str | None = "390d97d11c6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        "check_running_has_celery_task_id",
        "jobs",
        "(status NOT IN ('RUNNING', 'CANCELLING')) OR (celery_task_id IS NOT NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("check_running_has_celery_task_id", "jobs", type_="check")
