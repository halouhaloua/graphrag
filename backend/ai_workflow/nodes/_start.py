from typing import Any, Dict

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import register_node


@register_node(
    "_start",
    metadata={
        "name": "开始",
        "description": "工作流起点，无实际操作",
        "params": {},
        "output": {"result": "启动信号"},
    },
)
class StartNode(BaseNode):
    """工作流开始节点

    作为 DAG 的入口节点，无实际操作，仅返回启动信号。
    """

    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        return {"result": "start", "success": True}
