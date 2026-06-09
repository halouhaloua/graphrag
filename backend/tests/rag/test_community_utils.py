"""社区工具模块单元测试

测试策略：
- _find_node_by_name / get_community_nodes / collect_community_summaries 纯函数
- 使用 NetworkX MultiDiGraph 构造测试图
"""

import networkx as nx

from rag.rag_models.retrieval.community_utils import (
    _find_node_by_name,
    get_community_nodes,
    collect_community_summaries,
)


def _build_test_graph() -> nx.MultiDiGraph:
    """构建测试用知识图谱

    节点：
      entity_0 (name="Beekeeper", chunk id="chunk_a", description="A person who keeps bees")
      entity_1 (name="Honey", chunk id="chunk_a", description="Sweet food made by bees")
      entity_2 (name="Hive", chunk id="chunk_b", description="Structure for bees")
      community_0 (name="Apiary", description="Beekeeping community", members=["Beekeeper", "Honey", "Hive"],
                   keywords=["beekeeping", "apiary"])
    边：
      entity_0 → entity_1 (relation="produces")
      entity_0 → entity_2 (relation="uses")
      entity_0 → community_0 (relation="member_of")
      entity_1 → community_0 (relation="member_of")
    """
    g = nx.MultiDiGraph()
    g.add_node("entity_0", label="entity", level=2, properties={
        "name": "Beekeeper", "chunk id": "chunk_a",
        "description": "A person who keeps bees",
    })
    g.add_node("entity_1", label="entity", level=2, properties={
        "name": "Honey", "chunk id": "chunk_a",
        "description": "Sweet food made by bees",
    })
    g.add_node("entity_2", label="entity", level=2, properties={
        "name": "Hive", "chunk id": "chunk_b",
        "description": "Structure for bees",
    })
    g.add_node("community_0", label="community", level=4, properties={
        "name": "Apiary",
        "description": "Beekeeping community",
        "members": ["Beekeeper", "Honey", "Hive"],
        "keywords": ["beekeeping", "apiary"],
    })
    g.add_edge("entity_0", "entity_1", relation="produces")
    g.add_edge("entity_0", "entity_2", relation="uses")
    g.add_edge("entity_0", "community_0", relation="member_of")
    g.add_edge("entity_1", "community_0", relation="member_of")
    return g


# ─── _find_node_by_name ───


class TestFindNodeByName:
    def setup_method(self):
        self.g = _build_test_graph()

    def test_exact_name(self):
        nid = _find_node_by_name(self.g, "Beekeeper")
        assert nid == "entity_0"

    def test_case_sensitive(self):
        nid = _find_node_by_name(self.g, "beekeeper")
        assert nid is None

    def test_nonexistent_name(self):
        nid = _find_node_by_name(self.g, "Nonexistent")
        assert nid is None

    def test_empty_name(self):
        nid = _find_node_by_name(self.g, "")
        assert nid is None

    def test_find_community_node_by_name(self):
        """函数遍历全部节点，社区节点也可按名称查找"""
        nid = _find_node_by_name(self.g, "Apiary")
        assert nid == "community_0"


# ─── get_community_nodes ───


class TestGetCommunityNodes:
    def setup_method(self):
        self.g = _build_test_graph()
        self.name_to_id = {"Beekeeper": "entity_0", "Honey": "entity_1", "Hive": "entity_2"}

    def test_valid_community(self):
        members = get_community_nodes(self.g, "community_0", self.name_to_id)
        assert len(members) == 3
        assert "entity_0" in members
        assert "entity_1" in members
        assert "entity_2" in members

    def test_without_name_to_id(self):
        """不带 name_to_id 索引时通过遍历查找"""
        members = get_community_nodes(self.g, "community_0")
        assert len(members) == 3

    def test_invalid_node_id(self):
        members = get_community_nodes(self.g, "nonexistent", self.name_to_id)
        assert members == []

    def test_non_community_node(self):
        members = get_community_nodes(self.g, "entity_0", self.name_to_id)
        assert members == []

    def test_community_with_empty_members(self):
        self.g.add_node("empty_comm", label="community", level=4, properties={
            "name": "Empty", "members": [],
        })
        members = get_community_nodes(self.g, "empty_comm", self.name_to_id)
        assert members == []

    def test_community_member_as_list(self):
        """members 中的元素可能是列表"""
        g = nx.MultiDiGraph()
        g.add_node("comm_0", label="community", level=4, properties={
            "name": "Test", "members": [["Person A", "Person B"]],
        })
        # When member is a list, the function joins with ", "
        members = get_community_nodes(g, "comm_0")
        assert members == []


