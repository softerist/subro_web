import logging
import tempfile
from pathlib import Path

from app.modules.subtitle.utils import (
    media_utils,  # Assuming new functions exist here
)

from .base import ProcessingContext, ProcessingStrategy

logger = logging.getLogger(__name__)


class FinalSelector(ProcessingStrategy):
    """
    Strategy to select the final EN subtitle path based on priority
    (Online > Standard > Local > Detected Embedded) *if* the RO goal was not met.
    Triggers extraction for embedded candidates only if selected.
    """

    def execute(self, context: ProcessingContext) -> bool:
        if context.found_final_ro:
            self.logger.debug("Skipping: Final RO subtitle already found.")
            return True

        selected_en_path = None
        selection_source = "None"

        # --- Priority Check for EN Candidates ---
        # 1. Online Candidate
        if context.candidate_en_path_online and Path(context.candidate_en_path_online).exists():
            selected_en_path = context.candidate_en_path_online
            selection_source = "Online"
        # 2. Standard File Candidate
        elif (
            context.candidate_en_path_standard and Path(context.candidate_en_path_standard).exists()
        ):
            selected_en_path = context.candidate_en_path_standard
            selection_source = "Standard File"
        # 3. Local Scanner Candidate (Assuming context.candidate_en_path_local exists)
        # elif context.candidate_en_path_local and os.path.exists(context.candidate_en_path_local):
        #    selected_en_path = context.candidate_en_path_local
        #    selection_source = "Local Scanner"

        # 4. Detected Embedded Candidate (Requires Extraction)
        elif context.potential_embedded_en_info:
            stream_index = context.potential_embedded_en_info.get("stream_index")
            codec_name = context.potential_embedded_en_info.get("codec_name", "unknown")
            self.logger.info(
                f"No higher priority EN found. Attempting extraction of detected embedded EN (Stream #{stream_index}, Codec: {codec_name})..."
            )

            if stream_index is None:
                self.logger.error(
                    "Cannot extract embedded EN: Stream index missing in context info."
                )
            else:
                # Create a dedicated temp directory for this extraction
                # Use the main video filename to make the temp dir more identifiable
                base_name = Path(context.video_path).stem
                try:
                    # Create temp dir (will be cleaned up by pipeline via context.add_temp_dir)
                    temp_extract_dir = tempfile.mkdtemp(prefix=f"embed_extract_{base_name}_")
                    context.add_temp_dir(temp_extract_dir)  # Register for cleanup!

                    # Call the extraction utility
                    extracted_path = media_utils.extract_embedded_stream_by_index(
                        context.video_path, stream_index, temp_extract_dir
                    )

                    if extracted_path and Path(extracted_path).exists():
                        self.logger.info(
                            f"Successfully extracted embedded EN subtitle to: {extracted_path}"
                        )
                        selected_en_path = extracted_path
                        selection_source = "Embedded (Extracted)"
                    else:
                        self.logger.warning(
                            f"Failed to extract embedded EN subtitle stream #{stream_index}."
                        )
                        # Optionally remove the empty temp dir now if extraction failed cleanly
                        # file_utils.clean_temp_directory(temp_extract_dir)
                        # context.temp_dirs_to_clean.discard(temp_extract_dir) # Remove if cleaned here

                except Exception as extract_err:
                    context.add_error(
                        self.name,
                        f"Failed to extract embedded EN stream #{stream_index}: {extract_err}",
                    )
                    self.logger.exception("Error during embedded EN extraction.", exc_info=True)
                    # Ensure selected_en_path remains None

        # --- Update Context if an EN subtitle was selected ---
        if selected_en_path:
            self.logger.info(
                f"Final EN subtitle selected (Source: {selection_source}): {Path(selected_en_path).name}"
            )
            context.final_en_sub_path = selected_en_path
            # context.found_final_en = True # Re-introduce if needed
        else:
            self.logger.info(
                "No suitable final EN subtitle candidate found or selected from any source."
            )
            # context.found_final_en = False

        return True  # Strategy completed its selection/extraction task
