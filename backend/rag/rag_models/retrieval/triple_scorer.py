"""三元组评分与重排序

功能：
- 实体相似度计算（单节点 / 批量）
- 三元组相关性评分（余弦相似度 + 关系类型加权）
- 多路径结果合并排序
- 三元组格式化输出
"""

from typing import Dict, List, Tuple

import torch
import torch.nn.functional as F

from rag.rag_models.retrieval.text_processor import (
    build_triple_text,
    get_node_properties,
    get_node_text,
    is_valid_node_text,
)
from loguru import logger

# 对特定关系类型给予额外加分（如 "is", "born" 等事实性关系）
_RELATION_BONUS_KEYWORDS = {
    "is",
    "was",
    "has",
    "had",
    "contains",
    "located",
    "born",
    "died",
    "是",
    "位于"
}


# ─── 实体相似度 ───


def compute_entity_similarity(
    encoder,
    query_embed: torch.Tensor,
    node_text: str,
    cache: Dict[str, torch.Tensor] = {},
    node_id: str = "",
) -> float:
    """计算查询与单个实体的余弦相似度

    优先使用缓存中的节点嵌入，避免重复编码
    """
    if not is_valid_node_text(node_text):
        return 0.0
    try:
        if cache and node_id and node_id in cache:
            node_embed = cache[node_id]
        else:
            node_embed = (
                torch.tensor(encoder.encode(node_text)).float().to(query_embed.device)
            )
            if cache is not None and node_id:
                cache[node_id] = node_embed
        sim = F.cosine_similarity(
            query_embed.unsqueeze(0), node_embed.unsqueeze(0), dim=1
        ).item()
        return max(0.0, sim)
    except Exception as e:
        logger.error(f"Error computing entity similarity: {e}")
        return 0.0


def batch_compute_entity_similarities(
    encoder,
    query_embed: torch.Tensor,
    nodes_with_texts: List[Tuple[str, str]],
    cache: Dict[str, torch.Tensor] = {},
) -> Dict[str, float]:
    """批量计算查询与多个实体的余弦相似度

    输入: [(node_id, node_text), ...]
    输出: {node_id: similarity}
    """
    texts = []
    valid_items = []
    for node_id, node_text in nodes_with_texts:
        if not is_valid_node_text(node_text):
            continue
        if cache and node_id in cache:
            texts.append("")
            valid_items.append((node_id, node_text, True))
        else:
            texts.append(node_text)
            valid_items.append((node_id, node_text, False))
    if not valid_items:
        return {}

    results = {}
    try:
        # 仅对未缓存的文本编码
        if any(not cached for _, _, cached in valid_items):
            embeddings = encoder.encode(texts, convert_to_tensor=True).to(
                query_embed.device
            )
            for i, (node_id, node_text, cached) in enumerate(valid_items):
                if cached:
                    embed = cache[node_id]
                else:
                    embed = embeddings[i]
                    if cache is not None:
                        cache[node_id] = embed
                sim = F.cosine_similarity(
                    query_embed.unsqueeze(0), embed.unsqueeze(0), dim=1
                ).item()
                results[node_id] = max(0.0, sim)
        else:
            # 全部命中缓存，直接计算
            for node_id, _, _ in valid_items:
                embed = cache[node_id]
                sim = F.cosine_similarity(
                    query_embed.unsqueeze(0), embed.unsqueeze(0), dim=1
                ).item()
                results[node_id] = max(0.0, sim)
    except Exception:
        # 退化为单个计算
        for node_id, node_text, _ in valid_items:
            results[node_id] = compute_entity_similarity(
                encoder, query_embed, node_text, cache, node_id
            )
    return results


def _score_single_triple(similarity: float, relation: str) -> float:
    """对单个三元组打分：基础相似度 + 关系类型加权"""
    bonus = 0.1 if relation.lower() in _RELATION_BONUS_KEYWORDS else 0.0
    return max(0.0, similarity + bonus)


