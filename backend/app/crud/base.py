# backend/app/crud/base.py
from typing import Any, Generic, TypeVar  # Ensure all necessary imports

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement  # For type hinting order_by clauses

from app.db.base_class import Base  # Your project's Base SQLAlchemy model

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: type[ModelType]):
        """
        CRUD object with default methods to Create, Read, Update, Delete (CRUD).

        **Parameters**

        * `model`: A SQLAlchemy model class
        """
        self.model = model

    async def get(self, db: AsyncSession, id: Any) -> ModelType | None:
        """
        Get a single record by ID.
        """
        # Assuming 'id' is the primary key attribute name in your models
        result = await db.execute(select(self.model).filter(self.model.id == id))
        return result.scalars().first()

    async def get_multi(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        order_by: ColumnElement | list[ColumnElement] | None = None,
    ) -> list[ModelType]:
        """
        Get multiple records with pagination and ordering.
        """
        stmt = select(self.model).offset(skip).limit(limit)
        if order_by is not None:
            if isinstance(order_by, list):  # Check if it's a list of order_by clauses
                stmt = stmt.order_by(*order_by)
            else:  # Assume it's a single order_by clause
                stmt = stmt.order_by(order_by)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, *, obj_in: CreateSchemaType) -> ModelType:
        """
        Create a new record.
        """
        # Pydantic's model_dump() is preferred over jsonable_encoder for this
        db_obj = self.model(**obj_in.model_dump())
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: ModelType,
        obj_in: UpdateSchemaType | dict[str, Any],
    ) -> ModelType:
        """
        Update an existing record.
        """
        obj_data = jsonable_encoder(db_obj)  # Convert existing DB object to dict
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            # For Pydantic models, exclude_unset=True ensures only provided fields are used for update
            update_data = obj_in.model_dump(exclude_unset=True)

        for field in obj_data:
            if field in update_data:
                setattr(db_obj, field, update_data[field])

        db.add(db_obj)  # Add the updated object to the session
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def remove(self, db: AsyncSession, *, id: Any) -> ModelType | None:
        """
        Remove a record by ID.
        Returns the removed object or None if not found.
        """
        # Assuming 'id' is the primary key attribute name
        result = await db.execute(select(self.model).filter(self.model.id == id))
        obj = result.scalars().first()
        if obj:
            await db.delete(obj)
            await db.commit()
        return obj
