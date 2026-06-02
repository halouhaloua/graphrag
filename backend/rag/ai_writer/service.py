from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.base_service import BaseService
from rag.ai_writer.model import WriterConversation, WriterMessage, WriterDocument
from rag.ai_writer.schema import WriterConversationCreate, WriterMessageCreate, WriterDocumentCreate


class WriterConversationService(
    BaseService[WriterConversation, WriterConversationCreate, BaseModel]
):
    model = WriterConversation
    excel_columns = {
        "id": "会话ID",
        "user_id": "用户ID",
        "title": "会话标题",
        "model_name": "使用模型",
        "sys_create_datetime": "创建时间",
        "sys_update_datetime": "更新时间",
    }
    excel_sheet_name = "AI写作对话列表"

    @classmethod
    async def get_user_conversations(
        cls, db: AsyncSession, user_id: str, page: int = 1, page_size: int = 20
    ) -> Tuple[List[WriterConversation], int]:
        filters = [cls.model.user_id == user_id]
        return await cls.get_list(db, page=page, page_size=page_size, filters=filters)


class WriterMessageService(BaseService[WriterMessage, WriterMessageCreate, BaseModel]):
    model = WriterMessage
    excel_columns = {
        "id": "消息ID",
        "conversation_id": "会话ID",
        "role": "角色",
        "content": "内容",
        "model_name": "模型",
        "sys_create_datetime": "发送时间",
    }
    excel_sheet_name = "AI写作消息记录"

    @classmethod
    async def get_messages_by_conversation(
        cls, db: AsyncSession, conversation_id: str
    ) -> List[WriterMessage]:
        query = (
            select(cls.model)
            .where(
                cls.model.conversation_id == conversation_id,
                cls.model.is_deleted == False,
            )
            .order_by(cls.model.sys_create_datetime.asc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @classmethod
    async def update_message_content(
        cls, db: AsyncSession, message_id: str, new_content: str
    ) -> Optional[WriterMessage]:
        msg = await cls.get_by_id(db, message_id)
        if not msg:
            return None
        msg.content = new_content
        await db.flush()
        await db.refresh(msg)
        return msg


class WriterDocumentService(BaseService[WriterDocument, WriterDocumentCreate, BaseModel]):
    model = WriterDocument
    excel_columns = {
        "id": "文档ID",
        "conversation_id": "会话ID",
        "message_id": "来源消息ID",
        "title": "文档标题",
        "content": "文档内容",
        "sys_create_datetime": "创建时间",
        "sys_update_datetime": "更新时间",
    }
    excel_sheet_name = "AI写作文档列表"

    @classmethod
    async def get_documents_by_conversation(
        cls, db: AsyncSession, conversation_id: str
    ) -> List[WriterDocument]:
        query = (
            select(cls.model)
            .where(
                cls.model.conversation_id == conversation_id,
                cls.model.is_deleted == False,
            )
            .order_by(cls.model.sys_create_datetime.asc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @classmethod
    async def get_documents_by_message(
        cls, db: AsyncSession, message_id: str
    ) -> List[WriterDocument]:
        query = (
            select(cls.model)
            .where(
                cls.model.message_id == message_id,
                cls.model.is_deleted == False,
            )
            .order_by(cls.model.sys_create_datetime.asc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @classmethod
    async def update_document(
        cls, db: AsyncSession, document_id: str, title: Optional[str] = None, content: Optional[str] = None
    ) -> Optional[WriterDocument]:
        doc = await cls.get_by_id(db, document_id)
        if not doc:
            return None
        if title is not None:
            doc.title = title
        if content is not None:
            doc.content = content
        await db.flush()
        await db.refresh(doc)
        return doc
