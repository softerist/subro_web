# src/services/opensubtitles_client.py

import logging
from typing import Any

# Import the original module for its functions and config constants
# It's assumed that opensubtitles.py handles reading API keys/credentials from settings
from app.modules.subtitle.services import opensubtitles as opensubtitles_service

logger = logging.getLogger(__name__)


class OpenSubtitlesClient:
    """
    A stateful wrapper around the OpenSubtitles service functions,
    managing the authentication token and state for a single processing run.

    This client is intended to be instantiated once per processing pipeline
    (e.g., via a DI container) to handle login/logout correctly for that run.
    """

    def __init__(self):
        """Initializes the client with no token and resets the failure flag."""
        self._token: str | None = None
        self._auth_failed_this_session: bool = False
        # User agent is handled by the underlying service using config settings
        logger.debug("OpenSubtitlesClient initialized (Token: None, Auth Failed Flag: False)")

    def is_authenticated(self) -> bool:
        """
        Checks if the client currently holds a valid authentication token.

        Returns:
            bool: True if authenticated, False otherwise.
        """
        return bool(self._token)

    def authenticate(self) -> bool:
        """
        Attempts authentication using the underlying service function if not
        already authenticated or previously failed within this client instance.
        Stores the token locally upon success.

        Returns:
            bool: True if authentication is successful or client is already authenticated,
                  False otherwise (e.g., missing credentials, API error, previous failure).
        """
        if self.is_authenticated():
            logger.debug("OpenSubtitlesClient: Already authenticated in this session.")
            return True
        if self._auth_failed_this_session:
            logger.warning(
                "OpenSubtitlesClient: Skipping authentication attempt, previously failed in this session."
            )
            return False

        logger.info("OpenSubtitlesClient: Attempting authentication via underlying service...")

        # Call the underlying service function to perform authentication.
        # This function sets the module-level token in opensubtitles.py
        auth_success = opensubtitles_service.authenticate()

        if auth_success:
            # Retrieve the token that the service function obtained and stored globally
            self._token = opensubtitles_service.get_token()
            if self._token:
                logger.info(
                    f"OpenSubtitlesClient: Authentication successful (Token stored locally, ends '...{self._token[-5:]}')."
                )
                self._auth_failed_this_session = False  # Reset failure flag
                return True
            else:
                # This case indicates an internal issue if authenticate() returned True but get_token() returned None
                logger.error(
                    "OpenSubtitlesClient: Auth service reported success but failed to retrieve token."
                )
                self._auth_failed_this_session = True  # Mark as failed due to inconsistency
                return False
        else:
            logger.warning(
                "OpenSubtitlesClient: Authentication failed (via underlying service function)."
            )
            self._auth_failed_this_session = True  # Mark as failed for this session
            self._token = None  # Ensure token is cleared
            return False

    def logout(self) -> bool:
        """
        Logs out using the underlying service function and clears the local token state.

        Returns:
            bool: True if logout API call was successful or if not logged in initially,
                  False on API error during logout.
        """
        if not self.is_authenticated():
            logger.debug("OpenSubtitlesClient: Not logged in, skipping logout call.")
            # No API call needed, local state is already logged out.
            self._auth_failed_this_session = False  # Reset failure flag on explicit logout attempt
            return True

        logger.info("OpenSubtitlesClient: Attempting logout via underlying service...")
        # Call the service's logout function, which handles the API call
        # and clears the service's internal token state.
        logout_success = opensubtitles_service.logout()

        if logout_success:
            logger.info("OpenSubtitlesClient: Logout successful (via underlying service function).")
        else:
            logger.warning(
                "OpenSubtitlesClient: Logout failed or encountered an error (via underlying service function). Check service logs."
            )

        # Always clear local state after logout attempt, regardless of API success
        self._token = None
        self._auth_failed_this_session = False  # Reset failure flag after explicit logout
        logger.debug("OpenSubtitlesClient: Local token and failure flag cleared.")
        return logout_success

    # --- Wrapper methods for API calls ---

    def search_subtitles(self, **kwargs) -> list[dict[str, Any]] | None:
        """
        Wraps the service's search function, ensuring authentication first.

        Args:
            **kwargs: Arguments to pass directly to opensubtitles_service.search_subtitles
                      (e.g., language, imdb_id, query, type).

        Returns:
            Optional[List[Dict[str, Any]]]: A list of subtitle result dictionaries if successful,
                                            an empty list if no results found, or None on error/auth failure.
        """
        # Attempt authentication if not already logged in
        if not self.is_authenticated():
            logger.info(
                "OpenSubtitlesClient: Authentication required for search. Attempting implicit auth..."
            )
            if not self.authenticate():
                logger.error(
                    "OpenSubtitlesClient: Implicit authentication failed. Cannot perform search."
                )
                return None  # Return None if auth fails

        # If authenticated (or implicit auth succeeded), call the underlying service
        try:
            logger.debug(f"OpenSubtitlesClient: Calling search_subtitles with args: {kwargs}")
            results = opensubtitles_service.search_subtitles(**kwargs)
            # The underlying function returns None on error, [] if no results found
            return results
        except Exception as e:
            logger.error(
                f"OpenSubtitlesClient: Unexpected error during search_subtitles call: {e}",
                exc_info=True,
            )
            # Potential causes: Network issues not caught by underlying service's retry, unexpected data format, etc.
            return None

    def get_download_info(self, file_id: int) -> dict[str, Any] | None:
        """
        Wraps the service's get_download_info function, ensuring authentication first.

        Args:
            file_id (int): The file_id of the subtitle.

        Returns:
            Optional[Dict[str, Any]]: Dictionary containing download info (link, filename, etc.)
                                     if successful, None otherwise.
        """
        if not self.authenticate():  # Ensure authenticated implicitly
            logger.error("OpenSubtitlesClient: Authentication failed. Cannot get download info.")
            return None

        try:
            logger.debug(f"OpenSubtitlesClient: Calling get_download_info for file_id: {file_id}")
            info = opensubtitles_service.get_download_info(file_id)
            # Underlying function returns None on error
            return info
        except Exception as e:
            logger.error(
                f"OpenSubtitlesClient: Unexpected error during get_download_info call: {e}",
                exc_info=True,
            )
            return None

    def download_subtitle_content(self, download_link: str) -> bytes | None:
        """
        Wraps the service's download_subtitle_content function.
        This typically does not require authentication state from the client itself.

        Args:
            download_link (str): The direct download URL obtained from get_download_info.

        Returns:
            Optional[bytes]: The raw byte content of the subtitle file if successful,
                             None otherwise.
        """
        # No authentication check needed here as the link itself is usually temporary/signed
        # or doesn't require the session token.
        try:
            logger.debug(
                f"OpenSubtitlesClient: Calling download_subtitle_content for link: {download_link[:70]}..."
            )
            content = opensubtitles_service.download_subtitle_content(download_link)
            # Underlying function returns None on error or empty content
            return content
        except Exception as e:
            logger.error(
                f"OpenSubtitlesClient: Unexpected error during download_subtitle_content call: {e}",
                exc_info=True,
            )
            return None


# --- Explicit Exports ---
__all__ = ["OpenSubtitlesClient"]
