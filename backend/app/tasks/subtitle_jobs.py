# backend/app/tasks/subtitle_jobs.py
from __future__ import annotations

import asyncio
import json
import logging
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import redis.asyncio as aioredis
from celery import Task as CeleryTaskDef
from celery import states
from celery.exceptions import Ignore, TaskRevokedError, Terminated

# asyncio.CancelledError is a built-in exception
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud.crud_job import CRUDJob
from app.crud.crud_job import job as crud_job_operations
from app.db.session import get_worker_db_session
from app.exceptions import (
    JobAlreadyCancellingError,
    JobAlreadyTerminalError,
    JobNotFoundErrorForSetup,
    TaskSetupError,
)
from app.schemas.job import JobStatus
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


# Define EXIT_CODE constants for clarity (these should ideally live in a constants module or config)
EXIT_CODE_SUCCESS = 0
EXIT_CODE_GENERIC_FAILURE = -1
EXIT_CODE_CANCELLED_BY_USER = -100  # From _handle_job_cancellation_finalization (default)
EXIT_CODE_CANCELLED_TERMINATION = -101  # From _handle_terminated_job_in_db
EXIT_CODE_CANCELLED_RACE_CONDITION = -102  # From _finalize_job_after_script
EXIT_CODE_CANCELLED_SETUP_ABORT_CANCELLING = -103  # If JobAlreadyCancellingError during setup
EXIT_CODE_CANCELLED_SETUP_ABORT_PREEMPTIVE_ASYNC = (
    -104
)  # If asyncio.CancelledError during setup (from _execute_subtitle_script)
EXIT_CODE_SCRIPT_NOT_FOUND = -201
EXIT_CODE_SUBPROCESS_SETUP_FAILED = (
    -254
)  # from _setup_subprocess or _handle_script_timeout if script never started
EXIT_CODE_SUBPROCESS_CREATE_FAILED = -250  # from _setup_subprocess
EXIT_CODE_SCRIPT_TIMEOUT = -99
EXIT_CODE_TASK_WRAPPER_ERROR = -600
EXIT_CODE_TERMINATED_BY_SIGNAL = (
    -700
)  # From _handle_terminated_job_in_db as fallback if not a specific cancellation code


async def _publish_to_redis_pubsub_async(
    redis_client: aioredis.Redis,
    job_db_id_str: str,
    message_type: Literal["status", "log", "info"],
    payload: dict,
    task_log_prefix: str,
):
    """
    Publishes a message to a job-specific Redis Pub/Sub channel.
    """
    channel = f"job:{job_db_id_str}:logs"
    if "ts" not in payload:
        payload["ts"] = datetime.now(UTC).isoformat()
    elif isinstance(payload["ts"], datetime):
        payload["ts"] = payload["ts"].isoformat()

    message_data = {"type": message_type, "payload": payload}
    try:
        json_message = json.dumps(message_data)
        await redis_client.publish(channel, json_message)

        if message_type == "status":
            logger.info(
                f"{task_log_prefix} Published STATUS to Redis Pub/Sub channel '{channel}': {payload.get('status', 'N/A')}"
            )
        elif message_type == "log":
            logger.debug(f"{task_log_prefix} Published LOG to Redis Pub/Sub channel '{channel}'")
        elif message_type == "info":
            logger.info(
                f"{task_log_prefix} Published INFO to Redis Pub/Sub channel '{channel}': {payload.get('message', 'N/A')}"
            )

        if settings.DEBUG:  # Assuming settings.DEBUG exists
            logger.debug(f"{task_log_prefix} Pub/Sub message data: {json_message}")
    except aioredis.RedisError as e_redis:
        logger.error(
            f"{task_log_prefix} Redis Pub/Sub publish error to channel '{channel}': {e_redis}",
            exc_info=settings.LOG_TRACEBACKS,
        )
    except Exception as e_general:
        logger.error(
            f"{task_log_prefix} Unexpected error during Redis Pub/Sub publish to channel '{channel}': {e_general}",
            exc_info=settings.LOG_TRACEBACKS,
        )


async def _read_stream_and_publish(
    stream_reader: asyncio.StreamReader,
    stream_name: Literal["stdout", "stderr"],
    redis_client: aioredis.Redis | None,
    job_db_id_str: str,
    task_log_prefix: str,
    output_buffer: list[bytes],
):
    """
    Reads lines from a stream, publishes them to Redis Pub/Sub, and appends to buffer.
    """
    while True:
        try:
            line_bytes = await stream_reader.readline()
        except Exception as e:
            logger.error(
                f"{task_log_prefix} Error reading from {stream_name}: {e}",
                exc_info=settings.LOG_TRACEBACKS,
            )
            break

        if not line_bytes:
            break
        output_buffer.append(line_bytes)
        line_str = line_bytes.decode("utf-8", errors="replace").strip()
        if redis_client:
            await _publish_to_redis_pubsub_async(
                redis_client,
                job_db_id_str,
                "log",
                {"stream": stream_name, "message": line_str},
                task_log_prefix,
            )


async def _handle_job_cancellation_finalization(
    db: AsyncSession,
    redis_client: aioredis.Redis | None,
    crud_ops: CRUDJob,
    job_db_id: UUID,
    stdout_accumulator: list[bytes],
    stderr_accumulator: list[bytes],
    task_log_prefix: str,
    cancellation_message: str = "Job cancelled by user request.",
    exit_code_for_cancelled_job: int = -100,
) -> dict:
    """Handles the final DB update and Pub/Sub notification for a CANCELLED job."""
    job_db_id_str = str(job_db_id)
    logger.warning(
        f"{task_log_prefix} Finalizing job {job_db_id_str} as CANCELLED. Message: {cancellation_message}"
    )

    log_snippet_cancelled = _build_log_snippet(
        b"".join(stdout_accumulator).decode("utf-8", errors="replace"),
        b"".join(stderr_accumulator).decode("utf-8", errors="replace"),
        JobStatus.CANCELLED,
        exit_code_for_cancelled_job,
        task_log_prefix,
    )
    log_snippet_cancelled = _trim(log_snippet_cancelled, settings.JOB_LOG_SNIPPET_MAX_LEN)

    try:
        cancellation_time_utc = datetime.now(UTC)
        await crud_ops.update_job_completion_details(
            db=db,
            job_id=job_db_id,
            status=JobStatus.CANCELLED,
            exit_code=exit_code_for_cancelled_job,
            result_message=_trim(cancellation_message, settings.JOB_RESULT_MESSAGE_MAX_LEN),
            log_snippet=log_snippet_cancelled,
            completed_at=cancellation_time_utc,
        )

        if redis_client:
            await _publish_to_redis_pubsub_async(
                redis_client,
                job_db_id_str,
                "status",
                {
                    "status": JobStatus.CANCELLED.value,
                    "ts": cancellation_time_utc,
                    "message": cancellation_message,
                    "exit_code": exit_code_for_cancelled_job,
                },
                task_log_prefix,
            )
        logger.info(
            f"{task_log_prefix} Job {job_db_id_str} successfully finalized as CANCELLED in DB (pending commit by caller) and Pub/Sub updated."
        )
        return {
            "job_id": job_db_id_str,
            "status": JobStatus.CANCELLED.value,
            "message": cancellation_message,
            "exit_code": exit_code_for_cancelled_job,
        }
    except Exception as e_finalization:
        logger.error(
            f"{task_log_prefix} Error during job cancellation finalization for {job_db_id_str}: {e_finalization}",
            exc_info=settings.LOG_TRACEBACKS,
        )
        raise RuntimeError(
            f"Failed to finalize job as CANCELLED: {e_finalization}"
        ) from e_finalization


