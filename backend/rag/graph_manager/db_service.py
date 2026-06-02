from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.base_service import BaseService
from pydantic import BaseModel as PydanticBaseModel

from rag.graph_manager.model import KnowledgeGraph
from rag.graph_manager.schema import KnowledgeGraphCreate


class KnowledgeGraphService(
    BaseService[KnowledgeGraph, KnowledgeGraphCreate, PydanticBaseModel]
):
    model = KnowledgeGraph

    @classmethod
    async def get_by_file(cls, db: AsyncSession, file_id: str) -> Optional[KnowledgeGraph]:
        query = select(cls.model).where(
            cls.model.file_id == file_id,
            cls.model.is_deleted == False,
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    @classmethod
    async def delete_by_file(cls, db: AsyncSession, file_id: str) -> bool:
        graph = await cls.get_by_file(db, file_id)
        if graph:
            await cls.delete(db, graph.id)
            return True
        return False
