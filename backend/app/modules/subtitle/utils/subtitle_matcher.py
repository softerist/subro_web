import logging
import os
import re
from pathlib import Path

# Import constants and other utilities safely
try:
    from app.modules.subtitle.core import constants
except ImportError:
    logging.error(
        "Failed to import constants from app.modules.subtitle.core.constants in subtitle_matcher. Critical functionality may fail."
    )
    # Define minimal fallbacks if necessary for testing, but real run will likely fail
    constants = type(
        "obj",
        (object,),
        {
            "priority_criteria": {},
            "category_weights": {},
            "LANGUAGE_CODE_MAPPING_3_TO_2": {"rum": "ro", "ron": "ro", "eng": "en"},
        },
    )()  # Create a dummy object

try:
    # Use relative import if part of the same package structure
    from .subtitle_parser import tokenize_and_normalize
except ImportError:
    # Fallback to absolute if src is in PYTHONPATH
    try:
        from app.modules.subtitle.utils.subtitle_parser import tokenize_and_normalize
    except (ImportError, ModuleNotFoundError):
        logging.critical(
            "Failed to import tokenize_and_normalize from subtitle_parser. Scoring will fail."
        )

        # Define a dummy function to avoid immediate crash, but scoring will be 0
        def tokenize_and_normalize(_text):
            return []


try:
    from app.core.config import settings
except ImportError:
    logging.error(
        "Failed to import settings from app.core.config. Using default values for thresholds."
    )

    # Define a dummy settings object with defaults
    class DummySettings:
        LOCAL_MIN_MATCH_SCORE = 5
        SUBTITLE_MIN_OVERALL_SCORE = 10

    settings = DummySettings()

logger = logging.getLogger(__name__)

# --- Configuration ---
# Fetch settings with defaults
MIN_LOCAL_MATCH_SCORE = getattr(settings, "LOCAL_MIN_MATCH_SCORE", 5)
MIN_OVERALL_MATCH_SCORE = getattr(settings, "SUBTITLE_MIN_OVERALL_SCORE", 10)

# --- Regex Pre-compilation ---
compiled_patterns = {}
try:
    # Check if priority_criteria itself exists and is a dictionary
    if isinstance(constants.priority_criteria, dict):
        for category, criteria_list_or_dict in constants.priority_criteria.items():
            patterns = []
            criteria_list = []
            # Handle both list and dict structures for criteria
            if isinstance(criteria_list_or_dict, list):
                criteria_list = criteria_list_or_dict
            elif isinstance(criteria_list_or_dict, dict):
                # Flatten dict values into a single list for pattern compilation
                criteria_list = [
                    item for sublist in criteria_list_or_dict.values() for item in sublist
                ]
            else:
                logging.warning(
                    f"Unexpected format for priority_criteria category '{category}'. Skipping."
                )
                continue

            for criterion in criteria_list:
                try:
                    # Ensure criterion is string before escaping
                    criterion_str = str(criterion)
                    # Use word boundaries (\b) to match whole words only, case-insensitive
                    # Escape special regex characters in the criterion itself
                    patterns.append(
                        re.compile(r"\b" + re.escape(criterion_str) + r"\b", re.IGNORECASE)
                    )
                except re.error as regex_err:
                    logging.error(
                        f"Failed to compile regex for criterion '{criterion_str}' in category '{category}': {regex_err}"
                    )
                except Exception as e:
                    logging.error(
                        f"Unexpected error compiling regex for criterion '{criterion_str}': {e}"
                    )
            compiled_patterns[category] = patterns
    else:
        logging.error(
            "priority_criteria from constants not loaded correctly or not a dictionary. Weighted scoring may be inaccurate."
        )

except Exception as e:
    logging.error(f"Failed during pre-compilation of regex patterns: {e}", exc_info=True)
    # Allow to continue, scoring might be less effective


