import html
import logging
import re
from urllib.error import URLError  # Import URLError for potential download issues

# Import NLTK for sentence tokenization, handle import error gracefully
# Global flag to track if NLTK is usable
NLTK_AVAILABLE = False
try:
    import nltk

    # Check if 'punkt' is already downloaded or download it
    try:
        # Use a reliable way to check if the resource exists without downloading if possible
        # nltk.data.find will raise LookupError if not found
        nltk.data.find("tokenizers/punkt")
        logging.info("NLTK 'punkt' tokenizer already available.")
        NLTK_AVAILABLE = True
    except LookupError:
        logging.info("NLTK 'punkt' tokenizer not found. Attempting download...")
        try:
            # Attempt download quietly
            nltk.download("punkt", quiet=True)
            # Verify download by finding again
            nltk.data.find(
                "tokenizers/punkt"
            )  # This will raise LookupError again if download failed
            logging.info("NLTK 'punkt' tokenizer downloaded successfully.")
            NLTK_AVAILABLE = True
        except URLError as url_err:
            logging.error(
                f"Failed to download NLTK 'punkt' tokenizer due to network error: {url_err}. Sentence splitting might be less accurate."
            )
            # NLTK_AVAILABLE remains False
        except Exception as download_err:
            logging.error(
                f"Failed to download NLTK 'punkt' tokenizer: {download_err}. Sentence splitting might be less accurate."
            )
            # NLTK_AVAILABLE remains False
except ImportError:
    logging.warning(
        "NLTK library not found (pip install nltk). Sentence splitting will rely on basic line breaks."
    )
    # NLTK_AVAILABLE remains False
except Exception as nltk_init_err:
    # Catch other potential errors during NLTK import/setup
    logging.error(f"An unexpected error occurred during NLTK setup: {nltk_init_err}")
    # NLTK_AVAILABLE remains False


# Get logger for this module
logger = logging.getLogger(__name__)

# --- Diacritics ---
# Romanian diacritic correction maps
diacritics_map1 = {
    "ª": "Ș",
    "º": "ș",
    "Þ": "Ț",
    "þ": "ț",
}  # Incorrect legacy chars (often from bad CP conversion)
diacritics_map2 = {
    "Ã": "Ă",
    "ã": "ă",
    "Î": "Î",
    "î": "î",
    "Â": "Â",
    "â": "â",
    "Ş": "Ș",
    "ş": "ș",
    "Ţ": "Ț",
    "ţ": "ț",
}  # Correcting cedilla to comma below, handling other common issues


def fix_diacritics(text: str) -> str:
    """
    Fixes common incorrect diacritics for Romanian and unescapes HTML entities.

    Args:
        text (str): The input text (potentially the whole subtitle content).

    Returns:
        str: Text with diacritics corrected and HTML entities unescaped.
    """
    if not isinstance(text, str):
        logger.warning(f"fix_diacritics expected a string, but got {type(text)}. Returning as is.")
        return text

    try:
        # 1. Unescape HTML entities first (e.g., &ș; -> ș, & -> &)
        # Apply twice for robustness against nested or partial entities.
        text_temp = html.unescape(text)
        text_corrected = html.unescape(text_temp)

        # 2. Apply correction maps for specific incorrect characters
        # Apply map1 (legacy) then map2 (cedilla/others)
        for char, replacement in diacritics_map1.items():
            text_corrected = text_corrected.replace(char, replacement)
        for char, replacement in diacritics_map2.items():
            text_corrected = text_corrected.replace(char, replacement)

        # Check if any changes were made
        if text_corrected != text:
            logging.debug("Applied diacritic/HTML entity corrections.")
        else:
            logging.debug("No diacritic/HTML entity corrections needed.")

        return text_corrected
    except Exception as e:
        logger.error(f"Error during diacritic fixing: {e}", exc_info=True)
        return text  # Return original text on error


