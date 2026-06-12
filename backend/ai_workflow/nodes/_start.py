from typing import Any, Dict

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import register_node


@register_node(
    "_start",
    metadata={
        "name": "开始",
        "description": "工作流起点，接收用户输入并传递给下游",
        "params": {
            "user_input_description": {
                "type": "str",
                "default": "",
                "description": "用户输入提示（如：请输入您的问题）",
            },
        },
        "output": {"result": "启动信号"},
    },
)
class StartNode(BaseNode):
    """工作流开始节点

    作为 DAG 的入口节点，用户输入通过引擎注入为 ``_input`` 变量供下游节点引用。
    """

    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        _input = params.get("_input", {})
        msg = _input.get("message", "") if isinstance(_input, dict) else ""
        return {"result": msg or "start", "success": True}
