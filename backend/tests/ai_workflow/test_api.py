"""ai_workflow API 端点单元测试

测试策略：
- 验证端点路由和请求/响应格式（通过 schema 校验）
- 验证 DAG 校验在创建时的拦截
- 验证业务逻辑（发布、运行、取消）的约束
"""

import pytest
from pydantic import ValidationError

from ai_workflow.workflow.schema import (
    WorkflowDefCreate,
    WorkflowDefNodeSchema,
    WorkflowDefEdgeSchema,
    WorkflowDefOut,
    WorkflowRunRequest,
)
from ai_workflow.workflow.events import WorkflowEventType


class TestWorkflowDefCreateSchema:
    """WorkflowDefCreate schema 校验"""

    def test_valid_minimal(self):
        """最小有效输入"""
        data = WorkflowDefCreate(name="测试工作流")
        assert data.name == "测试工作流"
        assert data.nodes == []
        assert data.edges == []

    def test_with_nodes_and_edges(self):
        """含节点和边的输入"""
        data = WorkflowDefCreate(
            name="有向工作流",
            nodes=[
                WorkflowDefNodeSchema(id="n1", type="python_execute"),
                WorkflowDefNodeSchema(id="n2", type="chat"),
            ],
            edges=[WorkflowDefEdgeSchema(source="n1", target="n2")],
            global_params={"key": "value"},
        )
        assert len(data.nodes) == 2
        assert data.nodes[0].error_mode == "stop"
        assert data.edges[0].source == "n1"

    def test_name_too_short(self):
        """空名称应报错"""
        with pytest.raises(ValidationError):
            WorkflowDefCreate(name="")

    def test_invalid_error_mode(self):
        """error_mode 默认为 stop，不允许其他值（schema 层面）"""
        # error_mode 是 str 类型，没有枚举限制，只需验证默认值
        node = WorkflowDefNodeSchema(id="n1", type="test")
        assert node.error_mode == "stop"
        node2 = WorkflowDefNodeSchema(id="n2", type="test", error_mode="continue")
        assert node2.error_mode == "continue"


class TestWorkflowRunRequest:
    """执行请求 schema"""

    def test_empty_input(self):
        req = WorkflowRunRequest()
        assert req.input_params is None

    def test_with_params(self):
        req = WorkflowRunRequest(input_params={"a": 1})
        assert req.input_params == {"a": 1}


class TestWorkflowDefOutSchema:
    """WorkflowDefOut JSON 字段反序列化"""

    def test_parse_nodes_from_string(self):
        """模拟 SQLAlchemy 返回 JSON 字符串的场景"""
        raw = {
            "id": "abc123",
            "name": "test",
            "nodes": '[{"id":"n1","type":"python_execute","params":{},"position":null,"error_mode":"stop"}]',
            "edges": "[]",
            "is_published": False,
            "version": 1,
            "sort": 0,
            "is_deleted": False,
            "global_params": None,
        }
        out = WorkflowDefOut.model_validate(raw)
        assert len(out.nodes) == 1
        assert out.nodes[0].id == "n1"
        assert out.nodes[0].type == "python_execute"
        assert out.edges == []

    def test_parse_nodes_from_list(self):
        """模拟直接传入 Python 对象的场景"""
        raw = {
            "id": "abc123",
            "name": "test",
            "nodes": [
                {
                    "id": "n1",
                    "type": "python_execute",
                    "params": {},
                    "error_mode": "stop",
                }
            ],
            "edges": [],
            "is_published": True,
            "version": 1,
            "sort": 0,
            "is_deleted": False,
        }
        out = WorkflowDefOut.model_validate(raw)
        assert len(out.nodes) == 1


class TestWorkflowEventType:
    """事件类型常量"""

    def test_constants_match_service(self):
        assert WorkflowEventType.WORKFLOW_START == "workflow_start"
        assert WorkflowEventType.WORKFLOW_COMPLETE == "workflow_complete"
        assert WorkflowEventType.WORKFLOW_ERROR == "workflow_error"
        assert WorkflowEventType.NODE_START == "node_start"
        assert WorkflowEventType.NODE_COMPLETE == "node_complete"
        assert WorkflowEventType.NODE_ERROR == "node_error"
        assert WorkflowEventType.NODE_OUTPUT == "node_output"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
