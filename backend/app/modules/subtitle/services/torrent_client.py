import logging
from typing import Any

import qbittorrentapi

# Import the centralized settings
from app.core.config import settings

# Access settings safely
QBITTORRENT_HOST = getattr(settings, "QBITTORRENT_HOST", "192.168.1.254")
QBITTORRENT_PORT = getattr(settings, "QBITTORRENT_PORT", 8080)
QBITTORRENT_USERNAME = getattr(settings, "QBITTORRENT_USERNAME", None)
QBITTORRENT_PASSWORD = getattr(settings, "QBITTORRENT_PASSWORD", None)


def get_client() -> qbittorrentapi.Client | None:
    """
    Initializes and returns a qBittorrent API client instance.
    Handles basic connection setup. Returns None if configuration is missing.
    """
    # Validate essential configuration
    if not all(
        [QBITTORRENT_HOST, QBITTORRENT_USERNAME is not None, QBITTORRENT_PASSWORD is not None]
    ):
        # Allow empty username/password if user configured it that way, but host must exist
        if not QBITTORRENT_HOST:
            logging.error("qBittorrent configuration 'qbittorrent_host' is missing in config.yaml.")
            return None
        # Log warning if username/password look missing but proceed
        if QBITTORRENT_USERNAME is None or QBITTORRENT_PASSWORD is None:
            logging.warning(
                "qBittorrent username or password might be missing/empty in config.yaml."
            )

    try:
        client = qbittorrentapi.Client(
            host=QBITTORRENT_HOST,
            port=QBITTORRENT_PORT,
            username=QBITTORRENT_USERNAME or "",  # Pass empty string if None
            password=QBITTORRENT_PASSWORD or "",  # Pass empty string if None
            # Add REQUESTS_ARGS for timeout? Might be useful.
            # REQUESTS_ARGS={'timeout': (10, 30)} # connect, read timeouts
        )
        # Optional: Add verification step here if supported by library version
        # client.auth_verify() # Example, check actual method if exists
        return client
    except Exception as e:
        logging.error(f"Failed to initialize qBittorrent client: {e}", exc_info=True)
        return None


def login_to_qbittorrent() -> qbittorrentapi.Client | None:
    """
    Attempts to log in to the qBittorrent client.

    Returns:
        qbittorrentapi.Client or None: The logged-in client instance or None if login fails.
    """
    client = get_client()
    if not client:
        return None  # Initialization failed

    try:
        logging.info(
            f"Attempting to log in to qBittorrent @ {QBITTORRENT_HOST}:{QBITTORRENT_PORT}..."
        )
        client.auth_log_in()  # This might raise exceptions on failure
        # Verify login status if possible (older versions might not have is_logged_in reliably)
        if client.is_logged_in:
            api_version = client.app.version
            webui_version = client.app.web_api_version
            logging.info(
                f"Successfully logged in to qBittorrent (API v{api_version}, WebUI v{webui_version})"
            )
            return client
        else:
            # Should not happen if auth_log_in succeeded without error, but safety check
            logging.error(
                "qBittorrent login appeared to succeed but client status is not logged in."
            )
            return None
    except qbittorrentapi.LoginFailed as e:
        logging.error(
            f"qBittorrent login failed for user '{QBITTORRENT_USERNAME}' at "
            f"{QBITTORRENT_HOST}:{QBITTORRENT_PORT}: {e}"
        )
        return None
    except qbittorrentapi.exceptions.APIConnectionError as e:
        logging.error(
            f"Could not connect to qBittorrent at {QBITTORRENT_HOST}:{QBITTORRENT_PORT}: {e}"
        )
        return None
    except qbittorrentapi.exceptions.APIError as e:
        logging.error(f"qBittorrent API error during login: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during qBittorrent login: {e}", exc_info=True)
        return None


