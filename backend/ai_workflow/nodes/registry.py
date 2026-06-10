from typing import Type, Dict, Optional

from ai_workflow.nodes.base import BaseNode


_node_registry: Dict[str, Type[BaseNode]] = {}
_node_metadata: Dict[str, dict] = {}


def register_node(node_type: str, metadata: Optional[dict] = None):
    """注册节点类型的装饰器

    Args:
        node_type: 节点类型标识符（如 "python_execute"）
        metadata: 节点元数据（名称、描述、参数定义等），可选

    Usage:
        @register_node("python_execute", metadata={"name": "Python执行", ...})
        class PythonExecuteNode(BaseNode):
            ...
    """

    def decorator(cls):
        _node_registry[node_type] = cls
        if metadata:
            _node_metadata[node_type] = metadata
        return cls

    return decorator


class NodeRegistry:
    """节点注册中心"""

    @classmethod
    def get(cls, node_type: str) -> Optional[Type[BaseNode]]:
        """根据类型获取节点类"""
        return _node_registry.get(node_type)

    @classmethod
    def get_all_types(cls) -> list[str]:
        """获取所有已注册的节点类型列表"""
        return list(_node_registry.keys())

    @classmethod
    def get_metadata(cls, node_type: str) -> Optional[dict]:
        """获取节点类型的元数据"""
        return _node_metadata.get(node_type)

    @classmethod
    def get_all_metadata(cls) -> list[dict]:
        """获取所有节点的元数据列表"""
        return list(_node_metadata.values())

    @classmethod
    def register(
        cls, node_type: str, node_class: Type[BaseNode], metadata: Optional[dict] = None
    ):
        """直接注册节点类型（非装饰器方式）"""
        _node_registry[node_type] = node_class
        if metadata:
            _node_metadata[node_type] = metadata
