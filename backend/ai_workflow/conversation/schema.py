from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.base_schema import CSTDatetime


class ConversationCreate(BaseModel):
    """创建会话请求"""

    workflow_def_id: str = Field(..., description="工作流定义ID")


class ConversationOut(BaseModel):
    """会话响应"""

    id: str
    workflow_def_id: str
    title: Optional[str] = None
    turn_count: int = 0
    sys_create_datetime: Optional[CSTDatetime] = None

    model_config = ConfigDict(from_attributes=True)


class TurnRequest(BaseModel):
    """发送消息请求"""

    message: str = Field(..., min_length=1, max_length=10000, description="用户消息")


class TurnOut(BaseModel):
    """一轮对话的输出"""

    turn_index: int
    input_message: str
    output_result: Optional[Any] = None
    status: str = "completed"
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
