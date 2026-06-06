"""Chunk（文本块）检索模块

功能：
- 构建 chunk 嵌入 + FAISS 索引
- 按查询相似度检索 chunk
- 检索结果重排序（FAISS 分数 + 余弦相似度加权平均）
- 持久化/加载（独立于图签名的 chunk 签名校验）
"""

import hashlib
import json
import os
import time
from typing import Dict, Optional, Tuple

import faiss
import torch
import torch.nn.functional as F

from rag.rag_models.retrieval.text_processor import get_node_chunk_id
from loguru import logger
from rag.rag_models.retrieval import utils as retriever_utils


def compute_chunk_signature(chunk2id: Dict[str, str]) -> str:
    """计算 chunk 数据集的签名（独立于图，仅依赖 chunk_id 集合）"""
    sorted_ids = sorted(chunk2id.keys())
    content = "|".join(sorted_ids)
    return hashlib.md5(content.encode()).hexdigest()


def _chunk_consistency_path(cache_dir: str, dataset: str) -> str:
    return os.path.join(cache_dir, dataset, "_chunk_consistency.json")


def _check_chunk_consistency(
    chunk2id: Dict[str, str],
    cache_dir: str,
    dataset: str,
) -> bool:
    path = _chunk_consistency_path(cache_dir, dataset)
    if not os.path.exists(path):
        return False
    try:
        with open(path) as f:
            meta = json.load(f)
        return meta.get("chunk_signature") == compute_chunk_signature(chunk2id)
    except Exception:
        return False


def _save_chunk_consistency(
    chunk2id: Dict[str, str],
    cache_dir: str,
    dataset: str,
):
    path = _chunk_consistency_path(cache_dir, dataset)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(
            {
                "chunk_signature": compute_chunk_signature(chunk2id),
                "built_at": time.time(),
            },
            f,
        )


# ─── 构建 ───


def build_chunk_embeddings(
    encoder,
    chunk2id: Dict[str, str],
    batch_size: int = 100,
) -> Tuple[Dict[str, torch.Tensor], faiss.Index]:
    """构建 chunk 嵌入和 FAISS 索引

    每个 chunk 文本用 encoder 编码后存入 IndexFlatIP
    """
    chunk_ids = list(chunk2id.keys())
    texts = [chunk2id[cid] for cid in chunk_ids]
    embeddings = encoder.encode(texts, convert_to_tensor=True)
    chunk_embedding_cache = {}
    for i, cid in enumerate(chunk_ids):
        chunk_embedding_cache[cid] = embeddings[i].detach()
    embeddings_np = embeddings.cpu().numpy().astype("float32")
    dim = embeddings_np.shape[1]
    index = faiss.IndexFlatIP(dim)
    faiss.normalize_L2(embeddings_np)
    index.add(embeddings_np)
    return chunk_embedding_cache, index


def search_chunks(
    chunk_index: faiss.Index,
    query_embed: torch.Tensor,
    chunk2id: Dict[str, str],
    index_to_chunk_id: Dict[int, str],
    top_k: int,
) -> Dict:
    """在 chunk FAISS 索引中搜索 top-k chunk"""
    query_np = query_embed.cpu().numpy().reshape(1, -1).astype("float32")
    search_k = min(top_k * 2, len(index_to_chunk_id))
    if search_k <= 0:
        return {"chunk_ids": [], "scores": [], "chunk_contents": []}
    D, indices = chunk_index.search(query_np, search_k)
    chunk_ids = []
    scores = []
    chunk_contents = []
    for i, idx in enumerate(indices[0]):
        if idx != -1 and idx in index_to_chunk_id:
            cid = index_to_chunk_id[idx]
            chunk_ids.append(cid)
            scores.append(float(D[0][i]))
            chunk_contents.append(chunk2id.get(cid, ""))
    return {"chunk_ids": chunk_ids, "scores": scores, "chunk_contents": chunk_contents}


