import logging
import os
from pathlib import Path
from typing import Any

# Note: opensubtitles_service is NOT directly used here anymore for core processing
# --- Import Config & Constants ---
from app.core.config import settings
from app.modules.subtitle.core.constants import SKIP_PATTERNS, VIDEO_EXTENSIONS

# --- Import New Pipeline Components ---
from app.modules.subtitle.core.di import ServiceContainer  # Dependency Injection
from app.modules.subtitle.core.strategies import (
    EmbedScanner,
    FinalSelector,
    LocalScanner,  # Assuming this exists and follows the pattern
    OnlineFetcher,
    ProcessingContext,
    StandardFileChecker,
    SubtitlePipeline,
    Synchronizer,
    Translator,
)

# --- Import Services ---
# IMDB service is used for initial info gathering
from app.modules.subtitle.services import imdb as imdb_service

# --- Get Logger ---
logger = logging.getLogger(__name__)

# === Core Pipeline Runner (Internal Function) ===


# Keep the underscore prefix as it's primarily called by the functions within this module
# or the main orchestrator (main.py).
def _run_pipeline_for_file(video_file_path: str, options: dict[str, Any] | None = None) -> bool:
    """
    Sets up and runs the subtitle processing pipeline for a single video file.

    Args:
        video_file_path (str): Full path to the video file.
        options (dict, optional): Processing options (e.g., skip flags). Defaults to {}.

    Returns:
        bool: True if the pipeline reported overall success (found RO or suitable EN),
              False otherwise.
    """
    options = options or {}
    video_basename = Path(video_file_path).name
    logger.info(f"Preparing pipeline for: {video_basename}")

    # --- 1. Initialize DI Container ---
    # A fresh container for each file ensures service states (like login tokens)
    # are managed correctly per processing run.
    di_container = ServiceContainer()

    # --- 2. Gather Initial Video Info ---
    video_info: dict[str, Any] = {"basename": video_basename}
    imdb_id: str | None = None
    media_type: str | None = None
    title_or_show_name: str | None = None  # For logging

    try:
        # Try TV show extraction first (more specific pattern)
        show_name, s, e, year = imdb_service.extract_tv_show_details(video_basename)
        if show_name and s and e:
            media_type = "episode"
            title_or_show_name = show_name
            video_info.update({"s": s, "e": e, "year": year, "show_name": show_name})
            # Get IMDb ID for the show (using DI container's instance if needed)
            imdb_id_result, _, _ = di_container.imdb.get_imdb_id(
                show_name, year, content_type="series"
            )
            imdb_id = imdb_id_result
        else:
            # Fallback to movie extraction
            title, year = imdb_service.extract_movie_details(video_basename)
            if title:
                media_type = "movie"
                title_or_show_name = title
                video_info.update({"year": year, "title": title})
                # Get IMDb ID for the movie
                imdb_id_result, _, _ = di_container.imdb.get_imdb_id(
                    title, year, content_type="movie"
                )
                imdb_id = imdb_id_result
            else:
                logger.error(
                    f"Could not extract meaningful title/details from filename: {video_basename}. Cannot process."
                )
                # Ensure services requiring shutdown (like logout) are handled even on early exit
                di_container.shutdown()
                return False  # Cannot proceed without basic info

        if not imdb_id:
            # Log warning but proceed - local/embed strategies might still work
            logger.warning(
                f"Could not retrieve IMDb ID for {media_type or 'media'} '{title_or_show_name or video_basename}'. Online fetching will be skipped."
            )

        video_info["type"] = media_type
        video_info["imdb_id"] = imdb_id
        logger.info(
            f"Identified media: Type='{media_type or 'Unknown'}', Title='{title_or_show_name or 'Unknown'}', IMDb='{imdb_id or 'N/A'}'"
        )

    except Exception as info_err:
        logger.error(
            f"Error gathering initial info for '{video_basename}': {info_err}", exc_info=True
        )
        di_container.shutdown()  # Ensure cleanup on error
        return False

    # --- 3. Create Processing Context ---
    # Pass all gathered info and options to the context.
    # target_ro/en_path will be set by StandardFileChecker strategy initially.
    context = ProcessingContext(
        video_path=video_file_path,
        video_info=video_info,
        options=options,
        di=di_container,  # Pass the container instance for strategies to use
    )

    # --- 4. Define and Instantiate Pipeline ---
    # The order of strategies is crucial for the desired logic flow.
    strategy_classes = [
        StandardFileChecker,  # 1. Check standard named files (.ro.srt, .en.srt -> candidate_en_path_standard)
        EmbedScanner,  # 2. Check embedded streams (RO -> final, EN -> candidate_en_path_embedded)
        LocalScanner,  # 3. Check other local .srt files (RO -> final, EN -> could overwrite candidate)
        OnlineFetcher,  # 4. Search online (RO -> final, EN -> candidate_en_path_online)
        FinalSelector,  # 5. *Selects* final_en_sub_path from candidates if RO not found
        Translator,  # 6. Translates final_en_sub_path to RO if needed and possible
        Synchronizer,  # 7. Syncs the final selected subtitle (RO or EN)
    ]
    try:
        pipeline = SubtitlePipeline(strategy_classes)
    except (
        ValueError
    ) as pipe_init_err:  # Catch errors during pipeline init (e.g., empty strategy list)
        logger.critical(
            f"Pipeline initialization failed for '{video_basename}': {pipe_init_err}", exc_info=True
        )
        di_container.shutdown()
        return False

    # --- 5. Run Pipeline ---
    # The pipeline itself handles logging start/end, strategy execution, errors, and cleanup.
    try:
        pipeline_success = pipeline.run(context)
        # The pipeline's return value directly indicates if a suitable subtitle was finalized.
        return pipeline_success
    except Exception as pipe_run_err:
        # Catch unexpected errors during the pipeline's run orchestration
        logger.critical(
            f"Pipeline execution failed critically for '{video_basename}': {pipe_run_err}",
            exc_info=True,
        )
        # Ensure container shutdown is called even on pipeline error (though pipeline's finally should also do it)
        # The DI container instance is held by the context, which pipeline manages.
        # If the error is *before* pipeline.run finishes, manually trigger shutdown.
        # If it's *during* pipeline.run, the pipeline's finally block should handle it.
        # Calling shutdown multiple times should be safe if implemented correctly in the DI container.
        di_container.shutdown()
        return False