async def _execute_subtitle_downloader_async_logic(
    task_name_for_log: str,
    celery_internal_task_id: str,
    job_db_id: UUID,
    folder_path: str,
    language: str | None,
) -> dict:
    """
    Main orchestrator for the async task logic. It no longer manages a single
    database session, instead delegating session management to its helpers
    to ensure data freshness at each critical step.
    """
    job_db_id_str = str(job_db_id)
    task_log_prefix = f"[AsyncTask:{task_name_for_log} CeleryID:{celery_internal_task_id} DBJobID:{job_db_id_str}]"
    logger.info(f"{task_log_prefix} ASYNC LOGIC ENTERED.")

    # Initialize resources
    redis_client = await _initialize_redis_client(settings.REDIS_PUBSUB_URL, task_log_prefix)
    stdout_accumulator: list[bytes] = []
    stderr_accumulator: list[bytes] = []
    response = {
        "job_id": job_db_id_str,
        "status": JobStatus.FAILED.value,
        "exit_code": -1,
    }  # Default error response

    try:
        # STEP 1: Set the job to RUNNING. This function now manages its own DB session.
        await _setup_job_as_running(
            redis_client, crud_job_operations, job_db_id, celery_internal_task_id, task_log_prefix
        )

        # Check for script existence before running
        script_path = Path(settings.SUBTITLE_DOWNLOADER_SCRIPT_PATH)
        if not script_path.exists():
            # This will be caught by the general exception handler below
            raise FileNotFoundError(
                f"Configuration error: Subtitle downloader script not found at {script_path}"
            )

        # STEP 2: Execute the long-running external script. This step does not interact with the DB.
        exit_code_from_script = await _run_script_and_get_output(
            script_path=str(script_path),
            folder_path=folder_path,
            language=language,
            job_timeout_sec=float(settings.JOB_TIMEOUT_SEC),
            task_log_prefix=task_log_prefix,
            redis_client=redis_client,
            job_db_id_str=job_db_id_str,
            stdout_accumulator=stdout_accumulator,
            stderr_accumulator=stderr_accumulator,
        )

        # STEP 3: Finalize the job. This function opens a NEW, FRESH DB session
        # to guarantee it sees any changes made by the API during script execution.
        response = await _finalize_job_after_script(
            redis_client,
            crud_job_operations,
            job_db_id,
            exit_code_from_script,
            b"".join(stdout_accumulator),
            b"".join(stderr_accumulator),
            task_log_prefix,
        )

    except (JobAlreadyCancellingError, JobAlreadyTerminalError) as e:
        # This handles the case where _setup_job_as_running finds the job
        # is already cancelled/finished before it even starts.
        logger.warning(f"{task_log_prefix} Task setup aborted: {e}.")
        response = await _handle_job_cancellation_finalization(
            redis_client,
            crud_job_operations,
            job_db_id,
            str(e),
            task_log_prefix,
            exit_code_override=-104,
        )
    except Exception as e:
        # A general catch-all for any other unexpected errors (e.g., script not found, DB connection issues).
        logger.error(
            f"{task_log_prefix} Unhandled exception in async logic: {type(e).__name__}: {e}",
            exc_info=True,
        )
        response = await _handle_task_failure_in_db(
            None,  # No db session here, handler will create its own
            redis_client,
            crud_job_operations,
            job_db_id,
            e,
            task_log_prefix,
            exit_code_override=-500,
        )
    finally:
        # Cleanup resources
        if redis_client:
            await redis_client.close()
        logger.info(
            f"{task_log_prefix} ASYNC LOGIC EXITING. Final determined status: {response.get('status')}"
        )

    return response


async def _create_default_error_response(job_id_str: str) -> dict:  # Renamed job_id to job_id_str
    """Create a default error response for early task failures."""
    return {
        "job_id": job_id_str,
        "status": JobStatus.FAILED.value,
        "message": "Task execution did not complete as expected due to an early error.",
        "error_type": "EarlyTaskError",
        "exit_code": -1,  # Generic early error code
    }


async def _initialize_redis_client(
    redis_url: str | None, task_log_prefix: str
) -> aioredis.Redis | None:
    """Initialize and connect Redis client for real-time updates."""
    if not redis_url:
        logger.warning(
            f"{task_log_prefix} REDIS_PUBSUB_URL not configured. Real-time updates will be disabled."
        )
        return None

    try:
        redis_client = await aioredis.from_url(str(redis_url))
        logger.info(f"{task_log_prefix} Redis client for Pub/Sub connected.")
        return redis_client
    except (aioredis.RedisError, Exception) as e_redis_conn:
        logger.error(
            f"{task_log_prefix} Failed to connect to Redis for Pub/Sub: {e_redis_conn}",
            exc_info=settings.LOG_TRACEBACKS,
        )
        return None


async def _execute_main_task_logic(
    job_db_id: UUID,
    celery_task_id: str,  # Renamed from celery_internal_task_id for clarity
    folder_path: str,
    language: str | None,
    task_log_prefix: str,
    redis_client: aioredis.Redis | None,
    stdout_accumulator: list[bytes],
    stderr_accumulator: list[bytes],
) -> dict:
    """Main task execution block with DB session management and specific error handling."""
    job_db_id_str = str(job_db_id)  # For convenience in this scope

    async with get_worker_db_session() as db:
        try:
            await _setup_job_as_running(
                db,
                redis_client,
                crud_job_operations,
                job_db_id,
                celery_task_id,  # This is the Celery task ID
                task_log_prefix,
            )

            script_path_setting = Path(settings.SUBTITLE_DOWNLOADER_SCRIPT_PATH)
            if not script_path_setting.exists():
                return await _handle_missing_script(
                    db, redis_client, job_db_id, task_log_prefix, script_path_setting
                )

            result_dict = await _execute_subtitle_script(
                db,
                redis_client,
                crud_job_operations,
                job_db_id,
                folder_path,
                language,
                task_log_prefix,
                stdout_accumulator,
                stderr_accumulator,
            )
            # Commit happens automatically if this block exits without unhandled exceptions.
            # _finalize_job_in_db (normal completion) and _handle_job_cancellation_finalization
            # (if called by _execute_subtitle_script) stage DB changes.
            return result_dict

        except JobAlreadyCancellingError as e_cancelling:
            logger.warning(
                f"{task_log_prefix} Task setup aborted: {e_cancelling}. Finalizing as CANCELLED."
            )
            # Use the 'db' session from this context.
            final_response = await _handle_job_cancellation_finalization(
                db,
                redis_client,
                crud_job_operations,
                job_db_id,
                stdout_accumulator,
                stderr_accumulator,
                task_log_prefix,
                cancellation_message=str(e_cancelling),
                exit_code_for_cancelled_job=-104,
            )
            await (
                db.commit()
            )  # Commit the CANCELLED state from _handle_job_cancellation_finalization.
            return final_response

        except JobAlreadyTerminalError as e_terminal:
            logger.info(
                f"{task_log_prefix} Task setup aborted: {e_terminal}. Job already in a final state."
            )
            # No DB changes from this worker are needed, job is already finalized.
            # We can re-fetch for the most current state to return.
            job = await crud_job_operations.get(db, id=job_db_id)
            if job:
                return {
                    "job_id": job_db_id_str,
                    "status": job.status.value,
                    "message": f"Task not run: {e_terminal!s}",
                    "exit_code": job.exit_code if job.exit_code is not None else -700,
                }
            else:  # Should be caught by JobNotFoundErrorForSetup if that's the case
                return {
                    "job_id": job_db_id_str,
                    "status": JobStatus.FAILED.value,
                    "message": "Job disappeared unexpectedly during terminal state check.",
                    "exit_code": -701,
                }

        except (TaskSetupError, JobNotFoundErrorForSetup) as e_task_setup:
            err_msg = f"Critical task setup failure for job {job_db_id_str}: {e_task_setup}"
            logger.error(f"{task_log_prefix} {err_msg}", exc_info=settings.LOG_TRACEBACKS)
            # _handle_task_failure_in_db uses the 'db' session and commits.
            await _handle_task_failure_in_db(
                db,
                redis_client,
                crud_job_operations,
                job_db_id,
                e_task_setup,
                task_log_prefix,
                exit_code_override=-505,
            )
            return {
                "job_id": job_db_id_str,
                "status": JobStatus.FAILED.value,
                "error": str(e_task_setup)[: settings.JOB_RESULT_MESSAGE_MAX_LEN],
                "error_type": type(e_task_setup).__name__,
                "exit_code": -505,
            }

        except SQLAlchemyError as db_e_main_logic:
            err_msg = (
                f"Database error in main task logic for job {job_db_id_str}: {db_e_main_logic}"
            )
            logger.error(f"{task_log_prefix} {err_msg}", exc_info=settings.LOG_TRACEBACKS)
            await _handle_task_failure_in_db(
                db,
                redis_client,
                crud_job_operations,
                job_db_id,
                db_e_main_logic,
                task_log_prefix,
                exit_code_override=-504,
            )
            return {
                "job_id": job_db_id_str,
                "status": JobStatus.FAILED.value,
                "error": err_msg[: settings.JOB_RESULT_MESSAGE_MAX_LEN],
                "error_type": "MainLogicSQLAlchemyError",
                "exit_code": -504,
            }
        # Other unhandled exceptions will cause the `async with db:` to rollback
        # and then propagate to _execute_subtitle_downloader_async_logic's general handlers.


async def _handle_missing_script(
    db: AsyncSession,
    redis_client: aioredis.Redis | None,
    job_db_id: UUID,
    task_log_prefix: str,
    script_path: Path,
) -> dict:
    """Handle the case when the script is not found. Commits FAILED state."""
    job_db_id_str = str(job_db_id)
    err_msg = f"Configuration error: Subtitle downloader script not found at {script_path}"
    logger.error(f"{task_log_prefix} {err_msg}")

    await _handle_task_failure_in_db(
        db,
        redis_client,
        crud_job_operations,
        job_db_id,
        err_msg,
        task_log_prefix,
        exit_code_override=-201,
    )
    # _handle_task_failure_in_db now commits.
    return {
        "job_id": job_db_id_str,
        "status": JobStatus.FAILED.value,
        "error": err_msg[: settings.JOB_RESULT_MESSAGE_MAX_LEN],
        "error_type": "ScriptNotFoundError",
        "exit_code": -201,
    }


async def _handle_runtime_error(
    e: RuntimeError, job_db_id_str: str, redis_client: aioredis.Redis | None, task_log_prefix: str
) -> dict:
    """Handle RuntimeError exceptions. Does not handle DB updates here."""
    err_msg = f"Critical error during async task execution: {type(e).__name__}: {e!s}"
    logger.error(f"{task_log_prefix} {err_msg}", exc_info=settings.LOG_TRACEBACKS)

    response = {
        "job_id": job_db_id_str,
        "status": JobStatus.FAILED.value,
        "error": f"Task execution failed (RuntimeError): {str(e)[:settings.JOB_RESULT_MESSAGE_MAX_LEN]}",
        "error_type": "AsyncTaskRuntimeError",
        "exit_code": -501,  # Default exit code for this handler
    }
    # Specific check for TaskSetupError as its message implies it handles its own Redis pub
    if not isinstance(e, TaskSetupError) and redis_client:
        await _publish_to_redis_pubsub_async(
            redis_client,
            job_db_id_str,
            "status",
            {
                "status": JobStatus.FAILED.value,
                "error_message": response["error"],
                "exit_code": response["exit_code"],
            },
            task_log_prefix,
        )
    return response


