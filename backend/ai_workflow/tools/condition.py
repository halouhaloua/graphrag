"""条件判断节点

评估条件表达式，返回布尔值和分支标识。
用于工作流中的分支路由，下游节点可通过 ``${node_id.condition_met}`` 或
``${node_id.branch}`` 引用判断结果。
"""

import logging
from typing import Any, Dict

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import register_node

logger = logging.getLogger(__name__)

_OPERATORS = {
    "equals": lambda left, right: left == right,
    "not_equals": lambda left, right: left != right,
    "contains": lambda left, right: right in left if left else False,
    "gt": lambda left, right: _to_num(left) > _to_num(right) if _is_numeric(left, right) else str(left) > str(right),
    "gte": lambda left, right: _to_num(left) >= _to_num(right) if _is_numeric(left, right) else str(left) >= str(right),
    "lt": lambda left, right: _to_num(left) < _to_num(right) if _is_numeric(left, right) else str(left) < str(right),
    "lte": lambda left, right: _to_num(left) <= _to_num(right) if _is_numeric(left, right) else str(left) <= str(right),
    "is_empty": lambda left, _: left is None or left == "" or left == [],
    "is_not_empty": lambda left, _: left is not None and left != "" and left != [],
    "starts_with": lambda left, right: str(left).startswith(str(right)) if left else False,
    "ends_with": lambda left, right: str(left).endswith(str(right)) if left else False,
}


def _to_num(value: Any) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return float("nan")


def _is_numeric(left: Any, right: Any) -> bool:
    for v in (left, right):
        if v is None or v == "":
            return False
        try:
            float(v)
        except (ValueError, TypeError):
            return False
    return True


@register_node(
    "condition",
    metadata={
        "name": "条件判断",
        "description": "根据表达式判断条件真假，用于工作流分支路由",
        "params": {
            "left": {
                "type": "str",
                "required": True,
                "description": "左值（支持 ${node.key} 引用）",
            },
            "operator": {
                "type": "str",
                "default": "equals",
                "description": (
                    "比较运算符: "
                    "equals/not_equals/contains/gt/gte/lt/lte/"
                    "is_empty/is_not_empty/starts_with/ends_with"
                ),
            },
            "right": {
                "type": "str",
                "default": "",
                "description": "右值（is_empty/is_not_empty 时可不填）",
            },
        },
        "output": {
            "result": "布尔值比较结果",
            "condition_met": "同 result",
            "branch": '"true" 或 "false" 字符串',
            "left_value": "左值实际值",
            "right_value": "右值实际值",
            "operator": "使用的运算符",
        },
    },
)
class ConditionNode(BaseNode):
    """条件判断节点

    评估 ``left`` 和 ``right`` 之间由 ``operator`` 定义的关系，
    返回布尔值和分支选择字符串。

    Usage::

        params:
          left: "${serper_search_01.result_count}"
          operator: "gt"
          right: "0"

        # 返回: {result: True, condition_met: True, branch: "true"}

    工作流中典型的分支模式::

        start → condition → [true 分支] → path_a → end
                           → [false 分支] → path_b → end
    """

    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        left = params.get("left")
        operator = str(params.get("operator", "equals")).lower().strip()
        right = params.get("right", "")

        if operator not in _OPERATORS:
            return {
                "result": False,
                "condition_met": False,
                "branch": "false",
                "left_value": left,
                "right_value": right,
                "operator": operator,
                "error": f"不支持的运算符: {operator}",
                "success": False,
            }

        try:
            result = _OPERATORS[operator](left, right)
        except Exception as e:
            logger.warning("条件判断失败 left=%r operator=%s right=%r: %s", left, operator, right, e)
            result = False

        return {
            "result": result,
            "condition_met": result,
            "branch": "true" if result else "false",
            "left_value": left,
            "right_value": right,
            "operator": operator,
        }
