from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class StoragePathBase(BaseModel):
    path: str = Field(..., min_length=1, description="Absolute filesystem path")
    label: str | None = Field(None, description="Optional label for the path")


class StoragePathCreate(StoragePathBase):
    pass


class StoragePathUpdate(StoragePathBase):
    pass


class StoragePathRead(StoragePathBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True
