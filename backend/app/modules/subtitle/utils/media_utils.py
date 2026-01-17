import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# --- Imports and Setup ---
# Import configuration from app.core.config (Pydantic settings)
from app.core.config import settings
from app.modules.subtitle.core import constants
from app.modules.subtitle.utils import file_utils, subtitle_parser

logger = logging.getLogger(__name__)

# --- Configuration ---
# Use separate settings for ffmpeg and ffprobe if available, otherwise derive from ffmpeg
FFMPEG_PATH = getattr(settings, "FFMPEG_PATH", "ffmpeg")
FFPROBE_PATH = getattr(
    settings,
    "FFPROBE_PATH",
    FFMPEG_PATH.replace("ffmpeg", "ffprobe") if "ffmpeg" in FFMPEG_PATH else "ffprobe",
)
SUP2SRT_PATH = getattr(settings, "SUP2SRT_PATH", "sup2srt")
SUP2SRT_TIMEOUT = getattr(settings, "SUP2SRT_TIMEOUT", 400)
FFPROBE_TIMEOUT = getattr(settings, "FFPROBE_TIMEOUT", 60)
FFMPEG_TIMEOUT = getattr(settings, "FFMPEG_TIMEOUT", 180)

# --- Define subtitle codec types ---
# --- Define subtitle codec types ---
# Codec constants are imported from app.modules.subtitle.core.constants to avoid circular imports
TEXT_SUBTITLE_CODECS = constants.TEXT_SUBTITLE_CODECS
IMAGE_SUBTITLE_CODECS_RO = constants.IMAGE_SUBTITLE_CODECS_RO
IMAGE_SUBTITLE_CODECS_EN = constants.IMAGE_SUBTITLE_CODECS_EN
IGNORED_OCR_CODECS = constants.IGNORED_OCR_CODECS

# --- Helper: Check Tool Availability ---
_tool_cache: dict[str, bool | None] = {}  # Cache for tool availability status


def _is_tool_available(tool_path: str, tool_name: str) -> bool:
    """Checks if an external tool exists and is executable, using a cache."""
    global _tool_cache
    cache_key = f"{tool_name}|{tool_path}"

    # Check cache first
    if cache_key in _tool_cache:
        # logger.debug(f"Tool '{tool_name}' availability cache hit: {_tool_cache[cache_key]}")
        return _tool_cache[cache_key] or False

    is_available = False
    resolved_path = shutil.which(tool_path)
    if resolved_path:
        # Basic check if it's a file and executable (on non-Windows)
        try:
            if Path(resolved_path).is_file():
                is_executable = os.name == "nt" or os.access(resolved_path, os.X_OK)
                if is_executable:
                    is_available = True
                    logger.debug(
                        f"Tool '{tool_name}' ({tool_path}) found and executable at '{resolved_path}'"
                    )
                else:
                    # On some systems (like containers), os.access might fail even if executable
                    is_available = True  # Assume executable if check fails but it's a file
                    logger.warning(
                        f"Tool '{tool_name}' ({tool_path}) found at '{resolved_path}' but OS executable check failed/skipped (assuming OK)."
                    )
            else:
                is_available = False
                logger.warning(
                    f"Tool '{tool_name}' ({tool_path}) resolved to '{resolved_path}' but it's not a file."
                )
        except OSError as e:
            is_available = False
            logger.warning(f"Error checking executable status for '{resolved_path}': {e}")
    else:
        is_available = False
        logger.warning(
            f"Tool '{tool_name}' ({tool_path}) not found in system PATH or configured path."
        )

    # Update cache
    _tool_cache[cache_key] = is_available
    # logger.debug(f"Updated tool '{tool_name}' availability cache: {is_available}")

    return is_available


