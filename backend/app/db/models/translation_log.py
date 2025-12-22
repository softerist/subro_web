# backend/app/db/models/translation_log.py
"""
Model for tracking individual translation jobs.
Replaces the JSON-based translation_log.json file.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class TranslationLog(Base):
    """
    Records each translation job for statistics and history tracking.
    """

    __tablename__ = "translation_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    source_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    target_language: Mapped[str] = mapped_column(String(10), nullable=False)
    service_used: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "deepl", "google", "mixed", "failed"
    characters_billed: Mapped[int] = mapped_column(Integer, default=0)
    deepl_characters: Mapped[int] = mapped_column(Integer, default=0)
    google_characters: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(50), default="success"
    )  # "success", "partial_failure", "failed"
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Path to the translated output file (for download)
    output_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<TranslationLog(file={self.file_name}, service={self.service_used}, "
            f"chars={self.characters_billed})>"
        )