async def _handle_database_error(
    db_e: SQLAlchemyError,
    job_db_id_str: str,
    redis_client: aioredis.Redis | None,
    task_log_prefix: str,
) -> dict:
    """Handle SQLAlchemy database errors. Does not handle DB updates here."""
    err_msg = f"Database operation failed in async task logic: {type(db_e).__name__}: {db_e!s}"
    logger.error(f"{task_log_prefix} {err_msg}", exc_info=settings.LOG_TRACEBACKS)

    response = {
        "job_id": job_db_id_str,
        "status": JobStatus.FAILED.value,
        "error": f"Database error: {str(db_e)[:settings.JOB_RESULT_MESSAGE_MAX_LEN]}",
        "error_type": "AsyncTaskSQLAlchemyError",
        "exit_code": -503,
    }

    if redis_client:
        await _publish_to_redis_pubsub_async(
            redis_client,
            job_db_id_str,
            "status",
            {
                "status": JobStatus.FAILED.value,
                "error_message": response["error"],
                "exit_code": response["exit_code"],
            },
            task_log_prefix,
        )
    return response


async def _handle_unexpected_error(
    e: Exception,
    job_db_id: UUID,
    redis_client: aioredis.Redis | None,
    task_log_prefix: str,
) -> dict:
    """Handle unexpected exceptions and attempts emergency DB update."""
    job_db_id_str = str(job_db_id)
    err_msg = f"Unhandled exception in async task logic: {type(e).__name__}: {e!s}"
    logger.error(f"{task_log_prefix} {err_msg}", exc_info=settings.LOG_TRACEBACKS)

    response = {
        "job_id": job_db_id_str,
        "status": JobStatus.FAILED.value,
        "error": f"Task execution failed unexpectedly: {str(e)[:settings.JOB_RESULT_MESSAGE_MAX_LEN]}",
        "error_type": "AsyncTaskUnhandledException",
        "exit_code": -502,
    }

    if redis_client:
        await _publish_to_redis_pubsub_async(
            redis_client,
            job_db_id_str,
            "status",
            {
                "status": JobStatus.FAILED.value,
                "error_message": response["error"],
                "exit_code": response["exit_code"],
            },
            task_log_prefix,
        )

    try:
        async with get_worker_db_session() as db_emergency:
            await _handle_task_failure_in_db(
                db_emergency,
                redis_client,  # Pass client for potential pubsub within handler
                crud_job_operations,
                job_db_id,
                e,
                task_log_prefix,
                exit_code_override=response["exit_code"],  # Use the code set for this handler
            )
            # _handle_task_failure_in_db now commits.
    except Exception as db_failure_on_unhandled:
        logger.error(
            f"{task_log_prefix} Emergency DB update FAILED after unhandled exception: {db_failure_on_unhandled}",
            exc_info=settings.LOG_TRACEBACKS,
        )
    return response


async def _cleanup_resources(
    redis_client: aioredis.Redis | None,
    task_log_prefix: str,
    final_status: Any,  # final_status is for logging
) -> None:
    """Close Redis connections and log task completion."""
    if redis_client:
        try:
            await redis_client.close()
            logger.debug(f"{task_log_prefix} Redis client for Pub/Sub closed.")
        except Exception as e_redis_close:
            logger.error(f"{task_log_prefix} Error closing Redis client: {e_redis_close}")

    logger.info(f"{task_log_prefix} ASYNC LOGIC EXITING. Final determined status: {final_status}")


async def _setup_job_as_running(
    redis_client: aioredis.Redis | None,
    crud_ops: CRUDJob,
    job_db_id: UUID,
    celery_task_id: str,
    task_log_prefix: str,
):
    """
    Sets the job status to RUNNING in the DB.
    It creates and manages its own dedicated, short-lived database session
    to ensure it reads the most current job status before making changes.
    Includes full error handling.
    """
    # This `async with` block creates a new, fresh session for this operation only.
    async with get_worker_db_session() as db:
        try:
            # Fetch the job using the fresh session.
            job = await crud_ops.get(db, id=job_db_id)

            # --- Validation logic using the fresh data ---
            if not job:
                raise JobNotFoundErrorForSetup(f"Job {job_db_id} not found.")

            if job.status == JobStatus.CANCELLING:
                # This check is now guaranteed to be against the latest DB state.
                raise JobAlreadyCancellingError(f"Job {job_db_id} is already CANCELLING.")

            terminal_states = [JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED]
            if job.status in terminal_states:
                raise JobAlreadyTerminalError(
                    f"Job {job_db_id} is already in terminal state {job.status.value}."
                )

            # --- Update and Commit logic within the same fresh session ---
            current_time_utc = datetime.now(UTC)
            await crud_ops.update_job_start_details(
                db=db, job_id=job_db_id, started_at=current_time_utc, celery_task_id=celery_task_id
            )
            await (
                db.commit()
            )  # Commit the RUNNING state. The session is closed upon exiting the 'with' block.

            logger.info(f"{task_log_prefix} Job status updated to RUNNING in DB and committed.")

            # Publish the status update to Redis after the DB is successfully updated.
            if redis_client:
                await _publish_to_redis_pubsub_async(
                    redis_client,
                    str(job_db_id),
                    "status",
                    {"status": JobStatus.RUNNING.value, "ts": current_time_utc},
                    task_log_prefix,
                )

        except (JobAlreadyCancellingError, JobAlreadyTerminalError, JobNotFoundErrorForSetup) as e:
            # These are expected validation failures. Re-raise them so the calling function
            # can handle them (e.g., finalize as CANCELLED).
            logger.warning(f"{task_log_prefix} Setup validation failed: {e}")
            raise
        except SQLAlchemyError as db_exc:
            # Handle unexpected database errors during the operation.
            await db.rollback()
            err_msg = f"DB error setting job {job_db_id} to RUNNING: {db_exc}"
            logger.error(f"{task_log_prefix} {err_msg}", exc_info=True)
            # Wrap in our custom exception to be handled by the main orchestrator.
            raise TaskSetupError(err_msg) from db_exc
        except Exception as e:
            # Catch any other unexpected errors.
            await db.rollback()
            err_msg = f"Unexpected error setting job {job_db_id} to RUNNING: {e}"
            logger.error(f"{task_log_prefix} {err_msg}", exc_info=True)
            raise TaskSetupError(err_msg) from e


async def _execute_subtitle_script(
    script_path: str,
    folder_path: str,
    language: str | None,
    job_timeout_sec: float,
    task_log_prefix: str,
    redis_client: aioredis.Redis | None,
    job_db_id_str: str,
    stdout_accumulator: list[bytes],
    stderr_accumulator: list[bytes],
) -> int:
    """
    Manages the execution of the external subtitle script and captures its output.
    This function has been simplified to focus only on subprocess management.
    It no longer contains any database logic.
    """
    cmd_args = [str(settings.PYTHON_EXECUTABLE_PATH), script_path, "--folder-path", folder_path]
    if language:
        cmd_args.extend(["--language", language])

    final_script_exit_code = -255
    process: asyncio.subprocess.Process | None = None
    monitoring_tasks: list[asyncio.Task[Any] | None] = [None, None, None]
    all_tasks_gather_future: asyncio.Future[list[Any]] | None = None

    try:
        process = await _setup_subprocess(
            cmd_args, task_log_prefix, redis_client, job_db_id_str, stderr_accumulator
        )

        (
            monitoring_tasks,
            all_tasks_gather_future,
        ) = await _create_monitoring_tasks_and_gather_future(
            process,
            redis_client,
            job_db_id_str,
            task_log_prefix,
            stdout_accumulator,
            stderr_accumulator,
        )

        logger.debug(
            f"{task_log_prefix} Gathering subprocess tasks with timeout {job_timeout_sec}s."
        )
        gathered_results = await asyncio.wait_for(all_tasks_gather_future, timeout=job_timeout_sec)
        final_script_exit_code = _process_gather_results(gathered_results, process, task_log_prefix)

    except RuntimeError as e_setup_or_mgmt:
        final_script_exit_code = getattr(e_setup_or_mgmt, "exit_code", -252)
        stderr_accumulator.append(
            f"\n[TASK_INTERNAL_ERROR] Script setup/management error: {e_setup_or_mgmt}\n".encode()
        )
        raise

    except asyncio.CancelledError:
        logger.warning(
            f"{task_log_prefix} Script execution gather cancelled (PID: {getattr(process, 'pid', 'N/A')})."
        )
        await _handle_cancelled_gather_future(
            all_tasks_gather_future, str(getattr(process, "pid", "N/A")), task_log_prefix
        )

        if process and process.returncode is None:
            final_script_exit_code = await _terminate_process_gracefully(process, task_log_prefix)
        elif process and process.returncode is not None:
            final_script_exit_code = process.returncode
        else:
            final_script_exit_code = -253

        stderr_accumulator.append(
            f"\n[TASK_INTERNAL_ERROR] Script task cancelled. Final exit code after cleanup: {final_script_exit_code}.\n".encode()
        )
        raise

    except TimeoutError:
        final_script_exit_code = await _handle_script_timeout(
            process, all_tasks_gather_future, job_timeout_sec, stderr_accumulator, task_log_prefix
        )
        raise

    except Exception as e_unhandled_gather:
        final_script_exit_code = await _handle_script_management_error(
            e_unhandled_gather,
            process,
            all_tasks_gather_future,
            stderr_accumulator,
            task_log_prefix,
        )
        raise

    finally:
        # This crucial cleanup ensures all subprocess-related resources are properly handled.
        final_script_exit_code = await _final_process_cleanup_kill(
            process,
            all_tasks_gather_future,
            monitoring_tasks,
            final_script_exit_code,
            task_log_prefix,
        )

    return final_script_exit_code


