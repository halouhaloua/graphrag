"""三元组评分模块单元测试

测试策略：
- format_scored_triples 对 description 字段的处理
"""

import networkx as nx

from rag.rag_models.retrieval.triple_scorer import format_scored_triples


def _build_test_graph() -> nx.MultiDiGraph:
    """构建含 description 的测试图"""
    g = nx.MultiDiGraph()
    g.add_node("e0", label="entity", level=2, properties={
        "name": "Shawshank Redemption", "description": "A 1994 film",
    })
    g.add_node("e1", label="entity", level=2, properties={
        "name": "Stephen King", "description": "An American author",
    })
    g.add_node("e2", label="entity", level=2, properties={
        "name": "Frank Darabont", "description": "Film director",
    })
    # Edge WITH description
    g.add_edge("e0", "e1", relation="based on",
               keywords="adaptation",
               description="The Shawshank Redemption is based on Stephen King's novella")
    # Edge WITHOUT description
    g.add_edge("e0", "e2", relation="directed by")
    return g


class TestFormatScoredTriples:
    def setup_method(self):
        self.g = _build_test_graph()

    def test_description_gets_appended(self):
        """description 应成功追加到尾行"""
        scored = [("e0", "based on", "e1", 0.95)]
        result = format_scored_triples(self.g, scored)
        assert len(result) == 1
        assert "→" in result[0]
        assert "The Shawshank Redemption is based on Stephen King's novella" in result[0]

    def test_no_description(self):
        """无描述时不应追加额外行"""
        scored = [("e0", "directed by", "e2", 0.85)]
        result = format_scored_triples(self.g, scored)
        assert len(result) == 1
        assert "→" not in result[0]

    def test_mixed_presence(self):
        """有描述的关系追加描述行，无描述的不追加"""
        scored = [
            ("e0", "based on", "e1", 0.95),
            ("e0", "directed by", "e2", 0.85),
        ]
        result = format_scored_triples(self.g, scored)
        assert len(result) == 2
        desc_items = [r for r in result if "→" in r]
        assert len(desc_items) == 1  # only "based on" has description
        assert "novella" in desc_items[0]

    def test_empty_scored_triples(self):
        result = format_scored_triples(self.g, [])
        assert result == []

    def test_nonexistent_node(self):
        """节点不存在的三元组应跳过"""
        scored = [("nonexistent", "rel", "e0", 0.5)]
        result = format_scored_triples(self.g, scored)
        # nonexistent 节点会使 head_text 为空（get_node_text 返回空）
        # 空文本会被 is_valid_node_text 过滤掉
        assert len(result) == 0

    def test_score_formatting(self):
        """分数应格式化为三位小数"""
        scored = [("e0", "based on", "e1", 0.95555)]
        result = format_scored_triples(self.g, scored)
        assert "0.956" in result[0]

    def test_tail_grouping_with_desc(self):
        """多个 tail 合并后，取首条 tail 的描述追加"""
        g = nx.MultiDiGraph()
        g.add_node("h0", label="entity", level=2, properties={"name": "Head"})
        g.add_node("t0", label="entity", level=2, properties={"name": "Tail1"})
        g.add_node("t1", label="entity", level=2, properties={"name": "Tail2"})
        g.add_edge("h0", "t0", relation="relates", description="Desc for Tail1")
        g.add_edge("h0", "t1", relation="relates", description="Desc for Tail2")
        scored = [("h0", "relates", "t0", 0.9), ("h0", "relates", "t1", 0.8)]
        result = format_scored_triples(g, scored)
        assert len(result) == 1
        assert "Tail1" in result[0]
        assert "Tail2" in result[0]
        assert "→" in result[0]
        assert "Desc for Tail1" in result[0]

    def test_description_edge_not_found(self):
        """graph.get_edge_data 找不到边时应返回空字符串"""
        g = nx.MultiDiGraph()
        g.add_node("h0", label="entity", level=2, properties={"name": "Head"})
        g.add_node("t0", label="entity", level=2, properties={"name": "Tail"})
        # Don't add the edge to graph, but add to scored
        # This won't happen in practice, but tests the defensive code
        g.add_edge("h0", "t0", relation="some_rel")  # different relation
        scored = [("h0", "nonexistent_rel", "t0", 0.5)]
        result = format_scored_triples(g, scored)
        assert "→" not in result[0]
