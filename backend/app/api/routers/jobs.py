# backend/app/api/routers/jobs.py
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError  # For more specific DB error handling
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.users import current_active_user  # Corrected import path
from app.db.models.job import Job, JobStatus
from app.db.models.user import User
from app.db.session import get_async_session
from app.schemas.job import JobCreate, JobRead

# Later, we'll uncomment these for Celery integration
# from app.tasks.celery_app import celery_app
# from app.tasks.subtitle_jobs import run_subtitle_downloader_mock # Or the real task

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/jobs",
    tags=["Jobs - Subtitle Download Management"],  # More descriptive tag
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Resource not found"},
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated"},
        status.HTTP_403_FORBIDDEN: {"description": "Not authorized"},
    },  # Expanded default responses
)


@router.post(
    "/",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a new subtitle download job",
    description=(
        "Allows authenticated users to submit a new subtitle download job for a specified folder path. "
        "The path is validated against allowed media directories. "
        "A job record is created with PENDING status and will be processed asynchronously."
    ),
)
async def create_job(
    job_in: JobCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
) -> JobRead:
    """
    Submits a new subtitle download job.

    - **job_in**: Contains `folder_path` and optional `language`.
    - **db**: Async database session.
    - **current_user**: The authenticated user submitting the job.

    The `folder_path` must be within the `ALLOWED_MEDIA_FOLDERS` defined in settings.
    Returns the created job details.
    """

    # --- 1. Input Validation: folder_path against ALLOWED_MEDIA_FOLDERS_ENV ---
    try:
        # Ensure folder_path is an absolute path and normalized
        # os.path.abspath might be useful if relative paths could be passed and need resolving
        # based on a known root, but for now, assuming paths are already well-formed or absolute.
        normalized_job_folder_path = os.path.normpath(job_in.folder_path)
    except Exception as e:  # Catch potential errors from os.path.normpath with weird inputs
        logger.warning(
            f"Invalid folder_path received for normalization: {job_in.folder_path}. Error: {e}"
        )
        raise HTTPException from e(
            status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_FOLDER_PATH_FORMAT"
        )

    is_allowed = False
    if not settings.ALLOWED_MEDIA_FOLDERS:
        logger.warning("ALLOWED_MEDIA_FOLDERS is not configured or empty. Denying job submission.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,  # Or 400 if considered client's fault for trying
            detail="SERVER_CONFIGURATION_ERROR_MEDIA_FOLDERS",
        )

    for allowed_base_path_str in settings.ALLOWED_MEDIA_FOLDERS:
        normalized_allowed_base = os.path.normpath(allowed_base_path_str)
        # Check if the job path is exactly an allowed base or a subdirectory of an allowed base
        if (
            normalized_job_folder_path == normalized_allowed_base
            or normalized_job_folder_path.startswith(normalized_allowed_base + os.sep)
        ):
            is_allowed = True
            break

    if not is_allowed:
        logger.warning(
            f"User {current_user.email} attempted to submit job for disallowed path: '{job_in.folder_path}'. "
            f"Normalized: '{normalized_job_folder_path}'. Allowed bases: {settings.ALLOWED_MEDIA_FOLDERS}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"The provided folder path '{job_in.folder_path}' is not within the allowed media directories. "
                f"Ensure the path is valid and starts with one of the configured base paths."
            ),
        )

    logger.info(
        f"Folder path '{normalized_job_folder_path}' is allowed for user {current_user.email}."
    )

    # --- 2. Create Job DB record ---
    db_job = Job(
        user_id=current_user.id,
        folder_path=normalized_job_folder_path,
        language=job_in.language,
        status=JobStatus.PENDING,
        # id and submitted_at will have DB defaults
    )

    try:
        db.add(db_job)
        await db.commit()
        await db.refresh(db_job)
        logger.info(
            f"Job {db_job.id} created in DB for user {current_user.email} with status {db_job.status}."
        )
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(
            f"Database error while creating job for user {current_user.email}, path '{normalized_job_folder_path}': {e}",
            exc_info=True,
        )
        raise HTTPException from e(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JOB_CREATION_DB_ERROR"
        )
    except Exception as e:  # Catch any other unexpected errors during DB interaction
        await db.rollback()  # Ensure rollback for other exceptions too
        logger.error(
            f"Unexpected error while creating job for user {current_user.email}, path '{normalized_job_folder_path}': {e}",
            exc_info=True,
        )
        raise HTTPException from e(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JOB_CREATION_UNEXPECTED_ERROR",
        )

    # --- 3. Enqueue Celery task (Placeholder) ---
    # task_id_str = str(uuid.uuid4()) # Example: Generate a task ID hint if needed
    # try:
    #     task = run_subtitle_downloader_mock.apply_async(
    #         args=[str(db_job.id), db_job.folder_path, db_job.language],
    #         task_id=task_id_str # Optional: provide a specific task ID
    #     )
    #     db_job.celery_task_id = task.id # Store Celery's actual task ID
    #     await db.commit()
    #     await db.refresh(db_job) # Refresh to get the updated celery_task_id if your model tracks it
    #     logger.info(f"Job {db_job.id} enqueued with Celery task ID: {db_job.celery_task_id}")
    # except Exception as e: # Catch Celery connection errors or other issues
    #     logger.error(f"Failed to enqueue Celery task for job {db_job.id}: {e}", exc_info=True)
    #     # Decide how to handle this:
    #     # Option 1: Mark job as FAILED_TO_ENQUEUE
    #     # db_job.status = JobStatus.FAILED # Or a new status like FAILED_TO_ENQUEUE
    #     # db_job.notes = f"Failed to enqueue Celery task: {str(e)}"
    #     # await db.commit()
    #     # Option 2: Raise an error to the client (might not be 202 anymore)
    #     # raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JOB_ENQUEUE_FAILED")
    #     # For now, we'll just log and proceed, job will remain PENDING

    return db_job


# TODO: Add other job-related endpoints:
# - GET /jobs/ : List jobs for the current user (or all jobs for admin)
# - GET /jobs/{job_id} : Get specific job details
# - DELETE /jobs/{job_id} : Cancel/delete a job (if applicable)
# - GET /jobs/statuses : Get available JobStatus enum values
