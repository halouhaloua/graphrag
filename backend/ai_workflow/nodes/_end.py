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
            "_main_node_result": {
                "type": "any",
                "default": None,
                "description": "主输出节点结果（由引擎自动注入）",
            },
        },
        "output": {"result": "上游主节点输出", "success": "是否成功"},
    },
)
class EndNode(BaseNode):
    """工作流结束节点

    接收引擎注入的 ``_main_node_result`` 并将主输出节点的结果作为最终结果返回。
    """

    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        main_result = params.get("_main_node_result")

        # 有主节点结果 → 直接返回（chat 或工具节点均可）
        if main_result is not None:
            return {"result": main_result, "success": True}

        # fallback: 返回全量上游输出
        upstream = params.get("_upstream_outputs", {})
        return {"result": upstream, "success": True}
