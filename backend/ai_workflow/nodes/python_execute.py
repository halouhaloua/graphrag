import json
import os
import logging

import httpx
from typing import Any, Dict

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import register_node

logger = logging.getLogger(__name__)


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

    通过沙箱API执行代码，支持变量注入和网络控制。
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

        sandbox_host = os.getenv("SANDBOX_HOST", "127.0.0.1")
        sandbox_port = int(os.getenv("SANDBOX_PORT", "8000"))
        sandbox_api_key = os.getenv("SANDBOX_API_KEY", "")
        sandbox_timeout = float(os.getenv("SANDBOX_REQUEST_TIMEOUT", "3600"))

        # 协议探测：保持显式协议不变；裸主机名 → localhost 用 http，远程用 https
        if "http://" not in sandbox_host and "https://" not in sandbox_host:
            is_local = sandbox_host in ("127.0.0.1", "localhost", "0.0.0.0", "::1")
            sandbox_host = ("http://" if is_local else "https://") + sandbox_host

        # 安全检查：API key 通过 HTTP 发送到非 localhost 时记录警告
        if sandbox_api_key and sandbox_host.startswith("http://"):
            host_only = sandbox_host[len("http://"):]
            if ":" in host_only:
                host_only = host_only.split(":")[0]
            if host_only not in ("127.0.0.1", "localhost", "0.0.0.0", "::1"):
                logger.warning(
                    "SECURITY: Sandbox API key sent over HTTP to %s. "
                    "Use https:// for SANDBOX_HOST in production.",
                    host_only,
                )

        api_url = f"{sandbox_host}:{sandbox_port}/v1/sandbox/run"

        if language == "python" and variables:
            var_code = "\n".join(f"{k} = {repr(v)}" for k, v in variables.items())
            code = f"{var_code}\n{code}"

        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {sandbox_api_key}",
            }
            payload = {
                "code": code,
                "language": language,
                "enable_network": enable_network,
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    api_url,
                    headers=headers,
                    json=payload,
                    timeout=sandbox_timeout,
                )
                response.raise_for_status()
                api_result = response.json()

            if api_result.get("code") != 0:
                error_msg = api_result.get("stderr", "沙箱执行失败")
                return {
                    "result": None,
                    "stdout": "",
                    "stderr": error_msg,
                    "success": False,
                    "error": error_msg,
                }

            stdout = api_result.get("stdout", "")
            return {
                "result": stdout,
                "stdout": stdout,
                "stderr": api_result.get("stderr", ""),
                "success": True,
            }

        except httpx.HTTPStatusError as e:
            error = f"沙箱API请求失败: {e}"
            logger.error(error)
            return {
                "result": None,
                "stdout": "",
                "stderr": error,
                "success": False,
                "error": error,
            }
        except Exception as e:
            error = f"沙箱执行错误: {e}"
            logger.error(error)
            return {
                "result": None,
                "stdout": "",
                "stderr": error,
                "success": False,
                "error": error,
            }
