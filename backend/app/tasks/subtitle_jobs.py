# backend/app/tasks/subtitle_jobs.py
import asyncio
import logging
import sys
from datetime import UTC, datetime
from uuid import UUID

from celery import Task as CeleryTaskDef
from sqlalchemy.ext.asyncio import AsyncSession  # If not already imported for type hints

from app.core.config import settings
from app.db.crud import job as crud_job
from app.db.session import AsyncSessionLocal  # Keep this import
from app.schemas.job import JobStatus
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _execute_subtitle_downloader_async_logic(
    task_name_for_log: str,
    celery_internal_task_id: str,
    job_db_id: UUID,
    folder_path: str,
    language: str | None,
) -> dict:
    """
    Core async logic for the subtitle downloader task.
    This function has been refactored to reduce complexity by extracting subfunctions.
    """
    job_db_id_str = str(job_db_id)
    task_log_prefix = f"[AsyncTask:{task_name_for_log} CeleryID:{celery_internal_task_id} DBJobID:{job_db_id_str}]"

    logger.info(f"{task_log_prefix} ASYNC LOGIC ENTERED.")

    # Initialize response for eventual return
    response = {
        "job_id": job_db_id_str,
        "status": JobStatus.FAILED.value,
        "message": "Task execution did not complete",
    }

    try:
        # Create the database session
        async with AsyncSessionLocal() as db:
            # Update the job status to RUNNING and handle any setup issues
            setup_error = await _setup_job_as_running(db, job_db_id, task_log_prefix)
            if setup_error:
                return setup_error

            # Execute main task logic
            response = await _execute_subtitle_script(
                db, job_db_id, folder_path, language, task_log_prefix
            )

    except Exception as e:
        logger.error(
            f"{task_log_prefix} Unhandled exception in async task logic: {e}",
            exc_info=True,
        )
        response = {
            "job_id": job_db_id_str,
            "status": JobStatus.FAILED.value,
            "error": f"Task execution failed: {type(e).__name__}: {str(e)[:200]}",
        }

    logger.info(f"{task_log_prefix} ASYNC LOGIC EXITING. Response: {response}")
    return response


async def _execute_subtitle_script(
    db: AsyncSession, job_db_id: UUID, folder_path: str, language: str | None, task_log_prefix: str
) -> dict:
    """
    Execute the subtitle downloader script and process its results.
    Extracted from _execute_subtitle_downloader_async_logic to reduce complexity.
    """
    job_db_id_str = str(job_db_id)
    script_path = settings.SUBTITLE_DOWNLOADER_SCRIPT_PATH
    job_timeout = settings.SUBTITLE_JOB_TIMEOUT_SECONDS

    try:
        # Run the script process and handle timeouts
        exit_code, stdout_b, stderr_b = await _run_script_and_get_output(
            script_path, folder_path, language, job_timeout, task_log_prefix
        )

        # Parse the output
        status, result_message, log_snippet = _parse_script_output(
            exit_code, stdout_b, stderr_b, task_log_prefix
        )

        # Update job details in database
        await _finalize_job_in_db(
            db, job_db_id, status, exit_code, result_message, log_snippet, task_log_prefix
        )

        return {
            "job_id": job_db_id_str,
            "status": status.value,
            "message": result_message,
        }

    except Exception as e:
        err_msg = f"Task failed during main logic: {type(e).__name__}: {str(e)[:200]}"
        logger.error(f"{task_log_prefix} {err_msg}", exc_info=True)

        try:
            # Try to update DB to reflect failure
            await _handle_task_failure_in_db(db, job_db_id, e, task_log_prefix)
        except Exception as db_exc:
            logger.error(
                f"{task_log_prefix} Additionally failed to update DB with failure info: {db_exc}",
                exc_info=True,
            )

        return {
            "job_id": job_db_id_str,
            "status": JobStatus.FAILED.value,
            "error": err_msg,
        }


# Helper async function containing the core task logic (largely unchanged from your last version)
async def _setup_job_as_running(
    db: AsyncSession, job_db_id: UUID, task_log_prefix: str
) -> dict | None:
    """
    Tries to update the job to RUNNING.
    Returns an error dictionary if the job cannot be set to RUNNING.
    Raises DB-related exceptions if they occur during the update.
    Returns None if successful.
    """
    logger.debug(f"{task_log_prefix} Attempting to update job to RUNNING.")
    try:
        current_time_utc = datetime.now(UTC)
        updated_job = await crud_job.update_job_status_and_start_time(
            db, job_id=job_db_id, status=JobStatus.RUNNING, started_at=current_time_utc
        )
        if not updated_job:
            err_msg = f"Job with ID {job_db_id} not found or failed to update to RUNNING."
            logger.error(f"{task_log_prefix} {err_msg}")
            await _handle_task_failure_in_db(
                db,
                job_db_id,
                err_msg,  # Can pass string as simplified error
                task_log_prefix,
                exit_code_override=-300,
                log_snippet_override="Failed to set job to RUNNING state at task start.",
            )
            return {
                "job_id": str(job_db_id),
                "status": JobStatus.FAILED.value,
                "error": err_msg,
            }
        logger.info(f"{task_log_prefix} Job status updated to RUNNING in DB.")
        return None  # Success
    except Exception as db_exc:
        err_msg = f"DB error updating job {job_db_id} to RUNNING: {db_exc}"
        logger.error(f"{task_log_prefix} {err_msg}", exc_info=True)
        # Do not attempt further DB updates if the DB connection itself is the issue
        raise RuntimeError(f"Task setup failed (DB update to RUNNING): {err_msg}") from db_exc