# === Public Processing Functions ===


def process_movie_folder(movie_path: str, options: dict[str, Any] | None = None) -> int:  # noqa: C901
    """
    Processes all movie files in a given folder using the SubtitlePipeline.
    If `movie_path` is a file, processes only that file.

    Args:
        movie_path (str): Path to the movie folder or a single movie file.
        options (dict, optional): Processing options. Defaults to {}.

    Returns:
        int: The number of files for which the pipeline reported success.
    """
    logger.info(f"Starting Movie Folder/File Processing (Pipeline): {movie_path}")
    options = options or {}
    processed_files_count = 0
    successful_pipelines_count = 0
    target_path = Path(movie_path).resolve()

    files_to_process = []
    if target_path.is_file():
        # Check if it's a video file before adding
        if target_path.suffix.lower() in VIDEO_EXTENSIONS and not any(
            p in target_path.name.upper() for p in SKIP_PATTERNS
        ):
            files_to_process.append(str(target_path))
        else:
            logger.warning(f"Input path is a file but not a processable video file: {movie_path}")
    elif target_path.is_dir():
        logger.info(f"Scanning for movie files in: {target_path}")
        for root, _, files in os.walk(str(target_path)):
            for file in files:
                if file.lower().endswith(tuple(VIDEO_EXTENSIONS)) and not any(
                    p in file.upper() for p in SKIP_PATTERNS
                ):
                    full_path = Path(root) / file
                    # Basic check: ensure it doesn't look like a TV episode
                    _, s, e, _ = imdb_service.extract_tv_show_details(file)
                    if not (s and e):  # If season/episode not found, assume movie-like
                        files_to_process.append(str(full_path))
                    else:
                        logger.debug(
                            f"Skipping file (looks like TV episode) during movie scan: {file}"
                        )
    else:
        logger.error(f"Invalid path provided to process_movie_folder: {movie_path}")
        return 0

    if not files_to_process:
        logger.info("No suitable movie files found to process.")
        return 0

    logger.info(f"Found {len(files_to_process)} potential movie file(s) to process.")

    for video_file_path in files_to_process:
        if not Path(video_file_path).exists():
            logger.warning(
                f"Video file seems to have been removed during scan: {video_file_path}. Skipping."
            )
            continue

        processed_files_count += 1
        try:
            # Run the pipeline for the individual file and check success
            if _run_pipeline_for_file(video_file_path, options):
                successful_pipelines_count += 1
                # Success logging is handled inside _run_pipeline_for_file and pipeline
            else:
                # Failure logging is handled inside _run_pipeline_for_file and pipeline
                pass
        except Exception as e:
            # Catch unexpected errors at the file level to allow processing others
            logger.error(
                f"!! Unhandled error during pipeline invocation for movie file {video_file_path}: {e}",
                exc_info=True,
            )

    logger.info(f"Movie Folder/File Processing Complete (Pipeline): {movie_path}")
    logger.info(
        f"Attempted processing for {processed_files_count} video files. Pipeline reported success for {successful_pipelines_count} files."
    )
    return successful_pipelines_count


