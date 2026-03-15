from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StoragePathBase(BaseModel):
    path: str = Field(..., min_length=1, description="Absolute filesystem path")
    label: str | None = Field(None, description="Optional label for the path")


class StoragePathCreate(StoragePathBase):
    pass


class StoragePathUpdate(BaseModel):
    path: str | None = Field(None, min_length=1, description="Absolute filesystem path")
    label: str | None = Field(None, description="Optional label for the path")


class StoragePathRead(StoragePathBase):
    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StoragePathBrowseEntry(BaseModel):
    """A single directory entry returned by the browse endpoint."""

    name: str = Field(..., description="Directory name")
    path: str = Field(..., description="Absolute path to the directory")
    has_children: bool = Field(..., description="Whether this directory contains subdirectories")