async def _setup_subprocess(
    cmd_args: list[str],
    task_log_prefix: str,
    redis_client: aioredis.Redis | None,
    job_db_id_str: str,
    stderr_accumulator: list[bytes],  # To log internal errors if subprocess setup fails
) -> asyncio.subprocess.Process:
    """Creates and starts the subprocess. Raises RuntimeError with 'exit_code' attribute on failure."""
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        logger.info(
            f"{task_log_prefix} Process (PID: {process.pid}) started with command: {' '.join(cmd_args)}"
        )
    except Exception as e_create_proc:
        err_msg_create = f"Failed to create subprocess: {e_create_proc}"
        logger.error(f"{task_log_prefix} {err_msg_create}", exc_info=settings.LOG_TRACEBACKS)
        stderr_accumulator.append(f"[TASK_INTERNAL_ERROR] {err_msg_create}\n".encode())
        # This custom error will be caught by _execute_subtitle_script
        setup_error = RuntimeError(err_msg_create)
        setup_error.exit_code = -250  # Specific code for creation failure
        raise setup_error from e_create_proc

    if redis_client:
        await _publish_to_redis_pubsub_async(
            redis_client,
            job_db_id_str,
            "info",
            {"message": f"Subtitle downloader process (PID: {process.pid}) started execution."},
            task_log_prefix,
        )

    if not process.stdout or not process.stderr:
        err_msg_streams = "Process stdout/stderr streams unavailable after creation."
        logger.error(f"{task_log_prefix} {err_msg_streams}")
        stderr_accumulator.append(f"[TASK_INTERNAL_ERROR] {err_msg_streams}\n".encode())
        if process.returncode is None:  # Try to kill if it somehow started without streams
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass  # Ignore errors during this emergency kill

        setup_error = RuntimeError(err_msg_streams)
        setup_error.exit_code = -254
        raise setup_error
    return process


async def _wait_for_process_exit_and_log(
    process: asyncio.subprocess.Process, task_log_prefix: str
) -> int:
    """Waits for process to exit and logs its raw exit code. Can raise asyncio.CancelledError."""
    exit_code = await process.wait()
    logger.info(
        f"{task_log_prefix} Script process (PID: {process.pid}) exited. Raw Exit code: {exit_code}."
    )
    return exit_code


async def _create_monitoring_tasks_and_gather_future(
    process: asyncio.subprocess.Process,
    redis_client: aioredis.Redis | None,
    job_db_id_str: str,
    task_log_prefix: str,
    stdout_accumulator: list[bytes],
    stderr_accumulator: list[bytes],
) -> tuple[list[asyncio.Task[Any]], asyncio.Future[list[Any]]]:
    """Creates stdout/stderr reading tasks, process wait task, and their gather future."""
    assert process.stdout is not None  # Should be guaranteed by _setup_subprocess
    assert process.stderr is not None

    stdout_reader_task = asyncio.create_task(
        _read_stream_and_publish(
            process.stdout,
            "stdout",
            redis_client,
            job_db_id_str,
            task_log_prefix,
            stdout_accumulator,
        ),
        name=f"stdout_reader_{job_db_id_str}",
    )
    stderr_reader_task = asyncio.create_task(
        _read_stream_and_publish(
            process.stderr,
            "stderr",
            redis_client,
            job_db_id_str,
            task_log_prefix,
            stderr_accumulator,
        ),
        name=f"stderr_reader_{job_db_id_str}",
    )
    process_wait_task = asyncio.create_task(
        _wait_for_process_exit_and_log(process, task_log_prefix),
        name=f"process_wait_{job_db_id_str}",
    )

    tasks_list: list[asyncio.Task[Any]] = [
        stdout_reader_task,
        stderr_reader_task,
        process_wait_task,
    ]
    # return_exceptions=False: if any task fails (not CancelledError), gather raises that exception.
    # If a task is cancelled, gather raises CancelledError once children are also cancelled/completed.
    gather_future = asyncio.gather(*tasks_list, return_exceptions=False)
    return tasks_list, gather_future


def _process_gather_results(
    results: list[Any],  # Expected [None, None, exit_code] or propagated exception
    process: asyncio.subprocess.Process,
    task_log_prefix: str,
) -> int:
    """Processes results from asyncio.gather. Assumes gather did not raise an exception."""
    # results[2] should be the exit code from _wait_for_process_exit_and_log.
    process_wait_result = results[2]
    if isinstance(process_wait_result, int):
        exit_code_to_return = process_wait_result
    else:
        # This path implies process_wait_task might have returned something unexpected,
        # or gather(return_exceptions=True) was used and an exception object is here.
        # With return_exceptions=False, gather should have raised. This is a fallback.
        logger.error(
            f"{task_log_prefix} Unexpected result type from process_wait_task in gather: {process_wait_result}. "
            f"Using process.returncode ({process.returncode}) if available."
        )
        exit_code_to_return = process.returncode if process.returncode is not None else -97
    logger.info(
        f"{task_log_prefix} All stream/process tasks completed. Final exit code from gather: {exit_code_to_return}."
    )
    return exit_code_to_return


async def _handle_job_cancellation_finalization(
    redis_client: aioredis.Redis | None,
    crud_ops: CRUDJob,
    job_db_id: UUID,
    message: str,
    task_log_prefix: str,
    exit_code_override: int = -100,
) -> dict:
    """
    Emergency finalizer for the CANCELLED state.
    It now uses its own dedicated, short-lived database session.
    """
    logger.warning(
        f"{task_log_prefix} Job {job_db_id} is being finalized as CANCELLED. Reason: {message}"
    )

    # Create a fresh session for this atomic update.
    async with get_worker_db_session() as db:
        await crud_ops.update_job_completion_details(
            db,
            job_id=job_db_id,
            status=JobStatus.CANCELLED,
            exit_code=exit_code_override,
            result_message=_trim(message, settings.JOB_RESULT_MESSAGE_MAX_LEN),
            completed_at=datetime.now(UTC),
        )
        await db.commit()

    logger.info(f"{task_log_prefix} Job {job_db_id} successfully marked as CANCELLED in DB.")

    if redis_client:
        await _publish_to_redis_pubsub_async(
            redis_client,
            str(job_db_id),
            "status",
            {"status": JobStatus.CANCELLED.value},
            task_log_prefix,
        )

    return {
        "job_id": str(job_db_id),
        "status": JobStatus.CANCELLED.value,
        "message": message,
        "exit_code": exit_code_override,
    }


async def _handle_cancelled_gather_future(
    gather_future: asyncio.Future[list[Any]] | None,
    process_pid_str: str,  # For logging
    task_log_prefix: str,
):
    """Awaits a cancelled gather future to prevent 'Unretrieved _GatheringFuture exception'."""
    if gather_future and gather_future.cancelled() and not gather_future.done():
        logger.debug(
            f"{task_log_prefix} Attempting to await cancelled gather future for PID {process_pid_str}."
        )
        try:
            await gather_future
        except asyncio.CancelledError:
            logger.debug(
                f"{task_log_prefix} Gather future for PID {process_pid_str} was cancelled as expected."
            )
        except Exception as e_gather_await:  # Should not happen if it was only CancelledError
            logger.error(
                f"{task_log_prefix} Unexpected error awaiting cancelled gather for PID {process_pid_str}: {e_gather_await}",
                exc_info=settings.LOG_TRACEBACKS,
            )


async def _force_kill_process(
    process: asyncio.subprocess.Process,
    task_log_prefix: str,
    base_exit_code_on_failure: int = -9,  # Default for kill failure
) -> int:
    """Force kills a process (SIGKILL) and returns its exit code or a fallback."""
    pid = process.pid
    if process.returncode is None:  # Still running
        logger.warning(f"{task_log_prefix} Sending SIGKILL to process {pid}.")
        try:
            process.kill()
            killed_exit_code = await process.wait()
            logger.info(
                f"{task_log_prefix} Process {pid} killed by SIGKILL. Exit code: {killed_exit_code}"
            )
            return killed_exit_code
        except ProcessLookupError:  # Process died just before kill
            logger.warning(
                f"{task_log_prefix} Process {pid} disappeared before SIGKILL took effect."
            )
            return process.returncode if process.returncode is not None else -94  # Already exited
        except Exception as e_kill:
            logger.error(
                f"{task_log_prefix} Error during SIGKILL for PID {pid}: {e_kill}",
                exc_info=settings.LOG_TRACEBACKS,
            )
            return base_exit_code_on_failure
    else:  # Already exited
        logger.info(
            f"{task_log_prefix} Process {pid} already exited with {process.returncode} before SIGKILL attempt."
        )
        return process.returncode


