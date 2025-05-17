# backend/app/schemas/job.py
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, constr

# Import JobStatus Enum directly from the model for consistency
from app.db.models.job import JobStatus


# Schema for creating a new job (input from API consumer)
class JobCreate(BaseModel):
    folder_path: str = Field(
        ..., min_length=1, max_length=1024, description="Absolute path to the media folder"
    )
    language: constr(max_length=10) | None = Field(  # Use Optional for Python < 3.10
        # language: str | None = Field( # Use this for Python 3.10+
        default=None,
        description="Optional language code (e.g., 'en', 'es-ES')",
    )


# Schema for representing a job in API responses
class JobRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID  # Assuming user_id is always present on a job
    folder_path: str
    language: str | None = None  # Python < 3.10
    # language: str | None = None # Python 3.10+
    status: JobStatus  # Use the imported Enum
    submitted_at: datetime
    started_at: datetime | None = None  # Python < 3.10
    # started_at: datetime | None = None # Python 3.10+
    completed_at: datetime | None = None  # Python < 3.10
    # completed_at: datetime | None = None # Python 3.10+
    result_message: str | None = None  # Python < 3.10
    # result_message: str | None = None # Python 3.10+
    exit_code: int | None = None  # Python < 3.10
    # exit_code: int | None = None # Python 3.10+
    log_snippet: str | None = None  # Python < 3.10
    # log_snippet: str | None = None # Python 3.10+
    celery_task_id: str | None = None  # Python < 3.10
    # celery_task_id: str | None = None # Python 3.10+

    class Config:
        from_attributes = True  # Pydantic V2 (orm_mode = True in V1)
        # Consider adding:
        # use_enum_values = True # To serialize Enum members to their values (e.g., "PENDING" string)


# Schema for a simpler representation, e.g., for paginated lists
class JobReadLite(BaseModel):
    id: uuid.UUID
    folder_path: str
    status: JobStatus
    submitted_at: datetime
    language: str | None = None  # Python < 3.10
    # language: str | None = None # Python 3.10+
    user_id: uuid.UUID  # Often useful to know who submitted it even in a lite view

    class Config:
        from_attributes = True
        # use_enum_values = True
