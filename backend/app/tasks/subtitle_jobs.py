# backend/app/tasks/subtitle_jobs.py

import asyncio
import logging
import sys
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession  # Ensure this is imported for type hints

# Assuming these are your project's specific imports
from app.core.config import settings
from app.db.crud import job as crud_job
from app.db.session import AsyncSessionLocal  # Your async SQLAlchemy session factory
from app.schemas.job import JobStatus  # Your JobStatus enum

# Placeholder for your Celery app instance if you define tasks in this file
# from app.core.celery_app import celery_app # Example

logger = logging.getLogger(__name__)

# --- Helper Functions ---


async def _handle_task_failure_in_db(
    db: AsyncSession,
    job_id: UUID,
    error: Exception | str,
    task_log_prefix: str,
    exit_code_override: int = -400,  # Default for general task error
    log_snippet_override: str | None = None,
):
    """Safely updates job to FAILED on task error, minimizing chance of further exceptions."""
    err_str = str(error)
    result_message = f"Task failed: {err_str[:1997]}" + ("..." if len(err_str) > 2000 else "")
    log_snippet_detail = (
        log_snippet_override
        if log_snippet_override
        else f"Task error details: {err_str[:3997]}" + ("..." if len(err_str) > 4000 else "")
    )

    logger.debug(f"{task_log_prefix} Attempting to mark job as FAILED due to task error: {error}")
    try:
        await crud_job.update_job_completion_details(
            db,
            job_id=job_id,
            status=JobStatus.FAILED,
            completed_at=datetime.now(UTC),
            exit_code=exit_code_override,
            result_message=result_message,
            log_snippet=log_snippet_detail,
        )
        logger.info(f"{task_log_prefix} Job marked as FAILED in DB due to task error.")
    except Exception as db_exc:
        logger.error(
            f"{task_log_prefix} CRITICAL: Additionally FAILED to update DB on task error. Original error: {error}. DB update error: {db_exc}",
            exc_info=True,
        )