def rerank_chunks(
    encoder,
    chunk_results: Dict,
    query_embed: torch.Tensor,
    top_k: int,
    chunk_tags: Dict[str, dict] = None,
) -> Dict:
    """对 chunk 检索结果重排序

    策略：(FAISS 语义分 + 重编码余弦相似度) / 2 + tag 匹配分 × 0.3

    chunk_tags 结构：{chunk_id: {macro_tags: {intent, topic, function}, entities: [str]}}
    """
    chunk_ids = chunk_results.get("chunk_ids", [])
    scores = chunk_results.get("scores", [])
    chunk_contents = chunk_results.get("chunk_contents", [])
    if not chunk_ids:
        return {"chunk_ids": [], "scores": [], "chunk_contents": []}
    reranked = []
    for cid, faiss_score, content in zip(chunk_ids, scores, chunk_contents):
        try:
            chunk_embed = torch.tensor(encoder.encode(content)).float().to(query_embed.device)
            sim = F.cosine_similarity(
                query_embed.unsqueeze(0), chunk_embed.unsqueeze(0), dim=1
            ).item()
            sim = max(0.0, sim)
            combined = (faiss_score + sim) / 2  # 语义分
            # combined = faiss_score # 语义分
            # combined = sim  # 语义分
            # tag 匹配分
            tag_score = 0.0
            if chunk_tags and cid in chunk_tags:
                t = chunk_tags[cid]
                tag_text_parts = []
                mt = t.get("macro_tags", {})
                if mt.get("intent"):
                    tag_text_parts.append(mt["intent"])
                if mt.get("topic"):
                    tag_text_parts.append(mt["topic"])
                if mt.get("function"):
                    tag_text_parts.append(mt["function"])
                tag_text_parts.extend(t.get("entities", []))
                tag_text = " ".join(tag_text_parts)
                if tag_text.strip():
                    tag_embed = (
                        torch.tensor(encoder.encode(tag_text))
                        .float()
                        .to(query_embed.device)
                    )
                    tag_score = F.cosine_similarity(
                        query_embed.unsqueeze(0), tag_embed.unsqueeze(0), dim=1
                    ).item()
                    tag_score = max(0.0, tag_score)

            final_score = combined # + 0.3 * tag_score
            reranked.append((cid, final_score, content))
        except Exception as e:
            logger.warning(f"rerank_chunks error for {cid}: {e}")
            reranked.append((cid, faiss_score, content))
    reranked.sort(key=lambda x: x[1], reverse=True)
    top = reranked[:top_k]
    return {
        "chunk_ids": [x[0] for x in top],
        "scores": [x[1] for x in top],
        "chunk_contents": [x[2] for x in top],
    }


def build_chunk_index(
    encoder,
    chunk2id: Dict[str, str],
    cache_dir: str,
    dataset: str,
    batch_size: int = 100,
    force: bool = False,
) -> Tuple[Dict[str, torch.Tensor], faiss.Index, Dict[int, str]]:
    """构建或加载 chunk 索引

    优先从缓存加载（校验 chunk 签名），
    不匹配或强制重建时重新编码
    """
    if not force and _check_chunk_consistency(chunk2id, cache_dir, dataset):
        cached = _load_chunk_cache(cache_dir, dataset)
        if cached:
            return cached
    cache, index = build_chunk_embeddings(encoder, chunk2id, batch_size)
    index_to_chunk_id = {i: cid for i, cid in enumerate(chunk2id.keys())}
    _save_chunk_cache(cache, index, cache_dir, dataset, chunk2id)
    _save_chunk_consistency(chunk2id, cache_dir, dataset)
    return cache, index, index_to_chunk_id


# ─── 持久化 ───


def _chunk_cache_path(cache_dir: str, dataset: str) -> str:
    return os.path.join(cache_dir, dataset, "chunk_embedding_cache.pt")


def _chunk_index_path(cache_dir: str, dataset: str) -> str:
    return os.path.join(cache_dir, dataset, "chunk.index")


def _chunk_id_map_path(cache_dir: str, dataset: str) -> str:
    return os.path.join(cache_dir, dataset, "chunk_id_map.json")


def _save_chunk_cache(
    cache: dict,
    index: faiss.Index,
    cache_dir: str,
    dataset: str,
    chunk2id: Dict[str, str],
):
    os.makedirs(os.path.join(cache_dir, dataset), exist_ok=True)
    retriever_utils.save_embedding_cache(
        cache, _chunk_cache_path(cache_dir, dataset), logger=logger
    )
    faiss.write_index(index, _chunk_index_path(cache_dir, dataset))
    id_map = {i: cid for i, cid in enumerate(chunk2id.keys())}
    with open(_chunk_id_map_path(cache_dir, dataset), "w") as f:
        json.dump(id_map, f)


def _load_chunk_cache(
    cache_dir: str,
    dataset: str,
) -> Optional[Tuple[Dict, faiss.Index, Dict[int, str]]]:
    if not os.path.exists(_chunk_cache_path(cache_dir, dataset)):
        return None
    if not os.path.exists(_chunk_index_path(cache_dir, dataset)):
        return None
    if not os.path.exists(_chunk_id_map_path(cache_dir, dataset)):
        return None
    try:
        cache = retriever_utils.load_embedding_cache(
            _chunk_cache_path(cache_dir, dataset), "cpu", logger=logger
        )
        index = faiss.read_index(_chunk_index_path(cache_dir, dataset))
        with open(_chunk_id_map_path(cache_dir, dataset)) as f:
            id_map = json.load(f)
        id_map = {int(k): v for k, v in id_map.items()}
        if cache and index and id_map:
            return cache, index, id_map
    except Exception as e:
        logger.warning(f"Failed to load chunk cache: {e}")
    return None


# ─── 工具函数 ───


def extract_chunk_ids_from_nodes(graph, nodes: list) -> set:
    """从一组节点中提取所有的 chunk_id"""
    chunk_ids = set()
    for node in nodes:
        if node in graph.nodes:
            cid = get_node_chunk_id(graph, node)
            if cid:
                chunk_ids.add(str(cid))
    return chunk_ids


def extract_chunk_ids_from_triples(graph, scored_triples: list) -> set:
    """从带分数的三元组中提取所有的 chunk_id"""
    nodes = []
    for t in scored_triples:
        if len(t) >= 3:
            nodes.extend([t[0], t[2]])
    return extract_chunk_ids_from_nodes(graph, nodes)