async def _run_script_and_get_output(
    script_path: str,
    folder_path: str,
    language: str | None,
    job_timeout: int,
    task_log_prefix: str,
) -> tuple[int, bytes, bytes]:
    """Executes script, manages timeout, returns (exit_code, stdout, stderr)."""
    cmd_args = [sys.executable, script_path, "--folder-path", folder_path]
    if language:
        cmd_args.extend(["--language", language])

    logger.info(f"{task_log_prefix} Executing command: {' '.join(cmd_args)}")
    process = await asyncio.create_subprocess_exec(
        *cmd_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    stdout_b, stderr_b = b"", b""
    exit_code = -1  # Default

    try:
        logger.debug(
            f"{task_log_prefix} Awaiting process.communicate() with timeout {job_timeout}s."
        )
        stdout_b, stderr_b = await asyncio.wait_for(process.communicate(), timeout=job_timeout)
        exit_code = process.returncode if process.returncode is not None else -100
        logger.info(f"{task_log_prefix} Script process communicated. Exit code: {exit_code}.")
    except TimeoutError:
        logger.warning(f"{task_log_prefix} Script timed out after {job_timeout}s. Terminating.")
        exit_code = -99  # Specific code for timeout
        stderr_b = f"Script execution timed out after {job_timeout} seconds.".encode()
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except TimeoutError:
            logger.warning(f"{task_log_prefix} Process terminate timed out. Killing.")
            process.kill()
            await process.wait()
        except Exception as term_exc:
            logger.error(
                f"{task_log_prefix} Error during process termination: {term_exc}", exc_info=True
            )
            if process.returncode is None:
                process.kill()
                await process.wait()  # Ensure kill
    except Exception as comm_exc:
        logger.error(
            f"{task_log_prefix} Error during process.communicate(): {comm_exc}", exc_info=True
        )
        exit_code = -98  # Specific code for communication error
        stderr_b = f"Error communicating with script process: {comm_exc!s}".encode()
        if process.returncode is None:
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass  # Best effort to kill lingering process

    return exit_code, stdout_b, stderr_b


def _parse_script_output(
    exit_code: int, stdout_bytes: bytes, stderr_bytes: bytes, task_log_prefix: str
) -> tuple[JobStatus, str, str]:
    """Parses script output into status, result message, and log snippet."""
    stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

    if stdout:
        logger.debug(f"{task_log_prefix} STDOUT (last 1k):\n{stdout[-1000:]}")
    if stderr:
        logger.warning(f"{task_log_prefix} STDERR (last 1k):\n{stderr[-1000:]}")

    final_status = JobStatus.SUCCEEDED if exit_code == 0 else JobStatus.FAILED

    log_parts = []
    if stdout:
        log_parts.append(f"STDOUT:\n{stdout}")
    if stderr:
        log_parts.append(f"STDERR:\n{stderr}")

    result_msg = ""
    if final_status == JobStatus.SUCCEEDED:
        lines = [ln for ln in stdout.splitlines() if ln.strip()]
        result_msg = lines[-1] if lines else "Script completed successfully."
    else:
        err_lines = [ln for ln in stderr.splitlines() if ln.strip()]
        if err_lines:
            result_msg = err_lines[0]
        else:
            out_lines = [ln for ln in stdout.splitlines() if ln.strip()]
            result_msg = (
                out_lines[0] if out_lines else f"Script failed (code {exit_code}) with no output."
            )
        if not log_parts:
            log_parts.append("No standard output or error from script.")

    log_snippet = "\n\n".join(log_parts)
    # Truncate for DB
    result_msg = (result_msg[:1997] + "...") if len(result_msg) > 2000 else result_msg
    log_snippet = (log_snippet[:3997] + "...") if len(log_snippet) > 4000 else log_snippet

    return final_status, result_msg, log_snippet


async def _finalize_job_in_db(
    db: AsyncSession,
    job_db_id: UUID,
    status: JobStatus,
    exit_code: int,
    result_message: str,
    log_snippet: str,
    task_log_prefix: str,
):
    """Updates job completion details in the database."""
    logger.debug(f"{task_log_prefix} Attempting to update job completion details.")
    try:
        await crud_job.update_job_completion_details(
            db,
            job_id=job_db_id,
            status=status,
            completed_at=datetime.now(UTC),
            exit_code=exit_code,
            result_message=result_message,
            log_snippet=log_snippet,
        )
        logger.info(f"{task_log_prefix} Job final status updated to {status.value} in DB.")
    except Exception as e:
        logger.error(
            f"{task_log_prefix} FAILED to update job completion details in DB: {e}", exc_info=True
        )
        # Not re-raising to allow the primary task result to be returned if possible.


async def _handle_task_failure_in_db(
    db: AsyncSession,
    job_id: UUID,
    error: Exception | str,
    task_log_prefix: str,
    exit_code_override: int = -400,  # Default for general task error
    log_snippet_override: str | None = None,
):
    """Safely updates job to FAILED on task error."""
    err_str = str(error)
    result_message = f"Task failed: {err_str[:200]}"
    log_snippet = (
        log_snippet_override if log_snippet_override else f"Task error details: {err_str[:500]}"
    )

    logger.debug(f"{task_log_prefix} Attempting to mark job as FAILED due to task error.")
    try:
        await crud_job.update_job_completion_details(
            db,
            job_id=job_id,
            status=JobStatus.FAILED,
            completed_at=datetime.now(UTC),
            exit_code=exit_code_override,
            result_message=result_message,
            log_snippet=log_snippet,
        )
        logger.info(f"{task_log_prefix} Job marked as FAILED in DB due to task error.")
    except Exception as db_exc:
        logger.error(
            f"{task_log_prefix} Additionally FAILED to update DB on task error: {db_exc}",
            exc_info=True,
        )


# Celery task: Synchronous wrapper
@celery_app.task(
    name=settings.CELERY_SUBTITLE_TASK_NAME, bind=True, track_started=True, acks_late=True
)
def execute_subtitle_downloader_task(
    self: CeleryTaskDef, job_db_id_str: str, folder_path: str, language: str | None
):
    celery_internal_task_id = "unknown-celery-id"
    task_name_for_log = "unknown_task_name"

    if self.request and self.request.id:
        celery_internal_task_id = str(self.request.id)
    if self.name:
        task_name_for_log = str(self.name)

    wrapper_log_prefix = f"[CeleryTaskWrapper:{task_name_for_log} CeleryID:{celery_internal_task_id} DBJobID:{job_db_id_str}]"  # Log with job_db_id_str initially
    logger.info(f"{wrapper_log_prefix} SYNC WRAPPER ENTERED for DB Job ID {job_db_id_str}.")

    job_db_id = UUID(job_db_id_str)  # Convert once

    try:
        logger.info(f"{wrapper_log_prefix} Invoking asyncio.run() for async logic.")
        # It's crucial that any object shared with the async logic (like engine or sessionmaker)
        # is asyncio-compatible and handles loop transitions correctly.
        # AsyncSessionLocal itself should be fine as it creates sessions on demand.
        result = asyncio.run(
            _execute_subtitle_downloader_async_logic(
                task_name_for_log, celery_internal_task_id, job_db_id, folder_path, language
            )
        )
        logger.info(
            f"{wrapper_log_prefix} Async logic completed via asyncio.run(). Result: {result}"
        )
        logger.info(f"{wrapper_log_prefix} SYNC WRAPPER COMPLETED successfully.")
        return result
    except Exception as e:
        logger.error(
            f"{wrapper_log_prefix} Exception caught in SYNC WRAPPER from async logic/asyncio.run(): {type(e).__name__}: {e}",
            exc_info=True,
        )
        cleaned_error_message = (
            f"Async logic execution failed within wrapper: {type(e).__name__}: {str(e)[:500]}"
        )

        # Check if it's one of our pre-cleaned RuntimeErrors
        if isinstance(e, RuntimeError) and (
            "Task setup failed" in str(e)
            or "Task failed during main logic" in str(e)
            or "Unrecoverable error in async logic's outer scope" in str(e)
        ):
            # It's already a cleaned RuntimeError from the async logic.
            logger.warning(f"{wrapper_log_prefix} Propagating pre-cleaned error: {e}")
            # We still raise it so Celery marks task as failed with this specific message
        else:
            # This is a new/different exception, or an unhandled one from asyncio.run()
            logger.warning(
                f"{wrapper_log_prefix} Raising new cleaned error: {cleaned_error_message}"
            )

        # For Celery, always raise an exception to mark failure.
        # The original 'e' might contain non-serializable parts if it's from deep within asyncio/sqlalchemy.
        # So, we construct a new RuntimeError with a string representation.
        # The 'from None' is critical to prevent Celery from trying to serialize the original 'e' via __cause__ or __context__.
        raise RuntimeError(cleaned_error_message) from None
    finally:
        logger.info(f"{wrapper_log_prefix} SYNC WRAPPER EXITING.")
