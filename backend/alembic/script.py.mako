"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""

from alembic import op
from typing import Sequence, Union
from collections.abc import Sequence
from sqlalchemy.dialects import postgresql  # For explicit ENUM drop
import sqlalchemy as sa
import fastapi_users_db_sqlalchemy  # Make sure this import is present for generics.GUID

${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}

def upgrade() -> None:
    """Upgrade schema."""
    ${upgrades if upgrades else "pass"}

def downgrade() -> None:
    """Downgrade schema."""
    ${downgrades if downgrades else "pass"}
