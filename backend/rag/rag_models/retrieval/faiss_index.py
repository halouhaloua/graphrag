"""FAISS 索引管理 + 图一致性校验

功能：
- 构建 4 种 FAISS 索引（节点、关系、三元组、社区）
- 持久化/加载索引（含图签名一致性校验）
- 提供搜索函数

索引文本构成：
  node_index:      f"{node_name},{node_description}"       — 实体语义
  relation_index:  relation_name                           — 关系名
  triple_index:    f"{head_text},{keywords},{tail_text}     — 三元组语义
                   [ | description]"                        （keywords 优先，有 description 时追加）
  comm_index:      f"{comm_name},{comm_description}"       — 社区主题

数据流：
  NetworkX MultiDiGraph → compute_graph_signature() → md5（含 relation+keywords+description）
    → build_all_indices() → FAISSIndexSet
    → save_index_set() / load_index_set() → 磁盘持久化
    → search_nodes() / search_relations() / search_triples() / search_communities()

图签名机制：
  - compute_graph_signature() 根据节点集+边集(含relation+keywords+description)计算 MD5
  - 所有缓存（FAISS/文本/倒排）共享此签名
  - 图变更 → 签名不匹配 → 全量重建
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

    每种索引对应一个 FAISS IndexFlatIP（内积 = 归一化后的余弦相似度）。
    四个 map 将 FAISS 内部索引位置映射回图节点/三元组标识。

    Attributes:
        node_index (`faiss.Index`):
            节点语义索引，编码文本 = name,description
        relation_index (`faiss.Index`):
            关系名索引，编码文本 = 关系名称
        triple_index (`faiss.Index`):
            三元组语义索引，编码文本 = head_name,relation,tail_name
        comm_index (`faiss.Index`):
            社区索引，编码文本 = comm_name,comm_description
        node_map (`Dict[int, str]`):
            {FAISS 索引位置: 节点 ID}
        relation_map (`Dict[int, str]`):
            {FAISS 索引位置: 关系名称}
        triple_map (`Dict[int, Tuple]`):
            {FAISS 索引位置: (头节点ID, 关系, 尾节点ID)}
        comm_map (`Dict[int, str]`):
            {FAISS 索引位置: 社区节点 ID}
        graph_signature (`str`):
            构建时的图 MD5 签名，用于缓存一致性校验
    """

    node_index: faiss.Index
    relation_index: faiss.Index
    triple_index: faiss.Index
    comm_index: faiss.Index
    node_map: Dict[int, str]
    relation_map: Dict[int, str]
    triple_map: Dict[int, Tuple]
    comm_map: Dict[int, str]
    graph_signature: str = ""


# ─── 图签名 ───


def compute_graph_signature(graph: nx.MultiDiGraph) -> str:
    """计算图的唯一签名（MD5）

    对节点ID排序列表和边 (u:relation:keywords:description:v) 排序列表拼接后取 MD5。
    用于判断图是否发生变更，从而决定缓存是否失效。

    Args:
        graph (`nx.MultiDiGraph`):
            知识图谱 NetworkX 图对象

    Returns:
        `str`:
            32 字符 MD5 十六进制字符串
    """
    node_ids = sorted(graph.nodes())
    edges = sorted(
        f"{u}:{data.get('relation', '')}:{data.get('keywords', '')}:{data.get('description', '')}:{v}"
        for u, v, data in graph.edges(data=True)
    )
    content = "|".join(node_ids) + "||" + "|".join(edges)
    return hashlib.md5(content.encode()).hexdigest()


# ─── 一致性令牌 ───


def _consistency_path(cache_dir: str, dataset: str) -> str:
    """一致性令牌文件路径

    Args:
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称

    Returns:
        `str`: 令牌文件绝对路径
    """
    return os.path.join(cache_dir, dataset, "_consistency.json")


def _load_consistency_token(cache_dir: str, dataset: str) -> Optional[str]:
    """读取缓存的图签名

    Args:
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称

    Returns:
        `Optional[str]`:
            缓存中的图签名 MD5，若文件不存在或损坏则返回 None
    """
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
    """持久化图签名 + 构建时间

    Args:
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称
        graph_signature (`str`): 当前图的 MD5 签名
    """
    path = _consistency_path(cache_dir, dataset)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"graph_signature": graph_signature, "built_at": time.time()}, f)


