"""Path2 检索：纯三元组 + 社区驱动的知识图谱检索

执行流程：
1. 在三元组 FAISS 索引中搜索匹配的三元组
2. 对每个匹配的三元组，展开 3-hop 邻居
3. 用 FAISS 重新评分所有收集到的三元组
4. 在社区 FAISS 索引中搜索匹配的社区
5. 展开社区成员节点
6. 合并所有节点并评分

数据流：
  retrieve_path2(graph, index_set, query_embed, top_k, name_to_id)
    → {
        "triple_nodes": [node_id, ...],        # 三元组路径途经的节点
        "comm_nodes": [node_id, ...],           # 社区展开的成员节点
        "scores": {node_id: 0.5},               # 节点评分（当前为 fallback 常数）
        "scored_triples": [(h, r, t, score), ...]  # 带评分的三元组（供合并使用）
      }
"""

from collections import deque
from typing import Dict, List, Set, Tuple

import faiss
import networkx as nx
import torch

from rag.rag_models.retrieval.faiss_index import FAISSIndexSet, search_communities
from rag.rag_models.retrieval.community_utils import get_community_nodes


def _deduplicate_triples(triples: List[Tuple]) -> List[Tuple]:
    """三元组去重（保留首次出现顺序）

    Args:
        triples (`List[Tuple]`): 三元组列表

    Returns:
        `List[Tuple]`: 去重后的三元组
    """
    seen = set()
    result = []
    for t in triples:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def _get_3hop_neighbors(
    graph: nx.MultiDiGraph,
    center: str,
    cache: Dict = None,
) -> Set[str]:
    """BFS 3-hop 邻居展开（带缓存）

    从 center 节点出发，广度优先搜索 3 层范围内的所有节点。

    Args:
        graph (`nx.MultiDiGraph`): 图对象
        center (`str`): 起始节点 ID
        cache (`Dict`, optional): {节点ID: 邻居集合} 缓存

    Returns:
        `Set[str]`: 3-hop 范围内的所有节点 ID（含自身）
    """
    if cache is None:
        cache = {}
    if center in cache:
        return cache[center]
    if center not in graph.nodes:
        return set()
    neighbors = {center}
    visited = {center}
    queue = deque([(center, 0)])
    while queue:
        current, depth = queue.popleft()
        if depth >= 3:
            continue
        for neighbor in graph.neighbors(current):
            if neighbor not in visited:
                visited.add(neighbor)
                neighbors.add(neighbor)
                if depth < 2:
                    queue.append((neighbor, depth + 1))
    cache[center] = neighbors
    return neighbors


def _collect_neighbor_triples(
    graph: nx.MultiDiGraph,
    node: str,
    hop_cache: Dict = None,
) -> List[Tuple]:
    """收集一个节点 3-hop 范围内的所有三元组

    遍历出边和入边，提取有关关系的三元组。

    Args:
        graph (`nx.MultiDiGraph`): 图对象
        node (`str`): 中心节点 ID
        hop_cache (`Dict`, optional): 邻居展开缓存

    Returns:
        `List[Tuple]`: [(头ID, 关系, 尾ID), ...]
    """
    if node not in graph.nodes:
        return []
    neighbor_triples = []
    neighbors = _get_3hop_neighbors(graph, node, hop_cache)
    for neighbor in neighbors:
        for _, target, edge_data in graph.out_edges(neighbor, data=True):
            if "relation" in edge_data:
                neighbor_triples.append((neighbor, edge_data["relation"], target))
        for source, _, edge_data in graph.in_edges(neighbor, data=True):
            if "relation" in edge_data:
                neighbor_triples.append((source, edge_data["relation"], neighbor))
    return neighbor_triples


