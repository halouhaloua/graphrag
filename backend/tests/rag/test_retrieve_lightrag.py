"""retrieve_lightrag 模块辅助函数单元测试"""

import networkx as nx

from rag.rag_models.retrieval.retrieve_lightrag import (
    _dedup,
    _merge_nodes,
    _expand_1hop,
    _collect_community_info,
    _expand_community_members,
    _expand_chunk_entities,
)


def _build_test_graph() -> nx.MultiDiGraph:
    """构建一个测试用小型知识图谱

    Graph structure:
    entity_0 (Beekeeper, chunk=chunk_a) --[practice]--> entity_1 (Bee_Keeping, chunk=chunk_a)
    entity_0 --[use]--> entity_2 (Hive, chunk=chunk_b)
    entity_1 --[produce]--> entity_3 (Honey, chunk=chunk_a)
    community_0 (level=4, members=[Beekeeper, Bee_Keeping, Honey])
        --[member_of]--> entity_0, entity_1, entity_3
    """
    g = nx.MultiDiGraph()
    g.add_node(
        "entity_0",
        label="entity",
        level=2,
        properties={"name": "Beekeeper", "chunk id": "chunk_a"},
    )
    g.add_node(
        "entity_1",
        label="entity",
        level=2,
        properties={"name": "Bee_Keeping", "chunk id": "chunk_a"},
    )
    g.add_node(
        "entity_2",
        label="entity",
        level=2,
        properties={"name": "Hive", "chunk id": "chunk_b"},
    )
    g.add_node(
        "entity_3",
        label="entity",
        level=2,
        properties={"name": "Honey", "chunk id": "chunk_a"},
    )
    g.add_node(
        "community_0",
        label="community",
        level=4,
        properties={
            "name": "Apiary Community",
            "description": "Community about beekeeping and honey production",
            "keywords": ["beekeeping", "honey", "apiary"],
            "members": ["Beekeeper", "Bee_Keeping", "Honey"],
        },
    )
    g.add_edge("entity_0", "entity_1", relation="practice")
    g.add_edge("entity_0", "entity_2", relation="use")
    g.add_edge("entity_1", "entity_3", relation="produce")
    g.add_edge("entity_0", "community_0", relation="member_of")
    g.add_edge("entity_1", "community_0", relation="member_of")
    g.add_edge("entity_3", "community_0", relation="member_of")
    return g


class TestDedup:
    def test_empty_list(self):
        assert _dedup([]) == []

    def test_no_duplicates(self):
        assert _dedup(["a", "b", "c"]) == ["a", "b", "c"]

    def test_duplicates_string(self):
        assert _dedup(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]

    def test_duplicates_triples(self):
        triples = [
            ("a", "r1", "b"),
            ("a", "r1", "b"),
            ("c", "r2", "d"),
        ]
        assert _dedup(triples) == [("a", "r1", "b"), ("c", "r2", "d")]


class TestMergeNodes:
    def test_empty_input(self):
        assert _merge_nodes([], [], 5) == []

    def test_only_faiss(self):
        assert _merge_nodes(["a", "b"], [], 5) == ["a", "b"]

    def test_only_keyword(self):
        assert _merge_nodes([], ["x", "y"], 5) == ["x", "y"]

    def test_dedup_merged(self):
        result = _merge_nodes(["a", "b"], ["b", "c"], 5)
        assert result == ["a", "b", "c"]

    def test_top_k_truncation(self):
        result = _merge_nodes(["a", "b", "c", "d"], ["e", "f"], 3)
        assert len(result) == 3
        assert result == ["a", "b", "c"]


class TestExpand1hop:
    def setup_method(self):
        self.g = _build_test_graph()

    def test_empty_nodes(self):
        triples, cids = _expand_1hop(self.g, [])
        assert triples == []
        assert cids == []

    def test_single_node(self):
        triples, cids = _expand_1hop(self.g, ["entity_2"])
        # entity_2 only has incoming edge from entity_0
        assert len(triples) == 1
        assert ("entity_0", "use", "entity_2") in triples
        assert "chunk_b" in cids

    def test_node_with_multiple_edges(self):
        triples, cids = _expand_1hop(self.g, ["entity_0"])
        # entity_0 → entity_1 (practice), entity_0 → entity_2 (use)
        # also reverse: entity_0 is neighbor of community_0
        rels = {r for _, r, _ in triples}
        assert "practice" in rels
        assert "use" in rels
        assert "chunk_a" in cids

    def test_chunk_ids_from_neighbors(self):
        _, cids = _expand_1hop(self.g, ["entity_0"])
        # entity_0 chunk_a, neighbor entity_1 chunk_a, neighbor entity_2 chunk_b
        assert "chunk_a" in cids
        assert "chunk_b" in cids


