"""Storage-path management endpoints (CRUD + folder browsing)."""

import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.core.config import settings
from app.core.log_utils import sanitize_for_log as _sanitize_for_log
from app.core.path_utils import is_path_allowed, resolve_allowed_bases
from app.core.users import current_active_superuser, current_active_user
from app.db.models.user import User
from app.db.session import get_async_session
from app.schemas.storage_path import (
    StoragePathBrowseEntry,
    StoragePathCreate,
    StoragePathRead,
    StoragePathUpdate,
)

router = APIRouter(
    tags=["Storage Paths"],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Resource not found"},
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated"},
        status.HTTP_403_FORBIDDEN: {"description": "Not authorized"},
    },
)

logger = logging.getLogger(__name__)


@router.get("/browse", response_model=list[StoragePathBrowseEntry])
async def browse_folders(
    db: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(current_active_user),
    path: str | None = Query(
        None,
        description="Absolute path to browse. Omit to get allowed roots.",
    ),
) -> list[StoragePathBrowseEntry]:
    """Browse directories within allowed storage paths.

    - If ``path`` is omitted, returns the allowed root folders.
    - If ``path`` is provided, returns its direct child directories
      (only if the path is within an allowed root).
    """
    # Build the combined allowed-folders list (DB + env)
    db_paths = await crud.storage_path.get_multi(db)
    env_folders = settings.ALLOWED_MEDIA_FOLDERS or []
    all_allowed_strings = list({str(f) for f in env_folders} | {str(p.path) for p in db_paths})
    allowed_bases = resolve_allowed_bases(all_allowed_strings)

    if path is None:
        return _build_root_entries(allowed_bases)

    resolved = _resolve_browse_path(path)

    if not is_path_allowed(resolved, allowed_bases):
        logger.warning(
            "User %s attempted to browse outside allowed paths: %s",
            _sanitize_for_log(getattr(_current_user, "email", "unknown")),
            _sanitize_for_log(path),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Path is not within any allowed media folder.",
        )

    return _build_child_entries(resolved, path, allowed_bases)


def _resolve_browse_path(path: str) -> Path:
    """Resolve and validate a user-supplied browse path."""
    try:
        resolved = Path(path).resolve(strict=True)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Path '{path}' does not exist or is not accessible.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(f"Path '{path}' could not be resolved (e.g. symlink loop)."),
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Path '{path}' does not exist or is not accessible.",
        ) from exc

    if not resolved.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Path '{path}' is not a directory.",
        )
    return resolved


def _build_root_entries(
    allowed_bases: list[Path],
) -> list[StoragePathBrowseEntry]:
    """Return browse entries for the allowed root folders."""
    return [
        StoragePathBrowseEntry(
            name=base.name or str(base),
            path=str(base),
            has_children=_dir_has_subdirs(base),
        )
        for base in sorted(allowed_bases, key=str)
    ]


def _build_child_entries(
    resolved: Path,
    raw_path: str,
    allowed_bases: list[Path],
) -> list[StoragePathBrowseEntry]:
    """Return browse entries for the direct child directories of *resolved*."""
    entries: list[StoragePathBrowseEntry] = []
    try:
        for child in sorted(resolved.iterdir()):
            if not child.is_dir():
                continue
            # Skip symlinked children that resolve outside allowed roots
            try:
                child_resolved = child.resolve(strict=True)
            except (FileNotFoundError, RuntimeError, OSError):
                continue
            if not is_path_allowed(child_resolved, allowed_bases):
                continue
            entries.append(
                StoragePathBrowseEntry(
                    name=child.name,
                    path=str(child_resolved),
                    has_children=_dir_has_subdirs(child_resolved),
                )
            )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied reading directory '{raw_path}'.",
        ) from exc
    return entries


def _dir_has_subdirs(directory: Path) -> bool:
    """Return True if *directory* contains at least one subdirectory."""
    try:
        for child in directory.iterdir():
            if child.is_dir():
                return True
    except (PermissionError, OSError):
        pass
    return False


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
            p.resolve()
        except PermissionError as e:
            logger.error(
                "PermissionError in create_storage_path: %s | Path: %s",
                e,
                _sanitize_for_log(path_in.path),
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from e

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

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
                detail=(
                    "Standard users can only add subdirectories of existing allowed storage paths."
                ),
            )

    try:
        storage_path = await crud.storage_path.create(db=db, obj_in=path_in)
    except IntegrityError as e:
        logger.error("Error creating storage path: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Storage path already exists.",
        ) from e
    except Exception as e:
        logger.error("Error creating storage path: %s", e)
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

    update_data = path_in.model_dump(exclude_unset=True, exclude_none=True)
    update_data.pop("path", None)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one updatable field must be provided.",
        )

    updated_path = await crud.storage_path.update(db=db, db_obj=storage_path, obj_in=update_data)
    return updated_path  # type: ignore[return-value]