# --- Timestamp Handling ---


def ensure_correct_timestamp_format(content: str) -> str:
    """
    Ensures SRT timestamps use comma decimal separator and standard ' --> ' arrow format.
    Corrects common variations like '.' milliseconds or missing/incorrect spaces around the arrow.
    """
    if not isinstance(content, str):
        logger.warning("ensure_correct_timestamp_format expected string, got %s", type(content))
        return content  # Safety check

    try:
        # Regex 1: Replace dot with comma in HH:MM:SS.ms
        # Handles cases like 00:00:01.234 -> 00:00:01,234
        corrected_content = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", content)

        # Regex 2: Ensure standard ' --> ' arrow format.
        # Handles variations like '-->', ' -> ', '-- >' etc. between valid timestamps.
        # Makes the space optional but adds it back in the replacement.
        corrected_content = re.sub(
            r"(\d{2}:\d{2}:\d{2},\d{3})\s*--?>\s*(\d{2}:\d{2}:\d{2},\d{3})",
            r"\1 --> \2",
            corrected_content,
        )

        # Log if changes were made (optional)
        # if corrected_content != content:
        #     logging.debug("Applied timestamp format corrections.")

        return corrected_content
    except Exception as e:
        logger.error(f"Error correcting timestamp format: {e}", exc_info=True)  # Log traceback
        return content  # Return original on error


# --- Text Processing ---


def tokenize_and_normalize(text: str | None) -> list[str]:
    """
    Splits text into lower-case alphanumeric tokens.
    Useful for matching filenames. Handles potential None input.
    """
    if not text or not isinstance(text, str):
        return []
    try:
        # Split by one or more non-alphanumeric characters, treating underscore as separator
        # Keep hyphen as part of words unless surrounded by spaces? Current regex splits on hyphens.
        # Consider refining if hyphens in titles (e.g. Spider-Man) are important.
        # Current: Splits "Spider-Man" into "spider", "man".
        tokens = re.split(r"[\W_]+", text)
        # Filter out empty strings resulting from split (e.g., double separators)
        # and convert remaining tokens to lower case
        return [token.lower() for token in tokens if token]
    except Exception as e:
        # Log the beginning of the problematic text for easier debugging
        logger.error(f"Error tokenizing text: '{text[:50]}...': {e}")
        return []


# --- SRT Parsing/Manipulation Utilities (Used by Translator) ---
# These are kept as they are used by the Translator service, not just the old processor.


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
    srt_content_corrected = ensure_correct_timestamp_format(srt_content.strip())
    lines = srt_content_corrected.splitlines()

    segment_index = 0
    current_index_line = None
    current_ts_line = None
    current_text_lines: list[str] = []
    state = "index"  # Possible states: index, timestamp, text

    for line_num, line in enumerate(lines, 1):
        stripped_line = line.strip()

        if state == "index":
            if re.fullmatch(r"\d+", stripped_line):
                current_index_line = line  # Keep original line including spacing if any
                state = "timestamp"
            elif stripped_line:  # Non-empty, non-numeric line where index was expected
                logger.warning(
                    f"SRT Parse (Line {line_num}): Expected index number, found: '{line}'. Skipping line."
                )
            # Ignore blank lines when expecting index

        elif state == "timestamp":
            # Use regex for more flexible timestamp matching (already corrected format)
            ts_match = re.match(
                r"\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}", stripped_line
            )
            if ts_match:
                current_ts_line = line  # Keep original line including spacing
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
                current_text_lines.append(line)  # Keep original line format
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
        # Text content might already have internal newlines and should be preserved as is
        txt_fmt = txt_str

        # Add block: index, timestamp, text (potentially multi-line)
        srt_blocks.append(f"{idx_line_fmt}{ts_line_fmt}{txt_fmt}")

    # Join blocks with exactly one blank line (two newlines)
    result = "\n\n".join(srt_blocks)

    # Ensure the final string ends with exactly one newline if there's content
    if result:
        # Normalize trailing newlines: strip all trailing whitespace, add one newline
        result = result.rstrip() + "\n"

    return result


