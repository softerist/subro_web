import io
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path  # Use pathlib

# Import config safely
try:
    from app.core.config import settings
except ImportError:
    # Create a dummy settings object with defaults
    class DummySettings:
        FFSUBSYNC_PATH = "ffsubsync"
        ALASS_CLI_PATH = "alass-cli"
        FFMPEG_PATH = "ffmpeg"
        SUBTITLE_SYNC_OFFSET_THRESHOLD = 1.0
        FFSUBSYNC_TIMEOUT = 180
        ALASS_TIMEOUT = 300
        FFSUBSYNC_CHECK_TIMEOUT = 600

    settings = DummySettings()  # type: ignore[assignment, no-redef]
    logging.warning("Could not import config. Using default sync tool paths/timeouts.")

# Import file utils safely
try:
    # Use relative import if part of the same package
    from .file_utils import clean_temp_directory
except ImportError:
    # Fallback to absolute import
    try:
        from app.modules.subtitle.utils.file_utils import clean_temp_directory
    except (ImportError, ModuleNotFoundError):
        logging.critical(
            "Failed to import clean_temp_directory from file_utils. Sync cleanup may fail."
        )

        # Define dummy function
        def clean_temp_directory(_temp_dir_path: str | None) -> None:  # type: ignore[misc]
            pass


logger = logging.getLogger(__name__)

# --- Configuration ---
FFSUBSYNC_PATH = getattr(settings, "FFSUBSYNC_PATH", "ffsubsync")
ALASS_CLI_PATH = getattr(settings, "ALASS_CLI_PATH", "alass-cli")
FFMPEG_PATH = getattr(settings, "FFMPEG_PATH", "ffmpeg")
OFFSET_THRESHOLD = getattr(settings, "SUBTITLE_SYNC_OFFSET_THRESHOLD", 1.0)

# Load timeouts from settings with defaults
FFSUBSYNC_TIMEOUT = getattr(settings, "FFSUBSYNC_TIMEOUT", 300)
ALASS_TIMEOUT = getattr(settings, "ALASS_TIMEOUT", 300)
FFSUBSYNC_CHECK_TIMEOUT = getattr(settings, "FFSUBSYNC_CHECK_TIMEOUT", 600)

# --- Helper: Check Tool Availability ---
# Module-level cache dictionary for tool availability (replaces globals() usage)
_tool_cache: dict[str, bool | None] = {}


def _is_tool_available(tool_path: str, tool_name: str) -> bool:
    """Checks if an external tool exists and is executable (cached)."""
    cache_key = f"{tool_name}|{tool_path}"  # Unique key per tool name and path

    # Check cache first
    if cache_key in _tool_cache:
        return _tool_cache[cache_key] or False

    is_available = False  # Default if not found
    resolved_path = shutil.which(tool_path)
    if resolved_path:
        try:
            # Check if it's a file and executable (best effort)
            if Path(resolved_path).is_file() and (
                os.name == "nt" or os.access(resolved_path, os.X_OK)
            ):
                is_available = True
                logging.debug(
                    f"Tool '{tool_name}' ({tool_path}) found and seems executable at '{resolved_path}'"
                )
            elif Path(resolved_path).is_file():
                is_available = True  # Assume executable if check fails/not applicable
                logging.warning(
                    f"Tool '{tool_name}' ({tool_path}) found at '{resolved_path}' but OS executable check failed/skipped."
                )
            else:
                is_available = False
                logging.warning(
                    f"Tool '{tool_name}' ({tool_path}) resolved to '{resolved_path}' but it's not a file."
                )
        except OSError as e:
            is_available = False
            logging.warning(f"Error checking executable status for '{resolved_path}': {e}")
    else:
        is_available = False
        # Log as warning only if the tool is explicitly configured, otherwise debug
        configured_path = getattr(settings, f"{tool_name.replace('-', '_').upper()}_PATH", None)
        if configured_path == tool_path:  # Check if it's the configured path
            logging.warning(
                f"Tool '{tool_name}' ({tool_path}) not found in system PATH or configured path."
            )
        else:  # Tool path was default, might not be intended for use
            logging.debug(f"Tool '{tool_name}' ({tool_path}) not found. (Using default path).")

    # Update cache
    _tool_cache[cache_key] = is_available
    return is_available


# --- Synchronization Functions ---


