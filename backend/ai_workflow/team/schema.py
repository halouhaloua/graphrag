import json
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.base_schema import CSTDatetime


class TeamRoleSchema(BaseModel):
    """团队角色定义"""

    tools: list[str] = Field(default_factory=list, description="可用工具列表")
    agent_description: str = Field("", description="角色描述")
    model_name: str = Field("deepseek-chat", description="使用的模型")
    max_iterations: int = Field(25, ge=1, le=100, description="最大迭代次数")
    termination_conditions: list[dict] = Field(
        default_factory=list, description="终止条件"
    )


class TeamConfigCreate(BaseModel):
    """创建团队配置"""

    name: str = Field(..., min_length=1, max_length=200, description="团队名称")
    description: Optional[str] = Field(None, description="描述")
    team_rules: str = Field(..., description="团队规则")
    start_role: str = Field(..., description="起始角色名称")
    roles: dict[str, TeamRoleSchema] = Field(..., description="角色定义")


class TeamConfigUpdate(BaseModel):
    """更新团队配置"""

    name: Optional[str] = Field(
        None, min_length=1, max_length=200, description="团队名称"
    )
    description: Optional[str] = Field(None, description="描述")
    team_rules: Optional[str] = Field(None, description="团队规则")
    start_role: Optional[str] = Field(None, description="起始角色名称")
    roles: Optional[dict[str, TeamRoleSchema]] = Field(None, description="角色定义")
    is_active: Optional[bool] = Field(None, description="是否启用")


class TeamConfigOut(BaseModel):
    """团队配置输出"""

    id: str
    name: str
    description: Optional[str] = None
    team_rules: str
    start_role: str
    roles: dict[str, TeamRoleSchema]
    yaml_source: Optional[str] = None
    is_active: bool = True
    sort: int = 0
    is_deleted: bool = False
    sys_create_datetime: Optional[CSTDatetime] = None
    sys_update_datetime: Optional[CSTDatetime] = None

    @field_validator("roles", mode="before")
    @classmethod
    def parse_roles(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    model_config = ConfigDict(from_attributes=True)


class TeamRunRequest(BaseModel):
    """运行团队请求"""

    input_params: Optional[dict] = Field(None, description="输入参数")


class TeamYamlImport(BaseModel):
    """从YAML导入团队配置"""

    yaml_content: str = Field(..., description="YAML内容")
    name: Optional[str] = Field(None, description="团队名称（默认用文件名）")
    description: Optional[str] = Field(None, description="描述")
