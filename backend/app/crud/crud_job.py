# backend/app/crud/crud_job.py
import logging
from datetime import (
    UTC,  # For datetime.now(timezone.utc)
    datetime,  # For datetime.now(timezone.utc)
)
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.crud.base import CRUDBase  # Assuming CRUDBase is defined correctly
from app.db.models.job import Job, JobStatus  # Import JobStatus enum from model
from app.schemas.job import JobCreateInternal, JobUpdate  # Import JobUpdate schema

logger = logging.getLogger(__name__)


class CRUDJob(CRUDBase[Job, JobCreateInternal, JobUpdate]):
    # The base class 'create' and 'get' methods are generally sufficient if
    # JobCreateInternal and JobUpdate schemas are well-defined and handled by the API layer.

    async def get_multi_by_owner(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        skip: int = 0,
        limit: int = 100,
        order_by: ColumnElement | list[ColumnElement] | None = None,
    ) -> list[Job]:
        """
        Retrieve multiple jobs belonging to a specific user, with default ordering.
        """
        logger.debug(f"Fetching jobs for user_id: {user_id}, skip: {skip}, limit: {limit}")
        stmt = select(self.model).where(self.model.user_id == user_id).offset(skip).limit(limit)
        if order_by is not None:
            if isinstance(order_by, list):
                stmt = stmt.order_by(*order_by)
            else:
                stmt = stmt.order_by(order_by)
        else:  # Default ordering for jobs owned by a user
            stmt = stmt.order_by(desc(self.model.submitted_at))  # Newest first

        result = await db.execute(stmt)
        jobs = list(result.scalars().all())
        logger.debug(f"Found {len(jobs)} jobs for user_id: {user_id}")
        return jobs

    async def get_multi(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        order_by: ColumnElement | list[ColumnElement] | None = None,
    ) -> list[Job]:
        """
        Retrieve multiple jobs, with default ordering by submission time descending for all jobs.
        This is typically used by admin users.
        """
        logger.debug(f"Fetching all jobs, skip: {skip}, limit: {limit}")
        if order_by is None:  # Default order for all jobs if not specified by caller
            order_by = desc(self.model.submitted_at)  # Newest first

        # Call super().get_multi which now accepts order_by
        jobs = await super().get_multi(db, skip=skip, limit=limit, order_by=order_by)
        logger.debug(f"Found {len(jobs)} total jobs.")
        return jobs


async def update_job_completion_details(
    self,
    db: AsyncSession,
    *,
    job_id: UUID,
    status: JobStatus,
    completed_at: datetime | None = None,
    exit_code: int | None = None,
    result_message: str | None = None,
    log_snippet: str | None = None,
    started_at: datetime | None = None,
) -> Job | None:
    """
    Updates job status and other completion or running details using JobUpdate schema.
    Fetches the job by ID to ensure operating on the latest state.
    The actual commit to the database is expected to be handled by the caller.
    """
    logger.info(
        f"Updating job {job_id} to status: {status.value if isinstance(status, JobStatus) else status}"
    )

    db_job = await self.get(db, id=job_id)
    if not db_job:
        logger.warning(f"Job {job_id} not found for update_job_completion_details.")
        return None

    # Create the update data dictionary with non-None values
    update_data_dict = self._prepare_update_data(
        db_job, status, completed_at, exit_code, result_message, log_snippet, started_at
    )

    try:
        # Create JobUpdate schema instance from the dictionary
        update_schema = JobUpdate(**update_data_dict)
        logger.debug(
            f"JobUpdate schema for job {job_id}: {update_schema.model_dump(exclude_unset=True)}"
        )
        return await self.update(db, db_obj=db_job, obj_in=update_schema)
    except Exception as e:
        logger.error(f"Error creating JobUpdate schema for job {job_id}: {e}", exc_info=True)
        return None


def _prepare_update_data(
    self,
    db_job: Job,
    status: JobStatus,
    completed_at: datetime | None,
    exit_code: int | None,
    result_message: str | None,
    log_snippet: str | None,
    started_at: datetime | None,
) -> dict:
    """
    Prepares update data dictionary based on the job status and provided parameters.
    Handles the automatic setting of started_at and completed_at timestamps.
    """
    # Initialize with required status
    update_data = {"status": status}

    # Add non-None fields
    if result_message is not None:
        update_data["result_message"] = result_message
    if exit_code is not None:
        update_data["exit_code"] = exit_code
    if log_snippet is not None:
        update_data["log_snippet"] = log_snippet

    current_time_utc = datetime.now(UTC)

    # Handle started_at timestamp
    update_data = self._handle_started_at(update_data, db_job, status, started_at, current_time_utc)

    # Handle completed_at timestamp
    update_data = self._handle_completed_at(
        update_data, db_job, status, completed_at, current_time_utc
    )

    return update_data


@staticmethod
def _handle_started_at(
    update_data: dict,
    db_job: Job,
    status: JobStatus,
    started_at: datetime | None,
    current_time_utc: datetime,
) -> dict:
    """Handle the started_at timestamp logic."""
    # If started_at is explicitly provided
    if started_at is not None:
        update_data["started_at"] = started_at
    # If transitioning to RUNNING and not already started
    elif status == JobStatus.RUNNING and not db_job.started_at:
        update_data["started_at"] = current_time_utc
        logger.debug(f"Setting started_at for job {db_job.id} to {current_time_utc}")

    return update_data


@staticmethod
def _handle_completed_at(
    update_data: dict,
    db_job: Job,
    status: JobStatus,
    completed_at: datetime | None,
    current_time_utc: datetime,
) -> dict:
    """Handle the completed_at timestamp logic."""
    # Define terminal states
    terminal_states = [JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED]

    # If completed_at is explicitly provided
    if completed_at is not None:
        update_data["completed_at"] = completed_at
    # If transitioning to a terminal state and not already completed
    elif status in terminal_states and not db_job.completed_at:
        update_data["completed_at"] = current_time_utc
        logger.debug(f"Setting completed_at for job {db_job.id} to {current_time_utc}")

        # Ensure started_at is set if job moves to a completed state directly
        if not db_job.started_at and "started_at" not in update_data:
            # Use submitted_at as a fallback
            update_data["started_at"] = db_job.submitted_at
            logger.debug(
                f"Setting fallback started_at for job {db_job.id} to {update_data['started_at']}"
            )

    return update_data


# Instantiate the CRUDJob object for easy importing
job = CRUDJob(Job)