# --- Candidate Scoring ---
def score_candidate(candidate, media_tokens, media_basename, media_s, media_e, required_language):  # noqa: C901
    """
    Scores a subtitle candidate dictionary against media file info.
    Handles different sources (OpenSubtitles, Subs.ro) and language priority.

    Args:
        candidate (dict): Dictionary representing the subtitle candidate.
                          Expected keys: 'source', 'id', 'language', 'extracted_path' (for subsro),
                          'release_name', 'file_name', 'attributes' (for opensubs), 'score_bonus'.
        media_tokens (list): Normalized tokens from the media filename.
        media_basename (str): Basename of the media file (for episode check).
        media_s (str or None): Season number of the media file (e.g., '01').
        media_e (str or None): Episode number of the media file (e.g., '01').
        required_language (str): The 2-letter code of the desired language (e.g., 'ro').

    Returns:
        tuple or None: (score, priority, candidate) if scoring is successful and meets criteria,
                       otherwise None.
    """
    source = candidate.get("source")
    language = candidate.get("language")  # Should be 2-letter code
    identifier = candidate.get("id")
    extracted_path = candidate.get("extracted_path")  # Path to the actual SRT/SUB file for Subs.ro
    release_name = candidate.get("release_name", "") or ""  # Primarily for OpenSubtitles
    file_name = (
        candidate.get("file_name", "") or ""
    )  # For OpenSubtitles or derived from extracted_path

    if not source or not identifier or language is None:  # Language is essential for priority
        logging.warning(
            f"Cannot score candidate: Missing 'source', 'id', or 'language'. Candidate: {candidate}"
        )
        return None

    # Determine Language Priority: 1=Required, 2=Unknown/None (shouldn't happen here), 3=Other
    lang_priority_map = {required_language.lower(): 1}
    priority = lang_priority_map.get(language.lower(), 3)  # Default to 3 for any other language

    # --- Episode Matching (Crucial for TV shows) ---
    # Determine the filename to use for the episode check
    name_for_episode_check = None
    if source == "subsro" and extracted_path:
        name_for_episode_check = Path(extracted_path).name
    elif source == "opensubtitles":
        # Prefer file_name from OpenSubtitles API if available, fallback to release
        name_for_episode_check = file_name or release_name
    if not name_for_episode_check and identifier:
        # Fallback to using the ID string itself if no other name available
        name_for_episode_check = str(identifier)

    # If it's a TV episode (media_e is not None) and the subtitle doesn't match, skip it
    # Only perform check if name_for_episode_check is valid
    if (
        media_e
        and name_for_episode_check
        and not is_matching_episode(media_basename, name_for_episode_check)
    ):
        logging.debug(
            f"Skipping candidate {source} '{identifier}' (Lang: {language}, Prio: {priority}): Episode mismatch based on '{name_for_episode_check}'. Media: S{media_s or '?'}E{media_e}"
        )
        return None  # Skip this candidate entirely

    # --- Scoring Logic ---
    score = 0
    subtitle_tokens = []
    name_for_scoring = ""  # The string representation of the subtitle used for token matching

    try:
        if source == "opensubtitles":
            # Use release name first, fallback to filename if release name is empty/generic
            if release_name and len(release_name) > 5:  # Basic check for non-trivial release name
                name_for_scoring = release_name
            else:
                name_for_scoring = file_name

            if not name_for_scoring:  # If both are empty, cannot score
                score = 0
                logging.debug(
                    f"OpenSubtitles candidate {identifier} has no usable name for scoring."
                )
            else:
                subtitle_tokens = tokenize_and_normalize(name_for_scoring)
                if subtitle_tokens:
                    score = calculate_match_score(media_tokens, subtitle_tokens)
                else:
                    score = 0  # No tokens to match

            # Apply OpenSubtitles specific bonuses/penalties
            opensubs_attrs = candidate.get("attributes", {})
            if opensubs_attrs:
                if opensubs_attrs.get("from_trusted"):
                    score += 5
                    logging.debug("  +5 score bonus (OpenSubs Trusted)")
                # Penalties should be applied even if base score is 0
                if opensubs_attrs.get("ai_translated") or opensubs_attrs.get("machine_translated"):
                    score -= 20
                    logging.debug("  -20 score penalty (OpenSubs AI/Machine Translated)")
                if opensubs_attrs.get("hearing_impaired"):
                    score -= 2
                    logging.debug("  -2 score penalty (OpenSubs Hearing Impaired)")
            # Add any generic bonus passed in the candidate dict (e.g., for exact match)
            score += candidate.get("score_bonus", 0)

        if source == "subsro":
            if extracted_path and Path(extracted_path).exists():
                # Score based on the extracted filename
                extracted_filename = Path(extracted_path).name
                sub_base_name_no_ext = Path(extracted_filename).stem
                name_for_scoring = sub_base_name_no_ext  # Start with base name

                # Attempt to remove language code suffix for potentially better scoring
                # This uses the language already determined for the candidate
                if language:
                    pattern_to_remove = r"[._-]" + re.escape(language.lower()) + r"$"
                    # Check if the pattern actually exists at the end before removing
                    if re.search(pattern_to_remove, sub_base_name_no_ext, flags=re.IGNORECASE):
                        temp_name_for_scoring = re.sub(
                            pattern_to_remove, "", sub_base_name_no_ext, flags=re.IGNORECASE
                        ).strip("._- ")
                        # Only use the cleaned name if it's not empty
                        if temp_name_for_scoring:
                            name_for_scoring = temp_name_for_scoring
                            logging.debug(
                                f"  Using language-removed name for Subs.ro scoring: '{name_for_scoring}'"
                            )

                subtitle_tokens = tokenize_and_normalize(name_for_scoring)
                if subtitle_tokens:
                    score = calculate_match_score(media_tokens, subtitle_tokens)
                else:
                    score = 1  # Minimal score if tokens fail but path exists

                logging.debug(
                    f"  Scored Subs.ro candidate using extracted file '{extracted_filename}' -> '{name_for_scoring}'"
                )
            else:
                logging.warning(
                    f"Scoring Subs.ro candidate '{identifier}' without a valid 'extracted_path'. Score set to 1."
                )
                score = 1  # Very low score if path is missing or invalid

        else:
            logging.warning(f"Cannot score candidate: Unknown source '{source}'.")
            return None  # Unknown source type

    except Exception as scoring_err:
        logger.error(
            f"Error during detailed scoring of candidate {source} '{identifier}': {scoring_err}",
            exc_info=True,
        )
        score = 0  # Reset score to 0 on error

    # Final score adjustment (ensure score is not excessively negative)
    score = max(-50, score)  # Cap minimum score to avoid extreme negatives

    # Add candidate dict to the result tuple for later use
    result_tuple = (score, priority, candidate)

    logging.debug(
        f"Scored candidate {source} '{identifier}' (Lang: {language}, Prio: {priority}, Name: '{name_for_scoring[:60]}...'): Final Score={score}"
    )

    # Note: Minimum overall score check is usually applied *after* ranking all candidates.
    # We return the scored tuple here. The caller (OnlineFetcher) will apply the threshold.
    return result_tuple


