import logging
import random  # Keep for filename generation fallback
import re
import time  # Keep for filename generation fallback
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.core.config import settings
from app.modules.subtitle.utils.network_utils import create_session_with_retries, make_request

# --- Configuration & Constants ---
SUBSRO_BASE_URL = "https://subs.ro"

# Create a shared requests session for subs.ro scraping
network_session = create_session_with_retries(
    max_retries=getattr(settings, "NETWORK_MAX_RETRIES", 3),
    backoff_factor=getattr(settings, "NETWORK_BACKOFF_FACTOR", 1),
)
logger = logging.getLogger(__name__)

# --- Helper Functions ---


def _get_subtitle_page_url(imdb_id):
    """Constructs the URL for the subs.ro page for a given IMDb ID."""
    numeric_imdb_id = "".join(filter(str.isdigit, imdb_id or ""))  # Handle potential None input
    if not numeric_imdb_id:
        logging.error(f"Invalid IMDb ID format provided for Subs.ro URL: {imdb_id}")
        return None
    return f"{SUBSRO_BASE_URL}/subtitrari/imdbid/{numeric_imdb_id}"


def _fetch_and_parse_page(url):
    """Fetches the HTML content of a URL and parses it with BeautifulSoup."""
    logging.debug(f"Fetching Subs.ro page: {url}")
    # Use a reasonable timeout for scraping requests
    response = make_request(network_session, "GET", url, timeout=15)  # Add timeout
    if response and response.content:
        try:
            # Use lxml for potentially faster parsing if installed
            soup = BeautifulSoup(response.content, "lxml")  # Specify 'lxml' parser
            logging.debug(f"Successfully fetched and parsed HTML from {url} (using lxml)")
            return soup
        except ImportError:  # Fallback if lxml is not installed
            try:
                soup = BeautifulSoup(response.content, "html.parser")
                logging.debug(
                    f"Successfully fetched and parsed HTML from {url} (using html.parser)"
                )
                return soup
            except Exception as e:
                logging.error(
                    f"Error parsing HTML content from {url} with html.parser: {e}", exc_info=True
                )
                return None
        except Exception as e:
            logging.error(f"Error parsing HTML content from {url} with lxml: {e}", exc_info=True)
            return None
    # make_request logs errors on failure
    return None


def _extract_download_links(soup, language_code):
    """Extracts subtitle download links for a specific language from parsed HTML."""

    download_links = []
    if not soup:
        return download_links

    lang_suffix = f"- {language_code.lower()}"

    logging.debug(f"Searching for img alt tags ending with: '{lang_suffix}'")

    # Find image tags indicating the language
    subtitle_elements = soup.find_all(
        "img", alt=lambda x: x and x.strip().endswith(lang_suffix)
    )  # Stricter search
    # subtitle_elements = soup.find_all('img', alt=lambda x: x and lang_suffix in x) # Relaxed search - Keep this commented. Only remove it manually by a validated decision.

    if not subtitle_elements:
        logging.debug(f"No subtitles found for language '{language_code}' based on img alt tags.")
        return download_links

    logging.debug(
        f"Found {len(subtitle_elements)} potential subtitle entries for language '{language_code}'."
    )

    processed_links = set()  # Avoid duplicate URLs

    for img_tag in subtitle_elements:
        # Find the parent container div holding the link
        parent_div = img_tag.find_parent("div", class_="grid")
        if not parent_div:
            logging.warning("Could not find parent 'grid' div for a subtitle img tag.")
            continue

        # Find the download link within this container
        link_tags = parent_div.find_all("a", href=True)
        found_link_href = None
        for link in link_tags:
            link_text = link.text.strip().lower()
            # Check for download indicators
            if "descarcă" in link_text or link.find(
                "i", class_=lambda c: c and "fa-download" in c.split()
            ):
                href = link.get("href")
                if href:
                    found_link_href = href
                    break

        if found_link_href:
            # Make the URL absolute if it's relative
            absolute_link = urljoin(SUBSRO_BASE_URL, found_link_href)
            if absolute_link not in processed_links:
                logging.debug(f"Found download link: {absolute_link}")
                download_links.append(absolute_link)
                processed_links.add(absolute_link)
        else:
            img_alt = img_tag.get("alt", "N/A")
            logging.warning(
                f"Found subtitle entry ('{img_alt}') but couldn't locate download link within its grid."
            )

    return download_links


# --- Public Interface Functions ---