def get_completed_torrents(client: qbittorrentapi.Client) -> list[Any]:
    """
    Retrieves a list of completed torrents from the qBittorrent client.
    Includes torrents fully downloaded but still seeding/uploading.

    Args:
        client (qbittorrentapi.Client): An authenticated qBittorrent client instance.

    Returns:
        list: A list of torrent info objects for completed torrents, or an empty list if none found or error occurs.
    """
    if not client or not client.is_logged_in:
        logging.error("Cannot get completed torrents: qBittorrent client not logged in.")
        return []
    try:
        # Fetch torrents by relevant status filters
        completed = client.torrents_info(status_filter="completed")
        seeding = client.torrents_info(status_filter="seeding")

        # Combine lists, ensuring uniqueness by hash and checking progress
        potentially_complete: dict[str, Any] = {}
        for t in completed + seeding:
            if t.progress == 1.0:  # Check if fully downloaded
                # Use hash as key to automatically handle duplicates from different filters
                potentially_complete[t.hash] = t

        result_list = list(potentially_complete.values())

        if not result_list:
            logging.info("No completed or fully downloaded seeding/uploading torrents found.")
        else:
            logging.debug(f"Found {len(result_list)} potentially complete torrents.")
        return result_list

    except qbittorrentapi.exceptions.APIError as e:
        logging.error(f"API Error retrieving torrent list: {e}")
        return []
    except Exception as e:
        logging.error(f"An unexpected error occurred retrieving torrent list: {e}", exc_info=True)
        return []


def get_torrent_files(client: qbittorrentapi.Client, torrent_hash: str) -> list[Any]:
    """
    Retrieves the list of files for a specific torrent.

    Args:
        client (qbittorrentapi.Client): An authenticated qBittorrent client instance.
        torrent_hash (str): The hash of the torrent.

    Returns:
        list: A list of file info objects, or an empty list on error.
    """
    if not client or not client.is_logged_in:
        logging.error("Cannot get torrent files: qBittorrent client not logged in.")
        return []
    if not torrent_hash:
        logging.error("Cannot get torrent files: Torrent hash is required.")
        return []
    try:
        files = client.torrents_files(torrent_hash=torrent_hash)
        logging.debug(f"Retrieved {len(files)} files for torrent hash {torrent_hash}.")
        return list(files)
    except qbittorrentapi.exceptions.NotFound404Error:
        logging.error(f"Torrent with hash {torrent_hash} not found.")
        return []
    except qbittorrentapi.exceptions.APIError as e:
        logging.error(f"API Error retrieving files for torrent {torrent_hash}: {e}")
        return []
    except Exception as e:
        logging.error(
            f"An unexpected error occurred retrieving files for torrent {torrent_hash}: {e}",
            exc_info=True,
        )
        return []


def rename_torrent_file(
    client: qbittorrentapi.Client, torrent_hash: str, old_path: str, new_path: str
) -> bool:
    """
    Renames a file within a torrent in qBittorrent.

    Args:
        client (qbittorrentapi.Client): An authenticated qBittorrent client instance.
        torrent_hash (str): The hash of the torrent containing the file.
        old_path (str): The current relative path of the file within the torrent.
        new_path (str): The desired new relative path of the file within the torrent.

    Returns:
        bool: True if renaming was successful (or appeared to be), False otherwise.
    """
    if not client or not client.is_logged_in:
        logging.error("Cannot rename torrent file: qBittorrent client not logged in.")
        return False
    if not all([torrent_hash, old_path, new_path]):
        logging.error("Cannot rename torrent file: Missing torrent_hash, old_path, or new_path.")
        return False
    if old_path == new_path:
        logging.warning(
            f"Skipping rename for torrent {torrent_hash}: old path and new path are identical ('{old_path}')."
        )
        return True  # No action needed, considered success

    try:
        logging.info(f"Attempting to rename '{old_path}' to '{new_path}' in torrent {torrent_hash}")
        # The API call itself might not return useful status, rely on absence of exceptions
        client.torrents_rename_file(torrent_hash=torrent_hash, old_path=old_path, new_path=new_path)
        # Add a small delay and verify? Might be overkill and unreliable.
        # time.sleep(1)
        # files_after = client.torrents_files(torrent_hash=torrent_hash)
        # if any(f.name == new_path for f in files_after): ...
        logging.info(
            f"Successfully initiated rename of '{old_path}' to '{new_path}' in qBittorrent."
        )
        return True
    except qbittorrentapi.exceptions.NotFound404Error:
        logging.error(f"Rename failed: Torrent {torrent_hash} or file '{old_path}' not found.")
        return False
    except qbittorrentapi.exceptions.APIError as e:
        # Check for specific errors if the library provides useful info
        logging.error(
            f"API Error renaming file '{old_path}' to '{new_path}' in torrent {torrent_hash}: {e}"
        )
        return False
    except Exception as e:
        logging.error(
            f"An unexpected error occurred renaming file in torrent {torrent_hash}: {e}",
            exc_info=True,
        )
        return False


