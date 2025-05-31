# /backend/app/db/models/user.py

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import DateTime, String, func  # text is not needed if no server_default
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.db.models.job import Job


class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"

    role: Mapped[Literal["admin", "standard"]] = mapped_column(
        String(50), default="standard", nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    jobs: Mapped[list["Job"]] = relationship(
        "app.db.models.job.Job",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        is_s_user = getattr(self, "is_superuser", "N/A")
        user_role = getattr(self, "role", "N/A")
        return f"<User(id={self.id!r}, email={self.email!r}, role={user_role!r}, is_superuser={is_s_user!r})>"
