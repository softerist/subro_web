import subprocess
import sys
from pathlib import Path

# Determine the path to the mock script relative to this test file
# unit/utils/ -> up -> up -> integration/utils/mock_sub_downloader.py
MOCK_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "integration" / "utils" / "mock_sub_downloader.py"
)


def test_mock_script_exists() -> None:
    """Ensure we are targeting the correct file path."""
    assert MOCK_SCRIPT_PATH.exists(), f"Mock script not found at {MOCK_SCRIPT_PATH}"


def test_mock_script_success_output() -> None:
    """Test that the script prints the expected number of lines and exits with 0."""
    cmd = [
        sys.executable,
        str(MOCK_SCRIPT_PATH),
        "--duration",
        "0.1",
        "--stdout-lines",
        "3",
        "--stderr-lines",
        "1",
        "--exit-code",
        "0",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    assert result.returncode == 0

    # Analyze stdout
    # We expect 1 start line, 3 log lines, 1 finish line = 5 lines total (approx)
    # Splitting by newline and filtering empty strings
    stdout_lines = [line for line in result.stdout.split("\n") if line.strip()]
    assert len(stdout_lines) >= 3
    assert "STDOUT Line 1/3" in result.stdout
    assert "STDOUT Line 3/3" in result.stdout

    # Analyze stderr
    stderr_lines = [line for line in result.stderr.split("\n") if line.strip()]
    assert len(stderr_lines) == 1
    assert "STDERR Line 1/1" in result.stderr


def test_mock_script_failure_exit_code() -> None:
    """Test that the script returns the requested non-zero exit code."""
    cmd = [sys.executable, str(MOCK_SCRIPT_PATH), "--duration", "0.1", "--exit-code", "5"]

    result = subprocess.run(cmd, capture_output=True, text=True)

    assert result.returncode == 5
    assert "Script Finished. Exiting with code 5" in result.stdout


def test_mock_script_zero_output() -> None:
    """Test that the script handles zero output lines gracefully."""
    cmd = [
        sys.executable,
        str(MOCK_SCRIPT_PATH),
        "--duration",
        "0.1",
        "--stdout-lines",
        "0",
        "--stderr-lines",
        "0",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0
    # Should still see start/finish messages
    assert "Script Started" in result.stdout
    assert "Script Finished" in result.stdout
    # Should NOT see the Line counter messages
    assert "Line 1" not in result.stdout
