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

    # Security check: Ensure file exists
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    # Security check: Ensure it's a file, not a directory
    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is not a file",
        )

    # Security check: Ensure file is within allowed media folders
    allowed_folders = settings.ALLOWED_MEDIA_FOLDERS or []
    is_allowed = any(str(file_path).startswith(str(folder)) for folder in allowed_folders)
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
        path=str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream",
    )
