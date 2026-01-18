# backend/app/db/models/passkey.py
"""
Model for WebAuthn/Passkey credentials.

Stores registered passkeys for passwordless authentication.
Each user can have multiple passkeys (e.g., different devices).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class Passkey(Base):
    """
    Stores WebAuthn credentials (passkeys) for users.

    A passkey allows passwordless authentication using biometrics,
    security keys, or platform authenticators (Touch ID, Windows Hello).
    """

    __tablename__ = "user_passkeys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # WebAuthn credential ID - unique identifier from authenticator
    # Stored as bytes, used to look up credential during authentication
    credential_id: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, unique=True, index=True
    )

    # COSE-encoded public key from authenticator
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # Signature counter - incremented on each use, detects cloned authenticators
    sign_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Transport hints for authenticator (e.g., ["usb", "internal", "hybrid", "ble"])
    transports: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Authenticator AAGUID - identifies the authenticator model/type
    aaguid: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # User-friendly name for this passkey (e.g., "MacBook Touch ID")
    device_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Backup eligibility and state (for synced passkeys)
    # BE flag: credential is eligible for backup (can be synced)
    backup_eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # BS flag: credential has been backed up (is synced)
    backup_state: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationship to user
    user = relationship("User", backref="passkeys")

    def update_last_used(self) -> None:
        """Update the last_used_at timestamp."""
        self.last_used_at = datetime.now(UTC)

    def __repr__(self) -> str:
        return (
            f"<Passkey(id={self.id}, user_id={self.user_id}, "
            f"device={self.device_name}, sign_count={self.sign_count})>"
        )