def _retrieve_via_triples(
    graph: nx.MultiDiGraph,
    index_set: FAISSIndexSet,
    query_embed: torch.Tensor,
    top_k: int,
    hop_cache: Dict = None,
) -> List[Tuple[str, str, str, float]]:
    """通过三元组索引检索：搜索 → 3-hop 展开 → FAISS 重评分

    Args:
        graph (`nx.MultiDiGraph`): 图对象
        index_set (`FAISSIndexSet`): FAISS 索引集合
        query_embed (`torch.Tensor`): 查询嵌入
        top_k (`int`): top-k
        hop_cache (`Dict`, optional): BFS 邻居缓存

    Returns:
        `List[Tuple[str, str, str, float]]`:
            [(头ID, 关系, 尾ID, FAISS 评分), ...]
    """
    matched = list(search_triples_hard(index_set, query_embed, top_k))
    all_triples = list(matched)
    for h, r, t in matched:
        all_triples.extend(_collect_neighbor_triples(graph, h, hop_cache))
        all_triples.extend(_collect_neighbor_triples(graph, t, hop_cache))
    unique_triples = _deduplicate_triples(all_triples)
    scored = _score_triples_via_faiss(index_set, query_embed, unique_triples, top_k)
    return scored


def search_triples_hard(
    index_set: FAISSIndexSet,
    query_embed: torch.Tensor,
    top_k: int,
) -> List[Tuple[str, str, str]]:
    """搜索三元组索引，返回 (头ID, 关系, 尾ID) 列表

    Args:
        index_set (`FAISSIndexSet`): FAISS 索引集合
        query_embed (`torch.Tensor`): 查询嵌入
        top_k (`int`): 搜索数量（内部翻倍 x2）

    Returns:
        `List[Tuple[str, str, str]]`:
            [(头ID, 关系, 尾ID), ...] 按 FAISS 原始排序
    """
    query_np = query_embed.cpu().numpy().reshape(1, -1).astype("float32")
    search_k = min(top_k * 2, len(index_set.triple_map))
    if search_k <= 0:
        return []
    _, indices = index_set.triple_index.search(query_np, search_k)
    results = []
    for idx in indices[0]:
        if idx != -1 and idx in index_set.triple_map:
            val = index_set.triple_map[idx]
            results.append(tuple(val) if isinstance(val, list) else val)
    return results


def _score_triples_via_faiss(
    index_set: FAISSIndexSet,
    query_embed: torch.Tensor,
    triples: List[Tuple],
    top_k: int,
) -> List[Tuple[str, str, str, float]]:
    """用 FAISS 三元组索引对候选三元组重新评分

    用查询向量在 triple_index 中搜索，
    命中的三元组获得 FAISS 实际相似度分数，
    未命中的三元组获得默认低分（0.5）。

    Args:
        index_set (`FAISSIndexSet`): FAISS 索引集合
        query_embed (`torch.Tensor`): 查询嵌入
        triples (`List[Tuple]`): 候选三元组列表
        top_k (`int`): 返回 top-k

    Returns:
        `List[Tuple[str, str, str, float]]`:
            [(头ID, 关系, 尾ID, score), ...]
    """
    if not triples:
        return []
    query_np = query_embed.cpu().detach().numpy().reshape(1, -1).astype("float32")
    faiss.normalize_L2(query_np)
    input_set = set(triples)
    search_k = min(len(triples) * 2, 50)
    D, indices = index_set.triple_index.search(query_np, search_k)
    scored = []
    for i, idx in enumerate(indices[0]):
        if idx >= 0 and idx in index_set.triple_map:
            hit = index_set.triple_map[idx]
            hit = tuple(hit) if isinstance(hit, list) else hit
            if hit in input_set:
                scored.append((hit[0], hit[1], hit[2], float(D[0][i])))
    if not scored:
        for h, r, t in triples[:top_k]:
            scored.append((h, r, t, 0.5))
    scored.sort(key=lambda x: x[3], reverse=True)
    return scored[:top_k]


