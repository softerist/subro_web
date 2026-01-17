import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# Note: opensubtitles_service is NOT directly used here anymore for core processing
# --- Import Config & Constants ---
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

# --- Configuration & Constants (New v2.0) ---


class ContentType(str, Enum):
    """Content type classification"""

    MOVIE = "movie"
    TV = "tv"
    UNKNOWN = "unknown"


@dataclass
class DetectionSignals:
    """Normalized detection signals from path analysis"""

    # Filename signals
    has_tv_episode_pattern: bool = False  # S01E01, 1x01
    has_date_pattern: bool = False  # 2024.01.17 (daily shows)
    has_absolute_numbering: bool = False  # Show - 001
    has_multi_episode: bool = False  # S01E01-E02

    # Path structure signals
    has_season_folder: bool = False
    in_tv_named_folder: bool = False
    in_movie_named_folder: bool = False
    in_ignored_folder: bool = False  # sample, extras, etc.

    # Directory content signals (if scanning)
    tv_episode_count: int = 0
    movie_file_count: int = 0

    # Metadata
    path_depth: int = 0
    is_file: bool = True


@dataclass
class DetectionConfig:
    """Configuration for content detection"""

    # Folder indicators (normalized, lowercase)
    TV_INDICATORS: set[str] = field(
        default_factory=lambda: {"tv shows", "tv", "series", "episodes", "television"}
    )
    MOVIE_INDICATORS: set[str] = field(
        default_factory=lambda: {"movies", "films", "cinema", "flicks"}
    )

    # Folders to skip (prevent false positives)
    IGNORED_DIRS: set[str] = field(
        default_factory=lambda: {
            "sample",
            "samples",
            "subs",
            "subtitles",
            "extras",
            "featurettes",
            "behind the scenes",
            "deleted scenes",
            "bonus",
            "trailer",
            "trailers",
        }
    )

    # Performance limits
    MAX_SCAN_DEPTH: int = 3
    MAX_FILES_TO_SCAN: int = 15  # Stop after sampling this many files
    MAX_SCAN_TIME_SECONDS: float = 2.0  # Timeout for directory scans

    # Confidence thresholds
    MIN_TV_CONFIDENCE: int = 2  # Minimum score to classify as TV
    MIN_MOVIE_CONFIDENCE: int = 2  # Minimum score to classify as movie

    # Video extensions
    VIDEO_EXTENSIONS: set[str] = field(
        default_factory=lambda: {
            ".mkv",
            ".mp4",
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".m4v",
            ".mpg",
            ".mpeg",
            ".m2ts",
            ".ts",
            ".webm",
        }
    )


# Compiled regex patterns (performance optimization)
TV_PATTERNS = {
    "season_episode": re.compile(r"(?<!\w)[Ss]\d{1,2}[Ee]\d{1,2}(?!\w)"),
    "numeric_episode": re.compile(r"(?<!\w)\d{1,2}x\d{1,2}(?!\w)"),
    "multi_episode": re.compile(r"(?<!\w)[Ss]\d{1,2}[Ee]\d{1,2}[_\-]?[Ee]?\d{2}(?!\w)"),
    "date_pattern": re.compile(r"(?<!\w)\d{4}[.\-_]\d{2}[.\-_]\d{2}(?!\w)"),
    "absolute_numbering": re.compile(r"(?<!\w)\-\s*\d{2,4}(?!\w)"),  # Show - 001
    "season_folder": re.compile(r"(?i)^season[\s._\-]*0*(\d+)$"),
    "season_generic": re.compile(r"(?:season|s)\s*([0-9]{1,3})", re.IGNORECASE),  # Merged from user
}

_SEASON_PATTERN = TV_PATTERNS[
    "season_generic"
]  # Alias for backward compatibility with user helpers

# === Core Pipeline Runner (Internal Function) ===


