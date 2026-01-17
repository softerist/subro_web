"""Torrent post-processing: renames subtitle files based on language detection."""

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from app.modules.subtitle.core.constants import SUBTITLE_EXTENSIONS_LOWER_TUPLE
from app.modules.subtitle.core.di import ServiceContainer
from app.modules.subtitle.services import torrent_client
from app.modules.subtitle.utils import file_utils, subtitle_parser

try:
    from app.modules.subtitle.core.constants import SUBTITLE_EXTENSIONS_LOWER_TUPLE
except ImportError:
    # Fallback if constants haven't been updated yet
    logging.warning(
        "Could not import SUBTITLE_EXTENSIONS_LOWER_TUPLE from constants. Using fallback."
    )
    SUBTITLE_EXTENSIONS_LOWER_TUPLE = (".srt", ".sub", ".ass")


logger = logging.getLogger(__name__)


def post_process_completed_torrents(target_directory: str) -> None:  # noqa: C901
    """
    (Optional Cleanup Step) Finds the torrent matching the target_directory,
    renames subtitle files based on language detection using qBittorrent API.

    Args:
        target_directory (str): The directory path potentially associated with a completed torrent.
    """
    if not target_directory or not Path(target_directory).is_dir():
        logger.error("Torrent post-processing skipped: Invalid target directory provided.")
        return

    norm_target_dir = os.path.normpath(os.path.normcase(target_directory))
    logger.info(
        f"Starting optional post-processing for torrent associated with directory: {norm_target_dir}"
    )

    temp_di_container = ServiceContainer()
    client = temp_di_container.qbittorrent

    if not client:
        logger.error(
            "Torrent post-processing failed: Could not get or log in to qBittorrent client."
        )
        temp_di_container.shutdown()  # Clean up container attempt
        return

    processed_count = 0
    found_torrent = None
    torrent_hash = None
    torrent_name = "N/A"
    save_path = None

    try:
        # Use the functions from the imported torrent_client service module
        torrents = torrent_client.get_completed_torrents(client)
        if not torrents:
            logger.info(
                "No completed/downloaded torrents found in qBittorrent to check against path."
            )
            return  # No return needed in finally, shutdown will happen

        logger.debug(
            f"Searching {len(torrents)} torrents for save path matching '{norm_target_dir}'..."
        )
        matching_torrents = []
        for t in torrents:
            # Access attributes directly if available, use getattr as fallback
            torrent_save_path = getattr(t, "save_path", None) or getattr(
                t, "save_path", None
            )  # Check both common attr names just in case
            if torrent_save_path:
                norm_torrent_save_path = os.path.normpath(os.path.normcase(torrent_save_path))
                # Check for exact match or if target_dir is a subdirectory matching the torrent name
                if norm_torrent_save_path == norm_target_dir:
                    logger.debug(
                        f"Found potential match (Exact): Torrent '{t.name}' (Hash: {t.hash})"
                    )
                    matching_torrents.append(t)
                elif norm_target_dir.startswith(norm_torrent_save_path + os.sep):
                    relative_part = Path(norm_target_dir).name
                    torrent_obj_name = getattr(t, "name", "")
                    # Heuristic: If the target subfolder name is contained within the torrent name
                    if torrent_obj_name and torrent_obj_name.lower() in relative_part.lower():
                        logger.debug(
                            f"Found potential match (Parent Dir Match): Torrent '{t.name}' (Hash: {t.hash})"
                        )
                        matching_torrents.append(t)
                    # Add more specific checks if needed, e.g., if torrent is single-file and path matches file name

        if not matching_torrents:
            logger.info(
                f"No active torrent found in qBittorrent matching path '{norm_target_dir}'."
            )
            return  # No return needed in finally
        elif len(matching_torrents) > 1:
            logger.warning(
                f"Multiple torrents match path '{norm_target_dir}'. Processing first: '{matching_torrents[0].name}'"
            )
            found_torrent = matching_torrents[0]
        else:
            found_torrent = matching_torrents[0]

        torrent_hash = found_torrent.hash
        torrent_name = found_torrent.name
        # Use the confirmed save_path from the matched torrent object
        save_path = getattr(found_torrent, "save_path", None) or getattr(
            found_torrent, "save_path", None
        )
        # The path we actually scan is the target_directory the user provided
        processing_base_path = target_directory
        completion_timestamp = getattr(found_torrent, "completion_on", 0)
        completion_dt_str = (
            str(datetime.fromtimestamp(completion_timestamp)) if completion_timestamp else "N/A"
        )
        logger.info(
            f"Processing torrent: '{torrent_name}' (Hash: {torrent_hash}, Completed: {completion_dt_str}, Save Path: {save_path})"
        )

        subtitle_files_to_process = []
        logger.debug(f"Scanning for subtitle files within: {processing_base_path}")
        if not save_path:
            logger.error(
                f"Cannot process files for torrent '{torrent_name}': Save path is missing from torrent info."
            )
            return  # Cannot proceed without save_path for relative path calculation

        try:
            abs_save_path = Path(save_path).resolve()  # Get absolute save path once
            for root, _, files in os.walk(processing_base_path):
                for file in files:
                    # Use the constant imported (or fallback)
                    if file.lower().endswith(SUBTITLE_EXTENSIONS_LOWER_TUPLE):
                        full_path = str(Path(root) / file)
                        rel_path_for_api = None
                        try:
                            # Ensure we compare absolute paths correctly
                            abs_full_path = Path(full_path).resolve()
                            # Check if the file's absolute path starts with the torrent's absolute save path
                            if (
                                str(abs_full_path).startswith(str(abs_save_path) + os.sep)
                                or abs_full_path == abs_save_path
                            ):  # Handle root case too
                                rel_path_for_api = os.path.relpath(
                                    abs_full_path, abs_save_path
                                ).replace(os.sep, "/")
                            else:
                                logger.debug(
                                    f"File '{abs_full_path}' not within torrent save path '{abs_save_path}'."
                                )
                        except ValueError:
                            logger.warning(
                                f"Path value error calculating relative path for '{full_path}' vs '{save_path}'"
                            )

                        if rel_path_for_api is not None:  # Use explicit None check
                            logger.debug(
                                f"Found subtitle for potential processing: '{full_path}' (Rel path: {rel_path_for_api})"
                            )
                            subtitle_files_to_process.append(
                                {"rel_path_api": rel_path_for_api, "full_path": full_path}
                            )
                        # else: logger.debug(f"Ignoring subtitle file not resolvable relative to torrent save path: {full_path}") # Reduced verbosity
        except Exception as walk_err:
            logger.error(
                f"Error walking directory during torrent post-processing scan: {walk_err}",
                exc_info=True,
            )
            return  # Abort if scan fails

        if not subtitle_files_to_process:
            logger.info(
                f"No processable subtitle files found within '{target_directory}' associated with the torrent '{torrent_name}'."
            )
            return

        logger.info(
            f"Found {len(subtitle_files_to_process)} subtitle file(s) to check in torrent '{torrent_name}'."
        )
        ro_found_and_processed = False
        # Import langdetect locally only if needed
        try:
            from langdetect import LangDetectException, detect
        except ImportError:
            LangDetectException = Exception  # Define dummy exception
            detect = None  # Set detect to None if import fails
            logger.warning(
                "langdetect library not available. Torrent post-processing language detection skipped."
            )

        for sub_info in subtitle_files_to_process:
            # If we found and processed a RO file, stop processing others in this torrent
            if ro_found_and_processed:
                logger.debug(
                    "RO subtitle already found and processed for this torrent. Skipping remaining checks."
                )
                break

            original_full_path = sub_info["full_path"]
            original_rel_path_api = sub_info["rel_path_api"]
            log_prefix = "[Torrent File] "

            if not Path(original_full_path).exists():
                logger.warning(
                    f"{log_prefix}File disappeared before processing: {original_full_path}"
                )
                continue

            try:
                if not detect:
                    logger.debug(
                        f"{log_prefix}Skipping language detection for '{Path(original_full_path).name}' (langdetect not loaded)."
                    )
                    continue

                # Use file_utils for robust reading
                sub_content = file_utils.read_srt_file(original_full_path)
                if not sub_content or not sub_content.strip():
                    logger.warning(
                        f"{log_prefix}Subtitle '{Path(original_full_path).name}' is empty. Skipping."
                    )
                    continue

                detected_lang = None
                try:
                    # Detect on first 5k chars for performance
                    detected_lang = detect(sub_content[:5000])
                    logger.info(
                        f"{log_prefix}Detected lang for '{Path(original_full_path).name}': {detected_lang}"
                    )
                except LangDetectException as lang_err:
                    logger.warning(
                        f"{log_prefix}Could not detect lang for '{Path(original_full_path).name}': {lang_err}. Skipping rename."
                    )
                    continue

                # Get base path without extension for creating new name
                # Important: Use only the filename part for generating the preferred path *basename*
                original_filename_base = Path(original_full_path).stem

                target_lang_full_path = None
                target_lang_rel_path_api = None

                # Handle Romanian ('ro') - Primary Target
                if detected_lang == "ro":
                    target_lang_filename = Path(
                        file_utils.get_preferred_subtitle_path(original_filename_base, "ro")
                    ).name
                    target_lang_full_path = str(
                        Path(original_full_path).parent / target_lang_filename
                    )
                    try:
                        # Calculate relative path for API call
                        target_lang_rel_path_api = os.path.relpath(
                            Path(target_lang_full_path).resolve(), abs_save_path
                        ).replace(os.sep, "/")
                    except ValueError:
                        pass  # Handle cases where paths are on different drives etc.

                    # Check if already correctly named
                    if os.path.normpath(os.path.normcase(original_full_path)) == os.path.normpath(
                        os.path.normcase(target_lang_full_path)
                    ):
                        logger.info(
                            f"{log_prefix}Already named correctly as RO. Applying content fixes if needed."
                        )
                        try:
                            # Use subtitle_parser utilities
                            processed_content = subtitle_parser.fix_diacritics(sub_content)
                            processed_content = subtitle_parser.ensure_correct_timestamp_format(
                                processed_content
                            )
                            if processed_content != sub_content:
                                file_utils.write_srt_file(
                                    original_full_path, processed_content, allow_fallback=False
                                )
                                logger.info(
                                    f"{log_prefix}Applied fixes to existing RO file: {Path(original_full_path).name}"
                                )
                            processed_count += 1
                            ro_found_and_processed = True  # Mark RO as done for this torrent
                        except Exception as e:
                            logger.error(
                                f"{log_prefix}Failed fixing content for {original_full_path}: {e}"
                            )
                    # Check if renaming is possible via API
                    elif target_lang_rel_path_api:
                        logger.info(
                            f"{log_prefix}Processing and renaming to standard RO name: {Path(target_lang_full_path).name}"
                        )
                        # Process content *first* to a temporary file in the *final* directory
                        temp_ro_path = target_lang_full_path + ".tmp_proc"
                        try:
                            processed_content = subtitle_parser.fix_diacritics(sub_content)
                            processed_content = subtitle_parser.ensure_correct_timestamp_format(
                                processed_content
                            )
                            file_utils.write_srt_file(
                                temp_ro_path, processed_content, allow_fallback=False
                            )

                            # Attempt rename via qBittorrent API
                            if torrent_client.rename_torrent_file(
                                client,
                                torrent_hash,
                                original_rel_path_api,
                                target_lang_rel_path_api,
                            ):
                                # If API rename succeeds, move the processed temp file to the final name
                                try:
                                    shutil.move(temp_ro_path, target_lang_full_path)
                                    logger.info(
                                        f"Moved processed content to final RO path: {Path(target_lang_full_path).name}"
                                    )
                                    processed_count += 1
                                    ro_found_and_processed = True  # Mark RO as done
                                except Exception as move_err:
                                    logger.error(
                                        f"{log_prefix}API rename OK, but move from temp file failed: {move_err}. Manual check needed for {target_lang_full_path}"
                                    )
                                    # Attempt cleanup of temp file even on move error
                                    if Path(temp_ro_path).exists():
                                        Path(temp_ro_path).unlink()
                                    # Consider trying to delete the original via API if move failed? Maybe too risky.
                            else:
                                logger.warning(
                                    f"{log_prefix}Failed qBittorrent API rename for RO file. Content processed to temp file but not moved."
                                )
                                # Cleanup temp file if rename failed
                                if Path(temp_ro_path).exists():
                                    Path(temp_ro_path).unlink()
                        except Exception as e:
                            logger.error(
                                f"{log_prefix}Error processing/renaming RO file: {e}", exc_info=True
                            )
                            # Ensure temp file cleanup on any exception during processing
                            if Path(temp_ro_path).exists():
                                try:
                                    Path(temp_ro_path).unlink()
                                except OSError:
                                    pass
                    else:
                        logger.warning(
                            f"{log_prefix}Cannot rename RO file via API (relative path issue?). Skipping rename for {Path(original_full_path).name}"
                        )

                # Handle Other Languages (only if RO not already found)
                elif not ro_found_and_processed and detected_lang and len(detected_lang) == 2:
                    lang_code = detected_lang.lower()
                    # Generate standard filename relative to original file's location
                    target_lang_filename = Path(
                        file_utils.get_preferred_subtitle_path(original_filename_base, lang_code)
                    ).name
                    target_lang_full_path = str(
                        Path(original_full_path).parent / target_lang_filename
                    )

                    try:
                        target_lang_rel_path_api = os.path.relpath(
                            Path(target_lang_full_path).resolve(), abs_save_path
                        ).replace(os.sep, "/")
                    except ValueError:
                        pass

                    # Check if already named correctly
                    if os.path.normpath(os.path.normcase(original_full_path)) == os.path.normpath(
                        os.path.normcase(target_lang_full_path)
                    ):
                        logger.info(f"{log_prefix}Already named correctly for lang '{lang_code}'.")
                        processed_count += 1
                    # Check if renaming is possible via API
                    elif target_lang_rel_path_api:
                        logger.info(
                            f"{log_prefix}Attempting rename '{Path(original_full_path).name}' to standard '{lang_code}' name via API."
                        )
                        try:
                            if torrent_client.rename_torrent_file(
                                client,
                                torrent_hash,
                                original_rel_path_api,
                                target_lang_rel_path_api,
                            ):
                                logger.info(
                                    f"{log_prefix}Renamed to '{target_lang_filename}' via qBittorrent."
                                )
                                processed_count += 1
                            else:
                                logger.warning(
                                    f"{log_prefix}Failed qBittorrent API rename for '{lang_code}' file."
                                )
                        except Exception as e:
                            logger.error(
                                f"{log_prefix}Error during API rename for '{lang_code}' file: {e}",
                                exc_info=True,
                            )
                    else:
                        logger.warning(
                            f"{log_prefix}Cannot rename '{lang_code}' file via API (relative path issue?). Skipping rename for {Path(original_full_path).name}"
                        )

            except FileNotFoundError:
                logger.warning(
                    f"{log_prefix}Subtitle file disappeared during processing: {original_full_path}"
                )
            except Exception as e:
                logger.error(
                    f"{log_prefix}Unexpected error processing subtitle {original_full_path}: {e}",
                    exc_info=True,
                )

        if not ro_found_and_processed and detect:  # Check if langdetect was available
            logger.info(
                f"Finished torrent post-processing check/rename pass for '{torrent_name}'. No RO subtitle was finalized."
            )
        elif not detect:
            logger.info(
                f"Finished torrent post-processing scan for '{torrent_name}'. Language detection was skipped."
            )

    except Exception as e:
        logger.error(
            f"Error during torrent post-processing for '{torrent_name or target_directory}': {e}",
            exc_info=True,
        )
    finally:
        if found_torrent:
            logger.info(
                f"Torrent post-processing attempt finished for '{torrent_name}'. Processed/Checked: {processed_count}"
            )
        # Ensure the temporary DI container's shutdown method is called (e.g., for potential logout)
        temp_di_container.shutdown()


__all__ = [
    "post_process_completed_torrents",
]
