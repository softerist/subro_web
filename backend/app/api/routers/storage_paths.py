import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.core.security import current_active_superuser, current_active_user
from app.db.session import get_async_session
from app.schemas.storage_path import StoragePathCreate, StoragePathRead

router = APIRouter(
    tags=["Storage Paths"],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Resource not found"},
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated"},
        status.HTTP_403_FORBIDDEN: {"description": "Not authorized"},
    },
)

logger = logging.getLogger(__name__)


@router.get("/", response_model=list[StoragePathRead])
async def list_storage_paths(
    db: AsyncSession = Depends(get_async_session),
    # Any authenticated user can list paths? Or only superusers?
    # Request implies "we can manually add specified folder paths so we can choose them later from dashboard".
    # Assuming any active user can list, but maybe only admins can add?
    # Let's start with basic active user for listing.
    current_user=Depends(current_active_user),  # noqa: ARG001
):
    """
    List all configured storage paths from the database.
    """
    return await crud.storage_path.get_multi(db, limit=1000)


@router.post("/", response_model=StoragePathRead, status_code=status.HTTP_201_CREATED)
async def create_storage_path(
    path_in: StoragePathCreate,
    db: AsyncSession = Depends(get_async_session),
    # Assuming only superusers can configure server paths for security
    current_user=Depends(current_active_superuser),  # noqa: ARG001
):
    """
    Add a new storage path. Only accessible by superusers.
    Validates that the path exists on the server.
    """
    # 1. Check if path exists physically
    p = Path(path_in.path)

    # Common host-style prefixes for providing tips
    host_style_prefixes = ("/root", "/home", "/mnt", "/Users", "C:", "D:")
    is_host_style = str(path_in.path).startswith(host_style_prefixes)
    docker_tip = " TIP: You might be using a HOST path. Please use the path as it is MAPPED inside the container (e.g., '/downloads')."

    try:
        if not p.exists():
            detail = f"Path '{path_in.path}' does not exist on the server filesystem."
            if is_host_style:
                detail += docker_tip
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

        if not p.is_dir():
            detail = f"Path '{path_in.path}' is not a directory."
            if is_host_style:
                detail += docker_tip
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    except PermissionError as e:
        detail = f"Permission denied while accessing path '{path_in.path}'. Please ensure the backend has proper permissions for this folder."
        if is_host_style:
            detail += docker_tip

        logger.error(f"PermissionError in create_storage_path: {e} | Path: {path_in.path}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from e

    # 2. Check for duplicates
    existing = await crud.storage_path.get_by_path(db, path=path_in.path)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Storage path already exists.",
        )

    return await crud.storage_path.create(db, obj_in=path_in)


@router.delete("/{path_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_storage_path(
    path_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user=Depends(current_active_superuser),  # noqa: ARG001
):
    """
    Remove a storage path. Only accessible by superusers.
    """
    existing = await crud.storage_path.get(db, id=path_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage path not found.",
        )
    await crud.storage_path.remove(db, id=path_id)
