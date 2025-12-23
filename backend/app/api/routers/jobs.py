# backend/app/api/routers/jobs.py
import logging
from datetime import UTC, datetime  # Python 3.11+ for UTC, for older use datetime.timezone.utc

# from datetime import timezone # For Python < 3.11 if UTC is not available directly
from pathlib import Path
from typing import Annotated  # List for Python < 3.9 compatibility with list[]
from uuid import UUID

# FastAPI imports
from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Query,
    Request,  # Ensure Request is imported
    status,
)
from fastapi import Path as FastApiPath  # Renamed to avoid conflict with pathlib.Path
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud  # Assuming crud.job is available
from app.core.config import settings
from app.core.rate_limit import limiter  # Import limiter
from app.core.security import current_active_user  # Your user dependency
from app.db.models.job import Job, JobStatus
from app.db.models.user import User  # Assuming User model for type hinting
from app.db.session import get_async_session

# Ensure these schemas are correctly defined and imported from app.schemas.job
from app.schemas.job import (  # Removed JobUpdate as we'll set directly
    JobCreate,
    JobCreateInternal,
    JobRead,
    JobReadLite,
)
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
    """Checks if the resolved_path_to_check is within any of the allowed_paths_list."""
    for allowed_base_path_str in allowed_paths_list:
        try:
            resolved_allowed_base = Path(allowed_base_path_str).resolve(strict=True)
        except FileNotFoundError:
            logger.error(
                f"Configured allowed base path '{allowed_base_path_str}' does not exist or is a broken symlink. Skipping."
            )
            continue
        except RuntimeError as e:  # e.g. symlink loop
            logger.error(
                f"Resolution of configured allowed base path '{allowed_base_path_str}' failed (e.g. symlink loop). Skipping: {e}"
            )
            continue
        except Exception as e:  # NOSONAR
            logger.error(
                f"Unexpected error during resolution of configured allowed base path '{allowed_base_path_str}'. Skipping: {e}"
            )
            continue

        # Check if the path_to_check is the allowed base path itself or a subdirectory
        if (
            resolved_path_to_check == resolved_allowed_base
            or resolved_allowed_base in resolved_path_to_check.parents
        ):
            return True
    return False


async def _validate_and_resolve_job_path(
    folder_path_str: str, allowed_folders: list[str], user_email: str
) -> Path:
    """Validates the job folder path against allowed directories and resolves it."""
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
    except RuntimeError as e:  # e.g. symlink loop
        logger.warning(
            f"Path resolution failed for input '{folder_path_str}' by user {user_email}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The provided folder path '{folder_path_str}' is invalid or could not be resolved (e.g., symlink loop).",
        ) from e
    except Exception as e:  # NOSONAR - Catch any other FS related errors
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
    db: AsyncSession, job_create_schema: JobCreateInternal, user_email: str
) -> Job:
    """Creates a job record in the database and updates it with a Celery task ID (which is job.id as string)."""
    try:
        db_job = await crud.job.create(db, obj_in=job_create_schema)
        logger.info(
            f"Job {db_job.id} created in DB for user {user_email} (User ID: {job_create_schema.user_id}) with status {db_job.status}."
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

    celery_task_id_str = str(db_job.id)
    try:
        db_job.celery_task_id = celery_task_id_str  # This is now a field on the Job model
        db.add(db_job)  # Ensure change is tracked
        await db.commit()
        await db.refresh(db_job)
        logger.info(f"Job {db_job.id} celery_task_id set to {db_job.celery_task_id}.")
        return db_job
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(
            f"Database error while updating celery_task_id for job {db_job.id}: {e}", exc_info=True
        )
        try:
            # Mark job as FAILED directly on the model instance
            db_job.status = JobStatus.FAILED
            db_job.result_message = "Internal error: Failed to link Celery task ID."
            db_job.exit_code = -200  # Internal error code
            db_job.log_snippet = "Failed to set celery_task_id in DB after creation."
            db_job.completed_at = datetime.now(
                UTC
            )  # Or datetime.now(timezone.utc) for Python < 3.11
            db.add(db_job)
            await db.commit()
        except Exception as final_fail_exc:
            logger.critical(
                f"Failed to mark job {db_job.id} as FAILED after celery_id update error: {final_fail_exc}"
            )
            await db.rollback()  # Rollback the attempt to mark as FAILED
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JOB_CELERY_ID_UPDATE_DB_ERROR",
        ) from e