# Keep the underscore prefix as it's primarily called by the functions within this module
# or the main orchestrator (main.py).
def _run_pipeline_for_file(
    video_file_path: str,
    options: dict[str, Any] | None = None,
    tv_show_details: dict[str, str | None] | None = None,
) -> bool:
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
        if tv_show_details:
            show_name = tv_show_details.get("show_name")
            s = tv_show_details.get("season")
            e = tv_show_details.get("episode")
            year = tv_show_details.get("year")
            if not (show_name and s and e):
                logger.error(
                    f"Invalid TV show details provided for '{video_basename}'. Cannot process."
                )
                di_container.shutdown()
                return False
            media_type = "episode"
            title_or_show_name = show_name
            video_info.update({"s": s, "e": e, "year": year, "show_name": show_name})
            imdb_id_result, _, _ = di_container.imdb.get_imdb_id(
                show_name, year, content_type="series"
            )
            imdb_id = imdb_id_result
        else:
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


def process_tv_show_file(episode_path: str, options: dict[str, Any] | None = None) -> int:
    """
    Processes a single TV show episode file using the SubtitlePipeline.

    Args:
        episode_path (str): Path to a single episode file.
        options (dict, optional): Processing options. Defaults to {}.

    Returns:
        int: 1 if the pipeline reported success, 0 otherwise.
    """
    logger.info(f"Starting TV Show File Processing (Pipeline): {episode_path}")
    options = options or {}
    target_path = Path(episode_path).resolve()

    if not target_path.is_file():
        logger.error(f"Invalid file path provided to process_tv_show_file: {episode_path}")
        return 0

    if target_path.suffix.lower() not in VIDEO_EXTENSIONS:
        logger.warning(f"Input path is a file but not a processable video file: {episode_path}")
        return 0

    if any(p in target_path.name.upper() for p in SKIP_PATTERNS):
        logger.warning(f"Input file matches skip pattern: {episode_path}")
        return 0

    show_name, season, episode, year = _infer_tv_show_details_for_file(target_path)
    if not (show_name and season and episode):
        logger.info(
            f"File does not match TV episode patterns, falling back to movie processing: {episode_path}"
        )
        # Fallback to movie processing for files without episode patterns
        # This handles cases like movies placed in TV show folders
        return (_run_pipeline_for_file(str(target_path), options) and 1) or 0

    try:
        tv_show_details = {
            "show_name": show_name,
            "season": season,
            "episode": episode,
            "year": year,
        }
        if _run_pipeline_for_file(str(target_path), options, tv_show_details=tv_show_details):
            return 1
        return 0
    except Exception as e:
        logger.error(
            f"!! Unhandled error during pipeline invocation for episode file {episode_path}: {e}",
            exc_info=True,
        )
        return 0


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


def _extract_season_from_path(path: Path) -> str | None:
    season = None
    for part in path.parts:
        normalized = part.lower().replace("_", " ").replace("-", " ").strip()
        match = _SEASON_PATTERN.search(normalized)
        if match:
            season = str(int(match.group(1))).zfill(2)
    return season


def _normalize_path_parts(path: Path) -> tuple[list[str], list[str]]:
    parts = list(path.parts[:-1])
    normalized_parts = [part.lower().replace("_", " ").replace("-", " ").strip() for part in parts]
    return parts, normalized_parts


def _find_last_index(normalized_parts: list[str], predicate: Callable[[str], object]) -> int | None:
    last_index = None
    for idx, normalized in enumerate(normalized_parts):
        if predicate(normalized):
            last_index = idx
    return last_index


def _show_name_from_season_folder(
    parts: list[str], normalized_parts: list[str], tv_keywords: set[str]
) -> str | None:
    season_index = _find_last_index(normalized_parts, _SEASON_PATTERN.search)
    if season_index is None or season_index == 0:
        return None

    candidate = parts[season_index - 1]
    candidate_normalized = normalized_parts[season_index - 1]
    if candidate_normalized in tv_keywords:
        return None
    return candidate


