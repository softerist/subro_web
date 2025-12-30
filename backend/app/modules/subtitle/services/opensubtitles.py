"""OpenSubtitles API service with state management for single auth/logout per run."""

import logging
from typing import Any

# Import config, network utils, etc.
from app.core.config import settings
from app.modules.subtitle.utils.network_utils import create_session_with_retries, make_request
from app.modules.subtitle.utils.subtitle_matcher import calculate_match_score

# Import necessary utils for matching and parsing
from app.modules.subtitle.utils.subtitle_parser import tokenize_and_normalize

logger = logging.getLogger(__name__)

# Define valid options for filters
VALID_FILTER_OPTIONS = {"include", "exclude", "only"}

APP_NAME = getattr(settings, "USER_AGENT_APP_NAME", "SubtitleTool")
APP_VERSION = getattr(settings, "USER_AGENT_APP_VERSION", "1.0")
MIN_OPENSUBS_MATCH_SCORE = getattr(settings, "OPENSUBTITLES_MIN_MATCH_SCORE", 10)

BASE_URL = "https://api.opensubtitles.com/api/v1"
LOGIN_URL = f"{BASE_URL}/login"
SEARCH_URL = f"{BASE_URL}/subtitles"
DOWNLOAD_URL = f"{BASE_URL}/download"
LOGOUT_URL = f"{BASE_URL}/logout"

# Shared session
network_session = create_session_with_retries()

_current_opensubs_token = None
_auth_failed_this_run = False  # Tracks if auth failed in the current script execution