class TestCollectCommunityInfo:
    def setup_method(self):
        self.g = _build_test_graph()

    def test_empty_ids(self):
        assert _collect_community_info(self.g, []) == []

    def test_invalid_id(self):
        assert _collect_community_info(self.g, ["nonexistent"]) == []

    def test_non_community_node(self):
        assert _collect_community_info(self.g, ["entity_0"]) == []

    def test_valid_community(self):
        summaries = _collect_community_info(self.g, ["community_0"])
        assert len(summaries) == 1
        assert summaries[0]["name"] == "Apiary Community"
        assert "beekeeping" in summaries[0]["description"]
        assert "beekeeping" in summaries[0]["keywords"]

    def test_multiple_communities(self):
        self.g.add_node(
            "community_1",
            label="community",
            level=4,
            properties={"name": "C2", "description": "Desc2", "keywords": []},
        )
        summaries = _collect_community_info(self.g, ["community_0", "community_1"])
        assert len(summaries) == 2


class TestExpandCommunityMembers:
    def setup_method(self):
        self.g = _build_test_graph()
        self.name_to_id = {
            "Beekeeper": "entity_0",
            "Bee_Keeping": "entity_1",
            "Hive": "entity_2",
            "Honey": "entity_3",
        }

    def test_empty_ids(self):
        triples, cids = _expand_community_members(self.g, [], {})
        assert triples == []
        assert cids == []

    def test_community_member_triples(self):
        triples, cids = _expand_community_members(
            self.g, ["community_0"], self.name_to_id
        )
        # members: Beekeeper, Bee_Keeping, Honey → their 1-hop edges
        assert len(triples) >= 2
        rels = {r for _, r, _ in triples}
        assert "practice" in rels
        assert "produce" in rels
        assert "chunk_a" in cids


class TestExpandChunkEntities:
    def setup_method(self):
        self.g = _build_test_graph()
        self.chunk_to_entities = {
            "chunk_a": ["entity_0", "entity_1", "entity_3"],
            "chunk_b": ["entity_2"],
        }

    def test_empty_chunk_ids(self):
        triples, cids = _expand_chunk_entities(self.g, {}, [])
        assert triples == []
        assert cids == []

    def test_single_chunk(self):
        triples, cids = _expand_chunk_entities(
            self.g, self.chunk_to_entities, ["chunk_b"]
        )
        # chunk_b → entity_2 → 1-hop neighbor entity_0 → edge
        assert len(triples) == 1
        assert ("entity_0", "use", "entity_2") in triples

    def test_multiple_chunks(self):
        triples, cids = _expand_chunk_entities(
            self.g, self.chunk_to_entities, ["chunk_a", "chunk_b"]
        )
        assert len(triples) >= 3
        assert "chunk_a" in cids


class TestRescoreAndTruncate:
    def setup_method(self):
        from rag.rag_models.retrieval.retrieval_core import RetrievalState
        from rag.config import get_config

        cfg = get_config()
        self.encoder = cfg.embeddings.get_model()
        self.g = _build_test_graph()
        self.state = RetrievalState(
            graph=self.g,
            encoder=self.encoder,
            top_k=5,
            node_text_cache={
                "entity_0": "Beekeeper manages hives",
                "entity_1": "Bee_Keeping practices",
                "entity_2": "Hive structure",
                "entity_3": "Honey production",
                "community_0": "Apiary Community beekeeping",
            },
        )

    def test_empty_triples(self):
        from rag.rag_models.retrieval.retrieve_lightrag import _rescore_and_truncate

        result = _rescore_and_truncate(self.state, [], None)
        assert result == []

    def test_truncation(self):
        from rag.rag_models.retrieval.retrieve_lightrag import _rescore_and_truncate

        triples = [
            ("entity_0", "practice", "entity_1"),
            ("entity_0", "use", "entity_2"),
            ("entity_1", "produce", "entity_3"),
        ]
        query_embed = self.encoder.encode("beekeeper", convert_to_tensor=True).float()
        result = _rescore_and_truncate(self.state, triples, query_embed, top_k=2)
        assert len(result) == 2
        for h, r, t, score in result:
            assert isinstance(score, float)
            assert score >= 0.0

    def test_scores_vary(self):
        from rag.rag_models.retrieval.retrieve_lightrag import _rescore_and_truncate

        triples = [
            ("entity_0", "practice", "entity_1"),
            ("entity_2", "use", "entity_0"),
        ]
        query_embed = self.encoder.encode("hive structure", convert_to_tensor=True).float()
        result = _rescore_and_truncate(self.state, triples, query_embed, top_k=5)
        assert len(result) == 2
        assert all(isinstance(s, float) for _, _, _, s in result)
