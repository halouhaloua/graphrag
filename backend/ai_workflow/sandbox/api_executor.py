"""外部沙箱 API 执行器

通过 HTTP 调用外部沙箱服务执行代码，使用 Bearer Token 认证。
与 ``LocalSandboxExecutor`` 共享 ``AbstractSandboxExecutor`` 接口。
"""

import logging
from typing import Any

import httpx

from ai_workflow.sandbox.base import AbstractSandboxExecutor, ExecutorResult

logger = logging.getLogger(__name__)


class ApiSandboxExecutor(AbstractSandboxExecutor):
    """通过外部沙箱 API 执行代码"""

    def __init__(self, host: str, port: int, api_key: str):
        self._api_url = self._build_url(host, port)
        self._api_key = api_key
        self._log_security_warning(host)

    @staticmethod
    def _build_url(host: str, port: int) -> str:
        """构建沙箱 API URL，含协议探测"""
        if "http://" not in host and "https://" not in host:
            is_local = host in ("127.0.0.1", "localhost", "0.0.0.0", "::1")
            host = ("http://" if is_local else "https://") + host
        return f"{host}:{port}/v1/sandbox/run"

    def _log_security_warning(self, host: str):
        """API key 通过 HTTP 发送到非 localhost 时记录安全警告"""
        if not self._api_key:
            return
        if not host.startswith("http://"):
            return
        host_only = host[len("http://") :].split(":")[0]
        if host_only not in ("127.0.0.1", "localhost", "0.0.0.0", "::1"):
            logger.warning(
                "SECURITY: Sandbox API key sent over HTTP to %s. "
                "Use https:// for SANDBOX_HOST in production.",
                host_only,
            )

    async def execute(
        self,
        code: str,
        language: str,
        enable_network: bool,
        timeout: float,
    ) -> ExecutorResult:
        """通过外部沙箱 API 执行代码"""
        try:
            headers: dict[str, str] = {
                "Content-Type": "application/json",
            }
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            payload: dict[str, Any] = {
                "code": code,
                "language": language,
                "enable_network": enable_network,
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._api_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                )
                response.raise_for_status()
                api_result = response.json()

            if api_result.get("code") != 0:
                error_msg = api_result.get("stderr", "沙箱执行失败")
                return ExecutorResult(
                    success=False,
                    error=error_msg,
                    stderr=error_msg,
                )

            return ExecutorResult(
                stdout=api_result.get("stdout", ""),
                stderr=api_result.get("stderr", ""),
                success=True,
            )

        except httpx.HTTPStatusError as e:
            error = f"沙箱API请求失败: {e}"
            logger.error(error)
            return ExecutorResult(success=False, error=error, stderr=error)

        except Exception as e:
            error = f"沙箱执行错误: {e}"
            logger.error(error)
            return ExecutorResult(success=False, error=error, stderr=error)
