# backend/tests/unit/tasks/test_subtitle_jobs.py
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
    subtitle_jobs,
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
    mock_settings_obj.JOB_TIMEOUT_SEC = 0.01  # Short for testing main timeout
    mock_settings_obj.PROCESS_TERMINATE_GRACE_PERIOD_S = 0.001  # Shorter for testing grace period
    mock_settings_obj.LOG_TRACEBACKS = True
    mock_settings_obj.LOG_TRACEBACKS_IN_JOB_LOGS = True
    mock_settings_obj.LOG_TRACEBACKS_CELERY_WRAPPER = True
    mock_settings_obj.DEBUG = True
    mock_settings_obj.JOB_RESULT_MESSAGE_MAX_LEN = 256
    mock_settings_obj.JOB_LOG_SNIPPET_MAX_LEN = 1024
    mock_settings_obj.LOG_SNIPPET_PREVIEW_LEN = 100

    original_settings = getattr(subtitle_jobs, "settings", None)
    monkeypatch.setattr(subtitle_jobs, "settings", mock_settings_obj)

    yield mock_settings_obj

    if original_settings is not None:
        monkeypatch.setattr(subtitle_jobs, "settings", original_settings)


@pytest_asyncio.fixture
async def mock_redis_client() -> AsyncGenerator[AsyncMock, None]:
    mock_client = AsyncMock(spec=aioredis_module.Redis)
    mock_client.publish = AsyncMock(return_value=1)
    mock_client.rpush = AsyncMock(return_value=1)
    mock_client.expire = AsyncMock(return_value=True)
    mock_client.close = AsyncMock()
    yield mock_client


@pytest.fixture
def mock_async_redis_from_url(mock_redis_client: AsyncMock) -> AsyncMock:
    # This fixture provides a mock for aioredis.from_url that simulates a successful connection by default
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
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=execute_result)
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
    crud_mock.update_job_start_details = AsyncMock(return_value=mock_job_instance)
    crud_mock.get = AsyncMock(return_value=mock_job_instance)
    crud_mock.get_job_by_id = AsyncMock(return_value=mock_job_instance)
    return crud_mock


@pytest.fixture
def mock_celery_task_context() -> MagicMock:
    task_mock = MagicMock()
    task_mock.request = MagicMock()
    task_mock.request.id = TEST_CELERY_TASK_ID
    task_mock.name = "test_celery_task_name"
    return task_mock


# Helper for mock_subprocess_protocol to reduce its complexity
def _create_mock_stream_reader_helper() -> AsyncMock:
    reader = AsyncMock(spec=asyncio.StreamReader)
    # Attach a list to the mock directly to act as the buffer
    reader.lines_buffer: list[bytes] = []

    def _at_eof_impl():
        return not reader.lines_buffer

    reader.at_eof = MagicMock(side_effect=_at_eof_impl)

    async def readline_mock():
        if reader.lines_buffer:
            return reader.lines_buffer.pop(0)
        # If buffer is empty, simulate EOF for subsequent calls
        reader.at_eof = MagicMock(return_value=True)
        return b""

    reader.readline = AsyncMock(side_effect=readline_mock)
    return reader


class MockProcessController:
    def __init__(self, process_mock: AsyncMock):
        self.process_mock = process_mock
        self._actual_return_code: int | None = None
        # Dynamically add attribute for test tracking
        self.process_mock._terminate_signal_sent: bool = False  # type: ignore[attr-defined]

        type(self.process_mock).returncode = PropertyMock(side_effect=self.get_rc)
        self.process_mock.terminate = MagicMock(side_effect=self.on_terminate_called)
        self.process_mock.kill = MagicMock(side_effect=self.on_kill_called)
        self.process_mock.wait = AsyncMock(side_effect=self.simple_wait_side_effect)
        self.set_rc(None)  # Initialize return code

    def set_rc(self, val: int | None):
        self._actual_return_code = val

    def get_rc(self):
        return self._actual_return_code

    def on_terminate_called(self):
        self.process_mock._terminate_signal_sent = True  # type: ignore[attr-defined]

    def on_kill_called(self):
        self.set_rc(-9)  # SIGKILL

    async def simple_wait_side_effect(self):
        # If return code is already set, return it (simulates process already exited)
        if self.get_rc() is not None:
            return self.get_rc()
        # Otherwise, simulate waiting indefinitely (to be interrupted by timeout or explicit rc set)
        await asyncio.Event().wait()
        # This part is reached if the event is somehow set externally,
        # or if wait is called after rc is set by kill/terminate.
        return self.get_rc()


