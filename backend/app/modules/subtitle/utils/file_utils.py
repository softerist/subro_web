import codecs  # For reading/writing with specific encodings like utf-8-sig
import logging
import os
import re  # For filename manipulation
import shutil
import tempfile
import zipfile  # Requires 'zipfile' - built-in
from collections import defaultdict  # For directory cleanup logic
from pathlib import Path  # Use pathlib for robustness

import chardet  # Requires 'chardet' package
import rarfile  # Requires 'rarfile' package and 'unrar' command-line tool

logger = logging.getLogger(__name__)

# Check rarfile availability and unrar command status once at module level
RARFILE_AVAILABLE = False
UNRAR_CMD_AVAILABLE = False
if rarfile:
    RARFILE_AVAILABLE = True
    try:
        # rarfile.tool_setup() # Deprecated
        # Instead, try listing a dummy file or check executable directly
        if shutil.which(rarfile.UNRAR_TOOL) or shutil.which("unrar"):
            UNRAR_CMD_AVAILABLE = True
            logger.debug("rarfile library imported and 'unrar' command seems available.")
        else:
            logger.warning(
                "rarfile library imported, but 'unrar' command not found in PATH. RAR extraction will fail."
            )
    except (
        AttributeError
    ):  # Handle case where UNRAR_TOOL might not be defined in older rarfile versions
        if shutil.which("unrar"):
            UNRAR_CMD_AVAILABLE = True
            logger.debug("rarfile library imported and 'unrar' command seems available.")
        else:
            logger.warning(
                "rarfile library imported, but 'unrar' command not found in PATH. RAR extraction will fail."
            )
    except Exception as rar_setup_e:
        logger.warning(f"Error during rarfile setup check: {rar_setup_e}. RAR extraction may fail.")


# --- Helper Functions ---
def get_preferred_subtitle_path(base_path_no_ext, language_code):
    """
    Generates the standard path for a subtitle file (using .srt).
    Removes existing language codes before appending the new one.
    """
    # Regex to remove existing .<lang>. or _<lang>_ or -<lang>- suffixes (2 or 3 letters)
    # before the (assumed) final extension placeholder
    base_path_cleaned = re.sub(r"[._-][a-zA-Z]{2,3}$", "", base_path_no_ext, flags=re.IGNORECASE)
    # Ensure language code is lower case
    lang_code_lower = language_code.lower()
    return f"{base_path_cleaned}.{lang_code_lower}.srt"


# --- Encoding Detection ---


def detect_encoding(file_path, default="utf-8"):
    """Detects the encoding of a file using chardet."""
    file_path_str = str(file_path)  # Ensure string path
    if not Path(file_path_str).exists():
        logging.error(f"Cannot detect encoding: File not found at {file_path_str}")
        return default
    try:
        with Path(file_path_str).open("rb") as file:
            # Read a significant chunk, but limit memory usage
            raw_data = file.read(128 * 1024)  # Read up to 128KB
        if not raw_data:  # Handle empty file
            logging.warning(
                f"File is empty, cannot detect encoding: {file_path_str}. Using default '{default}'."
            )
            return default

        result = chardet.detect(raw_data)
        encoding = result["encoding"]
        confidence = result["confidence"]

        # Use default for low confidence or None, but log it
        if encoding is None or confidence < 0.75:  # Slightly higher confidence threshold
            logging.debug(
                f"Chardet detected {encoding} with low confidence ({confidence:.2f}) for {Path(file_path_str).name}. Falling back to '{default}'."
            )
            return default
        # Handle common misdetections or aliases
        elif encoding.lower() == "ascii":
            logging.debug(f"Chardet detected ASCII for {Path(file_path_str).name}, using 'utf-8'.")
            return "utf-8"
        elif encoding.lower() == "iso-8859-1":
            # Often interchangeable with Windows-1252, but 1252 is more common for subs
            logging.debug(
                f"Chardet detected ISO-8859-1 for {Path(file_path_str).name}, trying 'cp1252'."
            )
            return "cp1252"
        elif encoding.lower() == "windows-1252":
            return "cp1252"  # Standardize to cp1252 alias
        else:
            logging.debug(
                f"Detected encoding: {encoding} with confidence {confidence:.2f} for {Path(file_path_str).name}"
            )
            return encoding

    except FileNotFoundError:  # Should be caught above, but defensive
        logging.error(f"File not found during encoding detection: {file_path_str}")
        return default
    except Exception as e:
        logging.warning(
            f"Could not detect encoding for {file_path_str} due to error: {e}. Falling back to '{default}'."
        )
        return default


