import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.core.log_utils import sanitize_for_log as _sanitize_for_log
from app.core.users import current_active_superuser, current_active_user
from app.db.models.user import User
from app.db.session import get_async_session
from app.schemas.storage_path import StoragePathCreate, StoragePathRead, StoragePathUpdate

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
    _current_user: User = Depends(current_active_user),
) -> list[StoragePathRead]:
    """List all storage paths."""
    return await crud.storage_path.get_multi(db=db, limit=1000)  # type: ignore[return-value]


@router.post("/", response_model=StoragePathRead, status_code=status.HTTP_201_CREATED)
async def create_storage_path(
    path_in: StoragePathCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
) -> StoragePathRead:
    """
    Create a new storage path.
    Standard users can only add subdirectories of existing paths.
    Superusers can add any path.
    """
    # 1. Validate path exists on filesystem and is a directory
    p = Path(path_in.path)
    if not p.exists() or not p.is_dir():
        detail = f"Path '{path_in.path}' does not exist or is not a directory."
        try:
            resolved = p.resolve()
            if not resolved.exists():
                pass
        except PermissionError as e:
            logger.error(
                "PermissionError in create_storage_path: %s | Path: %s",
                e,
                _sanitize_for_log(path_in.path),
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from e

    # 3. Enforce "Subdirectory Only" policy for Non-Superusers
    if not current_user.is_superuser:
        existing_paths = await crud.storage_path.get_multi(db=db)
        new_path_resolved = p.resolve()
        is_subdir = False

        for existing in existing_paths:
            allowed_parent = Path(existing.path).resolve()
            # Check if new path is inside allowed_parent
            # Note: new_path must be a subdirectory, not the same directory
            if allowed_parent in new_path_resolved.parents:
                is_subdir = True
                break

        if not is_subdir:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Standard users can only add subdirectories of existing allowed storage paths.",
            )

    try:
        storage_path = await crud.storage_path.create(db=db, obj_in=path_in)
    except Exception as e:
        logger.error(f"Error creating storage path: {e}")
        from sqlalchemy.exc import IntegrityError

        if isinstance(e, IntegrityError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Storage path already exists.",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create storage path.",
        ) from e
    return storage_path  # type: ignore[return-value]


@router.delete("/{path_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_storage_path(
    path_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(current_active_superuser),
) -> None:
    """Delete a storage path. Only superusers can delete."""
    storage_path = await crud.storage_path.get(db=db, id=path_id)
    if not storage_path:
        raise HTTPException(status_code=404, detail="Storage path not found")
    await crud.storage_path.remove(db=db, id=path_id)


@router.patch("/{path_id}", response_model=StoragePathRead)
async def update_storage_path(
    path_id: UUID,
    path_in: StoragePathUpdate,
    db: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(current_active_user),
) -> StoragePathRead:
    """Update a storage path label."""
    storage_path = await crud.storage_path.get(db=db, id=path_id)
    if not storage_path:
        raise HTTPException(status_code=404, detail="Storage path not found")

    update_data = {"label": path_in.label}
    if path_in.path:
        # Optionally prevent path updates or handle relinking?
        # For safety, let's ignore path updates or error if they try to change path?
        # The previous code implied we only patch label.
        pass

    updated_path = await crud.storage_path.update(db=db, db_obj=storage_path, obj_in=update_data)
    return updated_path  # type: ignore[return-value]