# --- PGS to SRT Conversion ---
def _convert_pgs_to_srt(  # noqa: C901
    sup_file_path: str, output_srt_path: str, language_code_2_letter: str
) -> bool:
    """
    Converts a PGS (.sup) subtitle file to SRT format using sup2srt.

    Args:
        sup_file_path: Path to the input .sup file.
        output_srt_path: Path for the output .srt file.
        language_code_2_letter: The 2-letter language code for OCR (must be supported by sup2srt).

    Returns:
        True if conversion was successful and output file is valid, False otherwise.
    """
    if not _is_tool_available(SUP2SRT_PATH, "sup2srt"):
        logger.error(f"Cannot convert PGS: '{SUP2SRT_PATH}' tool unavailable.")
        return False
    if not Path(sup_file_path).exists():
        logger.error(f"Input .sup file not found for conversion: {sup_file_path}")
        return False
    if (
        not language_code_2_letter
        or len(language_code_2_letter) != 2
        or not language_code_2_letter.isalpha()
    ):
        logger.error(
            f"Invalid 2-letter language code '{language_code_2_letter}' provided for sup2srt."
        )
        return False

    sup_basename = Path(sup_file_path).name
    srt_basename = Path(output_srt_path).name
    logger.info(
        f"Converting PGS subtitle '{sup_basename}' to SRT '{srt_basename}' using language '{language_code_2_letter}'..."
    )

    # Ensure output directory exists
    output_dir = Path(output_srt_path).parent
    if not output_dir.exists():
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create output directory for SRT: {output_dir} - {e}")
            return False

    try:
        # Construct command - ensure language code is passed correctly
        # Use the actual executable path found by _is_tool_available if possible
        resolved_sup2srt_path = shutil.which(SUP2SRT_PATH) or SUP2SRT_PATH
        command = [
            resolved_sup2srt_path,
            sup_file_path,
            "-l",
            language_code_2_letter,  # Pass the 2-letter code
            "-o",
            output_srt_path,
        ]
        logger.debug(f"Running sup2srt command: {' '.join(command)}")

        result = subprocess.run(
            command,
            check=False,  # Check return code manually
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SUP2SRT_TIMEOUT,  # Use configured timeout
        )
        log_level = logging.DEBUG  # Default level for sup2srt output
        if result.returncode != 0 or "error" in result.stderr.lower():
            log_level = logging.WARNING  # Promote to warning if errors likely

        if result.stdout:
            logger.log(log_level, f"sup2srt stdout: {result.stdout.strip()}")
        if result.stderr:
            logger.log(log_level, f"sup2srt stderr: {result.stderr.strip()}")

        if result.returncode != 0:
            logger.error(f"sup2srt failed with exit code {result.returncode} for '{sup_basename}'.")
            if Path(output_srt_path).exists():  # Clean up potentially failed output
                try:
                    Path(output_srt_path).unlink()
                    logger.debug("Removed incomplete SRT output from failed sup2srt.")
                except OSError:
                    pass
            return False

        # Check if output file exists and has reasonable size (e.g., > 10 bytes)
        if Path(output_srt_path).exists() and Path(output_srt_path).stat().st_size > 10:
            logger.info(f"Successfully converted PGS to SRT: {srt_basename}")
            return True
        else:
            msg = f"sup2srt ran successfully (exit code 0) but did not create a valid output file: {srt_basename}"
            if Path(output_srt_path).exists():
                file_size = Path(output_srt_path).stat().st_size
                msg += f" (Size: {file_size} bytes)"
                # Clean up small/empty file
                try:
                    Path(output_srt_path).unlink()
                except OSError:
                    pass
            else:
                msg += " (File not found)"
            logger.error(msg)  # Changed from logging.error to logger.error
            return False

    except subprocess.TimeoutExpired:
        logger.error(
            f"Error converting PGS subtitle '{sup_basename}': sup2srt command timed out after {SUP2SRT_TIMEOUT} seconds."
        )
        if Path(output_srt_path).exists():
            try:
                Path(output_srt_path).unlink()
            except OSError:
                pass
        return False
    except FileNotFoundError:
        # Should be caught by _is_tool_available, but double check
        logger.error(f"'{SUP2SRT_PATH}' command not found during execution.")
        _tool_cache[f"sup2srt|{SUP2SRT_PATH}"] = False  # Update cache
        return False
    except Exception as ex:
        logger.error(
            f"Unexpected error during PGS conversion for '{sup_basename}': {ex}", exc_info=True
        )
        if Path(output_srt_path).exists():  # Clean up on any error
            try:
                Path(output_srt_path).unlink()
            except OSError:
                pass
        return False


# --- Language Code Normalization ---
def get_2_letter_code(code: str | None) -> str | None:
    """
    Maps a 3-letter language code, 2-letter code, or common name
    (if in constants map) to a standard 2-letter ISO 639-1 code.

    Args:
        code: The input language code or name (e.g., 'rum', 'ro', 'eng', 'en', 'Romanian').

    Returns:
        The corresponding 2-letter code (lowercase), or None if input is invalid
        or mapping fails. Returns None for 'und' (undetermined).
    """
    if not code or not isinstance(code, str):  # Handle None or non-string input
        # logger.debug(f"Invalid input type for language code: {type(code)}")
        return None

    code_lower = code.lower().strip()  # Ensure lower case and remove whitespace

    if not code_lower or code_lower == "und":  # Handle empty string or undetermined
        return None

    # Check if it's already a valid 2-letter code
    if len(code_lower) == 2:
        # Basic check if it looks like a valid 2-letter code (alphabetic)
        if code_lower.isalpha():
            # Verify it's a known 2-letter code by checking the reverse map first
            reverse_map = getattr(constants, "LANGUAGE_CODE_MAPPING_2_TO_3", {})
            if code_lower in reverse_map:
                return code_lower
            else:
                # As a fallback, check if it's a value in the 3->2 map
                map_3_to_2 = getattr(constants, "LANGUAGE_CODE_MAPPING_3_TO_2", {})
                if code_lower in map_3_to_2.values():
                    logger.debug(f"Input '{code}' is a valid 2-letter code value, returning.")
                    return code_lower
                else:
                    logger.warning(
                        f"Input '{code}' looks like a 2-letter code, but is not recognized in mappings."
                    )
                    return None  # Treat unrecognized 2-letter codes as invalid
        else:
            logger.debug(f"Ignoring invalid 2-character code: '{code}'")
            return None

    # If not 2 letters, lookup in the 3-to-2 (or name-to-2) mapping dictionary
    map_3_to_2 = getattr(constants, "LANGUAGE_CODE_MAPPING_3_TO_2", {})
    mapped_code = map_3_to_2.get(code_lower)
    if mapped_code:
        # Ensure the mapped code is valid 2 letters
        if isinstance(mapped_code, str) and len(mapped_code) == 2 and mapped_code.isalpha():
            return mapped_code
        else:
            logger.error(
                f"Internal Mapping Error: Code '{code}' mapped to invalid code '{mapped_code}' in constants."
            )
            return None  # Problem with the constant map definition
    else:
        logger.debug(f"Language code or name '{code}' not found in 3-to-2/name-to-2 mapping.")
        return None  # Return None if no mapping found


# --- Embedded Subtitle Detection and Extraction ---