def _show_name_after_tv_keyword(
    parts: list[str], normalized_parts: list[str], tv_keywords: set[str]
) -> str | None:
    tv_index = _find_last_index(normalized_parts, lambda value: value in tv_keywords)
    if tv_index is None:
        return None

    for idx in range(tv_index + 1, len(parts)):
        candidate_normalized = normalized_parts[idx]
        if candidate_normalized in tv_keywords:
            continue
        if _SEASON_PATTERN.search(candidate_normalized):
            continue
        return parts[idx]
    return None


def _extract_show_name_from_path(path: Path) -> str | None:
    tv_keywords = {"tv show", "tv shows", "tvshows", "series", "episode", "episodes"}
    parts, normalized_parts = _normalize_path_parts(path)

    show_name = _show_name_from_season_folder(parts, normalized_parts, tv_keywords)
    if show_name:
        return show_name
    return _show_name_after_tv_keyword(parts, normalized_parts, tv_keywords)


def _infer_tv_show_details_for_file(
    file_path: Path,
) -> tuple[str | None, str | None, str | None, str | None]:
    show, season, episode, year = imdb_service.extract_tv_show_details(file_path.name)
    if show and season and episode:
        return show, season, episode, year

    show_name = _extract_show_name_from_path(file_path)
    if not show_name:
        return None, None, None, None

    season_from_path = _extract_season_from_path(file_path.parent)
    synthetic_parts = [show_name]
    if season_from_path:
        synthetic_parts.append(f"Season {season_from_path}")
    synthetic_parts.append(file_path.stem)
    synthetic_name = " ".join(part for part in synthetic_parts if part)

    return imdb_service.extract_tv_show_details(synthetic_name)


def _path_has_tv_keywords(path: Path) -> bool:
    tv_keywords = {"tv show", "tv shows", "tvshows", "series", "episode", "episodes"}
    for part in path.parts:
        normalized = part.lower().replace("_", " ").replace("-", " ").strip()
        if normalized in tv_keywords:
            return True
        if normalized.startswith("season") and any(ch.isdigit() for ch in normalized):
            return True
    return False


def _score_tv(signals: DetectionSignals) -> int:
    tv_score = 0
    for condition, points in (
        (signals.has_tv_episode_pattern, 5),
        (signals.has_multi_episode, 5),
        (signals.has_season_folder, 3),
        (signals.in_tv_named_folder, 3),
        (signals.has_date_pattern, 2),
        (signals.has_absolute_numbering, 2),
    ):
        if condition:
            tv_score += points

    if signals.tv_episode_count >= 3:
        tv_score += 4
    elif signals.tv_episode_count >= 1:
        tv_score += 2

    return tv_score


def _score_movie(signals: DetectionSignals) -> int:
    movie_score = 0
    for condition, points in (
        (signals.in_movie_named_folder, 3),
        (signals.movie_file_count >= 1 and signals.tv_episode_count == 0, 2),
    ):
        if condition:
            movie_score += points

    if signals.is_file and not (
        signals.has_tv_episode_pattern
        or signals.has_multi_episode
        or signals.has_absolute_numbering
        or signals.has_date_pattern
    ):
        movie_score += 3  # Boost for clean filenames that look like movies

    return movie_score


def _apply_negative_signals(
    tv_score: int, movie_score: int, signals: DetectionSignals
) -> tuple[int, int]:
    if signals.in_tv_named_folder:
        # If in TV folder but NO episode pattern, be less harsh on movie score
        # This allows movies misfiled in TV folders to be detected as movies
        if signals.has_tv_episode_pattern or signals.has_season_folder:
            movie_score -= 5
        else:
            movie_score -= 1  # Light penalty only

    if signals.in_movie_named_folder:
        # If in movie folder but looks like TV (e.g. multi-episode file),
        # still penalize TV score, but maybe check patterns too?
        # For now, keep it strict as movies rarely look like TV episodes
        tv_score -= 5
    return tv_score, movie_score


