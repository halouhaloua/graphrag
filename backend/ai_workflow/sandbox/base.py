"""沙箱执行器抽象基类

定义 ``ExecutorResult`` 数据类和 ``AbstractSandboxExecutor`` 抽象接口，
供 ``ApiSandboxExecutor`` 和 ``LocalSandboxExecutor`` 统一实现。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ExecutorResult:
    """沙箱执行的标准返回结果"""

    stdout: str = ""
    stderr: str = ""
    success: bool = False
    error: str = ""  # 人类可读的错误描述（success=True 时为空）


class AbstractSandboxExecutor(ABC):
    """代码沙箱执行器抽象接口"""

    @abstractmethod
    async def execute(
        self,
        code: str,
        language: str,
        enable_network: bool,
        timeout: float,
    ) -> ExecutorResult:
        """执行代码并返回标准化结果

        Args:
            code: 要执行的源代码
            language: "python" 或 "shell"
            enable_network: 是否允许网络访问
            timeout: 超时秒数

        Returns:
            ExecutorResult: 标准化执行结果
        """