async def _terminate_process_gracefully(
    process: asyncio.subprocess.Process,
    task_log_prefix: str,
) -> int:
    """Attempts SIGTERM, then SIGKILL. Returns determined exit code."""
    pid = process.pid
    final_exit_code = -99  # Default if termination leads to this path (e.g. timeout)

    if process.returncode is not None:
        logger.info(
            f"{task_log_prefix} Process (PID: {pid}) already exited with {process.returncode} before graceful termination attempt."
        )
        return process.returncode

    logger.info(f"{task_log_prefix} Process (PID: {pid}) running. Attempting SIGTERM.")
    try:
        process.terminate()  # SIGTERM
        # Wait for process to exit after SIGTERM, with a grace period
        final_exit_code = await asyncio.wait_for(
            process.wait(), timeout=settings.PROCESS_TERMINATE_GRACE_PERIOD_S
        )
        logger.info(
            f"{task_log_prefix} Process {pid} terminated after SIGTERM. Exit code: {final_exit_code}"
        )
    except TimeoutError:  # SIGTERM grace period expired
        logger.warning(
            f"{task_log_prefix} Process {pid} did not terminate after SIGTERM grace period. Forcing SIGKILL."
        )
        final_exit_code = await _force_kill_process(
            process, task_log_prefix, final_exit_code
        )  # Pass current code as fallback
    except ProcessLookupError:  # Process disappeared during SIGTERM handling
        logger.warning(
            f"{task_log_prefix} Process {pid} disappeared during SIGTERM handling (ProcessLookupError)."
        )
        final_exit_code = (
            process.returncode if process.returncode is not None else -96
        )  # Assume it exited somehow
    except Exception as term_exc:  # Other errors during SIGTERM
        logger.error(
            f"{task_log_prefix} Error during SIGTERM for PID {pid}: {term_exc}. Forcing SIGKILL.",
            exc_info=settings.LOG_TRACEBACKS,
        )
        final_exit_code = await _force_kill_process(
            process, task_log_prefix, -95
        )  # Fallback to specific error code
    return final_exit_code


async def _ensure_tasks_cancelled_and_awaited(
    tasks_to_clean: list[asyncio.Task[Any] | None], task_log_prefix: str
):  # Renamed `tasks` to `tasks_to_clean`
    """Cancels and awaits a list of asyncio tasks, logging results/exceptions."""
    active_tasks = [t for t in tasks_to_clean if t is not None and not t.done()]
    if active_tasks:
        logger.debug(
            f"{task_log_prefix} Cancelling {len(active_tasks)} pending subprocess-related tasks."
        )
        for task in active_tasks:
            task.cancel()

    all_tasks = [t for t in tasks_to_clean if t is not None]
    if all_tasks:
        logger.debug(
            f"{task_log_prefix} Gathering all {len(all_tasks)} subprocess-related tasks to finalize."
        )
        results = await asyncio.gather(*all_tasks, return_exceptions=True)
        for i, res in enumerate(results):
            task_name = (
                all_tasks[i].get_name() if hasattr(all_tasks[i], "get_name") else f"Task-{i}"
            )
            if isinstance(res, asyncio.CancelledError):
                logger.debug(f"{task_log_prefix} Task '{task_name}' was cancelled as expected.")
            elif isinstance(res, Exception):
                logger.error(
                    f"{task_log_prefix} Task '{task_name}' raised an exception during gather: {type(res).__name__}: {res}",
                    exc_info=False,
                )  # exc_info=False as res is the exc
            # else: normal completion, no specific log needed for None results from stream readers
        logger.debug(f"{task_log_prefix} All subprocess-related tasks finalized.")
    else:
        logger.debug(f"{task_log_prefix} No subprocess-related tasks to clean up or gather.")


async def _handle_script_timeout(
    process: asyncio.subprocess.Process
    | None,  # process can be None if timeout happens before setup
    all_tasks_gather_future: asyncio.Future[list[Any]] | None,
    job_timeout_sec: float,
    stderr_accumulator: list[bytes],
    task_log_prefix: str,
) -> int:
    """Handles script timeout: cancels gather future, terminates process, logs."""
    logger.warning(f"{task_log_prefix} Script execution gather timed out after {job_timeout_sec}s.")
    exit_code_after_timeout = -99  # Specific code for timeout outcome

    pid_str = str(getattr(process, "pid", "N/A"))
    if all_tasks_gather_future and not all_tasks_gather_future.done():
        all_tasks_gather_future.cancel()
        await _handle_cancelled_gather_future(all_tasks_gather_future, pid_str, task_log_prefix)

    if process and process.returncode is None:  # Process was started and is still running
        exit_code_after_timeout = await _terminate_process_gracefully(process, task_log_prefix)
    elif process and process.returncode is not None:  # Process exited before termination logic
        logger.info(
            f"{task_log_prefix} Process (PID: {pid_str}) already exited with {process.returncode} when timeout handled."
        )
        exit_code_after_timeout = process.returncode
    # If process is None, exit_code_after_timeout remains -99

    timeout_msg = f"\n[TASK_INTERNAL_ERROR] Script execution timed out after {job_timeout_sec}s. Final exit code: {exit_code_after_timeout}.\n"
    stderr_accumulator.append(timeout_msg.encode())
    return exit_code_after_timeout


async def _handle_script_management_error(
    e_manage: Exception,
    process: asyncio.subprocess.Process | None,
    all_tasks_gather_future: asyncio.Future[list[Any]] | None,
    stderr_accumulator: list[bytes],
    task_log_prefix: str,
) -> int:
    """Handles errors during script management: cancels gather, kills process, logs."""
    logger.error(
        f"{task_log_prefix} Exception during script subprocess management: {type(e_manage).__name__}: {e_manage}",
        exc_info=settings.LOG_TRACEBACKS,
    )
    exit_code_after_error = -98  # Specific code for this failure type

    pid_str = str(getattr(process, "pid", "N/A"))
    if all_tasks_gather_future and not all_tasks_gather_future.done():
        all_tasks_gather_future.cancel()
        await _handle_cancelled_gather_future(all_tasks_gather_future, pid_str, task_log_prefix)

    error_msg_for_stderr = f"\n[TASK_INTERNAL_ERROR] Error managing script process: {type(e_manage).__name__}: {e_manage!s}\n".encode()
    stderr_accumulator.append(error_msg_for_stderr)

    if process and process.returncode is None:  # Process was started and is still running
        logger.warning(
            f"{task_log_prefix} Attempting to kill process (PID: {pid_str}) due to management error."
        )
        exit_code_after_error = await _force_kill_process(
            process, task_log_prefix, exit_code_after_error
        )
    elif process and process.returncode is not None:
        exit_code_after_error = process.returncode
    return exit_code_after_error


async def _final_process_cleanup_kill(
    process: asyncio.subprocess.Process | None,
    all_tasks_gather_future: asyncio.Future[list[Any]] | None,
    monitoring_tasks: list[asyncio.Task[Any] | None],  # stdout/stderr/wait tasks
    current_exit_code: int,  # The exit code determined so far
    task_log_prefix: str,
) -> int:
    """Ensures all monitoring tasks are cancelled and awaited, and forcibly kills the subprocess if still running."""
    # Cancel and await monitoring tasks and their gather future first
    if all_tasks_gather_future and not all_tasks_gather_future.done():
        all_tasks_gather_future.cancel()
        # Await the gather future itself to handle its cancellation or exceptions
        await _handle_cancelled_gather_future(
            all_tasks_gather_future, str(getattr(process, "pid", "N/A")), task_log_prefix
        )

    # Ensure individual monitoring tasks are also cleaned up
    await _ensure_tasks_cancelled_and_awaited(monitoring_tasks, task_log_prefix)

    # Now, deal with the subprocess itself
    if process and process.returncode is None:  # If process exists and is still running
        logger.warning(
            f"{task_log_prefix} Process (PID: {process.pid}) found still running in final cleanup. Forcing SIGKILL."
        )
        # Use _force_kill_process, it handles logging and getting exit code from kill
        killed_exit_code = await _force_kill_process(process, task_log_prefix, current_exit_code)

        # If the process had to be force-killed here, this is usually a more severe state.
        # The exit code from the kill operation itself (-9 for SIGKILL on Linux) or the
        # process's actual exit code if it died due to SIGKILL might be more representative.
        # `_force_kill_process` returns this.
        return killed_exit_code
    elif process and process.returncode is not None:  # Process already exited
        return process.returncode  # Return its actual exit code
    else:  # No process or process already cleaned up
        return current_exit_code  # Return the exit code determined before this cleanup


