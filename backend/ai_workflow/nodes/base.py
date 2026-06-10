from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class NodeContext:
    """节点执行上下文

    工作流引擎在每次执行节点时创建并注入此上下文，
    节点可通过此对象访问外部服务。
    """

    db: AsyncSession
    settings: Any
    logger: Any
    node_id: str = ""
    instance_id: str = ""
    workflow_name: str = ""
    stream_queue: Any = None


class BaseNode(ABC):
    """节点基类

    所有工作流节点必须继承此类并实现 execute 方法。
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        """执行节点

        Args:
            params: 节点参数
            context: 执行上下文（含 db session、settings、logger 等）

        Returns:
            Dict[str, Any]: 执行结果，必须包含 'result' 键
        """
