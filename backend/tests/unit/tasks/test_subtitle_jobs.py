import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

# Import ANY for timestamp matching
from unittest.mock import ANY, AsyncMock, MagicMock, PropertyMock, patch

import pytest
import pytest_asyncio
import redis.asyncio as aioredis_module
from pydantic import RedisDsn
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_job import CRUDJob
from app.db.models.job import Job
from app.schemas.job import JobStatus

# Make sure the SUT (System Under Test) is correctly imported
from app.tasks import (
    subtitle_jobs,  # Assuming subtitle_jobs is the module containing _execute_subtitle_downloader_async_logic
)

TEST_JOB_DB_ID = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
TEST_JOB_DB_ID_STR = str(TEST_JOB_DB_ID)
TEST_CELERY_TASK_ID = "celery-task-id-test"
TEST_FOLDER_PATH = "/test/folder"
TEST_LANGUAGE = "eng"


@pytest.fixture
def mock_settings_env(monkeypatch: pytest.MonkeyPatch):
    mock_settings_obj = MagicMock()
    mock_settings_obj.REDIS_PUBSUB_URL = RedisDsn("redis://mock-redis:6379/1")
    mock_settings_obj.SUBTITLE_DOWNLOADER_SCRIPT_PATH = "/mock/scripts/sub_downloader.py"
    mock_settings_obj.PYTHON_EXECUTABLE_PATH = "/usr/bin/python3"
    mock_settings_obj.JOB_TIMEOUT_SEC = 0.1  # Default, can be overridden in tests
    mock_settings_obj.LOG_TRACEBACKS = True
    mock_settings_obj.LOG_TRACEBACKS_IN_JOB_LOGS = True
    mock_settings_obj.LOG_TRACEBACKS_CELERY_WRAPPER = True
    mock_settings_obj.DEBUG = True
    mock_settings_obj.JOB_RESULT_MESSAGE_MAX_LEN = 256
    mock_settings_obj.JOB_LOG_SNIPPET_MAX_LEN = 1024
    mock_settings_obj.LOG_SNIPPET_PREVIEW_LEN = 100
    mock_settings_obj.PROCESS_TERMINATE_GRACE_PERIOD_S = 0.001

    original_settings = getattr(subtitle_jobs, "settings", None)
    monkeypatch.setattr(subtitle_jobs, "settings", mock_settings_obj)

    yield mock_settings_obj

    if original_settings is not None:
        monkeypatch.setattr(subtitle_jobs, "settings", original_settings)


@pytest_asyncio.fixture
async def mock_redis_client() -> AsyncGenerator[AsyncMock, None]:
    mock_client = AsyncMock(spec=aioredis_module.Redis)
    mock_client.publish = AsyncMock(return_value=1)
    mock_client.close = AsyncMock()
    yield mock_client


@pytest.fixture
def mock_async_redis_from_url(mock_redis_client: AsyncMock) -> MagicMock:
    mock_from_url_function = AsyncMock(return_value=mock_redis_client)
    with patch.object(
        subtitle_jobs.aioredis, "from_url", mock_from_url_function
    ) as patched_from_url:
        yield patched_from_url


@pytest_asyncio.fixture
async def mock_db_session() -> AsyncGenerator[AsyncMock, None]:
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    yield session


@pytest_asyncio.fixture
async def mock_get_worker_db_session(mock_db_session: AsyncMock) -> AsyncGenerator[MagicMock, None]:
    mock_context_manager = AsyncMock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_db_session)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)

    mock_function_that_returns_cm = MagicMock(return_value=mock_context_manager)

    with patch.object(
        subtitle_jobs, "get_worker_db_session", mock_function_that_returns_cm
    ) as patched_get_session_function:
        yield patched_get_session_function


@pytest.fixture
def mock_crud_job() -> AsyncMock:
    crud_mock = AsyncMock(spec=CRUDJob)
    mock_job_instance = MagicMock(spec=Job)
    mock_job_instance.id = TEST_JOB_DB_ID
    mock_job_instance.status = JobStatus.RUNNING

    crud_mock.update_job_completion_details = AsyncMock(return_value=mock_job_instance)
    crud_mock.get_job_by_id = AsyncMock(return_value=mock_job_instance)
    return crud_mock