async def _run_script_and_get_output(
    script_path: str,
    folder_path: str,
    language: str | None,
    job_timeout_sec: float,
    task_log_prefix: str,
    redis_client: aioredis.Redis | None,
    job_db_id_str: str,
    stdout_accumulator: list[bytes],
    stderr_accumulator: list[bytes],
) -> int:
    """
    Core subprocess execution logic. Manages subprocess creation, stream reading, timeout,
    and cancellation signals (asyncio.CancelledError).
    Returns the script's exit code.
    Raises TimeoutError, asyncio.CancelledError, or RuntimeError (with exit_code attribute for setup issues).
    """
    cmd_args = [str(settings.PYTHON_EXECUTABLE_PATH), script_path, "--folder-path", folder_path]
    if language:
        cmd_args.extend(["--language", language])

    final_script_exit_code = -255  # Default if errors occur before/during script run
    process: asyncio.subprocess.Process | None = None
    monitoring_tasks: list[asyncio.Task[Any] | None] = [
        None,
        None,
        None,
    ]  # stdout, stderr, process_wait
    all_tasks_gather_future: asyncio.Future[list[Any]] | None = None

    try:
        process = await _setup_subprocess(
            cmd_args, task_log_prefix, redis_client, job_db_id_str, stderr_accumulator
        )
        # _setup_subprocess raises RuntimeError with .exit_code if it fails, caught below

        (
            monitoring_tasks,
            all_tasks_gather_future,
        ) = await _create_monitoring_tasks_and_gather_future(
            process,
            redis_client,
            job_db_id_str,
            task_log_prefix,
            stdout_accumulator,
            stderr_accumulator,
        )

        logger.debug(
            f"{task_log_prefix} Gathering subprocess tasks with timeout {job_timeout_sec}s."
        )
        # Wait for all tasks (stdout/stderr readers, process.wait) to complete, or timeout
        gathered_results = await asyncio.wait_for(all_tasks_gather_future, timeout=job_timeout_sec)
        final_script_exit_code = _process_gather_results(gathered_results, process, task_log_prefix)

    except (
        RuntimeError
    ) as e_setup_or_mgmt:  # Covers _setup_subprocess errors or other RuntimeErrors here
        # Logged by _setup_subprocess or _handle_script_management_error.
        # Ensure exit_code_to_return reflects the specific error.
        final_script_exit_code = getattr(
            e_setup_or_mgmt, "exit_code", -252
        )  # Use custom code or default
        stderr_accumulator.append(
            f"\n[TASK_INTERNAL_ERROR] Script setup/management error: {e_setup_or_mgmt}\n".encode()
        )
        raise  # Re-raise for _execute_subtitle_script to handle with specific error type

    except asyncio.CancelledError:  # Raised by asyncio.wait_for or if gather_future is cancelled
        logger.warning(
            f"{task_log_prefix} Script execution gather cancelled (PID: {getattr(process, 'pid', 'N/A')})."
        )
        # Ensure gather_future itself is marked cancelled and awaited
        await _handle_cancelled_gather_future(
            all_tasks_gather_future, str(getattr(process, "pid", "N/A")), task_log_prefix
        )

        if process and process.returncode is None:  # If process was started and is running
            final_script_exit_code = await _terminate_process_gracefully(process, task_log_prefix)
        elif process and process.returncode is not None:
            final_script_exit_code = process.returncode
        else:  # Process not started or already gone
            final_script_exit_code = (
                -253
            )  # Specific code for cancellation impacting process lifecycle

        stderr_accumulator.append(
            f"\n[TASK_INTERNAL_ERROR] Script task cancelled. Final exit code after cleanup: {final_script_exit_code}.\n".encode()
        )
        raise  # Re-raise for _execute_subtitle_script to finalize as CANCELLED

    except TimeoutError:  # Raised by asyncio.wait_for
        # _handle_script_timeout handles logging, process termination, stderr append.
        final_script_exit_code = await _handle_script_timeout(
            process, all_tasks_gather_future, job_timeout_sec, stderr_accumulator, task_log_prefix
        )
        # Re-raise for _execute_subtitle_script to handle with specific error type
        # It will use final_script_exit_code (which is -99 from _handle_script_timeout)
        raise

    except Exception as e_unhandled_gather:  # Other unexpected errors during gather
        # _handle_script_management_error handles logging, process termination, stderr append.
        final_script_exit_code = await _handle_script_management_error(
            e_unhandled_gather,
            process,
            all_tasks_gather_future,
            stderr_accumulator,
            task_log_prefix,
        )
        # Re-raise for _execute_subtitle_script to handle with specific error type
        raise

    finally:
        # Crucial cleanup: ensures monitoring tasks are cancelled/awaited and subprocess is killed if still running.
        # This is vital if an unhandled exception occurred before normal completion or specific error handling.
        final_script_exit_code = await _final_process_cleanup_kill(
            process,
            all_tasks_gather_future,
            monitoring_tasks,
            final_script_exit_code,
            task_log_prefix,
        )
    return final_script_exit_code


async def _finalize_job_after_script(
    redis_client: aioredis.Redis | None,
    crud_ops: CRUDJob,
    job_db_id: UUID,
    exit_code: int,
    stdout_bytes: bytes,
    stderr_bytes: bytes,
    task_log_prefix: str,
) -> dict:
    """
    Finalizes the job's status after the script has run.
    This function is the definitive fix for the race condition. It creates a
    NEW, FRESH database session to guarantee it reads the most up-to-date
    job status before committing a final result.
    """
    # First, parse the script output to determine its outcome.
    stdout_str = stdout_bytes.decode("utf-8", errors="replace")
    stderr_str = stderr_bytes.decode("utf-8", errors="replace")

    script_status = JobStatus.SUCCEEDED if exit_code == 0 else JobStatus.FAILED
    result_message = _build_result_message(stdout_str, stderr_str, script_status, exit_code)
    log_snippet = _build_log_snippet(
        stdout_str, stderr_str, script_status, exit_code, task_log_prefix
    )

    # Create a new, fresh session to get the absolute latest state from the DB.
    async with get_worker_db_session() as db:
        # This `get` is guaranteed to be against the most recent DB data.
        job_to_finalize = await crud_ops.get(db, id=job_db_id)
        if not job_to_finalize:
            # This would be a critical error, but we handle it defensively.
            raise RuntimeError(
                f"Job {job_db_id} disappeared from the database before finalization."
            )

        final_status_to_set = script_status
        final_exit_code = exit_code
        final_message = result_message

        # THE CORE FAILSAFE LOGIC:
        # Check if the API set the job to CANCELLING while the script was running.
        if job_to_finalize.status == JobStatus.CANCELLING and script_status == JobStatus.SUCCEEDED:
            logger.warning(
                f"{task_log_prefix} RACE CONDITION DETECTED! Job was in CANCELLING state, but script SUCCEEDED. "
                f"Honoring the cancellation request."
            )
            # Override the script's success with a CANCELLED state.
            final_status_to_set = JobStatus.CANCELLED
            final_exit_code = -102  # Use a specific code for this race condition scenario.
            final_message = "Job cancelled by user during execution."

        # Now, update the database with the definitively correct final state.
        await crud_ops.update_job_completion_details(
            db=db,
            job_id=job_db_id,
            status=final_status_to_set,
            exit_code=final_exit_code,
            result_message=final_message,
            log_snippet=log_snippet,
            completed_at=datetime.now(UTC),
        )
        await db.commit()
        logger.info(
            f"{task_log_prefix} Job final status '{final_status_to_set.value}' committed to DB."
        )

    # Publish the final, correct status to Redis after the DB is committed.
    if redis_client:
        await _publish_to_redis_pubsub_async(
            redis_client,
            str(job_db_id),
            "status",
            {"status": final_status_to_set.value, "exit_code": final_exit_code},
            task_log_prefix,
        )

    # Return the final, correct result.
    return {
        "job_id": str(job_db_id),
        "status": final_status_to_set.value,
        "message": final_message,
        "exit_code": final_exit_code,
    }


async def _handle_job_cancellation_finalization(
    redis_client: aioredis.Redis | None,
    crud_ops: CRUDJob,
    job_db_id: UUID,
    message: str,
    task_log_prefix: str,
    exit_code_override: int = -100,
) -> dict:
    """Emergency finalizer for CANCELLED state. Uses its own session."""
    async with get_worker_db_session() as db:
        await crud_ops.update_job_completion_details(
            db,
            job_id=job_db_id,
            status=JobStatus.CANCELLED,
            exit_code=exit_code_override,
            result_message=message,
            completed_at=datetime.now(UTC),
        )
        await db.commit()
    logger.warning(f"{task_log_prefix} Job {job_db_id} finalized as CANCELLED.")
    if redis_client:
        await _publish_to_redis_pubsub_async(
            redis_client,
            str(job_db_id),
            "status",
            {"status": JobStatus.CANCELLED.value},
            task_log_prefix,
        )
    return {
        "job_id": str(job_db_id),
        "status": JobStatus.CANCELLED.value,
        "message": message,
        "exit_code": exit_code_override,
    }


def _parse_script_output(
    exit_code: int, stdout_bytes: bytes, stderr_bytes: bytes, task_log_prefix: str
) -> tuple[JobStatus, str, str]:
    """Parses script output to determine status, message, and log snippet."""
    stdout_str = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()
    _log_raw_output(stdout_str, stderr_str, task_log_prefix)

    final_status = JobStatus.SUCCEEDED if exit_code == 0 else JobStatus.FAILED
    log_snippet = _build_log_snippet(
        stdout_str, stderr_str, final_status, exit_code, task_log_prefix
    )
    result_message = _build_result_message(stdout_str, stderr_str, final_status, exit_code)

    return final_status, result_message, log_snippet  # Trimming happens in caller if needed


