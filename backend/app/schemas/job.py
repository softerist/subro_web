# backend/app/schemas/job.py
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, constr

# Re-use the JobStatus Enum from the model for consistency in schemas
from app.db.models.job import JobStatus


# Schema for creating a new job (input from user)
class JobCreate(BaseModel):
    folder_path: str = Field(
        ..., min_length=1, max_length=1024, description="Absolute path to the media folder"
    )
    language: constr(max_length=10) | None = Field(
        None, description="Optional language code (e.g., 'en', 'es-ES')"
    )  # For Python 3.9+ use str | None = ...


# Schema for representing a job in API responses (output to user)
class JobRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    folder_path: str
    language: str | None = None  # For Python 3.9+ use str | None
    status: JobStatus
    submitted_at: datetime
    started_at: datetime | None = None  # For Python 3.9+ use datetime | None
    completed_at: datetime | None = None  # For Python 3.9+ use datetime | None
    result_message: str | None = None  # For Python 3.9+ use str | None
    exit_code: int | None = None  # For Python 3.9+ use int | None
    log_snippet: str | None = None  # For Python 3.9+ use str | None
    celery_task_id: str | None = None  # For Python 3.9+ use str | None

    class Config:
        from_attributes = True  # For Pydantic V2 (was orm_mode = True in V1)
        # Allows creating schema instances from ORM objects


# Schema for a simpler representation, perhaps for lists
class JobReadLite(BaseModel):
    id: uuid.UUID
    folder_path: str
    status: JobStatus
    submitted_at: datetime
    language: str | None = None  # For Python 3.9+ use str | None

    class Config:
        from_attributes = True
