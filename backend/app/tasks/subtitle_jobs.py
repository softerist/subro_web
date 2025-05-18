# backend/app/tasks/subtitle_jobs.py
from __future__ import annotations

import asyncio
import json
import logging
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast  # Added Any
from uuid import UUID

import redis.asyncio as aioredis
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
    if "ts" not in payload:  # Ensure ts is string, not datetime object
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

        if settings.DEBUG:
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

        if not line_bytes:  # EOF
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


async def _execute_subtitle_downloader_async_logic(
    task_name_for_log: str,
    celery_internal_task_id: str,
    job_db_id: UUID,
    folder_path: str,
    language: str | None,
) -> dict:
    """Execute subtitle downloader task asynchronously with proper error handling and status reporting."""
    job_db_id_str = str(job_db_id)
    task_log_prefix = f"[AsyncTask:{task_name_for_log} CeleryID:{celery_internal_task_id} DBJobID:{job_db_id_str}]"
    logger.info(f"{task_log_prefix} ASYNC LOGIC ENTERED.")

    response = _create_default_error_response(job_db_id_str)
    stdout_accumulator: list[bytes] = []
    stderr_accumulator: list[bytes] = []
    redis_client = await _initialize_redis_client(settings.REDIS_PUBSUB_URL, task_log_prefix)

    try:
        response = await _execute_main_task_logic(
            job_db_id,
            job_db_id_str,
            celery_internal_task_id,
            folder_path,
            language,
            task_log_prefix,
            redis_client,
            stdout_accumulator,
            stderr_accumulator,
        )
    except RuntimeError as e:
        response = await _handle_runtime_error(e, job_db_id_str, redis_client, task_log_prefix)
    except SQLAlchemyError as db_e:
        response = await _handle_database_error(db_e, job_db_id_str, redis_client, task_log_prefix)
    except Exception as e_unhandled:
        response = await _handle_unexpected_error(
            e_unhandled, job_db_id, job_db_id_str, redis_client, task_log_prefix
        )
    finally:
        await _cleanup_resources(redis_client, task_log_prefix, response.get("status"))

    return response