def check_and_extract_embedded_subtitle(  # noqa: C901
    video_path: str, target_language_code: str
) -> tuple[str, str | None]:
    """
    Checks for embedded subtitles for a given language, prioritizes text-based,
    extracts the best match otherwise (handling text/PGS), and returns status and path.

    Handles language code normalization internally.

    Args:
        video_path (str): Path to the video file.
        target_language_code (str): The desired language code (e.g., 'ro', 'rum', 'en', 'eng').

    Returns:
        tuple[str, str | None]: A tuple containing:
            - status (str): One of "text_found_no_extract", "text_extracted", "pgs_extracted", "failed".
            - path_or_none (str | None): Path to the saved .srt file if extraction
              was performed and successful, otherwise None.
    """
    # --- Normalization Step ---
    target_lang_2_letter = get_2_letter_code(target_language_code)
    if not target_lang_2_letter:
        logger.error(
            f"Invalid or unsupported target language code provided: '{target_language_code}'"
        )
        return "failed", None
    # --- End Normalization ---

    video_path_str = str(video_path)  # Ensure string
    base_video_filename = Path(video_path_str).name
    # Use the normalized code in logging for clarity
    logger.info(
        f"Checking for embedded '{target_lang_2_letter}' subtitles (normalized from '{target_language_code}') in '{base_video_filename}'..."
    )

    # Check prerequisites
    if not Path(video_path_str).exists():
        logger.error(f"Video file not found: {video_path_str}")
        return "failed", None
    if not _is_tool_available(FFPROBE_PATH, "ffprobe"):
        logger.error(f"Cannot check embedded subtitles: '{FFPROBE_PATH}' tool unavailable.")
        return "failed", None

    # 1. Get stream info using ffprobe
    all_streams_data = []
    try:
        # Use the actual executable path found by _is_tool_available if possible
        resolved_ffprobe_path = shutil.which(FFPROBE_PATH) or FFPROBE_PATH
        ffprobe_cmd = [
            resolved_ffprobe_path,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-select_streams",
            "s",  # Select only subtitle streams
            video_path_str,
        ]
        logger.debug(f"Running ffprobe command: {' '.join(ffprobe_cmd)}")
        result = subprocess.run(
            ffprobe_cmd,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            errors="replace",
            timeout=FFPROBE_TIMEOUT,
        )
        all_streams_data = json.loads(result.stdout).get("streams", [])

    except subprocess.TimeoutExpired:
        logger.error(f"ffprobe timed out after {FFPROBE_TIMEOUT}s for '{base_video_filename}'.")
        return "failed", None
    except subprocess.CalledProcessError as e:
        stderr_snippet = e.stderr.strip()[-500:] if e.stderr else "(no stderr)"
        logger.error(
            f"ffprobe failed for '{base_video_filename}'. RC: {e.returncode}. Stderr: {stderr_snippet}"
        )
        return "failed", None
    except json.JSONDecodeError as e:
        stdout_snippet = result.stdout.strip()[:500] if result.stdout else "(no stdout)"
        logger.error(
            f"Failed to parse ffprobe JSON output for '{base_video_filename}': {e}. Output: {stdout_snippet}..."
        )
        return "failed", None
    except FileNotFoundError:
        logger.error(
            f"ffprobe command not found during execution (tried: {FFPROBE_PATH}). Ensure ffprobe (from FFmpeg) is installed and in PATH."
        )
        _tool_cache[f"ffprobe|{FFPROBE_PATH}"] = False  # Update cache
        return "failed", None
    except Exception as e:
        logger.error(
            f"An unexpected error occurred running ffprobe for '{base_video_filename}': {e}",
            exc_info=True,
        )
        return "failed", None

    if not all_streams_data:
        logger.info(f"No embedded subtitle streams found by ffprobe in '{base_video_filename}'.")
        return "failed", None

    # 2. Analyze streams and find the best candidate for the target language
    best_stream_for_extraction = None
    text_found_no_extract = False  # Flag if we find a text stream matching target
    logger.debug(f"Analyzing {len(all_streams_data)} subtitle streams found by ffprobe...")

    # --- Prioritize finding any matching text stream (no extraction needed) ---
    for stream in all_streams_data:
        lang_tag = stream.get("tags", {}).get("language", "und")
        stream_lang_2_letter = get_2_letter_code(lang_tag)
        stream_codec = stream.get("codec_name", "").lower()
        log_index = stream.get("index", "N/A")

        # Use the normalized target language code for comparison
        if stream_lang_2_letter == target_lang_2_letter and stream_codec in TEXT_SUBTITLE_CODECS:
            logger.info(
                f"Found embedded text-based '{target_lang_2_letter}' subtitle (Stream #{log_index}, Codec: {stream_codec}). Signaling success without extraction."
            )
            text_found_no_extract = True
            break  # Found the highest priority (text matching target), no need to check further

    if text_found_no_extract:
        return "text_found_no_extract", None

    # --- If no matching text stream found, find best candidate for EXTRACTION (Text or Image) ---
    candidate_streams: list[dict] = []
    # Select appropriate image codec set based on normalized target language
    image_codecs_to_consider = (
        IMAGE_SUBTITLE_CODECS_RO if target_lang_2_letter == "ro" else IMAGE_SUBTITLE_CODECS_EN
    )

    for stream in all_streams_data:
        lang_tag = stream.get("tags", {}).get("language", "und")
        stream_lang_2_letter = get_2_letter_code(lang_tag)
        stream_codec = stream.get("codec_name", "").lower()
        log_index = stream.get("index", "N/A")
        # logger.debug(f"  Stream #{log_index}: Codec='{stream_codec}', Tag='{lang_tag}', Mapped='{stream_lang_2_letter}'") # Can be verbose

        # Compare stream's mapped code with the normalized target code
        if stream_lang_2_letter == target_lang_2_letter:
            if stream_codec in IGNORED_OCR_CODECS:
                logger.warning(
                    f"Found embedded {stream_codec} stream #{log_index} for '{target_lang_2_letter}'. Skipping extraction because valid OCR quality is typically poor for this format."
                )

            is_extractable_text = stream_codec in TEXT_SUBTITLE_CODECS
            is_extractable_image = stream_codec in image_codecs_to_consider

            if is_extractable_text or is_extractable_image:
                candidate_streams.append(stream)
                logger.debug(
                    f"    Stream #{log_index}: Found candidate for target '{target_lang_2_letter}' (Codec: {stream_codec}, Type: {'Text' if is_extractable_text else 'Image'})."
                )
            # Optional: Log skipped streams for debugging
            # elif stream_codec in IMAGE_SUBTITLE_CODECS_RO or stream_codec in IMAGE_SUBTITLE_CODECS_EN:
            #     logger.debug(f"    -> Found matching language '{target_lang_2_letter}' but image codec '{stream_codec}' is not enabled for extraction for this language - skipped.")
            # else:
            #      logger.debug(f"    -> Found matching language '{target_lang_2_letter}' but unsupported codec '{stream_codec}' for extraction - skipped.")

    if not candidate_streams:
        logger.info(
            f"No suitable embedded subtitle streams found matching target language '{target_lang_2_letter}' for extraction."
        )
        return "failed", None

    # Prioritize text streams over image streams for extraction
    # Secondary sort: prefer non-SDH, then prefer default
    candidate_streams.sort(
        key=lambda s: (
            0 if s.get("codec_name", "").lower() in TEXT_SUBTITLE_CODECS else 1,  # Text first
            s.get("disposition", {}).get("hearing_impaired", 0),  # Then non-SDH (0 preferred)
            -s.get("disposition", {}).get(
                "default", 0
            ),  # Then default (1 preferred -> higher value first)
        )
    )
    best_stream_for_extraction = candidate_streams[0]  # Choose the best candidate

    stream_index = best_stream_for_extraction.get("index")
    stream_codec = best_stream_for_extraction.get("codec_name", "").lower()
    is_sdh = best_stream_for_extraction.get("disposition", {}).get("hearing_impaired", 0) == 1
    is_default = best_stream_for_extraction.get("disposition", {}).get("default", 0) == 1
    logger.info(
        f"Selected best candidate stream #{stream_index} (Codec: {stream_codec}, Default: {is_default}, SDH: {is_sdh}) for language '{target_lang_2_letter}' for extraction."
    )

    # 3. Extract and process the selected stream
    final_saved_path = None
    final_status = "failed"  # Default status if extraction fails
    temp_dir = None  # Initialize temp_dir to None

    # Ensure ffmpeg is available for extraction step
    if not _is_tool_available(FFMPEG_PATH, "ffmpeg"):
        logger.error(f"Cannot extract embedded subtitle: '{FFMPEG_PATH}' tool unavailable.")
        return "failed", None  # Cannot proceed without ffmpeg

    try:
        temp_dir = tempfile.mkdtemp(prefix=f"sub_extract_{target_lang_2_letter}_")
        logger.debug(f"Created temporary directory for extraction: {temp_dir}")
        # Use normalized 2-letter code for preferred path naming
        base_name_no_ext = str(Path(video_path_str).with_suffix(""))
        # file_utils might not be fully available in fallback, handle potential error
        try:
            target_sub_path = file_utils.get_preferred_subtitle_path(
                base_name_no_ext, target_lang_2_letter
            )
        except AttributeError:
            logger.warning(
                "file_utils.get_preferred_subtitle_path not available, using default naming."
            )
            target_sub_path = f"{base_name_no_ext}.{target_lang_2_letter}.srt"

        output_dir = Path(target_sub_path).parent
        if output_dir:  # Ensure output dir exists if it's not the current dir
            output_dir.mkdir(parents=True, exist_ok=True)

        # Use global stream index!
        map_specifier = f"0:{stream_index}"
        temp_srt_path = str(Path(temp_dir) / f"stream_{stream_index}_temp.srt")
        temp_sup_path = str(Path(temp_dir) / f"stream_{stream_index}_temp.sup")  # For image subs
        extracted_srt_path = None  # Path to the successfully extracted/converted SRT in temp dir

        # Use the actual executable path found by _is_tool_available if possible
        resolved_ffmpeg_path = shutil.which(FFMPEG_PATH) or FFMPEG_PATH

        if stream_codec in TEXT_SUBTITLE_CODECS:
            logger.info(
                f"Extracting text-based stream using global index #{stream_index} (map 0:{stream_index}) to SRT format..."
            )
            ffmpeg_cmd = [
                resolved_ffmpeg_path,
                "-nostdin",
                "-y",
                "-i",
                video_path_str,
                "-map",
                map_specifier,
                "-c:s",
                "srt",  # Force output to SRT format
                temp_srt_path,
            ]
            logger.debug(f"Running ffmpeg command: {' '.join(ffmpeg_cmd)}")
            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=FFMPEG_TIMEOUT,
                encoding="utf-8",
                errors="replace",
            )

            stderr_snippet = result.stderr.strip()[-500:] if result.stderr else "(no stderr)"
            if (
                result.returncode == 0
                and Path(temp_srt_path).exists()
                and Path(temp_srt_path).stat().st_size > 10
            ):
                extracted_srt_path = temp_srt_path
                final_status = "text_extracted"
                logger.debug(
                    f"Successfully extracted text stream #{stream_index} to temp SRT. RC={result.returncode}. Stderr: {stderr_snippet}"
                )
            else:
                logger.warning(
                    f"ffmpeg failed or produced empty file extracting text stream #{stream_index}. RC={result.returncode}. Stderr: {stderr_snippet}"
                )
                if Path(temp_srt_path).exists():
                    try:
                        Path(temp_srt_path).unlink()
                    except OSError:
                        pass

        elif stream_codec in image_codecs_to_consider:  # Handle allowed image formats
            logger.info(
                f"Extracting image-based stream using global index #{stream_index} (map 0:{stream_index}) ({stream_codec})..."
            )
            extract_cmd = [
                resolved_ffmpeg_path,
                "-nostdin",
                "-y",
                "-i",
                video_path_str,
                "-map",
                map_specifier,
                "-c:s",
                "copy",  # Copy the raw stream data (e.g., .sup for PGS)
                temp_sup_path,
            ]
            logger.debug(f"Running ffmpeg extract command: {' '.join(extract_cmd)}")
            result_extract = subprocess.run(
                extract_cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=FFMPEG_TIMEOUT,
                encoding="utf-8",
                errors="replace",
            )
            stderr_snippet = (
                result_extract.stderr.strip()[-500:] if result_extract.stderr else "(no stderr)"
            )

            # Check if raw extraction worked
            if (
                result_extract.returncode == 0
                and Path(temp_sup_path).exists()
                and Path(temp_sup_path).stat().st_size > 10
            ):  # Check size > 10 for raw image subs
                logger.debug(
                    f"Successfully extracted image stream #{stream_index} to '{temp_sup_path}'. Attempting OCR..."
                )
                # Use the normalized 2-letter code for sup2srt OCR
                ocr_success = _convert_pgs_to_srt(
                    temp_sup_path, temp_srt_path, target_lang_2_letter
                )
                if (
                    ocr_success
                    and Path(temp_srt_path).exists()
                    and Path(temp_srt_path).stat().st_size > 10
                ):
                    extracted_srt_path = temp_srt_path
                    final_status = "pgs_extracted"  # Specific status for successful PGS OCR
                    logger.info(f"Successfully OCR'd image stream #{stream_index} to SRT.")
                else:
                    logger.error(
                        f"Image subtitle OCR failed or produced empty/missing SRT for stream #{stream_index}."
                    )
                    # Clean up failed OCR output if it exists
                    if Path(temp_srt_path).exists():
                        try:
                            Path(temp_srt_path).unlink()
                        except OSError:
                            pass
            else:
                logger.warning(
                    f"ffmpeg failed or produced empty file extracting image stream #{stream_index}. RC={result_extract.returncode}. Stderr: {stderr_snippet}"
                )
                if Path(temp_sup_path).exists():  # Clean up failed raw extract
                    try:
                        Path(temp_sup_path).unlink()
                    except OSError:
                        pass

        # --- Post-processing and Saving ---
        if extracted_srt_path:
            logger.info(f"Processing and saving extracted subtitle from stream #{stream_index}...")
            try:
                # Use file_utils/parser if available, otherwise skip processing
                if "file_utils" in globals() and hasattr(file_utils, "read_srt_file"):
                    content = file_utils.read_srt_file(extracted_srt_path)
                else:
                    with Path(extracted_srt_path).open(encoding="utf-8", errors="replace") as f:
                        content = f.read()

                if not content or not content.strip():
                    logger.warning(
                        f"Extracted SRT file from stream #{stream_index} is empty after read. Skipping save."
                    )
                    final_status = "failed"  # Mark as failed if content is empty
                else:
                    processed_content = content
                    # Apply fixes only if parser is available
                    if "subtitle_parser" in globals():
                        processed_content = subtitle_parser.fix_diacritics(processed_content)
                        processed_content = subtitle_parser.ensure_correct_timestamp_format(
                            processed_content
                        )

                    if not processed_content or not processed_content.strip():
                        logger.warning(
                            f"Subtitle content became empty after processing for stream #{stream_index}. Skipping save."
                        )
                        final_status = "failed"
                    else:
                        # Use file_utils if available, otherwise basic write
                        if "file_utils" in globals() and hasattr(file_utils, "write_srt_file"):
                            target_sub_path = file_utils.write_srt_file(
                                target_sub_path, processed_content
                            )
                        else:
                            with Path(target_sub_path).open("w", encoding="utf-8") as f:
                                f.write(processed_content)

                        logger.info(
                            f"Saved final embedded subtitle as: {Path(target_sub_path).name}"
                        )
                        final_saved_path = target_sub_path
                        # final_status was already set ("text_extracted" or "pgs_extracted")

            except Exception as proc_err:
                logger.error(
                    f"Failed to process or save extracted subtitle from stream #{stream_index}: {proc_err}",
                    exc_info=True,
                )
                final_status = "failed"  # Mark as failed if processing error occurs
                final_saved_path = None
                # Clean up final target if save failed halfway? Maybe not needed.

    except subprocess.TimeoutExpired as time_err:
        logger.error(
            f"ffmpeg extraction process timed out for stream #{stream_index} after {FFMPEG_TIMEOUT}s: {time_err}"
        )
        final_status = "failed"
    except Exception as e:
        logger.error(
            f"Unexpected error during extraction process for '{base_video_filename}', stream #{stream_index}: {e}",
            exc_info=True,
        )
        final_status = "failed"
    finally:
        # Ensure temp directory is cleaned up
        if temp_dir and Path(temp_dir).exists():
            try:
                # Use file_utils cleanup if available, otherwise shutil
                if "file_utils" in globals() and hasattr(file_utils, "clean_temp_directory"):
                    file_utils.clean_temp_directory(temp_dir)
                else:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as cleanup_err:
                logger.warning(
                    f"Failed to clean up temporary directory '{temp_dir}': {cleanup_err}"
                )

    # Log final outcome
    if final_saved_path:
        logger.info(
            f"Embedded subtitle processing finished for '{target_lang_2_letter}'. Status: '{final_status}', Path: '{Path(final_saved_path).name}'"
        )
    else:
        logger.info(
            f"Embedded subtitle processing finished for '{target_lang_2_letter}'. Status: '{final_status}', No file saved."
        )

    return final_status, final_saved_path


