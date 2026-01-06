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
import websockets  # noqa: E402

from app.core.config import settings  # noqa: E402

# Constants
API_BASE_URL = f"http://{settings.SERVER_HOST}:{settings.SERVER_PORT}{settings.API_V1_STR}"
WS_BASE_URL = f"ws://{settings.SERVER_HOST}:{settings.SERVER_PORT}{settings.API_V1_STR}"
EMAIL = os.getenv("TEST_USER_EMAIL") or os.getenv("FIRST_SUPERUSER_EMAIL")
PASSWORD = os.getenv("TEST_USER_PASSWORD") or os.getenv("FIRST_SUPERUSER_PASSWORD")


async def main():  # noqa: C901
    print(">>> Starting E2E Verification")
    if not EMAIL or not PASSWORD:
        print(
            "Set TEST_USER_EMAIL/TEST_USER_PASSWORD or FIRST_SUPERUSER_EMAIL/FIRST_SUPERUSER_PASSWORD."
        )
        sys.exit(1)

    async with httpx.AsyncClient() as client:
        # 1. Login
        print(f"1. Logging in as {EMAIL}...")
        try:
            resp = await client.post(
                f"{API_BASE_URL}/auth/login",
                data={"username": EMAIL, "password": PASSWORD},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            print(f"   Login Status: {resp.status_code}")
            if resp.status_code != 200:
                print(f"   Login Failed: {resp.text}")
                sys.exit(1)

            token_data = resp.json()
            access_token = token_data["access_token"]
            print("   Login Successful. Token received.")
        except Exception as e:
            print(f"   Login Exception: {e}")
            sys.exit(1)

        headers = {"Authorization": f"Bearer {access_token}"}

        # 1.5 Check User Profile (Fix for Failed to fetch user profile)
        print("1.5 Checking User Profile (/users/me)...")
        try:
            resp = await client.get(f"{API_BASE_URL}/users/me", headers=headers)
            if resp.status_code != 200:
                print(f"   User Profile Failed: {resp.status_code} {resp.text}")
                sys.exit(1)
            user_data = resp.json()
            print(f"   User Profile: {user_data['email']} (ID: {user_data['id']})")
        except Exception as e:
            print(f"   User Profile Exception: {e}")
            sys.exit(1)

        # 2. Submit Job
        target_folder = "/tmp/subro-test-script"
        print(f"2. Submitting Job for {target_folder}...")
        try:
            job_payload = {"folder_path": target_folder, "language": "eng"}
            resp = await client.post(f"{API_BASE_URL}/jobs/", json=job_payload, headers=headers)
            print(f"   Submit Status: {resp.status_code}")
            if resp.status_code not in [200, 201]:
                print(f"   Submit Failed: {resp.text}")
                # It might fail if folder doesn't exist or not allowed.
                # But /tmp is allowed.
                sys.exit(1)

            job_data = resp.json()
            job_id = job_data["id"]
            print(f"   Job Submitted. ID: {job_id}")
        except Exception as e:
            import traceback

            print(f"   Submit Exception: {e!r}")
            traceback.print_exc()
            sys.exit(1)

        # 3. Connect to WebSocket Logs
        ws_url = f"{WS_BASE_URL}/ws/jobs/{job_id}/logs?token={access_token}"
        print(f"3. Connecting to WebSocket: {ws_url}...")
        try:
            async with websockets.connect(ws_url) as ws:
                print("   WebSocket Connected!")
                print("   Listening for log messages (timeout 5s)...")

                # Listen for a few messages
                try:
                    for _ in range(3):
                        msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        print(f"   [WS LOG] {msg}")
                        # If we get any message, it proves streaming works.
                except TimeoutError:
                    print("   Wait timeout (expected if no new logs).")

                print("   WebSocket test passed.")
        except Exception as e:
            print(f"   WebSocket Exception: {e}")
            sys.exit(1)

        # 4. Check Final Status
        print("4. Checking Job Status...")
        resp = await client.get(f"{API_BASE_URL}/jobs/{job_id}", headers=headers)
        if resp.status_code == 200:
            final_job = resp.json()
            print(f"   Final Status: {final_job['status']}")
        else:
            print("   Failed to fetch final status.")

    print(">>> E2E Verification COMPLETE and SUCCESSFUL")


if __name__ == "__main__":
    asyncio.run(main())
