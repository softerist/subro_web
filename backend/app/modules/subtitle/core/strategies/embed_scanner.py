# src/core/strategies/embed_scanner.py
import logging
from pathlib import Path

# Use relative imports assuming standard structure
try:
    from ...core import constants  # Go up two levels to src/, then down to core/
    from ...utils import media_utils  # Go up two levels to src/, then down to utils/
    from .base import ProcessingContext, ProcessingStrategy

    # Import specific sets from constants to avoid circular dependency via media_utils
    TEXT_SUBTITLE_CODECS = constants.TEXT_SUBTITLE_CODECS
    IMAGE_SUBTITLE_CODECS_EN = constants.IMAGE_SUBTITLE_CODECS_EN

    logger = logging.getLogger(__name__)
    logger.debug("EmbedScanner strategy: Successfully imported dependencies.")
except (ImportError, ValueError) as e:
    logger = logging.getLogger(__name__)
    logger.critical(
        f"EmbedScanner: Failed to import dependencies ({e}). Strategy will likely fail.",
        exc_info=True,
    )

    # Define dummies if needed to prevent load-time errors, though functionality will be broken
    class ProcessingStrategy:
        pass

    class ProcessingContext:
        pass

    media_utils = None  # Indicate missing dependency
    TEXT_SUBTITLE_CODECS = set()
    IMAGE_SUBTITLE_CODECS_EN = set()


class EmbedScanner(ProcessingStrategy):
    """
    Strategy to check for embedded subtitles.
    - Checks for RO:
        - If text-based RO found ('text_found_no_extract'), signals RO goal success immediately.
        - If extractable RO (text or PGS) found, extracts it and signals RO goal success.
    - If no RO goal met, DETECTS the best potential EN stream (text or allowed image):
        - Stores its info (index, codec, type, flags) in the context for potential later
          extraction by FinalSelector.
    """

    def execute(self, context: ProcessingContext) -> bool:  # noqa: C901
        # Check if dependency is loaded
        if not media_utils:
            context.add_error(self.name, "Media utilities dependency failed to load.")
            self.logger.error("Cannot execute: media_utils module not available.")
            return False  # Cannot proceed

        if context.found_final_ro:
            self.logger.debug("Skipping: Final RO subtitle already found.")
            return True

        video_filename = Path(context.video_path).name
        self.logger.info(f"Checking for embedded subtitles in '{video_filename}'...")

        # --- Check for RO Embedded (Extraction happens immediately for RO) ---
        ro_status = "failed"  # Default
        ro_extracted_path = None
        try:
            # Pass 'ro', the function will normalize it
            ro_status, ro_extracted_path = media_utils.check_and_extract_embedded_subtitle(
                context.video_path,
                "ro",  # Function handles normalization
            )

            if ro_status == "text_found_no_extract":
                self.logger.info(
                    "Found embedded text-based RO subtitle. Setting RO goal as met (no extraction needed here)."
                )
                context.found_final_ro = True
                context.final_ro_sub_path_or_status = (
                    "embedded_text_ro"  # Use a clear status string
                )
                return True  # RO goal met, stop processing this strategy

            elif ro_status in ["text_extracted", "pgs_extracted"] and ro_extracted_path:
                ro_type = "PGS/Image (OCR)" if ro_status == "pgs_extracted" else "Text"
                self.logger.info(
                    f"Found and extracted embedded RO ({ro_type}) subtitle: {Path(ro_extracted_path).name}"
                )
                context.found_final_ro = True
                context.final_ro_sub_path_or_status = ro_extracted_path
                # No need to add temp dir here; check_and_extract cleans up its own temp files.
                return True  # RO goal met, stop processing this strategy

            elif ro_status == "failed":
                self.logger.info(
                    "No suitable embedded RO subtitle found or check/extraction failed."
                )
                # Continue to check for EN below
            else:
                # This case should ideally not happen with the defined statuses
                self.logger.warning(
                    f"Unexpected status '{ro_status}' received from check_and_extract_embedded_subtitle for RO."
                )
                # Continue to check for EN just in case

        except Exception as e:
            context.add_error(self.name, f"Error checking/extracting embedded RO subs: {e}")
            self.logger.exception("Error during RO subtitle check/extraction.", exc_info=True)
            # Decide if this error should halt the pipeline step.
            # Let's allow EN check to proceed for robustness, but log the error.
            # return False # <-- uncomment this to make RO check failure halt this strategy

        # --- Detect EN Embedded (Only if RO goal not met yet) ---
        if not context.found_final_ro:
            self.logger.info("RO goal not met, detecting potential embedded EN streams...")
            try:
                # Use the function that *only finds* the best stream info for EN.
                # Prefer text codecs for EN detection scoring.
                best_en_stream_info = media_utils.find_best_embedded_stream_info(
                    context.video_path,
                    "en",  # Function handles normalization ('eng' would also work)
                    preferred_codecs=list(
                        TEXT_SUBTITLE_CODECS
                    ),  # Pass preferred text codecs for scoring
                )

                if best_en_stream_info:
                    codec = best_en_stream_info.get("codec_name", "unknown").lower()
                    index = best_en_stream_info.get("stream_index", "?")
                    # mapped_lang = best_en_stream_info.get("mapped_lang", "??")  # Should be 'en'

                    # Determine codec type and if it's usable for EN fallback
                    codec_type = None
                    is_usable_en_candidate = False
                    if codec in TEXT_SUBTITLE_CODECS:
                        codec_type = "text"
                        is_usable_en_candidate = True
                        self.logger.info(
                            f"Detected potential embedded EN subtitle (Text: Stream #{index}, Codec: {codec}). Storing info."
                        )
                    elif codec in IMAGE_SUBTITLE_CODECS_EN:  # Check against EN allowed image codecs
                        codec_type = "image"
                        is_usable_en_candidate = True  # We allow PGS for EN as a candidate
                        self.logger.info(
                            f"Detected potential embedded EN subtitle (Image: Stream #{index}, Codec: {codec}). Storing info as candidate."
                        )
                    else:
                        # Log detection but don't store info if codec isn't usable
                        self.logger.info(
                            f"Detected embedded EN subtitle (Stream #{index}, Codec: {codec}), but codec is not designated for text or allowed image extraction for EN. Skipping as candidate."
                        )

                    # Store the info if it's a valid candidate (text or allowed image)
                    if is_usable_en_candidate:
                        # Ensure info is mutable and add our determined codec_type
                        context.potential_embedded_en_info = dict(
                            best_en_stream_info
                        )  # Make a copy
                        context.potential_embedded_en_info["codec_type"] = codec_type
                    else:
                        context.potential_embedded_en_info = None  # Explicitly clear if not usable

                else:
                    self.logger.info("No suitable embedded EN subtitle stream detected.")
                    context.potential_embedded_en_info = None  # Ensure it's cleared

            except Exception as e:
                # Don't fail the entire pipeline step just because EN detection failed
                context.add_error(self.name, f"Error detecting embedded EN subs: {e}")
                self.logger.exception("Error during EN subtitle detection.", exc_info=True)
                context.potential_embedded_en_info = None  # Clear on error
                # Continue anyway, strategy technically completed its check

        # Strategy completed its RO check and EN detection task successfully,
        # regardless of whether anything was found or stored. The return value
        # primarily indicates if the RO goal was met earlier.
        # If we reach here, either RO failed/not found, or an error occurred during RO check
        # but we decided to proceed. The overall pipeline continues based on context flags.
        return True
