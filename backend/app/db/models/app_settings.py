# backend/app/db/models/app_settings.py
"""
Database model for application settings.
This is a singleton table (only one row with id=1) that stores
user-configurable settings like API keys and preferences.
"""

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class AppSettings(Base):
    """
    Singleton table for application configuration.

    All sensitive fields (API keys, passwords) are stored encrypted
    using Fernet symmetric encryption derived from SECRET_KEY.

    The singleton pattern is enforced at the CRUD layer, not the DB level,
    to allow flexibility during initialization.
    """

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # --- API Keys (Stored Encrypted) ---
    tmdb_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    omdb_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    opensubtitles_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    opensubtitles_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    opensubtitles_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    deepl_api_keys: Mapped[str | None] = mapped_column(Text, nullable=True)  # Encrypted JSON array

    # --- qBittorrent Settings ---
    qbittorrent_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qbittorrent_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qbittorrent_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qbittorrent_password: Mapped[str | None] = mapped_column(Text, nullable=True)  # Encrypted

    # --- Paths ---
    # Stored as JSON array string (e.g., '["/mnt/media", "/data/videos"]')
    allowed_media_folders: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Setup State ---
    setup_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<AppSettings(id={self.id}, setup_completed={self.setup_completed})>"
