# backend/app/db/models/webhook_key.py
"""Dedicated webhook key model for qBittorrent integration."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class WebhookKey(Base):
    """
    Dedicated webhook key for automated integrations like qBittorrent.

    Separate from user API keys because:
    - Limited scope (jobs:create only)
    - No user association (system-level)
    - Can be managed independently
    - Stored encrypted and written to env file for external scripts
    """

    __tablename__ = "webhook_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="qBittorrent Webhook")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Key storage (same pattern as ApiKey)
    prefix: Mapped[str] = mapped_column(String(12), index=True, nullable=False)
    last4: Mapped[str] = mapped_column(String(4), nullable=False)
    hashed_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    # Scope restriction
    scopes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=lambda: ["jobs:create"]
    )

    # Status and tracking
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    use_count: Mapped[int] = mapped_column(default=0, nullable=False)

    @property
    def preview(self) -> str:
        """Return a safe preview of the key."""
        return f"{self.prefix}...{self.last4}"
