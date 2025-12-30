import importlib.util
import logging
import pkgutil
import re
from collections import OrderedDict, defaultdict
from pathlib import Path


def _patch_pkgutil_find_loader() -> None:
    """Shim deprecated pkgutil.find_loader for imdbpy on newer Python versions."""
    if not hasattr(pkgutil, "find_loader"):
        return

    def _find_loader(name: str):
        return importlib.util.find_spec(name)

    pkgutil.find_loader = _find_loader  # type: ignore[assignment]


_patch_pkgutil_find_loader()

import imdb
from rapidfuzz import fuzz

from app.core.config import settings
from app.modules.subtitle.core.constants import (  # Import specific items to avoid long prefixes
    FUZZY_MATCH_THRESHOLD,
    TYPE_MAP,
)
from app.modules.subtitle.utils.network_utils import create_session_with_retries, make_request

logger = logging.getLogger(__name__)

# Initialize IMDbPY instance safely
try:
    ia = imdb.IMDb()
except Exception as e:
    logging.error(f"Failed to initialize IMDbPY client: {e}", exc_info=True)
    ia = None

# Create a shared requests session for OMDb/TMDb APIs
network_session = create_session_with_retries(
    max_retries=getattr(settings, "NETWORK_MAX_RETRIES", 3),
    backoff_factor=getattr(settings, "NETWORK_BACKOFF_FACTOR", 1),
)


# --- Helper Function ---
def _fuzzy_match(title, candidate, threshold=FUZZY_MATCH_THRESHOLD):
    """Internal helper for fuzzy string matching."""
    if not title or not candidate:
        return False
    # Ensure comparison is case-insensitive
    similarity = fuzz.ratio(str(title).lower(), str(candidate).lower())
    return similarity >= threshold


# Helper for dynamic key retrieval
def _get_dynamic_api_key(db_field, env_var_name=None):
    """
    Fetches API key synchronously from DB, falling back to Environment/Settings.
    """
    # 1. Try Database
    try:
        from sqlalchemy import select

        from app.core.security import decrypt_value
        from app.db.models.app_settings import AppSettings
        from app.db.session import SyncSessionLocal

        if SyncSessionLocal:
            with SyncSessionLocal() as session:
                settings_row = session.scalar(select(AppSettings).where(AppSettings.id == 1))
                if settings_row:
                    val = getattr(settings_row, db_field, None)
                    if val is not None:
                        if val == "":
                            return None  # Explicitly disabled in DB
                        return decrypt_value(val)
    except Exception as e:
        # Avoid spamming logs for every key check, debug only
        logging.debug(f"Failed to fetch {db_field} from DB: {e}")

    # 2. Fallback to Environment (Module-level settings object)
    if env_var_name:
        return getattr(settings, env_var_name, None)
    return None


# --- OMDb Functions ---
def _search_omdb_api(params):
    """Internal helper to query the OMDb API."""
    api_key = _get_dynamic_api_key("omdb_api_key", "OMDB_API_KEY")

    if not api_key:
        # Log only once or less frequently? For now, log per call.
        logging.error("OMDb API key is not configured.")
        return None

    base_url = "http://www.omdbapi.com/"
    params["apikey"] = api_key
    params["r"] = "json"  # Ensure response is JSON

    response = make_request(network_session, "GET", base_url, params=params)

    if response is not None:
        try:
            # Handle non-200 status codes (make_request returns response even on 4xx/5xx if raise_for_status=True)
            if response.status_code == 401:
                logging.warning("OMDb API: Unauthorized (Invalid API Key or Daily Limit reached).")
                return None
            if response.status_code == 429:
                logging.warning("OMDb API Error: Rate limited.")
                return None

            data = response.json()
            if data.get("Response") == "True":
                return data
            else:
                error_msg = data.get("Error", "Unknown error")
                if "not found" in error_msg.lower():
                    logging.debug(f"OMDb API Info: {error_msg} for params: {params}")
                elif "invalid api key" in error_msg.lower() or "limit reached" in error_msg.lower():
                    logging.warning(f"OMDb API: {error_msg}")
                else:
                    logging.warning(f"OMDb API Error: {error_msg} for params: {params}")
                return None
        except (ValueError, Exception) as e:
            logging.error(
                f"Failed to process OMDb response for params: {params}. Error: {e}. Status: {response.status_code}"
            )
            return None
    # make_request handles logging for network errors (None return)
    return None


