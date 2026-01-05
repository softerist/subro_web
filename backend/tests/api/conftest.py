import logging
from datetime import date

import pytest
from dateutil.relativedelta import relativedelta
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text

from app.core.users import current_active_user, get_current_active_admin_user
from app.db.models.user import User

logger = logging.getLogger(__name__)


@pytest.fixture
def audit_admin_headers():
    return {"Authorization": "Bearer admin-token"}


@pytest.fixture
def audit_user_headers():
    return {"Authorization": "Bearer user-token"}


@pytest.fixture(autouse=True)
async def create_test_partitions(db_session):
    # Manually create partitions for current and next month to avoid IntegrityError
    today = date.today()
    target_months = [today + relativedelta(months=i) for i in range(2)]

    for d in target_months:
        table_name = f"audit_logs_{d.strftime('%Y_%m')}"
        start_date = d.replace(day=1)
        next_month = start_date + relativedelta(months=1)

        sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name}
        PARTITION OF audit_logs
        FOR VALUES FROM ('{start_date}') TO ('{next_month}')
        """
        try:
            await db_session.execute(text(sql))
            await db_session.commit()
        except Exception as e:
            logger.error(f"Failed to create test partition {table_name}: {e}")
            await db_session.rollback()


@pytest.fixture(autouse=False)
def override_auth_dependencies():
    import uuid

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.security import current_active_user as security_active_user
    from app.db.session import get_async_session
    from app.main import app

    # Fixed IDs to match across suite
    admin_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")

    async def mock_active_user(request: Request, db: AsyncSession = Depends(get_async_session)):
        auth_header = request.headers.get("Authorization", "")
        if "admin" in auth_header:
            target_id = admin_id
            email = "admin@example.com"
            is_admin = True
            mfa = True
        elif "user" in auth_header:
            target_id = user_id
            email = "user@example.com"
            is_admin = False
            mfa = False
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

        # Unified fetch by email (logical identity)
        stmt = select(User).where(User.email == email)
        result = await db.execute(stmt)
        user = result.scalar()

        if not user:
            user = User(
                id=target_id,
                email=email,
                is_superuser=is_admin,
                role="admin" if is_admin else "standard",
                is_active=True,
                is_verified=True,
                mfa_enabled=mfa,
                hashed_password="mocked_password",
            )
            db.add(user)
            await db.flush()

        return user

    async def mock_active_admin(user: User = Depends(mock_active_user)):
        if user.role != "admin" and not user.is_superuser:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
        return user

    app.dependency_overrides[current_active_user] = mock_active_user
    app.dependency_overrides[security_active_user] = mock_active_user
    app.dependency_overrides[get_current_active_admin_user] = mock_active_admin
    yield
    app.dependency_overrides.pop(current_active_user, None)
    app.dependency_overrides.pop(security_active_user, None)
    app.dependency_overrides.pop(get_current_active_admin_user, None)
