from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase  # Use DeclarativeBase for modern SQLAlchemy

# Define a naming convention for constraints, useful for Alembic auto-generation
# and ensuring consistent naming across different DBs if you ever switch.
convention = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",  # Adjusted for multi-column indexes if needed
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",  # Adjusted for multi-column uniques
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",  # Adjusted
    "pk": "pk_%(table_name)s",
}

# Create a MetaData instance with the naming convention
# This metadata object will be shared by all models inheriting from Base
metadata_obj = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models in the application.
    It includes a shared MetaData object with a naming convention.
    """

    metadata = metadata_obj