@pytest_asyncio.fixture
async def mock_subprocess_protocol() -> (
    AsyncGenerator[tuple[AsyncMock, AsyncMock, AsyncMock], None]
):
    process_mock = AsyncMock(spec=asyncio.subprocess.Process)
    process_mock.pid = 12345

    MockProcessController(process_mock)  # Attaches behaviors to process_mock

    stdout_mock_reader = _create_mock_stream_reader_helper()
    process_mock.stdout = stdout_mock_reader
    # Expose buffer for tests to easily add lines / check content
    process_mock.stdout.stdout_lines = process_mock.stdout.lines_buffer  # type: ignore[attr-defined]

    stderr_mock_reader = _create_mock_stream_reader_helper()
    process_mock.stderr = stderr_mock_reader
    # Expose buffer for tests
    process_mock.stderr.stderr_lines = process_mock.stderr.lines_buffer  # type: ignore[attr-defined]

    yield process_mock, stdout_mock_reader, stderr_mock_reader


@pytest_asyncio.fixture
async def _mock_create_subprocess_exec(  # MODIFIED: Renamed fixture
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
    mock_async_redis_from_url: AsyncMock,
    mock_redis_client: AsyncMock,
    mock_get_worker_db_session: MagicMock,
    mock_db_session: AsyncMock,
    mock_crud_job: AsyncMock,
    _mock_create_subprocess_exec: AsyncMock,  # MODIFIED: Usage renamed
    mock_subprocess_protocol: tuple[AsyncMock, AsyncMock, AsyncMock],
    mock_path_exists: MagicMock,
):
    process_mock, stdout_mock_reader, stderr_mock_reader = mock_subprocess_protocol
    stdout_mock_reader.stdout_lines.extend([b"Script output line 1\n", b"Script output line 2\n"])
    stderr_mock_reader.stderr_lines.append(b"Script error detail 1\n")

    # Override the default fixture behavior for this specific test case
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
    assert mock_get_worker_db_session.call_count == 3
    assert mock_get_worker_db_session.return_value.__aenter__.await_count == 3
    assert mock_crud_job.update_job_start_details.await_count == 1
    assert mock_crud_job.update_job_completion_details.await_count == 1

    start_db_update_call_args = mock_crud_job.update_job_start_details.await_args_list[0]
    _, start_kwargs = start_db_update_call_args
    assert start_kwargs["db"] == mock_db_session
    assert start_kwargs["job_id"] == TEST_JOB_DB_ID
    assert start_kwargs["celery_task_id"] == TEST_CELERY_TASK_ID
    assert start_kwargs["started_at"] == ANY

    final_db_update_call_args = mock_crud_job.update_job_completion_details.await_args_list[0]
    _, final_kwargs = final_db_update_call_args
    assert final_kwargs["db"] == mock_db_session
    assert final_kwargs["job_id"] == TEST_JOB_DB_ID
    assert final_kwargs["status"] == JobStatus.SUCCEEDED
    assert final_kwargs["exit_code"] == 0
    assert "Script output line 2" in final_kwargs.get("result_message", "")
    assert "Script output line 1" in final_kwargs.get("log_snippet", "")
    assert "Script error detail 1" in final_kwargs.get("log_snippet", "")
    assert final_kwargs["completed_at"] == ANY
    assert mock_db_session.commit.await_count >= 2


@pytest.mark.asyncio
async def test_execute_subtitle_downloader_task_script_failure(
    mock_settings_env: Any,  # noqa: ARG001
    mock_celery_task_context: MagicMock,
    mock_async_redis_from_url: AsyncMock,  # noqa: ARG001
    mock_redis_client: AsyncMock,
    mock_get_worker_db_session: MagicMock,
    mock_db_session: AsyncMock,
    mock_crud_job: AsyncMock,
    _mock_create_subprocess_exec: AsyncMock,  # MODIFIED: Usage renamed
    mock_subprocess_protocol: tuple[AsyncMock, AsyncMock, AsyncMock],
    mock_path_exists: MagicMock,  # noqa: ARG001
):
    process_mock, stdout_mock_reader, stderr_mock_reader = mock_subprocess_protocol
    stdout_mock_reader.stdout_lines.append(b"Some output before error\n")
    stderr_mock_reader.stderr_lines.append(b"CRITICAL ERROR IN SCRIPT\n")

    # Override the default fixture behavior for this specific test case
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
                and isinstance(call_item.args[1], str | bytes)
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

    assert mock_get_worker_db_session.call_count == 3
    assert mock_crud_job.update_job_start_details.await_count == 1
    assert mock_crud_job.update_job_completion_details.await_count == 1

    start_db_update_call_args = mock_crud_job.update_job_start_details.await_args_list[0]
    _, start_kwargs = start_db_update_call_args
    assert start_kwargs["job_id"] == TEST_JOB_DB_ID
    assert start_kwargs["celery_task_id"] == TEST_CELERY_TASK_ID
    assert start_kwargs["started_at"] == ANY
    assert start_kwargs["db"] == mock_db_session

    final_db_update_call_args = mock_crud_job.update_job_completion_details.await_args_list[0]
    _, final_kwargs = final_db_update_call_args
    assert final_kwargs["status"] == JobStatus.FAILED
    assert final_kwargs["exit_code"] == 1
    assert "CRITICAL ERROR IN SCRIPT" in final_kwargs.get("result_message", "")
    assert "CRITICAL ERROR IN SCRIPT" in final_kwargs.get("log_snippet", "")
    assert final_kwargs["completed_at"] == ANY
    assert final_kwargs["db"] == mock_db_session
    assert mock_db_session.commit.await_count >= 2


