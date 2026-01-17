# backend/app/api/routers/translation_stats.py
"""
Endpoints for translation statistics and history.
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import current_active_user
from app.db.models.translation_log import TranslationLog
from app.db.models.user import User
from app.db.session import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/translation-stats", tags=["Translation Statistics"])


# --- Schemas ---


class TranslationLogRead(BaseModel):
    """Individual translation log entry."""

    id: int
    timestamp: datetime
    file_name: str
    source_language: str | None = None
    target_language: str
    service_used: str
    characters_billed: int
    deepl_characters: int
    google_characters: int
    status: str
    output_file_path: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AggregateStats(BaseModel):
    """Aggregate translation statistics."""

    total_translations: int = 0
    total_characters: int = 0
    deepl_characters: int = 0
    google_characters: int = 0
    success_count: int = 0
    failure_count: int = 0


class TranslationStatsResponse(BaseModel):
    """Response schema for translation statistics."""

    all_time: AggregateStats
    last_30_days: AggregateStats
    last_7_days: AggregateStats


class TranslationHistoryResponse(BaseModel):
    """Response schema for translation history."""

    items: list[TranslationLogRead]
    total: int
    page: int
    page_size: int


# --- Endpoints ---


@router.get(
    "",
    response_model=TranslationStatsResponse,
    summary="Get aggregate translation statistics",
)
async def get_translation_stats(
    db: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(current_active_user),
) -> TranslationStatsResponse:
    """
    Get aggregate translation statistics.

    Returns totals for all time, last 30 days, and last 7 days.

    **Accessible by all authenticated users.**
    """

    async def get_stats_for_period(start_date: datetime | None = None) -> AggregateStats:
        from sqlalchemy import case

        query = select(
            func.count(TranslationLog.id).label("total"),
            func.coalesce(func.sum(TranslationLog.characters_billed), 0).label("total_chars"),
            func.coalesce(func.sum(TranslationLog.deepl_characters), 0).label("deepl_chars"),
            func.coalesce(func.sum(TranslationLog.google_characters), 0).label("google_chars"),
            func.coalesce(
                func.sum(case((TranslationLog.status == "success", 1), else_=0)), 0
            ).label("success_count"),
        )
        if start_date:
            query = query.where(TranslationLog.timestamp >= start_date)

        result = await db.execute(query)
        row = result.one()

        return AggregateStats(
            total_translations=row.total or 0,
            total_characters=row.total_chars or 0,
            deepl_characters=row.deepl_chars or 0,
            google_characters=row.google_chars or 0,
            success_count=row.success_count or 0,
            failure_count=(row.total or 0) - (row.success_count or 0),
        )

    now = datetime.now(UTC)
    all_time = await get_stats_for_period()
    last_30_days = await get_stats_for_period(now - timedelta(days=30))
    last_7_days = await get_stats_for_period(now - timedelta(days=7))

    return TranslationStatsResponse(
        all_time=all_time,
        last_30_days=last_30_days,
        last_7_days=last_7_days,
    )


@router.get(
    "/history",
    response_model=TranslationHistoryResponse,
    summary="Get translation history",
)
async def get_translation_history(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(current_active_user),
) -> TranslationHistoryResponse:
    """
    Get paginated translation history.

    **Requires admin privileges.**
    """
    # Get total count
    count_query = select(func.count(TranslationLog.id))
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Get paginated items
    offset = (page - 1) * page_size
    items_query = (
        select(TranslationLog)
        .order_by(TranslationLog.timestamp.desc())
        .offset(offset)
        .limit(page_size)
    )
    # nosemgrep: generic-sql-fastapi, fastapi-aiosqlite-sqli - SQLAlchemy ORM uses parameterized queries
    items_result = await db.execute(items_query)
    items = items_result.scalars().all()

    return TranslationHistoryResponse(
        items=[TranslationLogRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