# --- Text Chunking (Used by Translator) ---


def chunk_text_for_translation(text: str, max_length: int = 4500) -> list[str]:  # noqa: C901
    """
    Chunks text into smaller pieces suitable for translation APIs,
    preferring sentence boundaries using NLTK if available, otherwise uses line breaks.

    Args:
        text (str): The text content to chunk.
        max_length (int): Maximum character length for each chunk.

    Returns:
        list[str]: A list of text chunks.
    """
    chunks: list[str] = []
    if not text or not isinstance(text, str):
        return chunks

    elements = []
    element_separator = "\n"  # Default separator if splitting by line

    # Decide splitting strategy based on NLTK availability
    if NLTK_AVAILABLE:  # Use the global flag checked during import
        try:
            # Attempt to use NLTK sentence tokenization
            elements = nltk.sent_tokenize(text)
            element_separator = "\n"  # Rejoin sentences with newline for translation context
            logger.debug("Using NLTK sentence tokenization for chunking.")
        except Exception as e:  # Catch potential errors during tokenization itself
            logger.warning(
                f"NLTK sentence tokenization failed unexpectedly: {e}. Falling back to line splitting."
            )
            elements = text.splitlines()  # Fallback
            element_separator = "\n"
    else:
        # Fallback to splitting by lines if NLTK wasn't loaded/available initially
        elements = text.splitlines()
        element_separator = "\n"
        logger.debug("NLTK not available or failed. Using line splitting for chunking.")

    # --- Chunking logic based on elements (sentences or lines) ---
    current_chunk_parts: list[str] = []
    current_length = 0
    for element in elements:
        # Process the element (strip maybe?) - keep original for joining for now
        processed_element = element  # Or element.strip() if desired

        if not processed_element:  # Skip effectively empty elements
            continue

        element_len = len(processed_element)
        # Length of separator to add *before* this element if chunk is not empty
        separator_len = len(element_separator) if current_length > 0 else 0

        # Check if the element itself exceeds the limit
        if element_len > max_length:
            logger.warning(
                f"Single element (sentence/line) length {element_len} exceeds max_length {max_length}. Splitting mid-element."
            )
            # If there's a pending chunk, finalize it first
            if current_chunk_parts:
                chunks.append(element_separator.join(current_chunk_parts))
            # Split the large element itself into pieces
            for i in range(0, element_len, max_length):
                chunks.append(processed_element[i : i + max_length])
            # Reset current chunk after handling the large element
            current_chunk_parts = []
            current_length = 0
            continue  # Move to the next element

        # Check if adding the next element (plus separator) exceeds max length
        if current_length + element_len + separator_len > max_length:
            # Finalize the current chunk
            if current_chunk_parts:  # Ensure we don't add empty chunks
                chunks.append(element_separator.join(current_chunk_parts))
            # Start a new chunk with the current element
            current_chunk_parts = [processed_element]
            current_length = element_len
        else:
            # Add element to the current chunk
            current_chunk_parts.append(processed_element)
            # Add element length and separator length (only if chunk wasn't empty)
            current_length += element_len + separator_len

    # Add the last remaining chunk if it's not empty
    if current_chunk_parts:
        chunks.append(element_separator.join(current_chunk_parts))

    logger.debug(
        f"Split text ({len(text)} chars) into {len(chunks)} chunks for translation (max_length={max_length})."
    )
    return chunks


# --- Explicit Exports ---
__all__ = [
    "chunk_text_for_translation",  # Used by Translator
    "ensure_correct_timestamp_format",
    "fix_diacritics",
    "parse_srt_into_segments",  # Used by Translator
    "rebuild_srt_from_segments",  # Used by Translator
    "tokenize_and_normalize",
]