def check_consistency(graph: nx.MultiDiGraph, cache_dir: str, dataset: str) -> bool:
    """检查缓存的图签名与当前图是否匹配

    所有缓存（FAISS 索引、文本缓存、倒排索引）共享此校验，
    一旦图变更 → 全量失效 → 全量重建。

    Args:
        graph (`nx.MultiDiGraph`): 当前图对象
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称

    Returns:
        `bool`: True 表示缓存有效，False 表示需要重建
    """
    cached_sig = _load_consistency_token(cache_dir, dataset)
    if cached_sig is None:
        return False
    return cached_sig == compute_graph_signature(graph)


# ─── 工具函数 ───


def _get_node_text_simple(graph: nx.MultiDiGraph, node_id: str) -> str:
    """获取节点文本（简化版，仅用于构建 FAISS 索引时）

    与 text_processor.get_node_text 不同，这里使用逗号分隔，
    不包含 description 后的空格。

    Args:
        graph (`nx.MultiDiGraph`): 图对象
        node_id (`str`): 节点ID

    Returns:
        `str`: "name,description" 格式的文本
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

    流程：
      1. 遍历图中所有节点，提取 name+description 文本
      2. 用 SentenceTransformer 编码为稠密向量
      3. 构建 IndexFlatIP（内积 = L2 归一化后的余弦相似度）
      4. 建立 {索引位置: 节点ID} 映射

    Args:
        graph (`nx.MultiDiGraph`): 知识图谱
        encoder: SentenceTransformer 编码器实例

    Returns:
        `Tuple[faiss.Index, Dict[int, str]]`:
            - faiss.Index: 节点语义索引
            - Dict[int, str]: {FAISS 内部索引: 节点 ID}
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
    fallback 通过编码空字符串检测。

    Args:
        encoder: 编码器实例

    Returns:
        `int`: 嵌入向量的维度
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

    输入：图中出现的所有不重复关系名称。
    输出：IndexFlatIP + {索引位置: 关系名称}。

    Args:
        graph (`nx.MultiDiGraph`): 知识图谱
        encoder: SentenceTransformer 编码器

    Returns:
        `Tuple[faiss.Index, Dict[int, str]]`:
            - faiss.Index: 关系名索引
            - Dict[int, str]: {FAISS 内部索引: 关系名称}
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

    输入：所有边的关系三元组 (头ID, 关系名称, 尾ID)。
    索引文本格式："头节点name,关系名称,尾节点name"。

    .. note::
        节点 name 在此处会被重新编码，与 build_node_index 存在重复计算。
        大图场景下可考虑复用节点嵌入以节省时间。

    Args:
        graph (`nx.MultiDiGraph`): 知识图谱
        encoder: SentenceTransformer 编码器

    Returns:
        `Tuple[faiss.Index, Dict[int, Tuple]]`:
            - faiss.Index: 三元组语义索引
            - Dict[int, Tuple]: {FAISS 内部索引: (头ID, 关系, 尾ID)}
    """
    triples = []
    for u, v, data in graph.edges(data=True):
        if "relation" in data:
            kw = data.get("keywords") or data.get("relation", "")
            desc = data.get("description", "")
            triples.append((u, data["relation"], v, kw, desc))
    texts = []
    for h, r, t, kw, desc in triples:
        idx_text = f"{_get_node_text_simple(graph, h)},{kw},{_get_node_text_simple(graph, t)}"
        if desc:
            idx_text += f" | {desc}"
        texts.append(idx_text)
    if not texts:
        dim = _detect_dim(encoder)
        return faiss.IndexFlatIP(dim), {}
    embeddings = encoder.encode(texts)
    embeddings_np = embeddings.astype("float32")
    dim = embeddings_np.shape[1]
    index = faiss.IndexFlatIP(dim)
    faiss.normalize_L2(embeddings_np)
    index.add(embeddings_np)
    triple_map = {i: (u, rel, v) for i, (u, rel, v, kw, desc) in enumerate(triples)}
    return index, triple_map


