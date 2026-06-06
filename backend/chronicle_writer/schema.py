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


# ─── 响应模型 ───


class SectionNode(BaseModel):
    """章节树节点"""

    id: str
    title: str
    level: int
    sort_order: int
    content: str
    word_count: int
    status: str
    children: list["SectionNode"] = []


class ReviewItem(BaseModel):
    """审查记录"""

    id: str
    section_id: Optional[str] = None
    review_type: str
    severity: str
    issue: str
    suggestion: Optional[str] = None
    resolved: bool


class LogEntry(BaseModel):
    """工作流日志条目"""

    stage: str
    event_type: str
    message: Optional[str] = None
    created_at: str


class ProjectDetail(BaseModel):
    """项目详情（聚合章节树、审查摘要、报告）"""

    id: str
    title: str
    chronicle_type: str
    region_name: Optional[str] = None
    scope_description: Optional[str] = None
    status: str
    word_count: int
    report: Optional[str] = None
    conversation_id: Optional[str] = None
    sections: list[SectionNode]
    review_summary: dict[str, int]
    created_at: str


class SectionListResponse(BaseModel):
    items: list[SectionNode]
    total: int


class ReviewListResponse(BaseModel):
    items: list[ReviewItem]
    total: int


class LogListResponse(BaseModel):
    items: list[LogEntry]
    total: int
