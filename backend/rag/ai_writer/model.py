from sqlalchemy import Column, String, Text
from app.base_model import BaseModel as AppBaseModel


class WriterConversation(AppBaseModel):
    __tablename__ = "rag_writer_conversations"
    title = Column(String(200), nullable=False, default="新对话", comment="会话标题")
    user_id = Column(String(21), nullable=False, index=True, comment="用户ID")
    model_name = Column(
        String(100), nullable=False, default="default", comment="使用的大模型名称"
    )


class WriterMessage(AppBaseModel):
    __tablename__ = "rag_writer_messages"
    conversation_id = Column(String(21), nullable=False, index=True, comment="会话ID")
    role = Column(String(20), nullable=False, comment="消息角色：user/assistant/system")
    content = Column(Text, nullable=False, comment="消息内容")
    model_name = Column(String(100), nullable=True, comment="该条消息使用的模型")


class WriterDocument(AppBaseModel):
    __tablename__ = "rag_writer_documents"
    conversation_id = Column(String(21), nullable=False, index=True, comment="所属会话ID")
    message_id = Column(String(21), nullable=False, index=True, comment="来源消息ID")
    title = Column(String(200), nullable=False, default="未命名文档", comment="文档标题")
    content = Column(Text, nullable=False, comment="文档内容（HTML格式）")