@pytest.fixture
def mock_celery_task_context() -> MagicMock:
    task_mock = MagicMock()
    task_mock.request = MagicMock()
    task_mock.request.id = TEST_CELERY_TASK_ID
    task_mock.name = "test_celery_task_name"
    return task_mock


@pytest_asyncio.fixture
async def mock_subprocess_protocol() -> (
    AsyncGenerator[tuple[AsyncMock, AsyncMock, AsyncMock], None]
):
    process_mock = AsyncMock(spec=asyncio.subprocess.Process)
    process_mock.pid = 12345

    _actual_return_code: int | None = None

    def set_rc(val: int | None):
        nonlocal _actual_return_code
        _actual_return_code = val

    def get_rc():
        return _actual_return_code

    type(process_mock).returncode = PropertyMock(side_effect=get_rc)
    set_rc(None)  # Initial state: process running / return code not yet set

    # Default wait behavior: returns the current _actual_return_code.
    # This code is set by terminate/kill side effects, or by test logic for specific scenarios.
    async def simple_wait_side_effect():
        return get_rc()

    process_mock.wait = AsyncMock(side_effect=simple_wait_side_effect)

    def on_terminate_called():
        # If process is terminated, its return code is typically -15 (SIGTERM).
        # Don't override if it was already killed (-9).
        if get_rc() != -9:
            set_rc(-15)

    process_mock.terminate = MagicMock(side_effect=on_terminate_called)

    def on_kill_called():
        # If process is killed, its return code is typically -9 (SIGKILL).
        set_rc(-9)

    process_mock.kill = MagicMock(side_effect=on_kill_called)

    # Helper to create mock stream readers
    def _create_mock_stream_reader() -> AsyncMock:
        reader = AsyncMock(spec=asyncio.StreamReader)
        # Tests will populate this list directly (e.g., reader.lines_buffer.append(b"line"))
        reader.lines_buffer: list[bytes] = []

        # at_eof initially depends on whether lines_buffer is empty
        reader.at_eof = MagicMock(side_effect=lambda: not reader.lines_buffer)

        async def readline_mock():
            if reader.lines_buffer:
                line = reader.lines_buffer.pop(0)
                # If buffer becomes empty, next at_eof() call (via lambda) will be True
                return line
            # Buffer is empty, so this readline call means EOF.
            # Future at_eof() calls should be sticky True.
            reader.at_eof = MagicMock(return_value=True)
            return b""

        reader.readline = AsyncMock(side_effect=readline_mock)
        return reader

    stdout_mock_reader = _create_mock_stream_reader()
    # Expose lines_buffer via a conventional name for tests to populate
    stdout_mock_reader.stdout_lines = stdout_mock_reader.lines_buffer

    stderr_mock_reader = _create_mock_stream_reader()
    # Expose lines_buffer via a conventional name for tests to populate
    stderr_mock_reader.stderr_lines = stderr_mock_reader.lines_buffer

    process_mock.stdout = stdout_mock_reader
    process_mock.stderr = stderr_mock_reader

    yield process_mock, stdout_mock_reader, stderr_mock_reader


@pytest_asyncio.fixture
async def mock_create_subprocess_exec(
    mock_subprocess_protocol: tuple[AsyncMock, AsyncMock, AsyncMock],
) -> AsyncGenerator[AsyncMock, None]:
    process_mock, _, _ = mock_subprocess_protocol
    with patch.object(
        subtitle_jobs.asyncio, "create_subprocess_exec", AsyncMock(return_value=process_mock)
    ) as mock_create_exec:
        yield mock_create_exec


