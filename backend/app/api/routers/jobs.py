# backend/app/api/routers/jobs.py
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import current_active_user
from app.db.crud import job as crud_job
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


def _is_path_allowed(resolved_path_to_check: Path, allowed_paths_list: list[str]) -> bool:
    """
    Checks if the resolved_path_to_check is within one of the allowed_paths.
    allowed_paths_list contains string paths that will be resolved.
    """
    for allowed_base_path_str in allowed_paths_list:
        try:
            resolved_allowed_base = Path(allowed_base_path_str).resolve(strict=True)
        except FileNotFoundError:
            logger.error(
                f"Configured allowed base path '{allowed_base_path_str}' does not exist or is a broken symlink. Skipping."
            )
            continue
        except RuntimeError as e:
            logger.error(
                f"Resolution of configured allowed base path '{allowed_base_path_str}' failed (e.g. symlink loop). Skipping: {e}"
            )
            continue
        except Exception as e:
            logger.error(
                f"Unexpected error during resolution of configured allowed base path '{allowed_base_path_str}'. Skipping: {e}"
            )
            continue

        if (
            resolved_path_to_check == resolved_allowed_base
            or resolved_allowed_base in resolved_path_to_check.parents
        ):
            return True
    return False


async def _validate_and_resolve_job_path(
    folder_path_str: str, allowed_folders: list[str], user_email: str
) -> Path:
    """
    Validates the folder path for a job submission.
    Resolves the path and checks if it's within allowed directories.
    """
    if not allowed_folders:
        logger.error(
            "CRITICAL: ALLOWED_MEDIA_FOLDERS is not configured or empty. Denying all job submissions."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SERVER_CONFIGURATION_ERROR_MEDIA_FOLDERS",
        )

    try:
        resolved_input_path = Path(folder_path_str).resolve(strict=True)
    except FileNotFoundError as e:
        logger.warning(
            f"User {user_email} submitted job for non-existent or inaccessible path: '{folder_path_str}'."
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The provided folder path '{folder_path_str}' does not exist or is not accessible.",
        ) from e
    except RuntimeError as e:
        logger.warning(
            f"Path resolution failed for input '{folder_path_str}' by user {user_email}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The provided folder path '{folder_path_str}' is invalid or could not be resolved (e.g., symlink loop).",
        ) from e
    except Exception as e:
        logger.warning(
            f"Unexpected error during path resolution for input '{folder_path_str}' by user {user_email}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path resolution failed for '{folder_path_str}'.",
        ) from e

    if not _is_path_allowed(resolved_input_path, allowed_folders):
        logger.warning(
            f"User {user_email} attempted to submit job for disallowed path: '{resolved_input_path!s}'. "
            f"Original input: '{folder_path_str}'. Allowed bases: {allowed_folders}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"The provided folder path '{resolved_input_path!s}' (resolved from '{folder_path_str}') "
                f"is not within the allowed media directories. "
                f"Ensure the path is valid and starts with one of the configured base paths."
            ),
        )
    logger.info(f"Folder path '{resolved_input_path!s}' is allowed for user {user_email}.")
    return resolved_input_path


async def _create_db_job_and_set_celery_id(
    db: AsyncSession, job_create_schema: JobCreate, user_id: int, user_email: str
) -> Job:
    """
    Creates a job record in the database and updates it with a Celery task ID.
    """
    try:
        db_job = await crud_job.create_job_db(db, job_in=job_create_schema, user_id=user_id)
        logger.info(
            f"Job {db_job.id} created in DB for user {user_email} with status {db_job.status}."
        )
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(
            f"Database error while creating job for user {user_email}, path '{job_create_schema.folder_path}': {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JOB_CREATION_DB_ERROR"
        ) from e

    celery_task_id = str(db_job.id)  # Use DB job ID as Celery task ID
    try:
        updated_db_job = await crud_job.update_job_celery_task_id(
            db, job_id=db_job.id, celery_task_id=celery_task_id
        )
        if not updated_db_job:
            logger.error(
                f"Critical: Failed to update celery_task_id for just-created job {db_job.id}."
            )
            # Attempt to mark job as failed if celery_task_id update fails
            await crud_job.update_job_completion_details(
                db,
                job_id=db_job.id,
                status=JobStatus.FAILED,
                completed_at=datetime.now(UTC),
                exit_code=-200,
                result_message="Internal error: Failed to link Celery task ID.",
                log_snippet="Failed to set celery_task_id in DB after creation.",
            )
            await db.commit()  # Commit the failure state
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="JOB_PREPARATION_FOR_ENQUEUE_FAILED",
            )
        logger.info(
            f"Job {updated_db_job.id} celery_task_id set to {updated_db_job.celery_task_id}."
        )
        return updated_db_job
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(
            f"Database error while updating celery_task_id for job {db_job.id}: {e}", exc_info=True
        )
        # Don't try to update db_job object here as session is rolled back
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JOB_CELERY_ID_UPDATE_DB_ERROR",
        ) from e


