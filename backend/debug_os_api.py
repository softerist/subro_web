import asyncio
import logging

import httpx

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test Credentials provided by user (Correct)
OS_KEY = "a4zU1bWcOiK6yNVKpK1xP0OdAvyZs6eY"
OS_USER = "softerist"
OS_PASS = "codein"


async def test_key(api_key, scenario):
    print(f"\n--- Testing Key Check: {scenario} ---")
    url = "https://api.opensubtitles.com/api/v1/formats"
    headers = {
        "Api-Key": api_key,
        "User-Agent": "SubtitleDownloader v1.0",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            print(f"Key Check Status: {response.status_code}")
            print(f"Key Check Body: {response.text}")
        except Exception as e:
            print(f"Key Check Error: {e}")


async def test_login(api_key, username, password, scenario):
    print(f"\n--- Testing Login: {scenario} ---")
    login_url = "https://api.opensubtitles.com/api/v1/login"

    headers = {
        "Api-Key": api_key,
        "Content-Type": "application/json",
        "User-Agent": "SubtitleDownloader v1.0",
    }
    payload = {"username": username, "password": password}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(login_url, headers=headers, json=payload, timeout=10.0)
            print(f"Login Status: {response.status_code}")
            print(f"Login Message: {response.json().get('message')}")
        except Exception as e:
            print(f"Login Error: {e}")


async def main():
    # 1. Test Key Validation (GET /formats)
    await test_key(OS_KEY, "Valid Key")
    await asyncio.sleep(2)
    await test_key("bad_key_12345", "Bad Key")

    await asyncio.sleep(2)

    # 2. Test Login (Bad Key)
    await test_login("bad_key_12345", OS_USER, OS_PASS, "Bad Key, Good Creds")


if __name__ == "__main__":
    asyncio.run(main())
