"""
Verification script to test that Redis and PostgreSQL are accessible from localhost.
This verifies the infrastructure fixes for the integration tests.
"""

import asyncio
import sys
from pathlib import Path

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def test_redis_connection():
    """Test Redis connection on localhost:6379"""
    print("Testing Redis connection on localhost:6379...")
    try:
        redis = Redis.from_url("redis://localhost:6379/2", encoding="utf-8", decode_responses=True)
        await redis.ping()

        # Test pub/sub
        await redis.set("test_key", "test_value")
        value = await redis.get("test_key")
        await redis.delete("test_key")

        await redis.close()
        print("✅ Redis connection successful!")
        print("   - Ping: OK")
        print(f"   - Set/Get: OK (value: {value})")
        return True
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False


async def test_postgres_connection():
    """Test PostgreSQL connection on localhost:5433"""
    print("\nTesting PostgreSQL connection on localhost:5433...")
    try:
        engine = create_async_engine(
            "postgresql+asyncpg://admin:Pa44w0rd@localhost:5433/subappdb", echo=False
        )

        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1 as test"))
            row = result.fetchone()

        await engine.dispose()
        print("✅ PostgreSQL connection successful!")
        print(f"   - Query result: {row[0]}")
        return True
    except Exception as e:
        print(f"❌ PostgreSQL connection failed: {e}")
        return False


def verify_env_test_config():
    """
    Verify .env.test file exists and has correct values.
    Made synchronous to avoid ASYNC101 (blocking I/O in async function).
    """
    print("\nVerifying .env.test configuration...")
    try:
        # Fix PTH123: Use Path.read_text instead of open()
        content = Path(".env.test").read_text(encoding="utf-8")

        required_vars = [
            "REDIS_HOST=localhost",
            "REDIS_PORT=6379",
            "DATABASE_URL=postgresql+asyncpg://admin:Pa44w0rd@localhost:5433/subappdb",
        ]

        all_present = all(var in content for var in required_vars)

        if all_present:
            print("✅ .env.test configuration correct!")
            print("   - REDIS_HOST=localhost ✓")
            print("   - REDIS_PORT=6379 ✓")
            print("   - DATABASE_URL points to localhost:5433 ✓")
            return True
        else:
            print("❌ .env.test missing required configurations")
            return False
    except FileNotFoundError:
        print("❌ .env.test file not found")
        return False


async def main():
    print("=" * 60)
    print("INTEGRATION TEST INFRASTRUCTURE VERIFICATION")
    print("=" * 60)
    print()

    results = []

    # Test connections
    results.append(await test_redis_connection())
    results.append(await test_postgres_connection())

    # Run sync function directly (no await)
    results.append(verify_env_test_config())

    print()
    print("=" * 60)
    if all(results):
        print("✅ ALL VERIFICATIONS PASSED!")
        print("The original socket.gaierror is FIXED.")
        print("Tests can now connect to Redis and PostgreSQL.")
        sys.exit(0)
    else:
        print("❌ SOME VERIFICATIONS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