def _log_raw_output(stdout: str, stderr: str, prefix: str) -> None:
    """Logs snippets of raw stdout and stderr for debugging."""
    # Ensure LOG_SNIPPET_PREVIEW_LEN is defined in settings
    preview_len = getattr(settings, "LOG_SNIPPET_PREVIEW_LEN", 200)
    if stdout:
        logger.debug(f"{prefix} STDOUT (first {preview_len} chars):\n{stdout[:preview_len]}")
    if stderr:
        logger.debug(f"{prefix} STDERR (first {preview_len} chars):\n{stderr[:preview_len]}")


def _build_log_snippet(
    stdout: str, stderr: str, status: JobStatus, code: int, task_log_prefix: str
) -> str:
    """Constructs a log snippet from stdout and stderr."""
    parts = []
    if stdout:
        parts.append(f"STDOUT:\n{stdout}")
    if stderr:
        parts.append(f"STDERR:\n{stderr}")
        # Log warning for failures with stderr, unless it's a known non-error code
        # (e.g. timeout, handled cancellation) as those are logged more specifically.
        known_non_error_codes = [-99, -100, -101, -102, -103, -104, -253]
        if status == JobStatus.FAILED and code not in known_non_error_codes:
            logger.warning(
                f"{task_log_prefix} Task failed (Code: {code}) with STDERR content. "
                f"STDERR (first 500 chars): {stderr[:500]}"
            )
    if not parts:  # No output from script
        msg = "Script completed" if status == JobStatus.SUCCEEDED else "Script processing finished"
        parts.append(f"[INFO] {msg} (code {code}) with no textual output.")

    # Trim final snippet in the functions that use this (_finalize_job_in_db, _handle_job_cancellation_finalization, etc.)
    return _trim("\n\n".join(parts), settings.JOB_LOG_SNIPPET_MAX_LEN)


def _build_result_message(stdout: str, stderr: str, status: JobStatus, code: int) -> str:
    """Constructs a result message, prioritizing stderr for failures."""
    if status == JobStatus.SUCCEEDED:
        lines = [ln for ln in stdout.splitlines() if ln.strip()]
        return _trim(
            lines[-1] if lines else "Script completed successfully.",
            settings.JOB_RESULT_MESSAGE_MAX_LEN,
        )

    # For failures, try to get a meaningful message from stderr
    err_lines = [
        ln
        for ln in stderr.splitlines()
        if ln.strip() and not ln.startswith("[TASK_INTERNAL_ERROR]")
    ]
    if err_lines:
        # Try to find a concise error, e.g., last few lines
        snippet = " | ".join(err_lines[-3:])  # Last 3 lines from stderr
        return _trim(
            f"Script failed (code {code}). Error: {snippet}", settings.JOB_RESULT_MESSAGE_MAX_LEN
        )

    # If no stderr, try stdout for failure message
    out_lines = [ln for ln in stdout.splitlines() if ln.strip()]
    if out_lines:
        return _trim(
            f"Script failed (code {code}). Last output: {out_lines[-1]}",
            settings.JOB_RESULT_MESSAGE_MAX_LEN,
        )

    # Fallback messages for known failure codes
    if code == -99:
        return f"Script failed due to timeout (code {code})."
    if code == -254:
        return f"Script subprocess setup failed (code {code})."  # from _setup_subprocess
    if code == -250:
        return f"Script subprocess creation failed (code {code})."  # from _setup_subprocess
    if code in [-100, -101, -102, -103, -104, -253]:
        return f"Script processing was cancelled (code {code})."

    return _trim(
        f"Script failed (code {code}) with no discernible output.",
        settings.JOB_RESULT_MESSAGE_MAX_LEN,
    )


def _trim(text: str, max_len: int) -> str:
    """Trims text to max_len, adding '...' if truncated."""
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


async def _finalize_job_in_db(
    db: AsyncSession,
    crud_ops: CRUDJob,
    job_db_id: UUID,
    status: JobStatus,
    exit_code: int,
    result_message: str,
    log_snippet: str,
    task_log_prefix: str,
):
    """### FIX 1: ADDED A FAILSAFE TO PREVENT OVERWRITING A CANCELLATION ###"""
    """Stages job completion details in DB, with a failsafe against race conditions."""
    logger.debug(
        f"{task_log_prefix} Staging job completion: Status {status.value}, Code {exit_code}."
    )
    try:
        # Failsafe: Re-fetch the job within the same transaction to get the most current state.
        job_to_finalize = await crud_ops.get(db, id=job_db_id)
        if not job_to_finalize:
            raise RuntimeError(f"Job {job_db_id} disappeared before finalization.")

        # If the API has marked the job as CANCELLING, we MUST NOT overwrite it with SUCCEEDED.
        if job_to_finalize.status == JobStatus.CANCELLING and status == JobStatus.SUCCEEDED:
            logger.warning(
                f"{task_log_prefix} RACE CONDITION DETECTED! Job was CANCELLING but script SUCCEEDED. "
                f"Honoring CANCELLING state. Finalizing job as CANCELLED."
            )
            # Finalize as CANCELLED instead of what the script reported.
            await crud_ops.update_job_completion_details(
                db=db,
                job_id=job_db_id,
                status=JobStatus.CANCELLED,
                exit_code=exit_code
                if exit_code != 0
                else -102,  # Preserve script error code if any
                result_message="Job cancelled by user during execution.",
                log_snippet=log_snippet,
                completed_at=datetime.now(UTC),
            )
        else:
            # Normal finalization path
            await crud_ops.update_job_completion_details(
                db=db,
                job_id=job_db_id,
                status=status,
                exit_code=exit_code,
                result_message=result_message,
                log_snippet=log_snippet,
                completed_at=datetime.now(UTC),
            )
        logger.info(f"{task_log_prefix} Job final status attributes prepared for commit.")
    except Exception as e_finalize:
        logger.error(
            f"{task_log_prefix} FAILED to stage job completion details for commit: {e_finalize}",
            exc_info=settings.LOG_TRACEBACKS,
        )
        raise


async def _handle_task_failure_in_db(  # noqa: C901
    db: AsyncSession | None,
    redis_client: aioredis.Redis | None,
    crud_ops: CRUDJob,
    job_id: UUID,
    error_obj: Any,
    task_log_prefix: str,
    exit_code_override: int = -400,
    log_snippet_override: str | None = None,
) -> dict:
    """
    Emergency finalizer for the FAILED state.
    If 'db' is None, it creates and manages its own session for this operation.
    Otherwise, it uses the provided 'db' session (caller must commit/rollback).
    """
    if isinstance(error_obj, Exception):
        message = f"Task failed: {type(error_obj).__name__}: {error_obj!s}"
        error_type = type(error_obj).__name__
    else:
        message = f"Task failed: {error_obj!s}"
        error_type = "GenericTaskFailure"

    logger.error(
        f"{task_log_prefix} Job {job_id} is being finalized as FAILED. Reason: {message}",
        exc_info=isinstance(error_obj, Exception) and getattr(settings, "LOG_TRACEBACKS", False),
    )

    final_log_snippet = log_snippet_override
    if final_log_snippet is None and isinstance(error_obj, Exception):
        final_log_snippet = _trim(traceback.format_exc(), settings.JOB_LOG_SNIPPET_MAX_LEN)
    elif final_log_snippet is None:
        final_log_snippet = _trim(message, settings.JOB_LOG_SNIPPET_MAX_LEN)

    db_to_use: AsyncSession
    db_context_manager = None
    used_own_session = False

    if db is None:
        logger.debug(f"{task_log_prefix} _handle_task_failure_in_db creating its own DB session.")
        db_context_manager = get_worker_db_session()
        db_to_use = await db_context_manager.__aenter__()
        used_own_session = True
    else:
        logger.debug(f"{task_log_prefix} _handle_task_failure_in_db using provided DB session.")
        db_to_use = db

    try:
        await crud_ops.update_job_completion_details(
            db_to_use,
            job_id=job_id,
            status=JobStatus.FAILED,
            exit_code=exit_code_override,
            result_message=_trim(message, settings.JOB_RESULT_MESSAGE_MAX_LEN),
            log_snippet=final_log_snippet,
            completed_at=datetime.now(UTC),
        )
        if used_own_session:
            await db_to_use.commit()
            logger.info(
                f"{task_log_prefix} Job {job_id} successfully marked as FAILED in DB (own session committed)."
            )
        else:
            logger.info(
                f"{task_log_prefix} Job {job_id} FAILED status staged in DB (caller to commit)."
            )

    except Exception as e_final_fail:
        logger.critical(
            f"{task_log_prefix} CRITICAL: Failed to mark/stage job {job_id} as FAILED in DB: {e_final_fail}",
            exc_info=True,
        )
        if used_own_session:
            try:
                await db_to_use.rollback()
            except Exception as e_rb:
                logger.error(
                    f"{task_log_prefix} CRITICAL: Rollback failed during emergency FAILED update: {e_rb}"
                )
        return {
            "job_id": str(job_id),
            "status": "DB_UPDATE_FAILED",
            "message": f"CRITICAL: DB update failed while finalizing job as FAILED. Original error: {message}",
            "exit_code": exit_code_override,
            "error_type": "EmergencyFinalizationDBError",
        }
    finally:
        if used_own_session and db_context_manager:
            try:
                await db_context_manager.__aexit__(None, None, None)
                logger.debug(f"{task_log_prefix} _handle_task_failure_in_db own DB session closed.")
            except Exception as e_ctx_exit:
                logger.error(
                    f"{task_log_prefix} Error closing own DB session in _handle_task_failure_in_db: {e_ctx_exit}"
                )

    if redis_client:
        await _publish_to_redis_pubsub_async(
            redis_client,
            str(job_id),
            "status",
            {
                "status": JobStatus.FAILED.value,
                "exit_code": exit_code_override,
                "error_message": message,
            },
            task_log_prefix,
        )

    return {
        "job_id": str(job_id),
        "status": JobStatus.FAILED.value,
        "message": message,
        "exit_code": exit_code_override,
        "error_type": error_type,
    }