def _retrieve_via_communities(
    graph: nx.MultiDiGraph,
    index_set: FAISSIndexSet,
    query_embed: torch.Tensor,
    top_k: int,
    name_to_id: Dict[str, str] = None,
) -> List[str]:
    """通过社区索引检索：搜索社区 → 展开成员节点

    Args:
        graph (`nx.MultiDiGraph`): 图对象（含社区超节点）
        index_set (`FAISSIndexSet`): FAISS 索引集合
        query_embed (`torch.Tensor`): 查询嵌入
        top_k (`int`): 搜索社区数量
        name_to_id (`Dict[str, str]`, optional): {实体名称: 节点ID}

    Returns:
        `List[str]`: 社区成员实体节点 ID 列表
    """
    matched_communities = search_communities(
        index_set, query_embed.cpu().numpy(), top_k
    )
    nodes = []
    seen = set()
    for comm_id in matched_communities:
        members = get_community_nodes(graph, comm_id, name_to_id)
        for member in members:
            if member not in seen and member in graph.nodes:
                seen.add(member)
                nodes.append(member)
    return nodes


def _build_name_to_id(graph: nx.MultiDiGraph) -> Dict[str, str]:
    """从图中构建 节点名称 → 节点ID 的映射（用于社区成员查找）

    使用 properties.name 而非 get_node_text（后者包含 description），
    确保多词实体名（如 "Harry Potter"）能完整匹配。

    Args:
        graph (`nx.MultiDiGraph`): 图对象

    Returns:
        `Dict[str, str]`: {实体名称: 节点ID}
    """
    mapping = {}
    for node_id in graph.nodes():
        node_data = graph.nodes[node_id]
        props = node_data.get("properties", {})
        name = props.get("name", "").strip()
        if name:
            mapping[name] = node_id
    return mapping


def retrieve_path2(
    graph: nx.MultiDiGraph,
    index_set: FAISSIndexSet,
    query_embed: torch.Tensor,
    top_k: int,
    name_to_id: Dict[str, str] = None,
) -> Dict:
    """Path2 检索入口

    并行执行三元组检索和社区检索，
    合并节点后统一评分，返回 scored_triples 供上层合并使用。

    Args:
        graph (`nx.MultiDiGraph`): 图对象
        index_set (`FAISSIndexSet`): FAISS 索引集合
        query_embed (`torch.Tensor`): 查询嵌入
        top_k (`int`): top-k
        name_to_id (`Dict[str, str]`, optional): 预计算的名称→ID 映射

    Returns:
        `Dict`:
            - "triple_nodes": List[str] — 三元组路径中的节点
            - "comm_nodes": List[str] — 社区展开的节点
            - "scores": Dict[str, float] — {节点ID: 分数}
            - "scored_triples": List[Tuple] — [(h, r, t, score), ...]
    """
    hop_cache = {}
    scored_triples = _retrieve_via_triples(
        graph, index_set, query_embed, top_k, hop_cache
    )
    triple_nodes = set()
    for h, r, t, score in scored_triples:
        if h in graph.nodes:
            triple_nodes.add(h)
        if t in graph.nodes:
            triple_nodes.add(t)
    triple_nodes = list(triple_nodes)

    if name_to_id is None:
        name_to_id = _build_name_to_id(graph)
    comm_nodes = _retrieve_via_communities(
        graph, index_set, query_embed, top_k, name_to_id
    )

    merged_nodes = list(set(triple_nodes + comm_nodes))
    node_scores = _score_nodes_fallback(query_embed, merged_nodes)

    return {
        "triple_nodes": triple_nodes,
        "comm_nodes": comm_nodes,
        "scores": node_scores,
        "scored_triples": scored_triples,
    }


def _score_nodes_fallback(
    query_embed: torch.Tensor,
    nodes: List[str],
) -> Dict[str, float]:
    """节点评分 fallback

    当前返回常数 0.5，后续可替换为编码器实际评分。

    Args:
        query_embed (`torch.Tensor`): 查询嵌入（当前未使用）
        nodes (`List[str]`): 待评分节点

    Returns:
        `Dict[str, float]`: {节点ID: 0.5}
    """
    return {node: 0.5 for node in nodes}
