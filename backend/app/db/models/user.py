from datetime import datetime
from typing import Literal

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import String, Boolean, TIMESTAMP, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Define a Base class for declarative models
# It's good practice to have a central Base for all models
class Base(DeclarativeBase):
    pass

# Define the User model inheriting from fastapi-users' base and our Base
class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"  # Explicitly define table name

    # fastapi-users provides:
    # id: Mapped[UUID]
    # email: Mapped[str]
    # hashed_password: Mapped[str]
    # is_active: Mapped[bool]
    # is_superuser: Mapped[bool] # We might rename/remap this conceptually to 'admin'
    # is_verified: Mapped[bool] # We might not use this initially

    # --- Custom Fields ---
    # Add a 'role' field with specific allowed values
    role: Mapped[Literal["admin", "standard"]] = mapped_column(
        String(20), nullable=False, server_default="standard", index=True
    )

    # Add timestamps (optional but recommended)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Consider renaming is_superuser if 'admin' role is the primary distinction
    # If is_superuser maps directly to your 'admin' role, you might not need
    # the separate 'role' field, or you can sync them.
    # For clarity, let's keep 'role' distinct for now.
    # We'll map fastapi-users' superuser concept to our 'admin' role later.