def check_offset_with_ffsubsync(video_file: str, subtitle_file: str) -> float | None:  # noqa: C901
    """
    Uses ffsubsync to estimate the offset between video audio and subtitles.
    Parses standard output for offset info. Uses FFSUBSYNC_CHECK_TIMEOUT.

    Args:
        video_file (str): Path to the video file.
        subtitle_file (str): Path to the subtitle file.

    Returns:
        float or None: The detected offset in seconds, or None if detection fails.
                       Returns 0.0 if no significant offset is detected by the tool.
    """
    video_path = Path(video_file).resolve()
    sub_path = Path(subtitle_file).resolve()

    if not _is_tool_available(FFSUBSYNC_PATH, "ffsubsync"):
        logging.error(f"Cannot check subtitle offset: '{FFSUBSYNC_PATH}' tool unavailable.")
        return None
    # Check if ffmpeg is needed and available (ffsubsync relies on it)
    if not _is_tool_available(FFMPEG_PATH, "ffmpeg"):
        logging.error(
            f"Cannot check subtitle offset: '{FFMPEG_PATH}' (dependency for ffsubsync) unavailable."
        )
        return None

    if not video_path.is_file():
        logging.error(f"Cannot check offset: Video file not found: {video_path}")
        return None
    if not sub_path.is_file() or sub_path.stat().st_size == 0:
        logging.error(f"Cannot check offset: Subtitle file not found or empty: {sub_path}")
        return None

    video_basename = video_path.name
    sub_basename = sub_path.name
    logging.info(f"Checking subtitle offset for '{sub_basename}' with video '{video_basename}'...")
    start_time = time.monotonic()
    offset = None  # Default to None (failure)

    try:
        # Run ffsubsync without --check-only, parse output for offset
        command = [
            FFSUBSYNC_PATH,
            str(video_path),
            "-i",
            subtitle_file,
            # '--max-offset-seconds', '60', # Limit search range
            "--reference-stream",
            "audio",
            # '--no-fix-framerate',
            # '--gss-num-workers=1',
        ]
        # Add optional arguments if needed (e.g., for debugging or performance)
        # command.extend(['--log-level', 'debug'])
        # command.extend(['--max-offset-seconds', '60'])
        # command.extend(['--gss-num-workers', '1']) # Limit workers if causing issues

        logging.debug(f"Running command: {' '.join(command)}")
        check_timeout = FFSUBSYNC_CHECK_TIMEOUT
        logging.debug(f"Using offset check timeout: {check_timeout} seconds")

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,  # Don't raise on error, check manually
            encoding="utf-8",
            errors="replace",
            timeout=check_timeout,  # Apply specific check timeout
        )
        # Combine stdout and stderr for parsing
        output = result.stdout + "\n" + result.stderr
        logging.debug(f"ffsubsync offset check exit code: {result.returncode}")
        # Log more output for debugging failures
        if result.returncode != 0 or "shifting subtitles by" not in output.lower():
            logging.debug(
                f"ffsubsync offset check output:\n{output[:3000]}..."
            )  # Log more on potential failure

        # Parse offset from standard sync output patterns
        # Look for "shifting subtitles by [number] seconds"
        offset_match = re.search(
            r"shifting subtitles by\s*([-+]?\d*\.?\d+)\s*seconds", output, re.IGNORECASE
        )

        if offset_match:
            offset = float(offset_match.group(1))
            logging.info(f"Detected offset via ffsubsync output: {offset:.3f} seconds.")
        else:
            # If command finished with non-zero code and no offset found -> Failure
            if result.returncode != 0:
                logging.error(
                    f"ffsubsync offset check command failed (exit code {result.returncode}) and no offset info found in output."
                )
                offset = None  # Ensure failure state
            # If command finished with zero code and no offset found -> Assume 0.0 offset
            else:
                logging.info(
                    "No offset shift message detected in ffsubsync output (assuming 0.0s)."
                )
                offset = 0.0

    except subprocess.TimeoutExpired:
        logging.error(
            f"ffsubsync offset check timed out after {check_timeout} seconds for '{sub_basename}'."
        )
        offset = None
    except FileNotFoundError:
        logging.error(f"'{FFSUBSYNC_PATH}' command not found during execution.")
        _ffsubsync_available = False  # Update cache
        offset = None
    except Exception as e:
        logging.error(
            f"Error checking offset with ffsubsync for '{sub_basename}': {e}", exc_info=True
        )
        offset = None
    finally:
        duration = time.monotonic() - start_time
        logging.debug(f"Offset check for '{sub_basename}' took {duration:.2f} seconds.")

    return offset


