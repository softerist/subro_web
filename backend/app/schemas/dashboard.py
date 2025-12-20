from uuid import UUID

from pydantic import BaseModel, Field


class TileBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    url: str  # Using str instead of HttpUrl to allow relative paths or internal schemes if needed, but validation is good. Let's start with str for flexibility.
    icon: str | None = None
    is_active: bool = True


class TileCreate(TileBase):
    order_index: int = 0


class TileUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=100)
    url: str | None = None
    icon: str | None = None
    order_index: int | None = None
    is_active: bool | None = None


class TileReorder(BaseModel):
    id: UUID
    order_index: int


class TileRead(TileBase):
    id: UUID
    order_index: int

    class Config:
        from_attributes = True
