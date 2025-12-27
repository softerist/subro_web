# backend/app/schemas/app_settings.py
"""
Pydantic schemas for application settings.
"""

from pydantic import BaseModel, Field


class SetupStatus(BaseModel):
    """Response schema for setup status check."""

    setup_completed: bool


class SettingsBase(BaseModel):
    """Base schema with common fields for settings."""

    # qBittorrent (non-sensitive)
    qbittorrent_host: str | None = None
    qbittorrent_port: int | None = None
    qbittorrent_username: str | None = None

    # Paths
    allowed_media_folders: list[str] = Field(default_factory=list)


class SettingsUpdate(SettingsBase):
    """
    Schema for updating settings.
    Accepts raw (unencrypted) values - encryption happens in CRUD layer.
    """

    # Override base field to allow None (no update)
    allowed_media_folders: list[str] | None = None

    # API Keys (will be encrypted before storage)
    tmdb_api_key: str | None = None
    omdb_api_key: str | None = None
    opensubtitles_api_key: str | None = None
    opensubtitles_username: str | None = None
    opensubtitles_password: str | None = None
    deepl_api_keys: list[str] | None = None
    qbittorrent_password: str | None = None

    # Google Cloud (JSON credentials blob)
    google_cloud_credentials: str | None = None


class DeepLUsage(BaseModel):
    """
    Schema for DeepL API usage statistics from logs.
    """

    key_alias: str
    character_count: int
    character_limit: int
    valid: bool | None = None


class SettingsRead(SettingsBase):
    """
    Schema for reading settings.
    Sensitive fields are masked (e.g., "****1234").
    """

    # API Keys (masked)
    tmdb_api_key: str = ""  # Will show as "****xxxx" or empty
    omdb_api_key: str = ""
    opensubtitles_api_key: str = ""
    opensubtitles_username: str = ""
    opensubtitles_password: str = ""
    deepl_api_keys: list[str] = Field(default_factory=list)  # Masked entries
    # Usage Stats (Read Only)
    deepl_usage: list[DeepLUsage] = Field(default_factory=list)
    qbittorrent_password: str = ""

    # Validation Status (set by backend after validating credentials)
    # None = Not Validated / Connection Error
    # True = Valid
    # True = Valid
    # False = Invalid
    tmdb_valid: str | None = None  # "valid", "invalid", "limit_reached", or None
    omdb_valid: str | None = None  # "valid", "invalid", "limit_reached", or None
    opensubtitles_valid: bool | None = None  # Login/Credentials status
    opensubtitles_key_valid: bool | None = None  # API Key status
    # OpenSubtitles subscription info
    opensubtitles_level: str | None = None  # e.g. "VIP Member", "Standard"
    opensubtitles_vip: bool | None = None
    opensubtitles_allowed_downloads: int | None = None
    opensubtitles_rate_limited: bool | None = None

    # Google Cloud (read-only display fields)
    google_cloud_configured: bool = False
    google_cloud_project_id: str | None = None
    google_cloud_valid: bool | None = None
    google_cloud_error: str | None = None

    # State
    setup_completed: bool = False

    class Config:
        from_attributes = True


class SetupComplete(BaseModel):
    """Schema for completing the setup wizard."""

    # Admin user creation
    admin_email: str
    admin_password: str

    # Optional settings (if user fills them in)
    settings: SettingsUpdate | None = None


class SetupSkip(BaseModel):
    """Schema for skipping setup (uses env defaults)."""

    # Admin user can still be created even if skipping config
    admin_email: str | None = None
    admin_password: str | None = None