def process_tv_show_folder(tv_show_path: str, options: dict[str, Any] | None = None) -> int:  # noqa: C901
    """
    Processes TV show episodes in a given folder using the SubtitlePipeline.

    Args:
        tv_show_path (str): Path to the TV show folder (containing season folders or episodes).
        options (dict, optional): Processing options. Defaults to {}.

    Returns:
        int: The number of episodes for which the pipeline reported success.
    """
    logger.info(f"Starting TV Show Folder Processing (Pipeline): {tv_show_path}")
    options = options or {}
    processed_episodes_count = 0
    successful_pipelines_count = 0
    target_path = Path(tv_show_path).resolve()

    if not target_path.is_dir():
        logger.error(f"Invalid directory path provided to process_tv_show_folder: {tv_show_path}")
        return 0

    episode_paths = []
    logger.info(f"Scanning for TV episode files in: {target_path}...")
    try:
        for root, _, files in os.walk(str(target_path)):
            for file in files:
                if any(p in file.upper() for p in SKIP_PATTERNS):
                    continue
                if not file.lower().endswith(tuple(VIDEO_EXTENSIONS)):
                    continue

                video_file_path = Path(root) / file
                if not video_file_path.exists():
                    continue

                # Check if it looks like an episode file using naming convention
                show_name, season, episode, _ = imdb_service.extract_tv_show_details(file)
                if show_name and season and episode:
                    episode_paths.append(str(video_file_path))
                    logger.debug(f"Found potential episode: {file}")
                else:
                    logger.debug(f"Skipping file (doesn't match TV pattern): {file}")
    except Exception as walk_err:
        logger.error(f"Error scanning directory {tv_show_path}: {walk_err}", exc_info=True)
        return 0  # Cannot proceed if scan fails

    if not episode_paths:
        logger.info("No TV show episodes found matching expected patterns.")
        return 0
    logger.info(f"Scan complete. Found {len(episode_paths)} potential episode files.")

    # --- Process Each Episode File ---
    for video_path in episode_paths:
        if not Path(video_path).exists():
            logger.warning(
                f"Episode file gone before processing: {Path(video_path).name}. Skipping."
            )
            continue

        processed_episodes_count += 1
        try:
            # Run the pipeline for the individual episode file
            if _run_pipeline_for_file(video_path, options):
                successful_pipelines_count += 1
            # Success logging handled by pipeline
            else:
                # Failure logging handled by pipeline
                pass
        except Exception as e:
            # Catch errors at the file level
            logger.error(
                f"!! Unhandled error during pipeline invocation for episode file {video_path}: {e}",
                exc_info=True,
            )

    logger.info(f"TV Show Folder Processing Finished (Pipeline): {tv_show_path}")
    logger.info(
        f"Attempted processing for {processed_episodes_count} potential episodes. Pipeline reported success for {successful_pipelines_count} episodes."
    )
    return successful_pipelines_count


