import uuid

from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base


class StoragePath(Base):
    __tablename__ = "storage_paths"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    path = Column(String, unique=True, index=True, nullable=False)
    label = Column(String, nullable=True)  # Optional user-friendly name
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<StoragePath id={self.id}, path={self.path}>"