def search_omdb_by_title(title, year=None, content_type=None):
    """Searches OMDb by title (uses 't=' parameter for specific match)."""
    params = {"t": title}
    if year:
        params["y"] = year
    if content_type:
        type_map = {"movie": "movie", "series": "series", "tvshow": "series", "episode": "episode"}
        omdb_type = type_map.get(str(content_type).lower())
        if omdb_type:
            params["type"] = omdb_type
    logging.debug(f"Searching OMDb by title with params: {params}")
    return _search_omdb_api(params)


def search_omdb_by_query(query, year=None, content_type=None):
    """Searches OMDb by query (uses 's=' parameter for broader search)."""
    params = {"s": query}
    if year:
        params["y"] = year
    if content_type:
        type_map = {"movie": "movie", "series": "series", "tvshow": "series", "episode": "episode"}
        omdb_type = type_map.get(str(content_type).lower())
        if omdb_type:
            params["type"] = omdb_type
    logging.debug(f"Searching OMDb by query with params: {params}")
    return _search_omdb_api(params)


# --- TMDb Functions ---
def _search_tmdb_api(endpoint, query_params):
    """Internal helper to query the TMDb API."""
    api_key = _get_dynamic_api_key("tmdb_api_key", "TMDB_API_KEY")

    if not api_key:
        logging.error("TMDb API key is not configured.")
        return None

    base_url = f"https://api.themoviedb.org/3/{endpoint}"
    query_params["api_key"] = api_key

    response = make_request(network_session, "GET", base_url, params=query_params)

    if response is not None:
        try:
            if response.status_code == 401:
                logging.error("TMDb API Error: Unauthorized (Invalid API Key).")
                return None
            if response.status_code == 429:
                logging.warning("TMDb API Error: Rate limited.")
                return None

            return response.json()
        except (ValueError, Exception) as e:
            logging.error(
                f"Failed to process TMDb response for endpoint {endpoint}. Error: {e}. Status: {response.status_code}"
            )
            return None
    # make_request handles logging
    return None


def search_tmdb_movie(title, year=None):
    """Searches TMDb for a movie and returns the best match's IMDb ID."""
    search_params = {"query": title}
    if year:
        search_params["year"] = year

    logging.debug(f"Searching TMDb movie with params: {search_params}")
    search_data = _search_tmdb_api("search/movie", search_params)

    if search_data and search_data.get("results"):
        best_match = None
        highest_score = 0
        for result in search_data["results"]:
            result_title = str(result.get("title", ""))
            score = fuzz.ratio(str(title).lower(), result_title.lower())

            result_year_str = str(result.get("release_date", "")).split("-")[0]
            year_matches = not year or not result_year_str or str(year) == result_year_str

            if score > highest_score and score >= FUZZY_MATCH_THRESHOLD and year_matches:
                highest_score = score
                best_match = result

        if best_match:
            movie_id = best_match["id"]
            logging.debug(
                f"Found TMDB movie match: {best_match.get('title')} (ID: {movie_id}), score: {highest_score}"
            )
            details_data = _search_tmdb_api(
                f"movie/{movie_id}", {"append_to_response": "external_ids"}
            )
            if details_data:
                imdb_id = details_data.get("external_ids", {}).get("imdb_id")
                if imdb_id and imdb_id.startswith("tt"):
                    logging.debug(f"Retrieved IMDb ID from TMDB: {imdb_id}")
                    return imdb_id, "movie"
                else:
                    logging.debug(
                        f"TMDb details found for {movie_id}, but no valid IMDb ID associated."
                    )
            else:
                logging.warning(
                    f"Could not fetch TMDb details/external_ids for movie ID {movie_id}"
                )
    else:
        logging.debug(f"No TMDb movie results for title: {title}, year: {year}")

    return None, None