# --- File Reading/Writing ---


def read_srt_file(file_path: str) -> str:
    """Reads an SRT file using detected encoding, falling back to common encodings."""
    file_path_str = str(file_path)  # Ensure string path
    if not Path(file_path_str).exists():
        logging.error(f"Cannot read SRT: File not found at {file_path_str}")
        raise FileNotFoundError(f"SRT file not found: {file_path_str}")
    if Path(file_path_str).stat().st_size == 0:
        logging.warning(f"SRT file is empty: {file_path_str}")
        return ""  # Return empty string for empty file

    initial_encoding = detect_encoding(file_path_str)
    # List of encodings to try in order
    encodings_to_try = [
        initial_encoding,
        "utf-8",
        "utf-8-sig",  # Try with BOM handling
        "cp1252",  # Common Windows encoding for Western/Central Europe
        "cp1250",  # Common Windows encoding for Central/Eastern Europe
        "iso-8859-2",  # Latin-2, alternative for Central/Eastern Europe
    ]
    # Remove duplicates while preserving order (ish)
    tried_encodings = set()
    unique_encodings = []
    for enc in encodings_to_try:
        if enc and enc not in tried_encodings:
            unique_encodings.append(enc)
            tried_encodings.add(enc)

    for encoding in unique_encodings:
        try:
            with codecs.open(
                file_path_str, "r", encoding=encoding, errors="strict"
            ) as file:  # Use 'strict' first
                content = file.read()
            # Remove BOM manually if necessary (though utf-8-sig should handle it)
            if content.startswith("\ufeff"):
                content = content[1:]
            logging.debug(
                f"Successfully read {len(content)} chars from {Path(file_path_str).name} using encoding '{encoding}'."
            )
            return content
        except UnicodeDecodeError:
            logging.debug(
                f"Read failed for {Path(file_path_str).name} with encoding '{encoding}' (strict)."
            )
            # Optionally try again with 'replace' or 'ignore' errors?
            # For now, just move to the next encoding.
            continue
        except Exception as e:
            logging.warning(
                f"Unexpected error reading {Path(file_path_str).name} with encoding '{encoding}': {e}"
            )
            # Continue trying other encodings unless it's a fundamental error

    # If all attempts fail
    logging.error(
        f"Failed to read SRT file {Path(file_path_str).name} with any attempted encoding: {unique_encodings}. Corrupted file or unknown encoding?"
    )
    raise OSError(f"Could not read file {file_path_str} with attempted encodings.")


def write_srt_file(file_path: str, content: str) -> None:
    """Writes content to an SRT file using UTF-8 with BOM encoding."""
    file_path_str = str(file_path)  # Ensure string path
    try:
        # Ensure the directory exists using pathlib
        Path(file_path_str).parent.mkdir(parents=True, exist_ok=True)

        # Write with utf-8-sig to include BOM (Byte Order Mark)
        with codecs.open(file_path_str, "w", encoding="utf-8-sig") as file:
            # Ensure consistent line endings (replace \r\n and \r with \n)
            content_normalized = content.replace("\r\n", "\n").replace("\r", "\n")
            file.write(content_normalized)
        logging.debug(
            f"Successfully wrote {len(content)} chars to {Path(file_path_str).name} (UTF-8 w/ BOM)."
        )
    except Exception as e:
        logging.error(f"Error writing SRT file {file_path_str}: {e}", exc_info=True)
        raise  # Re-raise error to signal failure