# Helper for dynamic setting retrieval
def _get_dynamic_setting(db_field, env_var_name=None):
    """
    Fetches setting synchronously from DB, falling back to Environment/Settings.
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
                        # Handle potentially unnecessary decryption check if field isn't encrypted?
                        # Assuming these specific fields MIGHT be encrypted in DB model.
                        # Based on AppSettings model, keys/passwords are usually encrypted.
                        # We'll try decrypting, if it fails assume plain or handle error.
                        # Actually for AppSettings, we should know if it matches the schema.
                        # Just calling decrypt_value is safe if value is encrypted string.
                        if val == "":
                            return None
                        try:
                            return decrypt_value(val)
                        except Exception:
                            return val
    except Exception:
        pass

    # 2. Fallback to Environment
    if env_var_name:
        return getattr(settings, env_var_name, None)
    return None


def set_token(token):
    """Sets the active OpenSubtitles token for the service."""
    global _current_opensubs_token
    _current_opensubs_token = token
    if token:
        logger.debug(f"OpenSubtitles token state updated (ends '...{token[-5:]}').")
    else:
        logger.debug("OpenSubtitles token state cleared (set to None).")


def get_token():
    """Gets the currently active OpenSubtitles token stored in the module."""
    return _current_opensubs_token


def clear_token():
    """Clears the stored OpenSubtitles token."""
    global _auth_failed_this_run
    set_token(None)


def is_authenticated():
    """Checks if a valid token currently exists."""
    return bool(_current_opensubs_token)


def authenticate():
    """
    Authenticates with the OpenSubtitles API if not already authenticated
    and no prior attempt failed in this run. Sets the module token.
    Returns True on success or if already authenticated, False otherwise.
    """
    global _auth_failed_this_run

    # 1. Check if already authenticated
    if is_authenticated():
        logger.debug("OpenSubtitles: Already authenticated in this session.")
        return True

    # 2. Check if a previous attempt in this run failed
    if _auth_failed_this_run:
        logger.warning(
            "OpenSubtitles: Skipping authentication attempt, previous attempt in this run failed."
        )
        return False

    # 3. Credentials check
    api_key = _get_dynamic_setting("opensubtitles_api_key", "OPENSUBTITLES_API_KEY")
    username = _get_dynamic_setting("opensubtitles_username", "OPENSUBTITLES_USERNAME")
    password = _get_dynamic_setting("opensubtitles_password", "OPENSUBTITLES_PASSWORD")

    if not all([api_key, username, password]):
        logger.error("OpenSubtitles Auth Error: Credentials/API Key missing in config.")
        _auth_failed_this_run = True  # Mark as failed
        return False

    # 4. Attempt API Login
    payload = {"username": username, "password": password}
    headers = {
        "Api-Key": api_key,
        "Content-Type": "application/json",
        "User-Agent": f"{APP_NAME} v{APP_VERSION}",
    }
    logger.info("Attempting OpenSubtitles authentication via API...")
    response = make_request(
        network_session, "POST", LOGIN_URL, headers=headers, json=payload, raise_for_status=False
    )

    # 5. Process response
    if response and response.status_code == 200:
        try:
            data = response.json()
            token = data.get("token")
            user_info = data.get("user", {})  # Get user info if available
            if token:
                logger.info(
                    f"Successfully authenticated with OpenSubtitles (User Level: {user_info.get('level', 'N/A')}, Allowed Downloads: {user_info.get('allowed_downloads', 'N/A')})."
                )
                set_token(token)
                _auth_failed_this_run = False  # Reset failure flag on success
                return True
            else:
                logger.error(
                    f"OpenSubtitles Auth Failed: API returned success status but no token. Resp: {data}"
                )
                _auth_failed_this_run = True
                return False
        except ValueError:
            logger.error(
                f"OpenSubtitles Auth Failed: Could not decode JSON response. Status:{response.status_code}"
            )
            _auth_failed_this_run = True
            return False
    elif response:
        logger.error(
            f"OpenSubtitles Auth Failed: API returned status {response.status_code}. Body: {response.text[:200]}"
        )
        _auth_failed_this_run = True
        return False
    else:
        logger.error("OpenSubtitles Auth Failed: Network error or no response received.")
        _auth_failed_this_run = True
        return False


def logout():
    """
    Logs out using the currently stored token (if any) and clears state.
    Returns True if logout API call was successful or if not logged in, False on API error.
    """
    global _auth_failed_this_run
    token = get_token()

    logout_success = False
    if not token:
        logger.debug("OpenSubtitles Logout: Not currently logged in or no API key.")
        logout_success = True  # Consider it "successful" in terms of state being logged out
    else:
        api_key = _get_dynamic_setting("opensubtitles_api_key", "OPENSUBTITLES_API_KEY")
        if not api_key:
            logger.error("OpenSubtitles Logout Error: API Key missing.")
            logout_success = False
        else:
            headers = {
                "Api-Key": api_key,
                "Authorization": f"Bearer {token}",
                "User-Agent": f"{APP_NAME} v{APP_VERSION}",
            }
            logger.info("Attempting OpenSubtitles logout via API...")
            response = make_request(
                network_session, "DELETE", LOGOUT_URL, headers=headers, raise_for_status=False
            )
            logout_success = response and response.status_code in [
                200,
                204,
            ]  # 204 No Content is also valid for DELETE success

            if logout_success:
                logger.info("Logged out from OpenSubtitles successfully via API.")
            elif response:
                logger.error(
                    f"OpenSubtitles Logout Failed: API returned status {response.status_code}. Body: {response.text[:200]}"
                )
            else:
                logger.error("OpenSubtitles Logout Failed: Network error or no response received.")

    # Always clear state after attempting logout
    logger.debug("Clearing OpenSubtitles token and resetting failure flag post-logout attempt.")
    set_token(None)
    _auth_failed_this_run = False
    return logout_success


def _opensubs_api_request(method, url, needs_auth=True, retry_on_401=True, **kwargs):
    """
    Internal helper to make API requests.
    Relies on authenticate() having been called previously if needs_auth=True.
    Handles token expiry (401 retry).
    """
    headers = kwargs.pop("headers", {})
    api_key = _get_dynamic_setting("opensubtitles_api_key", "OPENSUBTITLES_API_KEY")
    headers["Api-Key"] = api_key
    headers["User-Agent"] = f"{APP_NAME} v{APP_VERSION}"
    if "Content-Type" not in headers and ("json" in kwargs or "data" in kwargs):
        headers["Content-Type"] = "application/json"

    token = None
    if needs_auth:
        token = get_token()
        if not token:
            # Don't try to authenticate here. The caller should have done it.
            logger.error(
                f"OpenSubtitles API request aborted: Authentication required for {method} {url} but not currently logged in."
            )
            return None
        headers["Authorization"] = f"Bearer {token}"

    # Initial request
    response = make_request(
        network_session, method, url, headers=headers, raise_for_status=False, **kwargs
    )

    # Handle 401 Unauthorized (potentially expired token)
    if needs_auth and retry_on_401 and response and response.status_code == 401:
        logger.warning(
            f"Received 401 Unauthorized from OpenSubtitles for {url}. Token might be expired. Attempting re-authentication..."
        )
        # Call the main authenticate function - it handles state and might return a *new* token
        if authenticate():  # This will attempt API login only if necessary and possible
            new_token = get_token()  # Get the potentially updated token
            if new_token:  # Should always be true if authenticate() returned True
                logger.info("Re-authentication successful. Retrying original request...")
                headers["Authorization"] = f"Bearer {new_token}"  # Use the new token
                response = make_request(
                    network_session, method, url, headers=headers, raise_for_status=False, **kwargs
                )  # Retry ONCE
                if response and response.status_code == 401:
                    logger.error(
                        "Re-authentication successful, but API retry still resulted in 401. Giving up."
                    )
                    # Potentially invalidate the token again if 401 persists even after re-auth
                    # clear_token() # Or let the next call handle it
            else:
                # This case should theoretically not happen if authenticate() logic is correct
                logger.error(
                    "Re-authentication reported success but token is missing. Cannot retry."
                )
                # Return the original 401 response
        else:
            logger.error("Re-authentication attempt failed. Cannot retry request.")
            # Return the original 401 response
        # Return the response from the retry attempt (or the original 401 if re-auth failed)

    # Log other errors or handle success
    elif response is None:
        logger.error(f"OpenSubtitles API request failed (Network/Internal Error): {method} {url}")
    elif (
        response.status_code >= 400 and response.status_code != 401
    ):  # Log non-401 client/server errors
        log_level = logging.ERROR if response.status_code >= 500 else logging.WARNING
        logger.log(
            log_level,
            f"OpenSubtitles API request error: Status {response.status_code} for {method} {url}. Resp: {response.text[:200]}",
        )

    # Return the final response object (could be success, error, or None)
    return response


def clean_imdb_id(imdb_id: str | None) -> str | None:
    """
    Removes the "tt" prefix from an IMDb ID if present.

    Args:
        imdb_id: IMDb identifier as a string.

    Returns:
        The numeric part of the IMDb ID or None if the id is empty.
    """
    if imdb_id:
        imdb_id = imdb_id.strip()
        if imdb_id.startswith("tt"):
            return imdb_id[2:]
    return imdb_id


def search_subtitles(  # noqa: C901
    language: str = "ro",
    imdb_id: str | None = None,
    parent_imdb_id: str | None = None,
    season_number: int | None = None,
    episode_number: int | None = None,
    query: str | None = None,
    type: str | None = None,  # 'movie' or 'episode'
    machine_translated: str = "exclude",
    hearing_impaired: str = "exclude",
) -> list[dict[str, Any]] | None:
    """
    Performs subtitle search using precise API parameters when possible.
    Leverages explicit identifiers to reduce dependency on fuzzy textual queries.

    Args:
        language: 2-letter language code.
        imdb_id: Movie IMDb ID (used when type is 'movie').
        parent_imdb_id: Show IMDb ID (used when type is 'episode').
        season_number: Season number (used when type is 'episode').
        episode_number: Episode number (used when type is 'episode').
        query: Fallback search string (e.g., Movie Title [Year] or general query).
        type: 'movie' or 'episode'. Guides which parameters are used.
        machine_translated: One of 'include', 'exclude', 'only'.
        hearing_impaired: One of 'include', 'exclude', 'only'.

    Returns:
        A list of subtitle results if successful (empty list if no results),
        or None if an error occurs or if no valid identifier is provided.
    """
    # Validate filter parameters
    if machine_translated not in VALID_FILTER_OPTIONS:
        logger.error(
            f"Invalid machine_translated value: '{machine_translated}'. Allowed: {VALID_FILTER_OPTIONS}"
        )
        return None
    if hearing_impaired not in VALID_FILTER_OPTIONS:
        logger.error(
            f"Invalid hearing_impaired value: '{hearing_impaired}'. Allowed: {VALID_FILTER_OPTIONS}"
        )
        return None

    # Initialize parameters and search description
    params: dict[str, Any] = {"languages": language}
    search_description_parts: list[str] = []

    # Add filter parameters
    params["machine_translated"] = machine_translated
    search_description_parts.append(f"machine_translated={machine_translated}")

    params["hearing_impaired"] = hearing_impaired
    search_description_parts.append(f"hearing_impaired={hearing_impaired}")

    identifier_found = False

    # For TV episodes: use parent_imdb_id and season/episode numbers
    if (
        type == "episode"
        and parent_imdb_id
        and (season_number is not None)
        and (episode_number is not None)
    ):
        cleaned_parent_imdb = clean_imdb_id(parent_imdb_id)
        if not cleaned_parent_imdb:
            logger.error("Invalid parent_imdb_id provided.")
            return None
        params["parent_imdb_id"] = cleaned_parent_imdb
        params["season_number"] = int(season_number)
        params["episode_number"] = int(episode_number)
        search_description_parts.insert(
            0,
            f"TV Episode (imdb={parent_imdb_id}, S{str(season_number).zfill(2)}, E{str(episode_number).zfill(2)})",
        )
        identifier_found = True
    # For movies: prefer IMDb ID, then fallback to query
    elif type == "movie":
        if imdb_id:
            cleaned_imdb = clean_imdb_id(imdb_id)
            if not cleaned_imdb:
                logger.error("Invalid imdb_id provided.")
                return None
            params["imdb_id"] = cleaned_imdb
            search_description_parts.insert(0, f"Movie (imdb={imdb_id})")
            identifier_found = True
        elif query and query.strip():
            params["query"] = query.strip()
            search_description_parts.insert(0, f"Movie (query='{query.strip()}')")
            identifier_found = True
    # General fallback: use query if available and not just whitespace
    elif query and query.strip():
        params["query"] = query.strip()
        search_description_parts.insert(0, f"General (query='{query.strip()}')")
        identifier_found = True

    if not identifier_found:
        logger.error(
            "Cannot search OS: No valid identifier provided (imdb_id/parent_imdb_id+S/E, or query)."
        )
        return None

    # Remove None values from params (if any)
    params = {k: v for k, v in params.items() if v is not None}

    logger.info(
        f"Searching OpenSubtitles ({', '.join(search_description_parts)}) with params: {params}"
    )

    # Execute the API request; assumes _opensubs_api_request handles authentication and token refreshing.
    response = _opensubs_api_request("GET", SEARCH_URL, params=params)

    if response is None:
        logger.error(
            "OpenSubtitles search failed (request helper returned None - likely auth issue or network error)."
        )
        return None

    if response.status_code == 200:
        try:
            data = response.json()
            results = data.get("data", [])
            total_count = data.get("total_count", 0)
            if not results:
                logger.info("No OpenSubtitles subtitles found matching the search criteria.")
                return []  # Returning an empty list if no results are found
            else:
                logger.info(
                    f"OpenSubtitles search successful. Found {len(results)} subtitles (total matching criteria: {total_count})."
                )
                return results
        except ValueError:
            logger.error(
                f"Failed to decode OpenSubtitles search JSON. Status: {response.status_code}",
                exc_info=True,
            )
            return None
    else:
        logger.error(f"OpenSubtitles search request resulted in status {response.status_code}.")
        return None


def get_download_info(file_id):
    """
    Requests download info. Relies on prior call to authenticate().
    """
    if not file_id:
        logger.error("Cannot get download info: file_id missing.")
        return None
    payload = {"file_id": int(file_id)}
    logger.info(f"Requesting download info for file_id: {file_id}")

    # Use helper, needs auth implicitly
    response = _opensubs_api_request("POST", DOWNLOAD_URL, json=payload)

    if response is None:
        logger.error("OpenSubtitles get download info failed (request helper returned None).")
        return None

    if response.status_code == 200:
        try:
            data = response.json()
            if data and "link" in data and data["link"]:
                logger.info(f"OK: Retrieved download info for file_id: {file_id}")
                return data
            else:
                logger.error(
                    f"OpenSubtitles download info OK status, but 'link' missing/empty in response: {data}"
                )
                return None
        except ValueError:
            logger.error(
                f"Failed decode OpenSubtitles download JSON. Status:{response.status_code}"
            )
            return None
    else:
        # Error already logged by helper
        logger.error(
            f"OpenSubtitles get download info request resulted in status {response.status_code}."
        )
        return None


def download_subtitle_content(download_link):
    """Downloads subtitle content (no auth needed, uses separate session)."""
    if not download_link:
        logger.error("Cannot download subtitle: link missing.")
        return None
    logger.info(f"Downloading OpenSubtitles content from link: {download_link[:70]}...")
    # Use a temporary session for this potentially external URL, respecting redirects
    temp_session = create_session_with_retries()  # Use network_utils session creator
    temp_session.headers.update({"User-Agent": f"{APP_NAME} v{APP_VERSION}"})  # Add user agent
    response = make_request(
        temp_session, "GET", download_link, stream=True, allow_redirects=True
    )  # Use network_utils maker

    if response and response.status_code == 200:
        try:
            content = response.content
            if not content:
                logger.warning(f"Downloaded empty content from {download_link}")
                return None  # Return None for empty content
            logger.info(f"OK: Downloaded {len(content)} bytes OpenSubtitles content.")
            return content
        except Exception as e:
            logger.error(f"Error reading downloaded OpenSubtitles content: {e}")
            return None
    else:
        if response is not None:
            logger.error(f"Failed download OpenSubtitles content, status: {response.status_code}")
        else:
            logger.error("Failed download OpenSubtitles content (network error).")
        return None


def find_best_subtitle_match(subtitle_results, target_release_name):  # noqa: C901
    """
    Scores and finds the best matching subtitle from a list of OpenSubtitles API results.
    (Uses v2's scoring logic which is generally more robust)
    """
    if not subtitle_results:
        logger.debug("Cannot find best match: No results provided.")
        return None
    if not target_release_name:
        logger.warning("Cannot find best match: Target name empty.")
        return None
    logger.info(
        f"Finding best match for '{target_release_name}' among {len(subtitle_results)} OpenSubtitles results..."
    )
    target_tokens = tokenize_and_normalize(target_release_name)
    scored_subtitles = []
    for sub_result in subtitle_results:
        try:
            attrs = sub_result.get("attributes", {})
            files_info = attrs.get("files", [])
            if not files_info:
                continue
            # Ensure release and file_name are strings before tokenizing
            sub_release = attrs.get("release", "") or ""
            sub_file = files_info[0].get("file_name", "") or ""
            release_tokens = tokenize_and_normalize(sub_release)
            file_tokens = tokenize_and_normalize(sub_file)
            if not release_tokens and not file_tokens:
                continue

            release_score = calculate_match_score(target_tokens, release_tokens)
            file_score = calculate_match_score(target_tokens, file_tokens)
            # v2 scoring weights release name slightly higher
            combined_score = (release_score * 1.2) + (file_score * 0.8)
            # Bonus/Penalties
            if release_score > 10 and file_score > 10:
                combined_score += 10  # Good match on both
            if attrs.get("from_trusted"):
                combined_score += 5
            if attrs.get("ai_translated") or attrs.get("machine_translated"):
                combined_score -= 20
            if attrs.get("hearing_impaired"):
                combined_score -= 2
            logger.debug(
                f"  - Sub ID {sub_result.get('id')}: Rel='{sub_release}' (Scr:{release_score}) | File='{sub_file}' (Scr:{file_score}) | Combined:{combined_score:.2f}"
            )
            scored_subtitles.append((combined_score, sub_result))
        except Exception as score_err:
            logger.error(f"Error scoring OpenSubtitles result {sub_result.get('id')}: {score_err}")
    if not scored_subtitles:
        logger.warning("No OpenSubtitles subtitles could be scored.")
        return None

    scored_subtitles.sort(key=lambda x: x[0], reverse=True)
    best_score, best_match = scored_subtitles[0]
    if best_score < MIN_OPENSUBS_MATCH_SCORE:
        logger.warning(
            f"Best OpenSubtitles score ({best_score:.2f}) below threshold ({MIN_OPENSUBS_MATCH_SCORE}). No match."
        )
        return None

    attrs = best_match.get("attributes", {})
    file_info = attrs.get("files", [{}])[0]
    logger.info(
        f"Selected best OpenSubtitles match (Score: {best_score:.2f}): ID={best_match.get('id')}, Rel='{attrs.get('release', 'N/A')}', File='{file_info.get('file_name', 'N/A')}'"
    )
    return best_match


__all__ = [
    "authenticate",
    "download_subtitle_content",
    "find_best_subtitle_match",
    "get_download_info",
    "get_token",  # Added get_token
    "is_authenticated",
    "logout",
    "search_subtitles",
]
