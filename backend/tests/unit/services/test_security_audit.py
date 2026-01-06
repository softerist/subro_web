from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models.user import User
from app.services import account_lockout, api_validation, mfa_service


@pytest.mark.asyncio
async def test_mfa_setup_audit():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    user = User(id="user-123", email="test@example.com")

    with patch("app.services.audit_service.log_event", new_callable=AsyncMock) as mock_log:
        await mfa_service.setup_mfa(db, user)

        mock_log.assert_called()
        _, kwargs = mock_log.call_args
        assert kwargs["action"] == "auth.mfa.setup"
        assert kwargs["target_user_id"] == "user-123"


@pytest.mark.asyncio
async def test_api_key_validation_audit():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    class MockSettings:
        def __init__(self):
            self.tmdb_valid = None
            self.omdb_valid = None
            self.opensubtitles_valid = None
            self.opensubtitles_key_valid = None
            self.google_cloud_valid = None
            self.opensubtitles_rate_limited = None
            self.tmdb_rate_limited = None
            self.omdb_rate_limited = None

    settings_row = MockSettings()

    with (
        patch("app.services.api_validation.crud_app_settings") as mock_crud,
        patch("app.services.api_validation.validate_tmdb", new_callable=AsyncMock) as mock_tmdb,
        patch("app.services.api_validation.validate_omdb", new_callable=AsyncMock) as mock_omdb,
        patch(
            "app.services.api_validation.validate_opensubtitles", new_callable=AsyncMock
        ) as mock_os,
        patch(
            "app.services.api_validation.validate_google_cloud", new_callable=AsyncMock
        ) as mock_gc,
        patch("app.services.audit_service.log_event", autospec=True) as mock_log,
    ):
        mock_crud.get = AsyncMock(return_value=settings_row)

        async def mock_decrypt(_db, field):
            if any(x in field for x in ["key", "user", "pass", "cred"]):
                return "test-key"
            return None

        mock_crud.get_decrypted_value = AsyncMock(side_effect=mock_decrypt)

        mock_tmdb.return_value = {"valid": True, "rate_limited": False}
        mock_omdb.return_value = {"valid": True, "rate_limited": False}
        mock_os.return_value = {
            "key_valid": True,
            "login_valid": True,
            "rate_limited": False,
            "level": "Regular",
            "vip": False,
            "allowed_downloads": 5,
        }
        mock_gc.return_value = (True, "project-123", None)

        await api_validation.validate_all_settings(db)

        found_call = False
        for call in mock_log.call_args_list:
            _, kwargs = call
            if kwargs.get("action") == "security.api_validation":
                assert kwargs["details"]["tmdb_valid"] is True
                assert kwargs["details"]["validation_count"] == 4
                assert (
                    kwargs["details"]["apis_validated"] == "TMDB, OMDB, OpenSubtitles, Google Cloud"
                )
                found_call = True
        assert found_call


@pytest.mark.asyncio
async def test_account_lockout_delay_audit():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    with patch("app.services.audit_service.log_event", new_callable=AsyncMock):
        user = User(
            email="locked@example.com",
            failed_login_count=5,
            locked_until=datetime(2099, 1, 1, tzinfo=UTC),
            status="active",
        )

        mock_executor = MagicMock()
        mock_executor.scalar_one_or_none.return_value = user
        db.execute.return_value = mock_executor

        await account_lockout.get_progressive_delay(db, "locked@example.com")
