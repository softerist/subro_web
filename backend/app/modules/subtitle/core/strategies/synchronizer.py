import logging
from pathlib import Path

from app.modules.subtitle.utils import subtitle_sync  # Import the sync utility functions

from .base import ProcessingContext, ProcessingStrategy

logger = logging.getLogger(__name__)


class Synchronizer(ProcessingStrategy):
    """
    Strategy to synchronize the finalized subtitle file (RO or EN) with the video audio.
    Uses tools like ffsubsync or alass via the subtitle_sync utility.
    """

    def execute(self, context: ProcessingContext) -> bool:
        # === Pre-conditions ===
        # 1. Check skip flag
        if context.options.get("skip_sync", False):
            self.logger.info("Skipping: Synchronization explicitly disabled via options.")
            return True  # Success (nothing to do)

        # === Determine which subtitle file needs syncing ===
        target_sub_path = None
        sync_source_hint = "unknown"

        # 1. Prioritize RO path if it's a finalized *file*
        if (
            context.final_ro_sub_path_or_status
            and context.final_ro_sub_path_or_status != "embedded_text_ro"
        ):
            # Check if the path is valid and is an SRT file (sync tools work on SRT)
            ro_path = context.final_ro_sub_path_or_status
            if Path(ro_path).exists():
                if ro_path.lower().endswith(".srt"):
                    target_sub_path = ro_path
                    sync_source_hint = f"final_ro_{Path(target_sub_path).name}"
                    self.logger.debug(
                        f"Identified final RO subtitle for potential sync: {target_sub_path}"
                    )
                else:
                    self.logger.info(
                        f"Final RO subtitle exists but is not an SRT file ({ro_path}). Skipping audio sync."
                    )
            else:  # Path doesn't exist (shouldn't happen if set correctly)
                self.logger.warning(f"Final RO path '{ro_path}' does not exist. Cannot sync.")

        # 2. Fallback to EN path if RO wasn't suitable or found
        #    Uses the final_en_sub_path selected by FinalSelector.
        elif context.final_en_sub_path:
            en_path = context.final_en_sub_path
            if Path(en_path).exists():
                if en_path.lower().endswith(".srt"):
                    target_sub_path = en_path
                    sync_source_hint = f"final_en_{Path(target_sub_path).name}"
                    self.logger.debug(
                        f"Identified final EN subtitle for potential sync: {target_sub_path}"
                    )
                else:
                    self.logger.info(
                        f"Final EN subtitle exists but is not an SRT file ({en_path}). Skipping audio sync."
                    )
            else:  # Path doesn't exist
                self.logger.warning(f"Final EN path '{en_path}' does not exist. Cannot sync.")

        # === Check if a syncable subtitle was found ===
        if not target_sub_path:
            self.logger.info(
                "No suitable SRT subtitle file (RO or EN) found in context to synchronize."
            )
            return True  # Success (nothing to sync)

        self.logger.info(
            f"Attempting synchronization for: {Path(target_sub_path).name} (Source Hint: {sync_source_hint})"
        )

        # === Call Sync Utility ===
        try:
            # Call the main sync function from subtitle_sync utility
            # It handles offset checks and tool execution internally.
            subtitle_sync.sync_subtitles_with_audio(
                video_file_path=context.video_path, subtitle_file_path=target_sub_path
            )
            # sync_subtitles_with_audio handles its own logging for tool success/failure.
            self.logger.info(
                f"Synchronization process completed for {Path(target_sub_path).name} (check utility logs for details)."
            )

        except Exception as sync_err:
            # ... (error logging, return False) ... remains the same
            context.add_error(
                self.name,
                f"Unexpected error during sync utility call for '{target_sub_path}': {sync_err}",
            )
            self.logger.exception("Unexpected error during sync utility call.", exc_info=True)
            return False

        return True  # Strategy completed its task
