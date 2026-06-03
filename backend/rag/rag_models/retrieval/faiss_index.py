"""FAISS 索引管理 + 图一致性令牌

功能：
- 构建 4 种 FAISS 索引（节点、关系、三元组、社区）
- 持久化/加载索引（含图签名一致性校验）
- 提供搜索函数
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import faiss
import networkx as nx
import numpy as np

from rag.rag_models.retrieval import utils as retriever_utils
from loguru import logger


@dataclass
class FAISSIndexSet:
    """四种 FAISS 索引的聚合容器

    每种索引对应一个 FAISS IndexFlatIP（内积 = 归一化后的余弦相似度）
    """

    node_index: faiss.Index  # 节点索引：按 name,description 构建
    relation_index: faiss.Index  # 关系索引：按关系名构建
    triple_index: faiss.Index  # 三元组索引：按 "头,关系,尾" 文本构建
    comm_index: faiss.Index  # 社区索引：按社区 name,description 构建
    node_map: Dict[int, str]  # {FAISS索引位置: 节点ID}
    relation_map: Dict[int, str]  # {FAISS索引位置: 关系名称}
    triple_map: Dict[int, Tuple]  # {FAISS索引位置: (头ID, 关系, 尾ID)}
    comm_map: Dict[int, str]  # {FAISS索引位置: 社区节点ID}
    graph_signature: str = ""  # 构建时的图签名，用于一致性校验


def compute_graph_signature(graph: nx.MultiDiGraph) -> str:
    """计算图的唯一签名（MD5）

    对节点ID列表和边（u:relation:v）排序后拼接，用于判断图是否有变更
    """
    node_ids = sorted(graph.nodes())
    edges = sorted(
        f"{u}:{data.get('relation', '')}:{v}" for u, v, data in graph.edges(data=True)
    )
    content = "|".join(node_ids) + "||" + "|".join(edges)
    return hashlib.md5(content.encode()).hexdigest()


def _consistency_path(cache_dir: str, dataset: str) -> str:
    """一致性令牌文件路径"""
    return os.path.join(cache_dir, dataset, "_consistency.json")


def _load_consistency_token(cache_dir: str, dataset: str) -> Optional[str]:
    """读取缓存的图签名，返回 None 表示无缓存"""
    path = _consistency_path(cache_dir, dataset)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            meta = json.load(f)
        return meta.get("graph_signature")
    except Exception:
        return None


def _save_consistency_token(cache_dir: str, dataset: str, graph_signature: str):
    """持久化图签名 + 构建时间"""
    path = _consistency_path(cache_dir, dataset)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"graph_signature": graph_signature, "built_at": time.time()}, f)


def check_consistency(graph: nx.MultiDiGraph, cache_dir: str, dataset: str) -> bool:
    """检查缓存的图签名与当前图是否匹配

    所有缓存（FAISS 索引、文本缓存、倒排索引）共享此校验，
    一旦图变更 → 全量失效 → 全量重建
    """
    cached_sig = _load_consistency_token(cache_dir, dataset)
    if cached_sig is None:
        return False
    return cached_sig == compute_graph_signature(graph)


def _get_node_text_simple(graph: nx.MultiDiGraph, node_id: str) -> str:
    """获取节点文本（简化版，仅用于构建 FAISS 索引时）

    与 text_processor.get_node_text 不同，这里使用逗号分隔
    """
    data = graph.nodes[node_id]
    name, desc = retriever_utils.extract_node_name_and_description(data)
    return f"{name},{desc}".strip()


# ─── 索引构建 ───


def build_node_index(
    graph: nx.MultiDiGraph,
    encoder,
) -> Tuple[faiss.Index, Dict[int, str]]:
    """构建节点 FAISS 索引

    输入：所有图节点的 name+description 文本
    输出：IndexFlatIP + {索引位置: 节点ID} 映射
    """
    nodes = list(graph.nodes())
    texts = [_get_node_text_simple(graph, n) for n in nodes]
    embeddings = encoder.encode(texts, convert_to_tensor=True)
    embeddings_np = embeddings.cpu().numpy().astype("float32")
    dim = embeddings_np.shape[1]
    index = faiss.IndexFlatIP(dim)
    faiss.normalize_L2(embeddings_np)
    index.add(embeddings_np)
    node_map = {i: n for i, n in enumerate(nodes)}
    return index, node_map


def _detect_dim(encoder) -> int:
    """获取编码器输出维度

    优先使用 SentenceTransformer 的 get_sentence_embedding_dimension，
    fallback 通过编码空字符串检测
    """
    try:
        return encoder.get_sentence_embedding_dimension()
    except AttributeError:
        pass
    dummy = encoder.encode([""], convert_to_tensor=True)
    return dummy.shape[-1]


def build_relation_index(
    graph: nx.MultiDiGraph,
    encoder,
) -> Tuple[faiss.Index, Dict[int, str]]:
    """构建关系 FAISS 索引

    输入：图中出现的所有不重复关系名称
    """
    relations = sorted(
        {
            data["relation"]
            for _, _, data in graph.edges(data=True)
            if "relation" in data
        }
    )
    if not relations:
        dim = _detect_dim(encoder)
        return faiss.IndexFlatIP(dim), {}
    embeddings = encoder.encode(relations, convert_to_tensor=True)
    embeddings_np = embeddings.cpu().numpy().astype("float32")
    dim = embeddings_np.shape[1]
    index = faiss.IndexFlatIP(dim)
    faiss.normalize_L2(embeddings_np)
    index.add(embeddings_np)
    relation_map = {i: r for i, r in enumerate(relations)}
    return index, relation_map


def build_triple_index(
    graph: nx.MultiDiGraph,
    encoder,
) -> Tuple[faiss.Index, Dict[int, Tuple]]:
    """构建三元组 FAISS 索引

    输入：所有边的关系三元组 (头ID, 关系名称, 尾ID)
    索引文本格式："头节点name,关系名称,尾节点name"
    """
    triples = []
    for u, v, data in graph.edges(data=True):
        if "relation" in data:
            triples.append((u, data["relation"], v))
    texts = [
        f"{_get_node_text_simple(graph, h)},{r},{_get_node_text_simple(graph, t)}"
        for h, r, t in triples
    ]
    if not texts:
        dim = _detect_dim(encoder)
        return faiss.IndexFlatIP(dim), {}
    embeddings = encoder.encode(texts)
    embeddings_np = embeddings.astype("float32")
    dim = embeddings_np.shape[1]
    index = faiss.IndexFlatIP(dim)
    faiss.normalize_L2(embeddings_np)
    index.add(embeddings_np)
    triple_map = {i: t for i, t in enumerate(triples)}
    return index, triple_map


def build_community_index(
    graph: nx.MultiDiGraph,
    encoder,
) -> Tuple[faiss.Index, Dict[int, str]]:
    """构建社区 FAISS 索引

    输入：所有 label="community" 节点的 name+description 文本
    """
    communities = [
        n for n, d in graph.nodes(data=True) if d.get("label") == "community"
    ]
    texts = []
    valid_communities = []
    for comm in communities:
        data = graph.nodes[comm]
        props = data.get("properties", {})
        name = props.get("name", "")
        description = props.get("description", "")
        if name or description:
            texts.append(f"{name},{description}".strip())
            valid_communities.append(comm)
    if not valid_communities:
        dim = _detect_dim(encoder)
        return faiss.IndexFlatIP(dim), {}
    embeddings = encoder.encode(texts)
    embeddings_np = embeddings.astype("float32")
    dim = embeddings_np.shape[1]
    index = faiss.IndexFlatIP(dim)
    faiss.normalize_L2(embeddings_np)
    index.add(embeddings_np)
    comm_map = {i: n for i, n in enumerate(valid_communities)}
    return index, comm_map


def build_all_indices(graph: nx.MultiDiGraph, encoder) -> FAISSIndexSet:
    """一站式构建全部四种 FAISS 索引"""
    node_index, node_map = build_node_index(graph, encoder)
    relation_index, relation_map = build_relation_index(graph, encoder)
    triple_index, triple_map = build_triple_index(graph, encoder)
    comm_index, comm_map = build_community_index(graph, encoder)
    sig = compute_graph_signature(graph)
    return FAISSIndexSet(
        node_index=node_index,
        relation_index=relation_index,
        triple_index=triple_index,
        comm_index=comm_index,
        node_map=node_map,
        relation_map=relation_map,
        triple_map=triple_map,
        comm_map=comm_map,
        graph_signature=sig,
    )


# ─── 持久化 ───


def _safe_faiss_path(original_path: str, cache_root: str) -> str:
    """FAISS 的 C++ I/O 不支持中文路径，做 ASCII 安全映射"""
    return retriever_utils.safe_faiss_path(original_path, cache_root)


def save_index_set(index_set: FAISSIndexSet, cache_dir: str, dataset: str):
    """将四个 FAISS 索引 + 映射文件 + 一致性令牌写入磁盘"""
    os.makedirs(os.path.join(cache_dir, dataset), exist_ok=True)
    root = cache_dir

    def _save_index(index, name):
        path = _safe_faiss_path(os.path.join(cache_dir, dataset, f"{name}.index"), root)
        faiss.write_index(index, path)

    def _save_map(mapping, name):
        path = os.path.join(cache_dir, dataset, f"{name}_map.json")
        with open(path, "w") as f:
            json.dump(mapping, f)

    _save_index(index_set.node_index, "node")
    _save_index(index_set.relation_index, "relation")
    _save_index(index_set.triple_index, "triple")
    _save_index(index_set.comm_index, "comm")
    _save_map(index_set.node_map, "node")
    _save_map(index_set.relation_map, "relation")
    _save_map(index_set.triple_map, "triple")
    _save_map(index_set.comm_map, "comm")
    _save_consistency_token(cache_dir, dataset, index_set.graph_signature)
    logger.info(
        f"Saved FAISS index set with signature {index_set.graph_signature[:12]}... for dataset {dataset}"
    )


def load_index_set(
    graph: nx.MultiDiGraph,
    cache_dir: str,
    dataset: str,
) -> Optional[FAISSIndexSet]:
    """从磁盘加载 FAISS 索引

    先校验图签名，匹配则加载，否则返回 None 触发重建。
    任意索引文件缺失也会返回 None。
    """
    if not check_consistency(graph, cache_dir, dataset):
        logger.info(
            f"Graph signature mismatch or no cache for dataset {dataset}, need rebuild"
        )
        return None

    root = cache_dir

    def _load_index(name):
        path = _safe_faiss_path(os.path.join(cache_dir, dataset, f"{name}.index"), root)
        if not os.path.exists(path):
            return None
        return faiss.read_index(path)

    def _load_map(name):
        path = os.path.join(cache_dir, dataset, f"{name}_map.json")
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            data = json.load(f)
        return {int(k): v for k, v in data.items()} if data else {}

    # 四个索引缺一不可，任意缺失则触发重建
    node_index = _load_index("node")
    if node_index is None:
        return None
    relation_index = _load_index("relation")
    triple_index = _load_index("triple")
    comm_index = _load_index("comm")
    if relation_index is None or triple_index is None or comm_index is None:
        return None

    nodem = _load_map("node")
    relm = _load_map("relation")
    triplem = _load_map("triple")
    commm = _load_map("comm")

    sig = compute_graph_signature(graph)
    return FAISSIndexSet(
        node_index=node_index,
        relation_index=relation_index,
        triple_index=triple_index,
        comm_index=comm_index,
        node_map=nodem,
        relation_map=relm,
        triple_map=triplem,
        comm_map=commm,
        graph_signature=sig,
    )


# ─── 搜索 ───


def search_nodes(
    index_set: FAISSIndexSet,
    query_embed: np.ndarray,
    top_k: int,
) -> List[str]:
    """在节点索引中搜索 top-k 节点，返回节点 ID 列表"""
    query_np = query_embed.reshape(1, -1).astype("float32")
    search_k = min(top_k * 3, len(index_set.node_map))
    if search_k <= 0:
        return []
    _, indices = index_set.node_index.search(query_np, search_k)
    return [
        index_set.node_map[idx]
        for idx in indices[0]
        if idx != -1 and idx in index_set.node_map
    ]


def search_relations(
    index_set: FAISSIndexSet,
    query_embed: np.ndarray,
    top_k: int,
) -> List[str]:
    """在关系索引中搜索 top-k 关系，返回关系名称列表"""
    query_np = query_embed.reshape(1, -1).astype("float32")
    search_k = min(top_k, len(index_set.relation_map))
    if search_k <= 0:
        return []
    _, indices = index_set.relation_index.search(query_np, search_k)
    return [
        index_set.relation_map[idx]
        for idx in indices[0]
        if idx != -1 and idx in index_set.relation_map
    ]


def search_triples(
    index_set: FAISSIndexSet,
    query_embed: np.ndarray,
    top_k: int,
) -> List[Tuple[str, str, str]]:
    """在三元组索引中搜索 top-k 三元组，返回 (头ID, 关系, 尾ID) 列表"""
    query_np = query_embed.reshape(1, -1).astype("float32")
    search_k = min(top_k * 2, len(index_set.triple_map))
    if search_k <= 0:
        return []
    _, indices = index_set.triple_index.search(query_np, search_k)
    results = []
    for idx in indices[0]:
        if idx != -1 and idx in index_set.triple_map:
            results.append(index_set.triple_map[idx])
    return results


def search_communities(
    index_set: FAISSIndexSet,
    query_embed: np.ndarray,
    top_k: int,
) -> List[str]:
    """在社区索引中搜索 top-k 社区，返回社区节点 ID 列表"""
    query_np = query_embed.reshape(1, -1).astype("float32")
    search_k = min(top_k, len(index_set.comm_map))
    if search_k <= 0:
        return []
    _, indices = index_set.comm_index.search(query_np, search_k)
    return [
        index_set.comm_map[idx]
        for idx in indices[0]
        if idx != -1 and idx in index_set.comm_map
    ]