def configure_webhook_autorun(
    client: qbittorrentapi.Client,
    script_path: str = "/opt/subro_web/scripts/qbittorrent-nox-webhook.sh",
    api_key: str | None = None,
) -> bool:
    """
    Configure qBittorrent to run the webhook script on torrent completion.

    Args:
        client: An authenticated qBittorrent client instance.
        script_path: Path to the webhook script on the host.
        api_key: Optional API key to pass to the script via --api-key argument.

    Returns:
        bool: True if configuration was successful, False otherwise.
    """
    if not client or not client.is_logged_in:
        logging.error("Cannot configure autorun: qBittorrent client not logged in.")
        return False

    try:
        autorun_command = f'/usr/bin/bash {script_path} "%F"'
        if api_key:
            # Append API key securely quoted
            autorun_command += f' --api-key="{api_key}"'

        client.app.set_preferences(
            {
                "autorun_enabled": True,
                "autorun_program": autorun_command,
            }
        )
        # Log command with masked key for security
        log_cmd = autorun_command
        if api_key:
            log_cmd = log_cmd.replace(api_key, "***")
        logging.info(f"Configured qBittorrent autorun: {log_cmd}")
        return True
    except qbittorrentapi.exceptions.APIError as e:
        logging.error(f"API Error configuring autorun: {e}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error configuring autorun: {e}", exc_info=True)
        return False


def get_autorun_config(client: qbittorrentapi.Client) -> dict | None:
    """
    Get the current autorun configuration from qBittorrent.

    Returns:
        dict with 'enabled' and 'program' keys, or None on error.
    """
    if not client or not client.is_logged_in:
        logging.error("Cannot get autorun config: qBittorrent client not logged in.")
        return None

    try:
        prefs = client.app.preferences
        return {
            "enabled": prefs.get("autorun_enabled", False),
            "program": prefs.get("autorun_program", ""),
        }
    except Exception as e:
        logging.error(f"Error getting autorun config: {e}", exc_info=True)
        return None


def disable_webhook_autorun(client: qbittorrentapi.Client) -> bool:
    """
    Disable qBittorrent autorun configuration.

    Args:
        client: An authenticated qBittorrent client instance.

    Returns:
        bool: True if disabled successfully, False otherwise.
    """
    if not client or not client.is_logged_in:
        logging.error("Cannot disable autorun: qBittorrent client not logged in.")
        return False

    try:
        client.app.set_preferences(
            {
                "autorun_enabled": False,
                # Optionally clear the program, but disabling is sufficient and safer
                # to avoid wiping unrelated configs if someone toggles it back manually?
                # But requirement is "remove integration".
                "autorun_program": "",
            }
        )
        logging.info("Disabled qBittorrent autorun.")
        return True
    except qbittorrentapi.exceptions.APIError as e:
        logging.error(f"API Error disabling autorun: {e}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error disabling autorun: {e}", exc_info=True)
        return False


# Explicit Exports
__all__ = [
    "configure_webhook_autorun",
    "disable_webhook_autorun",
    "get_autorun_config",
    "get_client",
    "get_completed_torrents",
    "get_torrent_files",
    "login_to_qbittorrent",
    "rename_torrent_file",
]