def search_tmdb_tv(title, year=None):
    """Searches TMDb for a TV show and returns the best match's IMDb ID."""
    search_params = {"query": title}
    # Use 'first_air_date_year' for TV shows as per TMDb API docs
    if year:
        search_params["first_air_date_year"] = year

    logging.debug(f"Searching TMDb TV show with params: {search_params}")
    search_data = _search_tmdb_api("search/tv", search_params)

    if search_data and search_data.get("results"):
        best_match = None
        highest_score = 0
        for result in search_data["results"]:
            result_name = str(result.get("name", ""))
            score = fuzz.ratio(str(title).lower(), result_name.lower())

            result_year_str = str(result.get("first_air_date", "")).split("-")[0]
            year_matches = not year or not result_year_str or str(year) == result_year_str

            if score > highest_score and score >= FUZZY_MATCH_THRESHOLD and year_matches:
                highest_score = score
                best_match = result

        if best_match:
            tv_id = best_match["id"]
            logging.debug(
                f"Found TMDB TV match: {best_match.get('name')} (ID: {tv_id}), score: {highest_score}"
            )
            details_data = _search_tmdb_api(f"tv/{tv_id}", {"append_to_response": "external_ids"})
            if details_data:
                imdb_id = details_data.get("external_ids", {}).get("imdb_id")
                if imdb_id and imdb_id.startswith("tt"):
                    logging.debug(f"Retrieved IMDb ID from TMDb: {imdb_id}")
                    return imdb_id, "series"
                else:
                    logging.debug(
                        f"TMDb details found for TV ID {tv_id}, but no valid IMDb ID associated."
                    )
            else:
                logging.warning(f"Could not fetch TMDb details/external_ids for TV ID {tv_id}")
    else:
        logging.debug(f"No TMDb TV results for title: {title}, year: {year}")

    return None, None


# --- IMDbPY Functions ---
def search_imdbpy(title, year=None):
    logging.getLogger("imdbpy").setLevel(logging.INFO)
    """Searches using the IMDbPY library."""
    if ia is None:
        logging.error("IMDbPY client not initialized. Cannot search.")
        return None, None
    try:
        logging.debug(f"Searching IMDbPY for title: {title}, year: {year}")
        results = ia.search_movie(title)
        if not results:
            logging.debug(f"IMDbPY found no results for: {title}")
            return None, None

        best_match = None
        highest_score = 0
        for result in results:
            result_title = result.get("title") or result.get("long imdb title")
            if not result_title:
                continue

            # Calculate fuzzy match score
            score = fuzz.ratio(str(title).lower(), str(result_title).lower())
            result_year_val = result.get("year")
            year_matches = not year or not result_year_val or str(year) == str(result_year_val)

            # Validate the kind using the global TYPE_MAP rather than a hardcoded list
            kind = result.get("kind")
            if (
                kind
                and kind.lower() in TYPE_MAP
                and year_matches
                and score >= FUZZY_MATCH_THRESHOLD
            ):
                # TYPE_MAP is now imported directly
                if score > highest_score:
                    highest_score = score
                    best_match = result

        if best_match:
            imdb_id = f"tt{best_match.movieID}"
            kind = best_match.get("kind", "").lower()
            content_type = TYPE_MAP.get(kind)
            logging.debug(
                f"IMDbPY found best match: {best_match.get('title')} ({imdb_id}), kind: {kind}, mapped type: {content_type}, score: {highest_score}"
            )
            return imdb_id, content_type
        else:
            logging.debug(f"IMDbPY found results, but no match above threshold for: {title}")
            return None, None

    except Exception as e:
        logging.error(f"Error searching IMDbPY for '{title}': {e}", exc_info=True)
        return None, None


