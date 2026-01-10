from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.maintenance import manage_audit_partitions


@pytest.mark.asyncio
async def test_manage_audit_partitions_creation() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    # Mock relative date to be consistent
    today = date(2024, 1, 1)

    with patch("app.tasks.maintenance.date") as mock_date:
        mock_date.today.return_value = today

        # Mock DB responses:
        # 1st call: partition doesn't exist (returns None)
        # 2nd call: partition exists (returns something)
        mock_executor = MagicMock()
        mock_executor.scalar.side_effect = [
            None,
            "existing_table",
            "existing_table",
            "existing_table",
        ]
        db.execute.return_value = mock_executor

        # We need to mock the session maker used in the task
        with patch("app.tasks.maintenance.WorkerSessionLocal") as mock_session_local:
            mock_session_local.return_value.__aenter__.return_value = db

            await manage_audit_partitions()

            # Should have called execute for creation at least once
            assert db.execute.called

            # Verify the SQL matches roughly
            sql_calls = [str(call.args[0]) for call in db.execute.call_args_list]
            creation_called = any(
                "CREATE TABLE" in s and "audit_logs_2024_01" in s for s in sql_calls
            )
            assert creation_called
