import json
from typing import Optional, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.base_schema import CSTDatetime


class WorkflowDefNodeSchema(BaseModel):
    """工作流节点定义"""

    id: str = Field(..., description="节点ID")
    type: str = Field(..., description="节点类型")
    params: dict = Field(default_factory=dict, description="节点参数")
    position: Optional[dict] = Field(None, description="画布位置 {x, y}")
    error_mode: str = Field(default="stop", description="错误处理模式: stop/continue")


class WorkflowDefEdgeSchema(BaseModel):
    """工作流边定义"""

    source: str = Field(..., description="源节点ID")
    target: str = Field(..., description="目标节点ID")
    sourceHandle: Optional[str] = Field(None, description="源节点输出端口")
    targetHandle: Optional[str] = Field(None, description="目标节点输入端口")


class WorkflowDefCreate(BaseModel):
    """创建工作流定义"""

    name: str = Field(..., min_length=1, max_length=200, description="工作流名称")
    description: Optional[str] = Field(None, description="描述")
    nodes: list[WorkflowDefNodeSchema] = Field(
        default_factory=list, description="节点列表"
    )
    edges: list[WorkflowDefEdgeSchema] = Field(
        default_factory=list, description="边列表"
    )
    global_params: Optional[dict] = Field(None, description="全局参数")


class WorkflowDefUpdate(BaseModel):
    """更新工作流定义"""

    name: Optional[str] = Field(
        None, min_length=1, max_length=200, description="工作流名称"
    )
    description: Optional[str] = Field(None, description="描述")
    nodes: Optional[list[WorkflowDefNodeSchema]] = Field(None, description="节点列表")
    edges: Optional[list[WorkflowDefEdgeSchema]] = Field(None, description="边列表")
    global_params: Optional[dict] = Field(None, description="全局参数")
    is_published: Optional[bool] = Field(None, description="是否已发布")


class WorkflowDefOut(BaseModel):
    """工作流定义输出"""

    id: str
    name: str
    description: Optional[str] = None
    nodes: list[WorkflowDefNodeSchema]
    edges: list[WorkflowDefEdgeSchema]
    global_params: Optional[Any] = None
    is_published: bool = False
    version: int = 1
    sort: int = 0
    is_deleted: bool = False
    sys_create_datetime: Optional[CSTDatetime] = None
    sys_update_datetime: Optional[CSTDatetime] = None

    @field_validator("nodes", "edges", "global_params", mode="before")
    @classmethod
    def parse_json_fields(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    model_config = ConfigDict(from_attributes=True)


class WorkflowInstanceOut(BaseModel):
    """工作流实例输出"""

    id: str
    workflow_def_id: str
    status: str = "pending"
    input_params: Optional[Any] = None
    output_result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[CSTDatetime] = None
    finished_at: Optional[CSTDatetime] = None
    sort: int = 0
    is_deleted: bool = False
    sys_create_datetime: Optional[CSTDatetime] = None
    sys_update_datetime: Optional[CSTDatetime] = None

    @field_validator("input_params", "output_result", mode="before")
    @classmethod
    def parse_json_fields(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    model_config = ConfigDict(from_attributes=True)


class WorkflowNodeLogOut(BaseModel):
    """节点执行日志输出"""

    id: str
    instance_id: str
    node_id: str
    node_type: str
    status: str = "pending"
    input_data: Optional[Any] = None
    output_data: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[CSTDatetime] = None
    finished_at: Optional[CSTDatetime] = None
    duration_ms: Optional[int] = None

    @field_validator("input_data", "output_data", mode="before")
    @classmethod
    def parse_json_fields(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    model_config = ConfigDict(from_attributes=True)


class WorkflowRunRequest(BaseModel):
    """执行工作流请求"""

    input_params: Optional[dict] = Field(None, description="输入参数")
