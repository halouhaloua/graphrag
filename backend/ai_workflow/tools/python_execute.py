import json

import os
from typing import Any, Dict

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import register_node
from ai_workflow.sandbox import get_executor



@register_node(
    "python_execute",
    metadata={
        "name": "Python/Shell代码执行",
        "description": "在沙箱环境中执行Python/Shell代码",
        "params": {
            "code": {"type": "str", "required": True, "description": "要执行的代码"},
            "language": {
                "type": "str",
                "default": "python",
                "description": "python 或 shell",
            },
            "enable_network": {
                "type": "bool",
                "default": True,
                "description": "是否允许网络访问",
            },
            "variables": {
                "type": "dict",
                "default": {},
                "description": "传递给代码的变量",
            },
        },
        "output": {
            "result": "标准输出",
            "stdout": "标准输出",
            "stderr": "标准错误",
            "success": "是否成功",
        },
    },
)
class PythonExecuteNode(BaseNode):
    """Python/Shell代码执行节点

    通过沙箱执行器（``ApiSandboxExecutor`` 或 ``LocalSandboxExecutor``）执行代码。
    执行器由 ``SANDBOX_MODE`` 环境变量控制：
    - ``api``（默认） → 外部沙箱 API
    - ``local`` → 本地子进程（仅用于开发环境）
    """

    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        code = str(params.get("code", ""))
        if not code:
            raise ValueError("code参数不能为空")

        language = str(params.get("language", "python")).lower()
        if language not in ("python", "shell"):
            raise ValueError("language参数必须是python或shell")

        enable_network = params.get("enable_network", True)

        variables = params.get("variables", {})
        if isinstance(variables, str):
            variables = json.loads(variables)
        if not isinstance(variables, dict):
            raise ValueError("variables参数必须是字典类型")

        # 变量注入：在用户代码前插入变量赋值语句
        if language == "python" and variables:
            var_code = "\n".join(f"{k} = {repr(v)}" for k, v in variables.items())
            code = f"{var_code}\n{code}"

        # 委托执行器执行
        executor = get_executor()
        result = await executor.execute(
            code=code,
            language=language,
            enable_network=enable_network,
            timeout=float(
                params.get("_timeout") or os.getenv("SANDBOX_REQUEST_TIMEOUT", "3600")
            ),
        )

        if not result.success:
            return {
                "result": None,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": False,
                "error": result.error,
            }

        return {
            "result": result.stdout,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": True,
        }
