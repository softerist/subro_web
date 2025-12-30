import logging

# Import service modules/classes (adjust paths as needed)
# Stateless services (can often be referenced directly by module)
from app.modules.subtitle.services import imdb as imdb_service
from app.modules.subtitle.services import subsro as subsro_service
from app.modules.subtitle.services import (
    torrent_client as qb_client_service,  # Module with login function
)

# Stateful or complex initialization services
from app.modules.subtitle.services import (
    translator as translator_service,  # Has get_translation_manager() singleton
)
from app.modules.subtitle.services.opensubtitles_client import (
    OpenSubtitlesClient,  # Import the NEW stateful client wrapper
)

logger = logging.getLogger(__name__)


class ServiceContainer:
    """
    A simple container for lazily initializing and accessing services required
    by the subtitle processing pipeline strategies.
    """

    def __init__(self):
        """Initializes the container, setting up references but deferring actual client instantiation."""
        # References to stateless service modules
        self._imdb_service = imdb_service
        self._subsro_service = subsro_service

        # Placeholder for lazily initialized instances
        self._translator_manager_instance: translator_service.TranslationManager | None = None
        self._qb_client_instance: qb_client_service.qbittorrentapi.Client | None = None
        self._opensubtitles_client_instance: OpenSubtitlesClient | None = None

        logger.debug("ServiceContainer initialized.")

    @property
    def imdb(self):
        """Access the IMDb service module (assumed stateless)."""
        return self._imdb_service

    @property
    def subsro(self):
        """Access the Subs.ro service module (assumed stateless)."""
        return self._subsro_service

    @property
    def translator(self) -> translator_service.TranslationManager | None:
        """
        Lazily initializes and returns the Translation Manager singleton instance.
        Returns None if initialization fails.
        """
        if self._translator_manager_instance is None:
            logger.debug("Initializing Translation Manager...")
            try:
                # get_translation_manager handles initialization and singleton logic
                self._translator_manager_instance = translator_service.get_translation_manager()
                if self._translator_manager_instance:
                    logger.debug("Translation Manager initialized successfully.")
                else:
                    # This case implies get_translation_manager itself failed and returned None
                    logger.error(
                        "Translation Manager initialization failed (get_translation_manager returned None)."
                    )
            except Exception as e:
                logger.critical(
                    f"Critical error during Translation Manager initialization: {e}", exc_info=True
                )
                # Ensure instance remains None on error
                self._translator_manager_instance = None
        return self._translator_manager_instance

    @property
    def qbittorrent(self) -> qb_client_service.qbittorrentapi.Client | None:
        """
        Lazily initializes and returns an authenticated qBittorrent client.
        Returns None if login fails or client is not configured.
        """
        # Note: This property might not be used by the core pipeline strategies,
        # but is kept for potential use by post_process_completed_torrents if called separately.
        if self._qb_client_instance is None:
            logger.debug("Initializing qBittorrent client...")
            try:
                # login_to_qbittorrent handles config checks and potential login failures, returns None on fail
                self._qb_client_instance = qb_client_service.login_to_qbittorrent()
                if self._qb_client_instance:
                    logger.debug("qBittorrent client initialized and logged in.")
                else:
                    logger.warning(
                        "qBittorrent client initialization or login failed (check logs). Instance set to None."
                    )
            except Exception as e:
                logger.error(
                    f"Unexpected error during qBittorrent client initialization: {e}", exc_info=True
                )
                self._qb_client_instance = None  # Ensure None on error
        # Return the instance (which might be None if login failed)
        return self._qb_client_instance

    @property
    def opensubtitles(self) -> OpenSubtitlesClient | None:
        """
        Lazily initializes and returns the stateful OpenSubtitlesClient instance.
        Handles authentication internally within the client wrapper.
        Returns None if client initialization fails.
        """
        if self._opensubtitles_client_instance is None:
            logger.debug("Initializing OpenSubtitlesClient wrapper...")
            try:
                # Instantiate the new client wrapper
                self._opensubtitles_client_instance = OpenSubtitlesClient()
                logger.debug("OpenSubtitlesClient wrapper initialized.")
                # Implicit authentication attempt can happen when methods like search are called,
                # or we could optionally attempt it here after initialization if desired.
                # For now, let the client handle auth lazily on first use or via explicit calls.
            except Exception as e:
                logger.error(
                    f"Failed to initialize OpenSubtitlesClient wrapper: {e}", exc_info=True
                )
                self._opensubtitles_client_instance = None  # Ensure None on error
        return self._opensubtitles_client_instance

    def shutdown(self):
        """
        Performs cleanup actions for managed services, like logging out.
        Called by the pipeline at the end of processing for a file.
        """
        logger.info("Shutting down services via ServiceContainer...")

        # --- OpenSubtitles Logout ---
        if self._opensubtitles_client_instance:
            logger.debug("Attempting OpenSubtitles logout via client wrapper...")
            try:
                # Use the client wrapper's logout method
                logout_success = self._opensubtitles_client_instance.logout()
                if logout_success:
                    logger.debug("OpenSubtitles client logout call successful.")
                else:
                    logger.warning("OpenSubtitles client logout call reported failure or issues.")
            except Exception as e:
                logger.error(f"Error during OpenSubtitles client logout: {e}", exc_info=True)
        else:
            logger.debug("OpenSubtitles client was not initialized, skipping logout.")

        # --- qBittorrent Logout (Optional) ---
        # The qbittorrentapi client often doesn't require explicit logout,
        # but if it did, it would be handled here.
        # if self._qb_client_instance and hasattr(self._qb_client_instance, 'auth_log_out'):
        #     try:
        #         logger.debug("Attempting qBittorrent logout...")
        #         self._qb_client_instance.auth_log_out()
        #     except Exception as e:
        #         logger.error(f"Error during qBittorrent logout: {e}")

        # --- Other potential cleanup ---
        # e.g., closing database connections, releasing resources

        logger.info("ServiceContainer shutdown process complete.")
