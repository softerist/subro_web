from pathlib import Path
from unittest.mock import patch

import pytest

from app.modules.subtitle.utils import file_utils


def test_write_srt_file_primary_path(tmp_path: Path) -> None:
    target = tmp_path / "sample.srt"
    result = file_utils.write_srt_file(str(target), "Line 1\nLine 2")

    assert result == str(target)
    assert target.exists()
    assert target.read_text(encoding="utf-8-sig") == "Line 1\nLine 2"


def test_write_srt_file_fallback_on_permission_error(tmp_path: Path, monkeypatch) -> None:
    """Test that fallback path is used when primary path is not writable."""
    fallback_dir = tmp_path / "fallback"
    monkeypatch.setenv("SUBTITLE_FALLBACK_DIR", str(fallback_dir))

    target = tmp_path / "primary" / "fallback.srt"

    # Mock _ensure_writable_target to raise PermissionError on primary, succeed on fallback
    original_ensure = file_utils._ensure_writable_target
    call_count = 0

    def mock_ensure(path: Path) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # First call is for primary path
            raise PermissionError(f"Target directory is not writable: '{path.parent}'")
        # Second call is for fallback path - let it succeed
        original_ensure(path)

    with patch.object(file_utils, "_ensure_writable_target", side_effect=mock_ensure):
        result = file_utils.write_srt_file(str(target), "Fallback content")

    result_path = Path(result)
    assert result_path.exists()
    assert fallback_dir in result_path.parents
    assert result_path.read_text(encoding="utf-8-sig") == "Fallback content"


def test_write_srt_file_no_fallback_raises(tmp_path: Path) -> None:
    """Test that PermissionError is raised when allow_fallback=False and path is not writable."""
    target = tmp_path / "denied" / "denied.srt"

    with patch.object(
        file_utils,
        "_ensure_writable_target",
        side_effect=PermissionError("Target directory is not writable"),
    ):
        with pytest.raises(PermissionError):
            file_utils.write_srt_file(str(target), "Denied", allow_fallback=False)


def test_write_srt_file_fallback_also_fails(tmp_path: Path, monkeypatch) -> None:
    """Test that PermissionError is raised when both primary and fallback fail."""
    fallback_dir = tmp_path / "fallback_fail"
    monkeypatch.setenv("SUBTITLE_FALLBACK_DIR", str(fallback_dir))

    target = tmp_path / "primary" / "test.srt"

    # Mock to always raise PermissionError
    with patch.object(
        file_utils,
        "_ensure_writable_target",
        side_effect=PermissionError("Not writable"),
    ):
        with pytest.raises(PermissionError):
            file_utils.write_srt_file(str(target), "Content")
