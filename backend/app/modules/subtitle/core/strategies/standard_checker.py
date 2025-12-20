import logging
from pathlib import Path

from .base import ProcessingContext, ProcessingStrategy

# Assuming file_utils.get_preferred_subtitle_path primarily constructs the filename
# We will build the full path here for clarity.
# from app.modules.subtitle.utils import file_utils

logger = logging.getLogger(__name__)


class StandardFileChecker(ProcessingStrategy):
    def execute(self, context: ProcessingContext) -> bool:
        # --- Get the directory containing the video file ---
        video_path = Path(context.video_path)
        video_dir = video_path.parent
        # Fallback check (less likely needed with Path, but keeping logic structure)
        if not str(video_dir) or str(video_dir) == ".":
            # Pathlib handles this gracefully usually, but let's stick to simple
            pass

        # --- Get the base name without extension ---
        base_name_no_ext = video_path.stem

        # --- Construct FULL paths for RO and EN subtitles ---
        target_ro_filename = f"{base_name_no_ext}.ro.srt"
        target_ro_path = str(video_dir / target_ro_filename)
        context.target_ro_path = target_ro_path  # Store the full path

        target_en_filename = f"{base_name_no_ext}.en.srt"
        target_en_path = str(video_dir / target_en_filename)
        context.target_en_path = target_en_path  # Store the full path

        # --- Check RO (using the full path) ---
        ro_found = False
        if Path(target_ro_path).exists():
            try:
                if Path(target_ro_path).stat().st_size > 0:
                    self.logger.info(f"Found existing standard RO subtitle: {target_ro_path}")
                    context.found_final_ro = True
                    context.final_ro_sub_path_or_status = target_ro_path
                    ro_found = True
                else:
                    self.logger.warning(
                        f"Found standard RO file, but it is empty: {target_ro_path}"
                    )
            except OSError as e:
                self.logger.error(f"Error accessing RO file {target_ro_path}: {e}")
        else:
            self.logger.debug(f"No existing standard RO subtitle found at: {target_ro_path}")

        # --- Check EN (only if RO wasn't found, using the full path) ---
        if not ro_found:
            if Path(target_en_path).exists():
                try:
                    if Path(target_en_path).stat().st_size > 0:
                        self.logger.info(f"Found existing standard EN subtitle: {target_en_path}")
                        # Store as a candidate, DO NOT set found_final_en or final_en_sub_path yet
                        context.candidate_en_path_standard = target_en_path
                    else:
                        self.logger.warning(
                            f"Found standard EN file, but it is empty: {target_en_path}"
                        )
                except OSError as e:
                    self.logger.error(f"Error accessing EN file {target_en_path}: {e}")
            else:
                self.logger.debug(f"No existing standard EN subtitle found at: {target_en_path}")

        # This strategy always succeeds in *checking*, even if nothing is found.
        return True
