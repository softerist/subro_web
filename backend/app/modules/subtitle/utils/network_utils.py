import logging

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import (
    ConnectionError,
    ConnectTimeout,
    HTTPError,
    ReadTimeout,
    RequestException,
)
from urllib3.util.retry import Retry

# Import settings safely
try:
    from app.core.config import settings
except ImportError:
    # Fallback if run standalone or config structure changes
    class DummySettings:
        NETWORK_MAX_RETRIES = 3
        NETWORK_BACKOFF_FACTOR = 1
        NETWORK_CONNECT_TIMEOUT = 10.0
        NETWORK_READ_TIMEOUT = 30.0
        USER_AGENT_APP_NAME = "SubtitleTool"
        USER_AGENT_APP_VERSION = "1.0"

    settings = DummySettings()
    logging.warning("Could not import app.core.config. Using default network settings.")

logger = logging.getLogger(__name__)

# --- Configuration ---
DEFAULT_MAX_RETRIES = getattr(settings, "NETWORK_MAX_RETRIES", 3)
DEFAULT_BACKOFF_FACTOR = getattr(settings, "NETWORK_BACKOFF_FACTOR", 1)
DEFAULT_STATUS_FORCELIST = [429, 500, 502, 503, 504]  # Standard retry-worthy server/rate errors
# Use configured timeouts with fallback defaults
DEFAULT_CONNECT_TIMEOUT = getattr(settings, "NETWORK_CONNECT_TIMEOUT", 10.0)
DEFAULT_READ_TIMEOUT = getattr(settings, "NETWORK_READ_TIMEOUT", 30.0)


def create_session_with_retries(
    max_retries=DEFAULT_MAX_RETRIES,
    backoff_factor=DEFAULT_BACKOFF_FACTOR,
    status_forcelist=DEFAULT_STATUS_FORCELIST,
    allowed_methods=None,  # Include POST/DELETE etc. if needed
):
    """
    Creates a requests.Session configured with automatic retries on specific
    HTTP methods and status codes, using exponential backoff and respecting
    Retry-After headers.
    """
    if allowed_methods is None:
        allowed_methods = ["HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE"]
    session = requests.Session()
    retry_strategy = Retry(
        total=max_retries,
        status_forcelist=status_forcelist,
        allowed_methods=allowed_methods,
        backoff_factor=backoff_factor,
        respect_retry_after_header=True,  # Respect server-provided delay
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # Set User-Agent from config
    user_agent = f"{getattr(settings, 'USER_AGENT_APP_NAME', 'SubtitleTool')} v{getattr(settings, 'USER_AGENT_APP_VERSION', '1.0')}"
    session.headers.update({"User-Agent": user_agent})
    logger.debug(
        f"Requests session created with User-Agent='{user_agent}', "
        f"max_retries={max_retries}, backoff_factor={backoff_factor}, "
        f"status_forcelist={status_forcelist}, respect_retry_after=True"
    )
    return session


def make_request(session, method, url, **kwargs):  # noqa: C901
    """
    Makes an HTTP request using the provided session, handling common exceptions
    and logging request/response details. Uses configured default timeouts.

    Args:
        session (requests.Session): The session object to use.
        method (str): HTTP method (e.g., 'GET', 'POST').
        url (str): The URL to request.
        raise_for_status (bool): If True (default), raise HTTPError for bad responses (4xx/5xx).
                                  If False, return the response object even for errors.
        **kwargs: Additional arguments passed to session.request (e.g., params, json, data, headers, timeout).

    Returns:
        requests.Response or None: The response object if successful or if raise_for_status=False.
                                   None if a non-HTTP exception occurred (e.g., connection, timeout).
    """
    # Set default timeout if not provided in kwargs
    kwargs.setdefault("timeout", (DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT))
    raise_for_status = kwargs.pop("raise_for_status", True)

    # Log request details carefully (avoid logging sensitive headers completely)
    log_headers = kwargs.get("headers", session.headers).copy()  # Work with a copy
    if "Api-Key" in log_headers:
        log_headers["Api-Key"] = "***"
    if "Authorization" in log_headers:
        auth_val = log_headers["Authorization"]
        log_headers["Authorization"] = (
            auth_val[:15] + "..." if len(auth_val) > 15 else auth_val[:5] + "..."
        )

    logging.debug(f"Making request: {method} {url}")
    if kwargs.get("params"):
        logging.debug(f"  Params: {kwargs['params']}")
    # Truncate potentially large JSON/Data payloads in logs
    if kwargs.get("json"):
        logging.debug(f"  JSON: {str(kwargs['json'])[:300]}...")
    if kwargs.get("data"):
        logging.debug(f"  Data: {str(kwargs['data'])[:300]}...")
    # Log potentially modified headers
    logging.debug(f"  Headers: {log_headers}")
    logging.debug(f"  Timeout: {kwargs['timeout']}")

    try:
        response = session.request(method, url, **kwargs)
        # Log basic response info regardless of status code
        logging.debug(
            f"Request finished: {method} {url} -> Status {response.status_code} "
            f"(Size: {len(response.content)} bytes, Elapsed: {response.elapsed.total_seconds():.3f}s)"
        )
        # Optionally log Retry-After if present
        if "Retry-After" in response.headers:
            logging.info(
                f"  Server suggested Retry-After: {response.headers['Retry-After']} seconds"
            )

        # Raise exception for bad status codes ONLY if requested
        if raise_for_status:
            response.raise_for_status()  # Raises HTTPError for 4xx/5xx

        return response

    except HTTPError as e:
        # This block is only reached if raise_for_status=True and an HTTP error occurred
        status_code = e.response.status_code
        # Use appropriate log level based on client/server error
        log_level = logging.ERROR if status_code >= 500 else logging.WARNING

        # Build a clean error message
        if status_code == 404:
            error_info = f"Resource not found (404): {url} - The page may no longer exist or the ID is invalid."
        elif status_code == 401:
            error_info = f"Unauthorized (401): {url} - Check your API key or credentials."
        elif status_code == 403:
            error_info = f"Forbidden (403): {url} - Access denied. Check your API key permissions."
        elif status_code == 429:
            error_info = (
                f"Rate limited (429): {url} - Too many requests. Please wait before retrying."
            )
        else:
            # For other errors, include truncated response body
            error_info = f"{e}"
            if status_code < 500:
                try:
                    body_snippet = e.response.text[:200]
                    error_info += f" | Response: {body_snippet}"
                except Exception:
                    pass
        logging.log(log_level, error_info)

        return e.response  # Return the response containing the error status/body

    except (ConnectTimeout, ReadTimeout) as e:
        logging.warning(
            f"Timeout Error for {method} {url} (Connect: {kwargs['timeout'][0]}s, Read: {kwargs['timeout'][1]}s): {e}"
        )
        return None  # Indicate failure due to timeout
    except ConnectionError as e:
        logging.error(f"Connection Error for {method} {url}: {e}")
        return None  # Indicate failure due to connection issue
    except RequestException as e:
        # Catch other requests-related exceptions (e.g., InvalidURL)
        logging.error(f"Request Exception for {method} {url}: {e}", exc_info=True)
        return None
    except Exception as e:
        # Catch any other unexpected errors during the request/response cycle
        logging.error(f"An unexpected error occurred during request to {url}: {e}", exc_info=True)
        return None


# --- Explicit Exports ---
__all__ = [
    "create_session_with_retries",
    "make_request",
]
