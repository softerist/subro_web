# backend/app/api/routers/files.py
"""
File download endpoints for translated subtitle files.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.security import current_active_superuser
from app.db.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["Files"])


@router.get(
    "/download",
    summary="Download a file",
    description="Download a translated subtitle file by path.",
)
async def download_file(
    path: str = Query(..., description="Absolute path to the file"),
    current_user: User = Depends(current_active_superuser),
) -> FileResponse:
    """
    Download a file from the server.

    **Requires admin privileges.**

    Security: Only allows downloading files from configured media folders.
    """
    file_path = Path(path)
    try:
        resolved_file_path = file_path.resolve(strict=True)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    except RuntimeError as e:  # e.g. symlink loop
        logger.warning(f"Path resolution failed for download '{path}': {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path could not be resolved.",
        ) from e
    except Exception as e:  # NOSONAR
        logger.warning(f"Unexpected error during path resolution for download '{path}': {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path resolution failed.",
        ) from e

    # Security check: Ensure it's a file, not a directory
    if not resolved_file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is not a file",
        )

    # Security check: Ensure file is within allowed media folders
    allowed_folders = settings.ALLOWED_MEDIA_FOLDERS or []
    resolved_allowed_folders: list[Path] = []
    for folder in allowed_folders:
        try:
            resolved_allowed_folders.append(Path(folder).resolve(strict=True))
        except FileNotFoundError:
            logger.error(f"Configured allowed base path '{folder}' does not exist. Skipping.")
        except RuntimeError as e:  # e.g. symlink loop
            logger.error(
                f"Resolution of configured allowed base path '{folder}' failed (e.g. symlink loop). Skipping: {e}"
            )
        except Exception as e:  # NOSONAR
            logger.error(
                f"Unexpected error during resolution of configured allowed base path '{folder}'. Skipping: {e}"
            )

    is_allowed = any(
        resolved_file_path == base or base in resolved_file_path.parents
        for base in resolved_allowed_folders
    )
    if not is_allowed and allowed_folders:
        logger.warning(
            f"Attempted download outside allowed folders: {path} by {current_user.email}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: File is not in an allowed media folder",
        )

    logger.info(f"File download: {path} by {current_user.email}")

    return FileResponse(
        path=str(resolved_file_path),
        filename=resolved_file_path.name,
        media_type="application/octet-stream",
    )
