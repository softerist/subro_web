"""
Integration tests for WebSocket log streaming.

This test uses the running API container and creates test data via API endpoints
to avoid pytest-asyncio event loop conflicts.
"""

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest
import websockets
from redis.asyncio import Redis

# Fix for websockets 15.0+ - correct exception
from websockets.exceptions import InvalidStatus

from app.core.config import settings

# API base URL (running container)
API_BASE_URL = "http://localhost:8000"
WS_BASE_URL = "ws://localhost:8000"


class TestWebSocketLogStreaming:
    """Test suite for WebSocket log streaming functionality."""

    def _is_path_allowed(self, folder_path: Path, allowed_paths: list[str]) -> bool:
        try:
            resolved_target = folder_path.resolve(strict=True)
        except FileNotFoundError:
            return False

        for allowed_base in allowed_paths:
            try:
                resolved_allowed = Path(allowed_base).resolve(strict=True)
            except (FileNotFoundError, RuntimeError, OSError):
                continue

            if resolved_target == resolved_allowed or resolved_allowed in resolved_target.parents:
                return True
        return False

    async def _login_with_retry(self, client, email, password, max_attempts=2):
        for attempt in range(1, max_attempts + 1):
            login_response = await client.post(
                "/api/v1/auth/login",
                data={"username": email, "password": password},
            )
            if login_response.status_code == 200:
                return login_response
            if login_response.status_code == 429 and attempt < max_attempts:
                retry_after = login_response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 60.0
                print(f"   ⚠️  Rate limited for {email}. Retrying in {delay:.0f}s...")
                await asyncio.sleep(delay)
                continue
            return login_response

    def _setup_test_folder(self, test_id):
        """Helper to find a valid test folder location."""
        # Try multiple possible folder locations
        possible_bases = [
            "/tmp",  # Standard shared location from docker-compose
            "/mnt/sata0/Media",  # Your media mount from docker-compose
            os.getenv("TEST_FOLDER_BASE", "/tmp"),  # From environment
        ]

        for base in possible_bases:
            if not base:
                continue

            # Fix PTH103: Use Path object
            path = Path(base) / f"test_{test_id}"
            try:
                path.mkdir(parents=True, exist_ok=True)
                print(f"\n0. Created test folder: {path}")
                return path
            except Exception as e:
                print(f"   ⚠️  Cannot create folder in {base}: {e}")
                continue

        pytest.skip(
            f"Cannot create test folder in any of: {possible_bases}. "
            "Ensure /tmp is mounted in docker-compose.yml"
        )

    async def _register_and_login(self, client, email, password):
        """Helper to register and login a user."""
        # Step 1: Register
        print(f"1. Registering test user: {email}")
        register_response = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )

        if register_response.status_code not in [200, 201]:
            pytest.fail(f"Failed to register user: {register_response.text}")

        user_id = register_response.json()["id"]
        print(f"   ✅ User registered: {user_id}")

        # Step 2: Login
        print("2. Logging in to get JWT token")
        login_response = await self._login_with_retry(client, email, password)

        if login_response.status_code != 200:
            pytest.fail(f"Failed to login: {login_response.text}")

        token = login_response.json()["access_token"]
        print(f"   ✅ Login successful, got token: {token[:30]}...")
        return token

    async def _ensure_path_allowed(self, client, folder_path: Path, user_token: str | None) -> None:
        """Ensure the test folder is in allowed storage paths (admin-only)."""
        if user_token:
            allowed_response = await client.get(
                "/api/v1/jobs/allowed-folders",
                headers={"Authorization": f"Bearer {user_token}"},
            )
            if allowed_response.status_code == 200 and self._is_path_allowed(
                folder_path, allowed_response.json()
            ):
                return

        admin_email = settings.FIRST_SUPERUSER_EMAIL
        admin_password = settings.FIRST_SUPERUSER_PASSWORD
        if not admin_email or not admin_password:
            pytest.skip("Admin credentials not configured for storage path setup.")

        login_response = await self._login_with_retry(client, admin_email, admin_password)
        if login_response.status_code != 200:
            setup_response = await client.post(
                "/api/v1/setup/complete",
                json={"admin_email": admin_email, "admin_password": admin_password},
            )
            if setup_response.status_code not in (200, 201, 403, 409):
                pytest.fail(f"Failed to run setup for admin user: {setup_response.text}")

            login_response = await self._login_with_retry(client, admin_email, admin_password)
            if login_response.status_code != 200:
                pytest.fail(f"Failed to login as admin: {login_response.text}")

        admin_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {admin_token}"}
        payload = {"path": str(folder_path), "label": "Test Path"}
        response = await client.post("/api/v1/storage-paths/", json=payload, headers=headers)
        if response.status_code in (200, 201):
            return
        if response.status_code == 400 and "already exists" in response.text:
            return
        pytest.fail(f"Failed to allow test path: {response.text}")

    async def _create_test_job(self, client, token, folder_path):
        """Helper to create a job via API."""
        print("3. Creating test job")
        headers = {"Authorization": f"Bearer {token}"}

        await self._ensure_path_allowed(client, folder_path, token)

        # Verify folder accessibility via health check
        # Fix RUF001: Replaced ambiguous 'i' with '[INFO]'
        health_response = await client.get("/health", headers=headers)
        print(f"   [INFO] API health check: {health_response.status_code}")

        job_response = await client.post(
            "/api/v1/jobs/",
            json={"folder_path": str(folder_path), "additional_params": {}},
            headers=headers,
        )

        if job_response.status_code not in [200, 201]:
            error_msg = job_response.json().get("detail", job_response.text)
            print(f"   ❌ Job creation failed: {error_msg}")

            if "does not exist" in error_msg or "is not within" in error_msg:
                # Fix PTH110: Use Path.exists()
                print("\n   🔍 Debug Info:")
                print(f"   - Test folder created: {folder_path}")
                print(f"   - Folder exists on host: {folder_path.exists()}")
                print(f"   - ALLOWED_FOLDERS env: {os.getenv('ALLOWED_FOLDERS', 'not set')}")

                pytest.skip(
                    f"Folder {folder_path} not accepted by API container.\n"
                    f"Error: {error_msg}\n"
                    "Potential Fixes:\n"
                    "1. Update ALLOWED_FOLDERS=['/tmp'] in docker-compose.yml\n"
                    "2. Restart containers to apply changes"
                )
            pytest.fail(f"Failed to create job: {error_msg}")

        job_id = job_response.json()["id"]
        print(f"   ✅ Job created: {job_id}")
        return job_id

    async def _publish_test_logs(self, job_id):
        """Publishes test log messages to Redis channel."""
        await asyncio.sleep(1.5)  # Give WebSocket time to connect

        redis_url = str(settings.REDIS_PUBSUB_URL)
        if Path("/.dockerenv").exists():
            parsed = urlparse(redis_url)
            if parsed.hostname in {"localhost", "127.0.0.1"}:
                redis_url = redis_url.replace(parsed.hostname, "redis", 1)
        redis = Redis.from_url(redis_url)
        channel = f"job:{job_id}:logs"

        messages = [
            {
                "type": "status",
                "payload": {"status": "RUNNING", "ts": "2024-01-01T12:00:01Z"},
            },
            {
                "type": "log",
                "payload": {
                    "stream": "stdout",
                    "message": "Processing video files...",
                    "ts": "2024-01-01T12:00:02Z",
                },
            },
            {
                "type": "log",
                "payload": {
                    "stream": "stdout",
                    "message": "Downloading subtitles...",
                    "ts": "2024-01-01T12:00:03Z",
                },
            },
            {
                "type": "status",
                "payload": {
                    "status": "SUCCEEDED",
                    "exit_code": 0,
                    "ts": "2024-01-01T12:00:05Z",
                },
            },
        ]

        print("   📤 Publishing messages to Redis...")
        for msg in messages:
            await redis.publish(channel, json.dumps(msg))
            await asyncio.sleep(0.2)

        await redis.aclose()
        print("   ✅ All messages published")

    async def _cleanup_test_data(self, job_id, token, folder_path):
        """Helper to clean up API data and local folders."""
        print("\n5. Cleaning up test data...")

        # API Cleanup
        if job_id and token:
            try:
                async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=5.0) as client:
                    headers = {"Authorization": f"Bearer {token}"}
                    await client.delete(f"/api/v1/jobs/{job_id}", headers=headers)
                    print(f"   ✅ Deleted job: {job_id}")
            except Exception as e:
                print(f"   ⚠️  Failed to delete job: {e}")

        # Folder Cleanup
        # Fix PTH110: Use Path.exists()
        if folder_path and folder_path.exists():
            try:
                # Fix PTH106: Use Path.rmdir()
                folder_path.rmdir()
                print(f"   ✅ Deleted test folder: {folder_path}")
            except Exception as e:
                print(f"   ⚠️  Failed to delete test folder: {e}")

    @pytest.mark.asyncio
    async def test_websocket_log_streaming_flow(self):
        """
        Integration test for Real-time Log Streaming.
        """
        # Generate unique test data
        test_id = str(uuid.uuid4())[:8]
        test_email = f"wstest_{test_id}@example.com"
        test_password = "TestPass123!"

        # Step 0: Create folder
        test_folder = self._setup_test_folder(test_id)

        job_id = None
        user_token = None

        try:
            async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=10.0) as client:
                # Step 1 & 2: Register and Login
                user_token = await self._register_and_login(client, test_email, test_password)

                # Step 3: Create Job
                job_id = await self._create_test_job(client, user_token, test_folder)

            # Step 4: Setup WebSocket and Publisher
            print("4. Testing WebSocket connection")
            ws_url = f"{WS_BASE_URL}/api/v1/ws/jobs/{job_id}/logs?token={user_token}"

            publisher_task = asyncio.create_task(self._publish_test_logs(job_id))

            # Step 5: Connect and Verify
            async with websockets.connect(ws_url) as websocket:
                print("   ✅ WebSocket connected")

                # Receive system message
                data = json.loads(await websocket.recv())
                assert data["type"] == "system"
                print("   ✅ Received system message")

                # Receive RUNNING status
                data = json.loads(await websocket.recv())
                assert data["type"] == "status"
                assert data["payload"]["status"] == "RUNNING"
                print("   ✅ Received RUNNING status")

                # Receive logs and final status (ignore other message types like "info")
                log_messages = []
                succeeded = False
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and (len(log_messages) < 2 or not succeeded):
                    data = json.loads(await asyncio.wait_for(websocket.recv(), timeout=5))
                    msg_type = data.get("type")
                    if msg_type == "log":
                        log_messages.append(data.get("payload", {}).get("message", ""))
                    elif (
                        msg_type == "status"
                        and data.get("payload", {}).get("status") == "SUCCEEDED"
                    ):
                        succeeded = True

                assert any("Processing video" in message for message in log_messages)
                assert any("Downloading subtitles" in message for message in log_messages)
                assert succeeded
                print("   ✅ Received SUCCEEDED status")

            await publisher_task
            print("✅ Test completed successfully!")

        finally:
            await self._cleanup_test_data(job_id, user_token, test_folder)

    @pytest.mark.asyncio
    async def test_websocket_auth_failure(self):
        """Test that WebSocket connection is rejected with invalid token."""

        job_id = uuid.uuid4()
        ws_url = f"{WS_BASE_URL}/api/v1/ws/jobs/{job_id}/logs?token=INVALID_TOKEN"

        with pytest.raises(InvalidStatus) as exc_info:
            async with websockets.connect(ws_url):
                pass

        assert exc_info.value.response.status_code in [500, 403, 401]
        print(f"✅ Auth failure test passed (status: {exc_info.value.response.status_code})")
