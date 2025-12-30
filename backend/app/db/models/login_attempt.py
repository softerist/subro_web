# backend/app/db/models/login_attempt.py
"""
Model for tracking failed login attempts for account lockout.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LoginAttempt(Base):
    """
    Tracks failed login attempts for account lockout protection.

    Records are kept for a configurable duration to enable:
    - Progressive lockout (delay increases with failed attempts)
    - Brute force detection by IP or email
    - Security auditing
    """

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Target of the login attempt (email being tried)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Source IP address
    ip_address: Mapped[str] = mapped_column(
        String(45), nullable=False, index=True
    )  # IPv6 max length

    # When the attempt occurred
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )

    # Whether this attempt was successful (allows tracking both)
    success: Mapped[bool] = mapped_column(default=False)

    # User agent for additional context (optional)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Composite indexes for efficient lockout queries
    __table_args__ = (
        Index("ix_login_attempts_email_attempted", "email", "attempted_at"),
        Index("ix_login_attempts_ip_attempted", "ip_address", "attempted_at"),
    )

    def __repr__(self) -> str:
        return f"<LoginAttempt(email={self.email}, ip={self.ip_address}, success={self.success})>"
