"""节点工具适配器

将 ``@register_node`` 注册的节点动态适配为 AgentScope ``ToolBase``，
使团队执行器能通过 AgentScope Toolkit 调用节点作为标准 OpenAI 工具。
"""

import json
import logging
from typing import Any

from agentscope.message import TextBlock
from agentscope.permission import (
    PermissionBehavior,
    PermissionContext,
    PermissionDecision,
)
from agentscope.tool import ToolBase, ToolChunk

from ai_workflow.nodes.base import NodeContext
from ai_workflow.nodes.registry import NodeRegistry

logger = logging.getLogger(__name__)

_TYPE_MAP = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
}


def _build_schema(params: dict | None) -> dict:
    """将节点 params 元数据转为 JSON Schema"""
    if not params:
        return {"type": "object", "properties": {}}
    properties = {}
    required: list[str] = []
    for name, p in params.items():
        json_type = _TYPE_MAP.get(p.get("type", ""), "string")
        prop: dict[str, Any] = {
            "type": json_type,
            "description": p.get("description", ""),
        }
        default = p.get("default")
        if default is not None:
            prop["default"] = default
        properties[name] = prop
        if p.get("required"):
            required.append(name)
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


class NodeToolAdapter(ToolBase):
    """动态将注册节点适配为 AgentScope Tool

    从 ``NodeRegistry`` 读取节点的 metadata（name, description, params）
    自动生成 ``input_schema``，执行时实例化节点并调用 ``execute()``。
    """

    def __init__(
        self, node_type: str, settings: Any, log: logging.Logger | None = None
    ) -> None:
        self._node_type = node_type
        self._settings = settings
        self._log = log or logger
        meta = NodeRegistry.get_metadata(node_type) or {}
        self.name = node_type
        self.description = meta.get("description", "")
        self.input_schema = _build_schema(meta.get("params"))
        self.is_concurrency_safe = True

    async def check_permissions(
        self,
        tool_input: dict,
        context: PermissionContext,
    ) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW)

    async def __call__(self, **kwargs: Any) -> ToolChunk:
        node_cls = NodeRegistry.get(self._node_type)
        if not node_cls:
            return ToolChunk(
                content=[
                    TextBlock(
                        text=json.dumps(
                            {"error": f"未知节点类型: {self._node_type}"},
                            ensure_ascii=False,
                        )
                    )
                ],
            )
        try:
            node = node_cls()
            ctx = NodeContext(
                db=None,
                settings=self._settings,
                logger=self._log,
                node_id=self._node_type,
                instance_id="",
            )
            result = await node.execute(kwargs, ctx)
            return ToolChunk(
                content=[TextBlock(text=json.dumps(result, ensure_ascii=False))],
            )
        except Exception as e:
            self._log.exception("工具 %s 执行失败", self._node_type)
            return ToolChunk(
                content=[
                    TextBlock(text=json.dumps({"error": str(e)}, ensure_ascii=False))
                ],
            )
