import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

# Add backend directory to path so we can import app modules
project_root = Path(__file__).resolve().parents[2]
load_dotenv(project_root / ".env")

import httpx  # noqa: E402

from app.core.config import settings  # noqa: E402

API_URL = f"http://{settings.SERVER_HOST}:{settings.SERVER_PORT}{settings.API_V1_STR}/auth/login"


async def check_cookies():
    async with httpx.AsyncClient() as client:
        print(f"Checking Cookies from {API_URL}...")
        try:
            email = os.getenv("TEST_USER_EMAIL") or os.getenv("FIRST_SUPERUSER_EMAIL")
            password = os.getenv("TEST_USER_PASSWORD") or os.getenv(
                "FIRST_SUPERUSER_PASSWORD"
            )
            if not email or not password:
                raise RuntimeError(
                    "Set TEST_USER_EMAIL/TEST_USER_PASSWORD or FIRST_SUPERUSER_EMAIL/FIRST_SUPERUSER_PASSWORD."
                )
            data = {"username": email, "password": password}
            resp = await client.post(API_URL, data=data)

            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.text}")
            cookies = resp.headers.get_list("set-cookie")

            if not cookies:
                print("No Set-Cookie headers found!")
                exit(1)

            for cookie in cookies:
                print(f"Cookie: {cookie}")
                if "refresh_token" in cookie:
                    print("   -> Found refresh_token")
                    if "HttpOnly" in cookie:
                        print("   -> [PASS] HttpOnly is present")
                    else:
                        print("   -> [FAIL] HttpOnly is MISSING")

                    if "SameSite=strict" in cookie or "SameSite=Strict" in cookie:
                        print("   -> [PASS] SameSite=Strict is present")
                    else:
                        print(f"   -> [FAIL] SameSite is not Strict (Got: {cookie})")

                    if "Secure" in cookie:
                        print("   -> [PASS] Secure is present")
                    else:
                        print(
                            "   -> [INFO] Secure is MISSING (Expected if COOKIE_SECURE=False in .env)"
                        )
        except Exception as e:
            print(f"Failed: {e}")


if __name__ == "__main__":
    asyncio.run(check_cookies())