def _run_sync_tool(command: list[str], tool_name: str, timeout_seconds: int | None) -> bool:  # noqa: C901
    """Helper to run a synchronization command, log output, handle timeout."""
    try:
        logging.debug(f"Running command: {' '.join(command)}")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Redirect stderr to stdout
        )

        output_lines = []
        start_time = time.monotonic()
        last_log_time = start_time

        stdout_text = None
        try:
            if process.stdout is None:
                raise RuntimeError(f"{tool_name} stdout pipe was not created.")
            stdout_text = io.TextIOWrapper(
                process.stdout,
                encoding="utf-8",
                errors="replace",
                newline="",
            )

            while True:
                line = ""
                # Check if process finished
                process_poll = process.poll()
                if process_poll is not None:  # Process has finished
                    # Read any remaining output
                    remaining_output = stdout_text.read()
                    if remaining_output:
                        lines = remaining_output.splitlines()
                        for line in lines:
                            if line.strip():
                                output_lines.append(line.strip())
                    break  # Exit loop

                # Read output line if available
                try:
                    line = stdout_text.readline()
                except Exception as read_err:
                    logging.warning(f"Error reading stdout from {tool_name}: {read_err}")
                    # Break or continue? Let's break if reading fails consistently.
                    if process.poll() is None:  # Check if process died unexpectedly
                        time.sleep(0.5)
                        if process.poll() is None:
                            logging.error(
                                f"{tool_name} stdout reading error, process may be stuck. Terminating."
                            )
                            process.terminate()
                            time.sleep(0.5)
                            process.kill()
                            process.wait()
                            return False  # Indicate failure
                    break  # Assume process ended or reading is broken

                if line:
                    line_strip = line.strip()
                    if line_strip:  # Avoid logging empty lines excessively
                        output_lines.append(line_strip)
                        # Log progress lines or other notable output
                        # Be careful not to log too verbosely here
                        if (
                            tool_name == "alass"
                            and "INFO" in line_strip.upper()
                            and "%" in line_strip
                        ) or (tool_name == "ffsubsync" and "syncing segment" in line_strip.lower()):
                            current_time = time.monotonic()
                            # Throttle progress logging
                            if current_time - last_log_time > 2.0:
                                logging.info(f"[{tool_name}-progress] {line_strip}")
                                last_log_time = current_time
                        # else: logging.debug(f"[{tool_name}-output] {line_strip}") # Very verbose

                # Check for timeout
                if timeout_seconds and (time.monotonic() - start_time) > timeout_seconds:
                    logging.error(
                        f"{tool_name} synchronization timed out after {timeout_seconds} seconds."
                    )
                    process.terminate()
                    # Give it a moment to terminate gracefully
                    try:
                        process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        logging.warning(
                            f"{tool_name} process did not terminate gracefully, killing."
                        )
                        process.kill()
                    process.wait()  # Wait for kill
                    raise subprocess.TimeoutExpired(command, timeout_seconds)

                if not line and process.poll() is None:  # No output but process still running
                    time.sleep(0.1)  # Prevent tight loop consuming CPU
        finally:
            if stdout_text is not None:
                stdout_text.close()

        # After loop, check final return code
        returncode = process.returncode
        if returncode != 0:
            logging.error(f"{tool_name} failed with exit code: {returncode}")
            # Log last ~15 lines of output for context
            logging.error(f"Last output lines from {tool_name}:\n" + "\n".join(output_lines[-15:]))
        return returncode == 0

    except FileNotFoundError:
        logging.error(
            f"'{command[0]}' command not found for {tool_name}. Ensure it's installed and configured."
        )
        # Update cache to mark tool as unavailable
        cache_key = f"{tool_name}|{command[0]}"
        if cache_key not in _tool_cache:
            _tool_cache[cache_key] = False
        return False
    except subprocess.TimeoutExpired:
        return False  # Already logged
    except Exception as e:
        logging.error(
            f"An unexpected error occurred running {tool_name} command '{' '.join(command)}': {e}",
            exc_info=True,
        )
        return False


def sync_with_alass(video_file: str, subtitle_file: str, synced_output_path: str) -> bool:
    """Attempts to synchronize subtitles using alass-cli."""
    if not _is_tool_available(ALASS_CLI_PATH, "alass-cli"):
        logging.warning(f"Skipping alass sync: '{ALASS_CLI_PATH}' tool unavailable.")
        return False
    # alass also needs ffmpeg
    if not _is_tool_available(FFMPEG_PATH, "ffmpeg"):
        logging.error(f"Cannot use alass: '{FFMPEG_PATH}' (dependency) unavailable.")
        return False

    video_p = Path(video_file)
    sub_p = Path(subtitle_file)
    output_p = Path(synced_output_path)

    if not video_p.is_file():
        logging.error(f"alass: Video not found {video_p}")
        return False
    if not sub_p.is_file():
        logging.error(f"alass: Subtitle not found {sub_p}")
        return False

    logging.info("Attempting subtitle sync with alass-cli...")
    command = [ALASS_CLI_PATH, str(video_p), str(sub_p), str(output_p)]
    return _run_sync_tool(command, "alass", ALASS_TIMEOUT)