def decide_content_type(signals: DetectionSignals, config: DetectionConfig) -> ContentType:
    """
    Pure function to decide content type from signals.

    Uses a scoring system with confidence thresholds to avoid
    misclassification in ambiguous cases.
    """
    if signals.in_ignored_folder:
        return ContentType.UNKNOWN

    tv_score = _score_tv(signals)
    movie_score = _score_movie(signals)
    tv_score, movie_score = _apply_negative_signals(tv_score, movie_score, signals)

    # Decision with confidence thresholds
    if tv_score >= config.MIN_TV_CONFIDENCE and tv_score > movie_score:
        return ContentType.TV
    if movie_score >= config.MIN_MOVIE_CONFIDENCE and movie_score > tv_score:
        return ContentType.MOVIE

    # Low confidence - don't guess
    return ContentType.UNKNOWN


def _extract_signals(p: Path, config: DetectionConfig) -> DetectionSignals:
    """Extract all detection signals from a path"""
    signals = DetectionSignals()
    signals.is_file = p.is_file() if p.exists() else True  # Assume file if unsure

    # For files: analyze filename and parent structure
    if signals.is_file:
        if not _is_video_file(p, config):
            return signals  # Not a video, return empty signals

        signals = _analyze_filename(p.name, signals)
        signals = _analyze_path_structure(p, config, signals)
    else:
        # For directories: scan contents (with limits)
        signals = _scan_directory(p, config, signals)

    return signals


def _is_video_file(p: Path, config: DetectionConfig) -> bool:
    """Check if file has video extension (case-insensitive)"""
    return p.suffix.lower() in config.VIDEO_EXTENSIONS


def _analyze_filename(filename: str, signals: DetectionSignals) -> DetectionSignals:
    """Extract signals from filename patterns"""
    # TV episode patterns
    if TV_PATTERNS["season_episode"].search(filename):
        signals.has_tv_episode_pattern = True
    if TV_PATTERNS["numeric_episode"].search(filename):
        signals.has_tv_episode_pattern = True
    if TV_PATTERNS["multi_episode"].search(filename):
        signals.has_multi_episode = True
        signals.has_tv_episode_pattern = True
    if TV_PATTERNS["date_pattern"].search(filename):
        signals.has_date_pattern = True
    if TV_PATTERNS["absolute_numbering"].search(filename):
        signals.has_absolute_numbering = True

    return signals


def _analyze_path_structure(
    p: Path, config: DetectionConfig, signals: DetectionSignals
) -> DetectionSignals:
    """Analyze parent directory structure for signals"""
    # Traverse parents (limit depth for performance)
    for i, part in enumerate(p.parts):
        if i > 10:  # Safety limit
            break

        # Normalize folder name for comparison
        normalized = _normalize_folder_name(part)

        # Check for ignored directories
        if normalized in config.IGNORED_DIRS:
            signals.in_ignored_folder = True
            return signals  # Early exit

        # Check for TV indicators
        if normalized in config.TV_INDICATORS:
            signals.in_tv_named_folder = True

        # Check for movie indicators
        if normalized in config.MOVIE_INDICATORS:
            signals.in_movie_named_folder = True

        # Check for season folder pattern
        if TV_PATTERNS["season_folder"].match(part):
            signals.has_season_folder = True

    signals.path_depth = len(p.parts)
    return signals


def _normalize_folder_name(name: str) -> str:
    """Normalize folder name for matching"""
    # Convert to lowercase, replace separators with spaces, strip
    return name.lower().replace("_", " ").replace(".", " ").strip()


def _scan_timed_out(start_time: float, config: DetectionConfig, path: Path) -> bool:
    if time.time() - start_time > config.MAX_SCAN_TIME_SECONDS:
        logger.warning(f"Directory scan timeout for {path}")
        return True
    return False


def _calculate_depth(root: str, base: Path) -> int:
    try:
        return len(Path(root).relative_to(base).parts)
    except ValueError:
        return 0