def find_best_embedded_stream_info(  # noqa: C901
    video_path: str,
    target_language_code: str,  # Accept 2 or 3 letter code, or mapped name
    preferred_codecs: list[str] | None = None,
) -> dict[str, Any] | None:
    """
    Finds the best matching embedded subtitle stream's info without extracting.

    Uses ffprobe to get stream details. Prioritizes preferred codecs if provided.
    Handles language code normalization internally.

    Args:
        video_path: Path to the video file.
        target_language_code: The desired language code (e.g., 'en', 'eng', 'ro', 'rum').
        preferred_codecs: List of preferred codec names (lowercase) like ['subrip', 'ass'].

    Returns:
        A dictionary containing info for the best match (see keys inside function),
        or None if no suitable stream is found, ffprobe fails, or language code is invalid.
        Includes 'language' (original tag) and 'mapped_lang' (normalized 2-letter code).
    """
    # --- Normalization Step ---
    target_lang_2_letter = get_2_letter_code(target_language_code)
    if not target_lang_2_letter:
        logger.error(
            f"Invalid or unsupported target language code for detection: '{target_language_code}'"
        )
        return None
    # --- End Normalization ---

    preferred_codecs = [c.lower() for c in preferred_codecs] if preferred_codecs else []
    video_path_str = str(video_path)
    base_video_filename = Path(video_path_str).name

    # Check ffprobe availability
    if not _is_tool_available(FFPROBE_PATH, "ffprobe"):
        logger.error(
            f"ffprobe command not found or not executable (tried: {FFPROBE_PATH}). Cannot detect embedded streams."
        )
        return None
    if not Path(video_path_str).exists():
        logger.error(f"Video file not found: {video_path_str}")
        return None

    # Use the actual executable path found by _is_tool_available if possible
    resolved_ffprobe_path = shutil.which(FFPROBE_PATH) or FFPROBE_PATH
    command = [
        resolved_ffprobe_path,
        "-v",
        "error",  # Keep error level to avoid noise, check return code
        "-print_format",
        "json",
        "-show_streams",
        "-select_streams",
        "s",  # Select only subtitle streams
        video_path_str,
    ]

    logger.debug(f"Running ffprobe command for stream detection: {' '.join(command)}")
    media_info = None
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            errors="replace",
            timeout=FFPROBE_TIMEOUT,
        )
        media_info = json.loads(result.stdout)
    except FileNotFoundError:
        logger.error(f"ffprobe command '{FFPROBE_PATH}' not found during execution.")
        _tool_cache[f"ffprobe|{FFPROBE_PATH}"] = False  # Update cache
        return None
    except subprocess.TimeoutExpired:
        logger.error(
            f"ffprobe timed out after {FFPROBE_TIMEOUT}s for '{base_video_filename}' during stream detection."
        )
        return None
    except subprocess.CalledProcessError as e:
        stderr_snippet = e.stderr.strip()[-500:] if e.stderr else "(no stderr)"
        logger.error(
            f"ffprobe failed for stream detection on {base_video_filename} (RC={e.returncode}). Stderr: {stderr_snippet}"
        )
        return None
    except json.JSONDecodeError as e:
        stdout_snippet = result.stdout.strip()[:500] if result.stdout else "(no stdout)"
        logger.error(
            f"Failed to parse ffprobe JSON output for stream detection on '{base_video_filename}': {e}. Output: {stdout_snippet}..."
        )
        return None
    except Exception as e:
        logger.error(
            f"An unexpected error occurred running ffprobe for stream detection on '{base_video_filename}': {e}",
            exc_info=True,
        )
        return None

    subtitle_streams = media_info.get("streams", [])
    if not subtitle_streams:
        logger.debug(f"No embedded subtitle streams found in {base_video_filename}.")
        return None

    candidates = []
    # Use the normalized target language code here
    logger.debug(
        f"Searching for streams matching language '{target_lang_2_letter}' (normalized from '{target_language_code}')..."
    )

    for stream in subtitle_streams:
        stream_lang_tag = stream.get("tags", {}).get("language", "und")
        stream_lang_2_letter = get_2_letter_code(stream_lang_tag)  # Normalize stream lang
        codec_name = stream.get("codec_name", "unknown").lower()
        stream_index = stream.get("index")
        log_index = stream.get("index", "N/A")  # For logging

        # logger.debug(f"  Stream #{log_index}: Codec='{codec_name}', Tag='{stream_lang_tag}', Mapped='{stream_lang_2_letter}'") # Verbose

        # Compare the *mapped 2-letter code of the stream* with the *normalized target 2-letter code*
        if stream_lang_2_letter == target_lang_2_letter and stream_index is not None:
            if codec_name in IGNORED_OCR_CODECS:
                logger.warning(
                    f"Found embedded {codec_name} stream #{log_index} for '{target_lang_2_letter}'. Skipping extraction because valid OCR quality is typically poor for this format."
                )

            # Scoring logic to find the 'best' stream
            is_preferred_codec = codec_name in preferred_codecs
            disposition = stream.get("disposition", {})
            is_default = disposition.get("default", 0) == 1
            is_forced = disposition.get("forced", 0) == 1
            is_hearing_impaired = disposition.get("hearing_impaired", 0) == 1
            # Check title as fallback for SDH/HI (case-insensitive)
            title = stream.get("tags", {}).get("title", "")
            if (
                not is_hearing_impaired
                and title
                and ("sdh" in title.lower() or "hearing impaired" in title.lower())
            ):
                is_hearing_impaired = True

            # Higher score is better
            score = 0
            if is_preferred_codec:
                score += 20  # Big boost for preferred codec (e.g., text)
            else:
                # Give minor boost even for non-preferred text codecs over image codecs
                if codec_name in TEXT_SUBTITLE_CODECS:
                    score += 2

            if is_default:
                score += 10  # Boost for default track
            if not is_hearing_impaired:
                score += 5  # Prefer non-SDH slightly
            if not is_forced:
                score += 3  # Prefer non-forced slightly

            candidates.append(
                {
                    "score": score,
                    "stream_index": stream_index,
                    "codec_name": codec_name,
                    "language": stream_lang_tag,  # Store original tag from ffprobe
                    "mapped_lang": stream_lang_2_letter,  # Store mapped 2-letter code
                    "is_sdh": is_hearing_impaired,
                    "is_forced": is_forced,
                    "is_default": is_default,
                    "title": title,  # Store title for info/tie-breaking
                }
            )
            # logger.debug(f"    -> Added candidate Stream #{stream_index} for '{target_lang_2_letter}' with score {score} (Codec: {codec_name}, Default: {is_default}, Forced: {is_forced}, SDH: {is_hearing_impaired}).")

    if not candidates:
        logger.debug(
            f"No embedded subtitle streams found matching language '{target_lang_2_letter}'."
        )
        return None

    # Sort candidates by score (descending)
    candidates.sort(key=lambda x: x["score"], reverse=True)

    best_candidate = candidates[0]
    # Log using the normalized 2-letter code and details of the chosen stream
    logger.debug(
        f"Found best matching embedded stream for '{target_lang_2_letter}': Index={best_candidate['stream_index']}, "
        f"Codec={best_candidate['codec_name']}, Score={best_candidate['score']}, "
        f"OrigLang='{best_candidate['language']}', MappedLang='{best_candidate['mapped_lang']}', "
        f"Default={best_candidate['is_default']}, Forced={best_candidate['is_forced']}, SDH={best_candidate['is_sdh']}, "
        f"Title='{best_candidate['title']}'"
    )

    # Return a comprehensive dictionary of the best candidate's info
    return best_candidate


