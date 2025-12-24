#!/usr/bin/env python3
"""
Subtitle Downloader CLI Worker Script

This script is called by the Celery worker to process subtitle downloads.
All logging goes to stdout for real-time streaming to the web UI.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Force unbuffered output for real-time log streaming
# This MUST be done before any other imports that might buffer output
os.environ["PYTHONUNBUFFERED"] = "1"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)


# Create error tracker (before imports that might log)


class ErrorTrackingHandler(logging.Handler):
    """Custom handler to track if any ERROR level logs were emitted."""

    def __init__(self):
        super().__init__()
        self.has_errors = False

    def emit(self, record):
        if record.levelno >= logging.ERROR:
            self.has_errors = True


# Create error tracker (before imports that might log)
error_tracker = ErrorTrackingHandler()

# Now do the app imports (after setting up basic unbuffered output)
# Add backend directory to sys.path to allow imports from app.*
backend_path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_path))

# These imports may trigger logging, so we set up logging right after
from app.modules.subtitle.core.processor import (  # noqa: E402
    determine_content_type_for_path,
    process_movie_folder,
    process_tv_show_folder,
)
from app.modules.subtitle.utils.logging_config import setup_logging  # noqa: E402

logger = logging.getLogger("sub_downloader")


def main():
    """Main function to orchestrate the subtitle tool."""
    # Immediate print to verify output capture
    print("=== SUBTITLE DOWNLOADER SCRIPT STARTED ===", flush=True)

    parser = argparse.ArgumentParser(
        description="Subtitle Downloader CLI Worker", formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--folder-path", required=True, help="Path to the folder containing media")
    parser.add_argument("--language", help="Target language code (e.g., 'ro')", default="ro")
    parser.add_argument(
        "--log-level",
        type=str.upper,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set logging level (default: INFO)",
    )
    parser.add_argument(
        "--skip-translation", action="store_true", help="Skip the automatic translation step"
    )
    parser.add_argument(
        "--skip-sync", action="store_true", help="Skip the subtitle synchronization step"
    )

    args = parser.parse_args()

    # Setup logging with the specified level - this takes over ALL logging
    setup_logging(console_level_override=args.log_level, include_timestamp=False)

    # Re-attach error tracker to root logger after setup_logging clears handlers
    logging.getLogger().addHandler(error_tracker)

    folder_path = args.folder_path

    logger.info("=== Subtitle Downloader Started ===")
    logger.info(f"Folder path: {folder_path}")
    logger.info(f"Language: {args.language}")
    logger.info(f"Log level: {args.log_level}")
    logger.info(f"Skip translation: {args.skip_translation}")
    logger.info(f"Skip sync: {args.skip_sync}")

    if not Path(folder_path).exists():
        logger.error(f"Folder path does not exist: {folder_path}")
        print("=== SUBTITLE DOWNLOADER SCRIPT ENDED (error) ===", flush=True)
        sys.exit(1)

    # Build processing options
    processing_options = {
        "skip_translation": args.skip_translation,
        "skip_sync": args.skip_sync,
    }

    # Determine content type
    logger.info(f"Analyzing content type for: {folder_path}")
    content_type = determine_content_type_for_path(folder_path)
    logger.info(f"Detected content type: {content_type}")

    # If path is a file, default to movie processing
    if Path(folder_path).is_file():
        content_type = "movie"
        logger.info("Input is a file, treating as movie.")

    success_count = 0
    try:
        if content_type == "movie":
            logger.info(f"Processing as MOVIE: {folder_path}")
            success_count = process_movie_folder(folder_path, options=processing_options)
        elif content_type == "tvshow":
            logger.info(f"Processing as TV SHOW: {folder_path}")
            success_count = process_tv_show_folder(folder_path, options=processing_options)
        else:
            logger.warning(
                f"Could not determine content type for: {folder_path}. Defaulting to movie processing."
            )
            success_count = process_movie_folder(folder_path, options=processing_options)
    except Exception as e:
        logger.error(f"Error during processing: {e}", exc_info=True)
        print("=== SUBTITLE DOWNLOADER SCRIPT ENDED (error) ===", flush=True)
        sys.exit(1)

    logger.info("=== Processing Complete ===")
    logger.info(f"Subtitles processed successfully: {success_count}")

    # If we successfully processed at least one subtitle, consider it a success
    # even if there were some non-fatal errors logged during processing
    if success_count > 0:
        if error_tracker.has_errors:
            logger.info(
                "Some non-fatal errors occurred during processing, but subtitles were processed successfully."
            )
        print("=== SUBTITLE DOWNLOADER SCRIPT ENDED (success) ===", flush=True)
        sys.exit(0)

    # Check if any errors were logged during processing with no success
    if error_tracker.has_errors:
        logger.warning("Errors occurred during processing and no subtitles were processed.")
        print("=== SUBTITLE DOWNLOADER SCRIPT ENDED (with errors) ===", flush=True)
        sys.exit(1)

    # No errors but also no subtitles found - still success (nothing to do)
    print("=== SUBTITLE DOWNLOADER SCRIPT ENDED (success) ===", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