async def _enqueue_celery_task_and_handle_errors(
    db: AsyncSession, job_to_enqueue: Job, user_email: str
) -> None:
    """Enqueues the Celery task and updates job status to FAILED if enqueueing fails."""
    if not job_to_enqueue.celery_task_id:
        logger.error(
            f"Job {job_to_enqueue.id} has no celery_task_id, cannot enqueue. This should not happen."
        )
        # This case indicates a logic error in _create_db_job_and_set_celery_id
        # Mark job as FAILED if it reaches here without a celery_task_id
        job_to_enqueue.status = JobStatus.FAILED
        job_to_enqueue.result_message = "Internal error: Missing Celery task ID before enqueue."
        job_to_enqueue.exit_code = -202  # Different internal error code
        job_to_enqueue.completed_at = datetime.now(UTC)  # Or datetime.now(timezone.utc)
        db.add(job_to_enqueue)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JOB_MISSING_CELERY_ID_PRE_ENQUEUE",
        )

    try:
        task_name = settings.CELERY_SUBTITLE_TASK_NAME
        celery_app.send_task(
            name=task_name,
            args=[
                str(job_to_enqueue.id),  # Pass Job ID to the task
                job_to_enqueue.folder_path,
                job_to_enqueue.language,
                job_to_enqueue.log_level,  # Pass log level to the task
            ],
            task_id=job_to_enqueue.celery_task_id,  # Use the pre-set celery_task_id
        )
        logger.info(
            f"Successfully enqueued Celery task '{task_name}' with ID {job_to_enqueue.celery_task_id} "
            f"for job {job_to_enqueue.id} (user: {user_email})."
        )
    except Exception as e:  # Broad exception for Celery communication issues (e.g., broker down)
        logger.error(
            f"Failed to enqueue Celery task for job {job_to_enqueue.id} (user: {user_email}): {e}",
            exc_info=True,
        )
        try:
            # Mark job as FAILED directly on the model instance
            job_to_enqueue.status = JobStatus.FAILED
            job_to_enqueue.completed_at = datetime.now(UTC)  # Or datetime.now(timezone.utc)
            job_to_enqueue.exit_code = -201  # Internal error code for enqueue failure
            job_to_enqueue.result_message = f"Failed to enqueue Celery task: {str(e)[:200]}"
            job_to_enqueue.log_snippet = f"Celery send_task failed: {str(e)[:500]}"
            db.add(job_to_enqueue)
            await db.commit()
            await db.refresh(job_to_enqueue)  # To get updated_at if DB handles it
            logger.info(f"Updated job {job_to_enqueue.id} status to FAILED due to enqueue error.")
        except SQLAlchemyError as db_exc:
            await db.rollback()
            logger.error(
                f"Failed to update job {job_to_enqueue.id} status to FAILED after Celery enqueue error: {db_exc}",
                exc_info=True,
            )
            # Original exception 'e' (Celery error) is more relevant to client if one must be chosen.
            # But this is an internal server error cascade.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="JOB_ENQUEUE_FAILED_DB_UPDATE_ERROR",
            ) from db_exc  # Chain the DB exception
        # Raise an HTTP exception indicating enqueue failure, but job status is now FAILED in DB.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JOB_ENQUEUE_FAILED_NOW_MARKED_AS_FAILED_IN_DB",
        ) from e  # Chain the Celery exception


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
@limiter.limit("10/minute")
async def create_job(
    job_in: Annotated[JobCreate, Body(...)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(current_active_user)],
    request: Request = None,  # Required for SlowAPI  # noqa: ARG001
) -> Job:
    # Fetch dynamic allowed paths from DB
    db_paths = await crud.storage_path.get_multi(db)
    env_folders = settings.ALLOWED_MEDIA_FOLDERS or []
    allowed_folders = list(set(env_folders + [p.path for p in db_paths]))

    # Ensure settings.ALLOWED_MEDIA_FOLDERS is the correct config variable name
    resolved_input_path = await _validate_and_resolve_job_path(
        job_in.folder_path, allowed_folders, current_user.email
    )
    normalized_job_folder_path_str = str(resolved_input_path)

    job_create_internal = JobCreateInternal(
        folder_path=normalized_job_folder_path_str,
        language=job_in.language,
        log_level=job_in.log_level,
        user_id=current_user.id,
        # celery_task_id will be set after DB creation using job.id
    )
    db_job_with_celery_id = await _create_db_job_and_set_celery_id(
        db, job_create_internal, current_user.email
    )

    await _enqueue_celery_task_and_handle_errors(db, db_job_with_celery_id, current_user.email)

    return db_job_with_celery_id


@router.get(
    "/",
    response_model=list[JobReadLite],  # Use List for Python < 3.9
    summary="List subtitle download jobs",
    description=(
        "Retrieves a list of subtitle download jobs. "
        "Superusers can see all jobs. Regular users can only see their own jobs. "
        "Jobs are ordered by submission time, newest first, by default."
    ),
)
async def list_jobs(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(current_active_user)],
    skip: Annotated[int, Query(ge=0, description="Number of jobs to skip")] = 0,
    limit: Annotated[
        int, Query(ge=1, le=200, description="Maximum number of jobs to return")
    ] = 100,
) -> list[Job]:  # Use List for Python < 3.9
    logger.info(
        f"User '{current_user.email}' (ID: {current_user.id}, Superuser: {current_user.is_superuser}) listing jobs. Skip: {skip}, Limit: {limit}"
    )
    if current_user.is_superuser:
        jobs = await crud.job.get_multi(db, skip=skip, limit=limit)
    else:
        jobs = await crud.job.get_multi_by_owner(
            db, user_id=current_user.id, skip=skip, limit=limit
        )

    if (
        jobs is None
    ):  # crud.job.get_multi might return None on error or if not found (though usually empty list)
        jobs = []
    logger.info(f"Found {len(jobs)} jobs for user '{current_user.email}'.")
    return jobs


