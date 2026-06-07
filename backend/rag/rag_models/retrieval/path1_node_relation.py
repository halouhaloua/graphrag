"""Path1 检索：节点/关系驱动的知识图谱检索

执行策略（内部通过 ThreadPoolExecutor 并行）：
1. FAISS 节点索引搜索 → 余弦相似度评分
2. 关键词倒排索引匹配 → 余弦相似度评分
3. FAISS 关系索引搜索
4. 邻居展开（1-hop + 路径搜索 + 关系匹配）
5. Chunk 检索

数据流：
  retrieve_path1(graph, index_set, encoder, query_embed, question, keywords, ...)
    → {
        "top_nodes": [node_id, ...],           # Path1 匹配的 top-k 节点
        "top_relations": [rel_name, ...],       # FAISS 关系检索结果
        "one_hop_triples": [(h, r, t), ...],    # 所有路径收集的三元组
        "chunk_results": {...}                   # chunk 检索结果
      }

并行子任务：
  ┌─ FAISS 节点搜索 ──→ 批量余弦相似度 ──┐
  ├─ FAISS 关系搜索 ─────────────────────┤
  ├─ Chunk 检索 ─────────────────────────┤
  ├─ 关键词搜索 ──→ 批量余弦相似度 ──────┤→ 合并节点 → 邻居展开 → 路径搜索 → 汇总
  └────────────────────────────────────────┘
"""

from typing import Callable, Dict, List, Tuple

import torch
import concurrent.futures

import networkx as nx

from rag.rag_models.retrieval.faiss_index import (
    FAISSIndexSet,
    search_nodes,
    search_relations,
)
from rag.rag_models.retrieval.keyword_search import (
    search_by_keywords,
    path_based_search,
    get_relation_matched_triples,
)
from rag.rag_models.retrieval.triple_scorer import batch_compute_entity_similarities
from rag.rag_models.retrieval.text_processor import get_node_text


def _optimized_neighbor_expansion(
    graph: nx.MultiDiGraph,
    top_nodes: List[str],
) -> List[Tuple[str, str, str]]:
    """从 top_nodes 展开 1-hop 邻居，收集三元组

    先收集所有邻居节点，再双向检查边关系（出边+入边），
    避免重复遍历邻居集合。

    Args:
        graph (`nx.MultiDiGraph`): 图对象
        top_nodes (`List[str]`): 候选节点 ID 列表

    Returns:
        `List[Tuple[str, str, str]]`:
            [(头ID, 关系, 尾ID), ...]
    """
    all_neighbors = set()
    for node in top_nodes:
        if node in graph.nodes:
            all_neighbors.update(graph.neighbors(node))
    triples = []
    for node in top_nodes:
        for neighbor in all_neighbors:
            edge_data = graph.get_edge_data(node, neighbor)
            if edge_data:
                rel = list(edge_data.values())[0].get("relation", "")
                if rel:
                    triples.append((node, rel, neighbor))
            edge_data2 = graph.get_edge_data(neighbor, node)
            if edge_data2:
                rel = list(edge_data2.values())[0].get("relation", "")
                if rel:
                    triples.append((neighbor, rel, node))
    return triples


