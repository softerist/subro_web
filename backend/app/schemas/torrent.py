# backend/app/schemas/torrent.py
"""Schemas for qBittorrent torrent data."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CompletedTorrentInfo(BaseModel):
    """Information about a completed torrent from qBittorrent."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    save_path: str  # Directory where torrent files are saved
    content_path: str | None = None  # Resolved content root when available
    completed_on: datetime | None = None
