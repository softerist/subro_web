from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.users import current_active_superuser
from app.db.models.dashboard import DashboardTile
from app.db.models.user import User
from app.db.session import get_async_session
from app.schemas.dashboard import TileCreate, TileRead, TileReorder, TileUpdate

router = APIRouter()


# --- Public Endpoints ---
@router.get("/tiles", response_model=list[TileRead], summary="Get active dashboard tiles")
async def get_active_tiles(
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> Sequence[DashboardTile]:
    """
    Get all active dashboard tiles, ordered by order_index.
    """
    stmt = (
        select(DashboardTile)
        .where(DashboardTile.is_active.is_(True))
        .order_by(DashboardTile.order_index)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# --- Admin Endpoints ---


@router.get(
    "/admin/tiles", response_model=list[TileRead], summary="Get all dashboard tiles (Admin)"
)
async def get_all_tiles(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: Annotated[User, Depends(current_active_superuser)],  # noqa: ARG001
) -> Sequence[DashboardTile]:
    """
    Get all dashboard tiles (active and inactive), ordered by order_index.
    """
    stmt = select(DashboardTile).order_by(DashboardTile.order_index)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post(
    "/tiles",
    response_model=TileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new tile",
)
async def create_tile(
    tile_in: TileCreate,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: Annotated[User, Depends(current_active_superuser)],  # noqa: ARG001
) -> DashboardTile:
    """
    Create a new dashboard tile.
    """
    new_tile = DashboardTile(**tile_in.model_dump())
    db.add(new_tile)
    await db.commit()
    await db.refresh(new_tile)
    return new_tile


@router.patch("/tiles/{tile_id}", response_model=TileRead, summary="Update a tile")
async def update_tile(
    tile_id: UUID,
    tile_update: TileUpdate,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: Annotated[User, Depends(current_active_superuser)],  # noqa: ARG001
) -> DashboardTile:
    """
    Update a dashboard tile.
    """
    stmt = select(DashboardTile).where(DashboardTile.id == tile_id)
    result = await db.execute(stmt)
    tile = result.scalar_one_or_none()

    if not tile:
        raise HTTPException(status_code=404, detail="Tile not found")

    update_data = tile_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tile, field, value)

    await db.commit()
    await db.refresh(tile)
    return tile


@router.delete("/tiles/{tile_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a tile")
async def delete_tile(
    tile_id: UUID,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: Annotated[User, Depends(current_active_superuser)],  # noqa: ARG001
) -> None:
    """
    Delete a dashboard tile.
    """
    stmt = select(DashboardTile).where(DashboardTile.id == tile_id)
    result = await db.execute(stmt)
    tile = result.scalar_one_or_none()

    if not tile:
        raise HTTPException(status_code=404, detail="Tile not found")

    await db.delete(tile)
    await db.commit()
    return None


@router.post("/tiles/reorder", status_code=status.HTTP_200_OK, summary="Reorder tiles")
async def reorder_tiles(
    reorder_list: list[TileReorder],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: Annotated[User, Depends(current_active_superuser)],  # noqa: ARG001
) -> dict[str, str]:
    """
    Update the order_index of multiple tiles.
    """
    # Simple loop update - acceptable for small number of tiles (dashboard usually < 50 items)
    for item in reorder_list:
        stmt = (
            update(DashboardTile)
            .where(DashboardTile.id == item.id)
            .values(order_index=item.order_index)
        )
        await db.execute(stmt)

    await db.commit()
    return {"message": "Tiles reordered successfully"}