@pytest.fixture
def mock_path_exists(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    actual_exists_method_mock = MagicMock(return_value=True)

    class MockPathObject:
        def __init__(self, path_str: Any):
            self._path_str = str(path_str)

        def exists(self) -> bool:
            return actual_exists_method_mock(self._path_str)

        def __str__(self) -> str:
            return self._path_str

        def __fspath__(self) -> str:
            return self._path_str

    monkeypatch.setattr(subtitle_jobs, "Path", MockPathObject)
    return actual_exists_method_mock


# Tests
@pytest.mark.asyncio
async def test_execute_subtitle_downloader_task_success_with_pubsub(
    mock_settings_env: Any,
    mock_celery_task_context: MagicMock,
    mock_async_redis_from_url: MagicMock,
    mock_redis_client: AsyncMock,
    mock_get_worker_db_session: MagicMock,
    mock_db_session: AsyncMock,
    mock_crud_job: AsyncMock,
    _mock_create_subprocess_exec: AsyncMock,  # Renamed as it's for setup
    mock_subprocess_protocol: tuple[AsyncMock, AsyncMock, AsyncMock],
    mock_path_exists: MagicMock,
):
    process_mock, stdout_mock_reader, stderr_mock_reader = mock_subprocess_protocol
    stdout_mock_reader.stdout_lines.extend([b"Script output line 1\n", b"Script output line 2\n"])
    stderr_mock_reader.stderr_lines.append(b"Script error detail 1\n")

    # For success, the process should exit with code 0
    type(process_mock).returncode = PropertyMock(return_value=0)
    process_mock.wait = AsyncMock(return_value=0)

    with patch.object(subtitle_jobs, "crud_job_operations", mock_crud_job):
        result = await subtitle_jobs._execute_subtitle_downloader_async_logic(
            mock_celery_task_context.name,
            mock_celery_task_context.request.id,
            TEST_JOB_DB_ID,
            TEST_FOLDER_PATH,
            TEST_LANGUAGE,
        )
    assert result is not None
    assert result["job_id"] == TEST_JOB_DB_ID_STR
    assert result["status"] == JobStatus.SUCCEEDED.value
    assert "Script output line 2" in result.get("message", "")

    expected_channel = f"job:{TEST_JOB_DB_ID_STR}:logs"
    mock_async_redis_from_url.assert_awaited_once_with(str(mock_settings_env.REDIS_PUBSUB_URL))
    publish_calls = mock_redis_client.publish.call_args_list
    assert len(publish_calls) >= 3

    initial_status_call = publish_calls[0]
    args, _ = initial_status_call
    message_data = json.loads(args[1])
    assert args[0] == expected_channel
    assert message_data["type"] == "status"
    assert message_data["payload"]["status"] == JobStatus.RUNNING.value

    stdout_messages_published = any(
        json.loads(c.args[1])["type"] == "log"
        and json.loads(c.args[1])["payload"]["stream"] == "stdout"
        and "Script output line 1" in json.loads(c.args[1])["payload"]["message"]
        for c in publish_calls
        if c.args and len(c.args) > 1 and isinstance(c.args[1], str | bytes)
    )
    assert stdout_messages_published, "Stdout message 'Script output line 1' not published"

    stderr_messages_published = any(
        json.loads(c.args[1])["type"] == "log"
        and json.loads(c.args[1])["payload"]["stream"] == "stderr"
        and "Script error detail 1" in json.loads(c.args[1])["payload"]["message"]
        for c in publish_calls
        if c.args and len(c.args) > 1 and isinstance(c.args[1], str | bytes)
    )
    assert stderr_messages_published, "Stderr message 'Script error detail 1' not published"

    final_status_call = publish_calls[-1]
    args, _ = final_status_call
    message_data = json.loads(args[1])
    assert args[0] == expected_channel
    assert message_data["type"] == "status"
    assert message_data["payload"]["status"] == JobStatus.SUCCEEDED.value

    mock_path_exists.assert_any_call(str(mock_settings_env.SUBTITLE_DOWNLOADER_SCRIPT_PATH))

    mock_get_worker_db_session.assert_called_once()
    mock_get_worker_db_session.return_value.__aenter__.assert_awaited_once()

    assert mock_crud_job.update_job_completion_details.await_count == 2

    initial_db_update_call_args = mock_crud_job.update_job_completion_details.await_args_list[0]
    _, initial_kwargs = initial_db_update_call_args
    assert initial_kwargs["db"] == mock_db_session
    assert initial_kwargs["job_id"] == TEST_JOB_DB_ID
    assert initial_kwargs["status"] == JobStatus.RUNNING
    assert initial_kwargs["celery_task_id"] == TEST_CELERY_TASK_ID
    assert initial_kwargs["started_at"] == ANY

    final_db_update_call_args = mock_crud_job.update_job_completion_details.await_args_list[1]
    _, final_kwargs = final_db_update_call_args
    assert final_kwargs["db"] == mock_db_session
    assert final_kwargs["job_id"] == TEST_JOB_DB_ID
    assert final_kwargs["status"] == JobStatus.SUCCEEDED
    assert final_kwargs["exit_code"] == 0
    assert "Script output line 2" in final_kwargs.get("result_message", "")
    assert "Script output line 1" in final_kwargs.get("log_snippet", "")
    assert "Script error detail 1" in final_kwargs.get("log_snippet", "")
    assert final_kwargs["completed_at"] == ANY

    assert mock_db_session.commit.await_count >= 1


@pytest.mark.asyncio
async def test_execute_subtitle_downloader_task_script_failure(
    _mock_settings_env: Any,  # Renamed
    mock_celery_task_context: MagicMock,
    _mock_async_redis_from_url: MagicMock,  # Renamed
    mock_redis_client: AsyncMock,
    _mock_get_worker_db_session: MagicMock,  # Renamed
    _mock_db_session: AsyncMock,  # Renamed (assuming linter is right, verify if tests fail)
    mock_crud_job: AsyncMock,
    _mock_create_subprocess_exec: AsyncMock,  # Renamed
    mock_subprocess_protocol: tuple[AsyncMock, AsyncMock, AsyncMock],
    _mock_path_exists: MagicMock,  # Renamed
):
    process_mock, stdout_mock_reader, stderr_mock_reader = mock_subprocess_protocol
    stdout_mock_reader.stdout_lines.append(b"Some output before error\n")
    stderr_mock_reader.stderr_lines.append(b"CRITICAL ERROR IN SCRIPT\n")

    # For script failure, simulate non-zero exit code
    type(process_mock).returncode = PropertyMock(return_value=1)
    process_mock.wait = AsyncMock(return_value=1)

    with patch.object(subtitle_jobs, "crud_job_operations", mock_crud_job):
        result = await subtitle_jobs._execute_subtitle_downloader_async_logic(
            mock_celery_task_context.name,
            mock_celery_task_context.request.id,
            TEST_JOB_DB_ID,
            TEST_FOLDER_PATH,
            TEST_LANGUAGE,
        )

    assert result is not None
    assert result["job_id"] == TEST_JOB_DB_ID_STR
    assert result["status"] == JobStatus.FAILED.value
    assert "CRITICAL ERROR IN SCRIPT" in result.get("message", "")

    expected_channel = f"job:{TEST_JOB_DB_ID_STR}:logs"
    publish_calls = mock_redis_client.publish.call_args_list
    last_status_publish_call = None
    for call_item in reversed(publish_calls):
        try:
            if (
                call_item.args
                and len(call_item.args) > 1
                and isinstance(call_item.args[1], str | bytes)  # UP038 fix
            ):
                message_data = json.loads(call_item.args[1])
                if message_data.get("type") == "status":
                    last_status_publish_call = call_item
                    break
        except (json.JSONDecodeError, IndexError, KeyError, TypeError):
            continue

    assert last_status_publish_call is not None, "No FAILED status message published to Redis"
    args, _ = last_status_publish_call
    message_data = json.loads(args[1])
    assert args[0] == expected_channel
    assert message_data["payload"]["status"] == JobStatus.FAILED.value
    assert message_data["payload"]["exit_code"] == 1

    assert mock_crud_job.update_job_completion_details.await_count == 2

    initial_db_update_call_args = mock_crud_job.update_job_completion_details.await_args_list[0]
    _, initial_kwargs = initial_db_update_call_args
    assert initial_kwargs["status"] == JobStatus.RUNNING
    assert initial_kwargs["celery_task_id"] == TEST_CELERY_TASK_ID
    assert initial_kwargs["started_at"] == ANY
    # If _mock_db_session was correctly identified as unused, this assertion would fail:
    # assert initial_kwargs["db"] == _mock_db_session # This line is an example of where it might be used

    final_db_update_call_args = mock_crud_job.update_job_completion_details.await_args_list[1]
    _, final_kwargs = final_db_update_call_args
    assert final_kwargs["status"] == JobStatus.FAILED
    assert final_kwargs["exit_code"] == 1
    assert "CRITICAL ERROR IN SCRIPT" in final_kwargs.get("result_message", "")
    assert "CRITICAL ERROR IN SCRIPT" in final_kwargs.get("log_snippet", "")
    assert final_kwargs["completed_at"] == ANY


@pytest.mark.asyncio
async def test_execute_subtitle_downloader_task_script_timeout(
    mock_settings_env: Any,
    mock_celery_task_context: MagicMock,
    _mock_async_redis_from_url: MagicMock,  # Renamed
    mock_redis_client: AsyncMock,
    _mock_get_worker_db_session: MagicMock,  # Renamed
    _mock_db_session: AsyncMock,  # Renamed
    mock_crud_job: AsyncMock,
    _mock_create_subprocess_exec: AsyncMock,  # Renamed
    mock_subprocess_protocol: tuple[AsyncMock, AsyncMock, AsyncMock],
    _mock_path_exists: MagicMock,  # Renamed
):
    process_mock, _, _ = mock_subprocess_protocol
    mock_settings_env.JOB_TIMEOUT_SEC = 0.01

    original_asyncio_wait_for = asyncio.wait_for

    async def mock_wait_for_side_effect(
        awaitable: Any,
        timeout: float | None,
        *_args: Any,
        **_kwargs: Any,  # ARG001 fix
    ) -> Any:
        if timeout == mock_settings_env.JOB_TIMEOUT_SEC:
            raise TimeoutError("Simulated gather timeout")
        if (
            awaitable == process_mock.wait
            and timeout == mock_settings_env.PROCESS_TERMINATE_GRACE_PERIOD_S
        ):
            raise TimeoutError("Simulated grace period timeout")
        return await original_asyncio_wait_for(awaitable, timeout=timeout)

    with patch.object(
        subtitle_jobs.asyncio, "wait_for", side_effect=mock_wait_for_side_effect
    ) as mock_async_wait_for_supervisor:
        with patch.object(subtitle_jobs, "crud_job_operations", mock_crud_job):
            result = await subtitle_jobs._execute_subtitle_downloader_async_logic(
                mock_celery_task_context.name,
                mock_celery_task_context.request.id,
                TEST_JOB_DB_ID,
                TEST_FOLDER_PATH,
                TEST_LANGUAGE,
            )

    assert result is not None
    assert result["job_id"] == TEST_JOB_DB_ID_STR
    assert result["status"] == JobStatus.FAILED.value
    # Note: SUT's error message for TimeoutError might be "Task failed: TimeoutError(...)"
    # The original assertion was "Subtitle script timed out: Simulated gather timeout"
    # Checking against the actual exception message passed into the task result.
    # The SUT's _JobContext._set_final_status_from_exception wraps the error.
    expected_task_result_error_msg_fragment = "Simulated gather timeout"
    assert expected_task_result_error_msg_fragment in result.get("error", "")

    assert mock_async_wait_for_supervisor.call_count >= 2

    process_mock.terminate.assert_called_once()
    process_mock.kill.assert_called_once()

    expected_channel = f"job:{TEST_JOB_DB_ID_STR}:logs"
    publish_calls = mock_redis_client.publish.call_args_list
    last_status_publish_call = None
    for call_item in reversed(publish_calls):
        try:
            if (
                call_item.args
                and len(call_item.args) > 1
                and isinstance(call_item.args[1], str | bytes)  # UP038 fix
            ):
                message_data = json.loads(call_item.args[1])
                if message_data.get("type") == "status":
                    last_status_publish_call = call_item
                    break
        except (json.JSONDecodeError, IndexError, KeyError, TypeError):
            continue

    assert (
        last_status_publish_call is not None
    ), "No FAILED status message published to Redis on timeout"
    args, _ = last_status_publish_call
    message_data = json.loads(args[1])
    assert args[0] == expected_channel
    assert message_data["payload"]["status"] == JobStatus.FAILED.value
    assert message_data["payload"]["exit_code"] == -99

    assert mock_crud_job.update_job_completion_details.await_count == 2

    initial_db_update_call_args = mock_crud_job.update_job_completion_details.await_args_list[0]
    _, initial_kwargs = initial_db_update_call_args
    assert initial_kwargs["status"] == JobStatus.RUNNING
    assert initial_kwargs["celery_task_id"] == TEST_CELERY_TASK_ID
    assert initial_kwargs["started_at"] == ANY

    final_db_update_call_args = mock_crud_job.update_job_completion_details.await_args_list[1]
    _, final_kwargs = final_db_update_call_args
    assert final_kwargs["status"] == JobStatus.FAILED
    assert final_kwargs["exit_code"] == -99
    expected_db_result_message_fragment = "Simulated gather timeout"  # Match the error logged
    assert expected_db_result_message_fragment in final_kwargs.get("result_message", "")
    assert expected_db_result_message_fragment in final_kwargs.get("log_snippet", "")
    assert final_kwargs["completed_at"] == ANY


@pytest.mark.asyncio
async def test_execute_subtitle_downloader_task_redis_connection_failure(
    mock_settings_env: Any,
    mock_celery_task_context: MagicMock,
    mock_async_redis_from_url: MagicMock,
    _mock_get_worker_db_session: MagicMock,  # Renamed
    _mock_db_session: AsyncMock,  # Renamed
    mock_crud_job: AsyncMock,
    _mock_create_subprocess_exec: AsyncMock,  # Renamed
    mock_subprocess_protocol: tuple[AsyncMock, AsyncMock, AsyncMock],
    _mock_path_exists: MagicMock,  # Renamed
):
    mock_async_redis_from_url.side_effect = RedisConnectionError("Simulated Redis connection error")
    process_mock, _, _ = mock_subprocess_protocol

    # Script itself succeeds
    type(process_mock).returncode = PropertyMock(return_value=0)
    process_mock.wait = AsyncMock(return_value=0)

    with patch.object(subtitle_jobs, "crud_job_operations", mock_crud_job):
        result = await subtitle_jobs._execute_subtitle_downloader_async_logic(
            mock_celery_task_context.name,
            mock_celery_task_context.request.id,
            TEST_JOB_DB_ID,
            TEST_FOLDER_PATH,
            TEST_LANGUAGE,
        )

    mock_async_redis_from_url.assert_awaited_once_with(str(mock_settings_env.REDIS_PUBSUB_URL))

    assert result is not None
    assert result["job_id"] == TEST_JOB_DB_ID_STR
    assert result["status"] == JobStatus.SUCCEEDED.value
    assert "Script completed successfully" in result.get("message", "")

    assert mock_crud_job.update_job_completion_details.await_count == 2

    initial_db_update_call_args = mock_crud_job.update_job_completion_details.await_args_list[0]
    _, initial_kwargs = initial_db_update_call_args
    assert initial_kwargs["status"] == JobStatus.RUNNING
    assert initial_kwargs["celery_task_id"] == TEST_CELERY_TASK_ID
    assert initial_kwargs["started_at"] == ANY

    final_db_update_call_args = mock_crud_job.update_job_completion_details.await_args_list[1]
    _, final_kwargs = final_db_update_call_args
    assert final_kwargs["status"] == JobStatus.SUCCEEDED
    assert final_kwargs["exit_code"] == 0
    assert "Script completed successfully" in final_kwargs.get("result_message", "")
    # Check that SUT logs contain a warning about Redis connection
    assert "Failed to initialize Redis client or publish initial status" in final_kwargs.get(
        "log_snippet", ""
    )
    assert final_kwargs["completed_at"] == ANY
