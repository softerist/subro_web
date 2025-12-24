# backend/app/db/models/job.py
import enum
import uuid
from datetime import datetime
from typing import (  # Using Optional for broader Python compatibility if needed
    TYPE_CHECKING,
)

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,  # For server_default and onupdate
)
from sqlalchemy import Enum as SQLAlchemyEnum  # Renamed to avoid conflict with Python's enum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base  # Assuming Base is correctly imported

if TYPE_CHECKING:
    from app.db.models.user import User  # For type hinting relationship


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"  # New state: cancellation requested, task being terminated
    CANCELLED = "CANCELLED"  # Existing state: task confirmed terminated due to cancellation


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),  # Job deleted if user is deleted
        index=True,
        nullable=False,  # A job must have an associated user
    )
    user: Mapped["User"] = relationship(
        "app.db.models.user.User",  # Fully qualified path for clarity if User is in another module
        back_populates="jobs",
    )

    folder_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    log_level: Mapped[str] = mapped_column(String(10), nullable=False, default="INFO")

    status: Mapped[JobStatus] = mapped_column(
        SQLAlchemyEnum(  # Using the aliased import
            JobStatus,
            name="job_status_enum",  # Explicit name for the PostgreSQL ENUM type
            create_type=True,  # Ensures the ENUM type is created/managed in the DB
            values_callable=lambda obj: [
                e.value for e in obj
            ],  # Recommended for some SQLAlchemy versions/dialects
        ),
        default=JobStatus.PENDING,
        nullable=False,
        index=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # Database handles default timestamp on creation
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Automatically managed timestamp for row updates
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # Default on creation
        onupdate=func.now(),  # Automatically updated by the database on row modification
        nullable=False,
    )

    # Stores a brief message about the job's outcome or current state, e.g., error message, cancellation reason
    result_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Exit code of the executed script, if applicable
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # A snippet of the job's logs, e.g., last N lines or relevant error output
    log_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Complete logs from job execution (stdout + stderr combined)
    full_logs: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The actual command string executed by the Celery worker
    script_command: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The Process ID (PID) of the script subprocess, if captured by the worker
    script_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Stores the Celery task ID, which should be str(job.id)
    # This allows revoking the task using this identifier.
    celery_task_id: Mapped[str | None] = mapped_column(
        String(255),  # Celery task IDs are usually UUIDs as strings
        index=True,
        unique=True,  # Ensures task IDs are unique
        nullable=True,  # Can be null if the job is PENDING and task not yet dispatched
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, status='{self.status.value}', user_id='{self.user_id}')>"
