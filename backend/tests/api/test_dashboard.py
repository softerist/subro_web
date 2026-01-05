import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.dashboard import DashboardTile

from ..factories.user_factory import UserFactory

API_PREFIX = settings.API_V1_STR


async def login_user(client: AsyncClient, email: str, password: str) -> dict:
    login_data = {"username": email, "password": password}
    response = await client.post(f"{API_PREFIX}/auth/login", data=login_data)
    assert response.status_code == status.HTTP_200_OK
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_active_tiles(test_client: AsyncClient, db_session: AsyncSession):
    # Create some tiles
    tile1 = DashboardTile(title="Tile 1", url="http://t1.com", is_active=True, order_index=1)
    tile2 = DashboardTile(title="Tile 2", url="http://t2.com", is_active=False, order_index=2)
    db_session.add_all([tile1, tile2])
    await db_session.commit()

    response = await test_client.get(f"{API_PREFIX}/dashboard/tiles")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Tile 1"


@pytest.mark.asyncio
async def test_admin_get_all_tiles(test_client: AsyncClient, db_session: AsyncSession):
    admin = UserFactory.create_user(
        session=db_session, email="admin_dash@example.com", is_superuser=True
    )
    tile1 = DashboardTile(title="Tile 1", url="http://t1.com", is_active=True, order_index=1)
    tile2 = DashboardTile(title="Tile 2", url="http://t2.com", is_active=False, order_index=2)
    db_session.add_all([tile1, tile2])
    await db_session.flush()
    headers = await login_user(test_client, admin.email, "password123")

    response = await test_client.get(f"{API_PREFIX}/dashboard/admin/tiles", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_create_tile_admin(test_client: AsyncClient, db_session: AsyncSession):
    admin = UserFactory.create_user(
        session=db_session, email="admin_create_tile@example.com", is_superuser=True
    )
    await db_session.flush()
    headers = await login_user(test_client, admin.email, "password123")

    tile_data = {
        "title": "New Tile",
        "url": "http://new.com",
        "description": "A new dashboard tile",
        "is_active": True,
        "order_index": 5,
    }
    response = await test_client.post(
        f"{API_PREFIX}/dashboard/tiles", json=tile_data, headers=headers
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["title"] == "New Tile"


@pytest.mark.asyncio
async def test_update_tile_admin(test_client: AsyncClient, db_session: AsyncSession):
    admin = UserFactory.create_user(
        session=db_session, email="admin_update_tile@example.com", is_superuser=True
    )
    tile = DashboardTile(title="Old Title", url="http://old.com", is_active=True, order_index=1)
    db_session.add(tile)
    await db_session.flush()
    headers = await login_user(test_client, admin.email, "password123")

    update_data = {"title": "Updated Title"}
    response = await test_client.patch(
        f"{API_PREFIX}/dashboard/tiles/{tile.id}", json=update_data, headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_reorder_tiles_admin(test_client: AsyncClient, db_session: AsyncSession):
    admin = UserFactory.create_user(
        session=db_session, email="admin_reorder@example.com", is_superuser=True
    )
    tile1 = DashboardTile(title="T1", url="http://t1.com", order_index=1)
    tile2 = DashboardTile(title="T2", url="http://t2.com", order_index=2)
    db_session.add_all([tile1, tile2])
    await db_session.flush()
    headers = await login_user(test_client, admin.email, "password123")

    reorder_data = [
        {"id": str(tile1.id), "order_index": 2},
        {"id": str(tile2.id), "order_index": 1},
    ]
    response = await test_client.post(
        f"{API_PREFIX}/dashboard/tiles/reorder", json=reorder_data, headers=headers
    )
    assert response.status_code == status.HTTP_200_OK

    await db_session.refresh(tile1)
    await db_session.refresh(tile2)
    assert tile1.order_index == 2
    assert tile2.order_index == 1


@pytest.mark.asyncio
async def test_delete_tile_admin(test_client: AsyncClient, db_session: AsyncSession):
    admin = UserFactory.create_user(
        session=db_session, email="admin_delete_tile@example.com", is_superuser=True
    )
    tile = DashboardTile(title="To Delete", url="http://del.com", order_index=1)
    db_session.add(tile)
    await db_session.flush()
    headers = await login_user(test_client, admin.email, "password123")

    response = await test_client.delete(f"{API_PREFIX}/dashboard/tiles/{tile.id}", headers=headers)
    assert response.status_code == status.HTTP_204_NO_CONTENT

    deleted_tile = await db_session.get(DashboardTile, tile.id)
    assert deleted_tile is None
