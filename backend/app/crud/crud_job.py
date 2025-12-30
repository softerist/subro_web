import logging
from datetime import (
    UTC,  # Keeping your import if you prefer it and are on Python 3.11+
    datetime,  # Adding timezone for timezone.utc consistency
)
from typing import Any  # Added for type hint in _prepare_update_data
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.crud.base import CRUDBase
from app.db.models.job import Job, JobStatus
from app.schemas.job import (  # Assuming JobCreateInternal and JobUpdate are defined
    JobCreateInternal,
    JobUpdate,
)

logger = logging.getLogger(__name__)


class CRUDJob(CRUDBase[Job, JobCreateInternal, JobUpdate]):
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

    # MOVED METHODS START HERE (Indented to be part of CRUDJob class) - Preserving your comment
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
        full_logs: str | None = None,
        started_at: datetime | None = None,
        celery_task_id: str | None = None,
    ) -> Job | None:
        """
        Updates job status and other completion or running details using JobUpdate schema.
        Fetches the job by ID to ensure operating on the latest state.
        The actual commit to the database is expected to be handled by the caller.
        """
        logger.info(
            f"Updating job {job_id} to status: {status.value if isinstance(status, JobStatus) else status}"
        )

        db_job = await self.get(db, id=job_id)  # self.get is from CRUDBase
        if not db_job:
            logger.warning(f"Job {job_id} not found for update_job_completion_details.")
            return None

        # Create the update data dictionary with non-None values
        update_data_dict = self._prepare_update_data(  # Calls instance method
            db_job,  # Pass db_job instance
            status,
            completed_at,
            exit_code,
            result_message,
            log_snippet,
            full_logs,
            started_at,
            celery_task_id,
        )

        try:
            # Create JobUpdate schema instance from the dictionary
            update_schema = JobUpdate(**update_data_dict)
            logger.debug(
                f"JobUpdate schema for job {job_id}: {update_schema.model_dump(exclude_unset=True)}"
            )
            return await self.update(
                db, db_obj=db_job, obj_in=update_schema
            )  # self.update from CRUDBase
        except Exception as e:
            logger.error(f"Error creating JobUpdate schema for job {job_id}: {e}", exc_info=True)
            return None

    def _prepare_update_data(
        self,
        db_job: Job,  # Added db_job as it's used by helper methods
        status: JobStatus,
        completed_at: datetime | None,
        exit_code: int | None,
        result_message: str | None,
        log_snippet: str | None,
        full_logs: str | None,
        started_at: datetime | None,
        celery_task_id: str | None = None,
    ) -> dict[str, Any]:  # Added type hint for return
        """
        Prepares update data dictionary based on the job status and provided parameters.
        Handles the automatic setting of started_at and completed_at timestamps.
        """
        # Initialize with required status
        update_data: dict[str, Any] = {"status": status}  # Explicit type

        # Add non-None fields
        if result_message is not None:
            update_data["result_message"] = result_message
        if exit_code is not None:
            update_data["exit_code"] = exit_code
        if log_snippet is not None:
            update_data["log_snippet"] = log_snippet
        if full_logs is not None:
            update_data["full_logs"] = full_logs
        if celery_task_id is not None:
            update_data["celery_task_id"] = celery_task_id

        current_time_utc = datetime.now(UTC)  # Changed from UTC to timezone.utc

        # Handle started_at timestamp
        update_data = self._handle_started_at(  # Calls static method
            update_data, db_job, status, started_at, current_time_utc
        )

        # Handle completed_at timestamp
        update_data = self._handle_completed_at(  # Calls static method
            update_data, db_job, status, completed_at, current_time_utc
        )

        return update_data

    async def update_job_start_details(
        self,
        db: AsyncSession,
        *,
        job_id: UUID,
        celery_task_id: str,
        started_at: datetime | None = None,
    ) -> Job | None:
        """
        Updates a job to set its start time, Celery task ID, and status to RUNNING.
        """
        # CRUDBase.get expects 'id' as the kwarg for the primary key.
        db_obj = await self.get(db, id=job_id)  # Using self.get from CRUDBase
        if not db_obj:
            logger.warning(f"Job {job_id} not found for update_job_start_details.")
            return None

        if db_obj.status != JobStatus.PENDING:
            logger.warning(
                f"Job {job_id} attempted to start but was not in PENDING state (current: {db_obj.status}). Proceeding to set RUNNING."
            )

        db_obj.started_at = (
            started_at if started_at is not None else datetime.now(UTC)
        )  # Changed to timezone.utc
        db_obj.status = JobStatus.RUNNING
        db_obj.celery_task_id = celery_task_id
        # db_obj.updated_at is handled by the database's onupdate mechanism if configured on the model,
        # or needs to be set manually if not. Your Job model has onupdate=func.now() for updated_at.

        db.add(db_obj)
        # The caller (_setup_job_as_running in tasks/subtitle_jobs.py) is responsible for db.commit().
        # Flushing here ensures that any database-generated values are populated back to db_obj
        # and that any immediate database constraints are checked before the commit.
        await db.flush()
        await db.refresh(db_obj)
        logger.info(
            f"Job {job_id} start details updated. Status: RUNNING, Celery ID: {celery_task_id}."
        )
        return db_obj

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


job = CRUDJob(Job)