def _prune_by_depth(root: str, base: Path, config: DetectionConfig, dirs: list[str]) -> bool:
    depth = _calculate_depth(root, base)
    if depth > config.MAX_SCAN_DEPTH:
        dirs[:] = []
        return True
    return False


def _filter_ignored_dirs(dirs: list[str], config: DetectionConfig) -> None:
    dirs[:] = [d for d in dirs if _normalize_folder_name(d) not in config.IGNORED_DIRS]


def _update_counts_from_filename(filename: str, signals: DetectionSignals) -> None:
    file_signals = _analyze_filename(filename, DetectionSignals())
    if file_signals.has_tv_episode_pattern or file_signals.has_multi_episode:
        signals.tv_episode_count += 1
    else:
        signals.movie_file_count += 1


def _scan_files_in_dir(
    root: str,
    files: list[str],
    config: DetectionConfig,
    signals: DetectionSignals,
    files_checked: int,
) -> int:
    for file in files:
        if files_checked >= config.MAX_FILES_TO_SCAN:
            break

        file_path = Path(root) / file
        if not _is_video_file(file_path, config):
            continue

        files_checked += 1
        _update_counts_from_filename(file, signals)

    return files_checked


def _scan_directory(
    p: Path, config: DetectionConfig, signals: DetectionSignals
) -> DetectionSignals:
    """
    Scan directory contents to detect patterns.

    CRITICAL PERFORMANCE SAFEGUARDS:
    - Maximum file limit
    - Maximum depth limit
    - Maximum time limit
    - No symlink following (prevents loops)
    """
    start_time = time.time()
    files_checked = 0

    try:
        # Use os.walk with safeguards
        for root, dirs, files in os.walk(
            str(p),
            topdown=True,
            followlinks=False,  # CRITICAL: Prevent symlink loops
        ):
            if _scan_timed_out(start_time, config, p):
                break

            if _prune_by_depth(root, p, config, dirs):
                continue

            _filter_ignored_dirs(dirs, config)

            files_checked = _scan_files_in_dir(root, files, config, signals, files_checked)
            if files_checked >= config.MAX_FILES_TO_SCAN:
                return signals

    except PermissionError:
        logger.warning(f"Permission denied scanning directory {p}")
    except OSError as e:
        logger.warning(f"Error scanning directory {p}: {e}")

    return signals


def determine_content_type_for_path(
    directory: str | Path | None, config: DetectionConfig | None = None, strict_exists: bool = False
) -> str | None:
    """
    Determine if the path (file or folder) is better classified as 'movie' or 'tvshow'.
    Uses a signal-based scoring system.

    Args:
        directory (str|Path): The directory or file path to scan.
        config (DetectionConfig, optional): Custom config.
        strict_exists (bool): If True, raises FileNotFoundError if path missing.

    Returns:
        Optional[str]: "tvshow", "movie", or None.
    """
    logger.debug(f"Attempting content type detection for: {directory}")

    if config is None:
        config = DetectionConfig()

    if not directory:
        return None

    try:
        # Resolve path
        target_path = Path(directory).resolve()

        if strict_exists and not target_path.exists():
            raise FileNotFoundError(f"Path does not exist: {directory}")

        # Extract signals
        signals = _extract_signals(target_path, config)

        # Decide
        result = decide_content_type(signals, config)
        logger.info(f"Classified '{target_path.name}' as {result.value} (Signals: {signals})")

        if result == ContentType.TV:
            return "tvshow"
        elif result == ContentType.MOVIE:
            return "movie"
        else:
            return None  # UNKNOWN -> None for compatibility

    except Exception as e:
        logger.error(f"Error determining content type for {directory}: {e}", exc_info=True)
        return None


# === Define Public Interface ===
# List functions intended to be imported and used by other modules (like main.py)
__all__ = [
    "determine_content_type_for_path",
    "process_movie_folder",
    "process_tv_show_file",
    "process_tv_show_folder",
    # Note: _run_pipeline_for_file is not listed here as it's "internal",
    # but main.py imports it directly. This is acceptable.
]