# --- Archive Extraction ---


def extract_archive(archive_path, target_dir):  # noqa: C901
    """Extracts zip or rar archives to the target directory."""
    archive_path_str = str(archive_path)  # Ensure string path
    target_dir_str = str(target_dir)  # Ensure string path

    if not Path(archive_path_str).exists():
        logging.error(f"Cannot extract: Archive file not found at {archive_path_str}")
        return False

    # Ensure target directory exists
    try:
        Path(target_dir_str).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logging.error(f"Failed to create target directory {target_dir_str}: {e}")
        return False

    extracted = False
    archive_basename = Path(archive_path_str).name
    logging.info(f"Attempting to extract archive: {archive_basename} to {target_dir_str}")

    try:
        if zipfile.is_zipfile(archive_path_str):
            try:
                with zipfile.ZipFile(archive_path_str, "r") as zip_ref:
                    # Security: Check for potentially malicious paths (e.g., absolute paths, '..')
                    # This is a basic check; more robust libraries might exist for this.
                    for member in zip_ref.infolist():
                        member_path = (Path(target_dir_str) / member.filename).resolve()
                        if not str(member_path).startswith(str(Path(target_dir_str).resolve())):
                            raise zipfile.BadZipFile(
                                f"Malicious path detected in zip file: {member.filename}"
                            )
                    # If checks pass, extract
                    zip_ref.extractall(target_dir_str)
                logging.info(f"Extracted ZIP archive: {archive_basename}")
                extracted = True
            except zipfile.BadZipFile as e:
                logging.error(f"Error extracting ZIP {archive_basename}: {e}")
            except Exception as e:  # Catch other potential zipfile errors
                logging.error(f"Unexpected error extracting ZIP {archive_basename}: {e}")

        elif RARFILE_AVAILABLE and rarfile.is_rarfile(archive_path_str):
            if not UNRAR_CMD_AVAILABLE:
                logging.error(
                    f"Cannot extract RAR {archive_basename}: 'unrar' command unavailable."
                )
                return False
            try:
                with rarfile.RarFile(archive_path_str, "r") as rar_ref:
                    # Security considerations for RAR are less standardized than ZIP
                    # Assume rarfile handles basic path safety or accept the risk for now
                    rar_ref.extractall(target_dir_str)
                logging.info(f"Extracted RAR archive: {archive_basename}")
                extracted = True
            except rarfile.NeedFirstVolume:
                logging.warning(
                    f"Skipping multi-volume RAR part: {archive_basename} (needs first volume)"
                )
            except rarfile.BadRarFile as e:
                logging.error(f"Error extracting RAR {archive_basename}: Bad RAR file format. {e}")
            except rarfile.RarCannotExec as e:
                # Should be caught by UNRAR_CMD_AVAILABLE check, but double-check
                logging.error(f"Error executing 'unrar' for {archive_basename}: {e}.")
            except Exception as e:  # Catch other potential rarfile errors
                logging.error(f"Error extracting RAR {archive_basename}: {e}")
        else:
            if archive_path_str.lower().endswith(".rar") and not RARFILE_AVAILABLE:
                logging.warning(
                    f"Skipping RAR archive {archive_basename}: 'rarfile' library not installed."
                )
            else:
                logging.warning(f"File is not a recognized ZIP or RAR archive: {archive_basename}")

    except FileNotFoundError:
        logging.error(f"Archive file disappeared during extraction: {archive_path_str}")
    except Exception as e:
        logging.error(f"Failed to extract archive {archive_basename}: {e}", exc_info=True)

    return extracted


# --- Directory/File Manipulation & Cleanup ---


