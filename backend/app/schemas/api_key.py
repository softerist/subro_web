# backend/app/schemas/api_key.py
import uuid
from datetime import datetime

from pydantic import BaseModel


class ApiKeyCreateResponse(BaseModel):
    id: uuid.UUID
    api_key: str
    preview: str
    created_at: datetime


class ApiKeyRevokeResponse(BaseModel):
    revoked: bool
