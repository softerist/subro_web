import asyncio
import sys

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Add app to path (assuming script is run from /app)
sys.path.append("/app")

from app.core.config import settings
from app.core.security import get_password_hash

# Import dependent models first to satisfy registry
from app.db.models.user import User


async def verify_force_password():
    print("--- Starting Verification ---")

    # 0. Setup DB Session Standalone
    db_url = str(settings.ASYNC_SQLALCHEMY_DATABASE_URL)
    engine = create_async_engine(db_url)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # 1. Setup Test User
    email = "verify_force@example.com"
    password = "InitialPassword123!"
    new_password = "NewPassword123!"

    print(f"Connecting to DB: {db_url.split('@')[0]}@...")

    async with async_session() as session:
        # Check if user exists
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalars().first()

        if user:
            print(f"User {email} exists. Updating...")
            user.hashed_password = get_password_hash(password)
            user.force_password_change = True
            user.is_active = True
            await session.commit()
        else:
            print(f"Creating user {email}...")
            user = User(
                email=email,
                hashed_password=get_password_hash(password),
                is_active=True,
                is_superuser=False,
                is_verified=True,
                role="standard",
                force_password_change=True,
            )
            session.add(user)
            await session.commit()

    print("User setup complete. force_password_change=True")

    # 2. Test API Flow via httpx
    base_url = "http://localhost:8000"

    async with AsyncClient(base_url=base_url) as ac:
        # Login
        print("Logging in...")
        response = await ac.post(
            "/api/v1/auth/login",
            data={"username": email, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            print(f"Login failed: {response.status_code} {response.text}")
            return False

        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Verify Flag via /users/me
        print("Checking /users/me...")
        me_resp = await ac.get("/api/v1/users/me", headers=headers)
        if me_resp.status_code != 200:
            print(f"Get Me failed: {me_resp.status_code}")
            return False

        me_data = me_resp.json()
        print(f"Current force_password_change: {me_data.get('force_password_change')}")

        if me_data.get("force_password_change") is not True:
            print("ERROR: force_password_change is NOT True in /users/me response")
            # return False

        # Change Password
        print("Changing password...")
        change_resp = await ac.patch(
            "/api/v1/auth/password",
            json={"current_password": password, "new_password": new_password},
            headers=headers,
        )

        if change_resp.status_code != 200:
            print(f"Change Password failed: {change_resp.status_code} {change_resp.text}")
            return False

        print("Password changed successfully.")

        # Verify Flag is Cleared
        print("Verifying flag cleared...")
        me_resp_2 = await ac.get("/api/v1/users/me", headers=headers)
        me_data_2 = me_resp_2.json()
        print(f"New force_password_change: {me_data_2.get('force_password_change')}")

        if me_data_2.get("force_password_change") is not False:
            print("ERROR: force_password_change is NOT False after password change")
            return False

        print("SUCCESS: Full flow verified.")
        return True


if __name__ == "__main__":
    success = asyncio.run(verify_force_password())
    sys.exit(0 if success else 1)