def find_subtitle_download_urls(imdb_id, language_code="ro"):
    """
    Finds subtitle download URLs on Subs.ro for a given IMDb ID and language.

    Args:
        imdb_id (str): The IMDb ID (e.g., 'tt1234567').
        language_code (str): The 2-letter language code ('ro' or 'en'). Defaults to 'ro'.

    Returns:
        list: A list of absolute download URLs found, or an empty list if none found or error.
    """
    page_url = _get_subtitle_page_url(imdb_id)
    if not page_url:
        return []  # Error already logged

    logging.info(f"Searching Subs.ro for '{language_code.upper()}' URLs (IMDb: {imdb_id})")

    soup = _fetch_and_parse_page(page_url)
    if not soup:
        logging.info(
            f"Subs.ro: No subtitle page found for IMDb ID {imdb_id} (page may not exist yet)."
        )
        return []

    download_urls = _extract_download_links(soup, language_code)

    if download_urls:
        logging.info(
            f"Found {len(download_urls)} potential '{language_code.upper()}' subtitle download URLs on Subs.ro for {imdb_id}."
        )
    else:
        logging.info(
            f"No '{language_code.upper()}' subtitle download URLs found on Subs.ro for {imdb_id}."
        )

    return download_urls


def download_subtitle_archive(download_url, output_dir, filename_prefix="subsro_archive"):  # noqa: C901
    """
    Downloads a subtitle archive file from a given URL.

    Args:
        download_url (str): The absolute URL to the subtitle archive (zip/rar).
        output_dir (str): The directory where the downloaded archive should be saved.
        filename_prefix (str): A prefix to use for the saved file name.

    Returns:
        str or None: The full path to the downloaded archive file if successful, None otherwise.
    """
    if not download_url:
        logging.error("Cannot download archive: download_url is empty.")
        return None

    logging.info(f"Attempting to download archive from Subs.ro: {download_url[:100]}...")

    response = make_request(
        network_session, "GET", download_url, stream=True, timeout=60
    )  # Increase timeout

    if response:
        try:
            # Attempt to get filename from Content-Disposition header first
            content_disp = response.headers.get("Content-Disposition")
            base_filename = None
            if content_disp:
                disp_match = re.search(r'filename="?([^"]+)"?', content_disp)
                if disp_match:
                    base_filename = disp_match.group(1)
                    logging.debug(f"Using filename from Content-Disposition: {base_filename}")

            # Fallback to URL path
            if not base_filename:
                parsed_url = urlparse(download_url)
                url_path = parsed_url.path
                if url_path:
                    base_filename = Path(url_path).name
                    logging.debug(f"Using filename from URL path: {base_filename}")

            # Final fallback if still no filename
            if not base_filename or "." not in base_filename:
                timestamp = int(time.time())
                random_id = random.randint(1000, 9999)
                content_type = response.headers.get("Content-Type", "").lower()
                guessed_ext = ".zip"
                if "rar" in content_type:
                    guessed_ext = ".rar"
                elif "zip" in content_type:
                    guessed_ext = ".zip"
                base_filename = f"{filename_prefix}_{timestamp}_{random_id}{guessed_ext}"
                logging.warning(
                    f"Could not determine filename, using generated name: {base_filename}"
                )

            # Sanitize prefix and filename
            safe_prefix = "".join(
                c for c in filename_prefix if c.isalnum() or c in ("_", "-")
            ).rstrip()
            safe_basefilename = (
                "".join(c for c in base_filename if c.isalnum() or c in ("._- "))
                .replace("/", "_")
                .replace("\\", "_")
            )
            max_len = 200
            if len(safe_basefilename) > max_len:
                name_part = Path(safe_basefilename).stem
                ext_part = Path(safe_basefilename).suffix
                safe_basefilename = name_part[: max_len - len(ext_part) - 1] + ext_part

            output_filename = f"{safe_prefix}_{safe_basefilename}"
            output_path = str(Path(output_dir) / output_filename)

            Path(output_dir).mkdir(parents=True, exist_ok=True)

            # Download content
            downloaded_size = 0
            with Path(output_path).open("wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
            if downloaded_size == 0:
                logging.warning(f"Downloaded file appears empty: {output_path}")

            logging.info(
                f"Successfully downloaded archive ({downloaded_size} bytes) to: {output_path}"
            )
            return output_path

        except OSError as e:
            logging.error(f"Failed to write downloaded archive to {output_path}: {e}")
            return None
        except Exception as e:
            logging.error(
                f"An unexpected error occurred during archive download/saving: {e}", exc_info=True
            )
            if "output_path" in locals() and Path(output_path).exists():
                try:
                    Path(output_path).unlink()
                except OSError:
                    pass
            return None
    else:
        logging.error(f"Failed to download archive from {download_url}.")
        return None


# --- Explicit Exports ---
__all__ = [
    "download_subtitle_archive",  # Export the download function used by the processor
    "find_subtitle_download_urls",  # Export the function finding URLs
]