def clean_temp_directory(temp_dir_path):
    """Safely removes a temporary directory and its contents."""
    if temp_dir_path and Path(temp_dir_path).exists() and Path(temp_dir_path).is_dir():
        # Check if path is within expected temp locations (optional safety)
        is_temp = temp_dir_path.startswith(tempfile.gettempdir()) or Path(
            temp_dir_path
        ).name.startswith(("subsync_", "sub_extract_", "subsro_", "opensubs_"))
        if not is_temp:
            logging.warning(
                f"Attempting to clean directory outside expected temp locations: {temp_dir_path}. Skipping."
            )
            return

        try:
            shutil.rmtree(temp_dir_path)
            logging.debug(f"Removed temporary directory: {temp_dir_path}")
        except Exception as e:
            logging.error(f"Failed to remove temporary directory {temp_dir_path}: {e}")
    else:
        logging.debug(f"Temporary directory does not exist or is invalid: {temp_dir_path}")


def find_project_root(start_path, markers=(".git", "src", "config", "requirements.txt")):
    """Finds the project root directory by searching upwards for common markers."""
    current_path = Path(start_path).resolve()
    while True:
        # Check if any marker exists in the current directory
        if any((current_path / marker).exists() for marker in markers):
            logging.debug(f"Project root identified at: {current_path} (found marker)")
            return current_path
        parent_path = current_path.parent
        if parent_path == current_path:
            # Reached the filesystem root without finding the marker
            logging.warning(
                f"Could not find project root marker {markers}. Using start path '{start_path}' directory as fallback."
            )
            return Path(start_path).resolve()  # Fallback to starting point's directory
        current_path = parent_path


def remove_unmatched_subtitles(target_dir, processed_subtitle_paths):
    """
    Removes subtitle files (.srt, .sub, .ass) from a directory (recursively)
    that were not successfully processed/moved out. Used for cleaning temp dirs.

    Args:
        target_dir (str): The directory to clean.
        processed_subtitle_paths (set): A set of full paths to subtitle files that
                                         were handled (paths as they were in temp dir).
    """
    target_dir_str = str(target_dir)  # Ensure string path
    if not Path(target_dir_str).is_dir():
        logging.warning(f"Cannot clean unmatched subtitles: Directory not found: {target_dir_str}")
        return

    logging.info(f"Cleaning unmatched subtitle files from temporary directory: {target_dir_str}")
    removed_count = 0
    files_to_check = []
    try:
        # Use pathlib for walking
        for item in Path(target_dir_str).rglob("*"):
            if item.is_file():
                files_to_check.append(str(item))  # Store as string path
    except Exception as e:
        logging.error(f"Error walking directory {target_dir_str} for cleanup: {e}")
        return  # Abort cleanup if walk fails

    # Normalize paths in the processed set for comparison
    normalized_processed_paths = {os.path.normpath(p) for p in processed_subtitle_paths}

    for file_path in files_to_check:
        filename = Path(file_path).name
        # Check common subtitle extensions, ignore backups
        if filename.lower().endswith((".srt", ".sub", ".ass")) and not filename.lower().endswith(
            (".bak", ".syncbak")
        ):
            # Normalize the path being checked
            normalized_file_path = os.path.normpath(file_path)
            if normalized_file_path not in normalized_processed_paths:
                try:
                    Path(file_path).unlink()
                    logging.debug(f"Removed unmatched temp subtitle file: {file_path}")
                    removed_count += 1
                except OSError as e:
                    logging.error(f"Error removing unmatched temp subtitle {file_path}: {e}")

    logging.info(f"Removed {removed_count} unmatched subtitle files from {target_dir_str}.")