# --- Helper for Generating Search Candidates ---
def _generate_search_candidates(original_title, original_year):
    """
    Generates a list of (title, year) tuples to try for searching,
    prioritizing original, then cleaned versions.
    """
    candidates = OrderedDict()  # Use OrderedDict to keep insertion order

    # 1. Original Title and Year
    if original_title:
        candidates[(original_title, original_year)] = True

    # 2. Cleaned Title (Remove trailing (YYYY)) - Try with original year AND None
    cleaned_title = None
    if original_title:
        # Regex to find potential (YYYY) at the end, possibly surrounded by spaces/dots/underscores
        match = re.search(r"^(.*?)[._\s\(]+(\d{4})[._\s\)]*$", original_title)
        if match:
            potential_title = match.group(1).strip("._ ")
            potential_year_in_title = match.group(2)
            # Only clean if the year in title looks like the original year OR if original year was None
            if potential_title and (
                not original_year or potential_year_in_title == str(original_year)
            ):
                cleaned_title = potential_title
                logging.debug(f"Generated cleaned title '{cleaned_title}' from '{original_title}'")
                # Add cleaned title with original year (if any)
                if original_year:
                    candidates[(cleaned_title, original_year)] = True
                # Add cleaned title with no year specified
                candidates[(cleaned_title, None)] = True

    # 3. Original Title without Year (if year was provided)
    # Useful if year extraction was wrong or title doesn't need year.
    # Do this only if the cleaned title variation wasn't already the same as original title.
    if (
        original_title
        and original_year
        and (cleaned_title is None or cleaned_title != original_title)
    ):
        candidates[(original_title, None)] = True

    # Convert OrderedDict keys back to a list
    candidate_list = list(candidates.keys())
    logging.debug(
        f"Generated search candidates for ('{original_title}', {original_year}): {candidate_list}"
    )
    return candidate_list


