import logging
from pathlib import Path

from app.modules.subtitle.utils import file_utils  # For reading/writing files

from .base import ProcessingContext, ProcessingStrategy

logger = logging.getLogger(__name__)


class Translator(ProcessingStrategy):
    """
    Strategy to translate an existing English subtitle file (.srt) to Romanian
    if the RO subtitle goal hasn't been met yet.
    Uses the TranslationManager obtained via the DI container.
    """

    @property
    def is_critical(self) -> bool:
        """Translation is critical for the user's workflow."""
        return True

    def execute(self, context: ProcessingContext) -> bool:  # noqa: C901
        """
        Executes the translation logic.

        Args:
            context (ProcessingContext): The shared processing context.

        Returns:
            bool: True if the strategy executed (even if translation failed or was skipped),
                  False if a critical error occurred preventing execution (e.g., missing context).
        """
        # --- Pre-conditions ---
        if context.options.get("skip_translation", False):
            self.logger.info("Skipping: Translation explicitly disabled via options.")
            return True  # Skipped successfully

        if context.found_final_ro:
            # Includes embedded_text_ro status where translation is not applicable
            self.logger.debug(
                "Skipping: Final RO subtitle already found or marked as embedded text."
            )
            return True  # Nothing to do

        # Check if a potential English source file exists for translation
        en_path_to_translate = context.final_en_sub_path
        if not en_path_to_translate:
            self.logger.debug(
                "Skipping: No final EN subtitle path found in context to translate from."
            )
            return True  # Nothing to translate

        if not Path(en_path_to_translate).exists():
            self.logger.warning(
                f"Skipping: Final EN subtitle path '{en_path_to_translate}' does not exist."
            )
            # Update context flag if path doesn't exist? Or assume previous steps were correct?
            # Let's assume context is correct for now, but log warning.
            context.final_en_sub_path = None  # Clear the path if it doesn't exist
            context.found_final_en = False
            return True  # Cannot proceed without source file

        # Ensure the source file is an SRT file (translation logic assumes SRT)
        if not en_path_to_translate.lower().endswith(".srt"):
            self.logger.warning(
                f"Skipping: Final EN subtitle path '{en_path_to_translate}' is not an SRT file. Translation logic requires SRT."
            )
            return True  # Cannot translate non-SRT

        # Get the target RO path (should have been set by StandardFileChecker)
        target_ro_path = context.target_ro_path
        if not target_ro_path:
            context.add_error(
                self.name, "Cannot translate: Target RO path (.ro.srt) not set in context."
            )
            self.logger.error("Critical error: target_ro_path is missing in context.")
            return False  # Critical context missing, strategy cannot proceed

        # Safety check: Target RO file shouldn't exist if found_final_ro is False, but double-check.
        if Path(target_ro_path).exists():
            self.logger.warning(
                f"Skipping translation: Target RO file '{target_ro_path}' already exists, but found_final_ro flag was False. Reconciling context."
            )
            # Ensure context flag reflects reality if file exists
            if not context.found_final_ro:
                context.found_final_ro = True
                context.final_ro_sub_path_or_status = target_ro_path
            return True  # File exists, no translation needed

        # --- Get Translation Service via DI ---
        try:
            # **** Access TranslationManager via the context's DI container ****
            translator_manager = context.di.translator
            if not translator_manager:
                # This might happen if might happen if TranslationManager failed to initialize (e.g., config issues)
                self.logger.error(
                    "Skipping: Translation Manager service is not available from DI container."
                )
                context.add_error(self.name, "Translation Manager service unavailable.")
                # Treat as non-critical? Or should pipeline stop if translation is essential?
                # Let's return True, indicating strategy ran but couldn't translate.
                return True
        except AttributeError:
            self.logger.error(
                "Skipping: DI container ('context.di') does not have a 'translator' attribute."
            )
            context.add_error(self.name, "DI container missing 'translator' attribute.")
            return True
        except Exception as di_err:
            self.logger.error(
                f"Skipping: Error accessing translator service from DI container: {di_err}",
                exc_info=True,
            )
            context.add_error(self.name, f"Error accessing DI translator: {di_err}")
            return True

        self.logger.info(
            f"Preparing translation from EN '{Path(en_path_to_translate).name}' to RO '{Path(target_ro_path).name}'."
        )

        # --- Read EN Content ---
        try:
            en_content = file_utils.read_srt_file(en_path_to_translate)
            if not en_content or not en_content.strip():
                self.logger.warning(
                    f"Skipping translation: Source EN file is empty or whitespace only: {en_path_to_translate}"
                )
                return True  # Not an error, just nothing to translate
        except FileNotFoundError:
            # Should be caught by the earlier exists check, but handle defensively
            self.logger.error(f"Source EN file disappeared before reading: {en_path_to_translate}")
            context.add_error(
                self.name, f"Source EN file not found during read: {en_path_to_translate}"
            )
            return True  # Cannot proceed without source
        except Exception as read_err:
            context.add_error(
                self.name, f"Failed to read EN subtitle file '{en_path_to_translate}': {read_err}"
            )
            self.logger.exception("Failed to read EN subtitle file.", exc_info=True)
            return False  # Failed to read source, consider this a strategy failure

        # --- Perform Translation ---
        # Note: We pass source_lang=None to allow the API (DeepL/Google) to Auto-Detect the language.
        # This handles cases where tracks are mislabeled (e.g., German labeled as English).
        try:
            # Call the METHOD on the manager instance
            result = translator_manager.translate_file_content(
                input_file=en_path_to_translate,
                content=en_content,
                source_lang=None,  # Use API Auto-Detect
                target_lang="ro",
            )

            # Check translation result status
            # Possible statuses: "deepl_key_X", "google", "mixed", "partial_failure", "failed", "failed_parsing", etc.
            if (
                result
                and result.translated_content
                and result.service_used is not None
                and not result.service_used.startswith("failed")
            ):
                # Check for potential failure markers within the content
                if (
                    "[[FAIL:" in result.translated_content
                    or "[[TRUNCATED]]" in result.translated_content
                ):
                    self.logger.warning(
                        f"Translation result contains failure/truncation markers. Saving anyway but inspect file: {target_ro_path}"
                    )

                # Save the translated content (using file_utils for consistency)
                file_utils.write_srt_file(target_ro_path, result.translated_content)

                # Verify save
                if Path(target_ro_path).exists() and Path(target_ro_path).stat().st_size > 0:
                    self.logger.info(
                        f"Subtitle Translation successful to '{Path(target_ro_path).name}' (using {result.service_used})."
                    )
                    # Update context: RO goal achieved
                    context.found_final_ro = True
                    context.final_ro_sub_path_or_status = target_ro_path
                    # Optional: Clear the final_en_sub_path now that RO exists?
                    # context.final_en_sub_path = None
                    # context.found_final_en = False # Or keep EN info? Let's keep EN for now.
                    return True  # Indicate success
                else:
                    # File writing failed or produced empty file despite translator success
                    self.logger.error(
                        f"Translation API seemed successful (Service: {result.service_used}), but failed to write valid RO file: {target_ro_path}"
                    )
                    context.add_error(
                        self.name, f"Failed to write translated RO file '{target_ro_path}'"
                    )
                    # If write failed, don't update context flags
                    return False  # Failed to save result, strategy failed

            else:
                # Translation failed according to the result status
                fail_reason = result.service_used if result else "Unknown Error (Result is None)"
                self.logger.error(
                    f"Translation failed for '{Path(en_path_to_translate).name}'. Status: {fail_reason}"
                )
                context.add_error(self.name, f"Translation failed (Status: {fail_reason})")
                # Return False to indicate a critical failure, causing the job to fail as requested.
                return False

        except AttributeError as attr_err:
            # Add specific handling for AttributeError if it occurs again
            self.logger.critical(
                f"Still encountered AttributeError calling translate_file_content: {attr_err}. Check method definition in TranslationManager.",
                exc_info=True,
            )
            context.add_error(self.name, f"AttributeError: {attr_err}")
            return False  # Treat this as a critical failure

        except Exception as trans_err:
            # Catch unexpected errors during the translate_file_content call
            context.add_error(
                self.name, f"Unexpected error during translation process: {trans_err}"
            )
            self.logger.exception("Unexpected error during translation process.", exc_info=True)
            return False  # Indicate failure of this strategy step due to unexpected exception