async def _create_default_error_response(job_id: str) -> dict:
    """Create a default error response for early task failures."""
    return {
        "job_id": job_id,
        "status": JobStatus.FAILED.value,
        "message": "Task execution did not complete as expected due to an early error.",
        "error_type": "EarlyTaskError",
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
    job_db_id_str: str,
    celery_internal_task_id: str,
    folder_path: str,
    language: str | None,
    task_log_prefix: str,
    redis_client: aioredis.Redis | None,
    stdout_accumulator: list[bytes],
    stderr_accumulator: list[bytes],
) -> dict:
    """Execute the main task logic with database session."""
    async with get_worker_db_session() as db:
        await _setup_job_as_running(
            db,
            redis_client,
            crud_job_operations,
            job_db_id,
            celery_internal_task_id,
            task_log_prefix,
        )

        script_path = Path(settings.SUBTITLE_DOWNLOADER_SCRIPT_PATH)
        if not script_path.exists():
            return await _handle_missing_script(
                db, redis_client, job_db_id, job_db_id_str, task_log_prefix, script_path
            )

        return await _execute_subtitle_script(
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


async def _handle_missing_script(
    db: AsyncSession,
    redis_client: aioredis.Redis | None,
    job_db_id: UUID,
    job_db_id_str: str,
    task_log_prefix: str,
    script_path: Path,
) -> dict:
    """Handle the case when the script is not found."""
    err_msg = f"Configuration error: Subtitle downloader script not found at {script_path}"
    logger.error(f"{task_log_prefix} {err_msg}")

    await _handle_task_failure_in_db(
        db,
        redis_client,
        job_db_id_str,
        crud_job_operations,
        job_db_id,
        err_msg,
        task_log_prefix,
        exit_code_override=-201,
    )

    response = {
        "job_id": job_db_id_str,
        "status": JobStatus.FAILED.value,
        "error": err_msg[: settings.JOB_RESULT_MESSAGE_MAX_LEN],
        "error_type": "ScriptNotFoundError",
    }

    logger.warning(f"{task_log_prefix} {err_msg} - Job marked as FAILED.")
    return response


async def _handle_runtime_error(
    e: RuntimeError, job_db_id_str: str, redis_client: aioredis.Redis | None, task_log_prefix: str
) -> dict:
    """Handle RuntimeError exceptions."""
    err_msg = f"Critical error during async task execution: {type(e).__name__}: {e!s}"
    logger.error(f"{task_log_prefix} {err_msg}", exc_info=settings.LOG_TRACEBACKS)

    response = {
        "job_id": job_db_id_str,
        "status": JobStatus.FAILED.value,
        "error": f"Task execution failed (RuntimeError): {str(e)[:settings.JOB_RESULT_MESSAGE_MAX_LEN]}",
        "error_type": "AsyncTaskRuntimeError",
    }

    if not str(e).startswith("Task setup failed") and redis_client:
        await _publish_to_redis_pubsub_async(
            redis_client,
            job_db_id_str,
            "status",
            {
                "status": JobStatus.FAILED.value,
                "error_message": response["error"],
                "exit_code": -501,
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
    """Handle SQLAlchemy database errors."""
    err_msg = f"Database operation failed in async task logic: {type(db_e).__name__}: {db_e!s}"
    logger.error(f"{task_log_prefix} {err_msg}", exc_info=settings.LOG_TRACEBACKS)

    response = {
        "job_id": job_db_id_str,
        "status": JobStatus.FAILED.value,
        "error": f"Database error: {str(db_e)[:settings.JOB_RESULT_MESSAGE_MAX_LEN]}",
        "error_type": "AsyncTaskSQLAlchemyError",
    }

    if redis_client:
        await _publish_to_redis_pubsub_async(
            redis_client,
            job_db_id_str,
            "status",
            {
                "status": JobStatus.FAILED.value,
                "error_message": response["error"],
                "exit_code": -503,
            },
            task_log_prefix,
        )
    return response


async def _handle_unexpected_error(
    e: Exception,
    job_db_id: UUID,
    job_db_id_str: str,
    redis_client: aioredis.Redis | None,
    task_log_prefix: str,
) -> dict:
    """Handle unexpected exceptions and update the database accordingly."""
    err_msg = f"Unhandled exception in async task logic: {type(e).__name__}: {e!s}"
    logger.error(f"{task_log_prefix} {err_msg}", exc_info=settings.LOG_TRACEBACKS)

    response = {
        "job_id": job_db_id_str,
        "status": JobStatus.FAILED.value,
        "error": f"Task execution failed unexpectedly: {str(e)[:settings.JOB_RESULT_MESSAGE_MAX_LEN]}",
        "error_type": "AsyncTaskUnhandledException",
    }

    if redis_client:
        await _publish_to_redis_pubsub_async(
            redis_client,
            job_db_id_str,
            "status",
            {
                "status": JobStatus.FAILED.value,
                "error_message": response["error"],
                "exit_code": -502,
            },
            task_log_prefix,
        )

    try:
        async with get_worker_db_session() as db_emergency:
            await _handle_task_failure_in_db(
                db_emergency,
                redis_client,
                job_db_id_str,
                crud_job_operations,
                job_db_id,
                e,
                task_log_prefix,
                exit_code_override=-502,
            )
    except Exception as db_failure:
        logger.error(f"{task_log_prefix} Failed to record error in database: {db_failure}")

    return response


async def _cleanup_resources(
    redis_client: aioredis.Redis | None, task_log_prefix: str, final_status: Any
) -> None:
    """Close Redis connections and log task completion."""
    if redis_client:
        try:
            await redis_client.close()
            logger.debug(f"{task_log_prefix} Redis client for Pub/Sub closed.")
        except Exception as e_redis_close:
            logger.error(f"{task_log_prefix} Error closing Redis client: {e_redis_close}")

    logger.info(f"{task_log_prefix} ASYNC LOGIC EXITING. Final response status: {final_status}")


async def _setup_job_as_running(
    db: AsyncSession,
    redis_client: aioredis.Redis | None,
    crud_ops: CRUDJob,
    job_db_id: UUID,
    celery_task_id: str,
    task_log_prefix: str,
):
    logger.debug(
        f"{task_log_prefix} Attempting to update job to RUNNING with Celery ID {celery_task_id}."
    )
    job_db_id_str = str(job_db_id)

    try:
        current_time_utc = datetime.now(UTC)
        updated_job = await crud_ops.update_job_completion_details(
            db=db,
            job_id=job_db_id,
            status=JobStatus.RUNNING,
            started_at=current_time_utc,
            celery_task_id=celery_task_id,
            result_message=None,
            log_snippet=None,
            exit_code=None,
            completed_at=None,
        )

        if not updated_job:
            err_msg_for_exception = (
                f"Job with ID {job_db_id} not found or failed to update to RUNNING (pre-commit)."
            )
            logger.error(f"{task_log_prefix} {err_msg_for_exception}")
            if redis_client:
                await _publish_to_redis_pubsub_async(
                    redis_client,
                    job_db_id_str,
                    "status",
                    {
                        "status": JobStatus.FAILED.value,
                        "error_message": err_msg_for_exception,
                        "exit_code": -300,
                    },
                    task_log_prefix,
                )
            raise RuntimeError(f"Task setup failed: {err_msg_for_exception}")

        if redis_client:
            await _publish_to_redis_pubsub_async(
                redis_client,
                job_db_id_str,
                "status",
                {"status": JobStatus.RUNNING.value, "ts": current_time_utc},
                task_log_prefix,
            )
        else:
            logger.warning(
                f"{task_log_prefix} Redis client not available. Skipping RUNNING status publish to Pub/Sub."
            )

        await db.commit()
        logger.info(
            f"{task_log_prefix} Job status updated to RUNNING in DB and committed. Pub/Sub status sent if Redis available."
        )

    except SQLAlchemyError as db_exc:
        await db.rollback()
        err_msg = f"DB error updating job {job_db_id} to RUNNING: {db_exc}"
        if redis_client:
            await _publish_to_redis_pubsub_async(
                redis_client,
                job_db_id_str,
                "status",
                {"status": JobStatus.FAILED.value, "error_message": err_msg, "exit_code": -301},
                task_log_prefix,
            )
        logger.error(f"{task_log_prefix} {err_msg}", exc_info=settings.LOG_TRACEBACKS)
        raise RuntimeError(f"Task setup failed (DB update to RUNNING): {err_msg}") from db_exc
    except Exception as e:
        try:
            await db.rollback()
        except Exception as rb_exc:
            logger.error(
                f"{task_log_prefix} Rollback failed during general exception handling in _setup_job_as_running: {rb_exc}"
            )

        err_msg = f"Unexpected error updating job {job_db_id} to RUNNING: {e}"
        if redis_client:
            await _publish_to_redis_pubsub_async(
                redis_client,
                job_db_id_str,
                "status",
                {"status": JobStatus.FAILED.value, "error_message": err_msg, "exit_code": -302},
                task_log_prefix,
            )
        logger.error(f"{task_log_prefix} {err_msg}", exc_info=settings.LOG_TRACEBACKS)
        raise RuntimeError(f"Task setup failed (unexpected error): {err_msg}") from e


async def _execute_subtitle_script(
    db: AsyncSession,
    redis_client: aioredis.Redis | None,
    crud_ops: CRUDJob,
    job_db_id: UUID,
    folder_path: str,
    language: str | None,
    task_log_prefix: str,
    stdout_accumulator: list[bytes],
    stderr_accumulator: list[bytes],
) -> dict:
    job_db_id_str = str(job_db_id)
    script_path = Path(settings.SUBTITLE_DOWNLOADER_SCRIPT_PATH)
    job_timeout = settings.JOB_TIMEOUT_SEC

    exit_code: int = -1
    final_status: JobStatus = JobStatus.FAILED
    result_message: str = "Task processing encountered an unexpected state."
    log_snippet_str: str = ""

    try:
        exit_code = await _run_script_and_get_output(
            script_path=str(script_path),
            folder_path=folder_path,
            language=language,
            job_timeout_sec=float(job_timeout),
            task_log_prefix=task_log_prefix,
            redis_client=redis_client,
            job_db_id_str=job_db_id_str,
            stdout_accumulator=stdout_accumulator,
            stderr_accumulator=stderr_accumulator,
        )
        final_status, result_message, log_snippet_str = _parse_script_output(
            exit_code, b"".join(stdout_accumulator), b"".join(stderr_accumulator), task_log_prefix
        )

        await _finalize_job_in_db(
            db,
            crud_ops,
            job_db_id,
            final_status,
            exit_code,
            result_message,
            log_snippet_str,
            task_log_prefix,
        )

        if redis_client:
            final_payload = {"status": final_status.value, "ts": datetime.now(UTC)}
            if final_status == JobStatus.FAILED:
                final_payload["error_message"] = result_message
                final_payload["exit_code"] = exit_code
            await _publish_to_redis_pubsub_async(
                redis_client, job_db_id_str, "status", final_payload, task_log_prefix
            )
        else:
            logger.warning(
                f"{task_log_prefix} Redis client not available. Skipping final status ({final_status.value}) publish to Pub/Sub."
            )
        return {"job_id": job_db_id_str, "status": final_status.value, "message": result_message}

    except TimeoutError as te:
        err_msg_timeout = f"Subtitle script timed out: {te!s}"
        logger.error(f"{task_log_prefix} {err_msg_timeout}", exc_info=settings.LOG_TRACEBACKS)
        partial_stdout_str = b"".join(stdout_accumulator).decode("utf-8", errors="replace")
        partial_stderr_str = b"".join(stderr_accumulator).decode("utf-8", errors="replace")
        base_captured_script_log = _build_log_snippet(
            partial_stdout_str,
            partial_stderr_str,
            JobStatus.FAILED,
            -99,
            task_log_prefix,
        )
        log_snippet_for_timeout = f"TIMEOUT DETAILS: {err_msg_timeout}\n\n--- Captured Script Output ---\n{base_captured_script_log}"
        log_snippet_for_timeout = _trim(log_snippet_for_timeout, settings.JOB_LOG_SNIPPET_MAX_LEN)
        await _handle_task_failure_in_db(
            db,
            redis_client,
            job_db_id_str,
            crud_ops,
            job_db_id,
            te,
            task_log_prefix,
            exit_code_override=-99,
            log_snippet_override=log_snippet_for_timeout,
        )
        return {
            "job_id": job_db_id_str,
            "status": JobStatus.FAILED.value,
            "error": err_msg_timeout[: settings.JOB_RESULT_MESSAGE_MAX_LEN],
            "error_type": "ScriptTimeoutError",
        }
    except SQLAlchemyError as db_e:
        err_msg_db = (
            f"DB error during subtitle script finalization: {type(db_e).__name__}: {db_e!s}"
        )
        logger.error(f"{task_log_prefix} {err_msg_db}", exc_info=settings.LOG_TRACEBACKS)
        current_log_snippet = _build_log_snippet(
            b"".join(stdout_accumulator).decode("utf-8", errors="replace"),
            b"".join(stderr_accumulator).decode("utf-8", errors="replace"),
            JobStatus.FAILED,
            exit_code if exit_code != -1 else -202,
            task_log_prefix,
        )
        await _handle_task_failure_in_db(
            db,
            redis_client,
            job_db_id_str,
            crud_ops,
            job_db_id,
            db_e,
            task_log_prefix,
            exit_code_override=-202,
            log_snippet_override=_trim(current_log_snippet, settings.JOB_LOG_SNIPPET_MAX_LEN),
        )
        return {
            "job_id": job_db_id_str,
            "status": JobStatus.FAILED.value,
            "error": err_msg_db[: settings.JOB_RESULT_MESSAGE_MAX_LEN],
            "error_type": "ScriptFinalizationSQLAlchemyError",
        }
    except Exception as e:
        err_msg_general = (
            f"Subtitle script execution/finalization failed: {type(e).__name__}: {e!s}"
        )
        logger.error(f"{task_log_prefix} {err_msg_general}", exc_info=settings.LOG_TRACEBACKS)
        effective_exit_code = getattr(e, "exit_code", -200)
        if (
            exit_code != -1 and exit_code != -255
        ):  # -255 is initial value in _run_script_and_get_output
            effective_exit_code = exit_code
        current_log_snippet = _build_log_snippet(
            b"".join(stdout_accumulator).decode("utf-8", errors="replace"),
            b"".join(stderr_accumulator).decode("utf-8", errors="replace"),
            JobStatus.FAILED,
            effective_exit_code,
            task_log_prefix,
        )
        await _handle_task_failure_in_db(
            db,
            redis_client,
            job_db_id_str,
            crud_ops,
            job_db_id,
            e,
            task_log_prefix,
            exit_code_override=effective_exit_code,
            log_snippet_override=_trim(current_log_snippet, settings.JOB_LOG_SNIPPET_MAX_LEN),
        )
        return {
            "job_id": job_db_id_str,
            "status": JobStatus.FAILED.value,
            "error": err_msg_general[: settings.JOB_RESULT_MESSAGE_MAX_LEN],
            "error_type": "ScriptExecutionError",
        }


async def _setup_subprocess(
    cmd_args: list[str],
    task_log_prefix: str,
    redis_client: aioredis.Redis | None,
    job_db_id_str: str,
    stderr_accumulator: list[bytes],
) -> asyncio.subprocess.Process:
    """Creates and starts the subprocess, performs initial checks."""
    process = await asyncio.create_subprocess_exec(
        *cmd_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    logger.info(f"{task_log_prefix} Process (PID: {process.pid}) started.")
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
        if redis_client:
            await _publish_to_redis_pubsub_async(
                redis_client,
                job_db_id_str,
                "log",
                {"stream": "stderr", "message": f"[TASK_ERROR] {err_msg_streams}"},
                task_log_prefix,
            )
        raise RuntimeError(err_msg_streams)
    return process


async def _wait_for_process_exit_and_log(
    process: asyncio.subprocess.Process, task_log_prefix: str
) -> int:
    """Waits for process to exit and logs its raw exit code."""
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
    assert process.stdout is not None  # Ensured by _setup_subprocess
    assert process.stderr is not None  # Ensured by _setup_subprocess
    stdout_reader_task = asyncio.create_task(
        _read_stream_and_publish(
            process.stdout,
            "stdout",
            redis_client,
            job_db_id_str,
            task_log_prefix,
            stdout_accumulator,
        )
    )
    stderr_reader_task = asyncio.create_task(
        _read_stream_and_publish(
            process.stderr,
            "stderr",
            redis_client,
            job_db_id_str,
            task_log_prefix,
            stderr_accumulator,
        )
    )
    process_wait_task = asyncio.create_task(
        _wait_for_process_exit_and_log(process, task_log_prefix)
    )

    tasks_list: list[asyncio.Task[Any]] = [
        stdout_reader_task,
        stderr_reader_task,
        process_wait_task,
    ]
    gather_future: asyncio.Future[list[Any]] = asyncio.gather(*tasks_list, return_exceptions=True)
    return tasks_list, gather_future


def _process_gather_results(
    results: list[Any],
    process: asyncio.subprocess.Process,
    task_log_prefix: str,
) -> int:
    """Processes results from asyncio.gather, checking for task exceptions."""
    exit_code_to_return: int

    if isinstance(results[0], Exception):
        logger.error(
            f"{task_log_prefix} Stdout reading task failed: {results[0]}",
            exc_info=results[0] if settings.LOG_TRACEBACKS else False,
        )
    if isinstance(results[1], Exception):
        logger.error(
            f"{task_log_prefix} Stderr reading task failed: {results[1]}",
            exc_info=results[1] if settings.LOG_TRACEBACKS else False,
        )

    process_wait_result = results[2]
    if isinstance(process_wait_result, Exception):
        logger.error(
            f"{task_log_prefix} Process wait task itself failed: {process_wait_result}",
            exc_info=process_wait_result if settings.LOG_TRACEBACKS else False,
        )
        exit_code_to_return = process.returncode if process.returncode is not None else -97
    else:
        exit_code_to_return = cast(int, process_wait_result)

    logger.info(
        f"{task_log_prefix} All tasks (streams and process) completed. Final exit code from gather: {exit_code_to_return}."
    )
    return exit_code_to_return


async def _handle_cancelled_gather_future(
    gather_future: asyncio.Future[list[Any]] | None,
    process_pid_str: str,
    task_log_prefix: str,
):
    """Awaits a cancelled gather future to prevent 'Unretrieved _GatheringFuture exception'."""
    if gather_future and gather_future.cancelled():
        try:
            await gather_future
        except asyncio.CancelledError:
            logger.debug(
                f"{task_log_prefix} Gather future for PID {process_pid_str} was cancelled as expected after timeout."
            )
        except Exception as e_gather_await:
            logger.error(
                f"{task_log_prefix} Unexpected error awaiting cancelled gather for PID {process_pid_str}: {e_gather_await}",
                exc_info=settings.LOG_TRACEBACKS,
            )


async def _force_kill_process(
    process: asyncio.subprocess.Process, task_log_prefix: str, base_exit_code_on_failure: int
) -> int:
    """Force kills a process and logs, returning its exit code."""
    pid = process.pid
    if process.returncode is None:
        logger.warning(f"{task_log_prefix} Sending SIGKILL to process {pid}.")
        try:
            process.kill()
            killed_exit_code = await process.wait()
            logger.info(f"{task_log_prefix} Process {pid} killed. Exit code: {killed_exit_code}")
            return killed_exit_code
        except Exception as e:
            logger.error(
                f"{task_log_prefix} Error during SIGKILL for PID {pid}: {e}",
                exc_info=settings.LOG_TRACEBACKS,
            )
            return base_exit_code_on_failure
    if process.returncode is not None:  # Should be caught by earlier check, but defensive
        logger.info(
            f"{task_log_prefix} Process {pid} already exited with {process.returncode} before SIGKILL attempt."
        )
        return process.returncode
    return (
        base_exit_code_on_failure  # Should not be reached if process.returncode is None initially
    )


async def _terminate_process_gracefully(
    process: asyncio.subprocess.Process,
    task_log_prefix: str,
) -> int:
    """Attempts SIGTERM, then SIGKILL if process is still running. Returns determined exit code."""
    pid = process.pid
    determined_exit_code = -99

    if process.returncode is not None:
        logger.info(
            f"{task_log_prefix} Process (PID: {pid}) already exited with code {process.returncode} before _terminate_process_gracefully."
        )
        return process.returncode

    logger.info(f"{task_log_prefix} Process (PID: {pid}) still running. Attempting SIGTERM.")
    try:
        process.terminate()
        logger.info(f"{task_log_prefix} Sent SIGTERM to process {pid}.")
        await asyncio.wait_for(process.wait(), timeout=settings.PROCESS_TERMINATE_GRACE_PERIOD_S)
        if process.returncode is not None:
            determined_exit_code = process.returncode
        logger.info(
            f"{task_log_prefix} Process {pid} terminated after SIGTERM. Exit code: {determined_exit_code}"
        )
    except TimeoutError:
        logger.warning(
            f"{task_log_prefix} Process {pid} did not terminate after SIGTERM grace period."
        )
        determined_exit_code = await _force_kill_process(
            process, task_log_prefix, determined_exit_code
        )
    except ProcessLookupError:
        logger.warning(
            f"{task_log_prefix} Process {pid} already exited before SIGTERM could complete (ProcessLookupError)."
        )
        if process.returncode is not None:
            determined_exit_code = process.returncode
    except Exception as term_exc:
        logger.error(
            f"{task_log_prefix} Error during SIGTERM process termination for PID {pid}: {term_exc}",
            exc_info=settings.LOG_TRACEBACKS,
        )
        if process.returncode is None:
            logger.error(f"{task_log_prefix} Forcing kill due to error during SIGTERM.")
            determined_exit_code = await _force_kill_process(process, task_log_prefix, -9)
        elif process.returncode is not None:
            determined_exit_code = process.returncode
    return determined_exit_code


async def _ensure_tasks_cancelled_and_awaited(
    tasks: list[asyncio.Task[Any] | None], task_log_prefix: str
):
    """Cancels and awaits a list of tasks, typically in a finally block."""
    valid_tasks_to_finalize = [task for task in tasks if task is not None]
    if not valid_tasks_to_finalize:
        return

    logger.debug(
        f"{task_log_prefix} Ensuring {len(valid_tasks_to_finalize)} subprocess-related tasks are finalized."
    )
    for task_to_finalize in valid_tasks_to_finalize:
        if not task_to_finalize.done():
            task_to_finalize.cancel()

    await asyncio.gather(*valid_tasks_to_finalize, return_exceptions=True)
    logger.debug(f"{task_log_prefix} Finalized all provided subprocess-related tasks.")


async def _handle_script_timeout(
    process: asyncio.subprocess.Process | None,
    all_tasks_gather_future: asyncio.Future[list[Any]] | None,
    job_timeout_sec: float,
    stderr_accumulator: list[bytes],
    task_log_prefix: str,
) -> int:
    logger.warning(
        f"{task_log_prefix} Script execution gather timed out after {job_timeout_sec}s. Terminating process."
    )
    exit_code_after_timeout = -99

    current_pid_str = str(process.pid) if process else "Unknown"
    await _handle_cancelled_gather_future(all_tasks_gather_future, current_pid_str, task_log_prefix)

    if process and process.returncode is None:
        exit_code_after_timeout = await _terminate_process_gracefully(process, task_log_prefix)
    elif process and process.returncode is not None:
        logger.info(
            f"{task_log_prefix} Process (PID: {current_pid_str}) had already exited with code {process.returncode} when timeout was handled."
        )
        exit_code_after_timeout = process.returncode

    stderr_msg_timeout = f"\n[TASK_INTERNAL_ERROR] Script execution timed out after {job_timeout_sec} seconds. Final determined exit code: {exit_code_after_timeout}.\n".encode()
    stderr_accumulator.append(stderr_msg_timeout)
    return exit_code_after_timeout


async def _handle_script_management_error(
    e_manage: Exception,
    process: asyncio.subprocess.Process | None,
    stderr_accumulator: list[bytes],
    task_log_prefix: str,
) -> int:
    logger.error(
        f"{task_log_prefix} Exception during script subprocess management: {e_manage}",
        exc_info=settings.LOG_TRACEBACKS,
    )
    exit_code_after_error = -98

    stderr_msg_comm = (
        f"\n[TASK_INTERNAL_ERROR] Error managing script process: {e_manage!s}\n".encode()
    )
    stderr_accumulator.append(stderr_msg_comm)

    if process and process.returncode is None:
        logger.warning(
            f"{task_log_prefix} Attempting to kill process (PID: {process.pid}) due to management error."
        )
        try:
            process.kill()
            exit_code_after_error = await process.wait()
        except Exception as kill_err:
            logger.error(
                f"{task_log_prefix} Failed to kill process {getattr(process, 'pid', 'N/A')} after management error: {kill_err}"
            )
    elif process and process.returncode is not None:
        exit_code_after_error = process.returncode
    return exit_code_after_error


async def _final_process_cleanup_kill(
    process: asyncio.subprocess.Process | None,
    current_exit_code: int,
    task_log_prefix: str,
) -> int:
    if process and process.returncode is None:
        logger.warning(
            f"{task_log_prefix} Process (PID: {process.pid}) found still running in final `finally` block. Forcing kill."
        )
        try:
            process.kill()
            final_killed_exit_code = await asyncio.wait_for(process.wait(), timeout=1.0)
            special_error_codes = [-99, -98, -254, -9, -97]
            if current_exit_code not in special_error_codes and final_killed_exit_code is not None:
                return final_killed_exit_code
        except Exception as final_kill_exc:
            logger.error(
                f"{task_log_prefix} Error during final forced kill of process {process.pid}: {final_kill_exc}"
            )
            special_error_codes = [-99, -98, -254, -9, -97]
            if current_exit_code not in special_error_codes:
                return -9  # A distinct error code indicating final kill failure
    return current_exit_code


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
    cmd_args = [str(settings.PYTHON_EXECUTABLE_PATH), script_path, "--folder-path", folder_path]
    if language:
        cmd_args.extend(["--language", language])

    logger.info(f"{task_log_prefix} Executing command: {' '.join(cmd_args)}")

    exit_code_to_return = -255  # Default/initial "indeterminate" exit code
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
        (
            monitoring_tasks,  # [stdout_task, stderr_task, process_wait_task]
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
            f"{task_log_prefix} Gathering stream readers and process.wait() with timeout {job_timeout_sec}s."
        )
        # This is the main wait point. `all_tasks_gather_future` completes when all tasks in it complete.
        # The `process_wait_task` within it only completes when the subprocess itself exits.
        results = await asyncio.wait_for(all_tasks_gather_future, timeout=job_timeout_sec)
        exit_code_to_return = _process_gather_results(results, process, task_log_prefix)

    except RuntimeError as e_setup:  # Covers _setup_subprocess failure (e.g. streams not available)
        logger.error(
            f"{task_log_prefix} Subprocess setup failed: {e_setup}",
            exc_info=settings.LOG_TRACEBACKS,
        )
        exit_code_to_return = -254  # Specific code for setup failure before full execution
        # This error needs to be re-raised to be caught by _execute_subtitle_script's general Exception handler
        # which then calls _handle_task_failure_in_db.
        # Or, we can directly call something similar to _handle_task_failure_in_db logic here.
        # For simplicity, let the outer handler in _execute_subtitle_script catch it.
        raise
    except TimeoutError:  # Specifically from asyncio.wait_for(all_tasks_gather_future, ...)
        # This means the script + stream reading took too long.
        exit_code_to_return = await _handle_script_timeout(
            process, all_tasks_gather_future, job_timeout_sec, stderr_accumulator, task_log_prefix
        )
        # Re-raise for _execute_subtitle_script to handle TimeoutError specifically for DB update.
        raise
    except Exception as e_manage:  # Other errors during process management or gather
        exit_code_to_return = await _handle_script_management_error(
            e_manage, process, stderr_accumulator, task_log_prefix
        )
        # Re-raise for _execute_subtitle_script's general Exception handler.
        raise
    finally:
        # Ensure all monitoring tasks (stdout/stderr readers, process_wait_task) are cancelled and awaited.
        # This is crucial to prevent "Task was destroyed but it is pending!" warnings
        # and to clean up resources, especially if an exception occurred.
        await _ensure_tasks_cancelled_and_awaited(monitoring_tasks, task_log_prefix)

        # Final check: if process is somehow still running (e.g., cancellation logic failed or was bypassed), kill it.
        # This also handles the case where an error occurred *after* process start but *before* normal exit/timeout handling.
        exit_code_to_return = await _final_process_cleanup_kill(
            process, exit_code_to_return, task_log_prefix
        )

    return exit_code_to_return


def _parse_script_output(
    exit_code: int, stdout_bytes: bytes, stderr_bytes: bytes, task_log_prefix: str
) -> tuple[JobStatus, str, str]:
    stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
    _log_raw_output(stdout, stderr, task_log_prefix)
    final_status = JobStatus.SUCCEEDED if exit_code == 0 else JobStatus.FAILED
    log_snippet = _build_log_snippet(stdout, stderr, final_status, exit_code, task_log_prefix)
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
        logger.debug(
            f"{prefix} STDERR (first {settings.LOG_SNIPPET_PREVIEW_LEN} chars):\n"
            f"{stderr[:settings.LOG_SNIPPET_PREVIEW_LEN]}"
        )


def _build_log_snippet(
    stdout: str, stderr: str, status: JobStatus, code: int, task_log_prefix: str
) -> str:
    parts = []
    if stdout:
        parts.append(f"STDOUT:\n{stdout}")
    if stderr:
        parts.append(f"STDERR:\n{stderr}")
        if status == JobStatus.FAILED and code != -99:  # -99 is timeout, already logged explicitly
            logger.warning(
                f"{task_log_prefix} Task failed with STDERR. Code: {code}. STDERR (first 500 chars): {stderr[:500]}"
            )
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

    # For failures, prioritize stderr for the message
    err_lines = [
        ln
        for ln in stderr.splitlines()
        if ln.strip()
        and not ln.startswith("[TASK_INTERNAL_ERROR]")  # Filter out our own task messages
    ]
    if err_lines:
        relevant_err_lines = err_lines[-3:]  # Get last few lines
        snippet = " | ".join(relevant_err_lines)
        return f"Script failed (code {code}). Error: {snippet}"

    # If no stderr, try stdout for failure context
    out_lines = [ln for ln in stdout.splitlines() if ln.strip()]
    if out_lines:
        return f"Script failed (code {code}). Last output: {out_lines[-1]}"

    # Specific message for timeout if not already clear
    if code == -99:  # Timeout code from _handle_script_timeout
        return f"Script failed due to timeout (code {code})."
    return f"Script failed (code {code}) with no discernible output."


def _trim(text: str, max_len: int) -> str:
    return text[: max_len - 3] + "..." if len(text) > max_len else text


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
    logger.debug(
        f"{task_log_prefix} Attempting to stage job completion details with status {status.value}."
    )
    try:
        await crud_ops.update_job_completion_details(
            db=db,
            job_id=job_db_id,
            status=status,
            exit_code=exit_code,
            result_message=result_message,
            log_snippet=log_snippet,
            completed_at=datetime.now(UTC),
        )
        # Note: db.commit() is handled by the calling context (_execute_main_task_logic's `async with`)
        # or explicitly in error handlers (_handle_task_failure_in_db).
        logger.info(
            f"{task_log_prefix} Job final status attributes prepared for commit (status: {status.value})."
        )
    except Exception as e:  # Includes SQLAlchemyError if commit fails or other issues
        logger.error(
            f"{task_log_prefix} FAILED to stage job completion details for commit: {e}",
            exc_info=settings.LOG_TRACEBACKS,
        )
        raise  # Re-raise to be caught by the caller's error handling


async def _handle_task_failure_in_db(
    db: AsyncSession,
    redis_client: aioredis.Redis | None,
    job_db_id_str_for_pubsub: str,
    crud_ops: CRUDJob,
    job_id: UUID,
    error: Exception | str,
    task_log_prefix: str,
    exit_code_override: int = -400,  # General internal task failure
    log_snippet_override: str | None = None,
):
    err_str = str(error)
    result_message_full = (
        f"Task failed: {type(error).__name__}: {err_str}"
        if isinstance(error, Exception)
        else f"Task failed: {err_str}"
    )
    tb_str = ""
    if isinstance(error, Exception) and settings.LOG_TRACEBACKS_IN_JOB_LOGS:
        # Capture traceback if it's an exception and configured
        tb_full = traceback.format_exc()
        # Ensure traceback doesn't make log_snippet too long
        max_tb_len_for_snippet = (
            settings.JOB_LOG_SNIPPET_MAX_LEN - len(result_message_full) - 100
        )  # Approximation
        if max_tb_len_for_snippet < 200:  # Minimum reasonable length for a TB
            max_tb_len_for_snippet = 200
        tb_str = f"\nTraceback:\n{tb_full[:max_tb_len_for_snippet]}"
        if len(tb_full) > max_tb_len_for_snippet:
            tb_str += "..."

    log_snippet_full: str
    if log_snippet_override is not None:
        log_snippet_full = log_snippet_override
        if tb_str:  # Append traceback if available and an override is given
            log_snippet_full += tb_str
    else:
        log_snippet_full = f"Task error details: {result_message_full}{tb_str}"

    result_message_trimmed = _trim(result_message_full, settings.JOB_RESULT_MESSAGE_MAX_LEN)
    log_snippet_trimmed = _trim(log_snippet_full, settings.JOB_LOG_SNIPPET_MAX_LEN)

    logger.warning(f"{task_log_prefix} Attempting to mark job as FAILED due to task error: {error}")
    try:
        failure_time_utc = datetime.now(UTC)
        await crud_ops.update_job_completion_details(
            db=db,
            job_id=job_id,
            status=JobStatus.FAILED,
            exit_code=exit_code_override,
            result_message=result_message_trimmed,
            log_snippet=log_snippet_trimmed,
            completed_at=failure_time_utc,
        )
        # Try to publish failure to Redis if client is available
        if redis_client:
            await _publish_to_redis_pubsub_async(
                redis_client,
                job_db_id_str_for_pubsub,
                "status",
                {
                    "status": JobStatus.FAILED.value,
                    "ts": failure_time_utc,  # Use the same timestamp
                    "error_message": result_message_full,  # Publish full message
                    "exit_code": exit_code_override,
                },
                task_log_prefix,
            )
        else:
            logger.warning(
                f"{task_log_prefix} Redis client not available. Skipping FAILED status publish from _handle_task_failure_in_db."
            )

        await db.commit()  # Crucial: commit the failure state
        logger.info(
            f"{task_log_prefix} Job marked as FAILED in DB due to task error and committed. Pub/Sub status sent if Redis available."
        )
    except Exception as db_exc:  # If updating DB itself fails
        logger.error(
            f"{task_log_prefix} Additionally FAILED to update DB on task error: {db_exc}",
            exc_info=settings.LOG_TRACEBACKS,
        )
        try:
            await db.rollback()  # Attempt to rollback any partial changes
            logger.info(
                f"{task_log_prefix} Rolled back DB transaction after failing to mark job as FAILED."
            )
        except Exception as rb_exc:
            logger.error(
                f"{task_log_prefix} Rollback also failed after failing to update DB on task error: {rb_exc}"
            )
        # Original error should still be propagated or handled by caller


@celery_app.task(
    name=settings.CELERY_SUBTITLE_TASK_NAME,
    bind=True,
    track_started=True,
    acks_late=settings.CELERY_ACKS_LATE,
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

    job_db_id: UUID
    try:
        job_db_id = UUID(job_db_id_str)
    except ValueError:
        logger.error(
            f"{wrapper_log_prefix} Invalid job_db_id_str: '{job_db_id_str}'. Cannot proceed.",
            exc_info=True,
        )
        # This error occurs before DB interaction for this job, so we can't easily mark the specific job FAILED.
        # Raising ValueError will make Celery mark the task as FAILED.
        raise ValueError(f"Invalid Job DB ID format: {job_db_id_str}") from None

    final_result_from_async = None
    try:
        logger.info(f"{wrapper_log_prefix} Invoking asyncio.run() for async logic.")
        final_result_from_async = asyncio.run(
            _execute_subtitle_downloader_async_logic(
                task_name_for_log, celery_internal_task_id, job_db_id, folder_path, language
            )
        )
        logger.info(
            f"{wrapper_log_prefix} Async logic completed. Raw result: {str(final_result_from_async)[:500]}..."
        )

        # If async logic explicitly returned a FAILED status, ensure Celery task reflects this.
        if (
            isinstance(final_result_from_async, dict)
            and final_result_from_async.get("status") == JobStatus.FAILED.value
        ):
            failure_message = final_result_from_async.get(
                "error", final_result_from_async.get("message", "Async failure.")
            )
            error_type = final_result_from_async.get("error_type", "GenericAsyncFailure")
            logger.warning(
                f"{wrapper_log_prefix} Async logic reported failure (Type: {error_type}): '{failure_message}'. Raising."
            )
            # Raise a RuntimeError to make Celery mark the task as FAILED.
            # The DB job status should have already been set to FAILED by the async logic.
            raise RuntimeError(f"Task failed via async logic ({error_type}): {failure_message}")

        logger.info(
            f"{wrapper_log_prefix} SYNC WRAPPER COMPLETED successfully. Result: {final_result_from_async}"
        )
        return final_result_from_async  # This is what Celery stores as the task result

    except RuntimeError as e_runtime:
        # This catches RuntimeErrors raised from _execute_subtitle_downloader_async_logic
        # (e.g., from _setup_job_as_running or if we re-raise them)
        # or the one raised just above if async logic returned FAILED.
        logger.error(
            f"{wrapper_log_prefix} RuntimeError caught in SYNC WRAPPER: {e_runtime}",
            exc_info=settings.LOG_TRACEBACKS_CELERY_WRAPPER,
        )
        # Re-raise to ensure Celery marks the task as FAILED.
        # The job status in DB should ideally be FAILED already by this point if the error
        # originated within the main async try-except block.
        raise
    except Exception as e_unhandled_wrapper:
        # This catches truly unexpected errors in the sync wrapper or asyncio.run() itself.
        logger.error(
            f"{wrapper_log_prefix} Unexpected exception caught in SYNC WRAPPER: {type(e_unhandled_wrapper).__name__}: {e_unhandled_wrapper}",
            exc_info=settings.LOG_TRACEBACKS_CELERY_WRAPPER,
        )
        error_message_for_celery = f"Celery task wrapper unexpected error: {type(e_unhandled_wrapper).__name__}: {str(e_unhandled_wrapper)[:500]}"

        # Emergency attempt to mark the job as FAILED in DB and Pub/Sub,
        # as the main async logic might not have reached its own error handling.
        try:
            logger.error(
                f"{wrapper_log_prefix} Emergency: Attempting to mark job {job_db_id_str} as FAILED."
            )

            async def emergency_db_and_pubsub_update():
                redis_emergency_client = None
                try:
                    if settings.REDIS_PUBSUB_URL:
                        redis_emergency_client = await aioredis.from_url(
                            str(settings.REDIS_PUBSUB_URL)
                        )
                    async with get_worker_db_session() as db_emergency:
                        # traceback.format_exc() will capture the traceback of e_unhandled_wrapper
                        # as this function is called from within its except block.
                        tb_formatted_str = (
                            traceback.format_exc()
                        )  # Get traceback for the current exception
                        await _handle_task_failure_in_db(
                            db_emergency,
                            redis_emergency_client,
                            job_db_id_str,
                            crud_job_operations,
                            job_db_id,
                            error_message_for_celery,  # Pass the error string
                            wrapper_log_prefix,
                            exit_code_override=-600,  # Unique code for wrapper failure
                            log_snippet_override=f"Celery wrapper critical error: {error_message_for_celery}\n\n{tb_formatted_str}",
                        )
                except Exception as emergency_update_err:
                    logger.critical(
                        f"{wrapper_log_prefix} Emergency DB/PubSub update FAILED: {emergency_update_err}",
                        exc_info=True,  # Log this critical failure too
                    )
                finally:
                    if redis_emergency_client:
                        await redis_emergency_client.close()

            asyncio.run(emergency_db_and_pubsub_update())
        except (
            Exception
        ) as emergency_setup_exc:  # Catch errors from asyncio.run or redis/db connection
            logger.critical(
                f"{wrapper_log_prefix} Setup for emergency DB/PubSub update FAILED: {emergency_setup_exc}",
                exc_info=True,
            )

        # Finally, raise an error to make Celery mark the task as FAILED.
        raise RuntimeError(error_message_for_celery) from e_unhandled_wrapper
    finally:
        logger.info(f"{wrapper_log_prefix} SYNC WRAPPER EXITING.")