# --- Filename Parsing ---


def extract_season_episode(filename):
    """
    Extracts season and episode numbers (as strings, zero-padded) from a filename.
    Returns (season, episode) or (None, None).
    Handles S01E02, 1x02, S1E2, 1x2, E01, etc., prioritizing patterns with separators.
    """
    if not filename:
        return None, None

    # Clean filename: remove extension, replace separators
    base_name = Path(filename).stem
    # Replace common separators with a space for easier regex
    clean_name = re.sub(r"[._-]+", " ", base_name)

    # Patterns ranked by specificity (Season+Episode first)
    patterns = [
        # S01 E02 / S01.E02 / S01-E02 / S01E02 (Season mandatory)
        re.compile(r"\bS(\d{1,3})\s?E(\d{1,3})\b", re.IGNORECASE),
        # 1x02 / 1 x 02 (Season mandatory)
        re.compile(r"\b(\d{1,3})\s?x\s?(\d{1,3})\b", re.IGNORECASE),
        # Season 1 Episode 2 (Season optional if already found by other patterns)
        re.compile(r"\b(?:Season\s)?(\d{1,3})\s(?:Episode|Ep)\s(\d{1,3})\b", re.IGNORECASE),
    ]
    # Episode-only patterns (lower priority)
    ep_only_patterns = [
        # E01 / Ep 01 / Episode 01
        re.compile(r"\bE[Pp]?(?:isode)?\s?(\d{1,3})\b", re.IGNORECASE),
    ]

    s_match, e_match = None, None

    # Try Season+Episode patterns first
    for pattern in patterns:
        match = pattern.search(clean_name)
        if match:
            s_potential = match.group(1)
            e_potential = match.group(2)
            # Basic validation
            if s_potential and e_potential and len(s_potential) <= 3 and len(e_potential) <= 3:
                s_match = s_potential.zfill(2)
                e_match = e_potential.zfill(2)
                logging.debug(
                    f"Extracted S{s_match}E{e_match} from '{filename}' using pattern {pattern.pattern}"
                )
                return s_match, e_match

    # If no Season+Episode match, try Episode-only patterns
    if not e_match:  # Check if episode wasn't found yet
        for pattern in ep_only_patterns:
            match = pattern.search(clean_name)
            if match:
                e_potential = match.group(1)
                if e_potential and len(e_potential) <= 3:
                    # Found episode only, season remains None
                    e_match = e_potential.zfill(2)
                    logging.debug(
                        f"Extracted E{e_match} (Season unknown) from '{filename}' using pattern {pattern.pattern}"
                    )
                    return None, e_match  # Return None for season

    # If nothing matched
    logging.debug(f"Could not extract season/episode from '{filename}'")
    return None, None