# ─── 三元组重排序 ───


def rerank_triples(
    encoder,
    query_embed: torch.Tensor,
    triples: List[Tuple[str, str, str]],
    graph=None,
    top_k: int = 20,
) -> List[Tuple[str, str, str, float]]:
    """批量编码三元组文本并计算与查询的余弦相似度，返回带分数的结果"""
    if not triples:
        return []
    triple_texts = []
    valid_triples = []
    for h, r, t in triples:
        if graph is not None:
            text = build_triple_text(graph, h, r, t)
        else:
            text = f"{h} {r} {t}"
        if text and is_valid_node_text(text):
            triple_texts.append(text)
            valid_triples.append((h, r, t))
    if not valid_triples:
        return []
    try:
        embeddings = encoder.encode(triple_texts, convert_to_tensor=True).to(
            query_embed.device
        )
        similarities = F.cosine_similarity(query_embed.unsqueeze(0), embeddings, dim=1)
        scored = []
        for i, (h, r, t) in enumerate(valid_triples):
            score = _score_single_triple(similarities[i].item(), r)
            if score > 0.05:
                scored.append((h, r, t, score))
        scored.sort(key=lambda x: x[3], reverse=True)
        return scored[:top_k]
    except Exception as e:
        logger.error(f"Batch triple reranking failed: {e}, falling back to individual")
        return rerank_triples_individual(encoder, query_embed, triples, graph, top_k)


def rerank_triples_individual(
    encoder,
    query_embed: torch.Tensor,
    triples: List[Tuple[str, str, str]],
    graph=None,
    top_k: int = 20,
) -> List[Tuple[str, str, str, float]]:
    """逐个编码三元组并评分（batch 编码失败时的 fallback）"""
    scored = []
    for h, r, t in triples:
        try:
            if graph is not None:
                text = build_triple_text(graph, h, r, t)
            else:
                text = f"{h} {r} {t}"
            if not text or not is_valid_node_text(text):
                continue
            embed = torch.tensor(encoder.encode(text)).float().to(query_embed.device)
            sim = F.cosine_similarity(
                query_embed.unsqueeze(0), embed.unsqueeze(0), dim=1
            ).item()
            score = _score_single_triple(sim, r)
            if score > 0.05:
                scored.append((h, r, t, score))
        except Exception:
            continue
    scored.sort(key=lambda x: x[3], reverse=True)
    return scored[:top_k]


# ─── 结果合并 ───


def merge_and_sort_scored_triples(
    path1_triples: List[Tuple[str, str, str]],
    path2_scored: List[Tuple[str, str, str, float]],
    encoder,
    query_embed: torch.Tensor,
    top_k: int = 20,
    graph=None,
) -> List[Tuple[str, str, str, float]]:
    """合并两条检索路径的结果，去重后按分数排序

    Path1 的三元组无分数，需要先重排序再合并
    """
    all_scored = list(path2_scored)
    if path1_triples:
        path1_scored = rerank_triples(encoder, query_embed, path1_triples, graph, top_k)
        all_scored.extend(path1_scored)
    all_scored.sort(key=lambda x: x[3], reverse=True)
    return all_scored[:top_k]


def format_scored_triples(
    graph,
    scored_triples: List[Tuple[str, str, str, float]],
) -> List[str]:
    """将带分数的三元组格式化为可读字符串，用于 LLM 上下文

    格式: "(头文本 [属性], 关系, 尾文本 [属性]) [score: X.XXX]"
    """
    formatted = []
    for h, r, t, score in scored_triples:
        head_text = get_node_text(graph, h)
        tail_text = get_node_text(graph, t)
        if not is_valid_node_text(head_text) or not is_valid_node_text(tail_text):
            continue
        head_props = get_node_properties(graph, h)
        tail_props = get_node_properties(graph, t)
        triple_text = f"({head_text} {head_props}, {r}, {tail_text} {tail_props}) [score: {score:.3f}]"
        formatted.append(triple_text)
    return formatted
