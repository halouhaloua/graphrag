"""图序列化工具单元测试

测试策略：
- load_graph_from_json_data / save_graph_to_json 的 keywords/description 字段
- compute_graph_signature 对新增字段的响应
"""

import json
import tempfile

import networkx as nx

from rag.utils.graph_processor import (
    load_graph_from_json_data,
    save_graph_to_json,
    load_graph_from_json,
)
from rag.rag_models.retrieval.faiss_index import compute_graph_signature


# ─── 测试数据 ───

SIMPLE_GRAPH_DATA = [
    {
        "start_node": {"label": "entity", "properties": {"name": "Stephen King"}},
        "relation": "wrote",
        "end_node": {"label": "entity", "properties": {"name": "The Shining"}},
    },
]

GRAPH_WITH_KEYWORDS_DESC = [
    {
        "start_node": {"label": "entity", "properties": {"name": "Shawshank Redemption"}},
        "relation": "based on",
        "end_node": {
            "label": "entity",
            "properties": {"name": "Rita Hayworth and Shawshank Redemption"},
        },
        "keywords": "adaptation, inspiration source",
        "description": "The Shawshank Redemption is adapted from Stephen King's novella",
    },
    {
        "start_node": {"label": "entity", "properties": {"name": "Shawshank Redemption"}},
        "relation": "directed by",
        "end_node": {"label": "entity", "properties": {"name": "Frank Darabont"}},
        "keywords": "direction, film direction",
        "description": "Frank Darabont directed this film",
    },
]


# ─── load_graph_from_json_data ───


class TestLoadGraphFromJsonData:
    def test_basic_load(self):
        """加载基础图数据"""
        g = load_graph_from_json_data(SIMPLE_GRAPH_DATA)
        assert len(g.nodes) == 2
        assert len(g.edges) == 1

    def test_keywords_and_description_in_edge(self):
        """keywords 和 description 应作为边属性加载"""
        g = load_graph_from_json_data(GRAPH_WITH_KEYWORDS_DESC)
        for u, v, data in g.edges(data=True):
            if data.get("relation") == "based on":
                assert data.get("keywords") == "adaptation, inspiration source"
                assert data["description"] == "The Shawshank Redemption is adapted from Stephen King's novella"
            elif data.get("relation") == "directed by":
                assert data.get("keywords") == "direction, film direction"
                assert data["description"] == "Frank Darabont directed this film"

    def test_edge_without_keywords_desc(self):
        """老格式数据（无 keywords/description）应正常加载"""
        g = load_graph_from_json_data(SIMPLE_GRAPH_DATA)
        for _, _, data in g.edges(data=True):
            assert "keywords" not in data
            assert "description" not in data

    def test_empty_list(self):
        g = load_graph_from_json_data([])
        assert len(g.nodes) == 0


# ─── load_graph_from_json ───


class TestLoadGraphFromJson:
    def test_with_keywords_and_description(self):
        """从文件加载含 keywords/description 的数据"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(GRAPH_WITH_KEYWORDS_DESC, f, ensure_ascii=False)
            fpath = f.name
        try:
            g = load_graph_from_json(fpath)
            for _, _, data in g.edges(data=True):
                if data.get("relation") == "based on":
                    assert data.get("keywords") == "adaptation, inspiration source"
        finally:
            import os
            os.unlink(fpath)


# ─── save_graph_to_json ───


class TestSaveGraphToJson:
    def test_keywords_and_description_serialized(self):
        """keywords 和 description 应写入 JSON 输出"""
        g = load_graph_from_json_data(GRAPH_WITH_KEYWORDS_DESC)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            fpath = f.name
        try:
            save_graph_to_json(g, fpath)
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            for rel in data:
                if rel["relation"] == "based on":
                    assert "keywords" in rel
                    assert "description" in rel
                    assert rel["keywords"] == "adaptation, inspiration source"
        finally:
            import os
            os.unlink(fpath)

    def test_roundtrip(self):
        """load → save → load 应保留 keywords/description"""
        g1 = load_graph_from_json_data(GRAPH_WITH_KEYWORDS_DESC)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            fpath = f.name
        try:
            save_graph_to_json(g1, fpath)
            g2 = load_graph_from_json(fpath)
            for _, _, data in g2.edges(data=True):
                if data.get("relation") == "based on":
                    assert data.get("keywords") == "adaptation, inspiration source"
        finally:
            import os
            os.unlink(fpath)


# ─── compute_graph_signature ───


class TestComputeGraphSignature:
    def test_basic_signature(self):
        """基础图签名"""
        g = nx.MultiDiGraph()
        g.add_node("e0", label="entity", properties={"name": "A"})
        g.add_node("e1", label="entity", properties={"name": "B"})
        g.add_edge("e0", "e1", relation="rel")
        sig = compute_graph_signature(g)
        assert isinstance(sig, str)
        assert len(sig) == 32  # MD5 hex

    def test_signature_changes_with_keywords(self):
        """添加 keywords 应改变签名"""
        g1 = nx.MultiDiGraph()
        g1.add_node("e0", label="entity", properties={"name": "A"})
        g1.add_node("e1", label="entity", properties={"name": "B"})
        g1.add_edge("e0", "e1", relation="rel")

        g2 = nx.MultiDiGraph()
        g2.add_node("e0", label="entity", properties={"name": "A"})
        g2.add_node("e1", label="entity", properties={"name": "B"})
        g2.add_edge("e0", "e1", relation="rel", keywords="kw", description="desc")

        assert compute_graph_signature(g1) != compute_graph_signature(g2)

    def test_signature_change_with_description(self):
        """仅添加 description 也应改变签名"""
        g1 = nx.MultiDiGraph()
        g1.add_node("e0", label="entity", properties={"name": "A"})
        g1.add_node("e1", label="entity", properties={"name": "B"})
        g1.add_edge("e0", "e1", relation="rel")

        g2 = nx.MultiDiGraph()
        g2.add_node("e0", label="entity", properties={"name": "A"})
        g2.add_node("e1", label="entity", properties={"name": "B"})
        g2.add_edge("e0", "e1", relation="rel", description="desc only")

        assert compute_graph_signature(g1) != compute_graph_signature(g2)

    def test_signature_deterministic(self):
        """相同图应产生相同签名"""
        g = nx.MultiDiGraph()
        g.add_node("e0", label="entity", properties={"name": "A"})
        g.add_node("e1", label="entity", properties={"name": "B"})
        g.add_edge("e0", "e1", relation="rel", keywords="kw", description="desc")
        assert compute_graph_signature(g) == compute_graph_signature(g)

    def test_empty_graph(self):
        g = nx.MultiDiGraph()
        sig = compute_graph_signature(g)
        assert len(sig) == 32