def is_matching_episode(media_filename, subtitle_filename):
    """
    Checks if a subtitle filename corresponds to the same episode as a media filename.
    Returns True if episodes match (and seasons match if both are present), False otherwise.
    """
    if not media_filename or not subtitle_filename:
        return False

    media_s, media_e = extract_season_episode(media_filename)
    sub_s, sub_e = extract_season_episode(subtitle_filename)

    log_msg_prefix = f"Episode Matching: Media='{media_filename}' (S{media_s or '??'}E{media_e or '??'}) vs Subtitle='{subtitle_filename}' (S{sub_s or '??'}E{sub_e or '??'}) ->"

    # --- Matching Logic ---
    # 1. Media MUST have an episode number identified.
    if not media_e:
        logging.debug(f"{log_msg_prefix} Cannot match: Media episode unknown.")
        return False

    # 2. Subtitle MUST have an episode number identified.
    if not sub_e:
        logging.debug(f"{log_msg_prefix} Cannot match: Subtitle episode unknown.")
        return False

    # 3. Episode numbers MUST match.
    if media_e != sub_e:
        logging.debug(f"{log_msg_prefix} No Match: Episode numbers differ ({media_e} != {sub_e}).")
        return False

    # 4. If BOTH filenames provided a season number, they MUST match.
    #    If one provides a season and the other doesn't, we consider it a potential match
    #    (e.g., S01E01 vs E01 might be okay, but S01E01 vs S02E01 is not).
    if media_s and sub_s and media_s != sub_s:
        logging.debug(f"{log_msg_prefix} No Match: Season numbers differ ({media_s} != {sub_s}).")
        return False

    # If checks pass: Episodes match, and seasons (if both known) match.
    logging.debug(f"{log_msg_prefix} MATCH")
    return True


def get_subtitle_language_code(filename):
    """
    Extracts a 2-letter language code from the filename (e.g., .en.srt, _ro.srt).
    Normalizes common 3-letter codes (eng->en, rum->ro) using constant mapping.
    Returns the 2-letter code (lower-case) or None if not detected reliably.
    """
    if not filename:
        return None

    filename_base = Path(filename).name
    base, ext = Path(filename_base).stem, Path(filename_base).suffix
    # Allow common subtitle extensions
    if ext.lower() not in [".srt", ".sub", ".ass", ".vtt"]:
        return None

    # Regex: Look for common separators (dot, underscore, hyphen)
    # followed by 2 or 3 letters, anchored to the end of the base name.
    match = re.search(r"[._-]([a-zA-Z]{2,3})$", base, re.IGNORECASE)

    if match:
        lang_code_raw = match.group(1).lower()
        # Check 3-letter mapping first
        lang_code_2 = constants.LANGUAGE_CODE_MAPPING_3_TO_2.get(lang_code_raw)

        if lang_code_2:  # Successfully mapped 3->2
            logging.debug(
                f"Extracted and mapped language code '{lang_code_2}' from '{filename_base}'"
            )
            return lang_code_2
        elif len(lang_code_raw) == 2:  # Was already 2 letters
            # Optional: Validate against a known list of 2-letter codes?
            # For now, assume any 2 letters might be valid.
            logging.debug(
                f"Extracted 2-letter language code '{lang_code_raw}' from '{filename_base}'"
            )
            return lang_code_raw
        else:  # Was 3 letters but not in mapping
            logging.debug(
                f"Extracted 3-letter code '{lang_code_raw}' from '{filename_base}', but no 2-letter mapping found."
            )
            return None  # Treat unmappable 3-letter codes as unknown

    # logging.debug(f"No standard language code pattern detected in '{filename_base}'")
    return None


