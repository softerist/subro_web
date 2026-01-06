import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add backend directory to path so we can import app modules
project_root = Path(__file__).resolve().parents[2]
load_dotenv(project_root / ".env")
sys.path.append(str(project_root))

import httpx  # noqa: E402

from app.core.config import settings  # noqa: E402

default_url = (
    f"http://{settings.SERVER_HOST}:{settings.SERVER_PORT}{settings.API_V1_STR}/auth/login"
)
API_URL = os.getenv("TEST_API_URL", default_url)


async def test_limit():
    async with httpx.AsyncClient() as client:
        print(f"Testing Login Rate Limit against {API_URL} (Limit: 5/min)")
        hit_limit = False
        test_email = os.getenv("FIRST_SUPERUSER_EMAIL")
        test_password = os.getenv("FIRST_SUPERUSER_PASSWORD")
        if not test_email or not test_password:
            print(
                "Set FIRST_SUPERUSER_EMAIL and FIRST_SUPERUSER_PASSWORD in your environment before running."
            )
            sys.exit(1)
        for i in range(1, 10):
            try:
                # Login requires form data
                data = {"username": test_email, "password": test_password}
                resp = await client.post(API_URL, data=data)
                print(f"   Request {i}: Status {resp.status_code}")
                if resp.status_code == 429:
                    print("   [SUCCESS] Rate limit 429 triggered.")
                    hit_limit = True
                    break
            except Exception as e:
                print(f"   Request {i}: Failed with error {e}")

        if not hit_limit:
            print("   [FAILURE] Rate limit was NOT triggered after 9 attempts.")
            sys.exit(1)
        else:
            print("   Test Passed.")


if __name__ == "__main__":
    try:
        asyncio.run(test_limit())
    except KeyboardInterrupt:
        pass