# --- Consolidated ID Retrieval (Modified) ---
def get_imdb_id(title, year=None, content_type=None):  # noqa: C901
    """
    Attempts to find the most reliable IMDb ID using OMDb, TMDb, and IMDbPY.
    Tries variations of the title (removing year suffix) if initial searches fail.

    Args:
        title (str): The title of the movie or TV show.
        year (str, optional): The release year. Defaults to None.
        content_type (str, optional): Preferred type ('movie' or 'series'). Defaults to None.

    Returns:
        tuple: (imdb_id, found_type, errors)
    """
    initial_title = title  # Store original for logging
    initial_year = year
    logging.info(
        f"Attempting IMDb ID lookup for: Title='{initial_title}', Year={initial_year}, TypeHint={content_type}"
    )

    errors = []
    results_by_candidate = defaultdict(
        dict
    )  # Store results keyed by candidate: {('Title', 'Year'): {'omdb_title': (id, type), ...}, ...}
    source_log_by_candidate = defaultdict(
        lambda: defaultdict(list)
    )  # {(title, year): {id: [sources]}}

    # --- Generate Candidate Search Pairs ---
    search_candidates = _generate_search_candidates(initial_title, initial_year)

    # --- Iterate Through Candidates and Sources ---
    processed_sources_for_candidate = defaultdict(
        set
    )  # Track which sources ran for which candidate

    for title_candidate, year_candidate in search_candidates:
        candidate_key = (title_candidate, year_candidate)
        # Skip if candidate title is empty after cleaning
        if not title_candidate:
            logging.debug(f"Skipping empty title candidate derived from '{initial_title}'.")
            continue

        logging.debug(
            f"--- Searching with Candidate: Title='{title_candidate}', Year={year_candidate} ---"
        )

        # Helper to add result for the current candidate
        def add_result(source, data_id, data_type, candidate_key=candidate_key):
            nonlocal results_by_candidate, source_log_by_candidate
            processed_sources_for_candidate[candidate_key].add(source)  # Mark source as run
            if data_id and data_id.startswith("tt"):
                # Basic type consistency check (can be refined)
                type_map = {
                    "movie": "movie",
                    "series": "series",
                    "tv series": "series",
                    "tv movie": "movie",
                    "video movie": "movie",
                    "tv special": "series",
                    "episode": "series",
                }  # Map OMDb types too
                consistent_type = type_map.get(data_type.lower()) if data_type else None
                results_by_candidate[candidate_key][source] = (data_id, consistent_type)
                source_log_by_candidate[candidate_key][data_id].append(source)
                logging.debug(
                    f"-> Candidate {candidate_key} - Source '{source}' found: ID={data_id}, Type={consistent_type} (Original: {data_type})"
                )
            else:
                logging.debug(
                    f"-> Candidate {candidate_key} - Source '{source}': No valid IMDb ID found."
                )

        # --- Run Searches for Current Candidate ---

        # 1. OMDb Search by Title (Exact)
        source = "omdb_title"
        if source not in processed_sources_for_candidate[candidate_key]:
            omdb_title_data = search_omdb_by_title(title_candidate, year_candidate, content_type)
            add_result(
                source,
                omdb_title_data.get("imdbID") if omdb_title_data else None,
                omdb_title_data.get("Type") if omdb_title_data else None,
            )
            if not omdb_title_data:
                errors.append(f"OMDb(t) '{title_candidate}'({year_candidate or 'Any'}): Failed")

        # 2. TMDb Search
        source_m = "tmdb_movie"
        source_tv = "tmdb_tv"
        tmdb_id = None
        source_tv = "tmdb_tv"
        tmdb_id = None
        # tmdb_type removed (unused)
        run_tmdb_movie = (
            content_type == "movie" or not content_type
        ) and source_m not in processed_sources_for_candidate[candidate_key]
        run_tmdb_tv = (
            content_type == "series" or not content_type
        ) and source_tv not in processed_sources_for_candidate[candidate_key]

        if run_tmdb_movie:
            tmdb_id_m, tmdb_type_m = search_tmdb_movie(title_candidate, year_candidate)
            add_result(source_m, tmdb_id_m, tmdb_type_m)
            if tmdb_id_m:
                tmdb_id, _ = tmdb_id_m, tmdb_type_m

        if not tmdb_id and run_tmdb_tv:
            tmdb_id_tv, tmdb_type_tv = search_tmdb_tv(title_candidate, year_candidate)
            add_result(source_tv, tmdb_id_tv, tmdb_type_tv)
            if tmdb_id_tv:
                tmdb_id, _ = tmdb_id_tv, tmdb_type_tv

        if not tmdb_id and (run_tmdb_movie or run_tmdb_tv):
            errors.append(f"TMDb '{title_candidate}'({year_candidate or 'Any'}): Failed")

        # 3. OMDb Search by Query (Broader)
        source = "omdb_query"
        if source not in processed_sources_for_candidate[candidate_key]:
            omdb_query_data = search_omdb_by_query(title_candidate, year_candidate, content_type)
            best_omdb_query_match = None
            if omdb_query_data and "Search" in omdb_query_data:
                highest_score = 0
                for result in omdb_query_data["Search"]:
                    result_title = str(result.get("Title", ""))
                    score = fuzz.ratio(str(title_candidate).lower(), result_title.lower())
                    type_compatible = True
                    result_type_omdb = result.get("Type")
                    if content_type and result_type_omdb:
                        if (
                            content_type == "movie"
                            and result_type_omdb not in ["movie", "tv movie", "video movie"]
                        ) or (
                            content_type == "series"
                            and result_type_omdb
                            not in ["series", "tv series", "tv mini series", "tv special"]
                        ):  # Adjusted type check
                            type_compatible = False
                    year_matches = not year_candidate or str(year_candidate) == result.get("Year")

                    if (
                        score > highest_score
                        and score >= FUZZY_MATCH_THRESHOLD
                        and type_compatible
                        and year_matches
                    ):
                        highest_score = score
                        best_omdb_query_match = result
                if best_omdb_query_match:
                    add_result(
                        source,
                        best_omdb_query_match.get("imdbID"),
                        best_omdb_query_match.get("Type"),
                    )
                else:
                    errors.append(
                        f"OMDb(q) '{title_candidate}'({year_candidate or 'Any'}): No good match"
                    )
            elif source not in results_by_candidate.get(candidate_key, {}):
                errors.append(f"OMDb(q) '{title_candidate}'({year_candidate or 'Any'}): No results")
            processed_sources_for_candidate[candidate_key].add(source)  # Mark as processed

        # 4. IMDbPY Search (Slowest)
        source = "imdbpy"
        if source not in processed_sources_for_candidate[candidate_key]:
            imdbpy_id, imdbpy_type = search_imdbpy(title_candidate, year_candidate)
            add_result(source, imdbpy_id, imdbpy_type)
            if not imdbpy_id:
                errors.append(f"IMDbPY '{title_candidate}'({year_candidate or 'Any'}): Failed")

        # --- Check if we found a high-confidence result from this candidate ---
        # Let's disable early stopping for now to ensure all candidates are checked for maximum consensus data
        # current_results = results_by_candidate[candidate_key]
        # if len(current_results) >= 2 and len(set(r[0] for r in current_results.values() if r and r[0])) == 1:
        #     logging.debug(f"High-confidence result found for candidate {candidate_key}. Continuing to check other candidates for confirmation.")
        #     # break # Uncomment to stop early

    # --- Decision Logic (Operate on combined results from all candidates) ---
    all_results = {}  # Flatten results: {source_candidate_key_tuple: (id, type)}
    all_source_logs = defaultdict(list)  # {id: [source_candidate_key_tuple]}

    for candidate_key, sources_results in results_by_candidate.items():
        for source, (r_id, r_type) in sources_results.items():
            if r_id and r_id.startswith("tt"):
                # Use a tuple as the key combining source and candidate info
                result_key = (source, candidate_key)
                all_results[result_key] = (r_id, r_type)
                all_source_logs[r_id].append(result_key)

    if not all_results:
        logging.warning(
            f"No valid IMDb ID found for '{initial_title}' after trying all candidates."
        )
        unique_errors = list(OrderedDict.fromkeys(errors))
        return None, None, unique_errors

    # Aggregate counts across all successful searches
    id_counts = defaultdict(int)
    type_per_id = defaultdict(lambda: defaultdict(int))  # {id: {type: count}}
    for r_id, r_type in all_results.values():
        if r_id:
            id_counts[r_id] += 1
            if r_type:
                type_per_id[r_id][r_type] += 1  # Count occurrences of each type for an ID

    logging.debug(f"IMDb ID counts for '{initial_title}' (all candidates): {dict(id_counts)}")
    logging.debug(
        f"Types found per ID: { {id_: dict(types) for id_, types in type_per_id.items()} }"
    )

    # Find the most frequently found ID(s)
    final_id = None
    final_type = None
    chosen_source_info = "None"

    if id_counts:
        max_count = max(id_counts.values())
        most_common_ids = [id_ for id_, count in id_counts.items() if count == max_count]

        if len(most_common_ids) == 1:  # Clear winner ID
            final_id = most_common_ids[0]
            # Determine best type for this ID based on frequency
            possible_types = type_per_id.get(final_id, {})
            if len(possible_types) == 1:
                final_type = next(iter(possible_types.keys()))
            elif possible_types:  # Multiple types reported, choose most frequent
                final_type = max(possible_types, key=possible_types.get)
            else:  # No type reported for this ID? Fallback.
                final_type = content_type if content_type in ["movie", "series"] else None

            # Identify contributing sources/candidates
            contributors = [
                f"{src}({cand[0]},{cand[1]})" for src, cand in all_source_logs[final_id]
            ]
            chosen_source_info = f"Consensus ({max_count} sources: {', '.join(contributors)})"
            logging.info(
                f"Found consensus IMDb ID: {final_id} (Type: {final_type}) for '{initial_title}'."
            )

        elif len(most_common_ids) > 1:  # Tie between IDs
            logging.warning(
                f"Multiple IDs found with the same highest frequency ({max_count}) for '{initial_title}': {most_common_ids}. Applying source priority."
            )
            # Fallback to source priority among the tied IDs
            # Define priority order of sources AND potentially candidate preference (e.g., prefer original title candidate)
            source_priority = ["tmdb_tv", "tmdb_movie", "omdb_title", "omdb_query", "imdbpy"]
            found_in_tie = False
            for cand in search_candidates:  # Check candidates in order (original first)
                for source_base in source_priority:
                    result_key = (source_base, cand)
                    if result_key in all_results:
                        r_id, r_type = all_results[result_key]
                        if (
                            r_id in most_common_ids
                        ):  # Did this prioritized source/candidate yield one of the tied IDs?
                            final_id = r_id
                            final_type = r_type
                            chosen_source_info = f"Tie-breaker: Prioritized source '{source_base}' (Candidate: {cand})"
                            logging.info(
                                f"Using IMDb ID from prioritized source/candidate '{chosen_source_info}': {final_id} (Type: {final_type}) for '{initial_title}'."
                            )
                            found_in_tie = True
                            break  # Break source loop
                if found_in_tie:
                    break  # Break candidate loop

    # If still no ID after tie-breaking (shouldn't happen if most_common_ids wasn't empty)
    if not final_id and id_counts:
        logging.error(
            f"Consensus logic failed to select an ID for '{initial_title}'. This shouldn't happen."
        )
        # As a last resort: pick the ID with the most type consistency? Or just the first one found?
        # Let's return None to be safe
        final_id = None
        final_type = None

    # --- Final Validation and Return ---
    if final_id:
        # Basic validation on the chosen type again
        if final_type not in ["movie", "series"]:  # Only allow these two final types
            logging.warning(
                f"Resolved IMDb type '{final_type}' is not 'movie' or 'series'. Setting to None."
            )
            final_type = None
        # Ensure ID format is correct
        numeric_part = "".join(filter(str.isdigit, final_id))
        final_id = f"tt{numeric_part}" if numeric_part else None

    if not final_id:
        logging.warning(
            f"Could not definitively determine IMDb ID for '{initial_title}' after checking all sources and candidates."
        )

    unique_errors = list(OrderedDict.fromkeys(errors))  # Keep only unique error messages
    return final_id, final_type, unique_errors


