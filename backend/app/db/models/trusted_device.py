# backend/app/db/models/trusted_device.py
"""
Model for trusted devices that can skip MFA verification.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class TrustedDevice(Base):
    """
    Stores trusted device tokens for MFA bypass.

    When a user checks "Trust this device", a token is stored here
    and a corresponding cookie is set. On future logins, if the cookie
    matches a valid token, MFA is skipped.
    """

    __tablename__ = "trusted_devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Hashed device token (the raw token is stored in the cookie)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    # Device identifier for user display (e.g., "Chrome on Windows")
    device_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # IP address when device was trusted
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # When the trust was established
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # When this trust expires (default 30 days)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Last time this device was used for login
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationship to user
    user = relationship("User", backref="trusted_devices")

    def is_expired(self) -> bool:
        """Check if this trusted device has expired."""
        return datetime.now(UTC) > self.expires_at

    def __repr__(self) -> str:
        return f"<TrustedDevice(id={self.id}, user_id={self.user_id}, device={self.device_name})>"