def build_community_index(
    graph: nx.MultiDiGraph,
    encoder,
) -> Tuple[faiss.Index, Dict[int, str]]:
    """构建社区 FAISS 索引

    输入：所有 label="community" 节点的 name+description 文本。
    跳过名称和描述均为空的社区节点。

    Args:
        graph (`nx.MultiDiGraph`): 知识图谱（含社区超节点）
        encoder: SentenceTransformer 编码器

    Returns:
        `Tuple[faiss.Index, Dict[int, str]]`:
            - faiss.Index: 社区索引
            - Dict[int, str]: {FAISS 内部索引: 社区节点 ID}
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
    """一站式构建全部四种 FAISS 索引

    顺序构建节点、关系、三元组、社区索引，计算图签名后聚合为 FAISSIndexSet。

    Args:
        graph (`nx.MultiDiGraph`): 知识图谱
        encoder: SentenceTransformer 编码器

    Returns:
        `FAISSIndexSet`: 四种索引 + 映射 + 图签名
    """
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
    """FAISS 的 C++ I/O 不支持中文路径，做 ASCII 安全映射

    委托给 retriever_utils.safe_faiss_path 处理。

    Args:
        original_path (`str`): 原始路径（可能含中文）
        cache_root (`str`): 缓存根目录

    Returns:
        `str`: ASCII 安全路径
    """
    return retriever_utils.safe_faiss_path(original_path, cache_root)


def save_index_set(index_set: FAISSIndexSet, cache_dir: str, dataset: str):
    """将四个 FAISS 索引 + 映射文件 + 一致性令牌写入磁盘

    磁盘文件结构（cache_dir/dataset/）：
      - node.index, relation.index, triple.index, comm.index  — FAISS 二进制索引
      - node_map.json, relation_map.json, triple_map.json, comm_map.json  — JSON 映射
      - _consistency.json  — 图签名令牌

    Args:
        index_set (`FAISSIndexSet`): 待持久化的索引集合
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称
    """
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

    流程：
      1. 先校验图签名是否匹配
      2. 加载 4 个 index + 4 个 map（缺一不可）
      3. 重新计算当前图签名写入返回对象

    Args:
        graph (`nx.MultiDiGraph`): 当前图对象（用于签名校验和计算）
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称

    Returns:
        `Optional[FAISSIndexSet]`:
            - 成功加载返回 FAISSIndexSet
            - 签名不匹配或文件缺失返回 None（触发上游重建）
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
    """在节点索引中搜索 top-k 节点

    搜索数量为 min(top_k * 3, 节点总数)，保证召回率后再由上层筛选。

    Args:
        index_set (`FAISSIndexSet`): FAISS 索引集合
        query_embed (`np.ndarray`): 查询向量 (1, dim)
        top_k (`int`): 目标返回数量

    Returns:
        `List[str]`:
            节点 ID 列表，按 FAISS 相似度降序，最多 top_k*3 个
    """
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
    """在关系索引中搜索 top-k 关系

    Args:
        index_set (`FAISSIndexSet`): FAISS 索引集合
        query_embed (`np.ndarray`): 查询向量 (1, dim)
        top_k (`int`): 返回数量

    Returns:
        `List[str]`:
            关系名称列表，按 FAISS 相似度降序
    """
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
    """在三元组索引中搜索 top-k 三元组

    Args:
        index_set (`FAISSIndexSet`): FAISS 索引集合
        query_embed (`np.ndarray`): 查询向量 (1, dim)
        top_k (`int`): 返回数量

    Returns:
        `List[Tuple[str, str, str]]`:
            [(头节点ID, 关系名称, 尾节点ID), ...] 按 FAISS 相似度降序
    """
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
    """在社区索引中搜索 top-k 社区

    Args:
        index_set (`FAISSIndexSet`): FAISS 索引集合
        query_embed (`np.ndarray`): 查询向量 (1, dim)
        top_k (`int`): 返回数量

    Returns:
        `List[str]`:
            社区节点 ID 列表，按 FAISS 相似度降序
    """
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