async def _setup_job_as_running(
    db: AsyncSession, job_db_id: UUID, task_log_prefix: str
) -> dict | None:
    """
    Tries to update the job to RUNNING.
    Returns an error dictionary if the job cannot be set to RUNNING (e.g., not found).
    Raises DB-related exceptions if they occur during the update attempt.
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
            # Attempt to mark as failed in DB, but this helper focuses on logical failure.
            # The caller (_execute_...) will handle the DB update for this specific failure.
            await _handle_task_failure_in_db(
                db,
                job_db_id,
                err_msg,
                task_log_prefix,
                exit_code_override=-300,  # Specific code for setup failure
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
        # This is a more critical DB error during the setup phase.
        # Don't try to update DB further here if the connection itself might be the issue.
        err_msg = f"DB error updating job {job_db_id} to RUNNING: {db_exc}"
        logger.error(f"{task_log_prefix} {err_msg}", exc_info=True)
        raise RuntimeError(f"Task setup failed (DB update to RUNNING): {err_msg}") from db_exc


async def _run_script_and_get_output(
    script_path: str,
    folder_path: str,
    language: str | None,
    job_timeout: int,
    task_log_prefix: str,
) -> tuple[int, bytes, bytes]:
    """Executes external script, manages timeout, and returns (exit_code, stdout_bytes, stderr_bytes)."""
    cmd_args = [sys.executable, script_path, "--folder-path", folder_path]
    if language:
        cmd_args.extend(["--language", language])

    logger.info(f"{task_log_prefix} Executing command: {' '.join(cmd_args)}")
    process = await asyncio.create_subprocess_exec(
        *cmd_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    stdout_b, stderr_b = b"", b""
    # Default exit code for unhandled scenarios, though specific codes are preferred.
    exit_code = -1

    try:
        logger.debug(
            f"{task_log_prefix} Awaiting process.communicate() with timeout {job_timeout}s."
        )
        stdout_b, stderr_b = await asyncio.wait_for(process.communicate(), timeout=job_timeout)
        exit_code = (
            process.returncode if process.returncode is not None else -100
        )  # Script finished but no exit code
        logger.info(f"{task_log_prefix} Script process communicated. Exit code: {exit_code}.")
    except TimeoutError:
        logger.warning(
            f"{task_log_prefix} Script execution timed out after {job_timeout}s. Attempting to terminate."
        )
        exit_code = -99  # Specific exit code for timeout
        stderr_b += f"\nScript execution timed out after {job_timeout} seconds.".encode()
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5.0)  # Give it a moment to terminate
            logger.info(f"{task_log_prefix} Process terminated after timeout.")
        except TimeoutError:
            logger.warning(f"{task_log_prefix} Process terminate() timed out. Killing process.")
            process.kill()
            await process.wait()  # Ensure kill is processed
            logger.info(f"{task_log_prefix} Process killed after terminate() timeout.")
        except Exception as term_exc:
            logger.error(
                f"{task_log_prefix} Exception during process termination: {term_exc}", exc_info=True
            )
            if process.returncode is None:  # If still running
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass  # Best effort
    except Exception as comm_exc:
        logger.error(
            f"{task_log_prefix} Error during process.communicate(): {comm_exc}", exc_info=True
        )
        exit_code = -98  # Specific code for communication error
        stderr_b += f"\nError communicating with script process: {comm_exc!s}".encode()
        if process.returncode is None:  # If process might still be running
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass  # Best effort

    return exit_code, stdout_b, stderr_b


def _parse_script_output(
    exit_code: int, stdout_bytes: bytes, stderr_bytes: bytes, task_log_prefix: str
) -> tuple[JobStatus, str, str]:
    """Parses script output into status, result message, and log snippet."""
    stdout_str = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()

    if stdout_str:
        logger.debug(f"{task_log_prefix} STDOUT (last 1000 chars):\n{stdout_str[-1000:]}")
    if stderr_str:
        # Use warning for stderr as it often indicates issues, even if exit code is 0
        logger.warning(f"{task_log_prefix} STDERR (last 1000 chars):\n{stderr_str[-1000:]}")

    final_status = JobStatus.SUCCEEDED if exit_code == 0 else JobStatus.FAILED

    log_snippet_parts = []
    if stdout_str:
        log_snippet_parts.append(f"STDOUT:\n{stdout_str}")
    if stderr_str:
        log_snippet_parts.append(f"STDERR:\n{stderr_str}")

    result_message = ""
    if final_status == JobStatus.SUCCEEDED:
        stdout_lines = [line for line in stdout_str.splitlines() if line.strip()]
        result_message = stdout_lines[-1] if stdout_lines else "Script completed successfully."
    else:  # FAILED
        stderr_lines = [line for line in stderr_str.splitlines() if line.strip()]
        if stderr_lines:
            result_message = stderr_lines[0]  # First line of error often most relevant
        else:  # No stderr, check stdout for clues
            stdout_lines = [line for line in stdout_str.splitlines() if line.strip()]
            if stdout_lines:
                result_message = stdout_lines[0]
            else:
                result_message = f"Script failed with exit code {exit_code} and no output."

    if not log_snippet_parts:  # Ensure there's always some log content
        log_snippet_parts.append("No standard output or error from script.")

    # Truncate for database storage
    log_snippet_full = "\n\n".join(log_snippet_parts)
    final_result_message = (
        (result_message[:1997] + "...") if len(result_message) > 2000 else result_message
    )
    final_log_snippet = (
        (log_snippet_full[:3997] + "...") if len(log_snippet_full) > 4000 else log_snippet_full
    )

    return final_status, final_result_message, final_log_snippet


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
    logger.debug(f"{task_log_prefix} Attempting to update job completion details in DB.")
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
            f"{task_log_prefix} CRITICAL: FAILED to update job completion details in DB. Job: {job_db_id}, Status: {status}, Error: {e}",
            exc_info=True,
        )
        # Not re-raising here to allow the Celery task to potentially return its primary result.
        # However, this is a significant failure state.


# --- Main Orchestrator Function ---


async def _execute_subtitle_downloader_async_logic(
    task_name_for_log: str,
    celery_internal_task_id: str,
    job_db_id: UUID,
    folder_path: str,
    language: str | None,
) -> dict:  # Celery tasks often return a dictionary
    task_log_prefix = (
        f"[CeleryTask:{task_name_for_log} CeleryID:{celery_internal_task_id} DBJobID:{job_db_id}]"
    )
    logger.info(
        f"{task_log_prefix} ASYNC LOGIC ENTERED. Args: folder_path='{folder_path}', language='{language}'"
    )

    # Prepare a default failure payload, to be updated as task progresses or fails
    task_result_payload: dict = {
        "job_id": str(job_db_id),
        "status": JobStatus.FAILED.value,  # Default to FAILED
        "celery_task_id": celery_internal_task_id,
        "error": "Task processing started but encountered an unhandled issue.",
        "exit_code": -500,  # Generic task error code
    }

    try:
        async with AsyncSessionLocal() as db:
            logger.debug(f"{task_log_prefix} DB session acquired.")

            # 1. Attempt to set job to RUNNING
            initial_setup_error_payload = await _setup_job_as_running(
                db, job_db_id, task_log_prefix
            )
            if initial_setup_error_payload:
                # _setup_job_as_running already logged, updated DB (if possible), and returned error details.
                task_result_payload.update(initial_setup_error_payload)
                logger.error(
                    f"{task_log_prefix} ASYNC LOGIC FAILED during initial setup. Result: {task_result_payload}"
                )
                return task_result_payload

            # 2. Main script execution and output processing block
            # Errors here are related to script execution or processing its results.
            try:
                exit_code, stdout_bytes, stderr_bytes = await _run_script_and_get_output(
                    settings.DOWNLOAD_SCRIPT_PATH,
                    folder_path,
                    language,
                    settings.JOB_TIMEOUT_SEC,
                    task_log_prefix,
                )

                final_status, result_msg, log_snip = _parse_script_output(
                    exit_code, stdout_bytes, stderr_bytes, task_log_prefix
                )

                await _finalize_job_in_db(
                    db, job_db_id, final_status, exit_code, result_msg, log_snip, task_log_prefix
                )

                task_result_payload = {
                    "job_id": str(job_db_id),
                    "status": final_status.value,
                    "exit_code": exit_code,
                    "result_message": result_msg,  # This is already truncated
                    "celery_task_id": celery_internal_task_id,
                }
                # No "error" key if successful or script failed gracefully
                if final_status == JobStatus.FAILED:
                    task_result_payload["error"] = (
                        result_msg  # Use result_msg as error for failed scripts
                    )

                logger.info(
                    f"{task_log_prefix} ASYNC LOGIC COMPLETED (script part). Result: {task_result_payload}"
                )
                return task_result_payload

            except Exception as main_logic_exc:
                # This catches errors from _run_script_and_get_output, _parse_script_output,
                # or _finalize_job_in_db if it were to re-raise.
                err_msg = (
                    f"Critical error during script execution/processing phase: {main_logic_exc}"
                )
                logger.error(f"{task_log_prefix} {err_msg}", exc_info=True)
                # Attempt to update DB to FAILED status
                await _handle_task_failure_in_db(
                    db, job_db_id, main_logic_exc, task_log_prefix, exit_code_override=-401
                )

                task_result_payload["error"] = err_msg
                task_result_payload["exit_code"] = -401  # Specific code for this failure phase
                # Raise a clean RuntimeError to be caught by the Celery task mechanism if it's
                # configured to handle exceptions as task failures. Otherwise, the dict is returned.
                # For robustness, we'll let Celery decide based on its error handling.
                raise RuntimeError(f"Task failed during main logic: {err_msg}") from main_logic_exc

    except RuntimeError as e:
        # This catches RuntimeErrors propagated from _setup_job_as_running (DB issue)
        # or from the main_logic_exc block.
        # The DB status *should* have been updated to FAILED by the raiser or _handle_task_failure_in_db.
        logger.critical(
            f"{task_log_prefix} ASYNC LOGIC FAILED (RuntimeError). Propagated Error: {e}",
            exc_info=False,
        )  # exc_info already logged by original raiser
        task_result_payload["error"] = str(e)
        # Re-raise so Celery can mark the task as failed appropriately.
        raise
    except Exception as outer_exc:
        # Catches truly unexpected errors (e.g., AsyncSessionLocal() itself failing before `async with`)
        # or any other unhandled exception.
        final_err_msg = f"Unrecoverable error in async logic's outer scope: {type(outer_exc).__name__}: {outer_exc}"
        logger.critical(
            f"{task_log_prefix} ASYNC LOGIC FAILED (UNRECOVERABLE). {final_err_msg}",
            exc_info=True,
        )
        task_result_payload["error"] = final_err_msg
        task_result_payload["exit_code"] = -501  # Code for unrecoverable outer error

        # At this point, updating the DB is highly unlikely/risky.
        # We will re-raise a generic RuntimeError. Celery should handle this.
        raise RuntimeError(final_err_msg) from outer_exc
    finally:
        # This finally block executes regardless of exceptions.
        # The return statement for success/handled failure is within the try block.
        # If an exception is raised and not caught internally, it propagates out.
        logger.info(
            f"{task_log_prefix} ASYNC LOGIC EXITING. Final payload state if returned (may be overridden by exception): {task_result_payload}"
        )
        # If Celery *requires* a dict return even on unhandled exceptions (not typical),
        # you'd return task_result_payload here. But re-raising is standard.


# Example of how this might be used in a Celery task:
#
# from app.core.celery_app import celery_app # Your Celery app instance
#
# @celery_app.task(name="tasks.download_subtitles", bind=True)
# def download_subtitles_task(
#     self, job_db_id_str: str, folder_path: str, language: str | None = None
# ):
#     """
#     Celery task to download subtitles for videos in a folder.
#     This is the synchronous wrapper for the async logic.
#     """
#     task_name_for_log = self.name # "tasks.download_subtitles"
#     celery_internal_task_id = self.request.id
#     job_db_id = UUID(job_db_id_str)
#
#     # General log for task received by worker
#     logger.info(
#         f"[CeleryTask:{task_name_for_log} CeleryID:{celery_internal_task_id} DBJobID:{job_db_id}] Task received by worker. Args: folder='{folder_path}', lang='{language}'"
#     )
#
#     try:
#         # Run the async function using asyncio.run() or an event loop manager
#         # if your Celery worker is not already async-aware.
#         # If using Celery 5+ with an async worker (e.g., gevent with monkeypatching, or solo pool with asyncio),
#         # you might be able to directly await. For simplicity, using asyncio.run() here.
#         loop = asyncio.new_event_loop()
#         asyncio.set_event_loop(loop)
#         result = loop.run_until_complete(
#             _execute_subtitle_downloader_async_logic(
#                 task_name_for_log=task_name_for_log,
#                 celery_internal_task_id=str(celery_internal_task_id), # Ensure it's
