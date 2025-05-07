# backend/app/db/base_class.py
# Remove unused imports like Mapped, mapped_column, Column, String, PG_UUID, uuid if not used directly in THIS file for mixins etc.

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


# Create the base class for all SQLAlchemy models.
# All models should inherit from this Base.
class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models in the application.
    It includes a shared MetaData object with a naming convention.
    """

    metadata = metadata_obj


# You could also define Base more simply if you prefer the older style,
# but `class Base(DeclarativeBase): metadata = metadata_obj` is the modern way.
# Older style (also works):
# Base = declarative_base(metadata=metadata_obj)
