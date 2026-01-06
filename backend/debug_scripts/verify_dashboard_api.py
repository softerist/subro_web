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

API_BASE_URL = f"http://{settings.SERVER_HOST}:{settings.SERVER_PORT}{settings.API_V1_STR}"
EMAIL = os.getenv("TEST_USER_EMAIL") or os.getenv("FIRST_SUPERUSER_EMAIL")
PASSWORD = os.getenv("TEST_USER_PASSWORD") or os.getenv("FIRST_SUPERUSER_PASSWORD")


async def main():
    print(">>> Verifying Dashboard API")
    if not EMAIL or not PASSWORD:
        print(
            "Set TEST_USER_EMAIL/TEST_USER_PASSWORD or FIRST_SUPERUSER_EMAIL/FIRST_SUPERUSER_PASSWORD."
        )
        sys.exit(1)
    async with httpx.AsyncClient() as client:
        # 1. Login
        resp = await client.post(
            f"{API_BASE_URL}/auth/login", data={"username": EMAIL, "password": PASSWORD}
        )
        if resp.status_code != 200:
            print(f"Login failed: {resp.text}")
            sys.exit(1)
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("1. Login Successful")

        # 2. Create Tile
        tile_data = {
            "title": "Test Tile",
            "url": "https://example.com",
            "icon": "Frame",
            "order_index": 0,
        }
        resp = await client.post(f"{API_BASE_URL}/dashboard/tiles", json=tile_data, headers=headers)
        if resp.status_code != 201:
            print(f"Create Tile failed: {resp.text}")
            sys.exit(1)
        tile_id = resp.json()["id"]
        print(f"2. Created Tile: {tile_id}")

        # 3. List Tiles (Admin)
        resp = await client.get(f"{API_BASE_URL}/dashboard/admin/tiles", headers=headers)
        if resp.status_code != 200:
            print(f"List Tiles failed: {resp.text}")
            sys.exit(1)
        tiles = resp.json()
        print(f"3. Listed {len(tiles)} tiles")

        # 4. Check Public Endpoint
        resp = await client.get(f"{API_BASE_URL}/dashboard/tiles", headers=headers)
        if resp.status_code != 200:
            print(f"Public List Tiles failed: {resp.text}")
        print("4. Public Endpoint OK")

        # 5. Delete Tile
        resp = await client.delete(f"{API_BASE_URL}/dashboard/tiles/{tile_id}", headers=headers)
        if resp.status_code != 204:
            print(f"Delete Tile failed: {resp.text}")
            sys.exit(1)
        print("5. Deleted Tile")

    print(">>> Dashboard API Verification COMPLETE")


if __name__ == "__main__":
    asyncio.run(main())
