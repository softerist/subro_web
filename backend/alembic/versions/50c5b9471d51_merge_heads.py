"""merge_heads

Revision ID: 50c5b9471d51
Revises: e2f3g4h5i6j7, f1a2b3c4d5e6
Create Date: 2026-01-18 14:08:27.671962

"""

from alembic import op
from typing import Sequence, Union
from collections.abc import Sequence
from sqlalchemy.dialects import postgresql  # For explicit ENUM drop
import sqlalchemy as sa
import fastapi_users_db_sqlalchemy  # Make sure this import is present for generics.GUID



# revision identifiers, used by Alembic.
revision: str = '50c5b9471d51'
down_revision: Union[str, None] = ('e2f3g4h5i6j7', 'f1a2b3c4d5e6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    pass

def downgrade() -> None:
    """Downgrade schema."""
    pass