# === Utility Function (Used before main processing) ===


def determine_content_type_for_path(directory: str) -> str | None:  # noqa: C901
    """
    Determines if the directory content is primarily movies or TV shows
    based on counting filename patterns up to a configurable limit and threshold.

    Args:
        directory (str): The directory path to scan.

    Returns:
        Optional[str]: "tvshow", "movie", or None if no video files are found,
                       scan fails early, or the path is invalid.
    """
    logger.debug(f"Attempting content type detection for directory: {directory}")
    target_path = Path(directory).resolve()
    if not target_path.is_dir():
        logger.warning(
            f"Content type detection skipped: Path is not a valid directory: {directory}"
        )
        return None

    tv_count = 0
    movie_count = 0
    checked_files = 0
    file_limit = getattr(settings, "CONTENT_DETECTION_FILE_LIMIT", 50)
    tv_threshold_percent = getattr(settings, "CONTENT_DETECTION_TV_THRESHOLD_PERCENT", 50.0)
    # visited_paths = set() # Avoids issues with potential symlink loops, good practice

    try:
        # Use scandir for potentially better performance, but walk is fine
        for _, _, files in os.walk(
            str(target_path), topdown=True, followlinks=False
        ):  # Avoid infinite loops with followlinks=False
            if checked_files >= file_limit:
                logger.debug(f"Content detection limit ({file_limit}) reached.")
                break
            for file in files:
                if checked_files >= file_limit:
                    break
                # Construct full path for checks
                # file_path = os.path.join(root, file) # Not strictly needed if not using visited_paths

                # Check extension first (cheaper)
                if any(file.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
                    # Skip based on patterns
                    if any(p in file.upper() for p in SKIP_PATTERNS):
                        logger.debug(f"Skipping pattern match file during detection: {file}")
                        continue

                    # Now perform the more expensive name parsing
                    try:
                        show_name, season, episode, _ = imdb_service.extract_tv_show_details(file)
                        checked_files += 1
                        if show_name and season and episode:
                            tv_count += 1
                        else:
                            # Assume movie if not clearly an episode
                            movie_count += 1
                    except Exception as parse_err:
                        # Log error during parsing but still count it as checked (likely movie)
                        logger.debug(
                            f"Error parsing filename during detection for '{file}': {parse_err}. Counting as movie/other."
                        )
                        checked_files += 1
                        movie_count += 1

    except OSError as e_walk:  # Catch filesystem errors
        logger.error(f"Error during content type detection walk for '{directory}': {e_walk}.")
        # If walk failed early and we checked nothing, we can't determine type
        if checked_files == 0:
            logger.warning(
                f"Scan failed early for '{directory}' and no video files were checked. Cannot determine type."
            )
            return None
    except Exception as e_generic:  # Catch other unexpected errors
        logger.error(
            f"Unexpected error during content type detection walk for '{directory}': {e_generic}",
            exc_info=True,
        )
        if checked_files == 0:
            logger.warning(
                f"Scan failed unexpectedly for '{directory}' before checking files. Cannot determine type."
            )
            return None

    logger.debug(
        f"Detection scan results for '{directory}': Checked={checked_files}, TV={tv_count}, Movie/Other={movie_count}"
    )

    if checked_files == 0:
        logger.warning(
            f"No processable video files found matching patterns in '{directory}' during scan. Cannot determine type."
        )
        return None

    # Calculate percentage and determine type based on threshold
    tv_percentage = (tv_count / checked_files) * 100.0
    logger.info(
        f"Directory '{Path(directory).name}' TV Show Percentage = {tv_percentage:.1f}% (Threshold: {tv_threshold_percent}%)"
    )

    if tv_percentage >= tv_threshold_percent:
        return "tvshow"
    else:
        return "movie"


# === Define Public Interface ===
# List functions intended to be imported and used by other modules (like main.py)
__all__ = [
    "determine_content_type_for_path",
    "process_movie_folder",
    "process_tv_show_folder",
    # Note: _run_pipeline_for_file is not listed here as it's "internal",
    # but main.py imports it directly. This is acceptable.
]