# --- Filename Parsing Utilities ---

# Comprehensive TV Show Regex
tv_show_pattern = re.compile(
    r"^"
    # 1) Show title (non-greedy)
    r"(?P<show_title>.*?)"
    # 2) Optional year in parentheses or with separators
    r"(?:[\._\s\(]+(?P<year>\d{4})[\._\s\)]+)?"
    # 3) Optional explicit season indicator (like "Season 2" or "S03", possibly in brackets)
    r"(?:"
    r"[\._\s]+"
    r"(?:[\(\[]?(?:season|s)[\s\._\-]?(?P<explicit_season>\d{1,3})[\)\]]?)"
    r")?"
    # 4) Separators before the actual "episode identifier" group
    r"[\._\s\-]*"
    # 5) Episode identifier group (non-capturing group containing multiple alternatives):
    r"(?:"
    # (A) Standard SxxEyy format
    r"[Ss](?P<season_s>\d{1,3})[\._\s\-]*[Ee](?P<episode_s>\d{1,3})"
    r"|"
    # (B) 1x02 format (with negative lookbehind/lookahead to avoid partial matches)
    r"(?<!\d)(?P<season_x>\d{1,3})x(?P<episode_x>\d{2,3})(?!\d)"
    r"|"
    # (C) E02 or Episode 02 format (No season captured here)
    r"(?<!\d)[Ee](?:p(?:isode)?)?[\s\._\-]*(?P<episode_e>\d{1,3})(?!\d)"
    r"|"
    # (D) "Season 1 Episode 01" format (season optional if already specified above)
    r"(?:season[\s\._\-]+(?P<season_se>\d{1,3})[\s\._\-]+)?episode[\s\._\-]+(?P<episode_se>\d{1,3})"
    r")"  # Close group 5
    # 6) Optional multi-episode group: captures LAST repetition only
    r"(?:"
    # E-style: E03, E04, etc.
    r"(?:[-\s\._]?[Ee](?P<additional_episodes_e>\d{1,3}))*"
    r"|"
    # Or numeric style: 03, 04, etc.
    r"(?:[-\s\._](?P<additional_episodes>\d{1,3}))*"
    r")?"  # Close group 6
    # 7) Optional trailing episode title or additional info (non-greedy)
    r"(?:[\._\s\-]+(?P<title_info>.*?))?"
    # 8) End pattern on a non-digit or end of string
    r"(?:[._\s-][^0-9]|$)"  # End boundary check
    r"$",  # Ensure the match reaches the very end of the string being processed
    re.IGNORECASE | re.VERBOSE,
)