async def _enqueue_celery_task_and_handle_errors(
    db: AsyncSession, job_to_enqueue: Job, user_email: str
) -> None:
    """
    Enqueues the Celery task for the job and handles potential errors,
    updating job status if enqueueing fails.
    """
    try:
        task_name = settings.CELERY_SUBTITLE_TASK_NAME
        celery_app.send_task(
            name=task_name,
            args=[
                str(job_to_enqueue.id),
                job_to_enqueue.folder_path,
                job_to_enqueue.language,
            ],
            task_id=job_to_enqueue.celery_task_id,  # This should be set from previous step
        )
        logger.info(
            f"Successfully enqueued Celery task '{task_name}' with ID {job_to_enqueue.celery_task_id} "
            f"for job {job_to_enqueue.id} (user: {user_email})."
        )
    except Exception as e:
        logger.error(
            f"Failed to enqueue Celery task for job {job_to_enqueue.id} (user: {user_email}): {e}",
            exc_info=True,
        )
        try:
            await crud_job.update_job_completion_details(
                db,
                job_id=job_to_enqueue.id,
                status=JobStatus.FAILED,
                completed_at=datetime.now(UTC),
                exit_code=-201,
                result_message=f"Failed to enqueue Celery task: {str(e)[:200]}",
                log_snippet=f"Celery send_task failed: {str(e)[:500]}",
            )
            await db.commit()  # Commit the failure state
            logger.info(f"Updated job {job_to_enqueue.id} status to FAILED due to enqueue error.")
        except SQLAlchemyError as db_exc:
            await db.rollback()  # Rollback if update fails
            logger.error(
                f"Failed to update job {job_to_enqueue.id} status to FAILED after Celery enqueue error: {db_exc}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="JOB_ENQUEUE_FAILED_DB_UPDATE_ERROR",
            ) from db_exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JOB_ENQUEUE_FAILED_DB_UPDATED",  # Implies DB update to FAILED was successful before this re-raise
        ) from e


@router.post(
    "/",
    response_model=JobRead,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new subtitle download job",
    description=(
        "Allows authenticated users to submit a new subtitle download job for a specified folder path. "
        "The path is validated against allowed media directories. "
        "A job record is created, and a task is enqueued for asynchronous processing."
    ),
)
async def create_job(
    job_in: Annotated[JobCreate, Body(...)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(current_active_user)],
) -> Job:
    """
    Submits a new subtitle download job.
    1. Validates the input folder path.
    2. Creates a job record in the database and sets its Celery task ID.
    3. Enqueues the job to Celery.
    """
    resolved_input_path = await _validate_and_resolve_job_path(
        job_in.folder_path, settings.ALLOWED_MEDIA_FOLDERS, current_user.email
    )
    normalized_job_folder_path_str = str(resolved_input_path)

    # Prepare data for DB creation using the normalized path
    job_data_for_db = JobCreate(
        folder_path=normalized_job_folder_path_str, language=job_in.language
    )

    # This function now handles DB job creation and Celery task ID update
    db_job_with_celery_id = await _create_db_job_and_set_celery_id(
        db, job_data_for_db, current_user.id, current_user.email
    )

    # This function handles enqueuing and error cases related to it
    await _enqueue_celery_task_and_handle_errors(db, db_job_with_celery_id, current_user.email)

    # If all steps above are successful, commit the session changes
    # (e.g., job creation, celery_id update)
    # Note: _create_db_job_and_set_celery_id might commit on partial failure
    # and _enqueue_celery_task_and_handle_errors might commit on failure.
    # A successful path implies db_job_with_celery_id is already persisted.
    # If _create_db_job_and_set_celery_id had a SQLAlchemyError and rolled back,
    # an exception would have been raised, so we wouldn't reach here.
    # If _enqueue_celery_task_and_handle_errors failed, it would raise an exception
    # or commit a failure state for the job.
    # A final commit here ensures the successful creation and celery_id update is persisted if no errors occurred.
    try:
        await db.commit()
    except SQLAlchemyError as e:
        # This case should be rare if helpers manage their transactions on error,
        # but acts as a final safeguard.
        await db.rollback()
        logger.error(
            f"Final commit failed after successful operations for job {db_job_with_celery_id.id}: {e}",
            exc_info=True,
        )
        # Update job to FAILED if possible, though it might already be in a failed state or uncommittable
        try:
            await crud_job.update_job_completion_details(
                db,
                job_id=db_job_with_celery_id.id,
                status=JobStatus.FAILED,
                completed_at=datetime.now(UTC),
                exit_code=-202,  # Different code for this specific failure point
                result_message="Internal error: Final commit after task enqueue failed.",
                log_snippet=f"Final commit SQLAlchemyError: {str(e)[:500]}",
            )
            await db.commit()  # Try to commit this failure state
        except (
            Exception
        ) as final_update_exc:  # Catch all for any error during this last-ditch update
            logger.critical(
                f"CRITICAL: Failed to mark job {db_job_with_celery_id.id} as FAILED after final commit error: {final_update_exc}",
                exc_info=True,
            )
            # No further db operations possible here
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JOB_FINALIZATION_DB_ERROR"
        ) from e

    return db_job_with_celery_id
