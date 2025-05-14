# backend/app/api/routers/jobs.py
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.users import current_active_user
from app.db.models.job import Job, JobStatus
from app.db.models.user import User
from app.db.session import get_async_session
from app.schemas.job import JobCreate, JobRead
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Jobs - Subtitle Download Management"],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Resource not found"},
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated"},
        status.HTTP_403_FORBIDDEN: {"description": "Not authorized"},
    },
)


def _is_path_allowed(path_to_check: str, allowed_paths_list: list[str]) -> bool:
    """
    Checks if the path_to_check is within one of the allowed_paths.
    Normalizes paths and checks for containment.
    """
    try:
        normalized_job_folder_path = os.path.normpath(path_to_check)
        if normalized_job_folder_path.startswith(".."):  # Basic check against path traversal
            return False
    except Exception as e:
        logger.warning(f"Path normalization failed for '{path_to_check}': {e}")
        return False  # Treat normalization errors as disallowed

    for allowed_base_path_str in allowed_paths_list:
        normalized_allowed_base = os.path.normpath(allowed_base_path_str)
        # Check if the job path is exactly an allowed base or a subdirectory
        if (
            normalized_job_folder_path == normalized_allowed_base
            or normalized_job_folder_path.startswith(normalized_allowed_base + os.sep)
        ):
            return True
    return False


@router.post(
    "/",
    response_model=JobRead,
    status_code=status.HTTP_201_CREATED,  # Changed back to 201 as resource is created
    summary="Submit a new subtitle download job",
    description=(
        "Allows authenticated users to submit a new subtitle download job for a specified folder path. "
        "The path is validated against allowed media directories. "
        "A job record is created, and a task is enqueued for asynchronous processing."
    ),
)
async def create_job(
    job_in: JobCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
) -> Job:  # Return type is Job, Pydantic will handle JobRead conversion
    """
    Submits a new subtitle download job.

    - **job_in**: Contains `folder_path` and optional `language`.
    - **db**: Async database session.
    - **current_user**: The authenticated user submitting the job.

    The `folder_path` must be within the `ALLOWED_MEDIA_FOLDERS` defined in settings.
    Returns the created job details. If task enqueuing fails after DB record creation,
    the job status will be marked FAILED, and an error will be returned.
    """

    # --- 1. Input Validation: folder_path ---
    if not settings.ALLOWED_MEDIA_FOLDERS:
        logger.error(
            "CRITICAL: ALLOWED_MEDIA_FOLDERS is not configured or empty. Denying all job submissions."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,  # More appropriate if server is misconfigured
            detail="SERVER_CONFIGURATION_ERROR_MEDIA_FOLDERS",
        )

    if not _is_path_allowed(job_in.folder_path, settings.ALLOWED_MEDIA_FOLDERS):
        logger.warning(
            f"User {current_user.email} attempted to submit job for disallowed path: '{job_in.folder_path}'. "
            f"Allowed bases: {settings.ALLOWED_MEDIA_FOLDERS}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"The provided folder path '{job_in.folder_path}' is not within the allowed media directories. "
                f"Ensure the path is valid and starts with one of the configured base paths."
            ),
        )

    normalized_job_folder_path = os.path.normpath(job_in.folder_path)
    logger.info(
        f"Folder path '{normalized_job_folder_path}' is allowed for user {current_user.email}."
    )

    # --- 2. Create Job DB record ---
    job_uuid = uuid.uuid4()
    celery_task_id_str = str(job_uuid)

    db_job = Job(
        id=job_uuid,  # Use the generated UUID as primary key
        user_id=current_user.id,
        folder_path=normalized_job_folder_path,
        language=job_in.language,
        status=JobStatus.PENDING,
        celery_task_id=celery_task_id_str,  # Store the Celery task ID (same as job ID)
    )

    try:
        db.add(db_job)
        await db.commit()
        await db.refresh(db_job)
        logger.info(
            f"Job {db_job.id} (Celery Task ID: {db_job.celery_task_id}) created in DB for user "
            f"{current_user.email} with status {db_job.status}."
        )
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(
            f"Database error while creating job for user {current_user.email}, path '{normalized_job_folder_path}': {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JOB_CREATION_DB_ERROR"
        ) from e

    # --- 3. Enqueue Celery task ---
    try:
        task_name = "app.tasks.subtitle_jobs.run_subtitle_downloader_mock"
        celery_app.send_task(
            name=task_name,
            args=[str(db_job.id), db_job.folder_path, db_job.language],
            task_id=celery_task_id_str,
        )
        logger.info(
            f"Successfully enqueued Celery task '{task_name}' with ID {celery_task_id_str} "
            f"for job {db_job.id} (user: {current_user.email})."
        )
    except Exception as e:
        logger.error(
            f"Failed to enqueue Celery task for job {db_job.id} (user: {current_user.email}): {e}",
            exc_info=True,
        )
        # Attempt to update job status to FAILED as enqueuing failed
        db_job.status = JobStatus.FAILED
        db_job.result_message = f"Failed to enqueue Celery task: {str(e)[:500]}"
        try:
            await db.commit()
            await db.refresh(db_job)
            logger.info(f"Updated job {db_job.id} status to FAILED due to enqueue error.")
        except SQLAlchemyError as db_exc:
            await db.rollback()
            logger.error(
                f"Failed to update job {db_job.id} status to FAILED after Celery enqueue error: {db_exc}",
                exc_info=True,
            )
            # If updating status also fails, the original job record (PENDING) persists.
            # The client gets an error indicating enqueue failure, but the DB state might be less accurate.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="JOB_ENQUEUE_FAILED_DB_UPDATE_ERROR",
            ) from db_exc

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JOB_ENQUEUE_FAILED_DB_UPDATED",  # Client knows task didn't enqueue, job is marked FAILED
        ) from e

    return db_job
