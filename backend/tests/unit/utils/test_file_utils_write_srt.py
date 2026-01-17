import os
from pathlib import Path

import pytest

from app.modules.subtitle.utils import file_utils


def test_write_srt_file_primary_path(tmp_path: Path) -> None:
    target = tmp_path / "sample.srt"
    result = file_utils.write_srt_file(str(target), "Line 1\nLine 2")

    assert result == str(target)
    assert target.exists()
    assert target.read_text(encoding="utf-8-sig") == "Line 1\nLine 2"


def test_write_srt_file_fallback_on_permission_error(tmp_path: Path, monkeypatch) -> None:
    if os.name == "nt":
        pytest.skip("Permission-based directory tests are unreliable on Windows.")

    no_write_dir = tmp_path / "no_write"
    no_write_dir.mkdir()
    no_write_dir.chmod(0o555)
    if os.access(str(no_write_dir), os.W_OK):
        pytest.skip("Could not make directory non-writable in this environment.")

    fallback_dir = tmp_path / "fallback"
    monkeypatch.setenv("SUBTITLE_FALLBACK_DIR", str(fallback_dir))

    target = no_write_dir / "fallback.srt"
    result = file_utils.write_srt_file(str(target), "Fallback content")

    result_path = Path(result)
    assert result_path.exists()
    assert fallback_dir in result_path.parents
    assert result_path.read_text(encoding="utf-8-sig") == "Fallback content"


def test_write_srt_file_no_fallback_raises(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("Permission-based directory tests are unreliable on Windows.")

    no_write_dir = tmp_path / "no_write_no_fallback"
    no_write_dir.mkdir()
    no_write_dir.chmod(0o555)
    if os.access(str(no_write_dir), os.W_OK):
        pytest.skip("Could not make directory non-writable in this environment.")

    target = no_write_dir / "denied.srt"
    with pytest.raises(PermissionError):
        file_utils.write_srt_file(str(target), "Denied", allow_fallback=False)
