from typing import Any, Dict

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import register_node


@register_node(
    "_end",
    metadata={
        "name": "结束",
        "description": "工作流终点，无实际操作",
        "params": {},
        "output": {"result": "结束信号"},
    },
)
class EndNode(BaseNode):
    """工作流结束节点

    作为 DAG 的终点节点，无实际操作，仅返回结束信号。
    """

    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        return {"result": "end", "success": True}
