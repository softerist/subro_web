# backend/app/db/models/app_settings.py
"""
Database model for application settings.
This is a singleton table (only one row with id=1) that stores
user-configurable settings like API keys and preferences.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
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
    qbittorrent_connection_mode: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default="direct"
    )  # "direct" | "docker_host" | "custom"
    qbittorrent_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qbittorrent_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qbittorrent_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qbittorrent_password: Mapped[str | None] = mapped_column(Text, nullable=True)  # Encrypted
    qbittorrent_webhook_key_encrypted: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Encrypted raw webhook key for script retrieval

    # --- Paths ---
    # Stored as JSON array string (e.g., '["/mnt/media", "/data/videos"]')
    allowed_media_folders: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Google Cloud Translate ---
    # Encrypted JSON blob containing the full service account credentials
    google_cloud_credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Extracted project_id for display purposes (not encrypted)
    google_cloud_project_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_cloud_valid: Mapped[bool | None] = mapped_column(Boolean, default=None, nullable=True)

    # --- Google Usage Cache (Fallback) ---
    google_usage_total_chars: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    google_usage_month_chars: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    google_usage_last_updated: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Setup State ---
    setup_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    app_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # --- Registration Settings ---
    open_signup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- Validation Status (cached after API validation) ---
    tmdb_valid: Mapped[bool | None] = mapped_column(Boolean, default=None, nullable=True)
    tmdb_rate_limited: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    omdb_valid: Mapped[bool | None] = mapped_column(Boolean, default=None, nullable=True)
    omdb_rate_limited: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    opensubtitles_valid: Mapped[bool | None] = mapped_column(Boolean, default=None, nullable=True)
    opensubtitles_key_valid: Mapped[bool | None] = mapped_column(
        Boolean, default=None, nullable=True
    )
    # OpenSubtitles subscription info (from login response)
    opensubtitles_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    opensubtitles_vip: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    opensubtitles_allowed_downloads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opensubtitles_rate_limited: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    def __repr__(self) -> str:
        return f"<AppSettings(id={self.id}, setup_completed={self.setup_completed})>"
