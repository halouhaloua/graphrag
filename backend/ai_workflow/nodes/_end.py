from typing import Any, Dict

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import register_node


@register_node(
    "_end",
    metadata={
        "name": "结束",
        "description": "工作流终点，汇总上游节点输出",
        "params": {
            "_upstream_outputs": {
                "type": "dict",
                "default": {},
                "description": "上游节点输出汇总（由引擎自动注入）",
            },
        },
        "output": {"result": "上游节点输出汇总结果", "success": "是否成功"},
    },
)
class EndNode(BaseNode):
    """工作流结束节点

    接收引擎注入的 ``_upstream_outputs`` 并将上游节点输出合并为最终结果。
    """

    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        upstream = params.get("_upstream_outputs", {})
        # 取最后一个非 _end 节点的 result 作为主结果，同时保留全部上游输出
        return {"result": upstream, "success": True}