# --- Scoring Logic ---


def calculate_match_score(media_tokens, subtitle_tokens):  # noqa: C901
    """
    Calculates a match score based on shared tokens and weighted keywords.

    Args:
        media_tokens (list): List of normalized tokens from the media filename.
        subtitle_tokens (list): List of normalized tokens from the subtitle filename/release name.

    Returns:
        int: A score indicating the match quality. Higher is better. Can be negative.
    """
    if not media_tokens or not subtitle_tokens:
        return 0

    try:
        score = 0
        media_set = set(media_tokens)
        subtitle_set = set(subtitle_tokens)
        common_tokens = media_set.intersection(subtitle_set)

        # Base score for common tokens (e.g., 5 points per common token)
        base_common_score = len(common_tokens) * 5
        score += base_common_score

        # Bonus/Penalty points for weighted category matches found in *subtitle* tokens
        # Only apply bonus if the token is also present in the media tokens (relevant match)
        weighted_bonus = 0
        matched_categories = set()
        processed_tokens_for_bonus = set()  # Avoid double counting bonus for same token

        # Ensure category_weights exists and is a dict
        if not isinstance(constants.category_weights, dict):
            logging.error("Category weights not loaded correctly. Weighted scoring disabled.")
            return score  # Return only base score

        for token in subtitle_tokens:
            token_processed = False  # Flag if this token gave a bonus this iteration
            # Check if this token is relevant (present in media too) and hasn't received a bonus yet
            if token in common_tokens and token not in processed_tokens_for_bonus:
                for category, patterns in compiled_patterns.items():
                    category_weight = constants.category_weights.get(category)
                    if category_weight is None:
                        continue  # Skip if no weight defined

                    # Skip if this token already got a bonus for this category? No, allow multiple matches per token?
                    # Let's allow a token to match multiple patterns in *different* categories.

                    for pattern in patterns:
                        # Use fullmatch or search? Search is more lenient. Let's use search.
                        if pattern.search(token):
                            # Apply weight only if the token is common
                            weighted_bonus += category_weight
                            matched_categories.add(category)
                            # logging.debug(f"  Token '{token}' matched category '{category}' (Weight: {category_weight})")
                            token_processed = True
                            # Should a token contribute to multiple categories? Yes, potentially.
                            # Break from pattern loop for this category once matched? Optional.
                            # break # Break inner pattern loop if one match is enough per category per token
                # Mark token as processed for bonus if it matched *any* category
                if token_processed:
                    processed_tokens_for_bonus.add(token)

        score += weighted_bonus
        # Log breakdown only if there was a weighted bonus applied
        if weighted_bonus != 0:
            logging.debug(
                f"  Score Breakdown: BaseCommon={base_common_score}, WeightedBonus={weighted_bonus} (Categories: {matched_categories or 'None'}) -> Total={score}"
            )
        # else: log only base score? Too verbose maybe.

        return score
    except Exception as e:
        logging.error(f"Error during score calculation: {e}", exc_info=True)
        return 0  # Return 0 on error


# --- Finding Best Local Match (Kept for potential utility use) ---


