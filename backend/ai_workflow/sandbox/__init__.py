"""沙箱执行器

通过 ``get_executor()`` 工厂函数根据环境变量 ``SANDBOX_MODE`` 选择执行器：

- ``SANDBOX_MODE=api``（默认） → ``ApiSandboxExecutor`` — 外部 HTTP API
- ``SANDBOX_MODE=local`` → ``LocalSandboxExecutor`` — 本地子进程
"""

import os

from ai_workflow.sandbox.base import AbstractSandboxExecutor, ExecutorResult
from ai_workflow.sandbox.api_executor import ApiSandboxExecutor
from ai_workflow.sandbox.local_executor import LocalSandboxExecutor


def get_executor() -> AbstractSandboxExecutor:
    """工厂函数：根据环境变量选择沙箱执行器

    Returns:
        ``ApiSandboxExecutor``（默认）或 ``LocalSandboxExecutor``
    """
    mode = os.getenv("SANDBOX_MODE", "api").lower()

    if mode == "local":
        return LocalSandboxExecutor()

    # 默认：外部 API 执行器
    return ApiSandboxExecutor(
        host=os.getenv("SANDBOX_HOST", "127.0.0.1"),
        port=int(os.getenv("SANDBOX_PORT", "8000")),
        api_key=os.getenv("SANDBOX_API_KEY", ""),
    )


__all__ = [
    "AbstractSandboxExecutor",
    "ExecutorResult",
    "get_executor",
    "ApiSandboxExecutor",
    "LocalSandboxExecutor",
]
