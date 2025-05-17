# backend/app/schemas/job.py
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, constr  # Added ConfigDict

# Import JobStatus Enum directly from the model for consistency
from app.db.models.job import JobStatus


# Common base for Job schemas to avoid repetition
class JobBase(BaseModel):
    folder_path: str = Field(
        min_length=1, max_length=1024, description="Absolute path to the media folder"
    )
    language: constr(max_length=10) | None = Field(  # constr for validation
        default=None,
        description="Optional language code (e.g., 'en', 'es-ES')",
    )


# Schema for creating a new job (input from API consumer)
class JobCreate(JobBase):
    # Inherits folder_path and language from JobBase
    pass


# Schema for internal use, e.g., when creating a job with user_id already known
class JobCreateInternal(JobCreate):
    user_id: uuid.UUID


# Schema for updating a job (input for PATCH requests)
class JobUpdate(BaseModel):  # Not inheriting JobBase, as not all fields are always updated
    folder_path: str | None = Field(
        default=None, min_length=1, max_length=1024, description="Absolute path to the media folder"
    )
    language: constr(max_length=10) | None = Field(
        default=None,
        description="Optional language code (e.g., 'en', 'es-ES')",
    )
    status: JobStatus | None = Field(default=None, description="The current status of the job")
    started_at: datetime | None = Field(
        default=None, description="Timestamp when the job started processing"
    )
    completed_at: datetime | None = Field(
        default=None, description="Timestamp when the job completed or failed"
    )
    result_message: str | None = Field(
        default=None, max_length=1024, description="A brief message about the job's outcome"
    )  # Added max_length
    exit_code: int | None = Field(default=None, description="The exit code of the executed script")
    log_snippet: str | None = Field(
        default=None, description="A snippet of the job's logs, especially errors"
    )  # Potentially large, consider max_length if storing fixed size
    celery_task_id: str | None = Field(
        default=None, max_length=255, description="The Celery task ID associated with this job"
    )  # Added max_length

    # Pydantic V2 model configuration
    model_config = ConfigDict(
        from_attributes=True,  # Useful if you ever construct this from a model instance
        # use_enum_values=True, # If you want enums as strings in requests/responses
    )


# Schema for representing a full job in API responses
class JobRead(JobBase):  # Inherit from JobBase
    id: uuid.UUID
    user_id: uuid.UUID
    status: JobStatus
    submitted_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result_message: str | None = None
    exit_code: int | None = None
    log_snippet: str | None = None
    celery_task_id: str | None = None

    # Pydantic V2 model configuration
    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,  # Good practice for enums in responses
    )


# Schema for a simpler representation, e.g., for paginated lists
class JobReadLite(BaseModel):  # Not inheriting JobBase to be selective
    id: uuid.UUID
    folder_path: str  # Keep this as it's key info
    status: JobStatus
    submitted_at: datetime
    language: str | None = None  # Using simple str for lite view, constr validation on create
    user_id: uuid.UUID  # Often useful to know who submitted it

    # Pydantic V2 model configuration
    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,  # Good practice for enums in responses
    )
