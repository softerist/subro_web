# src/core/strategies/online_fetcher.py
import logging
import tempfile
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.modules.subtitle.utils import file_utils, subtitle_matcher, subtitle_parser

from .base import ProcessingContext, ProcessingStrategy

logger = logging.getLogger(__name__)

MIN_SCORE_THRESHOLD = getattr(
    settings, "SUBTITLE_MIN_OVERALL_SCORE", 5
)  # Min score to accept candidate


class OnlineFetcher(ProcessingStrategy):
    """
    Strategy to find, download, and process subtitles from online sources
    (Subs.ro, OpenSubtitles.org). Relies on DI container for service clients.
    It prioritizes finding RO subtitles. If an EN subtitle is processed,
    it's stored as a candidate in the context.
    """

    def execute(self, context: ProcessingContext) -> bool:  # noqa: C901
        # --- Pre-conditions ---
        if context.found_final_ro:
            self.logger.debug("Skipping: Final RO subtitle already found.")
            return True

        imdb_id = context.video_info.get("imdb_id")
        if not imdb_id:
            self.logger.warning(
                f"Skipping: Missing IMDb ID in context for video '{context.video_info.get('basename', 'Unknown')}'."
            )
            return True

        media_type = context.video_info.get("type")  # 'movie' or 'episode'
        if not media_type:
            self.logger.warning("Skipping: Missing media type ('movie'/'episode') in context.")
            return True

        self.logger.info(f"Searching online sources for IMDb ID: {imdb_id} (Type: {media_type})...")

        all_candidates = []
        # Create one main temp dir for this strategy run, will contain subdirs
        main_temp_dir = tempfile.mkdtemp(prefix=f"online_fetch_{imdb_id}_")
        context.add_temp_dir(main_temp_dir)
        self.logger.debug(f"Created main temp directory for online downloads: {main_temp_dir}")

        # Access services via Dependency Injection container
        subsro = context.di.subsro
        opensubs = context.di.opensubtitles  # This is the OpenSubtitlesClient instance

        # --- Gather Candidates ---
        try:
            # --- Subs.ro ---
            if subsro:
                try:
                    # Use a subdir within the main temp dir for subs.ro downloads
                    subsro_temp_sub_dir = Path(main_temp_dir) / "subsro"
                    subsro_temp_sub_dir.mkdir(exist_ok=True)

                    for lang in ["ro", "en"]:
                        urls = subsro.find_subtitle_download_urls(imdb_id, language_code=lang)
                        if not urls:
                            continue

                        self.logger.info(f"Processing {len(urls)} Subs.ro '{lang}' URLs...")
                        for index, url in enumerate(urls):
                            # Create a unique subdir for each archive to avoid filename collisions
                            archive_extract_dir = subsro_temp_sub_dir / f"{lang}_{index}"
                            extracted_sub_file_path = None
                            try:
                                archive_extract_dir.mkdir(exist_ok=True)
                                # Download archive into the extraction dir itself
                                archive_path = subsro.download_subtitle_archive(
                                    url,
                                    str(archive_extract_dir),
                                    filename_prefix=f"subsro_{lang}_{index}",
                                )
                                if not archive_path:
                                    continue

                                # Extract archive within its specific subdir
                                if not file_utils.extract_archive(
                                    archive_path, str(archive_extract_dir)
                                ):
                                    self.logger.warning(
                                        f"Failed to extract Subs.ro archive: {archive_path}"
                                    )
                                    continue

                                # Find the best sub *within* the extracted archive dir
                                best_local_path, _ = (
                                    subtitle_matcher.find_best_matching_subtitle_local(
                                        context.video_path,
                                        str(archive_extract_dir),
                                        lang,  # Pass lang hint
                                    )
                                )

                                if best_local_path:
                                    extracted_sub_file_path = best_local_path
                                    self.logger.debug(
                                        f"Selected best local match from Subs.ro archive: {Path(extracted_sub_file_path).name}"
                                    )
                                else:
                                    # Fallback: find *any* subtitle file if local matching fails
                                    extracted_subs = [
                                        str(p)
                                        for p in archive_extract_dir.rglob("*")
                                        if p.is_file()
                                        and p.suffix.lower() in {".srt", ".sub", ".ass"}
                                        and not p.name.lower().endswith((".bak", ".syncbak"))
                                    ]
                                    if extracted_subs:
                                        extracted_sub_file_path = extracted_subs[
                                            0
                                        ]  # Take the first one found
                                        self.logger.warning(
                                            f"Could not determine best local match in Subs.ro archive, using first found: {Path(extracted_sub_file_path).name}"
                                        )
                                    else:
                                        self.logger.warning(
                                            f"No subtitle files found after extracting Subs.ro archive: {archive_path}"
                                        )

                                if (
                                    extracted_sub_file_path
                                    and Path(extracted_sub_file_path).exists()
                                ):
                                    # Determine language (prefer detected, fallback to search lang)
                                    detected_lang = (
                                        subtitle_matcher.get_subtitle_language_code(
                                            Path(extracted_sub_file_path).name
                                        )
                                        or lang
                                    )

                                    candidate_dict = {
                                        "source": "subsro",
                                        "language": detected_lang,
                                        "id": url,
                                        "extracted_path": extracted_sub_file_path,  # Path to temp file within archive_extract_dir
                                        "file_name": Path(extracted_sub_file_path).name,
                                        "release_name": None,
                                        "score_bonus": 0,
                                        "attributes": {},
                                    }
                                    all_candidates.append(candidate_dict)
                                    self.logger.debug(
                                        f"Added Subs.ro candidate: Lang={detected_lang}, File={candidate_dict['file_name']}"
                                    )

                            except Exception as e_inner:
                                context.add_error(
                                    self.name, f"Error processing Subs.ro URL {url}: {e_inner}"
                                )
                                self.logger.exception(
                                    f"Error processing Subs.ro URL {url}.", exc_info=True
                                )

                except Exception as e_subsro:
                    context.add_error(self.name, f"Error gathering Subs.ro candidates: {e_subsro}")
                    self.logger.exception("Error gathering Subs.ro candidates.", exc_info=True)
            else:
                self.logger.warning("Subs.ro service not available in DI container.")

            # --- OpenSubtitles ---
            if opensubs:
                if not opensubs.authenticate():  # Use client's authenticate method
                    self.logger.warning(
                        "OpenSubtitles authentication failed or skipped. Skipping OpenSubtitles search."
                    )
                else:
                    search_params = {
                        "language": None,  # Iterate below
                        "imdb_id": imdb_id if media_type == "movie" else None,
                        "parent_imdb_id": imdb_id if media_type == "episode" else None,
                        "season_number": int(context.video_info["s"])
                        if context.video_info.get("s")
                        else None,
                        "episode_number": int(context.video_info["e"])
                        if context.video_info.get("e")
                        else None,
                        "query": context.video_info.get("basename", ""),  # Fallback query
                        "type": media_type,
                        "machine_translated": "exclude",
                        "hearing_impaired": "exclude",
                    }
                    for lang in ["ro", "en"]:
                        try:
                            search_params["language"] = lang
                            results = opensubs.search_subtitles(
                                **search_params
                            )  # Call client's search
                            if results:
                                self.logger.info(
                                    f"Processing {len(results)} OpenSubtitles '{lang}' candidates (metadata only)..."
                                )
                                for result in results:
                                    attrs = result.get("attributes", {})
                                    files = attrs.get("files", [])
                                    file_info = files[0] if files else {}
                                    file_id = file_info.get("file_id")
                                    if not file_id:
                                        continue

                                    api_lang = attrs.get("language")
                                    candidate_lang = api_lang if api_lang else lang
                                    all_candidates.append(
                                        {
                                            "source": "opensubtitles",
                                            "language": candidate_lang,
                                            "id": file_id,
                                            "release_name": attrs.get("release"),
                                            "file_name": file_info.get("file_name"),
                                            "attributes": attrs,
                                            "score_bonus": 0,
                                            "extracted_path": None,
                                        }
                                    )
                            else:
                                self.logger.debug(f"No OpenSubtitles results found for '{lang}'.")
                        except Exception as e_os_search:
                            context.add_error(
                                self.name,
                                f"Error searching OpenSubtitles for lang '{lang}': {e_os_search}",
                            )
                            self.logger.exception(
                                f"Error searching OpenSubtitles for lang '{lang}'.", exc_info=True
                            )
            else:
                self.logger.warning("OpenSubtitles service not available in DI container.")

        except Exception as gather_err:
            context.add_error(
                self.name, f"Unexpected error during candidate gathering: {gather_err}"
            )
            self.logger.exception("Unexpected error during candidate gathering.", exc_info=True)
            # Proceed to ranking if any candidates gathered before error

        # --- Ranking and Processing ---
        if not all_candidates:
            self.logger.info("No online candidates found from any source.")
            return True  # No candidates found isn't a failure

        # Rank candidates
        ranked_candidates = self._rank_candidates(
            all_candidates,
            context.video_info.get("basename", ""),
            context.video_info.get("s"),
            context.video_info.get("e"),
            required_language="ro",  # Target language
        )

        if not ranked_candidates:
            self.logger.warning("No suitable online candidates found after ranking.")
            return True

        # Attempt to download/process the best candidates
        processed_any_online = False  # Track if any online sub was successfully processed
        for score, priority, candidate in ranked_candidates:
            # Apply minimum score threshold
            if score < MIN_SCORE_THRESHOLD:
                self.logger.info(
                    f"Stopping online search: Best remaining candidate score ({score}) below threshold ({MIN_SCORE_THRESHOLD})."
                )
                break

            # Check if RO goal is already met by a higher-ranked candidate in *this run*
            if context.found_final_ro:
                self.logger.debug(
                    f"Skipping candidate (Lang: {candidate.get('language','N/A')}, Score: {score}): Final RO already found in this strategy run."
                )
                continue

            self.logger.info(
                f"Attempting top online candidate: {candidate['source']} (Lang: {candidate.get('language', 'N/A').upper()}, Score: {score}, Prio: {priority})"
            )

            # --- Call Helper to Download/Process/Save ---
            # This returns the final saved path or None
            attempt_path = self._download_process_selected(candidate, context, main_temp_dir)

            if attempt_path and Path(attempt_path).exists():
                selected_lang = candidate.get("language")
                self.logger.info(
                    f"Successfully processed ONLINE {selected_lang.upper()} subtitle to: {attempt_path}"
                )
                processed_any_online = True

                # --- Update context ---
                if selected_lang == "ro":
                    context.found_final_ro = True
                    context.final_ro_sub_path_or_status = attempt_path
                    self.logger.info("Final RO subtitle found via online source.")
                    # Syncing handled later
                    break  # Exit candidate loop on first *RO* success
                elif selected_lang == "en":
                    # Store as candidate EN path, preferred over standard/embedded if found
                    context.candidate_en_path_online = attempt_path
                    self.logger.info(
                        f"Stored online EN path as candidate: {Path(attempt_path).name}"
                    )
                    # Don't break, continue search for potential RO match
            else:
                # Failure logged within _download_process_selected or here
                self.logger.warning(
                    f"Failed to process online candidate {candidate.get('source')} {candidate.get('id')}. Trying next."
                )
                # context.add_error(...) # Error added in helper

        if not processed_any_online:
            self.logger.warning("Failed to successfully process any suitable online candidate.")
        elif not context.found_final_ro and context.candidate_en_path_online:
            self.logger.info(
                "Online search finished. RO not found, but an EN candidate was processed."
            )
        elif not context.found_final_ro:
            self.logger.info(
                "Online search finished. Neither RO nor EN subtitle processed successfully."
            )

        # Cleanup of the main temp dir is handled by the pipeline context manager

        return True  # Strategy completed its run

    def _rank_candidates(
        self,
        candidates: list[dict[str, Any]],
        # media_path unused argument removed
        media_basename: str,
        media_s: str | None,
        media_e: str | None,
        required_language: str,
    ) -> list[tuple[float, int, dict[str, Any]]]:
        """Scores and ranks candidates using subtitle_matcher."""
        if not candidates:
            return []
        media_tokens = subtitle_matcher.tokenize_and_normalize(Path(media_basename).stem)
        scored_results = []
        self.logger.debug(f"Ranking {len(candidates)} online candidates...")

        for candidate in candidates:
            candidate_id_repr = str(candidate.get("id", "N/A"))[:80]  # Truncate long URLs
            try:
                scored_tuple = subtitle_matcher.score_candidate(
                    candidate, media_tokens, media_basename, media_s, media_e, required_language
                )
                if scored_tuple:
                    _, _, _ = scored_tuple  # Unpack but ignore since we append the tuple itself
                    # _score, _priority, _ = scored_tuple  # unpack for potential use or debugging
                    scored_results.append(scored_tuple)
                else:
                    self.logger.debug(
                        f"Candidate {candidate.get('source')} {candidate_id_repr} disqualified during scoring (e.g., episode mismatch)."
                    )
            except Exception:
                # Use context.add_error here? Or let the caller handle it? Let's add error here.
                # context.add_error(self.name, f"Error scoring candidate {candidate.get('source')} {candidate_id_repr}: {e}")
                self.logger.exception(
                    f"Error scoring candidate {candidate.get('source')} {candidate_id_repr}.",
                    exc_info=True,
                )

        if not scored_results:
            return []

        # Sort by Priority (asc, 1 is best), then Score (desc)
        scored_results.sort(key=lambda x: (x[1], -x[0]))
        self.logger.debug(
            f"Ranking complete. Best score: {scored_results[0][0]}, Prio: {scored_results[0][1]}"
        )
        return scored_results

    def _download_process_selected(  # noqa: C901
        self,
        candidate: dict[str, Any],
        context: ProcessingContext,
        main_temp_dir: str,  # Pass the main temp dir for organizing downloads
    ) -> str | None:
        """
        Downloads (OpenSubtitles) or uses existing temp file (Subs.ro),
        processes, and saves the chosen candidate to the standard location.
        Returns the final path if successful, None otherwise.
        Does NOT update context flags.
        """
        source = candidate.get("source")
        identifier = candidate.get("id")  # URL for subsro, file_id for OS
        language = candidate.get("language")
        # score = candidate.get('_score', -1) # If score was added back in _rank_candidates

        final_subtitle_path = None
        extracted_sub_file_source_path = None
        target_save_path = None  # Initialize

        if not source or not identifier or language is None:
            context.add_error(
                self.name,
                f"Cannot process online candidate: Missing source, ID, or language. Data: {candidate}",
            )
            return None

        # Determine target save path based on language
        # base_name_no_ext = os.path.splitext(context.video_info['basename'])[0] # Done in execute now
        if language == "ro":
            target_save_path = context.target_ro_path
        elif language == "en":
            target_save_path = context.target_en_path
        else:
            self.logger.warning(
                f"Attempting to process candidate with unexpected language '{language}'. Cannot determine standard save path."
            )
            # If needed, construct a path like movie.lang.srt, but prefer standard paths
            # base_name_no_ext = os.path.splitext(context.video_info['basename'])[0]
            # target_save_path = file_utils.get_preferred_subtitle_path(base_name_no_ext, language)
            context.add_error(
                self.name, f"Cannot save subtitle for unexpected language '{language}'."
            )
            return None

        if not target_save_path:
            context.add_error(
                self.name,
                f"Could not determine target save path for candidate language '{language}'.",
            )
            return None

        # Ensure target directory exists
        target_dir = Path(target_save_path).parent
        if target_dir:
            target_dir.mkdir(exist_ok=True)

        # --- Main Download/Processing Block ---
        try:
            identifier_repr = str(identifier)[:80]  # Truncate long URLs/IDs for logging
            self.logger.info(
                f"Processing selected candidate: {source} '{identifier_repr}' (Lang: {language}) -> '{Path(target_save_path).name}'"
            )

            # --- Get Source Subtitle Path (Download if needed) ---
            if source == "opensubtitles":
                opensubs = context.di.opensubtitles
                if not opensubs:
                    raise RuntimeError("OpenSubtitles client unavailable.")

                file_id = int(identifier)  # Should be file_id number
                # Create a specific temp dir for this download within the main temp dir
                opensubs_dl_dir = Path(main_temp_dir) / f"opensubs_dl_{file_id}"
                opensubs_dl_dir.mkdir(exist_ok=True)
                # No need to add opensubs_dl_dir to context cleanup, main_temp_dir covers it.

                download_info = opensubs.get_download_info(file_id)
                if not download_info or not download_info.get("link"):
                    raise RuntimeError(
                        f"Failed to get OpenSubtitles download link for file_id {file_id}."
                    )

                content_bytes = opensubs.download_subtitle_content(download_info["link"])
                if not content_bytes:
                    raise RuntimeError(
                        f"Failed to download OpenSubtitles content for file_id {file_id}."
                    )

                # Save raw downloaded bytes temporarily
                dl_filename_hint = download_info.get(
                    "file_name", f"opensubs_download_{file_id}.bin"
                )
                safe_hint = "".join(
                    c for c in dl_filename_hint if c.isalnum() or c in ("._- ")
                ).strip()
                temp_bin_path = opensubs_dl_dir / (
                    safe_hint if safe_hint else f"opensubs_download_{file_id}.bin"
                )
                with temp_bin_path.open("wb") as f:
                    f.write(content_bytes)

                # Convert to UTF-8 SRT for consistent processing
                extracted_sub_file_source_path = str(
                    opensubs_dl_dir
                    / (
                        Path(safe_hint if safe_hint else f"opensubs_download_{file_id}").stem
                        + ".srt"
                    )
                )
                try:
                    content_str = file_utils.read_srt_file(
                        str(temp_bin_path)
                    )  # Reads with detected encoding
                    file_utils.write_srt_file(
                        extracted_sub_file_source_path, content_str
                    )  # Writes as UTF-8 BOM
                    self.logger.debug(
                        f"Decoded and saved OpenSubtitles sub to temp SRT: {extracted_sub_file_source_path}"
                    )
                except Exception as decode_err:
                    raise RuntimeError(
                        f"Failed to decode/save downloaded OpenSubtitles content: {decode_err}"
                    ) from decode_err

            elif source == "subsro":
                extracted_sub_file_source_path = candidate.get("extracted_path")
                if (
                    not extracted_sub_file_source_path
                    or not Path(extracted_sub_file_source_path).exists()
                ):
                    raise ValueError(
                        f"Subs.ro candidate missing or invalid 'extracted_path': {extracted_sub_file_source_path}"
                    )
                self.logger.debug(
                    f"Using pre-extracted Subs.ro file: {extracted_sub_file_source_path}"
                )

            else:
                raise ValueError(f"Unsupported candidate source: {source}")

            # --- Process and Save ---
            if not extracted_sub_file_source_path:
                raise RuntimeError(
                    "No source subtitle file path determined after download/extraction attempt."
                )

            self.logger.info(
                f"Processing subtitle file: {Path(extracted_sub_file_source_path).name}"
            )
            try:
                # Read content using utility (handles encoding detection)
                content = file_utils.read_srt_file(extracted_sub_file_source_path)
                if not content or not content.strip():
                    self.logger.warning(
                        f"Source subtitle file is empty: {extracted_sub_file_source_path}. Skipping processing."
                    )
                    return None  # Cannot process empty file

                # Apply fixes (diacritics for RO, timestamp format for all)
                processed_content = content
                if language == "ro":
                    processed_content = subtitle_parser.fix_diacritics(processed_content)
                processed_content = subtitle_parser.ensure_correct_timestamp_format(
                    processed_content
                )

                # Write to final destination using utility (handles UTF-8 BOM)
                file_utils.write_srt_file(target_save_path, processed_content)

                # Verify write success
                if Path(target_save_path).exists() and Path(target_save_path).stat().st_size > 0:
                    self.logger.info(
                        f"Saved processed subtitle to final destination: {target_save_path}"
                    )
                    final_subtitle_path = target_save_path
                else:
                    raise RuntimeError(
                        f"Failed to write valid processed subtitle file to {target_save_path}"
                    )

            except Exception as proc_err:
                raise RuntimeError(
                    f"Failed to process or save subtitle from {Path(extracted_sub_file_source_path).name}: {proc_err}"
                ) from proc_err

            # Note: Syncing is NOT done here, it's handled by Synchronizer strategy later.

            return final_subtitle_path  # Return the path where it was saved

        except Exception as e:
            context.add_error(
                self.name, f"Failed processing candidate {source} '{identifier_repr}': {e}"
            )
            self.logger.exception(
                f"Failed processing candidate {source} '{identifier_repr}'.", exc_info=True
            )
            # Attempt cleanup of target file if it exists after an error
            if target_save_path and Path(target_save_path).exists():
                try:
                    self.logger.warning(
                        f"Cleaning up potentially incomplete target file due to error: {target_save_path}"
                    )
                    Path(target_save_path).unlink()
                except OSError as rm_err:
                    self.logger.error(
                        f"Error removing incomplete target file {target_save_path}: {rm_err}"
                    )
            return None  # Return None on failure
        # Overall temp dir cleanup is handled by the pipeline context manager
