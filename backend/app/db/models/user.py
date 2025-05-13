# /backend/app/db/models/job.py

from datetime import datetime
from typing import TYPE_CHECKING, Literal  # Added List

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base  # Correct import

if TYPE_CHECKING:
    from app.db.models.job import Job  # Keep this for type checking


class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"

    # Fields inherited from SQLAlchemyBaseUserTableUUID are:
    # id: Mapped[GUID] (typically sqlalchemy.UUID)
    # email: Mapped[str]
    # hashed_password: Mapped[str]
    # is_active: Mapped[bool] (server_default=text("true"))
    # is_verified: Mapped[bool] (server_default=text("false"))
    # is_superuser: Mapped[bool] (server_default=text("false"))
    # These already match the server_default patterns in your target migration.

    # --- Custom Fields to Add to the User Model ---
    role: Mapped[Literal["admin", "standard"]] = mapped_column(
        String(50),
        default="standard",
        server_default=text("'standard'"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # --- Relationships ---
    jobs: Mapped[list["Job"]] = relationship(  # Use List for type hint
        "app.db.models.job.Job",  # <--- CHANGE HERE: Use the fully qualified string path
        back_populates="user",
    )

    def __repr__(self) -> str:
        is_s_user = getattr(self, "is_superuser", False)
        return f"<User(id={self.id!r}, email={self.email!r}, role={self.role!r}, is_superuser={is_s_user!r})>"
