import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.tasks.audit_export import EXPORT_DIR, _run_audit_export_task


@pytest.mark.asyncio
async def test_audit_export_uncompressed(db_session):
    # Setup
    filters = {"action": "auth.login"}
    actor_user_id = "test-user-id"

    # Mock task object
    mock_task = MagicMock()
    mock_task.request.id = "test-job-id"

    # Mock the database session module used in the task
    # We need WorkerSessionLocal() to return an async context manager that yields our db_session
    mock_db_module = MagicMock()

    # Async context manager mock
    class AsyncContextManager:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, exc_type, exc, tb):
            pass

    mock_db_module.WorkerSessionLocal.return_value = AsyncContextManager()

    # Patch the module in the task file
    with patch("app.tasks.audit_export.db_session", mock_db_module):
        try:
            # Execute
            result = await _run_audit_export_task(mock_task, filters, actor_user_id)

            # Verify
            assert result["status"] == "COMPLETED"
            assert result["filename"].endswith(".json")
            assert not result["filename"].endswith(".gz")

            filepath = Path(result["filepath"])
            assert filepath.exists()

            # Check content is readable JSON (not GZIP binary)
            content = await asyncio.to_thread(filepath.read_text, encoding="utf-8")
            # It's JSONL, so each line should be a valid JSON object
            lines = content.strip().split("\n")
            if lines and lines[0]:
                first_line = json.loads(lines[0])
                assert isinstance(first_line, dict)

        finally:
            # Cleanup created files
            # We can't rely on mock_task.request.id if the task failed before using it,
            # but here we know the ID we passed.
            for file in EXPORT_DIR.glob("*test-job-id*"):
                file.unlink()
