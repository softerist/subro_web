from datetime import datetime
from typing import TYPE_CHECKING, Literal  # For Python < 3.9, use List

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import TIMESTAMP, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base  # <-- IMPORT YOUR NEW BASE

if TYPE_CHECKING:
    from app.db.models.job import Job  # Forward reference for Job model


class User(SQLAlchemyBaseUserTableUUID, Base):  # <-- INHERIT FROM YOUR NEW BASE
    __tablename__ = "users"

    role: Mapped[Literal["admin", "standard"]] = mapped_column(
        String(20), nullable=False, server_default="standard", index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationship to Jobs
    jobs: Mapped[list["Job"]] = relationship(back_populates="user", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"