@pytest.mark.asyncio
async def test_execute_subtitle_downloader_task_script_timeout(
    mock_settings_env: Any,
    mock_celery_task_context: MagicMock,
    mock_async_redis_from_url: AsyncMock,  # noqa: ARG001
    mock_redis_client: AsyncMock,
    mock_get_worker_db_session: MagicMock,
    mock_db_session: AsyncMock,
    mock_crud_job: AsyncMock,
    _mock_create_subprocess_exec: AsyncMock,  # MODIFIED: Usage renamed
    mock_subprocess_protocol: tuple[AsyncMock, AsyncMock, AsyncMock],
    mock_path_exists: MagicMock,  # noqa: ARG001
):
    process_mock, _, _ = mock_subprocess_protocol
    # Note: process_mock.wait uses the fixture's simple_wait_side_effect (hangs until event set)
    # process_mock.returncode uses the fixture's get_rc (initially None)

    original_asyncio_wait_for = asyncio.wait_for

    async def _cancel_and_drain(awaitable: Any) -> None:
        task = asyncio.ensure_future(awaitable)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def mock_wait_for_side_effect(awaitable: Any, **kwargs: Any) -> Any:
        timeout = kwargs.get("timeout")
        if timeout == mock_settings_env.JOB_TIMEOUT_SEC:
            await _cancel_and_drain(awaitable)
            raise TimeoutError("Simulated gather timeout")
        if timeout == mock_settings_env.PROCESS_TERMINATE_GRACE_PERIOD_S:
            # Simulate that even after terminate, process.wait() times out
            await _cancel_and_drain(awaitable)
            raise TimeoutError("Simulated grace period timeout")
        return await original_asyncio_wait_for(awaitable, **kwargs)

    with patch.object(
        subtitle_jobs.asyncio, "wait_for", side_effect=mock_wait_for_side_effect
    ) as mock_asyncio_wait_for_patch:
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
    assert "Simulated gather timeout" in result.get("message", "")
    assert result.get("error_type") == "TimeoutError"

    main_timeout_called = any(
        call.kwargs.get("timeout") == mock_settings_env.JOB_TIMEOUT_SEC
        for call in mock_asyncio_wait_for_patch.call_args_list
    )
    grace_period_timeout_called = any(
        call.kwargs.get("timeout") == mock_settings_env.PROCESS_TERMINATE_GRACE_PERIOD_S
        for call in mock_asyncio_wait_for_patch.call_args_list
    )
    assert main_timeout_called, "asyncio.wait_for not called with main job timeout"
    assert grace_period_timeout_called, "asyncio.wait_for not called with grace period timeout"

    process_mock.terminate.assert_called_once()
    process_mock.kill.assert_called_once()  # Called after grace period timeout

    expected_channel = f"job:{TEST_JOB_DB_ID_STR}:logs"
    publish_calls = mock_redis_client.publish.call_args_list
    last_status_publish_call = None
    for call_item in reversed(publish_calls):
        try:
            if (
                call_item.args
                and len(call_item.args) > 1
                and isinstance(call_item.args[1], str | bytes)
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
    # Exit code after kill is -9, set by on_kill_called -> set_rc(-9) in MockProcessController
    # The task-level failure handler uses a generic error code for unexpected exceptions.
    assert message_data["payload"]["exit_code"] == -500

    assert mock_get_worker_db_session.call_count == 3
    assert mock_crud_job.update_job_start_details.await_count == 1
    assert mock_crud_job.update_job_completion_details.await_count == 1

    start_db_update_call_args = mock_crud_job.update_job_start_details.await_args_list[0]
    _, start_kwargs = start_db_update_call_args
    assert start_kwargs["job_id"] == TEST_JOB_DB_ID
    assert start_kwargs["celery_task_id"] == TEST_CELERY_TASK_ID
    assert start_kwargs["started_at"] == ANY
    assert start_kwargs["db"] == mock_db_session

    final_db_update_call_args = mock_crud_job.update_job_completion_details.await_args_list[0]
    final_args, final_kwargs = final_db_update_call_args
    assert final_kwargs["status"] == JobStatus.FAILED
    assert final_kwargs["exit_code"] == -500  # SUT's timeout falls back to generic failure
    assert "Simulated gather timeout" in final_kwargs.get("result_message", "")
    assert "Simulated gather timeout" in final_kwargs.get("log_snippet", "")
    assert final_kwargs["completed_at"] == ANY
    assert final_args[0] == mock_db_session
    assert mock_db_session.commit.await_count >= 2


@pytest.mark.asyncio
async def test_execute_subtitle_downloader_task_redis_connection_failure(
    mock_settings_env: Any,
    mock_celery_task_context: MagicMock,
    mock_async_redis_from_url: AsyncMock,  # noqa: ARG001
    mock_get_worker_db_session: MagicMock,
    mock_db_session: AsyncMock,
    mock_crud_job: AsyncMock,
    _mock_create_subprocess_exec: AsyncMock,  # MODIFIED: Usage renamed
    mock_subprocess_protocol: tuple[AsyncMock, AsyncMock, AsyncMock],
    mock_path_exists: MagicMock,  # noqa: ARG001
):
    async def raise_redis_connection_error(*_args: Any, **_kwargs: Any) -> None:
        raise RedisConnectionError("Simulated Redis connection error")

    # Create an AsyncMock specifically for this test's side effect and use it as `new` for patch
    mock_from_url_with_error = AsyncMock(side_effect=raise_redis_connection_error)

    process_mock, stdout_mock_reader, _ = mock_subprocess_protocol
    stdout_mock_reader.stdout_lines.append(b"Script completed successfully\n")

    # Override the default fixture behavior for this specific test case
    type(process_mock).returncode = PropertyMock(return_value=0)
    process_mock.wait = AsyncMock(return_value=0)

    # Patch aioredis.from_url with our specific error-raising mock
    with patch.object(subtitle_jobs.aioredis, "from_url", mock_from_url_with_error):
        with patch.object(subtitle_jobs, "crud_job_operations", mock_crud_job):
            result = await subtitle_jobs._execute_subtitle_downloader_async_logic(
                mock_celery_task_context.name,
                mock_celery_task_context.request.id,
                TEST_JOB_DB_ID,
                TEST_FOLDER_PATH,
                TEST_LANGUAGE,
            )

    mock_from_url_with_error.assert_awaited_once_with(str(mock_settings_env.REDIS_PUBSUB_URL))

    assert result is not None
    assert result["job_id"] == TEST_JOB_DB_ID_STR
    assert result["status"] == JobStatus.SUCCEEDED.value  # Job succeeds even if Redis PubSub fails
    assert "Script completed successfully" in result.get("message", "")

    assert mock_get_worker_db_session.call_count == 3
    assert mock_crud_job.update_job_start_details.await_count == 1
    assert mock_crud_job.update_job_completion_details.await_count == 1

    start_db_update_call_args = mock_crud_job.update_job_start_details.await_args_list[0]
    _, start_kwargs = start_db_update_call_args
    assert start_kwargs["job_id"] == TEST_JOB_DB_ID
    assert start_kwargs["celery_task_id"] == TEST_CELERY_TASK_ID
    assert start_kwargs["started_at"] == ANY
    assert start_kwargs["db"] == mock_db_session

    final_db_update_call_args = mock_crud_job.update_job_completion_details.await_args_list[0]
    _, final_kwargs = final_db_update_call_args
    assert final_kwargs["status"] == JobStatus.SUCCEEDED
    assert final_kwargs["exit_code"] == 0
    assert "Script completed successfully" in final_kwargs.get("result_message", "")
    assert "Script completed successfully" in final_kwargs.get("log_snippet", "")
    assert final_kwargs["completed_at"] == ANY
    assert final_kwargs["db"] == mock_db_session
    assert mock_db_session.commit.await_count >= 2
