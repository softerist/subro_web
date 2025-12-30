import logging
from pathlib import Path

# Let's import from processor temporarily, planning to move constants later.
from app.modules.subtitle.core.constants import SUBTITLE_EXTENSIONS_LOWER_TUPLE
from app.modules.subtitle.utils import file_utils, subtitle_matcher, subtitle_parser

from .base import ProcessingContext, ProcessingStrategy

# Language detection import
try:
    from langdetect import LangDetectException, detect

    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    LangDetectException = Exception  # Dummy for type hinting

logger = logging.getLogger(__name__)


class LocalScanner(ProcessingStrategy):
    """
    Strategy to find, process, and normalize *non-standard* local subtitle files.
    It looks for subtitle files in the video's directory that don't follow
    the standard naming convention (e.g., movie.title.mkv + movie.title.srt),
    detects their language, and if it matches 'ro', processes and renames them.
    """

    def execute(self, context: ProcessingContext) -> bool:  # noqa: C901
        # --- Pre-conditions ---
        if context.found_final_ro:
            self.logger.debug("Skipping: Final RO subtitle already found.")
            return True  # Success (nothing to do)

        if not LANGDETECT_AVAILABLE:
            self.logger.warning("Skipping: 'langdetect' library not available.")
            return True  # Success (cannot perform action)

        video_dir = Path(context.video_path).parent
        base_name_no_ext = Path(context.video_info.get("basename", "")).stem
        target_ro_path = file_utils.get_preferred_subtitle_path(base_name_no_ext, "ro")
        target_en_path = file_utils.get_preferred_subtitle_path(base_name_no_ext, "en")
        standard_ro_name_lower = Path(target_ro_path).name.lower()
        standard_en_name_lower = Path(target_en_path).name.lower()

        self.logger.info(f"Scanning '{video_dir}' for non-standard local RO subtitles...")
        local_ro_processed = False

        try:
            for item in video_dir.iterdir():
                item_path = item
                item_name = item.name
                item_lower = item_name.lower()

                # Basic checks: is file, subtitle extension, not standard name, not backup
                if not (item.is_file() and item_lower.endswith(SUBTITLE_EXTENSIONS_LOWER_TUPLE)):
                    continue
                if item_lower == standard_ro_name_lower or item_lower == standard_en_name_lower:
                    continue  # Skip standardly named files
                if item_lower.endswith((".bak", ".syncbak")):
                    continue

                # Avoid processing files that look like standard format for *other* languages
                # e.g., movie.fr.srt - improves robustness slightly
                # Avoid processing files that look like standard format for *other* languages
                # e.g., movie.fr.srt - improves robustness slightly
                potential_lang = subtitle_matcher.get_subtitle_language_code(item_name)
                if potential_lang and len(potential_lang) == 2:
                    self.logger.debug(
                        f"Skipping file '{item_name}' - looks like standard format for lang '{potential_lang}'."
                    )
                    continue

                self.logger.info(f"Found potential non-standard local subtitle: {item_name}")
                try:
                    sub_content = file_utils.read_srt_file(item_path)
                    if not sub_content or not sub_content.strip():
                        self.logger.warning(f"Local subtitle '{item}' is empty. Skipping.")
                        continue

                    detected_lang = detect(sub_content[:5000])  # Detect on first 5k chars
                    self.logger.info(f"Detected language for '{item_name}': {detected_lang}")

                    if detected_lang == "ro":
                        self.logger.info(
                            f"Processing detected non-standard local RO subtitle: {item_name}"
                        )
                        # Process: Fix diacritics, ensure timestamp format
                        processed_content = subtitle_parser.fix_diacritics(sub_content)
                        processed_content = subtitle_parser.ensure_correct_timestamp_format(
                            processed_content
                        )
                        # Save to standard path
                        file_utils.write_srt_file(target_ro_path, processed_content)

                        if Path(target_ro_path).exists():
                            self.logger.info(
                                f"Saved processed local subtitle to standard path: {target_ro_path}"
                            )
                            # Remove original non-standard file
                            try:
                                item.unlink()
                                self.logger.info(
                                    f"Removed original non-standard local subtitle: {item_name}"
                                )
                            except OSError as e:
                                self.logger.warning(
                                    f"Could not remove original non-standard local subtitle '{item_name}': {e}"
                                )

                            # Update context
                            context.found_final_ro = True
                            context.final_ro_sub_path_or_status = target_ro_path
                            local_ro_processed = True
                            break  # Exit loop after finding and processing one RO file
                        else:
                            self.logger.error(
                                f"Failed to write processed local subtitle to standard path: {target_ro_path}"
                            )
                            context.add_error(
                                self.name,
                                f"Failed to write processed local subtitle to '{target_ro_path}'",
                            )
                            # Continue searching other files

                except LangDetectException as lang_err:
                    self.logger.warning(f"Could not detect language for '{item_name}': {lang_err}")
                except FileNotFoundError:
                    self.logger.warning(f"File '{item_name}' disappeared during processing.")
                except Exception as proc_err:
                    context.add_error(
                        self.name,
                        f"Error processing non-standard local subtitle '{item_name}': {proc_err}",
                    )
                    self.logger.exception(
                        f"Error processing non-standard local subtitle '{item_name}'.",
                        exc_info=True,
                    )  # Log full traceback

            if local_ro_processed:
                self.logger.info("Successfully processed a non-standard local RO subtitle.")
            else:
                self.logger.info(
                    "No suitable non-standard local RO subtitle found in directory scan."
                )

        except Exception as scan_err:
            context.add_error(
                self.name, f"Error during non-standard local subtitle scan: {scan_err}"
            )
            self.logger.exception("Error during non-standard local subtitle scan.", exc_info=True)
            return False  # Indicate potential failure of the scan itself

        return True  # Strategy completed its task successfully
