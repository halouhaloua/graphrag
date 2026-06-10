from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.base_model import BaseModel


class WorkflowDef(BaseModel):
    """工作流定义"""

    __tablename__ = "ai_workflow_def"

    name = Column(String(200), nullable=False, index=True, comment="工作流名称")
    description = Column(Text, nullable=True, comment="描述")
    nodes = Column(
        Text, nullable=False, comment="节点定义 JSON: [{id, type, params, position}]"
    )
    edges = Column(
        Text,
        nullable=False,
        comment="边定义 JSON: [{source, target, sourceHandle, targetHandle}]",
    )
    global_params = Column(Text, nullable=True, comment="全局参数 JSON")
    is_published = Column(Boolean, default=False, comment="是否已发布")
    version = Column(Integer, default=1, comment="版本号")


class WorkflowInstance(BaseModel):
    """工作流运行实例"""

    __tablename__ = "ai_workflow_instance"

    workflow_def_id = Column(
        String(21),
        ForeignKey("ai_workflow_def.id"),
        nullable=False,
        index=True,
        comment="关联的工作流定义ID",
    )
    status = Column(
        String(20),
        default="pending",
        index=True,
        comment="状态: pending/running/completed/failed/cancelled",
    )
    input_params = Column(Text, nullable=True, comment="输入参数 JSON")
    output_result = Column(Text, nullable=True, comment="最终输出结果 JSON")
    error = Column(Text, nullable=True, comment="错误信息")
    started_at = Column(DateTime, nullable=True, comment="开始执行时间")
    finished_at = Column(DateTime, nullable=True, comment="执行完成时间")

    workflow_def = relationship("WorkflowDef", backref="instances")


class WorkflowNodeLog(BaseModel):
    """节点执行日志"""

    __tablename__ = "ai_workflow_node_log"

    instance_id = Column(
        String(21),
        ForeignKey("ai_workflow_instance.id"),
        nullable=False,
        index=True,
        comment="关联的执行实例ID",
    )
    node_id = Column(String(100), nullable=False, comment="节点ID")
    node_type = Column(String(100), nullable=False, comment="节点类型")
    status = Column(
        String(20), default="pending", comment="状态: pending/running/completed/failed"
    )
    input_data = Column(Text, nullable=True, comment="输入数据 JSON")
    output_data = Column(Text, nullable=True, comment="输出数据 JSON")
    error = Column(Text, nullable=True, comment="错误信息")
    started_at = Column(DateTime, nullable=True, comment="开始执行时间")
    finished_at = Column(DateTime, nullable=True, comment="执行完成时间")
    duration_ms = Column(Integer, nullable=True, comment="执行耗时(毫秒)")

    instance = relationship("WorkflowInstance", backref="node_logs")