def sync_with_ffsubsync(video_file: str, subtitle_file: str, synced_output_path: str) -> bool:
    """Attempts to synchronize subtitles using ffsubsync."""
    if not _is_tool_available(FFSUBSYNC_PATH, "ffsubsync"):
        logging.warning(f"Skipping ffsubsync sync: '{FFSUBSYNC_PATH}' tool unavailable.")
        return False
    # ffsubsync also needs ffmpeg
    if not _is_tool_available(FFMPEG_PATH, "ffmpeg"):
        logging.error(f"Cannot use ffsubsync: '{FFMPEG_PATH}' (dependency) unavailable.")
        return False

    video_p = Path(video_file)
    sub_p = Path(subtitle_file)
    output_p = Path(synced_output_path)

    if not video_p.is_file():
        logging.error(f"ffsubsync: Video not found {video_p}")
        return False
    if not sub_p.is_file():
        logging.error(f"ffsubsync: Subtitle not found {sub_p}")
        return False

    logging.info("Attempting subtitle sync with ffsubsync...")
    command = [
        FFSUBSYNC_PATH,
        str(video_p),
        "-i",
        str(sub_p),
        "-o",
        str(output_p),
        # Consider adding/removing optional args based on performance/accuracy needs
        # '--max-offset-seconds', '60', # Limit search range? Default is 300
        # '--vad', 'google', # Use google VAD if installed? (pip install webrtcvad-wheels)
    ]
    # Use the FULL sync timeout here
    return _run_sync_tool(command, "ffsubsync", FFSUBSYNC_TIMEOUT)


