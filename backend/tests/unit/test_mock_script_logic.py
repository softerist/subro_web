import subprocess
import sys
from pathlib import Path

# Locate the mock script relative to this test file
CURRENT_DIR = Path(__file__).parent
# Adjust this path if you saved the script elsewhere
MOCK_SCRIPT_PATH = CURRENT_DIR.parent / "scripts" / "mock_downloader.py"


class TestMockScriptBehavior:
    """
    Verifies that the mock script (Task 3.1A) behaves correctly
    when executed as a subprocess.
    """

    def test_mock_script_exists(self) -> None:
        """Ensure the mock script file actually exists."""
        assert MOCK_SCRIPT_PATH.exists(), f"Mock script not found at {MOCK_SCRIPT_PATH}"

    def test_mock_script_success_output(self) -> None:
        """Test that the script prints to stdout and exits with 0."""
        cmd = [
            sys.executable,
            str(MOCK_SCRIPT_PATH),
            "--folder-path",
            "/tmp/test_media",
            "--mock-stdout-lines",
            "2",
            "--mock-duration",
            "0.1",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        # Verify exit code
        assert result.returncode == 0

        # Verify stdout
        assert "[MOCK] Starting subtitle download" in result.stdout
        assert "[MOCK] Processing file 1/2..." in result.stdout
        assert "[MOCK] Download complete." in result.stdout

        # Verify stderr is empty (default)
        assert result.stderr == ""

    def test_mock_script_failure_behavior(self) -> None:
        """Test that the script produces stderr and non-zero exit code when asked."""
        cmd = [
            sys.executable,
            str(MOCK_SCRIPT_PATH),
            "--folder-path",
            "/tmp/test_media",
            "--mock-exit-code",
            "1",
            "--mock-stderr-lines",
            "1",
            "--mock-duration",
            "0.1",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        # Verify exit code
        assert result.returncode == 1

        # Verify stderr
        assert "[MOCK ERROR] Simulated error message 1" in result.stderr

    def test_mock_script_argument_parsing(self) -> None:
        """Test that the script accepts the required --folder-path argument."""
        # Run without required args
        cmd = [sys.executable, str(MOCK_SCRIPT_PATH)]
        result = subprocess.run(cmd, capture_output=True, text=True)

        assert result.returncode != 0
        assert "the following arguments are required: --folder-path" in result.stderr
