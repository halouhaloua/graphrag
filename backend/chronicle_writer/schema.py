from typing import Optional, Literal
from pydantic import BaseModel, Field


class InterruptDecision(BaseModel):
    action: Literal["retry", "override", "skip"] = Field(
        ..., description="retry=重新考证 override=采用当前数据 skip=跳过"
    )
    override_data: Optional[dict] = Field(
        default=None, description="人工修正的数据，如 {claims: [{claim, corrected}]}"
    )


class ChronicleChatRequest(BaseModel):
    conversation_id: Optional[str] = Field(
        default=None, description="会话ID，不传则服务端自动创建"
    )
    question: str = Field(default="", description="用户消息")
    kb_ids: list[str] = Field(default=[], description="选定的知识库ID列表")
    project_config: Optional[dict] = Field(
        default=None,
        description="项目配置 {title, topic, chronicle_type, region_name, scope}",
    )
    interrupt_decision: Optional[InterruptDecision] = Field(
        default=None, description="中断决策（人工复核时使用）"
    )
