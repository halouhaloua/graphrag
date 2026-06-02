"""构造阶段的数据库操作

职责：将 KTBuilder 中 agent 模式发现的 schema 变更持久化到数据库。
不包含任何构造逻辑，仅处理 DB 写入。
"""

from sqlalchemy.ext.asyncio import AsyncSession


async def update_file_schema(
    db: AsyncSession,
    file_id: str,
    schema: dict,
) -> None:
    """将 agent 模式发现的新 schema 类型持久化到文件记录

    在图谱构建完成后调用，仅在 builder.schema_updated=True 时触发。
    """
    from rag.kb_manager.db_service import KnowledgeBaseFileService

    record = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not record:
        return
    record.schema_json = schema
    await db.flush()
