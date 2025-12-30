# src/services/translator.py

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import html  # Added for unescaping entities
import json
import logging
import os
import re  # Added for regex parsing and SRT corrections
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError

# --- External Libraries ---
try:
    import requests
except ImportError:
    print("Error: 'requests' library not found. Please install it: pip install requests")
    requests = None  # Indicate library is missing

try:
    import deepl
except ImportError:
    print("Error: 'deepl' library not found. Please install it: pip install deepl")
    deepl = None  # Indicate library is missing

try:
    import nltk
    from nltk.tokenize import sent_tokenize
except ImportError:
    print(
        "Warning: 'nltk' library not found (pip install nltk). Sentence splitting will rely on basic line breaks."
    )
    nltk = None  # Indicate library is missing
    sent_tokenize = None

try:
    from google.api_core import exceptions as google_exceptions
    from google.cloud import translate_v3 as google_translate
except ImportError:
    print(
        "Warning: Google Cloud Translate libraries not found (pip install google-cloud-translate). Google Translate functionality disabled."
    )
    google_translate = None
    google_exceptions = None

# ------------------------------------------------------------------
#  Configuration Loader & Utility References (Adapt as needed)
# ------------------------------------------------------------------
"""
This script assumes configuration (API keys, project ID, etc.) is loaded
into the global variables DEEPL_KEYS, GOOGLE_PROJECT_ID_CONFIG, etc.
before the TranslationManager is instantiated. This typically happens
via an external loader (like Pydantic settings) or within the
`if __name__ == "__main__":` block for standalone testing.
"""
try:
    # Example: Using a hypothetical settings object
    from app.core.config import settings
    from app.db import base as _  # noqa: F401 Ensure all models are registered before DB access
    from app.db.models.deepl_usage import DeepLUsage
    from app.db.models.translation_log import TranslationLog
    from app.db.session import SyncSessionLocal

    CONFIG_LOADER_AVAILABLE = True
    DATABASE_AVAILABLE = True
except ImportError:
    settings = None
    SyncSessionLocal = None
    DeepLUsage = None
    TranslationLog = None
    CONFIG_LOADER_AVAILABLE = False
    DATABASE_AVAILABLE = False
    # In a real application, handle missing config loader more robustly.

try:
    from app.modules.subtitle.utils.file_utils import find_project_root

    PROJECT_ROOT_FUNC_AVAILABLE = True
except ImportError:
    PROJECT_ROOT_FUNC_AVAILABLE = False

# ------------------------------------------------------------------
#  Global Settings (Placeholders - Initialized by Loader/Main)
# ------------------------------------------------------------------
DEEPL_KEYS = []
GOOGLE_PROJECT_ID_CONFIG = None
GOOGLE_CREDENTIALS_PATH = None
DEEPL_QUOTA_PER_KEY = 500000  # Default DeepL monthly free tier limit (chars)

# ------------------------------------------------------------------
#  Constants for API Limits
# ------------------------------------------------------------------
# DeepL limits (adjust if using Pro API with different limits)
DEEPL_MAX_CHUNK_SIZE_FREE = 4800  # Stay slightly under 5k char limit for safety
DEEPL_MAX_STRINGS_PER_REQUEST = 50  # Max texts in a list translation request

# Google Translate limits (V3) - Check official docs for current values
GOOGLE_MAX_CHUNK_SIZE_BYTES = 29000  # Stay under 30k byte limit per string
GOOGLE_MAX_STRINGS_PER_REQUEST = 1000  # Max texts in a list translation request (higher than DeepL)
GOOGLE_MAX_TOTAL_BYTES_PER_REQUEST = 100000  # Approximate total byte limit per request

# ------------------------------------------------------------------
#  Logging Setup
# ------------------------------------------------------------------

logger = logging.getLogger(__name__)  # Logger for this module


# ------------------------------------------------------------------
#  NLTK Tokenizer Check/Download
# ------------------------------------------------------------------
def download_nltk_data_if_needed(resource_name, resource_subdir):
    """Downloads NLTK data if not found."""
    if not nltk:
        logger.warning("NLTK library not available, cannot download data.")
        return False
    try:
        nltk.data.find(f"{resource_subdir}/{resource_name}")
        logger.debug(f"NLTK resource '{resource_name}' found.")
        return True
    except LookupError:
        logger.info(f"NLTK resource '{resource_name}' not found. Attempting download...")
        try:
            nltk.download(resource_name, quiet=True)
            logger.info(f"Successfully downloaded NLTK resource '{resource_name}'.")
            # Verify download
            try:
                nltk.data.find(f"{resource_subdir}/{resource_name}")
                return True
            except LookupError:
                logger.error(
                    f"NLTK resource '{resource_name}' still not found after download attempt."
                )
                return False
        except URLError as url_err:
            logger.warning(
                f"Failed to download NLTK '{resource_name}' due to network error: {url_err}. Text processing might be less accurate."
            )
            return False
        except Exception as e:
            logger.warning(
                f"Failed to download NLTK '{resource_name}': {e}. Text processing may be less accurate."
            )
            return False
    except Exception as nltk_init_err:
        logger.error(f"An unexpected error occurred during NLTK setup check: {nltk_init_err}")
        return False


# ------------------------------------------------------------------
#  Initialization Logic (Lazy)
# ------------------------------------------------------------------
_is_module_initialized = False
NLTK_PUNKT_AVAILABLE = False
TRANSLATION_LOG_FILE = "translation_log.json"  # Default


def _ensure_initialized():
    """
    Performs one-time initialization (NLTK check, Log file path) that requires logging to be ready.
    Called by get_translation_manager().
    """
    global _is_module_initialized, NLTK_PUNKT_AVAILABLE, TRANSLATION_LOG_FILE
    if _is_module_initialized:
        return

    # --- NLTK Check ---
    if nltk:
        NLTK_PUNKT_AVAILABLE = download_nltk_data_if_needed("punkt", "tokenizers")
    else:
        NLTK_PUNKT_AVAILABLE = False

    # --- Translation Log File ---
    try:
        if PROJECT_ROOT_FUNC_AVAILABLE:
            _project_root = find_project_root(Path(__file__).resolve().parent)
            TRANSLATION_LOG_FILE = str(Path(_project_root) / "logs" / "translation_log.json")
            logger.info(f"Translation log file path target: {TRANSLATION_LOG_FILE}")
        else:
            logger.warning(
                "Project root finding function unavailable. Using default log file name in CWD."
            )
            TRANSLATION_LOG_FILE = str(Path.cwd() / "translation_log.json")
    except Exception as e:
        logger.error(
            f"Could not determine project root for log file: {e}. Using default 'translation_log.json' in current directory.",
            exc_info=True,
        )
        TRANSLATION_LOG_FILE = str(Path.cwd() / "translation_log.json")

    _is_module_initialized = True


# The actual creation of the 'logs' directory, if needed, is handled
# later within the '_log_usage' method before writing the file.


# ------------------------------------------------------------------
#  Dataclasses
# ------------------------------------------------------------------
@dataclass
class TranslationJob:
    input_file: str
    content: str
    source_language: str
    target_language: str


@dataclass
class TranslationResult:
    input_file: str
    translated_content: str
    characters_translated: int  # Total chars *billed* by APIs
    service_used: str  # e.g., "deepl", "google", "mixed", "failed", "partial_failure"


# ------------------------------------------------------------------
#  Subtitle/Utility Functions
# ------------------------------------------------------------------


def ensure_correct_timestamp_format(content: str) -> str:
    """
    Ensures SRT timestamps use comma decimal separator and ' --> ' arrow format.
    Corrects common variations like '.' milliseconds or different arrow styles.
    """
    if not isinstance(content, str):
        logger.warning("ensure_correct_timestamp_format expected string, got %s", type(content))
        return content

    try:
        # Regex 1: Replace dot with comma in HH:MM:SS.ms format
        corrected_content = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", content)
        # Regex 2: Standardize ' --> ' arrow format between valid timestamps
        corrected_content = re.sub(
            r"(\d{2}:\d{2}:\d{2},\d{3})\s*--?>\s*(\d{2}:\d{2}:\d{2},\d{3})",
            r"\1 --> \2",
            corrected_content,
        )
        return corrected_content
    except Exception as e:
        logger.error(f"Error correcting timestamp format: {e}", exc_info=True)
        return content  # Return original on error


def correct_text_after_translation(content: str) -> str:
    """
    General post-translation cleanup: Unescape HTML entities.
    """
    if not isinstance(content, str):
        return content
    try:
        # Unescape HTML entities like &, <, >, etc.
        content_unescaped = html.unescape(content)
        # Apply twice for nested entities like <
        content_unescaped = html.unescape(content_unescaped)
        return content_unescaped
    except Exception as e:
        logger.error(f"Error in correct_text_after_translation (unescaping): {e}", exc_info=True)
        return content  # Return original on error


def correct_srt_after_translation(content: str) -> str:
    """
    SRT-specific post-translation cleanup: Unescape HTML and re-ensure timestamp format.
    """
    if not isinstance(content, str):
        return content
    try:
        content_unescaped = correct_text_after_translation(content)
        # Ensure timestamps are correct *after* potential HTML entity changes
        return ensure_correct_timestamp_format(content_unescaped)
    except Exception as e:
        logger.error(f"Error in correct_srt_after_translation: {e}", exc_info=True)
        return content  # Return original on error


def chunk_text_for_translation(text: str, max_length: int) -> list[str]:  # noqa: C901
    """
    Splits a single large text block into chunks <= max_length.
    Prefers sentence boundaries using NLTK if available, falls back to newlines.
    """
    chunks = []
    if not text or not isinstance(text, str) or max_length <= 0:
        return chunks

    elements = []
    element_separator = "\n"  # Default separator if splitting by line

    # Try NLTK sentence splitting if available and successful
    if NLTK_PUNKT_AVAILABLE and sent_tokenize:
        try:
            elements = sent_tokenize(text)
            element_separator = " "  # Rejoin sentences with space for context (adjust if needed)
            logger.debug("Using NLTK sentence tokenization for single text block chunking.")
        except Exception as e:
            logger.warning(
                f"NLTK sentence tokenization failed: {e}. Falling back to line splitting."
            )
            elements = text.splitlines()
            element_separator = "\n"
    else:
        # Fallback to splitting by lines
        elements = text.splitlines()
        element_separator = "\n"
        if nltk is None:
            logger.debug("NLTK not available. Using line splitting for single text block chunking.")
        else:
            logger.debug(
                "NLTK available but 'punkt' data missing/failed. Using line splitting for single text block chunking."
            )

    # --- Chunking logic ---
    current_chunk_parts = []
    current_chunk_len = 0
    for element in elements:
        element = (
            element.strip()
        )  # Work with stripped elements, but join original if needed? For now, use stripped.
        if not element:
            continue

        element_len = len(element)
        # Length of separator to add *before* this element if chunk is not empty
        separator_len = len(element_separator) if current_chunk_len > 0 else 0

        # Check if the element *itself* exceeds the limit
        if element_len > max_length:
            logger.warning(
                f"Single element (sentence/line) length {element_len} exceeds max_length {max_length}. Splitting mid-element."
            )
            # If there's a pending chunk, finalize it first
            if current_chunk_parts:
                chunks.append(element_separator.join(current_chunk_parts))
            # Split the large element itself into pieces based on max_length
            for i in range(0, element_len, max_length):
                chunks.append(element[i : i + max_length])
            # Reset current chunk
            current_chunk_parts = []
            current_chunk_len = 0
            continue  # Move to the next element

        # Check if adding the next element (plus separator) exceeds max length
        if current_chunk_len + element_len + separator_len > max_length:
            # Finalize the current chunk
            if current_chunk_parts:
                chunks.append(element_separator.join(current_chunk_parts))
            # Start a new chunk with the current element
            current_chunk_parts = [element]
            current_chunk_len = element_len
        else:
            # Add element to the current chunk
            current_chunk_parts.append(element)
            current_chunk_len += element_len + separator_len

    # Add the last remaining chunk
    if current_chunk_parts:
        chunks.append(element_separator.join(current_chunk_parts))

    logger.debug(
        f"Split single text block ({len(text)} chars) into {len(chunks)} chunks (max_length={max_length})."
    )
    return chunks


