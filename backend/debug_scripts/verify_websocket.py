"""
Standalone verification of WebSocket log streaming functionality.
This bypasses pytest to verify the WebSocket endpoint works correctly.
"""

import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import websockets
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.models.job import Job, JobStatus
from app.db.models.user import User


def create_test_token(user_id: str, email: str) -> str:
    """Create a valid JWT access token."""
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),
        "email": email,
        "aud": ["fastapi-users:auth"],
        "exp": expire,
        "iat": now,
        "nbf": now,
    }

    return jwt.encode(payload, str(settings.SECRET_KEY), algorithm=settings.ALGORITHM)


async def main():
    print("=" * 70)
    print("WEBSOCKET LOG STREAMING VERIFICATION")
    print("=" * 70)
    print()

    # Connect to test database
    print("1. Connecting to test database...")
    engine = create_async_engine(
        "postgresql+asyncpg://admin:Pa44w0rd@localhost:5433/subappdb", echo=False
    )

    # Create session
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session:
        print("   ✅ Database connection successful")

        # Create test user and job
        print("\n2. Creating test user and job...")
        user_id = uuid.uuid4()
        user_email = f"ws_verify_{user_id}@example.com"
        user = User(
            id=user_id,
            email=user_email,
            hashed_password="test_hash",
            is_active=True,
            is_verified=True,
            role="standard",
        )
        session.add(user)

        job_id = uuid.uuid4()
        job = Job(
            id=job_id,
            user_id=user_id,
            folder_path="/tmp/verify_test",
            status=JobStatus.PENDING,
            celery_task_id=str(job_id),
        )
        session.add(job)
        await session.commit()
        print(f"   ✅ Created user: {user_email}")
        print(f"   ✅ Created job: {job_id}")

        # Create JWT token
        access_token = create_test_token(str(user_id), user_email)
        print(f"\n3. Created JWT token: {access_token[:30]}...")

        # Define publisher function
        async def publish_test_logs():
            """Publishes test log messages to Redis."""
            await asyncio.sleep(1.0)  # Wait for WS to connect

            redis = Redis.from_url(str(settings.REDIS_PUBSUB_URL))
            channel = f"job:{job_id}:logs"

            # Publish messages
            messages = [
                {"type": "status", "payload": {"status": "RUNNING", "ts": "2024-01-01T12:00:00Z"}},
                {
                    "type": "log",
                    "payload": {
                        "stream": "stdout",
                        "message": "Test log message",
                        "ts": "2024-01-01T12:00:01Z",
                    },
                },
                {
                    "type": "status",
                    "payload": {
                        "status": "SUCCEEDED",
                        "exit_code": 0,
                        "ts": "2024-01-01T12:00:02Z",
                    },
                },
            ]

            for msg in messages:
                await redis.publish(channel, json.dumps(msg))
                await asyncio.sleep(0.1)

            await redis.aclose()
            print("   📤 Published all test messages to Redis")

        # Test WebSocket connection
        print("\n4. Testing WebSocket connection to http://localhost:8000...")
        ws_url = f"ws://localhost:8000/api/v1/ws/jobs/{job_id}/logs?token={access_token}"

        try:
            # Start publisher task
            publisher = asyncio.create_task(publish_test_logs())

            # Connect to WebSocket
            async with websockets.connect(ws_url) as websocket:
                print("   ✅ WebSocket connected successfully")

                # Receive system message
                data = json.loads(await websocket.recv())
                assert data["type"] == "system", f"Expected system message, got {data}"
                print("   ✅ Received system message")

                # Receive RUNNING status
                data = json.loads(await websocket.recv())
                assert data["type"] == "status" and data["payload"]["status"] == "RUNNING"
                print("   ✅ Received RUNNING status")

                # Receive log message
                data = json.loads(await websocket.recv())
                assert data["type"] == "log"
                print(f"   ✅ Received log: {data['payload']['message']}")

                # Receive SUCCEEDED status
                data = json.loads(await websocket.recv())
                assert data["type"] == "status" and data["payload"]["status"] == "SUCCEEDED"
                print("   ✅ Received SUCCEEDED status")

            # Wait for publisher
            await publisher

        except Exception as e:
            print(f"   ❌ WebSocket test failed: {e}")
            await engine.dispose()
            return False

    await engine.dispose()

    print()
    print("=" * 70)
    print("✅ ALL TESTS PASSED!")
    print(" WebSocket log streaming is working correctly!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
