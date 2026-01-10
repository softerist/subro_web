# /backend/app/db/models/user.py

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import JSON, DateTime, String, func  # text is not needed if no server_default
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.db.models.api_key import ApiKey
    from app.db.models.job import Job


class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"

    # Explicitly hint fields inherited from mixins to help Mypy/SQLAlchemy plugin
    id: Mapped[UUID]
    email: Mapped[str]
    hashed_password: Mapped[str]
    is_active: Mapped[bool]
    is_superuser: Mapped[bool]
    is_verified: Mapped[bool]

    role: Mapped[Literal["admin", "standard"]] = mapped_column(
        String(50), default="standard", nullable=False, index=True
    )
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    # MFA fields
    mfa_secret: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )  # Encrypted TOTP secret
    mfa_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    mfa_backup_codes: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )  # Encrypted JSON array of backup codes
    # Password change tracking for session invalidation
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Updated when password changes, used to invalidate old tokens
    force_password_change: Mapped[bool] = mapped_column(default=False, nullable=False)

    # --- Account Status & Security ---
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False, index=True
    )  # active|suspended|banned
    failed_login_count: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    preferences: Mapped[dict | None] = mapped_column(JSON, default={}, nullable=True)
    jobs: Mapped[list["Job"]] = relationship(
        "Job",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    api_keys: Mapped[list["ApiKey"]] = relationship(
        "ApiKey",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def api_key_preview(self) -> str | None:
        if not self.api_keys:
            return None
        now = datetime.now(UTC)
        active_keys = [
            key
            for key in self.api_keys
            if key.revoked_at is None and (key.expires_at is None or key.expires_at > now)
        ]
        if not active_keys:
            return None
        fallback_time = datetime.min.replace(tzinfo=UTC)
        active_keys.sort(key=lambda key: key.created_at or fallback_time, reverse=True)
        return active_keys[0].preview

    def __repr__(self) -> str:
        is_s_user = getattr(self, "is_superuser", "N/A")
        user_role = getattr(self, "role", "N/A")
        return f"<User(id={self.id!r}, email={self.email!r}, role={user_role!r}, is_superuser={is_s_user!r})>"