def find_best_matching_subtitle_local(media_file_path, subtitle_files_dir, required_language="ro"):  # noqa: C901
    """
    Finds the best matching local subtitle file for a given media file.
    Searches recursively in subtitle_files_dir. Prioritizes required language.

    Args:
        media_file_path (str): Full path to the media file.
        subtitle_files_dir (str): Directory containing candidate subtitle files.
        required_language (str): The preferred 2-letter language code.

    Returns:
        tuple: (best_match_path, best_score) or (None, -1).
    """
    best_match_path = None
    best_score = -1

    if not Path(media_file_path).exists():
        logging.error(f"Cannot find local match: Media file not found at {media_file_path}")
        return None, -1
    if not Path(subtitle_files_dir).is_dir():
        logging.warning(
            f"Cannot find local match: Subtitle directory not found or not a directory: {subtitle_files_dir}"
        )
        return None, -1

    media_basename = Path(media_file_path).name
    media_base_name_no_ext = Path(media_basename).stem
    media_tokens = tokenize_and_normalize(media_base_name_no_ext)
    media_s, media_e = extract_season_episode(media_basename)

    req_lang_lower = required_language.lower()
    logging.info(
        f"Finding best local match for media: '{media_basename}' (Req Lang: {req_lang_lower}) in dir: {subtitle_files_dir}"
    )
    logging.debug(f"Media tokens: {media_tokens} | Episode: S{media_s or '??'}E{media_e or '??'}")

    # Gather Candidate Files
    candidate_paths = []
    try:
        for root, _, files in os.walk(subtitle_files_dir):
            for file in files:
                if file.lower().endswith((".srt", ".sub", ".ass")) and not file.lower().endswith(
                    (".bak", ".syncbak")
                ):
                    full_path = str(Path(root) / file)
                    if os.path.normpath(full_path) != os.path.normpath(media_file_path):
                        candidate_paths.append(full_path)
    except Exception as e:
        logging.error(f"Error walking subtitle directory {subtitle_files_dir}: {e}")
        return None, -1

    if not candidate_paths:
        logging.info(
            f"No local subtitle candidates (.srt, .sub, .ass) found in: {subtitle_files_dir}"
        )
        return None, -1
    logging.debug(f"Found {len(candidate_paths)} local candidate subtitle files.")

    # Score and Rank Candidates
    scored_matches = []  # List of tuples: (score, language_priority, path)
    lang_priority_map = {req_lang_lower: 1, None: 2}  # Prio map: 1=req, 2=unknown, 3=other

    for sub_path in candidate_paths:
        sub_filename = Path(sub_path).name
        language_code = get_subtitle_language_code(sub_filename)  # Detect language from filename
        priority = lang_priority_map.get(language_code, 3)  # Assign priority

        # Skip if episode mismatch for TV shows
        if media_e and not is_matching_episode(media_basename, sub_filename):
            logging.debug(f"Skipping local '{sub_filename}': Episode mismatch.")
            continue

        # Prepare subtitle name for tokenization (remove lang code and extension)
        sub_base_name_no_ext = Path(sub_filename).stem
        sub_name_for_scoring = sub_base_name_no_ext
        if language_code:
            pattern_to_remove = r"[._-]" + re.escape(language_code) + r"$"
            if re.search(pattern_to_remove, sub_base_name_no_ext, flags=re.IGNORECASE):
                cleaned_name = re.sub(
                    pattern_to_remove, "", sub_base_name_no_ext, flags=re.IGNORECASE
                ).strip("._- ")
                if cleaned_name:
                    sub_name_for_scoring = cleaned_name

        sub_tokens = tokenize_and_normalize(sub_name_for_scoring)
        if not sub_tokens:
            logging.debug(
                f"Skipping local '{sub_filename}': Could not generate tokens from '{sub_name_for_scoring}'."
            )
            continue

        score = calculate_match_score(media_tokens, sub_tokens)
        logging.debug(
            f"Scored local '{sub_filename}' (Lang: {language_code or 'Unknown'}, Prio: {priority}): Score={score}"
        )

        # Add to list if score is potentially valid
        if score >= 0:  # Allow score 0, apply threshold after sorting
            scored_matches.append((score, priority, sub_path))

    if not scored_matches:
        logging.info(
            f"No suitable local subtitle found for '{media_basename}' after filtering and scoring."
        )
        return None, -1

    # Sort: PRIORITY first (ascending, 1 is best), then SCORE second (descending)
    scored_matches.sort(key=lambda x: (x[1], -x[0]))

    best_score, best_prio, best_match_path = scored_matches[0]
    best_match_filename = Path(best_match_path).name

    # Apply minimum local score threshold
    if best_score < MIN_LOCAL_MATCH_SCORE:
        logging.info(
            f"Best local match score ({best_score}) for '{best_match_filename}' is below threshold ({MIN_LOCAL_MATCH_SCORE}). Ignoring match."
        )
        return None, -1

    logging.info(
        f"Best local match for '{media_basename}': '{best_match_filename}' (Score: {best_score}, Prio: {best_prio})"
    )
    return best_match_path, best_score


# --- Explicit Exports ---
__all__ = [
    "calculate_match_score",
    "extract_season_episode",
    "find_best_matching_subtitle_local",
    "get_subtitle_language_code",
    "is_matching_episode",
    "score_candidate",
    "tokenize_and_normalize",
]
