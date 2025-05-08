# /home/user/subro_web/backend/app/db/models/job.py

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base  # <-- IMPORT YOUR NEW BASE
from app.db.models.user import (
    User,  # No longer need to import User here for relationship if using string reference
)


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Job(Base):  # <-- INHERIT FROM YOUR NEW BASE
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # Use string "User" for forward reference if User model imports Job, avoids circular import issues
    user: Mapped["User"] = relationship(back_populates="jobs")  # type: ignore

    folder_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    language: Mapped[str | None] = mapped_column(String(10))

    status: Mapped[JobStatus] = mapped_column(
        SQLAlchemyEnum(
            JobStatus, name="job_status_enum", create_type=True, inherit_schema=True
        ),  # inherit_schema for Alembic
        default=JobStatus.PENDING,
        nullable=False,
        index=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    result_message: Mapped[str | None] = mapped_column(Text)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    log_snippet: Mapped[str | None] = mapped_column(Text)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), index=True, unique=True)

    # metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, name="metadata")

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, status='{self.status}', folder='{self.folder_path}')>"