def chunk_text_list_for_translation(  # noqa: C901
    texts: list[str],
    max_length: int,  # Max chars (DeepL) or bytes (Google) per batch
    max_strings: int,  # Max number of strings per batch
    use_bytes: bool = False,  # True for Google, False for DeepL
) -> list[list[str]]:
    """
    Chunks a list of strings into batches for list translation APIs.
    Respects max total length (chars/bytes) AND max number of strings per batch.
    """
    batches = []
    if not texts:
        return batches
    if max_strings <= 0:
        logger.error("max_strings must be positive. Setting to 1.")
        max_strings = 1
    if max_length <= 0:
        logger.error("max_length must be positive. Setting to 100.")
        max_length = 100

    # Define length function based on bytes or characters
    def len_func(s):
        return len(s.encode("utf-8", errors="ignore")) if use_bytes else len(s)

    current_batch = []
    current_batch_len = 0

    for i, text in enumerate(texts):
        # Process even empty strings to maintain list structure integrity
        text_len = len_func(text)

        # Check if the text *itself* is too large for a single batch item
        # Note: Google might have a per-string limit smaller than the per-batch limit.
        # This simple check handles the *batch* limit. API might still reject oversized individual strings.
        if text_len > max_length:
            logger.warning(
                f"Single text segment #{i+1} ({text_len} {'bytes' if use_bytes else 'chars'}) "
                f"exceeds batch max_length {max_length}. Sending as its own potentially oversized batch. "
                f"API may reject it."
            )
            # If there's a pending batch, finalize it first
            if current_batch:
                batches.append(current_batch)
            # Add the oversized item as its own batch
            batches.append([text])
            # Reset for next batch
            current_batch = []
            current_batch_len = 0
            continue

        # Check if adding this text would break limits for the *current* batch
        adding_breaks_length = current_batch_len + text_len > max_length and current_batch
        adding_breaks_count = len(current_batch) >= max_strings

        if adding_breaks_length or adding_breaks_count:
            # Finalize the current batch
            batches.append(current_batch)
            # Start new batch with the current text
            current_batch = [text]
            current_batch_len = text_len
        else:
            # Add text to the current batch
            current_batch.append(text)
            current_batch_len += text_len

    # Add the last batch if it's not empty
    if current_batch:
        batches.append(current_batch)

    # Verification
    total_texts_in_batches = sum(len(b) for b in batches)
    if total_texts_in_batches != len(texts):
        logger.critical(
            f"CRITICAL BATCHING MISMATCH: Original list had {len(texts)} items, batches contain {total_texts_in_batches}. Check chunk_text_list_for_translation logic."
        )
        # Handle error: maybe return empty list or raise exception
        # return [] # Or raise ValueError("Batching mismatch error")

    logger.debug(
        f"Split {len(texts)} text segments into {len(batches)} batches (Max Strings: {max_strings}, Max {'Bytes' if use_bytes else 'Chars'}: {max_length})."
    )
    return batches


# ------------------------------------------------------------------
#  SRT Parsing and Rebuilding
# ------------------------------------------------------------------


def parse_srt_into_segments(srt_content: str) -> list[tuple[str, str, str]]:  # noqa: C901
    """
    Parses SRT content into a list of (index_line, timestamp_line, subtitle_text).
    Robustly handles formatting variations and potential errors.
    """
    segments = []
    if not isinstance(srt_content, str):
        logger.error("SRT parsing failed: Input content is not a string.")
        return segments

    # Pre-process: Ensure basic timestamp format and clean up whitespace
    srt_content = ensure_correct_timestamp_format(srt_content.strip())
    lines = srt_content.splitlines()

    segment_index = 0
    current_index_line = None
    current_ts_line = None
    current_text_lines = []
    state = "index"  # Possible states: index, timestamp, text

    for line_num, line in enumerate(lines, 1):
        stripped_line = line.strip()

        if state == "index":
            if re.fullmatch(r"\d+", stripped_line):
                current_index_line = line  # Keep original line
                state = "timestamp"
            elif stripped_line:  # Non-empty, non-numeric line where index was expected
                logger.warning(
                    f"SRT Parse (Line {line_num}): Expected index number, found: '{line}'. Skipping line."
                )
            # Ignore blank lines when expecting index

        elif state == "timestamp":
            # Use regex for more flexible timestamp matching
            ts_match = re.match(
                r"\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}", stripped_line
            )
            if ts_match:
                # Re-ensure format using the matched part for consistency
                current_ts_line = ensure_correct_timestamp_format(
                    line
                )  # Keep original line spacing if needed
                state = "text"
            elif stripped_line:  # Non-empty, non-timestamp line where timestamp was expected
                logger.warning(
                    f"SRT Parse (Line {line_num}): Expected timestamp 'HH:MM:SS,ms --> HH:MM:SS,ms', found: '{line}'. Resetting segment."
                )
                # Reset state and discard the partial segment
                current_index_line, current_ts_line, current_text_lines = None, None, []
                state = "index"  # Look for a new index
            # Ignore blank lines when expecting timestamp

        elif state == "text":
            if stripped_line:  # Collect non-empty lines as text
                current_text_lines.append(line)  # Keep original line
            else:  # Blank line marks the end of the text block
                if current_index_line and current_ts_line:
                    segment_text = "\n".join(current_text_lines)
                    segments.append((current_index_line, current_ts_line, segment_text))
                    segment_index += 1
                else:
                    # Should not happen if state machine is correct, but safeguard
                    logger.warning(
                        f"SRT Parse (Near Line {line_num}): Reached end of text block (blank line) but missing index or timestamp. Discarding collected text: {current_text_lines}"
                    )

                # Reset for the next segment
                current_index_line, current_ts_line, current_text_lines = None, None, []
                state = "index"  # Expect index next

    # Handle the last segment if the file doesn't end with a blank line
    if state == "text" and current_text_lines:
        if current_index_line and current_ts_line:
            segment_text = "\n".join(current_text_lines)
            segments.append((current_index_line, current_ts_line, segment_text))
            segment_index += 1
        else:
            logger.warning(
                f"SRT Parse (End of File): Reached EOF while collecting text, but missing index or timestamp. Discarding final text: {current_text_lines}"
            )

    if not segments and srt_content:
        logger.warning(
            "SRT parsing resulted in zero segments, although content was provided. Check SRT format."
        )
    elif segments:
        logger.info(f"Parsed {len(segments)} SRT segments.")

    return segments


def rebuild_srt_from_segments(segments: list[tuple[str, str, str]]) -> str:
    """
    Rebuilds an SRT file content string from parsed segments.
    Ensures standard formatting with blank lines between entries.
    """
    if not segments:
        return ""

    srt_blocks = []
    for i, (idx_line, ts_line, text_content) in enumerate(segments):
        # Basic validation
        idx_str = str(idx_line).strip() if idx_line is not None else ""
        ts_str = str(ts_line).strip() if ts_line is not None else ""
        txt_str = str(text_content) if text_content is not None else ""  # Allow empty text

        if not idx_str or "-->" not in ts_str:  # Check if timestamp line looks valid
            logger.warning(
                f"Skipping segment {i+1} during rebuild due to invalid index ('{idx_str}') or timestamp ('{ts_str}')."
            )
            continue

        # Use original lines to preserve potential formatting, ensure they end with newline
        idx_line_fmt = str(idx_line).rstrip("\n") + "\n"
        ts_line_fmt = str(ts_line).rstrip("\n") + "\n"
        txt_fmt = txt_str  # Text content might already have internal newlines

        # Add block: index, timestamp, text (potentially multi-line)
        srt_blocks.append(f"{idx_line_fmt}{ts_line_fmt}{txt_fmt}")

    # Join blocks with exactly one blank line (two newlines)
    result = "\n\n".join(srt_blocks)

    # Ensure the final string ends with exactly one newline if there's content
    if result:
        result = result.strip() + "\n"

    return result


# ------------------------------------------------------------------
#  DeepL Usage Check
# ------------------------------------------------------------------
def get_deepl_usage(api_key: str) -> dict | None:  # noqa: C901
    """Gets usage info for a single DeepL API key (Free or Pro)."""
    if not deepl or not requests:
        logger.error("Cannot check DeepL usage: 'deepl' or 'requests' library not available.")
        return None
    if not api_key:
        logger.warning("Cannot check DeepL usage: API key is empty.")
        return None

    is_free_key = ":fx" in api_key
    url = "https://api-free.deepl.com/v2/usage" if is_free_key else "https://api.deepl.com/v2/usage"
    headers = {"Authorization": f"DeepL-Auth-Key {api_key}"}
    key_suffix = api_key[-8:] if len(api_key) >= 8 else "***"  # Updated to 8 chars for logging

    try:
        response = requests.get(url, headers=headers, timeout=15)  # Increased timeout
        response.raise_for_status()
        usage_data = response.json()

        # Validate response structure
        if (
            isinstance(usage_data, dict)
            and "character_count" in usage_data
            and "character_limit" in usage_data
        ):
            # Ensure values are integers
            usage_data["character_count"] = int(usage_data["character_count"])
            usage_data["character_limit"] = int(usage_data["character_limit"])
            logger.debug(f"DeepL usage check success for '...{key_suffix}'.")
            return usage_data
        else:
            logger.warning(
                f"DeepL usage check for '...{key_suffix}' returned unexpected data format: {usage_data}"
            )
            return None

    except requests.exceptions.HTTPError as http_err:
        status_code = http_err.response.status_code
        response_text = http_err.response.text[:200]
        if status_code == 403:  # Forbidden - Invalid Key
            logger.warning(
                f"DeepL key '...{key_suffix}': Invalid or expired API key (403). Key will be skipped."
            )
        elif status_code == 429:  # Too Many Requests
            logger.warning(f"DeepL key '...{key_suffix}': Rate limited (429). Try again later.")
        elif status_code == 456:  # Quota Exceeded (specific DeepL code)
            logger.warning(
                f"DeepL key '...{key_suffix}': Monthly quota exceeded (456). Key unusable until reset."
            )
            # We can still return a dict indicating quota is full
            return {
                "character_count": DEEPL_QUOTA_PER_KEY,
                "character_limit": DEEPL_QUOTA_PER_KEY,
                "quota_exceeded": True,
            }
        else:
            logger.error(
                f"DeepL usage check HTTP error for key '...{key_suffix}'. Status: {status_code}. Response: '{response_text}...'"
            )
        return None  # Indicate failure for most HTTP errors
    except requests.exceptions.RequestException as req_err:  # Network, Timeout, etc.
        logger.error(f"Network error checking DeepL usage for key '...{key_suffix}': {req_err}")
        return None
    except json.JSONDecodeError as json_err:
        logger.error(
            f"Error decoding DeepL usage JSON response for key '...{key_suffix}': {json_err}. Response text: '{response.text[:200]}...'"
        )
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error during DeepL usage check for key '...{key_suffix}': {e}",
            exc_info=True,
        )
        return None


