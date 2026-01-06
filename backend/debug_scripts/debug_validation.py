import asyncio
import logging
import os

import httpx

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test credentials are read from the environment.
TMDB_KEY = os.getenv("TMDB_API_KEY")
OMDB_KEY = os.getenv("OMDB_API_KEY")
OS_KEY = os.getenv("OPENSUBTITLES_API_KEY")
OS_USER = os.getenv("OPENSUBTITLES_USERNAME")
OS_PASS = os.getenv("OPENSUBTITLES_PASSWORD")


async def _validate_tmdb(api_key: str) -> bool:
    """Validate TMDB API key by making a test request."""
    if not api_key or not api_key.strip():
        return False

    api_key = api_key.strip()
    url = f"https://api.themoviedb.org/3/configuration?api_key={api_key}"

    logger.info(f"Testing TMDB Key: {api_key[:5]}...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=10.0)
            logger.info(f"TMDB Response Status: {response.status_code}")
            logger.info(f"TMDB Response Body: {response.text[:100]}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"TMDB validation error: {e}")
            return False


async def _validate_omdb(api_key: str) -> bool:
    """Validate OMDB API key by making a test request."""
    if not api_key or not api_key.strip():
        return False

    api_key = api_key.strip()
    # Use a simple test query
    url = f"http://www.omdbapi.com/?apikey={api_key}&t=test"

    logger.info(f"Testing OMDB Key: {api_key[:5]}...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=10.0)
            logger.info(f"OMDB Response Status: {response.status_code}")
            logger.info(f"OMDB Response Body: {response.text[:100]}")

            if response.status_code == 200:
                data = response.json()
                return data.get("Response") != "False" or "Invalid API" not in data.get("Error", "")
            return False
        except Exception as e:
            logger.error(f"OMDB validation error: {e}")
            return False


async def _validate_opensubtitles(api_key: str, username: str, password: str) -> bool:
    """Validate OpenSubtitles credentials by attempting login."""
    if not all([api_key, username, password]):
        logger.error("Missing OpenSubtitles credentials")
        return False

    api_key = api_key.strip()
    username = username.strip()
    password = password.strip()

    login_url = "https://api.opensubtitles.com/api/v1/login"

    headers = {
        "Api-Key": api_key,
        "Content-Type": "application/json",
        "User-Agent": "SubtitleDownloader v1.0",
    }
    payload = {"username": username, "password": password}

    logger.info(f"Testing OpenSubtitles Login. Key: {api_key[:5]}..., User: {username}")

    async with httpx.AsyncClient() as client:
        try:
            # Attempt login
            response = await client.post(login_url, headers=headers, json=payload, timeout=10.0)
            logger.info(f"OpenSubtitles Response Status: {response.status_code}")
            logger.info(f"OpenSubtitles Response Body: {response.text[:200]}")

            if response.status_code == 200:
                data = response.json()
                token = data.get("token")
                return bool(token)

            return False
        except Exception as e:
            logger.error(f"OpenSubtitles validation error: {e}")
            return False


async def main():
    print("--- Starting Validation Debug ---")

    print("\n1. TMDB Validation:")
    if TMDB_KEY:
        tmdb_valid = await _validate_tmdb(TMDB_KEY)
        print(f"TMDB Valid: {tmdb_valid}")
    else:
        print("TMDB_API_KEY not set; skipping TMDB validation.")

    print("\n2. OMDB Validation:")
    if OMDB_KEY:
        omdb_valid = await _validate_omdb(OMDB_KEY)
        print(f"OMDB Valid: {omdb_valid}")
    else:
        print("OMDB_API_KEY not set; skipping OMDB validation.")

    print("\n3. OpenSubtitles Validation:")
    if OS_KEY and OS_USER and OS_PASS:
        os_valid = await _validate_opensubtitles(OS_KEY, OS_USER, OS_PASS)
        print(f"OpenSubtitles Valid: {os_valid}")
    else:
        print(
            "OPENSUBTITLES_API_KEY/OPENSUBTITLES_USERNAME/OPENSUBTITLES_PASSWORD not set; "
            "skipping OpenSubtitles validation."
        )


if __name__ == "__main__":
    asyncio.run(main())