def sync_subtitles_with_audio(video_file_path: str, subtitle_file_path: str) -> str:  # noqa: C901
    """
    Synchronizes a subtitle file with the audio of a video file.
    Checks offset first, then tries alass, then ffsubsync as fallback.
    Overwrites the original subtitle file on success.

    Args:
        video_file_path (str): Path to the video file.
        subtitle_file_path (str): Path to the subtitle file to sync.

    Returns:
        str: The path to the synchronized subtitle file (the original path).
             Content is modified in-place if sync is successful.
    """
    sub_path = Path(subtitle_file_path).resolve()
    video_path = Path(video_file_path).resolve()
    sub_basename = sub_path.name

    if not video_path.is_file():
        logging.error(f"Sync failed for '{sub_basename}': Video file not found at {video_path}")
        return str(sub_path)  # Return original path string
    if not sub_path.is_file():
        logging.error(f"Sync failed for '{sub_basename}': Subtitle file not found at {sub_path}")
        return str(sub_path)  # Return original path string
    if sub_path.stat().st_size == 0:
        logging.warning(f"Sync skipped for '{sub_basename}': Subtitle file is empty.")
        return str(sub_path)

    logging.info(f"Starting subtitle synchronization process for '{sub_basename}'")

    # 1. Check offset
    offset = check_offset_with_ffsubsync(str(video_path), str(sub_path))
    perform_sync = True  # Default to performing sync unless offset is small

    if offset is not None:  # Offset check completed (successfully or returned 0.0)
        if abs(offset) < OFFSET_THRESHOLD:
            logging.info(
                f"Subtitle offset ({offset:.3f}s) within threshold ({OFFSET_THRESHOLD}s). Sync not required for '{sub_basename}'."
            )
            perform_sync = False
        else:  # Offset exceeds threshold
            logging.info(
                f"Initial offset {offset:.3f}s exceeds threshold ({OFFSET_THRESHOLD}s) for '{sub_basename}'. Proceeding with sync."
            )
    else:  # Offset check failed (returned None)
        logging.warning(
            f"Failed to determine initial offset for '{sub_basename}'. Proceeding with sync attempt."
        )
        # perform_sync remains True

    if not perform_sync:
        logging.info(f"Synchronization skipped based on offset check for '{sub_basename}'.")
        return str(sub_path)  # Return original path string

    # 2. Prepare for sync attempts
    temp_dir = None
    synced_temp_path = None
    success = False
    sync_tool_used = "None"
    start_time = time.monotonic()

    try:
        # Create temporary file in the same directory as original subtitle for permissions/move reliability
        temp_dir = Path(tempfile.mkdtemp(prefix="subsync_", dir=sub_path.parent))
        base, ext = sub_path.stem, sub_path.suffix  # Use stem for name without extension
        synced_temp_path = temp_dir / f"{base}_synced_temp{ext}"

        # 3. Try alass first
        if _is_tool_available(ALASS_CLI_PATH, "alass-cli"):
            if sync_with_alass(str(video_path), str(sub_path), str(synced_temp_path)):
                success = True
                sync_tool_used = "alass-cli"
                logging.info(f"Synchronization successful using alass-cli for '{sub_basename}'.")
            else:
                logging.warning(f"alass-cli sync failed for '{sub_basename}'. Will try fallback.")
                if synced_temp_path.exists():  # Clean up failed output
                    try:
                        synced_temp_path.unlink()
                    except OSError:
                        pass
        else:
            logging.debug("alass-cli not available, skipping.")

        # 4. Try ffsubsync as fallback
        if not success and _is_tool_available(FFSUBSYNC_PATH, "ffsubsync"):
            if sync_with_ffsubsync(str(video_path), str(sub_path), str(synced_temp_path)):
                success = True
                sync_tool_used = "ffsubsync"
                logging.info(f"Synchronization successful using ffsubsync for '{sub_basename}'.")
            else:
                logging.warning(f"ffsubsync sync also failed for '{sub_basename}'.")
                if synced_temp_path.exists():  # Clean up failed output
                    try:
                        synced_temp_path.unlink()
                    except OSError:
                        pass
        elif not success:
            logging.debug("ffsubsync not available or not needed, skipping.")

        # 5. Replace original file if sync succeeded
        if success and synced_temp_path.exists() and synced_temp_path.stat().st_size > 10:
            backup_path = None
            try:
                # Create backup in the same directory
                backup_path = sub_path.with_suffix(sub_path.suffix + ".syncbak")
                # Only backup if it doesn't already exist to avoid overwriting a previous backup
                if not backup_path.exists():
                    shutil.copy2(str(sub_path), str(backup_path))  # Use str() for shutil
                    logging.debug(f"Created backup of original subtitle: {backup_path.name}")

                # Use replace for atomic move where possible
                shutil.move(str(synced_temp_path), str(sub_path))  # Use str() for shutil
                logging.info(
                    f"Replaced original subtitle with synced version: {sub_path.name} (using {sync_tool_used})"
                )

                # Remove backup on successful move
                if backup_path and backup_path.exists():
                    try:
                        backup_path.unlink()
                        logging.debug(f"Removed sync backup: {backup_path.name}")
                    except OSError as remove_err:
                        logging.warning(f"Could not remove sync backup {backup_path}: {remove_err}")

            except Exception as e:
                logging.error(
                    f"Error replacing original subtitle '{sub_basename}' with synced version: {e}"
                )
                # Attempt to restore backup if replacement failed? Risky.
                success = False  # Mark overall as failed if replacement step fails
                if backup_path and backup_path.exists() and not sub_path.exists():
                    try:
                        logging.warning(
                            f"Attempting to restore backup file '{backup_path.name}'..."
                        )
                        shutil.move(str(backup_path), str(sub_path))
                    except Exception as restore_err:
                        logging.error(f"Failed to restore backup file: {restore_err}")

        elif success:  # Tool reported success but output is bad
            logging.error(
                f"Sync tool ({sync_tool_used}) reported success for '{sub_basename}', but synced output file is missing or empty!"
            )
            success = False  # Mark as failed overall
        else:  # Both tools failed or weren't available
            logging.error(
                f"Subtitle synchronization failed using all available methods for '{sub_basename}'."
            )

    except Exception as e:
        logging.error(
            f"Unexpected error during sync process for '{sub_basename}': {e}", exc_info=True
        )
        success = False  # Ensure success flag is false on unexpected error
    finally:
        # Use the imported cleanup utility
        if temp_dir:
            clean_temp_directory(str(temp_dir))
        duration = time.monotonic() - start_time
        logging.info(
            f"Subtitle synchronization process for '{sub_basename}' finished in {duration:.2f} seconds. Success: {success}"
        )

    return str(sub_path)  # Always return the original path name (as string)


# --- Explicit Exports ---
__all__ = [
    "check_offset_with_ffsubsync",
    "sync_subtitles_with_audio",
]
