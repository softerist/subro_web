import asyncio
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.job import Job
from app.db.models.user import User
from app.schemas.job import JobStatus
from app.tasks.subtitle_jobs import _execute_subtitle_downloader_async_logic

# Locate the mock script
CURRENT_DIR = Path(__file__).parent
MOCK_SCRIPT_PATH = CURRENT_DIR.parent / "scripts" / "mock_downloader.py"


# --- Helper Fixture for Mocking Dependencies ---
@pytest.fixture
def mock_deps(db_session):
    """Provides mocks for Redis and DB context manager."""
    mock_redis = MagicMock()
    mock_redis.publish = AsyncMock()
    mock_redis.rpush = AsyncMock()
    mock_redis.expire = AsyncMock()
    mock_redis.close = AsyncMock()

    class MockDbSessionContext:
        def __init__(self):
            self.session = db_session

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    return mock_redis, MockDbSessionContext()


async def create_test_job(db_session, status=JobStatus.PENDING):
    """Helper to create a user and job."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"t_{user_id}@ex.com",
        hashed_password="pw",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    job_id = uuid.uuid4()
    job = Job(
        id=job_id,
        user_id=user_id,
        folder_path="/tmp/test",
        language="en",
        status=status,
        celery_task_id="tid",
    )
    db_session.add(job)
    await db_session.commit()
    return job_id


# --- TEST CASES ---


@pytest.mark.asyncio
async def test_task_runs_mock_script_success(db_session: AsyncSession, mock_deps):
    """Verifies successful script execution (Exit Code 0)."""
    mock_redis, mock_db_ctx = mock_deps
    job_id = await create_test_job(db_session)

    with (
        patch(
            "app.tasks.subtitle_jobs.settings.SUBTITLE_DOWNLOADER_SCRIPT_PATH",
            str(MOCK_SCRIPT_PATH),
        ),
        patch("app.tasks.subtitle_jobs.settings.JOB_TIMEOUT_SEC", 5.0),
        patch("app.tasks.subtitle_jobs._initialize_redis_client", return_value=mock_redis),
        patch("app.tasks.subtitle_jobs.get_worker_db_session", return_value=mock_db_ctx),
    ):
        # Default mock script args produce success
        result = await _execute_subtitle_downloader_async_logic(
            "t", "tid", job_id, "/tmp/test", "en"
        )

    assert result["status"] == JobStatus.SUCCEEDED.value
    assert result["exit_code"] == 0

    job = await db_session.get(Job, job_id)
    assert job.status == JobStatus.SUCCEEDED
    assert "[MOCK] Download complete" in job.log_snippet


@pytest.mark.asyncio
async def test_task_runs_mock_script_failure(db_session: AsyncSession, mock_deps):
    """Verifies script failure (Non-Zero Exit Code)."""
    mock_redis, mock_db_ctx = mock_deps
    job_id = await create_test_job(db_session)

    # To simulate failure, we need to pass --mock-exit-code 1 via command line args.
    # The current task logic constructs args internally based on folder_path/language.
    # We can't easily change the args passed to the script without patching the cmd construction
    # OR updating the mock script to fail based on a "magic" folder path.
    # Let's patch the argument construction in `_run_script_and_get_output` implicitly?
    # NO, better approach: Modify the Mock Script to look for a special folder name to trigger error?
    # Actually, simpler: Patch `_setup_subprocess` to inject our specific arguments.

    # Wait! The current task implementation allows passing `language`.
    # Let's abuse `language` to inject our mock flags since it's just a string appended to args.
    # The script parses args. If we pass language="en --mock-exit-code 1", argparse might complain
    # unless we are careful about quoting.
    # A cleaner way is to patch `settings.PYTHON_EXECUTABLE_PATH` or the args list.

    # Strategy: Patch asyncio.create_subprocess_exec to receive the arguments we WANT
    # regardless of what the function builds.

    # BETTER Strategy: Update the Mock Script logic? No, let's keep it generic.
    # Let's use the `folder_path` to trigger failure if we modify the mock script? No.

    # BEST Strategy: We will patch the `cmd_args` list inside `_execute_subtitle_script`?
    # That's hard to target.

    # ALTERNATIVE: We can rely on the fact that `asyncio.create_subprocess_exec` is called with `*cmd_args`.
    # Let's just create a job where the `folder_path` *contains* the trigger,
    # BUT we need the mock script to parse it.
    # Let's assume we can pass specific args.

    # Actually, let's patch `_run_script_and_get_output`? No, we want to test that.

    # Let's use `unittest.mock.patch` to wrap `_setup_subprocess`.
    # But wait, `language` is passed as an argument.
    # If we pass language="en", args are: [... --language en]
    # We can try to modify the actual `app.tasks.subtitle_jobs.py` to allow arbitrary args? No.

    # Workaround: We will use a magic string in `language` and assume the task handles it safely?
    # Python's subprocess array handling prevents injection.

    # OK, let's patch `asyncio.create_subprocess_exec` to *replace* the arguments it receives
    # with the ones that trigger failure, just before calling the real function.

    original_create_subprocess = asyncio.create_subprocess_exec

    async def side_effect_create_fail(*args, **kwargs):
        # We replace the args with our failure configuration
        new_args = list(args)
        # Find mock_downloader.py path index
        script_idx = -1
        for i, arg in enumerate(new_args):
            if str(MOCK_SCRIPT_PATH) in str(arg):
                script_idx = i
                break

        # Inject failure args
        if script_idx != -1:
            new_args.insert(script_idx + 1, "--mock-exit-code")
            new_args.insert(script_idx + 2, "1")
            new_args.insert(script_idx + 3, "--mock-stderr-lines")
            new_args.insert(script_idx + 4, "2")

        return await original_create_subprocess(*new_args, **kwargs)

    with (
        patch(
            "app.tasks.subtitle_jobs.settings.SUBTITLE_DOWNLOADER_SCRIPT_PATH",
            str(MOCK_SCRIPT_PATH),
        ),
        patch("app.tasks.subtitle_jobs.settings.JOB_TIMEOUT_SEC", 5.0),
        patch("app.tasks.subtitle_jobs._initialize_redis_client", return_value=mock_redis),
        patch("app.tasks.subtitle_jobs.get_worker_db_session", return_value=mock_db_ctx),
        patch("asyncio.create_subprocess_exec", side_effect=side_effect_create_fail),
    ):
        result = await _execute_subtitle_downloader_async_logic(
            "t", "tid", job_id, "/tmp/test", "en"
        )

    assert result["status"] == JobStatus.FAILED.value
    assert result["exit_code"] == 1

    job = await db_session.get(Job, job_id)
    assert job.status == JobStatus.FAILED
    assert "[MOCK ERROR] Simulated error message" in job.log_snippet


@pytest.mark.asyncio
async def test_task_setup_aborted_if_cancelled(db_session: AsyncSession, mock_deps):
    """Verifies task aborts immediately if Job is CANCELLING before start."""
    mock_redis, mock_db_ctx = mock_deps
    # Create job already in CANCELLING state
    job_id = await create_test_job(db_session, status=JobStatus.CANCELLING)

    with (
        patch(
            "app.tasks.subtitle_jobs.settings.SUBTITLE_DOWNLOADER_SCRIPT_PATH",
            str(MOCK_SCRIPT_PATH),
        ),
        patch("app.tasks.subtitle_jobs._initialize_redis_client", return_value=mock_redis),
        patch("app.tasks.subtitle_jobs.get_worker_db_session", return_value=mock_db_ctx),
    ):
        result = await _execute_subtitle_downloader_async_logic(
            "t", "tid", job_id, "/tmp/test", "en"
        )

    # Should finalize as CANCELLED immediately without running script
    assert result["status"] == JobStatus.CANCELLED.value
    # -104 is EXIT_CODE_CANCELLED_SETUP_ABORT_PREEMPTIVE_ASYNC or similar mapped code
    # We check if it matches the code set in `_execute_subtitle_downloader_async_logic` exception handler
    assert result["exit_code"] == -104

    job = await db_session.get(Job, job_id)
    assert job.status == JobStatus.CANCELLED
