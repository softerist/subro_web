# backend/app/db/models/job.py
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING  # For Python < 3.10

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base  # Assuming Base is here

if TYPE_CHECKING:
    from app.db.models.user import User  # For type hinting relationship


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    # Assuming user_id from FastAPI-Users is also UUID.
    # If it's int, adjust FASTAPI_USERS_GUID_TYPE or use Integer.
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),  # Use PG_UUID if your users.id is also PG_UUID
        # If users.id is standard UUID, fastapi_users_db_sqlalchemy.generics.GUID might be fine
        # but PG_UUID(as_uuid=True) is safer for consistency with job.id if both are UUIDs in PG
        ForeignKey("users.id", ondelete="SET NULL"),  # Consider ondelete behavior
        index=True,
        nullable=False,  # A job must have a user
    )
    # Corrected relationship string path
    user: Mapped["User"] = relationship(
        "app.db.models.user.User",  # Fully qualified path to the User model
        back_populates="jobs",
    )

    folder_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    # language: Mapped[str | None] = mapped_column(String(10), nullable=True) # Python 3.10+
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)  # Python < 3.10

    status: Mapped[JobStatus] = mapped_column(
        SQLAlchemyEnum(
            JobStatus,
            name="job_status_enum",  # Name for the PostgreSQL ENUM type
            create_type=True,  # Ensures the ENUM type is created in the DB
            values_callable=lambda obj: [e.value for e in obj],  # For compatibility
            # inherit_schema=True, # Usually good, ensures ENUM is in the correct schema if you use multiple PG schemas
        ),
        default=JobStatus.PENDING,
        nullable=False,
        index=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # Let the DB handle default timestamp
        nullable=False,
    )
    # started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True) # Python 3.10+
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Python < 3.10
    # completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True) # Python 3.10+
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Python < 3.10

    # result_message: Mapped[str | None] = mapped_column(Text, nullable=True) # Python 3.10+
    result_message: Mapped[str | None] = mapped_column(Text, nullable=True)  # Python < 3.10
    # exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True) # Python 3.10+
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Python < 3.10
    # log_snippet: Mapped[str | None] = mapped_column(Text, nullable=True) # Python 3.10+
    log_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)  # Python < 3.10

    # celery_task_id: Mapped[str | None] = mapped_column( # Python 3.10+
    celery_task_id: Mapped[str | None] = mapped_column(  # Python < 3.10
        String(255),  # Celery task IDs are usually UUIDs, but string is safer
        index=True,
        unique=True,  # Ensure task IDs are unique if they are primary identifiers for Celery tasks
        nullable=True,  # Might be null before task is sent, or if sending fails
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, status='{self.status.value}', user_id='{self.user_id}')>"