def extract_tv_show_details(filename):  # noqa: C901
    """
    Extracts TV show details using a comprehensive regex with named groups.
    Returns (show_title, season, episode, year) or (None, None, None, None).
    """
    logging.debug(f"Attempting TV detail extraction from: {filename}")
    base_name = Path(filename).stem
    match = tv_show_pattern.match(base_name)  # Use the new complex pattern

    if match:
        groups = match.groupdict()
        logging.debug(f"Regex matched. Groupdict: {groups}")

        # --- Consolidate extracted parts ---
        show_title = groups.get("show_title")
        year = groups.get("year")  # Year might be captured separately

        # Determine Season (prioritize explicit, then Sxx, then x, then SE)
        season = (
            groups.get("explicit_season")
            or groups.get("season_s")
            or groups.get("season_x")
            or groups.get("season_se")
        )

        # Determine Episode (prioritize Sxx, then x, then E, then SE)
        episode = (
            groups.get("episode_s")
            or groups.get("episode_x")
            or groups.get("episode_e")
            or groups.get("episode_se")
        )

        # Clean up title (remove potential trailing separators)
        if show_title:
            show_title = re.sub(r"[\s\._-]+$", "", show_title).strip()
            # replace dots and underscores with spaces for better search results
            show_title = show_title.replace(".", " ").replace("_", " ")
            # Remove extra spaces if any
            show_title = re.sub(r"\s+", " ", show_title).strip()

        # Format season/episode with zero-padding if found
        if season:
            try:
                season = str(int(season)).zfill(2)
            except (ValueError, TypeError):
                season = None
        if episode:
            try:
                episode = str(int(episode)).zfill(2)
            except (ValueError, TypeError):
                episode = None

        # Log the final interpretation
        logging.debug(
            f"Interpreted details: Show='{show_title}', Season={season}, Episode={episode}, Year={year}"
        )

        # --- Validation: Ensure essential parts are present ---
        if show_title and season and episode:
            # Optionally clean title further if year was part of it initially
            if year and show_title.lower().endswith(f"({year})"):
                show_title = show_title[: -len(f"({year})")].strip()
            elif year and show_title.lower().endswith(str(year)):
                show_title = show_title[: -len(str(year))].strip()

            logging.info(
                f"Successfully extracted TV details: Show='{show_title}', Season={season}, Episode={episode}, Year={year} from '{filename}'"
            )
            return show_title, season, episode, year
        else:
            missing = []
            if not show_title:
                missing.append("Show Title")
            if not season:
                missing.append("Season")
            if not episode:
                missing.append("Episode")
            logging.warning(
                f"Extraction incomplete from '{filename}'. Missing: {', '.join(missing)}. Raw Match: {groups}"
            )
            return None, None, None, None

    # --- No Match ---
    logging.debug(f"Could not extract TV details using complex regex from filename: {filename}")
    return None, None, None, None