def cleanup_target_directory(  # noqa: C901
    target_dir, video_extensions=(".mkv", ".mp4", ".avi", ".mov", ".wmv")
):  # TO BE ALLIGNED WITH from app.modules.subtitle.core.constants import VIDEO_EXTENSIONS
    """
    Performs final cleanup on the main media directory:
    1. Removes subtitle files (.lang.srt, etc.) without a matching video file.
    2. Removes empty subdirectories recursively.

    Args:
        target_dir (str): The main directory where media and final subtitles reside.
        video_extensions (tuple): Tuple of lower-case video file extensions.
    """
    target_dir_path = Path(target_dir).resolve()  # Use pathlib
    if not target_dir_path.is_dir():
        logging.warning(f"Cannot perform final cleanup: Directory not found: {target_dir_path}")
        return

    logging.info(f"Performing final cleanup (orphaned subs, empty dirs) in: {target_dir_path}")
    removed_subs_count = 0
    removed_dirs_count = 0
    video_extensions_lower = tuple(ext.lower() for ext in video_extensions)  # Ensure lower case

    # --- Remove orphaned subtitles ---
    video_basenames_in_dirs = defaultdict(
        set
    )  # { Path('/path/to/dir'): {'basename1', 'basename2'} }
    try:
        # First pass: collect all video basenames per directory
        for item in target_dir_path.rglob("*"):
            if item.is_file() and item.suffix.lower() in video_extensions_lower:
                basename = item.stem  # Basename without extension
                video_basenames_in_dirs[item.parent].add(basename)
    except Exception as e:
        logging.error(f"Error scanning for video files during cleanup in {target_dir_path}: {e}")
        # Proceed cautiously

    # Second pass: check subtitles against video basenames in the same directory
    all_files = []
    try:
        for item in target_dir_path.rglob("*"):
            if item.is_file():
                all_files.append(item)  # Store Path objects
    except Exception as e:
        logging.error(f"Error walking directory for subtitle cleanup in {target_dir_path}: {e}")
        all_files = []  # Abort subtitle cleanup part

    # Regex to match standard subtitle format: basename.lang.ext
    sub_pattern = re.compile(r"^(.*)\.([a-zA-Z]{2,3})\.(srt|sub|ass)$", re.IGNORECASE)
    for file_path in all_files:  # file_path is a Path object
        match = sub_pattern.match(file_path.name)
        if match:
            sub_basename = match.group(1)  # Basename without lang/ext
            parent_dir = file_path.parent
            # Check if the corresponding video basename exists in that specific directory
            if sub_basename not in video_basenames_in_dirs.get(parent_dir, set()):
                try:
                    file_path.unlink()  # Use pathlib's unlink for removal
                    logging.info(
                        f"Removed orphaned subtitle: {file_path} (no matching video found in dir)"
                    )
                    removed_subs_count += 1
                except OSError as e:
                    logging.error(f"Error removing orphaned subtitle {file_path}: {e}")

    # --- Remove empty directories ---
    # Walk bottom-up to remove empty subdirs first
    try:
        for root, dirs, _ in os.walk(str(target_dir_path), topdown=False):
            for dirname in dirs:
                dir_path = Path(root) / dirname
                try:
                    # Check if directory is empty
                    if not any(dir_path.iterdir()):  # Check if iterator is empty
                        dir_path.rmdir()  # Use pathlib's rmdir
                        logging.info(f"Removed empty directory: {dir_path}")
                        removed_dirs_count += 1
                except FileNotFoundError:
                    logging.debug(
                        f"Directory {dir_path} was already removed."
                    )  # Skip if removed between checks
                except OSError as e:
                    # Log error but continue, maybe dir became non-empty or permissions issue
                    logging.warning(
                        f"Could not remove directory {dir_path} (may not be empty or permission issue): {e}"
                    )
    except Exception as e:
        logging.error(f"Error walking directories for empty dir cleanup in {target_dir_path}: {e}")

    logging.info(
        f"Final cleanup complete. Removed {removed_subs_count} orphaned subtitles and {removed_dirs_count} empty directories."
    )


# --- Explicit Exports ---
__all__ = [
    "clean_temp_directory",
    "cleanup_target_directory",
    "detect_encoding",
    "extract_archive",
    "find_project_root",
    "get_preferred_subtitle_path",
    "read_srt_file",
    "remove_unmatched_subtitles",
    "write_srt_file",
]
