# backend/app/db/models/deepl_usage.py
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class DeepLUsage(Base):
    """
    Table to store DeepL API key usage statistics.
    Migrated from translation_log.json to the database for better persistence.
    """

    __tablename__ = "deepl_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Unique identifier for the key (usually the suffix or a hash)
    # Using suffix for now as it matches the UI display logic
    key_identifier: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    character_count: Mapped[int] = mapped_column(Integer, default=0)
    character_limit: Mapped[int] = mapped_column(Integer, default=500000)
    valid: Mapped[bool] = mapped_column(Boolean, default=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    def __repr__(self) -> str:
        return f"<DeepLUsage(key={self.key_identifier}, count={self.character_count}/{self.character_limit})>"
