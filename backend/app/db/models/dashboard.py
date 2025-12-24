import uuid

from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base


class DashboardTile(Base):
    __tablename__ = "dashboard_tiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    title = Column(String, nullable=False)
    url = Column(String, nullable=False)
    icon = Column(String, nullable=True)  # Lucide icon name
    order_index = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
