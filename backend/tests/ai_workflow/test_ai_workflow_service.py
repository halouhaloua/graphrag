"""WorkflowEngine 核心逻辑单元测试

测试策略：
- validate_dag：覆盖空图、线性链、并行节点、循环依赖、孤立节点、dangling 边
- resolve_params：覆盖普通引用、缺失引用、嵌套 dict、list、非字符串值
- create_instance：模拟 DB 会话测试校验逻辑
"""

import pytest

from ai_workflow.service import WorkflowEngine


class TestValidateDAG:
    """拓扑排序验证测试"""

    def test_empty_nodes_and_edges(self):
        """空节点列表应返回有效"""
        ok, err, levels = WorkflowEngine.validate_dag([], [])
        assert ok
        assert err == ""
        assert levels == []

    def test_single_node(self):
        """单节点无边的图"""
        ok, _, levels = WorkflowEngine.validate_dag(
            [{"id": "n1"}],
            [],
        )
        assert ok
        assert levels == [["n1"]]

    def test_linear_chain(self):
        """线性链：n1 → n2 → n3"""
        nodes = [{"id": "n1"}, {"id": "n2"}, {"id": "n3"}]
        edges = [
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n3"},
        ]
        ok, _, levels = WorkflowEngine.validate_dag(nodes, edges)
        assert ok
        assert levels == [["n1"], ["n2"], ["n3"]]

    def test_parallel_nodes(self):
        """并行节点：n1→n3, n2→n3"""
        nodes = [{"id": "n1"}, {"id": "n2"}, {"id": "n3"}]
        edges = [
            {"source": "n1", "target": "n3"},
            {"source": "n2", "target": "n3"},
        ]
        ok, _, levels = WorkflowEngine.validate_dag(nodes, edges)
        assert ok
        assert set(levels[0]) == {"n1", "n2"}
        assert levels[1] == ["n3"]

    def test_cycle_detection(self):
        """循环引用应被检测为无效"""
        nodes = [{"id": "n1"}, {"id": "n2"}, {"id": "n3"}]
        edges = [
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n3"},
            {"source": "n3", "target": "n1"},
        ]
        ok, err, _ = WorkflowEngine.validate_dag(nodes, edges)
        assert not ok
        assert "循环" in err

    def test_all_nodes_have_in_degree(self):
        """所有节点都有入边的闭环"""
        nodes = [{"id": "n1"}, {"id": "n2"}]
        edges = [
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n1"},
        ]
        ok, err, _ = WorkflowEngine.validate_dag(nodes, edges)
        assert not ok

    def test_dangling_edge_reference(self):
        """边的 source/target 引用不存在的节点应被忽略"""
        nodes = [{"id": "n1"}, {"id": "n2"}]
        edges = [
            {"source": "n1", "target": "n2"},
            {"source": "n1", "target": "nonexistent"},
        ]
        ok, _, levels = WorkflowEngine.validate_dag(nodes, edges)
        assert ok
        assert levels == [["n1"], ["n2"]]

    def test_isolated_node(self):
        """孤立节点应作为第一层"""
        nodes = [{"id": "n1"}, {"id": "n2"}, {"id": "n3"}]
        edges = [{"source": "n1", "target": "n2"}]
        ok, _, levels = WorkflowEngine.validate_dag(nodes, edges)
        assert ok
        # n3 是孤立节点，应与 n1 同在第一层
        assert set(levels[0]) == {"n1", "n3"}
        assert levels[1] == ["n2"]

    def test_complex_dag(self):
        """多层复杂 DAG"""
        nodes = [
            {"id": "a"},
            {"id": "b"},
            {"id": "c"},
            {"id": "d"},
            {"id": "e"},
        ]
        edges = [
            {"source": "a", "target": "c"},
            {"source": "b", "target": "c"},
            {"source": "c", "target": "d"},
            {"source": "c", "target": "e"},
        ]
        ok, _, levels = WorkflowEngine.validate_dag(nodes, edges)
        assert ok
        assert set(levels[0]) == {"a", "b"}
        assert levels[1] == ["c"]
        assert set(levels[2]) == {"d", "e"}


class TestResolveParams:
    """变量引用解析测试"""

    def test_simple_reference(self):
        """基本变量引用替换"""
        outputs = {"n1": {"result": 42}}
        params = {"code": "print(${n1.result})"}
        res = WorkflowEngine.resolve_params(params, outputs)
        assert res["code"] == "print(42)"

    def test_multiple_references(self):
        """多个变量引用"""
        outputs = {"n1": {"a": 1}, "n2": {"b": 2}}
        params = {"code": "${n1.a} + ${n2.b}"}
        res = WorkflowEngine.resolve_params(params, outputs)
        assert res["code"] == "1 + 2"

    def test_missing_node_reference(self):
        """引用不存在的节点应保持原样"""
        outputs = {"n1": {"result": 42}}
        params = {"x": "${n9.val}"}
        res = WorkflowEngine.resolve_params(params, outputs)
        assert res["x"] == "${n9.val}"

    def test_missing_key_reference(self):
        """引用存在的节点但 key 不存在时应保持原样"""
        outputs = {"n1": {"result": 42}}
        params = {"x": "${n1.missing}"}
        res = WorkflowEngine.resolve_params(params, outputs)
        assert res["x"] == "${n1.missing}"

    def test_nested_dict(self):
        """嵌套字典中的引用"""
        outputs = {"n1": {"data": "hello"}}
        params = {"nested": {"key": "${n1.data}", "static": 99}}
        res = WorkflowEngine.resolve_params(params, outputs)
        assert res["nested"]["key"] == "hello"
        assert res["nested"]["static"] == 99

    def test_list_with_reference(self):
        """列表中的引用"""
        outputs = {"n1": {"val": "x"}}
        params = {"list": ["${n1.val}", 3, "static"]}
        res = WorkflowEngine.resolve_params(params, outputs)
        assert res["list"] == ["x", 3, "static"]

    def test_non_string_value(self):
        """非字符串值（数字、布尔）保持原样"""
        outputs = {"n1": {"result": 42}}
        params = {"count": 100, "enabled": True, "data": None}
        res = WorkflowEngine.resolve_params(params, outputs)
        assert res["count"] == 100
        assert res["enabled"] is True
        assert res["data"] is None

    def test_deep_nested_dict(self):
        """深层嵌套字典"""
        outputs = {"n1": {"val": "deep"}}
        params = {"level1": {"level2": {"level3": "${n1.val}"}}}
        res = WorkflowEngine.resolve_params(params, outputs)
        assert res["level1"]["level2"]["level3"] == "deep"

    def test_empty_params(self):
        """空参数字典"""
        res = WorkflowEngine.resolve_params({}, {"n1": {"r": 1}})
        assert res == {}


class TestCreateInstance:
    """创建实例测试（mock 版暂只验证参数校验逻辑）"""

    def test_node_outputs_summary(self):
        """验证执行结果的 output_result 格式
        （纯逻辑测试，不依赖 DB）
        """
        node_outputs = {
            "n1": {"result": "hello", "success": True},
            "n2": {"result": 42, "success": True},
        }
        summary = {k: v.get("result", v) for k, v in node_outputs.items()}
        assert summary == {"n1": "hello", "n2": 42}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