def retrieve_path1(
    graph: nx.MultiDiGraph,
    index_set: FAISSIndexSet,
    encoder,
    query_embed: torch.Tensor,
    question: str,
    keywords: List[str],
    node_text_cache: Dict[str, str],
    node_text_index: Dict[str, set],
    chunk_retrieval_fn: Callable,
    config,
    top_k: int,
    max_workers: int = 4,
) -> Dict:
    """Path1 检索入口

    先进行 FAISS 节点搜索 + 关键词搜索（有并行子任务），
    然后进行邻居展开、路径搜索、关系匹配，最后汇总三元组和 chunk。

    Args:
        graph (`nx.MultiDiGraph`): 知识图谱
        index_set (`FAISSIndexSet`): FAISS 索引集合
        encoder: SentenceTransformer 编码器
        query_embed (`torch.Tensor`): 查询嵌入向量
        question (`str`): 原始查询文本（未使用，保留接口）
        keywords (`List[str]`): extract_query_keywords 提取的关键词
        node_text_cache (`Dict[str, str]`): {节点ID: 节点文本}
        node_text_index (`Dict[str, set]`): 倒排索引 {单词: {节点ID}}
        chunk_retrieval_fn (`Callable`): chunk 检索闭包
        config: 配置对象
        top_k (`int`): 返回 top-k 节点
        max_workers (`int`): 内部 ThreadPoolExecutor 线程数

    Returns:
        `Dict`:
            - "top_nodes": List[str] — 合并后的 top-k 节点（FAISS + 关键词）
            - "top_relations": List[str] — FAISS 关系检索命中的关系名
            - "one_hop_triples": List[Tuple] — 邻居+路径+关系匹配的三元组
            - "chunk_results": Dict — chunk 检索结果
    """
    if config:
        max_workers = getattr(getattr(config, "retrieval", None), "faiss", None)
        max_workers = getattr(max_workers, "max_workers", 4) if max_workers else 4

    search_k = min(top_k * 3, 50)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 并行：FAISS 节点搜索 + 关系搜索 + chunk 检索
        future_faiss_nodes = executor.submit(
            search_nodes, index_set, query_embed.cpu().numpy(), search_k
        )
        future_faiss_relations = executor.submit(
            search_relations, index_set, query_embed.cpu().numpy(), top_k
        )
        future_chunk_retrieval = executor.submit(chunk_retrieval_fn, query_embed, top_k)

        faiss_candidate_nodes = future_faiss_nodes.result()

        # FAISS 命中节点 → 批量计算与查询的余弦相似度
        future_faiss_sim = executor.submit(
            _batch_similarities,
            encoder,
            query_embed,
            faiss_candidate_nodes,
            graph,
            node_text_cache,
        )

        # 关键词命中节点（在倒排索引中查找）
        keyword_nodes = (
            search_by_keywords(node_text_index, keywords) if keywords else []
        )
        existing_faiss = set(faiss_candidate_nodes)
        keyword_candidate_nodes = [n for n in keyword_nodes if n not in existing_faiss]

        # 关键词命中节点 → 批量计算余弦相似度（在后台线程）
        future_keyword_sim = None
        if keyword_candidate_nodes:
            future_keyword_sim = executor.submit(
                _batch_similarities,
                encoder,
                query_embed,
                keyword_candidate_nodes,
                graph,
                node_text_cache,
            )

        # 合并 FAISS + 关键词结果，按分数排序取 top-k
        candidate_nodes = []
        faiss_similarities = future_faiss_sim.result()
        candidate_nodes.extend((node, sim) for node, sim in faiss_similarities.items())
        if future_keyword_sim:
            keyword_similarities = future_keyword_sim.result()
            candidate_nodes.extend(
                (node, sim) for node, sim in keyword_similarities.items() if sim > 0.05
            )
        candidate_nodes.sort(key=lambda x: x[1], reverse=True)
        top_nodes = [node for node, score in candidate_nodes[:top_k] if score > 0.05]

        all_relations = future_faiss_relations.result()

        # 并行：路径搜索 + 邻居展开
        future_path_triples = None
        if keywords:
            future_path_triples = executor.submit(
                path_based_search,
                graph,
                top_nodes,
                keywords,
                max_depth=2,
            )
        future_neighbor_triples = executor.submit(
            _optimized_neighbor_expansion,
            graph,
            top_nodes,
        )

        one_hop_triples = future_neighbor_triples.result()
        path_triples = future_path_triples.result() if future_path_triples else []
        relation_triples = get_relation_matched_triples(graph, top_nodes, all_relations)

        all_triples = list(
            {triple for triple in one_hop_triples + path_triples + relation_triples}
        )
        chunk_results = future_chunk_retrieval.result()

    return {
        "top_nodes": top_nodes,
        "top_relations": all_relations,
        "one_hop_triples": all_triples,
        "chunk_results": chunk_results,
    }


def _batch_similarities(
    encoder,
    query_embed: torch.Tensor,
    nodes: List[str],
    graph: nx.MultiDiGraph,
    text_cache: Dict[str, str],
) -> Dict[str, float]:
    """批量计算查询与一组节点的余弦相似度

    .. note::
        当前没有持久化嵌入缓存，相同节点在不同查询或子问题间会重复编码。
        可考虑将嵌入缓存传入以复用。

    Args:
        encoder: SentenceTransformer 编码器
        query_embed (`torch.Tensor`): 查询嵌入
        nodes (`List[str]`): 待评分节点 ID 列表
        graph (`nx.MultiDiGraph`): 图对象
        text_cache (`Dict[str, str]`): {节点ID: 文本}

    Returns:
        `Dict[str, float]`: {节点ID: 余弦相似度}
    """
    if not nodes:
        return {}
    items = []
    for n in nodes:
        text = text_cache.get(n) or get_node_text(graph, n)
        items.append((n, text))
    return batch_compute_entity_similarities(encoder, query_embed, items)
