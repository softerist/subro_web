# backend/app/tasks/subtitle_jobs.py
import asyncio
import logging
import traceback
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from celery import Task as CeleryTaskDef
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.crud_job import CRUDJob
from app.crud.crud_job import (
    job as crud_job_operations,
)
from app.db.session import get_worker_db_session
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
    Manages DB session via get_worker_db_session.
    """
    job_db_id_str = str(job_db_id)
    task_log_prefix = f"[AsyncTask:{task_name_for_log} CeleryID:{celery_internal_task_id} DBJobID:{job_db_id_str}]"
    logger.info(f"{task_log_prefix} ASYNC LOGIC ENTERED.")

    response = {
        "job_id": job_db_id_str,
        "status": JobStatus.FAILED.value,  # Default to FAILED
        "message": "Task execution did not complete as expected due to an early error.",
    }

    db_session_generator = get_worker_db_session()
    db: AsyncSession | None = None

    try:
        db = await db_session_generator.__anext__()
        # crud_job_operations is already an instance, no need to pass db for instantiation here

        # Pass crud_job_operations to helper functions
        await _setup_job_as_running(db, crud_job_operations, job_db_id, task_log_prefix)

        # Execute main task logic only if setup was successful
        response = await _execute_subtitle_script(
            db, crud_job_operations, job_db_id, folder_path, language, task_log_prefix
        )

    except RuntimeError as e:
        # This catches RuntimeErrors re-raised deliberately from helper functions
        err_msg = f"Critical error during async task execution: {type(e).__name__}: {e!s}"
        logger.error(f"{task_log_prefix} {err_msg}", exc_info=settings.LOG_TRACEBACKS)
        response = {
            "job_id": job_db_id_str,
            "status": JobStatus.FAILED.value,
            "error": f"Task execution failed: {str(e)[:settings.JOB_RESULT_MESSAGE_MAX_LEN]}",
        }
        if db and not str(e).startswith(
            "Task setup failed"
        ):  # Avoid double-handling setup failures
            try:
                await _handle_task_failure_in_db(
                    db, crud_job_operations, job_db_id, e, task_log_prefix, exit_code_override=-501
                )
            except Exception as db_final_fail_exc:
                logger.error(
                    f"{task_log_prefix} Additionally failed to update DB on critical async error: {db_final_fail_exc}"
                )
    except SQLAlchemyError as db_e:
        err_msg = f"Database operation failed in async task logic: {type(db_e).__name__}: {db_e!s}"
        logger.error(f"{task_log_prefix} {err_msg}", exc_info=settings.LOG_TRACEBACKS)
        response = {
            "job_id": job_db_id_str,
            "status": JobStatus.FAILED.value,
            "error": f"Database error: {str(db_e)[:settings.JOB_RESULT_MESSAGE_MAX_LEN]}",
        }
    except Exception as e:
        err_msg = f"Unhandled exception in async task logic: {type(e).__name__}: {e!s}"
        logger.error(f"{task_log_prefix} {err_msg}", exc_info=settings.LOG_TRACEBACKS)
        response = {
            "job_id": job_db_id_str,
            "status": JobStatus.FAILED.value,
            "error": f"Task execution failed unexpectedly: {str(e)[:settings.JOB_RESULT_MESSAGE_MAX_LEN]}",
        }
        if db:
            try:
                await _handle_task_failure_in_db(
                    db, crud_job_operations, job_db_id, e, task_log_prefix, exit_code_override=-502
                )
            except Exception as db_final_fail_exc:
                logger.error(
                    f"{task_log_prefix} Additionally failed to update DB on unhandled async error: {db_final_fail_exc}"
                )
        raise RuntimeError(f"Unhandled async error: {err_msg}") from e
    finally:
        if db_session_generator:
            try:
                await db_session_generator.aclose()
                logger.debug(f"{task_log_prefix} DB session generator closed.")
            except Exception as e_close:
                logger.error(f"{task_log_prefix} Error closing DB session generator: {e_close}")

    logger.info(f"{task_log_prefix} ASYNC LOGIC EXITING. Response: {response}")
    return response


async def _setup_job_as_running(
    db: AsyncSession, crud_ops: CRUDJob, job_db_id: UUID, task_log_prefix: str
):
    """Tries to update the job to RUNNING. Raises RuntimeError on failure."""
    logger.debug(f"{task_log_prefix} Attempting to update job to RUNNING.")
    try:
        current_time_utc = datetime.now(UTC)
        updated_job = await crud_ops.update_job_completion_details(
            db=db,  # Pass the db session
            job_id=job_db_id,
            status=JobStatus.RUNNING,
            started_at=current_time_utc,
        )
        await db.commit()  # Commit after successful update

        if not updated_job:
            err_msg = f"Job with ID {job_db_id} not found or failed to update to RUNNING (commit successful but no job returned)."
            logger.error(f"{task_log_prefix} {err_msg}")
            try:
                await _handle_task_failure_in_db(
                    db,
                    crud_ops,
                    job_db_id,
                    err_msg,
                    task_log_prefix,
                    exit_code_override=-300,
                    log_snippet_override="Failed to set job to RUNNING (job not found/returned post-commit).",
                )
            except Exception as db_fail_exc:
                logger.error(
                    f"{task_log_prefix} Additionally failed to update DB with setup failure info: {db_fail_exc}"
                )
            raise RuntimeError(f"Task setup failed: {err_msg}")
        logger.info(f"{task_log_prefix} Job status updated to RUNNING in DB and committed.")
    except SQLAlchemyError as db_exc:
        await db.rollback()
        err_msg = f"DB error updating job {job_db_id} to RUNNING: {db_exc}"
        logger.error(f"{task_log_prefix} {err_msg}", exc_info=settings.LOG_TRACEBACKS)
        raise RuntimeError(f"Task setup failed (DB update to RUNNING): {err_msg}") from db_exc
    except Exception as e:
        await db.rollback()
        err_msg = f"Unexpected error updating job {job_db_id} to RUNNING: {e}"
        logger.error(f"{task_log_prefix} {err_msg}", exc_info=settings.LOG_TRACEBACKS)
        raise RuntimeError(f"Task setup failed (unexpected error): {err_msg}") from e


async def _execute_subtitle_script(
    db: AsyncSession,
    crud_ops: type(crud_job_operations),
    job_db_id: UUID,
    folder_path: str,
    language: str | None,
    task_log_prefix: str,
) -> dict:
    """Execute the subtitle script, process results, and update DB. Raises RuntimeError on failure."""
    job_db_id_str = str(job_db_id)
    script_path = Path(settings.SUBTITLE_DOWNLOADER_SCRIPT_PATH)
    job_timeout = settings.JOB_TIMEOUT_SEC

    # Use Path.exists() instead of os.path.exists()
    if not script_path.exists():
        err_msg = f"Configuration error: Script not found at {script_path}"
        logger.error(f"{task_log_prefix} {err_msg}")
        await _handle_task_failure_in_db(
            db, crud_ops, job_db_id, err_msg, task_log_prefix, exit_code_override=-201
        )
        raise RuntimeError(err_msg)

    try:
        exit_code, stdout_b, stderr_b = await _run_script_and_get_output(
            str(script_path), folder_path, language, job_timeout, task_log_prefix
        )
        status, result_message, log_snippet = _parse_script_output(
            exit_code, stdout_b, stderr_b, task_log_prefix
        )
        await _finalize_job_in_db(
            db, crud_ops, job_db_id, status, exit_code, result_message, log_snippet, task_log_prefix
        )
        await db.commit()  # Commit after successful finalization

        return {"job_id": job_db_id_str, "status": status.value, "message": result_message}

    except SQLAlchemyError as db_e:
        await db.rollback()
        err_msg = (
            f"DB error during subtitle script finalization: " f"{type(db_e).__name__}: {db_e!s}"
        )
        logger.error(f"{task_log_prefix} {err_msg}", exc_info=settings.LOG_TRACEBACKS)
        try:
            await _handle_task_failure_in_db(
                db, crud_ops, job_db_id, db_e, task_log_prefix, exit_code_override=-202
            )
        except Exception as nested_db_exc:
            logger.error(
                f"{task_log_prefix} Additionally failed to update DB with script finalization DB failure info: {nested_db_exc}"
            )
        raise RuntimeError(f"Error in subtitle script phase (DB): {err_msg}") from db_e

    except Exception as e:
        await db.rollback()
        err_msg = f"Subtitle script execution/finalization failed: " f"{type(e).__name__}: {e!s}"
        logger.error(f"{task_log_prefix} {err_msg}", exc_info=settings.LOG_TRACEBACKS)
        try:
            await _handle_task_failure_in_db(
                db, crud_ops, job_db_id, e, task_log_prefix, exit_code_override=-200
            )
        except Exception as db_exc:
            logger.error(
                f"{task_log_prefix} Additionally failed to update DB with script execution failure info: {db_exc}"
            )
        raise RuntimeError(f"Error in subtitle script phase: {err_msg}") from e


async def _run_script_and_get_output(
    script_path: str,
    folder_path: str,
    language: str | None,
    job_timeout_sec: int,
    task_log_prefix: str,
) -> tuple[int, bytes, bytes]:
    """Executes script, manages timeout, returns (exit_code, stdout_bytes, stderr_bytes)."""
    cmd_args = [str(settings.PYTHON_EXECUTABLE_PATH), script_path, "--folder-path", folder_path]
    if language:
        cmd_args.extend(["--language", language])

    logger.info(f"{task_log_prefix} Executing command: {' '.join(cmd_args)}")

    stdout_b, stderr_b = b"", b""
    exit_code = -255  # Default for pre-execution failure

    process: asyncio.subprocess.Process | None = None
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        logger.debug(
            f"{task_log_prefix} Process (PID: {process.pid}) started. Awaiting communicate() with timeout {job_timeout_sec}s."
        )

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                process.communicate(), timeout=float(job_timeout_sec)
            )
            exit_code = process.returncode if process.returncode is not None else -1
            logger.info(
                f"{task_log_prefix} Script process (PID: {process.pid}) communicated. Exit code: {exit_code}."
            )
        except TimeoutError:
            logger.warning(
                f"{task_log_prefix} Script (PID: {process.pid}) timed out after {job_timeout_sec}s. Terminating."
            )
            exit_code = -99
            stderr_msg_timeout = f"\n[TASK_ERROR] Script execution timed out after {job_timeout_sec} seconds.".encode()
            stderr_b = stderr_b + stderr_msg_timeout if stderr_b else stderr_msg_timeout

            if process.returncode is None:
                try:
                    process.terminate()
                    logger.info(f"{task_log_prefix} Sent SIGTERM to process {process.pid}.")
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                    exit_code = process.returncode if process.returncode is not None else exit_code
                    logger.info(
                        f"{task_log_prefix} Process {process.pid} terminated gracefully. Exit code: {exit_code}"
                    )
                except TimeoutError:
                    logger.warning(
                        f"{task_log_prefix} Process {process.pid} did not terminate gracefully after SIGTERM. Sending SIGKILL."
                    )
                    process.kill()
                    await process.wait()
                    exit_code = process.returncode if process.returncode is not None else exit_code
                    logger.info(
                        f"{task_log_prefix} Process {process.pid} killed. Exit code: {exit_code}"
                    )
                except ProcessLookupError:
                    logger.warning(
                        f"{task_log_prefix} Process {process.pid} already exited before explicit termination was needed."
                    )
                except Exception as term_exc:
                    logger.error(
                        f"{task_log_prefix} Error during process termination for PID {process.pid}: {term_exc}"
                    )
            else:
                logger.info(
                    f"{task_log_prefix} Process {process.pid} had already exited with code {process.returncode} before timeout termination logic."
                )
                exit_code = process.returncode

    except Exception as comm_exc:
        logger.error(
            f"{task_log_prefix} Error during script subprocess management: {comm_exc}",
            exc_info=settings.LOG_TRACEBACKS,
        )
        exit_code = -98
        stderr_msg_comm = f"\n[TASK_ERROR] Error managing script process: {comm_exc!s}".encode()
        stderr_b = stderr_b + stderr_msg_comm if stderr_b else stderr_msg_comm
        if process and process.returncode is None:
            try:
                logger.warning(
                    f"{task_log_prefix} Attempting to kill process (PID: {process.pid}) due to subprocess management error."
                )
                process.kill()
                await process.wait()
                exit_code = process.returncode if process.returncode is not None else exit_code
            except Exception as kill_err:
                logger.error(
                    f"{task_log_prefix} Failed to kill process {getattr(process, 'pid', 'N/A')} after management error: {kill_err}"
                )

    return exit_code, stdout_b, stderr_b


def _parse_script_output(
    exit_code: int, stdout_bytes: bytes, stderr_bytes: bytes, task_log_prefix: str
) -> tuple[JobStatus, str, str]:
    """Parses script output into status, result message, and log snippet."""
    stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

    _log_raw_output(stdout, stderr, task_log_prefix)

    final_status = JobStatus.SUCCEEDED if exit_code == 0 else JobStatus.FAILED
    log_snippet = _build_log_snippet(stdout, stderr, final_status, exit_code)
    result_msg = _build_result_message(stdout, stderr, final_status, exit_code)

    result_msg = _trim(result_msg, settings.JOB_RESULT_MESSAGE_MAX_LEN)
    log_snippet = _trim(log_snippet, settings.JOB_LOG_SNIPPET_MAX_LEN)

    return final_status, result_msg, log_snippet


def _log_raw_output(stdout: str, stderr: str, prefix: str) -> None:
    if stdout:
        logger.debug(
            f"{prefix} STDOUT (first {settings.LOG_SNIPPET_PREVIEW_LEN} chars):\n"
            f"{stdout[:settings.LOG_SNIPPET_PREVIEW_LEN]}"
        )
    if stderr:
        logger.warning(
            f"{prefix} STDERR (first {settings.LOG_SNIPPET_PREVIEW_LEN} chars):\n"
            f"{stderr[:settings.LOG_SNIPPET_PREVIEW_LEN]}"
        )


def _build_log_snippet(stdout: str, stderr: str, status: JobStatus, code: int) -> str:
    parts = []
    if stdout:
        parts.append(f"STDOUT:\n{stdout}")
    if stderr:
        parts.append(f"STDERR:\n{stderr}")
    if not parts:
        info = (
            f"Script succeeded (code {code}) with no textual output."
            if status == JobStatus.SUCCEEDED
            else f"Script failed (code {code}) with no textual output."
        )
        parts.append(f"[INFO] {info}")
    return "\n\n".join(parts)


def _build_result_message(stdout: str, stderr: str, status: JobStatus, code: int) -> str:
    if status == JobStatus.SUCCEEDED:
        lines = [ln for ln in stdout.splitlines() if ln.strip()]
        return lines[-1] if lines else "Script completed successfully with no specific message."

    # failure
    err_lines = [ln for ln in stderr.splitlines() if ln.strip()]
    if err_lines:
        snippet = " | ".join(err_lines[:3])
        return snippet + ("..." if len(err_lines) > 3 else "")
    out_lines = [ln for ln in stdout.splitlines() if ln.strip()]
    if out_lines:
        return out_lines[0]
    return f"Script failed (code {code}) with no output."


def _trim(text: str, max_len: int) -> str:
    return text[: max_len - 3] + "..." if len(text) > max_len else text


async def _finalize_job_in_db(
    db: AsyncSession,
    crud_ops: type(crud_job_operations),
    job_db_id: UUID,
    status: JobStatus,
    exit_code: int,
    result_message: str,
    log_snippet: str,
    task_log_prefix: str,
):
    """Updates job completion details in the database. Raises RuntimeError on DB error."""
    logger.debug(
        f"{task_log_prefix} Attempting to stage job completion details with status {status.value}."
    )
    try:
        await crud_ops.update_job_completion_details(
            db=db,  # Pass the db session
            job_id=job_db_id,
            status=status,
            # completed_at will be set by update_job_completion_details if status is final
            exit_code=exit_code,
            result_message=result_message,
            log_snippet=log_snippet,
        )
        logger.info(
            f"{task_log_prefix} Job final status attributes prepared for commit (status: {status.value})."
        )
        # Commit is handled by the caller (_execute_subtitle_script)
    except Exception as e:
        logger.error(
            f"{task_log_prefix} FAILED to stage job completion details for commit: {e}",
            exc_info=settings.LOG_TRACEBACKS,
        )
        raise RuntimeError(f"Failed to finalize job in DB: {e}") from e


async def _handle_task_failure_in_db(
    db: AsyncSession,
    crud_ops: type(crud_job_operations),
    job_id: UUID,
    error: Exception | str,
    task_log_prefix: str,
    exit_code_override: int = -400,
    log_snippet_override: str | None = None,
):
    """Safely attempts to update job to FAILED. Commits changes. Does not re-raise from itself."""
    err_str = str(error)
    result_message_full = (
        f"Task failed: {type(error).__name__}: {err_str}"
        if isinstance(error, Exception)
        else f"Task failed: {err_str}"
    )

    tb_str = ""
    if isinstance(error, Exception) and settings.LOG_TRACEBACKS_IN_JOB_LOGS:
        tb_str = f"\nTraceback:\n{traceback.format_exc()}"

    log_snippet_full = (
        log_snippet_override
        if log_snippet_override
        else f"Task error details: {result_message_full}{tb_str}"
    )

    result_message = (
        (result_message_full[: settings.JOB_RESULT_MESSAGE_MAX_LEN - 3] + "...")
        if len(result_message_full) > settings.JOB_RESULT_MESSAGE_MAX_LEN
        else result_message_full
    )
    log_snippet = (
        (log_snippet_full[: settings.JOB_LOG_SNIPPET_MAX_LEN - 3] + "...")
        if len(log_snippet_full) > settings.JOB_LOG_SNIPPET_MAX_LEN
        else log_snippet_full
    )

    logger.debug(f"{task_log_prefix} Attempting to mark job as FAILED due to task error: {error}")
    try:
        await crud_ops.update_job_completion_details(
            db=db,  # Pass the db session
            job_id=job_id,
            status=JobStatus.FAILED,
            # completed_at will be set by update_job_completion_details
            exit_code=exit_code_override,
            result_message=result_message,
            log_snippet=log_snippet,
        )
        await db.commit()  # Commit the failure update
        logger.info(
            f"{task_log_prefix} Job marked as FAILED in DB due to task error and committed."
        )
    except Exception as db_exc:
        logger.error(
            f"{task_log_prefix} Additionally FAILED to update DB on task error: {db_exc}",
            exc_info=settings.LOG_TRACEBACKS,
        )
        try:
            await db.rollback()
            logger.info(
                f"{task_log_prefix} Rolled back DB transaction after failing to mark job as FAILED."
            )
        except Exception as rb_exc:
            logger.error(
                f"{task_log_prefix} Rollback also failed after failing to update DB on task error: {rb_exc}"
            )


@celery_app.task(
    name=settings.CELERY_SUBTITLE_TASK_NAME,
    bind=True,
    track_started=True,
    acks_late=True,
    # task_soft_time_limit=settings.JOB_TIMEOUT_SEC + 60,
    # task_time_limit=settings.JOB_TIMEOUT_SEC + 120,
)
def execute_subtitle_downloader_task(
    self: CeleryTaskDef, job_db_id_str: str, folder_path: str, language: str | None
):
    celery_internal_task_id = (
        str(self.request.id) if self.request and self.request.id else "unknown-celery-id"
    )
    task_name_for_log = self.name

    wrapper_log_prefix = f"[CeleryTaskWrapper:{task_name_for_log} CeleryID:{celery_internal_task_id} DBJobID:{job_db_id_str}]"
    logger.info(
        f"{wrapper_log_prefix} SYNC WRAPPER ENTERED for job on folder '{folder_path}', lang '{language}'."
    )

    try:
        job_db_id = UUID(job_db_id_str)
    except ValueError:
        logger.error(
            f"{wrapper_log_prefix} Invalid job_db_id_str: '{job_db_id_str}'. Cannot proceed.",
            exc_info=True,
        )
        raise ValueError(
            f"Invalid Job DB ID format provided to Celery task: {job_db_id_str}"
        ) from None

    result = None
    try:
        logger.info(f"{wrapper_log_prefix} Invoking asyncio.run() for async logic.")
        result = asyncio.run(
            _execute_subtitle_downloader_async_logic(
                task_name_for_log, celery_internal_task_id, job_db_id, folder_path, language
            )
        )
        logger.info(
            f"{wrapper_log_prefix} Async logic completed. Raw result: {str(result)[:500]}..."
        )

        if isinstance(result, dict) and result.get("status") == JobStatus.FAILED.value:
            failure_message = result.get(
                "error",
                result.get(
                    "message", "Async logic reported failure without specific error message."
                ),
            )
            logger.warning(
                f"{wrapper_log_prefix} Async logic reported failure: '{failure_message}'. Raising RuntimeError for Celery."
            )
            raise RuntimeError(f"Task failed as per async logic: {failure_message}")

        logger.info(f"{wrapper_log_prefix} SYNC WRAPPER COMPLETED successfully.")
        return result

    except RuntimeError as e:
        logger.error(
            f"{wrapper_log_prefix} RuntimeError caught in SYNC WRAPPER: {e}",
            exc_info=settings.LOG_TRACEBACKS_CELERY_WRAPPER,
        )
        raise
    except Exception as e:
        logger.error(
            f"{wrapper_log_prefix} Unexpected exception caught in SYNC WRAPPER: {type(e).__name__}: {e}",
            exc_info=settings.LOG_TRACEBACKS_CELERY_WRAPPER,
        )
        error_message_for_celery = f"Celery task wrapper encountered an unexpected error: {type(e).__name__}: {str(e)[:500]}"
        raise RuntimeError(error_message_for_celery) from e
    finally:
        logger.info(f"{wrapper_log_prefix} SYNC WRAPPER EXITING.")