@router.get(
    "/allowed-folders",
    response_model=list[str],
    summary="Get allowed media folders",
    description="Returns the list of directories allowed for subtitle download jobs.",
)
async def get_allowed_folders(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(current_active_user)],  # noqa: ARG001
) -> list[str]:
    db_paths = await crud.storage_path.get_multi(db)
    env_folders = settings.ALLOWED_MEDIA_FOLDERS or []
    combined = list(set(env_folders + [p.path for p in db_paths]))
    return sorted(combined)


@router.get(
    "/{job_id}",
    response_model=JobRead,
    summary="Get details for a specific job",
    description=(
        "Retrieves detailed information for a specific subtitle download job by its ID. "
        "Superusers can access any job. Regular users can only access their own jobs."
    ),
)
async def get_job_details(
    job_id: Annotated[UUID, FastApiPath(description="The ID of the job to retrieve")],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(current_active_user)],
) -> Job:
    logger.info(
        f"User '{current_user.email}' (ID: {current_user.id}) requesting details for job ID: {job_id}"
    )
    job = await crud.job.get(db, id=job_id)  # Assuming crud.job.get fetches the job
    if not job:
        logger.warning(f"Job ID {job_id} not found when requested by user '{current_user.email}'.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="JOB_NOT_FOUND")

    if not current_user.is_superuser and job.user_id != current_user.id:
        logger.warning(  # Changed to warning as it's a denied access, not an error in system logic
            f"User '{current_user.email}' (ID: {current_user.id}) FORBIDDEN from accessing job ID {job_id} owned by user ID {job.user_id}."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="NOT_AUTHORIZED_TO_ACCESS_JOB"
        )

    logger.info(f"Successfully retrieved job ID {job_id} for user '{current_user.email}'.")
    return job


@router.delete(
    "/{job_id}",
    response_model=JobRead,  # Note: if deleted, this might need to be Optional or specific response. But for 200 OK, we can return the deleted object state or empty.
    # Actually, if deleted, returning the object is fine as "last known state". Or 204.
    # But for backward compatibility with "Cancel" returning the updated job, let's keep it responding with JobRead.
    # But if deleted, we can't refresh it.
    # Let's return the job object *before* deletion if deleted?
    # Or just return detailed message?
    # The frontend expects JobRead or similar?
    # The frontend cancelMutation expects data.
    # If I verify JobHistoryList, it invalidates query.
    # Let's try to return the job object.
    status_code=status.HTTP_200_OK,
    summary="Cancel or Delete a job",
    description=(
        "If the job is PENDING or RUNNING, it initiates cancellation (stops the task). "
        "If the job is already in a terminal state (SUCCEEDED, FAILED, CANCELLED, CANCELLING), "
        "it deletes the job record from the database."
    ),
)
async def delete_or_cancel_job(
    job_id: Annotated[UUID, FastApiPath(description="The ID of the job to cancel or delete")],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(current_active_user)],
) -> Job:
    logger.info(f"User '{current_user.email}' attempting to cancel/delete job '{job_id}'.")

    job = await crud.job.get(db, id=job_id)
    if not job:
        logger.warning(
            f"Cancel/Delete request for non-existent job '{job_id}' by user '{current_user.email}'."
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="JOB_NOT_FOUND")

    # Authorization check
    if not current_user.is_superuser and job.user_id != current_user.id:
        logger.warning(f"User '{current_user.email}' unauthorized to modify job '{job_id}'.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="NOT_AUTHORIZED_TO_MODIFY_JOB"
        )

    # Job state check for Revocation
    celery_task_id_to_revoke = job.celery_task_id

    if celery_task_id_to_revoke:
        logger.info(
            f"Job '{job_id}' being deleted has active task '{celery_task_id_to_revoke}'. Sending revoke signal."
        )
        try:
            # We send SIGTERM to the worker process.
            # Since we are deleting the DB record immediately after, the worker's subsequent
            # attempts to update the DB will fail (or handle "Job Not Found").
            # This is the expected "Force Remove" behavior.
            celery_app.control.revoke(celery_task_id_to_revoke, terminate=True, signal="SIGTERM")
        except Exception as e:
            logger.error(
                f"Failed to send revoke command for Celery task_id '{celery_task_id_to_revoke}': {e}"
            )
            # We proceed to delete anyway, as the user requested removal.

    # Always Delete
    try:
        logger.info(f"Removing job '{job_id}' from database.")
        await db.delete(job)
        await db.commit()
        # Returns the job object as it was before deletion (with old status)
        # or we could return a specific message.
        # Returning the object is fine for now; frontend just invalidates list.
        return job
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error while deleting job {job_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JOB_DELETION_DB_ERROR",
        ) from e