async def _handle_terminated_job_in_db(
    job_db_id: UUID,
    error_obj: Exception,
    task_log_prefix: str,
):
    """Specifically handles jobs that were terminated by a signal (e.g., SIGTERM)."""
    logger.warning(
        f"{task_log_prefix} Finalizing job {job_db_id} as CANCELLED due to termination signal."
    )
    try:
        async with get_worker_db_session() as db:
            cancellation_time_utc = datetime.now(UTC)
            await crud_job_operations.update_job_completion_details(
                db=db,
                job_id=job_db_id,
                status=JobStatus.CANCELLED,
                exit_code=-101,
                result_message=f"Job cancelled due to worker termination signal ({type(error_obj).__name__}).",
                log_snippet=f"Task received {type(error_obj).__name__} and was terminated.",
                completed_at=cancellation_time_utc,
            )
            await db.commit()
            logger.info(
                f"{task_log_prefix} Job {job_db_id} marked as CANCELLED in DB due to termination."
            )
    except Exception as e:
        logger.critical(
            f"{task_log_prefix} CRITICAL FAILURE: Could not mark terminated job {job_db_id} as CANCELLED in DB: {e}",
            exc_info=True,
        )


@celery_app.task(
    name=settings.CELERY_SUBTITLE_TASK_NAME,
    bind=True,
    track_started=True,
    acks_late=settings.CELERY_ACKS_LATE,
)
def execute_subtitle_downloader_task(  # noqa: C901
    self: CeleryTaskDef, job_db_id_str: str, folder_path: str, language: str | None
):
    celery_task_id = str(self.request.id) if self.request.id else "unknown-celery-id"
    task_name_for_log = self.name
    wrapper_log_prefix = (
        f"[CeleryTaskWrapper:{task_name_for_log} CeleryID:{celery_task_id} DBJobID:{job_db_id_str}]"
    )
    logger.info(
        f"{wrapper_log_prefix} SYNC WRAPPER ENTERED for job on folder '{folder_path}', lang '{language}'."
    )

    job_db_id: UUID
    try:
        job_db_id = UUID(job_db_id_str)
    except ValueError:
        err_msg = f"Invalid job_db_id_str: '{job_db_id_str}'. Cannot proceed."
        logger.error(f"{wrapper_log_prefix} {err_msg}", exc_info=True)
        raise ValueError(err_msg) from None

    final_result_from_async_logic: dict | None = None  # To store the result for the except block

    try:
        e_unhandled_wrapper = None
        logger.info(f"{wrapper_log_prefix} Invoking asyncio.run() for async logic.")
        final_result_from_async_logic = asyncio.run(
            _execute_subtitle_downloader_async_logic(
                task_name_for_log, celery_task_id, job_db_id, folder_path, language
            )
        )
        logger.info(
            f"{wrapper_log_prefix} Async logic completed. Raw result: {str(final_result_from_async_logic)[:500]}..."
        )

        if not isinstance(final_result_from_async_logic, dict):
            unexpected_type_msg = f"Async logic returned unexpected result type: {type(final_result_from_async_logic)}. Expected dict."
            logger.error(f"{wrapper_log_prefix} {unexpected_type_msg}")
            raise RuntimeError(unexpected_type_msg)

        status_from_async = final_result_from_async_logic.get("status")
        message_from_async = final_result_from_async_logic.get("message", "N/A")

        if status_from_async == JobStatus.SUCCEEDED.value:
            logger.info(f"{wrapper_log_prefix} Async logic reported SUCCEEDED.")
            return final_result_from_async_logic

        elif status_from_async == JobStatus.FAILED.value:
            error_type = final_result_from_async_logic.get("error_type", "GenericAsyncFailure")
            full_error_message = f"Task failed via async logic ({error_type}): {message_from_async}"
            logger.warning(
                f"{wrapper_log_prefix} Async logic reported FAILED. Raising RuntimeError: {full_error_message}"
            )
            raise RuntimeError(full_error_message)

        elif status_from_async == JobStatus.CANCELLED.value:
            logger.info(
                f"{wrapper_log_prefix} Async logic reported CANCELLED. Raising TaskRevokedError."
            )
            raise TaskRevokedError()

        else:
            unknown_status_msg = f"Async logic returned dict with unknown or missing 'status': '{status_from_async}'. Result: {final_result_from_async_logic}."
            logger.error(f"{wrapper_log_prefix} {unknown_status_msg}")
            raise RuntimeError(unknown_status_msg)

    except TaskRevokedError as err:
        logger.info(
            f"{wrapper_log_prefix} TaskRevokedError caught. Setting state to REVOKED with payload."
        )

        if (
            final_result_from_async_logic
            and final_result_from_async_logic.get("status") == JobStatus.CANCELLED.value
        ):
            revoked_payload = {
                "message": final_result_from_async_logic.get(
                    "message", "Job processing was revoked."
                ),
                "exit_code": final_result_from_async_logic.get("exit_code"),
                "log_snippet": final_result_from_async_logic.get("log_snippet"),
                "status_from_app": JobStatus.CANCELLED.value,
            }
        else:
            revoked_payload = {
                "message": "Task was revoked externally or before application logic determined cancellation.",
                "status_from_app": "REVOKED_BY_CELERY_OR_EXTERNAL",
            }

        self.update_state(state=states.REVOKED, meta=revoked_payload)

        raise Ignore() from err

    except Ignore as err:
        logger.warning(f"{wrapper_log_prefix} Task explicitly ignored (Ignore exception caught).")
        raise err from None

    except (SystemExit, KeyboardInterrupt, Terminated) as term_signal_exc:
        logger.warning(
            f"{wrapper_log_prefix} Termination signal ({type(term_signal_exc).__name__}) caught. Emergency DB update."
        )
        try:
            asyncio.run(
                _handle_terminated_job_in_db(job_db_id, term_signal_exc, wrapper_log_prefix)
            )
        except Exception as emergency_run_exc:
            logger.critical(
                f"{wrapper_log_prefix} Emergency DB update for terminated job FAILED: {emergency_run_exc}",
                exc_info=getattr(settings, "LOG_TRACEBACKS_CELERY_WRAPPER", False),
            )
        raise

    except RuntimeError as e_runtime:
        logger.error(
            f"{wrapper_log_prefix} RuntimeError caught: {e_runtime}",
            exc_info=getattr(settings, "LOG_TRACEBACKS_CELERY_WRAPPER", False),
        )
        raise

    except Exception as e_unhandled_wrapper:
        error_message_for_celery = f"SYNC WRAPPER UNEXPECTED error: {type(e_unhandled_wrapper).__name__}: {str(e_unhandled_wrapper)[:500]}"
        logger.error(
            f"{wrapper_log_prefix} {error_message_for_celery}",
            exc_info=getattr(settings, "LOG_TRACEBACKS_CELERY_WRAPPER", False),
        )
        try:
            logger.error(
                f"{wrapper_log_prefix} Emergency FAILED DB update for UNEXPECTED wrapper exception."
            )

            async def _emergency_db_update_on_wrapper_fail_local():
                tb_formatted = traceback.format_exc()
                log_snip_emergency = _trim(
                    f"Celery wrapper critical UNEXPECTED error: {error_message_for_celery}\n\n{tb_formatted}",
                    settings.JOB_LOG_SNIPPET_MAX_LEN,
                )
                await _handle_task_failure_in_db(
                    db=None,
                    redis_client=None,
                    crud_ops=crud_job_operations,
                    job_id=job_db_id,
                    error_obj=e_unhandled_wrapper,
                    task_log_prefix=wrapper_log_prefix + "[EmergencyWrapperUnexpectedFail]",
                    exit_code_override=EXIT_CODE_TASK_WRAPPER_ERROR,
                    log_snippet_override=log_snip_emergency,
                )

            asyncio.run(_emergency_db_update_on_wrapper_fail_local())
        except Exception as emerg_run_exc_outer:
            logger.critical(
                f"{wrapper_log_prefix} Emergency DB update (UNEXPECTED fail) FAILED: {emerg_run_exc_outer}",
                exc_info=True,
            )
        raise RuntimeError(error_message_for_celery) from e_unhandled_wrapper
    finally:
        logger.info(f"{wrapper_log_prefix} SYNC WRAPPER EXITING.")

    # Fallback - should not be reached if all statuses are handled by return/raise
    logger.critical(
        f"{wrapper_log_prefix} Reached unexpected end of sync wrapper. Async result: {final_result_from_async_logic}"
    )
    raise RuntimeError(
        "Sync wrapper logic error: Reached end without explicit return or exception for async result."
    )