# ------------------------------------------------------------------
#  Translation Manager Class
# ------------------------------------------------------------------
class TranslationManager:
    """
    Manages translation using DeepL (with key switching/quota management)
    and Google Cloud Translate as a fallback. Handles different content types (SRT, text).
    """

    def translate_file_content(  # Now a method
        self,  # Changed from 'manager'
        input_file: str,
        content: str,
        source_lang: str,  # Keep: Needed for dispatched methods
        target_lang: str,  # Keep: Needed for dispatched methods
    ) -> TranslationResult:
        """
        Main public entry point for translating file content.
        Dispatches to SRT-specific or generic text translation based on file extension.
        """
        # Basic check (usually implicit for methods, but can be added)
        if not self:
            logger.error("Method called without valid instance context.")
            return TranslationResult(input_file, content, 0, "failed_no_manager")

        if not isinstance(content, str):
            logger.error(
                f"Invalid content type for translation (expected str, got {type(content)}). File: {input_file}"
            )
            # Attempt conversion, might still fail later
            content = str(content)

        # --- DEFINE file_basename and file_lower HERE ---
        # Ensure 'os' module is imported at the top of the file
        file_basename = Path(input_file).name if input_file else "Unknown File"
        file_lower = file_basename.lower()
        # --- END DEFINE ---

        # --- SRT Handling ---
        if file_lower.endswith(".srt"):
            logger.debug(f"Processing '{file_basename}' as SRT file ({len(content)} chars)")
            try:
                # Use 'self' to call the other method
                result = self.batched_srt_translate(  # <-- Use self
                    input_file=input_file,
                    srt_content=content,
                    source_lang=source_lang,  # Pass along
                    target_lang=target_lang,  # Pass along
                )
                return result
            except Exception as e:
                logger.error(
                    f"Batched SRT translation failed unexpectedly for '{file_basename}': {e}",
                    exc_info=True,
                )
                return TranslationResult(input_file, content, 0, "failed_srt_exception")

        # --- Plain Text / Other Formats Handling ---
        else:
            logger.debug(
                f"Processing '{file_basename}' as generic text file ({len(content)} chars)"
            )
            # Create the Job object, including the languages
            job = TranslationJob(input_file, content, source_lang, target_lang)
            try:
                # Use 'self' to call the other method
                result = self.translate_generic_text(job)  # <-- Use self
                return result
            except Exception as e:
                logger.error(
                    f"Generic text translation job failed unexpectedly for '{file_basename}': {e}",
                    exc_info=True,
                )
                return TranslationResult(input_file, content, 0, "failed_generic_exception")

    def __init__(self):  # noqa: C901
        # --- Load Configured Settings ---
        # These globals should be populated by an external mechanism before instantiation
        global DEEPL_KEYS, GOOGLE_PROJECT_ID_CONFIG, GOOGLE_CREDENTIALS_PATH, DEEPL_QUOTA_PER_KEY
        self.deepl_keys = [key for key in DEEPL_KEYS if key]  # Filter out empty keys
        self.deepl_quota_per_key = DEEPL_QUOTA_PER_KEY if DEEPL_QUOTA_PER_KEY > 0 else 500000
        self.google_project_id_config = GOOGLE_PROJECT_ID_CONFIG
        self.google_credentials_path = GOOGLE_CREDENTIALS_PATH

        # --- INSERTED DEBUG LINES ---
        logger.debug(
            f"Inside TranslationManager init - self.google_project_id_config: {self.google_project_id_config}"
        )
        logger.debug(
            f"Inside TranslationManager init - self.google_credentials_path: {self.google_credentials_path}"
        )
        # --- END INSERTED DEBUG LINES ---

        # --- Initialize State Variables ---
        self.google_client = None
        self.google_parent = None
        self.google_project_id_num = None  # Stores the validated project ID string
        self.current_deepl_key_index = 0
        self.deepl_usage_cache = {}  # { key_index: {"count": int, "limit": int, "valid": bool} }
        self.google_used_session = 0  # Track chars translated by Google in this run

        # --- Validate DeepL Setup ---
        if not self.deepl_keys:
            logger.warning(
                "No valid DeepL API keys found in configuration. DeepL translation will be unavailable."
            )
        elif not deepl:
            logger.error("'deepl' library is not available. DeepL translation disabled.")
            self.deepl_keys = []  # Clear keys if library is missing

        # --- Validate and Initialize Google Client ---
        google_fully_configured = self.google_project_id_config and self.google_credentials_path
        google_partially_configured = self.google_project_id_config or self.google_credentials_path

        if google_fully_configured:
            if not google_translate or not google_exceptions:
                logger.error(
                    "Google Cloud Translate libraries not available. Google Translate disabled."
                )
            elif not self.google_credentials_path:  # Check if path is non-empty
                logger.error(
                    "Google credentials path is configured but empty. Google Translate disabled."
                )
            elif not Path(self.google_credentials_path).exists():
                logger.error(
                    f"Google credentials file not found at '{self.google_credentials_path}'. Google Translate disabled."
                )
            else:
                try:
                    # Set environment variable for credentials
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.google_credentials_path
                    self.google_client = google_translate.TranslationServiceClient()

                    # Parse Project ID from config (handles full path or just ID)
                    config_value = self.google_project_id_config
                    extracted_project_id = None
                    location = "global"  # Default location
                    # Use regex to parse 'projects/PROJECT_ID/locations/LOCATION' format
                    path_match = re.match(
                        r"projects/([^/]+)(?:/locations/([^/]+))?", config_value
                    )  # Location part optional

                    if path_match:
                        extracted_project_id = path_match.group(1)
                        location = path_match.group(2) or "global"  # Use found location or default
                        logger.info(
                            f"Parsed Google Project ID '{extracted_project_id}' and location '{location}' from config path."
                        )
                    else:
                        # Assume the config value *is* the project ID
                        extracted_project_id = config_value
                        logger.info(
                            f"Assuming config value '{config_value}' is the Google Project ID directly. Using default location '{location}'."
                        )

                    # Validate the extracted project ID
                    if not extracted_project_id:
                        raise ValueError("Could not determine Google Project ID.")
                    # Basic sanity check, allow alphanumeric and hyphens
                    if not re.fullmatch(
                        r"[a-z0-9][a-z0-9-]*[a-z0-9]", extracted_project_id.lower()
                    ):
                        raise ValueError(
                            f"Determined Project ID '{extracted_project_id}' appears invalid."
                        )

                    self.google_project_id_num = extracted_project_id
                    # Construct the parent string required by the API using determined location
                    self.google_parent = (
                        f"projects/{self.google_project_id_num}/locations/{location}"
                    )
                    logger.info(
                        f"Google Translate client initialized. Project ID: {self.google_project_id_num}, API Parent: {self.google_parent}"
                    )

                except ValueError as ve:
                    logger.critical(
                        f"Failed to initialize Google Translate client: Invalid Project ID configuration. Error: {ve} (Config: '{self.google_project_id_config}')"
                    )
                    self._reset_google_state()
                except Exception as e:
                    logger.critical(
                        f"Failed to initialize Google Translate client: {type(e).__name__} - {e}",
                        exc_info=False,
                    )
                    logger.debug("Google init traceback:", exc_info=True)
                    self._reset_google_state()

        elif google_partially_configured:
            logger.warning(
                "Google Translate configuration incomplete (missing Project ID or Credentials Path). Google Translate disabled."
            )
            self._reset_google_state()
        else:
            logger.info("Google Translate not configured. Google Translate disabled.")
            self._reset_google_state()

        # --- Initialize DeepL Usage Cache ---
        if self.deepl_keys:
            self.update_deepl_usage_cache()  # Fetch initial usage

    def _reset_google_state(self):
        """Helper to reset Google-related instance variables."""
        self.google_client = None
        self.google_parent = None
        self.google_project_id_num = None

    def update_deepl_usage_cache(self):
        """Fetches and updates usage info for all configured, valid DeepL keys."""
        if not self.deepl_keys:
            logger.debug("No DeepL keys to update usage cache for.")
            return

        logger.info("Updating DeepL API key usage cache...")
        valid_count = 0
        invalid_count = 0
        for index, key in enumerate(self.deepl_keys):
            key_suffix = key[-4:] if len(key) >= 4 else "***"
            usage_info = get_deepl_usage(key)

            if usage_info:
                count = usage_info.get("character_count", 0)
                api_limit = usage_info.get("character_limit", 0)
                quota_exceeded = usage_info.get("quota_exceeded", False)

                # Use configured quota if it's lower and positive, otherwise use API limit
                effective_limit = api_limit
                if self.deepl_quota_per_key > 0:
                    effective_limit = min(api_limit, self.deepl_quota_per_key)
                # Ensure limit is non-negative
                effective_limit = max(0, effective_limit)

                # Mark as invalid if quota explicitly exceeded via HTTP 456
                is_valid = not quota_exceeded

                self.deepl_usage_cache[index] = {
                    "count": count,
                    "limit": effective_limit,
                    "valid": is_valid,
                }
                status = "VALID" if is_valid else "QUOTA EXCEEDED"
                logger.info(
                    f"  [Key {index+1} ..{key_suffix}]: Usage {count}/{effective_limit} chars. Status: {status}"
                )
                if is_valid:
                    valid_count += 1
                else:
                    invalid_count += 1

            else:  # Usage check failed entirely (e.g., invalid key, network error)
                self.deepl_usage_cache[index] = {"count": 0, "limit": 0, "valid": False}
                logger.warning(
                    f"  [Key {index+1} ..{key_suffix}]: Failed usage check. Marking INVALID."
                )
                invalid_count += 1

        logger.info(
            f"DeepL usage cache update complete. Usable keys: {valid_count}, Invalid/Quota Exceeded: {invalid_count}"
        )

    def _get_current_deepl_key_info(self) -> tuple[int, str | None, int, bool]:
        """Returns (key_index, key_str, available_chars, is_valid) for the current key."""
        num_keys = len(self.deepl_keys)
        if num_keys == 0 or self.current_deepl_key_index >= num_keys:
            return self.current_deepl_key_index, None, 0, False

        key_index = self.current_deepl_key_index
        key = self.deepl_keys[key_index]
        usage = self.deepl_usage_cache.get(key_index)

        if not usage:
            logger.warning(
                f"Usage cache missing for current DeepL key index {key_index}. Assuming invalid."
            )
            return key_index, key, 0, False

        is_valid = usage.get("valid", False)
        if not is_valid:
            return key_index, key, 0, False

        count = usage.get("count", 0)
        limit = usage.get("limit", 0)
        available = max(0, limit - count)
        # Re-validate based on available quota
        is_truly_valid = available > 0

        if not is_truly_valid and is_valid:  # Was marked valid but count >= limit now
            logger.warning(
                f"DeepL Key {key_index+1} is now out of quota ({count}/{limit}). Marking invalid temporarily."
            )
            self.deepl_usage_cache[key_index]["valid"] = False  # Mark invalid in cache
            is_valid = False  # Reflect this in the return value

        return key_index, key, available, is_valid

    def _switch_deepl_key(self) -> bool:
        """
        Cycles to the next DeepL key that is valid and has quota > 0.
        Returns True if a usable key was found (could be the same one), False otherwise.
        """
        num_keys = len(self.deepl_keys)
        if num_keys == 0:
            logger.warning("Cannot switch DeepL key: no keys configured.")
            return False

        start_index = self.current_deepl_key_index
        # Iterate through all keys starting from the *next* one, wrapping around
        for i in range(1, num_keys + 1):  # Check up to num_keys times
            next_index = (start_index + i) % num_keys
            usage = self.deepl_usage_cache.get(next_index)

            if not usage:  # Cache entry missing
                logger.warning(
                    f"Key index {next_index+1} not found in usage cache during switch attempt."
                )
                continue

            is_valid = usage.get("valid", False)
            if not is_valid:  # Skip explicitly invalid keys
                # logger.debug(f"Skipping invalid DeepL key {next_index+1} during switch.")
                continue

            # Check quota for potentially valid keys
            count = usage.get("count", 0)
            limit = usage.get("limit", 0)
            available = max(0, limit - count)

            if available > 0:
                # Found a usable key
                if next_index != start_index:
                    key_suffix = (
                        self.deepl_keys[next_index][-4:]
                        if len(self.deepl_keys[next_index]) >= 4
                        else "***"
                    )
                    logger.info(
                        f"Switched to DeepL key {next_index+1} (..{key_suffix}). Available chars: ~{available}"
                    )
                self.current_deepl_key_index = next_index
                return True  # Usable key found

            else:  # Key was marked valid but has no quota left
                if is_valid:  # Mark it invalid in cache now if we just discovered it's full
                    logger.warning(
                        f"DeepL Key {next_index+1} found to have no quota ({count}/{limit}) during switch. Marking invalid."
                    )
                    self.deepl_usage_cache[next_index]["valid"] = False

        # If loop completes without finding a usable key
        logger.warning("No valid DeepL keys with available quota found after checking all keys.")
        # Consider re-checking usage here if desired, but could be slow
        # self.update_deepl_usage_cache()
        return False

    # --- DeepL Translation Methods ---

    def _translate_deepl_chunk(  # noqa: C901
        self, text: str, target_language: str, source_language: str | None = None
    ) -> tuple[str | None, int]:
        """
        Translates one chunk with the current DeepL key. Internal use.
        Returns (translated_text, characters_billed) or (None, 0) on failure.
        Raises DeepLException or subclasses if API call fails, allowing caller to handle.
        """
        if not deepl:
            return None, 0  # Library check

        key_index, key, available, is_valid = self._get_current_deepl_key_info()
        key_suffix = key[-4:] if key and len(key) >= 4 else "N/A"

        if not is_valid or not key:
            # This condition is logged/handled by the caller trying to switch keys
            raise ValueError(f"No valid DeepL key available (Tried index: {key_index}).")

        # Check for empty input
        clean_text = text.strip()
        if not clean_text:
            return "", 0

        chars_to_bill = len(text)  # DeepL bills based on original input length

        # Pre-flight quota check
        if available <= 0:
            logger.warning(
                f"DeepL Key {key_index+1} (..{key_suffix}) has no available quota ({available})."
            )
            raise deepl.QuotaExceededException("Pre-flight check: No available quota.")
        if chars_to_bill > available:
            logger.warning(
                f"Estimated billing {chars_to_bill} exceeds available quota {available} for key {key_index+1} (..{key_suffix})."
            )
            raise deepl.QuotaExceededException(
                f"Pre-flight check: Billing ({chars_to_bill}) exceeds available quota ({available})."
            )

        # Ensure chunk size limit (should be handled by caller's chunking)
        text_to_send = text
        truncated = False
        if len(text) > DEEPL_MAX_CHUNK_SIZE_FREE:
            logger.warning(
                f"DeepL chunk received text ({len(text)} chars) larger than limit ({DEEPL_MAX_CHUNK_SIZE_FREE}). Truncating."
            )
            text_to_send = text[:DEEPL_MAX_CHUNK_SIZE_FREE]
            # Billing is based on original length by DeepL, so `chars_to_bill` remains `len(text)`.
            truncated = True

        try:
            translator = deepl.Translator(key)
            # Target language mapping (examples)
            tg_lang = target_language.upper()
            if tg_lang == "EN":
                tg_lang = "EN-US"
            elif tg_lang == "PT":
                tg_lang = "PT-PT"  # Or PT-BR if preferred

            src_lang = source_language.upper() if source_language else None

            logger.debug(
                f"DeepL translating chunk ({len(text_to_send)}/{chars_to_bill} sent/billed chars) with key {key_index+1} (..{key_suffix}). Target: {tg_lang}, Source: {src_lang or 'auto'}"
            )

            result = translator.translate_text(
                text_to_send,
                source_lang=src_lang,
                target_lang=tg_lang,
                tag_handling="xml",  # Handles basic HTML/XML tags
                # formality='less' # Example option
            )
            translated_text = result.text

            # Update usage cache immediately after successful call
            if key_index in self.deepl_usage_cache:
                self.deepl_usage_cache[key_index]["count"] += chars_to_bill
                new_count = self.deepl_usage_cache[key_index]["count"]
                limit = self.deepl_usage_cache[key_index].get("limit", 0)
                logger.debug(f"Updated DeepL Key {key_index+1} usage cache: {new_count}/{limit}")

            if truncated:
                translated_text += " [[TRUNCATED]]"

            return translated_text, chars_to_bill

        except deepl.DeepLException as e:
            # Specific DeepL errors are caught and handled by the caller (e.g., key switch)
            logger.error(
                f"DeepL API error on chunk with key {key_index+1} (..{key_suffix}): {type(e).__name__} - {e}"
            )
            if isinstance(e, deepl.AuthorizationException):
                if key_index in self.deepl_usage_cache:
                    self.deepl_usage_cache[key_index]["valid"] = False
                logger.error(
                    f"Marked DeepL Key {key_index+1} as INVALID due to Authorization error."
                )
            elif isinstance(e, deepl.QuotaExceededException):
                if key_index in self.deepl_usage_cache:
                    limit = self.deepl_usage_cache[key_index].get("limit", 0)
                    self.deepl_usage_cache[key_index]["count"] = limit  # Assume full usage
                    self.deepl_usage_cache[key_index]["valid"] = False  # Mark invalid
                logger.warning(f"DeepL Key {key_index+1} hit quota limit. Marked invalid.")
            # Re-raise the specific DeepL error for caller
            raise e
        except Exception as e:
            # Catch unexpected errors during the process
            logger.error(
                f"Unexpected error during DeepL chunk translation with key {key_index+1} (..{key_suffix}): {e}",
                exc_info=True,
            )
            # Wrap in a generic DeepLException or re-raise
            raise deepl.DeepLException(
                f"Unexpected error during DeepL chunk translation: {e}"
            ) from e

    def _translate_deepl_list(  # noqa: C901
        self, texts: list[str], target_language: str, source_language: str | None = None
    ) -> tuple[list[str] | None, int]:
        """
        Translates a list of strings using the current DeepL key. Internal use.
        Returns (list_of_translated_texts, total_characters_billed) or (None, 0).
        Raises DeepLException or subclasses if API call fails.
        """
        if not deepl:
            return None, 0  # Library check

        key_index, key, available, is_valid = self._get_current_deepl_key_info()
        key_suffix = key[-4:] if key and len(key) >= 4 else "N/A"

        if not is_valid or not key:
            raise ValueError(f"No valid DeepL key available (Tried index: {key_index}).")
        if not texts:
            return [], 0

        # Check list size limit (should be handled by caller's batching)
        if len(texts) > DEEPL_MAX_STRINGS_PER_REQUEST:
            logger.error(
                f"DeepL list translation received {len(texts)} strings, exceeding API limit {DEEPL_MAX_STRINGS_PER_REQUEST}. Pre-batching failed."
            )
            raise ValueError(
                f"Batch size {len(texts)} exceeds DeepL string limit {DEEPL_MAX_STRINGS_PER_REQUEST}"
            )

        # Calculate billable characters (sum of lengths) and filter empty strings for API call
        original_indices = []
        texts_to_send_api = []
        chars_to_bill = 0
        for i, text in enumerate(texts):
            chars_to_bill += len(text)  # DeepL bills for all characters in the list
            if text and text.strip():  # Only send non-empty strings to the API
                original_indices.append(i)
                texts_to_send_api.append(text)

        # If all strings were empty/whitespace
        if not texts_to_send_api:
            return list(texts), 0  # Return original list structure, no billing

        # Pre-flight quota check
        if available <= 0:
            logger.warning(
                f"DeepL Key {key_index+1} (..{key_suffix}) has no available quota ({available}) for list."
            )
            raise deepl.QuotaExceededException("Pre-flight check: No available quota for list.")
        if chars_to_bill > available:
            logger.warning(
                f"List billing {chars_to_bill} exceeds available quota {available} for key {key_index+1} (..{key_suffix})."
            )
            raise deepl.QuotaExceededException(
                f"Pre-flight check: List billing ({chars_to_bill}) exceeds available quota ({available})."
            )

        try:
            translator = deepl.Translator(key)
            tg_lang = target_language.upper()
            if tg_lang == "EN":
                tg_lang = "EN-US"
            elif tg_lang == "PT":
                tg_lang = "PT-PT"
            src_lang = source_language.upper() if source_language else None

            logger.debug(
                f"DeepL translating list ({len(texts_to_send_api)} non-empty/{len(texts)} total segments, {chars_to_bill} billed chars) with key {key_index+1} (..{key_suffix}). Target: {tg_lang}, Source: {src_lang or 'auto'}"
            )

            # Call API with only non-empty texts
            results = translator.translate_text(
                texts_to_send_api, source_lang=src_lang, target_lang=tg_lang, tag_handling="xml"
            )

            # Verify result count
            if not isinstance(results, list) or len(results) != len(texts_to_send_api):
                logger.error(
                    f"DeepL list translation size mismatch: Expected {len(texts_to_send_api)} results, got {len(results) if isinstance(results, list) else type(results)}. API Response sample: {str(results)[:200]}"
                )
                # This indicates a significant API issue or bug
                raise deepl.DeepLException(
                    f"List translation result size mismatch (Expected {len(texts_to_send_api)}, Got {len(results) if isinstance(results, list) else 'N/A'})."
                )

            # Reconstruct the full list with original empty strings
            final_translations = list(texts)  # Start with a copy
            for i, result in enumerate(results):
                original_idx = original_indices[i]
                if isinstance(result, deepl.TextResult):
                    final_translations[original_idx] = result.text
                else:  # Should not happen with current API
                    logger.warning(
                        f"Unexpected item type in DeepL results list at index {i}: {type(result)}. Using original text for segment {original_idx}."
                    )
                    final_translations[original_idx] = texts_to_send_api[
                        i
                    ]  # Fallback to original text for that segment

            # Update usage cache
            if key_index in self.deepl_usage_cache:
                self.deepl_usage_cache[key_index]["count"] += chars_to_bill
                new_count = self.deepl_usage_cache[key_index]["count"]
                limit = self.deepl_usage_cache[key_index].get("limit", 0)
                logger.debug(f"Updated DeepL Key {key_index+1} usage cache: {new_count}/{limit}")

            return final_translations, chars_to_bill

        except deepl.DeepLException as e:
            # Handle specific errors and update cache/state as before
            logger.error(
                f"DeepL API error on list with key {key_index+1} (..{key_suffix}): {type(e).__name__} - {e}"
            )
            if isinstance(e, deepl.AuthorizationException):
                if key_index in self.deepl_usage_cache:
                    self.deepl_usage_cache[key_index]["valid"] = False
                logger.error(f"Marked DeepL Key {key_index+1} as INVALID.")
            elif isinstance(e, deepl.QuotaExceededException):
                if key_index in self.deepl_usage_cache:
                    limit = self.deepl_usage_cache[key_index].get("limit", 0)
                    self.deepl_usage_cache[key_index]["count"] = limit
                    self.deepl_usage_cache[key_index]["valid"] = False
                logger.warning(
                    f"DeepL Key {key_index+1} hit quota limit during list. Marked invalid."
                )
            raise e  # Re-raise for caller
        except Exception as e:
            logger.error(
                f"Unexpected error during DeepL list translation with key {key_index+1} (..{key_suffix}): {e}",
                exc_info=True,
            )
            raise deepl.DeepLException(
                f"Unexpected error during DeepL list translation: {e}"
            ) from e

    # --- Google Translation Methods ---

    def _translate_google_chunk(  # noqa: C901
        self, text: str, target_language: str, source_language: str | None = None
    ) -> tuple[str | None, int]:
        """
        Translates one chunk with Google Translate. Internal use.
        Returns (translated_text, characters_billed) or (None, 0) on failure.
        """
        # Check if Google client was initialized successfully
        if not self.google_client or not self.google_parent:
            if not self.google_project_id_config or not self.google_credentials_path:
                logger.debug("Google Translate client not configured, skipping chunk translation.")
            else:
                # Logged critical error during init, just debug log here
                logger.debug(
                    "Google Translate client failed initialization, skipping chunk translation."
                )
            return None, 0

        # Handle empty string input
        clean_text = text.strip()
        if not clean_text:
            return "", 0

        # Google bills characters, but has byte limits per string/request
        chars_to_bill = len(text)
        text_bytes = text.encode("utf-8", errors="ignore")
        text_to_send = text
        truncated = False

        # Check per-string byte limit
        if len(text_bytes) > GOOGLE_MAX_CHUNK_SIZE_BYTES:
            logger.warning(
                f"Google chunk text ({len(text_bytes)} bytes) exceeds per-string limit ({GOOGLE_MAX_CHUNK_SIZE_BYTES}). Truncating bytes."
            )
            # Truncate bytes carefully, decode back ignoring errors
            truncated_bytes = text_bytes[:GOOGLE_MAX_CHUNK_SIZE_BYTES]
            text_to_send = truncated_bytes.decode("utf-8", errors="ignore")
            # Recalculate chars billed based on truncated text sent
            chars_to_bill = len(text_to_send)
            truncated = True
            if not text_to_send:
                logger.error("Truncation resulted in empty string for Google chunk.")
                return "[[TRUNCATION FAILED]]", 0  # Indicate failure

        try:
            request = google_translate.TranslateTextRequest(
                parent=self.google_parent,
                contents=[text_to_send],  # API expects a list
                mime_type="text/plain",  # Use "text/html" if input contains HTML tags
                source_language_code=source_language if source_language else None,
                target_language_code=target_language,
            )
            logger.debug(
                f"Google translating chunk ({chars_to_bill} chars). Target: {target_language}, Source: {source_language or 'auto'}"
            )
            response = self.google_client.translate_text(request=request)

            if not response or not response.translations:
                logger.error("Google Translate returned no translations for chunk.")
                return None, 0

            translated = response.translations[0].translated_text
            self.google_used_session += chars_to_bill  # Track session usage
            logger.debug(
                f"Google chunk translated. Session usage: {self.google_used_session} chars."
            )

            if truncated:
                translated += " [[TRUNCATED]]"

            return translated, chars_to_bill

        except google_exceptions.InvalidArgument as e:
            # Often indicates exceeding request size limits (total bytes, strings, etc.)
            logger.error(
                f"Google API InvalidArgument error on chunk (check limits, languages): {e}",
                exc_info=False,
            )
            return None, 0
        except google_exceptions.GoogleAPICallError as e:  # More general API errors
            logger.error(f"Google API call error on chunk: {e}", exc_info=True)
            return None, 0
        except Exception as e:
            logger.error(f"Unexpected Google error during chunk translation: {e}", exc_info=True)
            return None, 0

    def _translate_google_list(
        self, texts: list[str], target_language: str, source_language: str | None = None
    ) -> tuple[list[str] | None, int]:
        """
        Translates a list of strings using Google Translate. Internal use.
        Returns (list_of_translated_texts, total_characters_billed) or (None, 0).
        """
        # Check if Google client was initialized successfully
        if not self.google_client or not self.google_parent:
            if not self.google_project_id_config or not self.google_credentials_path:
                logger.debug("Google Translate client not configured, skipping list translation.")
            else:
                logger.debug(
                    "Google Translate client failed initialization, skipping list translation."
                )
            return None, 0
        if not texts:
            return [], 0

        # Check string count limit (warn if exceeded, API might handle it)
        if len(texts) > GOOGLE_MAX_STRINGS_PER_REQUEST:
            logger.warning(
                f"Google list translation received {len(texts)} strings, exceeding recommended limit {GOOGLE_MAX_STRINGS_PER_REQUEST}. API might reject or perform poorly."
            )

        # Calculate total characters billed (sum of lengths)
        total_chars_to_bill = sum(len(t) for t in texts)
        if total_chars_to_bill == 0:  # If list contains only empty strings
            return list(texts), 0

        # Note: Google's SDK/API should handle total byte limits, raising InvalidArgument if exceeded.
        # We don't pre-calculate total bytes here unless proving necessary.

        try:
            request = google_translate.TranslateTextRequest(
                parent=self.google_parent,
                contents=texts,  # Send the list as is (API handles empty strings)
                mime_type="text/plain",
                source_language_code=source_language if source_language else None,
                target_language_code=target_language,
            )
            logger.debug(
                f"Google translating list ({len(texts)} segments, {total_chars_to_bill} billable chars). Target: {target_language}, Source: {source_language or 'auto'}"
            )
            response = self.google_client.translate_text(request=request)

            # Validate response
            if (
                not response
                or not response.translations
                or len(response.translations) != len(texts)
            ):
                expected_count = len(texts)
                received_count = (
                    len(response.translations) if response and response.translations else 0
                )
                logger.error(
                    f"Google Translate list returned mismatched translation count. Expected {expected_count}, got {received_count}."
                )
                return None, 0

            translated_list = [t.translated_text for t in response.translations]
            self.google_used_session += total_chars_to_bill
            logger.debug(
                f"Google list translated. Session usage: {self.google_used_session} chars."
            )

            return translated_list, total_chars_to_bill

        except google_exceptions.InvalidArgument as e:
            logger.error(
                f"Google API InvalidArgument error on list (check limits, languages): {e}",
                exc_info=False,
            )
            return None, 0
        except google_exceptions.GoogleAPICallError as e:
            logger.error(f"Google API call error during list translation: {e}", exc_info=True)
            return None, 0
        except Exception as e:
            logger.error(f"Unexpected Google error during list translation: {e}", exc_info=True)
            return None, 0

    # --- Main Translation Logic ---

    def batched_srt_translate(  # noqa: C901
        self, input_file: str, srt_content: str, source_lang: str, target_lang: str
    ) -> TranslationResult:
        """
        Translates SRT content using batched list translation for efficiency.
        Uses DeepL first, falls back to Google per batch.
        """
        start_time = time.monotonic()
        logger.info(f"Starting batched SRT translation for: {Path(input_file).name}")

        original_segments = parse_srt_into_segments(srt_content)
        if not original_segments:
            logger.warning(
                f"No valid segments parsed from {input_file}. Returning original content."
            )
            return TranslationResult(input_file, srt_content, 0, "failed_parsing")

        texts_to_translate = [seg[2] for seg in original_segments]  # List of text blocks

        # --- Batching Strategy for DeepL ---
        # Use DeepL limits first as it's preferred.
        deepl_batches = chunk_text_list_for_translation(
            texts=texts_to_translate,
            max_length=DEEPL_MAX_CHUNK_SIZE_FREE,  # Character limit for batch payload (approx)
            max_strings=DEEPL_MAX_STRINGS_PER_REQUEST,
            use_bytes=False,
        )
        logger.info(
            f"Split {len(texts_to_translate)} SRT text segments into {len(deepl_batches)} batches for DeepL."
        )

        all_translated_texts = []
        total_billed_chars = 0
        service_summary_parts = []  # Track service used per *original DeepL batch*
        batch_billing_details = []  # Store {"service": str, "chars": int, "batch_index": int}

        original_text_index = 0  # Track progress through texts_to_translate

        # --- Process Batches ---
        for i, deepl_batch in enumerate(deepl_batches):
            batch_start_time = time.monotonic()
            batch_idx = i + 1
            if not deepl_batch:
                logger.warning(f"Skipping empty batch #{batch_idx}")
                continue

            batch_size = len(deepl_batch)
            current_batch_texts_original = texts_to_translate[
                original_text_index : original_text_index + batch_size
            ]
            if len(current_batch_texts_original) != batch_size:
                logger.critical(
                    f"Batch {batch_idx}: Mismatch between deepl_batch size ({batch_size}) and sliced original texts ({len(current_batch_texts_original)}). Aborting batch."
                )
                # Handle error: append failures for this batch
                all_translated_texts.extend(
                    [f"[[FAIL:BATCH_INDEX_ERROR]] {txt}" for txt in current_batch_texts_original]
                )
                service_summary_parts.append("failed_internal")
                batch_billing_details.append(
                    {"service": "failed_internal", "chars": 0, "batch_index": batch_idx}
                )
                original_text_index += len(current_batch_texts_original)  # Try to recover index
                continue

            translated_batch_texts = None
            billed_chars_batch = 0
            service_used_for_batch = "failed"
            last_exception_batch = None

            # --- Try DeepL for the batch ---
            if self.deepl_keys:  # Only attempt if DeepL keys are configured
                should_retry_deepl = True
                while should_retry_deepl:
                    should_retry_deepl = False  # Assume no retry unless key switches
                    current_key_idx_batch = self.current_deepl_key_index
                    try:
                        translated_batch_texts, billed_chars_batch = self._translate_deepl_list(
                            deepl_batch, target_lang, source_lang
                        )
                        # _translate_deepl_list returns None on certain errors, but raises on API/Quota/Auth errors
                        if translated_batch_texts is not None:
                            service_used_for_batch = f"deepl_key_{current_key_idx_batch + 1}"
                            logger.info(
                                f"Batch {batch_idx}/{len(deepl_batches)} (Size: {batch_size}): Translated via {service_used_for_batch}."
                            )
                            break  # Success, exit DeepL attempts for this batch
                        else:
                            # This case should be rare if exceptions are raised correctly
                            logger.error(
                                f"Batch {batch_idx}: _translate_deepl_list returned None unexpectedly. Treating as failure."
                            )
                            last_exception_batch = RuntimeError(
                                "_translate_deepl_list returned None"
                            )
                            break  # Exit DeepL attempts

                    except (
                        deepl.QuotaExceededException,
                        deepl.AuthorizationException,
                        ValueError,
                        deepl.DeepLException,
                    ) as e:
                        last_exception_batch = e
                        logger.warning(
                            f"Batch {batch_idx}: DeepL Key {current_key_idx_batch+1} failed: {type(e).__name__}. Attempting key switch or fallback."
                        )
                        # Try switching key. If successful and key *changed*, retry.
                        if (
                            self._switch_deepl_key()
                            and self.current_deepl_key_index != current_key_idx_batch
                        ):
                            logger.info(f"Batch {batch_idx}: Switched key. Retrying DeepL.")
                            should_retry_deepl = True  # Loop again with the new key
                        else:
                            # Switch failed, or no *new* usable key found, or non-recoverable error
                            logger.warning(
                                f"Batch {batch_idx}: DeepL key switch failed or no new key available. Falling back to Google Translate API."
                            )
                            translated_batch_texts = None  # Ensure fallback is triggered
                            break  # Exit DeepL attempts

                    except Exception as e:  # Catch other unexpected errors
                        last_exception_batch = e
                        logger.error(
                            f"Batch {batch_idx}: Unexpected DeepL error on Key {current_key_idx_batch+1}: {e}. Falling back.",
                            exc_info=True,
                        )
                        translated_batch_texts = None
                        break  # Exit DeepL attempts
            else:
                logger.info(f"Batch {batch_idx}: DeepL not configured. Skipping DeepL attempt.")
                translated_batch_texts = None  # Proceed directly to Google fallback

            # --- Fallback to Google for the batch if DeepL failed or wasn't used ---
            if translated_batch_texts is None:
                if self.google_client:  # Check if Google is available
                    # Build a user-friendly reason for the fallback
                    fallback_reason = "DeepL unavailable"
                    if last_exception_batch:
                        if isinstance(last_exception_batch, ValueError):
                            fallback_reason = "No valid DeepL keys available"
                        else:
                            fallback_reason = f"DeepL error: {type(last_exception_batch).__name__}"
                    logger.info(
                        f"Batch {batch_idx}: Falling back to Google Translate. Reason: {fallback_reason}"
                    )

                    # Re-chunk the *current DeepL batch* for Google's limits
                    google_sub_batches = chunk_text_list_for_translation(
                        texts=deepl_batch,  # Chunk the texts from the current DeepL batch
                        max_length=GOOGLE_MAX_CHUNK_SIZE_BYTES,  # Google uses bytes
                        max_strings=GOOGLE_MAX_STRINGS_PER_REQUEST,
                        use_bytes=True,
                    )
                    if len(google_sub_batches) > 1:
                        logger.debug(
                            f"Batch {batch_idx}: Sub-batching for Google resulted in {len(google_sub_batches)} chunks."
                        )

                    temp_google_translations = []
                    google_billed_total = 0
                    google_batch_success = True

                    for sub_batch_idx, google_chunk in enumerate(google_sub_batches):
                        if not google_chunk:
                            continue
                        try:
                            chunk_translation, chunk_billed = self._translate_google_list(
                                google_chunk, target_lang, source_lang
                            )
                            if chunk_translation is not None:  # Check if sub-chunk succeeded
                                temp_google_translations.extend(chunk_translation)
                                google_billed_total += chunk_billed
                            else:
                                logger.error(
                                    f"Google fallback failed for sub-chunk {sub_batch_idx+1}/{len(google_sub_batches)} within Batch {batch_idx}. Marking batch as partially failed."
                                )
                                google_batch_success = False
                                # Append original texts for the failed sub-chunk with markers
                                failed_sub_chunk_originals = list(
                                    google_chunk
                                )  # Get originals corresponding to this sub-batch
                                temp_google_translations.extend(
                                    [
                                        f"[[FAIL-G:SUB_BATCH]] {txt}"
                                        for txt in failed_sub_chunk_originals
                                    ]
                                )
                                # Continue processing other sub-chunks unless we want to fail the whole batch on first error

                        except Exception as e:
                            logger.error(
                                f"Unexpected error during Google fallback sub-chunk {sub_batch_idx+1} of Batch {batch_idx}: {e}",
                                exc_info=True,
                            )
                            google_batch_success = False
                            failed_sub_chunk_originals = list(google_chunk)
                            temp_google_translations.extend(
                                [
                                    f"[[FAIL-G:SUB_BATCH_EXC]] {txt}"
                                    for txt in failed_sub_chunk_originals
                                ]
                            )

                    # Assess outcome of Google fallback attempt for the whole original batch
                    if google_batch_success:
                        translated_batch_texts = temp_google_translations
                        billed_chars_batch = google_billed_total
                        service_used_for_batch = "google_api"
                        logger.info(
                            f"Batch {batch_idx}: Translated via Google fallback (potentially {len(google_sub_batches)} sub-batches)."
                        )
                    else:
                        # Use the partially failed list from Google attempt
                        translated_batch_texts = (
                            temp_google_translations  # Contains markers for failed parts
                        )
                        billed_chars_batch = google_billed_total  # Log partial billing
                        service_used_for_batch = (
                            "failed_google_fallback"  # Indicate partial/full failure
                        )
                        logger.error(
                            f"Batch {batch_idx}: Google fallback translation failed or partially failed."
                        )

                else:  # Google client not available
                    logger.error(
                        f"Batch {batch_idx}: DeepL failed and Google Translate is not configured/available. Translation failed for this batch."
                    )
                    service_used_for_batch = "failed_no_fallback"
                    translated_batch_texts = None  # Ensure failure state persists

            # --- Process Batch Result ---
            if translated_batch_texts is not None and len(translated_batch_texts) == batch_size:
                # Success (either DeepL or full Google fallback)
                all_translated_texts.extend(translated_batch_texts)
                total_billed_chars += billed_chars_batch
                service_summary_parts.append(service_used_for_batch)
                batch_billing_details.append(
                    {
                        "service": service_used_for_batch,
                        "chars": billed_chars_batch,
                        "batch_index": batch_idx,
                    }
                )
            else:
                # Failure for the batch (DeepL failed, Google failed/unavailable, or size mismatch)
                failure_reason = (
                    "mismatched_size"
                    if translated_batch_texts is not None
                    else service_used_for_batch
                )
                logger.error(
                    f"Batch {batch_idx} translation failed ({failure_reason}). Using original text for {batch_size} segments."
                )
                failed_marker = f"[[FAIL:{failure_reason}]]"
                # Use the original texts corresponding to this specific batch
                all_translated_texts.extend(
                    [f"{failed_marker} {txt}" for txt in current_batch_texts_original]
                )
                service_summary_parts.append(
                    service_used_for_batch
                    if service_used_for_batch.startswith("failed")
                    else "failed"
                )
                batch_billing_details.append(
                    {"service": service_used_for_batch, "chars": 0, "batch_index": batch_idx}
                )

            original_text_index += batch_size  # Move index forward by processed batch size
            batch_duration = time.monotonic() - batch_start_time
            logger.debug(f"Batch {batch_idx} processing took {batch_duration:.2f} seconds.")

        # --- Final Checks and Reconstruction ---
        if len(all_translated_texts) != len(original_segments):
            logger.critical(
                f"CRITICAL MISMATCH after processing all batches: "
                f"Expected {len(original_segments)} translated segments, but collected {len(all_translated_texts)}. "
                f"This indicates a flaw in batch processing logic. Returning original content."
            )
            # Log details for debugging
            logger.debug(f"Original segment count: {len(original_segments)}")
            logger.debug(f"Collected translated text count: {len(all_translated_texts)}")
            logger.debug(f"Service summary parts: {service_summary_parts}")
            return TranslationResult(input_file, srt_content, total_billed_chars, "failed_mismatch")

        # Rebuild SRT with translated text
        new_segments = []
        for i, (idx_line, ts_line, _) in enumerate(original_segments):
            # Safety check for index out of bounds (should be caught by mismatch check above)
            if i < len(all_translated_texts):
                # Apply general text corrections (like unescaping) to the translated text *before* rebuilding
                corrected_text = correct_text_after_translation(all_translated_texts[i])
                new_segments.append((idx_line, ts_line, corrected_text))
            else:
                # This case should ideally not be reached due to the mismatch check
                logger.error(
                    f"Index {i} out of bounds for translated texts during SRT rebuild. Skipping segment."
                )

        final_srt = rebuild_srt_from_segments(new_segments)
        # Apply SRT-specific corrections (timestamp format) after rebuilding
        final_srt = ensure_correct_timestamp_format(final_srt)  # Ensure timestamps one last time

        # Summarize overall service usage
        final_service_status = self._summarize_service_status(service_summary_parts)

        # Log detailed usage for this file
        deepl_billed = sum(
            d["chars"] for d in batch_billing_details if d["service"].startswith("deepl")
        )
        google_billed = sum(
            d["chars"] for d in batch_billing_details if d["service"] == "google_api"
        )
        self._log_usage(
            deepl_chars=deepl_billed,
            google_chars=google_billed,
            file_name=input_file,
            service_details=list(set(service_summary_parts)),  # Unique raw services used
            billing_details=batch_billing_details,  # NEW: Pass detailed billing
            target_lang=target_lang,
            source_lang=source_lang,
        )

        total_duration = time.monotonic() - start_time
        logger.info(
            f"Finished batched SRT translation for {Path(input_file).name} in {total_duration:.2f}s. Status: {final_service_status}, Billed: {total_billed_chars} chars."
        )

        return TranslationResult(input_file, final_srt, total_billed_chars, final_service_status)

    def translate_generic_text(self, job: TranslationJob) -> TranslationResult:  # noqa: C901
        """
        Translates generic text content (non-SRT).
        Uses character-based chunking and fallback logic per chunk.
        """
        start_time = time.monotonic()
        logger.info(f"Starting generic text translation for: {Path(job.input_file).name}")
        original_content = job.content

        # Use standard text chunking based on characters/sentences
        # Use DeepL's limit for chunking as it's usually smaller/preferred
        chunks = chunk_text_for_translation(original_content, DEEPL_MAX_CHUNK_SIZE_FREE)

        if not chunks and original_content and original_content.strip():
            logger.warning(
                "Chunking resulted in no chunks for non-empty content. Using original content as one chunk."
            )
            chunks = [original_content]
        elif not chunks:
            logger.info(
                f"Content for {job.input_file} is empty or whitespace only. No translation needed."
            )
            return TranslationResult(job.input_file, "", 0, "no_content")

        translated_chunks = []
        total_chars_billed = 0
        service_details = []  # Track service per chunk: "deepl_key_X", "google_api", "failed"
        chunk_billing_details = []  # Store {"service": str, "chars": int, "chunk_index": int}

        for i, chunk in enumerate(chunks):
            chunk_idx = i + 1
            # Skip empty/whitespace chunks resulting from splitting
            if not chunk or not chunk.strip():
                translated_chunks.append(chunk)  # Preserve empty lines if necessary?
                continue

            translated_chunk_text = None
            billed_chars_chunk = 0
            chunk_service = "failed"
            last_exception_chunk = None

            # --- Try DeepL First ---
            if self.deepl_keys:
                should_retry_deepl_chunk = True
                while should_retry_deepl_chunk:
                    should_retry_deepl_chunk = False
                    current_key_idx_chunk = self.current_deepl_key_index
                    try:
                        # _translate_deepl_chunk raises exceptions on failure
                        translated_chunk_text, billed_chars_chunk = self._translate_deepl_chunk(
                            chunk, job.target_language, job.source_language
                        )
                        if translated_chunk_text is not None:  # Should always be str or raise error
                            chunk_service = f"deepl_key_{current_key_idx_chunk + 1}"
                            logger.info(
                                f"Chunk {chunk_idx}/{len(chunks)}: Translated via {chunk_service}."
                            )
                            break  # Success for this chunk
                        else:
                            # Should not happen if exceptions are raised correctly
                            logger.error(
                                f"Chunk {chunk_idx}: _translate_deepl_chunk returned None unexpectedly."
                            )
                            last_exception_chunk = RuntimeError(
                                "_translate_deepl_chunk returned None"
                            )
                            break

                    except (
                        deepl.QuotaExceededException,
                        deepl.AuthorizationException,
                        ValueError,
                        deepl.DeepLException,
                    ) as e:
                        last_exception_chunk = e
                        logger.warning(
                            f"Chunk {chunk_idx}: DeepL Key {current_key_idx_chunk+1} failed: {type(e).__name__}. Switching key."
                        )
                        if (
                            self._switch_deepl_key()
                            and self.current_deepl_key_index != current_key_idx_chunk
                        ):
                            logger.info(f"Chunk {chunk_idx}: Switched key. Retrying DeepL.")
                            should_retry_deepl_chunk = True
                        else:
                            logger.warning(
                                f"Chunk {chunk_idx}: DeepL key switch failed or no new key. Breaking DeepL attempts."
                            )
                            translated_chunk_text = None  # Ensure fallback
                            break  # Exit while loop

                    except Exception as e:
                        last_exception_chunk = e
                        logger.error(
                            f"Chunk {chunk_idx}: Unexpected DeepL error with key {current_key_idx_chunk+1}: {e}",
                            exc_info=True,
                        )
                        translated_chunk_text = None  # Ensure fallback
                        break  # Exit while loop
            else:
                logger.debug(f"Chunk {chunk_idx}: DeepL not configured.")
                translated_chunk_text = None

            # --- Fallback to Google if DeepL failed ---
            if translated_chunk_text is None:
                if self.google_client:
                    # Build a user-friendly reason for the fallback
                    fallback_reason = "DeepL unavailable"
                    if last_exception_chunk:
                        if isinstance(last_exception_chunk, ValueError):
                            fallback_reason = "No valid DeepL keys available"
                        else:
                            fallback_reason = f"DeepL error: {type(last_exception_chunk).__name__}"
                    logger.info(
                        f"Chunk {chunk_idx}: Falling back to Google. Reason: {fallback_reason}"
                    )
                    try:
                        translated_chunk_text, billed_chars_chunk = self._translate_google_chunk(
                            chunk, job.target_language, job.source_language
                        )
                        if translated_chunk_text is not None:  # Check Google succeeded
                            chunk_service = "google_api"
                            logger.info(f"Chunk {chunk_idx}: Translated via Google fallback.")
                        else:
                            logger.error(
                                f"Chunk {chunk_idx}: Google fallback translation also failed."
                            )
                            chunk_service = "failed_google_fallback"
                            # translated_chunk_text remains None

                    except Exception as e:
                        logger.error(
                            f"Chunk {chunk_idx}: Unexpected Google fallback error: {e}",
                            exc_info=True,
                        )
                        chunk_service = "failed_google_exception"
                        translated_chunk_text = None
                else:
                    logger.error(
                        f"Chunk {chunk_idx}: DeepL failed and Google is not available. Translation failed."
                    )
                    chunk_service = "failed_no_fallback"
                    translated_chunk_text = None

            # --- Process Chunk Result ---
            if translated_chunk_text is not None:
                # Apply general text corrections (like unescaping)
                corrected_chunk = correct_text_after_translation(translated_chunk_text)
                translated_chunks.append(corrected_chunk)
                total_chars_billed += billed_chars_chunk
                service_details.append(chunk_service)
                chunk_billing_details.append(
                    {
                        "service": chunk_service,
                        "chars": billed_chars_chunk,
                        "chunk_index": chunk_idx,
                    }
                )
            else:
                logger.error(
                    f"Chunk {chunk_idx} failed translation permanently ({chunk_service}). Using original chunk."
                )
                translated_chunks.append(
                    f"[[[FAIL:{chunk_service}]]]\n{chunk}"
                )  # Append original with marker
                service_details.append(
                    chunk_service if chunk_service.startswith("failed") else "failed"
                )
                chunk_billing_details.append(
                    {"service": chunk_service, "chars": 0, "chunk_index": chunk_idx}
                )

        # Reconstruct the full text (typically just joining chunks with newlines)
        # The original separator might be better depending on chunking strategy (sentences vs lines)
        final_translated = "\n".join(translated_chunks)

        # Summarize overall service usage
        final_service_status = self._summarize_service_status(service_details)

        # Log detailed usage for this file
        deepl_billed = sum(
            d["chars"] for d in chunk_billing_details if d["service"].startswith("deepl")
        )
        google_billed = sum(
            d["chars"] for d in chunk_billing_details if d["service"] == "google_api"
        )
        self._log_usage(
            deepl_chars=deepl_billed,
            google_chars=google_billed,
            file_name=job.input_file,
            service_details=list(set(service_details)),
            target_lang=job.target_language,
            source_lang=job.source_language,
        )

        total_duration = time.monotonic() - start_time
        logger.info(
            f"Finished generic text translation for {Path(job.input_file).name} in {total_duration:.2f}s. Status: {final_service_status}, Billed: {total_chars_billed} chars."
        )

        return TranslationResult(
            job.input_file, final_translated, total_chars_billed, final_service_status
        )

    def _summarize_service_status(self, service_details: list[str]) -> str:
        """Determines the overall status string based on per-batch/chunk results."""
        if not service_details:
            return "no_action"

        has_failures = any(s.startswith("failed") for s in service_details)
        # Successful services are those not starting with 'failed'
        successful_services = [s for s in service_details if not s.startswith("failed")]
        has_success = bool(successful_services)
        # Get unique base services used (e.g., 'deepl', 'google')
        unique_success_bases = {s.split("_")[0] for s in successful_services if s}

        if has_failures and has_success:
            return "partial_failure"
        elif has_success:
            if len(unique_success_bases) > 1:
                return "mixed"  # e.g., some batches deepl, some google
            elif len(unique_success_bases) == 1:
                base = next(iter(unique_success_bases))
                return (
                    "google" if base == "google_api" else base
                )  # Return 'google' instead of 'google_api'
            else:  # Should not happen if has_success is true
                return "unknown_success"
        elif has_failures:
            return "failed"  # Only failures occurred
        else:  # Only "no_action" or empty details?
            return "no_action"

    def _log_usage(  # noqa: C901
        self,
        deepl_chars: int,
        google_chars: int,
        file_name: str,
        service_details: list[str],
        billing_details: list[dict] | None = None,
        output_file_path: str | None = None,
        target_lang: str | None = None,
        source_lang: str | None = None,
    ):
        """Logs translation usage details to the JSON log file and Database."""
        global TRANSLATION_LOG_FILE, DATABASE_AVAILABLE, SyncSessionLocal, DeepLUsage
        if not TRANSLATION_LOG_FILE:
            logger.error("Translation log file path not set. Skipping usage logging.")
            return

        # 1. Update Database (New)
        if DATABASE_AVAILABLE and SyncSessionLocal and DeepLUsage:
            try:
                with SyncSessionLocal() as db:
                    # Update counts for each key used
                    if billing_details:
                        # Aggregate by service
                        deepl_usage_updates = {}  # {key_hash: {"count": int, "limit": int, "valid": bool}}

                        import hashlib

                        for detail in billing_details:
                            service = detail.get("service", "")
                            if service.startswith("deepl_key_"):
                                try:
                                    idx = int(service.replace("deepl_key_", "")) - 1
                                    if 0 <= idx < len(self.deepl_keys):
                                        key_str = self.deepl_keys[idx]
                                        # Use standard SHA256 hash for identifier
                                        key_hash = hashlib.sha256(
                                            key_str.strip().encode()
                                        ).hexdigest()

                                        # Get latest info from cache or just use billed chars
                                        info = self.deepl_usage_cache.get(idx, {})
                                        count_incr = detail.get("chars", 0)

                                        if key_hash not in deepl_usage_updates:
                                            deepl_usage_updates[key_hash] = {
                                                "count_incr": 0,
                                                "limit": info.get("limit", 500000),
                                                "valid": info.get("valid", True),
                                            }
                                        deepl_usage_updates[key_hash]["count_incr"] += count_incr
                                        # Update limit/validity if we have more recent info in cache
                                        if info.get("limit"):
                                            deepl_usage_updates[key_hash]["limit"] = info["limit"]
                                        if "valid" in info:
                                            deepl_usage_updates[key_hash]["valid"] = info["valid"]
                                except (ValueError, IndexError):
                                    continue

                        for key_hash, data in deepl_usage_updates.items():
                            usage_record = (
                                db.query(DeepLUsage)
                                .filter(DeepLUsage.key_identifier == key_hash)
                                .first()
                            )
                            if not usage_record:
                                usage_record = DeepLUsage(
                                    key_identifier=key_hash,
                                    character_count=data["count_incr"],
                                    character_limit=data["limit"],
                                    valid=data["valid"],
                                )
                                db.add(usage_record)
                                logger.debug(
                                    f"Created new DeepL usage record for key: {key_hash[:16]}..."
                                )
                            else:
                                usage_record.character_count += data["count_incr"]
                                # Only update limit if it changed and we have a valid value
                                if data["limit"] and data["limit"] != 500000:
                                    usage_record.character_limit = data["limit"]
                                usage_record.valid = data["valid"]
                                logger.debug(
                                    f"Updated DeepL usage for key {key_hash[:16]}...: +{data['count_incr']} chars"
                                )

                        db.commit()

                    # --- NEW: Log the translation job itself ---
                    if TranslationLog:
                        # Determine overall status
                        overall_status = self._summarize_service_status(service_details)

                        log_entry = TranslationLog(
                            file_name=file_name,
                            source_language=source_lang,
                            target_language=target_lang or "unknown",
                            service_used=overall_status,
                            characters_billed=deepl_chars + google_chars,
                            deepl_characters=deepl_chars,
                            google_characters=google_chars,
                            status="success"
                            if overall_status not in ("failed", "partial_failure")
                            else overall_status,
                            output_file_path=output_file_path,
                        )
                        db.add(log_entry)
                        db.commit()
                        logger.debug(f"Logged translation job for file: {file_name}")

            except Exception as e:
                logger.error(f"CRITICAL Database error in _log_usage: {e}", exc_info=True)
                raise  # Propagate error so job fails properly

        # 2. Update JSON Log (Maintain for backward compatibility/backup)
        try:
            log_data = {
                "log_schema_version": "1.1",  # Add versioning
                "cumulative_totals": {"deepl": 0, "google": 0, "overall": 0, "last_updated": None},
                "jobs": [],
                "deepl_keys_snapshot": {},
            }
            if Path(TRANSLATION_LOG_FILE).exists():
                try:
                    with Path(TRANSLATION_LOG_FILE).open(encoding="utf-8") as f:
                        log_data = json.load(f)
                    # Basic validation/migration for older format
                    if "total_chars" in log_data and "cumulative_totals" not in log_data:
                        log_data["cumulative_totals"] = log_data.pop("total_chars")
                        log_data["cumulative_totals"]["last_updated"] = None
                    if "files" in log_data and "jobs" not in log_data:
                        log_data["jobs"] = log_data.pop("files")
                    if (
                        "deepl_keys_usage_snapshot" in log_data
                        and "deepl_keys_snapshot" not in log_data
                    ):
                        log_data["deepl_keys_snapshot"] = log_data.pop("deepl_keys_usage_snapshot")

                    # Ensure current structure exists
                    log_data.setdefault("log_schema_version", "1.0")  # Mark older logs
                    log_data.setdefault(
                        "cumulative_totals",
                        {"deepl": 0, "google": 0, "overall": 0, "last_updated": None},
                    )
                    log_data["cumulative_totals"].setdefault("deepl", 0)
                    log_data["cumulative_totals"].setdefault("google", 0)
                    log_data.setdefault("jobs", [])
                    log_data.setdefault("deepl_keys_snapshot", {})

                except (OSError, json.JSONDecodeError, TypeError, KeyError) as e:
                    logger.warning(
                        f"Log file '{TRANSLATION_LOG_FILE}' invalid, unreadable, or old format: {e}. Re-initializing log."
                    )
                    # Use default structure initialized above

            # Update cumulative totals
            current_time_iso = datetime.now(UTC).isoformat()
            log_data["cumulative_totals"]["deepl"] = (
                log_data["cumulative_totals"].get("deepl", 0) + deepl_chars
            )
            log_data["cumulative_totals"]["google"] = (
                log_data["cumulative_totals"].get("google", 0) + google_chars
            )
            log_data["cumulative_totals"]["overall"] = (
                log_data["cumulative_totals"]["deepl"] + log_data["cumulative_totals"]["google"]
            )  # Recalculate overall
            log_data["cumulative_totals"]["last_updated"] = current_time_iso

            # Create entry for this specific job
            job_entry = {
                "file_basename": Path(file_name).name
                if file_name
                else "Unknown",  # Handle potential None
                "timestamp_utc": current_time_iso,
                "billed_chars": {
                    "deepl": deepl_chars,
                    "google": google_chars,
                    "total": deepl_chars + google_chars,
                },
                # Provide a sorted, unique list of raw service identifiers used
                "services_used_raw": sorted(set(service_details)) if service_details else ["none"],
                "overall_status": self._summarize_service_status(
                    service_details
                ),  # Add summary status
            }
            log_data["jobs"].append(job_entry)

            # Update the snapshot of DeepL key usage based on the current cache state
            for key_idx, usage_info in self.deepl_usage_cache.items():
                key_id = f"key_{key_idx+1}"  # Consistent identifier
                log_data["deepl_keys_snapshot"][key_id] = {
                    "count": usage_info.get("count", "N/A"),
                    "limit": usage_info.get("limit", "N/A"),
                    "valid": usage_info.get("valid", False),  # Default to False if missing
                    "snapshot_timestamp_utc": current_time_iso,
                }

            # Write updated log data back to file
            try:
                log_dir = Path(TRANSLATION_LOG_FILE).parent
                if log_dir and not log_dir.exists():
                    log_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Created directory for log file: {log_dir}")

                with Path(TRANSLATION_LOG_FILE).open("w", encoding="utf-8") as f:
                    json.dump(log_data, f, indent=2, ensure_ascii=False)

            except OSError as e:
                logger.error(
                    f"Could not write to translation log file '{TRANSLATION_LOG_FILE}': {e}"
                )
            except TypeError as e:
                logger.error(f"Data serialization error writing to log file: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Unexpected error updating translation log: {e}", exc_info=True)