def extract_movie_details(filename):
    """Extracts movie title and year from filename."""
    base_name = Path(filename).stem
    # Keep the simpler movie pattern focused on year detection
    # Negative lookahead to avoid matching common resolutions like 1080p, 720p, 2160p etc. or i for interlaced
    movie_pattern = re.compile(
        r"^(.*?)(?:[._\s\(]+(19\d{2}|20\d{2})(?!p|i|\d{1,2}0p)[._\s\)]*).*$", re.IGNORECASE
    )
    match = movie_pattern.match(base_name)
    if match:
        title = match.group(1).replace(".", " ").replace("_", " ").strip()
        year = match.group(2)
        # Clean trailing separators potentially left before the year part
        title = re.sub(r"[\s\._-]+$", "", title).strip()
        logging.debug(f"Extracted Movie details: Title='{title}', Year={year} from '{filename}'")
        return title, year
    else:
        # Fallback: treat the whole name as the title if no year pattern matched
        title = base_name.replace(".", " ").replace("_", " ").strip()
        # Basic cleanup for common separators often left at the end
        title = re.sub(r"[\s\._-]+$", "", title).strip()
        logging.debug(
            f"Extracted Movie details (no year pattern): Title='{title}' from '{filename}'"
        )
        return title, None


# --- Explicit Exports ---
__all__ = ["extract_movie_details", "extract_tv_show_details", "get_imdb_id"]
