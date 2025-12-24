# backend/app/db/crud/job.py
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload  # For eager loading user if needed

from app.db.models.job import Job
from app.schemas.job import JobCreate, JobStatus  # JobCreate only if used by a CRUD create function


async def get_job(db: AsyncSession, job_id: UUID) -> Job | None:
    """Gets a single job by its ID, optionally loading the related user."""
    result = await db.execute(select(Job).options(selectinload(Job.user)).where(Job.id == job_id))
    return result.scalar_one_or_none()


async def create_job_db(db: AsyncSession, job_in: JobCreate, user_id: UUID) -> Job:
    """
    Creates a new job record in the database.
    The celery_task_id is typically set in a subsequent step after the job ID is known.
    """
    db_job = Job(
        folder_path=job_in.folder_path,
        language=job_in.language,
        user_id=user_id,
        status=JobStatus.PENDING,
        submitted_at=datetime.now(UTC),
        # celery_task_id is nullable and can be set later
    )
    db.add(db_job)
    await db.commit()
    await db.refresh(db_job)
    return db_job


async def update_job_celery_task_id(
    db: AsyncSession, job_id: UUID, celery_task_id: str
) -> Job | None:
    """Updates the Celery task ID for a given job."""
    await db.execute(update(Job).where(Job.id == job_id).values(celery_task_id=celery_task_id))
    await db.commit()
    return await get_job(db, job_id=job_id)  # Fetch to confirm and return updated


async def update_job_status_and_start_time(
    db: AsyncSession, job_id: UUID, status: JobStatus, started_at: datetime
) -> Job | None:
    """Updates a job's status and records its start time."""
    await db.execute(
        update(Job).where(Job.id == job_id).values(status=status, started_at=started_at)
    )
    await db.commit()
    return await get_job(db, job_id=job_id)


async def update_job_completion_details(
    db: AsyncSession,
    job_id: UUID,
    status: JobStatus,
    completed_at: datetime,
    exit_code: int | None,  # Allow None for exit_code
    result_message: str | None,
    log_snippet: str | None,
) -> Job | None:
    """Updates a job's details upon completion or failure."""
    values_to_update = {
        "status": status,
        "completed_at": completed_at,
        "exit_code": exit_code,
        "result_message": result_message[:2000] if result_message else None,  # Truncate
        "log_snippet": log_snippet[:4000] if log_snippet else None,  # Truncate
    }
    await db.execute(update(Job).where(Job.id == job_id).values(**values_to_update))
    await db.commit()
    return await get_job(db, job_id=job_id)


async def list_jobs_for_user(
    db: AsyncSession, user_id: UUID, skip: int = 0, limit: int = 100
) -> list[Job]:
    """Lists jobs for a specific user with pagination."""
    result = await db.execute(
        select(Job)
        .where(Job.user_id == user_id)
        .order_by(Job.submitted_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_all_jobs(db: AsyncSession, skip: int = 0, limit: int = 100) -> list[Job]:
    """Lists all jobs (admin) with pagination."""
    result = await db.execute(
        select(Job).order_by(Job.submitted_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all())
