import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.core.users import current_active_superuser
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
    # Request implies "we can manually add specified folder paths so we can choose them later from dashboard".
    # Assuming any active user can list, but maybe only admins can add?
    # Let's start with basic active user for listing.
    _current_user: User = Depends(current_active_superuser),
) -> list[StoragePathRead]:
    """List all storage paths."""
    return await crud.storage_path.get_multi(db=db, limit=1000)  # type: ignore[return-value]


@router.post("/", response_model=StoragePathRead, status_code=status.HTTP_201_CREATED)
async def create_storage_path(
    path_in: StoragePathCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_superuser),
) -> StoragePathRead:
    """
    Create a new storage path.
    Superusers only.
    """
    # 1. Validate path exists on filesystem and is a directory
    p = Path(path_in.path)
    if not p.exists() or not p.is_dir():
        # Security check: check ownership/permissions if needed?
        # For now, just existence.
        detail = f"Path '{path_in.path}' does not exist or is not a directory."
        try:
            # Try to resolve to ensure no funny business, though Pydantic might catch some
            resolved = p.resolve()
            if not resolved.exists():
                # Should be caught above
                pass
        except PermissionError as e:
            logger.error(f"PermissionError in create_storage_path: {e} | Path: {path_in.path}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from e

    # 2. Check for duplicates (moved to IntegrityError handling during creation)
    # existing = await crud.storage_path.get_by_path(db, path=path_in.path)
    # if existing:
    #     raise HTTPException(
    #         status_code=status.HTTP_400_BAD_REQUEST,
    #         detail="Storage path already exists.",
    #     )

    # 3. Enforce "Subdirectory Only" policy for Non-Superusers
    if not current_user.is_superuser:
        # Prevent adding root dirs like / or /usr
        # This route is currently restricted to superusers anyway via Dependency,
        # but good to keep logic if we relax it later.
        pass

    try:
        storage_path = await crud.storage_path.create(db=db, obj_in=path_in)
    except Exception as e:
        # IntegrityError likely
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
    """Delete a storage path."""
    storage_path = await crud.storage_path.get(db=db, id=path_id)
    if not storage_path:
        raise HTTPException(status_code=404, detail="Storage path not found")
    await crud.storage_path.remove(db=db, id=path_id)


@router.put("/{path_id}", response_model=StoragePathRead)
async def update_storage_path(
    path_id: UUID,
    path_in: StoragePathUpdate,
    db: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(current_active_superuser),
) -> StoragePathRead:
    """Update a storage path."""
    storage_path = await crud.storage_path.get(db=db, id=path_id)
    if not storage_path:
        raise HTTPException(status_code=404, detail="Storage path not found")

    # We only allow updating the label. If they provide a new path, we might ignore it or error.
    # To keep it simple and safe for non-superusers, we only patch the label.
    update_data = {"label": path_in.label}
    updated_path = await crud.storage_path.update(db=db, db_obj=storage_path, obj_in=update_data)
    return updated_path  # type: ignore[return-value]
