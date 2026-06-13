"""本地子进程沙箱执行器

在不依赖外部沙箱 API 的情况下，通过 ``subprocess`` + ``tempfile`` 在开发环境中
本地执行 Python / Shell 代码。

**⚠️ 安全说明**
此执行器仅提供进程级隔离（临时目录、超时终止），**不提供安全沙箱**。
仅用于开发环境测试简单代码片段。生产环境请使用 ``ApiSandboxExecutor``。
"""

import asyncio
import logging
import os
import signal
import sys
import tempfile
from typing import Optional

from ai_workflow.sandbox.base import AbstractSandboxExecutor, ExecutorResult

logger = logging.getLogger(__name__)

# Windows 下阻止弹出控制台窗口
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class LocalSandboxExecutor(AbstractSandboxExecutor):
    """本地子进程沙箱执行器

    通过 ``asyncio.create_subprocess_exec`` 执行代码，每个调用使用独立的
    临时工作目录，并强制超时。
    """

    def __init__(self, log: Optional[logging.Logger] = None):
        self._log = log or logger

    async def execute(
        self,
        code: str,
        language: str,
        enable_network: bool,
        timeout: float,
    ) -> ExecutorResult:
        if language not in ("python", "shell"):
            return ExecutorResult(
                success=False,
                error=f"不支持的 language: {language}",
            )

        if not enable_network:
            self._log.warning(
                "LocalSandboxExecutor: enable_network=False 在本地模式下无效，"
                "代码始终可访问网络。"
            )

        if language == "python":
            return await self._run_python(code, timeout)
        return await self._run_shell(code, timeout)

    async def _run_python(self, code: str, timeout: float) -> ExecutorResult:
        """使用当前 Python 解释器执行代码"""
        # ignore_cleanup_errors=True: Windows 可能因进程句柄锁定临时目录,
        # 出错时忽略清理失败，由系统后续清理
        with tempfile.TemporaryDirectory(
            prefix="sandbox_py_", ignore_cleanup_errors=True
        ) as work_dir:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                creationflags=_CREATE_NO_WINDOW,
            )
            return await self._collect_result(proc, timeout)

    async def _run_shell(self, code: str, timeout: float) -> ExecutorResult:
        """使用系统 shell 执行命令"""
        shell_cmd = self._get_shell_cmd()
        with tempfile.TemporaryDirectory(
            prefix="sandbox_sh_", ignore_cleanup_errors=True
        ) as work_dir:
            proc = await asyncio.create_subprocess_exec(
                *shell_cmd,
                code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                creationflags=_CREATE_NO_WINDOW,
            )
            return await self._collect_result(proc, timeout)

    async def _collect_result(
        self,
        proc: asyncio.subprocess.Process,
        timeout: float,
    ) -> ExecutorResult:
        """收集子进程输出，强制超时"""
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            self._kill_orphan(proc)
            return ExecutorResult(
                success=False,
                error=f"代码执行超时 ({timeout}s)",
                stderr=f"Timeout after {timeout}s",
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        if proc.returncode == 0:
            return ExecutorResult(stdout=stdout, stderr=stderr, success=True)

        return ExecutorResult(
            stdout=stdout,
            stderr=stderr,
            success=False,
            error=f"进程退出码: {proc.returncode}",
        )

    @staticmethod
    def _kill_orphan(proc: asyncio.subprocess.Process):
        """强制终止超时子进程（尽力而为）"""
        try:
            proc.kill()
        except ProcessLookupError:
            pass

        # Unix 下同时终止进程组
        if sys.platform != "win32" and proc.pid:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass

    @staticmethod
    def _get_shell_cmd() -> list[str]:
        """返回当前平台可用的 shell 命令"""
        if sys.platform == "win32":
            return ["cmd", "/c"]
        return ["bash", "-c"]
