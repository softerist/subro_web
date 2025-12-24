from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models.storage_path import StoragePath
from app.schemas.storage_path import StoragePathCreate, StoragePathUpdate


class CRUDStoragePath(CRUDBase[StoragePath, StoragePathCreate, StoragePathUpdate]):
    async def get_by_path(self, db: AsyncSession, *, path: str) -> StoragePath | None:
        result = await db.execute(select(StoragePath).filter(StoragePath.path == path))
        return result.scalars().first()


storage_path = CRUDStoragePath(StoragePath)
