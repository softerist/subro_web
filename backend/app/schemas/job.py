# backend/app/schemas/job.py
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, constr

# Import JobStatus Enum directly from the model for consistency
from app.db.models.job import JobStatus


# Common base for Job schemas to avoid repetition
class JobBase(BaseModel):
    folder_path: str = Field(
        min_length=1, max_length=1024, description="Absolute path to the media folder"
    )
    language: constr(max_length=10) | None = Field(
        default=None,
        description="Optional language code (e.g., 'en', 'es-ES')",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level for the job (DEBUG, INFO, WARNING, ERROR)",
        pattern="^(DEBUG|INFO|WARNING|ERROR)$",
    )


# Schema for creating a new job (input from API consumer)
class JobCreate(JobBase):
    # Inherits folder_path and language from JobBase
    pass


# Schema for internal use, e.g., when creating a job with user_id already known
class JobCreateInternal(JobCreate):
    user_id: uuid.UUID


# Schema for updating a job (input for PATCH requests or internal updates)
# This schema defines all fields that *could* be updated on a job.
# API endpoints will control which fields are actually settable by users/admins.
class JobUpdate(BaseModel):
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
        default=None,
        max_length=2048,
        description="A brief message about the job's outcome",  # Increased max_length
    )
    exit_code: int | None = Field(default=None, description="The exit code of the executed script")
    log_snippet: str | None = Field(
        default=None,
        description="A snippet of the job's logs, especially errors",  # Potentially large
    )
    full_logs: str | None = Field(
        default=None,
        description="Complete logs from job execution",
    )
    # New fields from model, typically set by the worker, not direct user update
    script_command: str | None = Field(default=None, description="The command executed for the job")
    script_pid: int | None = Field(
        default=None, description="The Process ID of the executed script"
    )
    celery_task_id: str | None = Field(
        default=None, max_length=255, description="The Celery task ID associated with this job"
    )

    # Pydantic V2 model configuration
    model_config = ConfigDict(
        from_attributes=True,  # Allows constructing from ORM models
        # use_enum_values=True, # If enums should be string values in requests
    )


# Schema for representing a full job in API responses
class JobRead(JobBase):  # Inherit common fields from JobBase
    id: uuid.UUID
    user_id: uuid.UUID
    status: JobStatus
    submitted_at: datetime
    updated_at: datetime  # Added: Timestamp of the last update
    started_at: datetime | None = None
    completed_at: datetime | None = None

    result_message: str | None = None
    exit_code: int | None = None
    log_snippet: str | None = None

    script_command: str | None = None  # Added: The command executed
    script_pid: int | None = None  # Added: PID of the script

    celery_task_id: str | None = None

    # Pydantic V2 model configuration
    model_config = ConfigDict(
        from_attributes=True,  # Allows Pydantic to map ORM model attributes to schema fields
        use_enum_values=True,  # Ensures enum values (e.g., "RUNNING") are used in responses, not Enum members
    )


# Schema for a simpler representation, e.g., for paginated lists
class JobReadLite(BaseModel):
    id: uuid.UUID
    folder_path: str
    status: JobStatus
    submitted_at: datetime
    updated_at: datetime  # Added: Often useful to see when it was last touched
    language: str | None = None
    user_id: uuid.UUID

    # Pydantic V2 model configuration
    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )


# Schema for paginated list responses, using JobRead (full detail per job)
class JobListResponse(BaseModel):
    jobs: list[
        JobRead
    ]  # Changed from JobReadLite for more detail in lists, can be reverted if lite is preferred
    total: int
    page: int
    size: int
    pages: int


# Schema for responses that just need to return a job ID (e.g., after creation)
class JobIdResponse(BaseModel):
    job_id: uuid.UUID