# --- Optional: Helper for direct extraction by index ---
def extract_embedded_stream_by_index(  # noqa: C901
    video_path: str,
    stream_index: int,
    output_dir: str,
    output_filename_base: str | None = None,
    apply_fixes: bool = True,  # Option to apply post-processing
) -> str | None:
    """
    Extracts a specific subtitle stream by its index using ffmpeg, attempting SRT conversion.

    Optionally applies standard post-processing (diacritics, timestamp format).
    Does NOT handle image-based subtitle OCR - use check_and_extract_embedded_subtitle for that.

    Args:
        video_path: Path to the video file.
        stream_index: The index of the subtitle stream to extract.
        output_dir: The directory to save the extracted file.
        output_filename_base: Optional base name for the output file (without extension).
                              Defaults to video filename base + stream index.
        apply_fixes: If True, apply diacritics and timestamp fixes after extraction.

    Returns:
        The full path to the extracted and potentially processed subtitle file (.srt assumed),
        or None on failure or if the stream is image-based (requires OCR).
    """
    video_path_str = str(video_path)
    if not _is_tool_available(FFMPEG_PATH, "ffmpeg"):
        logger.error(
            f"ffmpeg tool unavailable ('{FFMPEG_PATH}'). Cannot extract stream #{stream_index}."
        )
        return None
    if not Path(video_path_str).exists():
        logger.error(f"Video file not found: {video_path_str}")
        return None
    if not Path(output_dir).is_dir():
        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created output directory: {output_dir}")
        except OSError as e:
            logger.error(
                f"Output directory does not exist and could not be created: {output_dir} - {e}"
            )
            return None

    if output_filename_base is None:
        output_filename_base = f"{Path(video_path_str).stem}_stream_{stream_index}"

    # Assume SRT output, ffmpeg will attempt conversion for text-based subs
    output_subtitle_path = str(Path(output_dir) / f"{output_filename_base}.srt")

    # Use the actual executable path found by _is_tool_available if possible
    resolved_ffmpeg_path = shutil.which(FFMPEG_PATH) or FFMPEG_PATH
    command = [
        resolved_ffmpeg_path,
        "-nostdin",  # Prevent interference from stdin
        "-y",  # Overwrite output files without asking
        "-i",
        video_path_str,
        # Use global stream index mapping since 'stream_index' comes from ffprobe's 'index' field which is global.
        # Original Bug: using "0:s:{stream_index}" treated it as relative subtitle index (e.g. 3rd subtitle)
        # instead of the 3rd stream overall.
        "-map",
        f"0:{stream_index}",
        "-c:s",
        "srt",  # Attempt to force output codec to SRT
        # "-vn", "-an",              # Not strictly necessary when only mapping subs, but harmless
        output_subtitle_path,
    ]

    logger.info(
        f"Attempting to extract subtitle using global stream index #{stream_index} (map 0:{stream_index}) to '{Path(output_subtitle_path).name}'..."
    )
    logger.debug(f"Running ffmpeg command: {' '.join(command)}")

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=FFMPEG_TIMEOUT,
            encoding="utf-8",
            errors="replace",
        )  # Check manually

        # Log ffmpeg output (useful for debugging)
        log_level = logging.DEBUG
        stderr_lower = result.stderr.lower() if result.stderr else ""
        if (
            result.returncode != 0
            or "error" in stderr_lower
            or "unable to find a suitable output format" in stderr_lower
        ):
            log_level = logging.WARNING
        # Log snippets to avoid flooding
        stdout_snippet = result.stdout.strip()[-500:] if result.stdout else "(no stdout)"
        stderr_snippet = (
            result.stderr.strip()[-1000:] if result.stderr else "(no stderr)"
        )  # Longer stderr snippet

        if result.stdout:
            logger.log(
                log_level, f"ffmpeg extract stdout (stream #{stream_index}): {stdout_snippet}"
            )
        if result.stderr:
            logger.log(
                log_level, f"ffmpeg extract stderr (stream #{stream_index}): {stderr_snippet}"
            )

        # Check success conditions more carefully
        success = False
        if (
            result.returncode == 0
            and Path(output_subtitle_path).exists()
            and Path(output_subtitle_path).stat().st_size > 10
        ):
            # Double check stderr for common silent failures like codec issues
            if "Subtitle codec" in result.stderr and "is not supported" in result.stderr:
                logger.warning(
                    f"ffmpeg indicated subtitle codec for stream #{stream_index} is not supported for SRT conversion."
                )
            elif "unable to find a suitable output format" in stderr_lower:
                logger.warning(
                    f"ffmpeg was unable to convert stream #{stream_index} to SRT (likely image-based or unsupported format)."
                )
            else:
                success = True
        else:
            # Log specific failure reason
            if result.returncode != 0:
                logger.error(
                    f"ffmpeg extraction failed for stream #{stream_index} (return code {result.returncode})."
                )
            elif not Path(output_subtitle_path).exists():
                logger.error(
                    f"ffmpeg command ran (RC=0) but output file is missing: {Path(output_subtitle_path).name}"
                )
            elif Path(output_subtitle_path).stat().st_size <= 10:
                logger.error(
                    f"ffmpeg command ran (RC=0) but output file is too small (<10 bytes): {Path(output_subtitle_path).name}"
                )

        if success:
            logger.info(
                f"Successfully extracted stream #{stream_index} to {Path(output_subtitle_path).name}"
            )

            # Optional: Post-process (fix diacritics, timestamps)
            if apply_fixes:
                logger.debug(
                    f"Applying post-processing fixes to extracted stream #{stream_index}..."
                )
                processed = False
                try:
                    # Use file_utils/parser if available
                    if (
                        "file_utils" in globals()
                        and hasattr(file_utils, "read_srt_file")
                        and "subtitle_parser" in globals()
                    ):
                        content = file_utils.read_srt_file(output_subtitle_path)
                        if content and content.strip():
                            processed_content = subtitle_parser.fix_diacritics(content)
                            processed_content = subtitle_parser.ensure_correct_timestamp_format(
                                processed_content
                            )
                            if processed_content and processed_content.strip():
                                file_utils.write_srt_file(
                                    output_subtitle_path, processed_content, allow_fallback=False
                                )
                                processed = True
                            else:
                                logger.warning(
                                    f"Content became empty after processing for stream #{stream_index}. Reverting to original."
                                )
                        else:
                            logger.warning(
                                f"Extracted file for stream #{stream_index} was empty before processing."
                            )
                    else:
                        logger.warning(
                            "Cannot apply fixes: file_utils or subtitle_parser not fully available."
                        )

                    if processed:
                        logger.debug(
                            f"Successfully applied fixes to {Path(output_subtitle_path).name}"
                        )
                    else:
                        # If processing failed or wasn't possible, the original extracted file remains
                        logger.debug(
                            f"Skipped or failed applying fixes to {Path(output_subtitle_path).name}. Using raw extraction."
                        )

                except Exception as fix_err:
                    logger.error(
                        f"Error applying fixes to extracted stream #{stream_index}: {fix_err}",
                        exc_info=True,
                    )
                    # Keep the original extracted file even if fixes fail

            return output_subtitle_path
        else:
            # Clean up potentially empty/failed file
            if Path(output_subtitle_path).exists():
                try:
                    logger.debug(f"Removing failed/empty extraction output: {output_subtitle_path}")
                    Path(output_subtitle_path).unlink()
                except OSError as rm_err:
                    logger.warning(
                        f"Could not remove failed output file {output_subtitle_path}: {rm_err}"
                    )
            return None  # Indicate failure

    except FileNotFoundError:
        logger.error(f"ffmpeg command '{FFMPEG_PATH}' not found during execution.")
        _tool_cache[f"ffmpeg|{FFMPEG_PATH}"] = False  # Update cache
        return None
    except subprocess.TimeoutExpired:
        logger.error(
            f"ffmpeg extraction timed out after {FFMPEG_TIMEOUT}s for stream #{stream_index}. Process killed."
        )
        if Path(output_subtitle_path).exists():
            try:
                Path(output_subtitle_path).unlink()
            except OSError:
                pass
        return None
    except Exception as e:
        logger.error(
            f"An unexpected error occurred running ffmpeg for stream #{stream_index}: {e}",
            exc_info=True,
        )
        if Path(output_subtitle_path).exists():
            try:
                Path(output_subtitle_path).unlink()
            except OSError:
                pass
        return None


# --- Explicit Exports ---
# List functions/classes intended for use by other modules
__all__ = [
    "IMAGE_SUBTITLE_CODECS_EN",
    "IMAGE_SUBTITLE_CODECS_RO",
    "TEXT_SUBTITLE_CODECS",
    "check_and_extract_embedded_subtitle",
    "extract_embedded_stream_by_index",
    "find_best_embedded_stream_info",
    "get_2_letter_code",
    # Constants related to codecs might be exported if needed externally
    # Tool paths might be useful sometimes, but usually accessed via functions
    # "FFMPEG_PATH", "FFPROBE_PATH", "SUP2SRT_PATH"
]

logger.info("Media utilities module initialized.")