# ------------------------------------------------------------------
#  Public Convenience Functions / Singleton Access
# ------------------------------------------------------------------

_translation_manager_instance = None


def get_translation_manager():  # noqa: C901
    """
    Singleton accessor for the TranslationManager.
    Initializes the manager on first call. Ensures config is loaded first.
    """
    global _translation_manager_instance
    if _translation_manager_instance is None:
        # --- Perform Module Initialization First (Lazy) ---
        _ensure_initialized()

        logger.info("Initializing TranslationManager instance...")
        try:
            # --- Ensure Global Config Vars are Set ---
            global \
                DEEPL_KEYS, \
                GOOGLE_PROJECT_ID_CONFIG, \
                GOOGLE_CREDENTIALS_PATH, \
                DEEPL_QUOTA_PER_KEY

            # --- 1. Load Defaults from Environment (via settings) ---
            if CONFIG_LOADER_AVAILABLE and settings:
                DEEPL_KEYS = [k for k in (getattr(settings, "DEEPL_API_KEYS", None) or []) if k]
                GOOGLE_PROJECT_ID_CONFIG = getattr(settings, "GOOGLE_PROJECT_ID", None)
                GOOGLE_CREDENTIALS_PATH = getattr(settings, "GOOGLE_CREDENTIALS_PATH", None)
                DEEPL_QUOTA_PER_KEY = getattr(settings, "DEEPL_CHARACTER_QUOTA", 500000)

            # --- 2. Attempt Direct DB Override (Sync) ---
            # This ensures that changes made in the UI (saved to DB) take precedence
            # over static environment variables.
            if DATABASE_AVAILABLE and SyncSessionLocal:
                logger.debug("Checking Database for configuration overrides...")
                try:
                    # Import base to ensure all models are registered in metadata/mapping
                    from sqlalchemy import select

                    from app.core.security import decrypt_value
                    from app.db.models.app_settings import AppSettings

                    with SyncSessionLocal() as session:
                        result = session.execute(select(AppSettings).where(AppSettings.id == 1))
                        db_settings = result.scalar_one_or_none()

                        if db_settings:
                            # --- DeepL Keys ---
                            # If deepl_api_keys is set in DB (even empty string), it overrides Env
                            if db_settings.deepl_api_keys is not None:
                                raw_keys = db_settings.deepl_api_keys
                                if raw_keys == "":
                                    # Explicitly disabled
                                    DEEPL_KEYS = []
                                    logger.info(
                                        "DeepL API Keys explicitly cleared by Database settings."
                                    )
                                else:
                                    try:
                                        decrypted_json = decrypt_value(raw_keys)
                                        parsed_keys = json.loads(decrypted_json)
                                        if isinstance(parsed_keys, list):
                                            DEEPL_KEYS = [
                                                str(k).strip()
                                                for k in parsed_keys
                                                if str(k).strip()
                                            ]
                                            logger.info(
                                                f"Loaded {len(DEEPL_KEYS)} DeepL keys from Database settings (overriding env)."
                                            )
                                    except Exception as db_key_err:
                                        DEEPL_KEYS = []
                                        logger.error(
                                            "Failed to decrypt/parse DeepL keys from DB; disabling DeepL keys to avoid env fallback: %s",
                                            db_key_err,
                                        )

                            # --- Google Credentials ---
                            # Logic: If DB has credential blob, use that.
                            # Since we can't easily write a temp file here safely in all contexts,
                            # we might rely on the Env path if DB is empty, OR we need to handle blob usage.
                            # For now, let's respect project_id override at least.
                            if db_settings.google_cloud_project_id:
                                GOOGLE_PROJECT_ID_CONFIG = db_settings.google_cloud_project_id
                                logger.info(
                                    f"Using Google Project ID from Database: {GOOGLE_PROJECT_ID_CONFIG}"
                                )

                            # Note: Handling raw Google Credentials blob from DB requires writing to a file
                            # because google-cloud-library expects a file path or environment variable content.
                            # Current implementation prioritizes the config path if DB blob logic isn't fully implemented in Translator.
                            # However, if using Env vars, user settings usually write to a generic shared path or rely on Env.

                except Exception as db_err:
                    logger.warning(
                        f"Failed to load settings from Database (falling back to Env): {db_err}"
                    )

            if not CONFIG_LOADER_AVAILABLE:
                logger.warning(
                    "Configuration loader not available. Ensure global config variables (DEEPL_KEYS, etc.) are set manually."
                )

            logger.debug(f"Reference Settings Loaded -> DEEPL_KEYS: {len(DEEPL_KEYS)} keys")
            logger.debug(
                f"Reference Settings Loaded -> GOOGLE_PROJECT_ID: {GOOGLE_PROJECT_ID_CONFIG}"
            )

            # Now, instantiate the manager
            _translation_manager_instance = TranslationManager()
            logger.info("TranslationManager instance created successfully.")

        except Exception as e:
            logger.critical(f"FATAL: Could not initialize TranslationManager: {e}", exc_info=True)
            raise RuntimeError(f"Fatal: TranslationManager initialization failed: {e}") from e

    return _translation_manager_instance


# ------------------------------------------------------------------
#  Explicit Exports & Standalone Test
# ------------------------------------------------------------------
__all__ = [
    "TranslationJob",
    "TranslationManager",
    "TranslationResult",
    "get_translation_manager",
]
