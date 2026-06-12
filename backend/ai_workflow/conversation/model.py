from sqlalchemy import Column, String, ForeignKey

from app.base_model import BaseModel


class WorkflowConversation(BaseModel):
    """对话会话（用于 AI 工作流多轮对话）"""

    __tablename__ = "ai_workflow_conversation"

    workflow_def_id = Column(
        String(21),
        ForeignKey("ai_workflow_def.id"),
        nullable=False,
        index=True,
        comment="关联的工作流定义ID",
    )
    title = Column(String(200), nullable=True, comment="会话标题（从首条消息自动生成）")