# ─── collect_community_summaries ───


class TestCollectCommunitySummaries:
    def setup_method(self):
        self.g = _build_test_graph()

    def test_scored_triple_in_community(self):
        """三元组的实体在社区中，应返回社区摘要"""
        scored = [("entity_0", "produces", "entity_1", 0.9)]
        summaries = collect_community_summaries(self.g, scored)
        assert len(summaries) == 1
        assert summaries[0]["name"] == "Apiary"
        assert summaries[0]["description"] == "Beekeeping community"
        assert summaries[0]["keywords"] == ["beekeeping", "apiary"]

    def test_key_members_included(self):
        """社区摘要应包含 key_members 字段"""
        scored = [("entity_0", "produces", "entity_1", 0.9)]
        summaries = collect_community_summaries(self.g, scored)
        assert "key_members" in summaries[0]
        assert len(summaries[0]["key_members"]) > 0
        # Beekeeper should be a key member
        bm = next((km for km in summaries[0]["key_members"] if km["name"] == "Beekeeper"), None)
        assert bm is not None
        assert bm["description"] == "A person who keeps bees"

    def test_key_member_with_chunk_excerpt(self):
        """当提供 chunk2id 时，key_members 应包含 chunk excerpt"""
        scored = [("entity_0", "produces", "entity_1", 0.9)]
        chunk2id = {"chunk_a": "Beekeepers maintain hives and collect honey from bees."}
        summaries = collect_community_summaries(self.g, scored, chunk2id=chunk2id)
        bm = next((km for km in summaries[0]["key_members"] if km["name"] == "Beekeeper"), None)
        assert bm is not None
        assert bm["chunk_excerpt"] == "Beekeepers maintain hives and collect honey from bees."

    def test_no_chunk2id_provided(self):
        """不提供 chunk2id 时，chunk_excerpt 应为空字符串"""
        scored = [("entity_0", "produces", "entity_1", 0.9)]
        summaries = collect_community_summaries(self.g, scored)
        bm = next((km for km in summaries[0]["key_members"] if km["name"] == "Beekeeper"), None)
        assert bm["chunk_excerpt"] == ""

    def test_empty_scored_triples(self):
        summaries = collect_community_summaries(self.g, [])
        assert summaries == []

    def test_dedup_communities(self):
        """同一社区多个三元组应去重"""
        scored = [
            ("entity_0", "produces", "entity_1", 0.9),
            ("entity_0", "uses", "entity_2", 0.8),
        ]
        summaries = collect_community_summaries(self.g, scored)
        assert len(summaries) == 1  # 两个三元组都属于同一个社区

    def test_only_first_10_members(self):
        """key_members 只取前 10 个成员"""
        g = nx.MultiDiGraph()
        g.add_node("entity_0", label="entity", level=2, properties={"name": "E0"})
        all_members = [f"Member_{i}" for i in range(15)]
        g.add_node("community_0", label="community", level=4, properties={
            "name": "BigComm", "description": "desc", "members": all_members, "keywords": [],
        })
        g.add_edge("entity_0", "community_0", relation="member_of")
        scored = [("entity_0", "rel", "entity_0", 0.5)]
        summaries = collect_community_summaries(g, scored)
        assert len(summaries[0]["key_members"]) <= 10

    def test_node_not_in_graph(self):
        """三元组中的节点不在图中应跳过"""
        scored = [("nonexistent", "rel", "entity_0", 0.5)]
        summaries = collect_community_summaries(self.g, scored)
        # entity_0 will still be processed but its community is Apiary
        # Actually entity_0 IS in the graph, so it should find the community
        # But the source is not in the graph so it skips that
        assert len(summaries) >= 1  # entity_0 should still match

    def test_multiple_communities(self):
        """多个不同社区的三元组应分别收集"""
        g = _build_test_graph()
        g.add_node("entity_3", label="entity", level=2, properties={"name": "Entity3"})
        g.add_node("community_1", label="community", level=4, properties={
            "name": "Comm2", "description": "desc2", "members": ["Entity3"], "keywords": [],
        })
        g.add_edge("entity_3", "community_1", relation="member_of")
        scored = [
            ("entity_0", "produces", "entity_1", 0.9),
            ("entity_3", "rel", "entity_3", 0.5),
        ]
        summaries = collect_community_summaries(g, scored)
        assert len(summaries) == 2
