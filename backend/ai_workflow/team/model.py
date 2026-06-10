from sqlalchemy import Column, String, Text, Boolean

from app.base_model import BaseModel


class TeamConfig(BaseModel):
    """团队配置

    存储多智能体团队的定义，包括团队规则、角色列表和可用工具。
    角色定义以 JSON 格式存储在 ``roles`` 字段中。
    """

    __tablename__ = "ai_workflow_team_config"

    name = Column(String(200), nullable=False, index=True, comment="团队名称")
    description = Column(Text, nullable=True, comment="描述")
    team_rules = Column(Text, nullable=False, comment="团队规则与目标描述")
    start_role = Column(String(50), nullable=False, comment="起始角色名称")
    roles = Column(Text, nullable=False, comment="角色定义 JSON")
    yaml_source = Column(Text, nullable=True, comment="原始YAML内容（可选）")
    is_active = Column(Boolean, default=True, comment="是否启用")
