"""Chunk（文本块）检索模块

功能：
- 构建 chunk 嵌入 + FAISS 索引
- 按查询相似度检索 chunk
- 检索结果重排序（FAISS 分数 + 余弦相似度加权平均，关联三元组相似度从 FAISS index 重建）
- 持久化/加载（独立于图签名的 chunk 签名校验）

数据流：
  build_chunk_embeddings(encoder, chunk2id) → {chunk_id: embedding}, faiss.Index
  build_chunk_index(encoder, chunk2id, cache_dir, dataset) → cache, index, id_map
  search_chunks(index, query_embed, chunk2id, id_map, top_k)
    → {"chunk_ids": [...], "scores": [...], "chunk_contents": [...]}
   rerank_chunks(results, query_embed, top_k, triple_index, chunk_to_triple_positions, triple_weight)
    → {"chunk_ids": [...], "scores": [...], "chunk_contents": [...]}

   三元组相似度使用 FAISS triple_index.reconstruct() 读取预计算嵌入，无需重新编码。

Chunk 签名机制（独立于图签名）：
  基于 chunk_id 集合的 MD5，仅 chunk 变更时重建，图变更不影响 chunk 缓存。

反向回溯：
  extract_chunk_ids_from_nodes(graph, nodes) → Set[chunk_id]
  extract_chunk_ids_from_triples(graph, scored_triples) → Set[chunk_id]
  通过实体节点的 properties["chunk id"] 从检索结果回溯源文本块。
"""

import hashlib
import json
import os
import time
from typing import Dict, List, Optional, Tuple

import faiss
import torch
import torch.nn.functional as F

from rag.rag_models.retrieval.text_processor import get_node_chunk_id
from loguru import logger
from rag.rag_models.retrieval import utils as retriever_utils


# ─── Chunk 签名（独立于图签名） ───


def compute_chunk_signature(chunk2id: Dict[str, str]) -> str:
    """计算 chunk 数据集的签名（仅依赖 chunk_id 集合，不依赖图）

    Args:
        chunk2id (`Dict[str, str]`): {chunk_id: chunk_text}

    Returns:
        `str`: 32 字符 MD5 十六进制字符串
    """
    sorted_ids = sorted(chunk2id.keys())
    content = "|".join(sorted_ids)
    return hashlib.md5(content.encode()).hexdigest()


def _chunk_consistency_path(cache_dir: str, dataset: str) -> str:
    """Chunk 一致性令牌文件路径

    Args:
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称

    Returns:
        `str`: 令牌文件路径
    """
    return os.path.join(cache_dir, dataset, "_chunk_consistency.json")


def _check_chunk_consistency(
    chunk2id: Dict[str, str],
    cache_dir: str,
    dataset: str,
) -> bool:
    """检查缓存的 chunk 签名与当前 chunk 是否匹配

    Args:
        chunk2id (`Dict[str, str]`): 当前 chunk 数据集
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称

    Returns:
        `bool`: True 表示缓存有效，False 需要重建
    """
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
    """持久化 chunk 签名 + 构建时间

    Args:
        chunk2id (`Dict[str, str]`): chunk 数据集
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称
    """
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

    每个 chunk 文本用 encoder 编码后存入 IndexFlatIP（内积 = 余弦相似度）。

    Args:
        encoder: SentenceTransformer 编码器
        chunk2id (`Dict[str, str]`): {chunk_id: chunk_text}
        batch_size (`int`): 编码批次大小

    Returns:
        `Tuple[Dict[str, torch.Tensor], faiss.Index]`:
            - {chunk_id: 嵌入向量}
            - FAISS IndexFlatIP 索引
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
    """在 chunk FAISS 索引中搜索 top-k chunk

    搜索数量为 min(top_k * 2, 索引大小) 以增加召回。

    Args:
        chunk_index (`faiss.Index`): chunk FAISS 索引
        query_embed (`torch.Tensor`): 查询嵌入向量
        chunk2id (`Dict[str, str]`): {chunk_id: chunk_text}
        index_to_chunk_id (`Dict[int, str]`): {FAISS 索引位置: chunk_id}
        top_k (`int`): 目标返回数量

    Returns:
        `Dict`:
            - "chunk_ids": List[str] — 匹配的 chunk ID 列表
            - "scores": List[float] — FAISS 相似度分数
            - "chunk_contents": List[str] — chunk 文本内容
    """
    query_np = query_embed.cpu().numpy().reshape(1, -1).astype("float32")
    search_k = min(top_k * 2, len(index_to_chunk_id))
    if search_k <= 0:
        logger.warning(
            f"Chunk FAISS index is empty or zero-length "
            f"(top_k={top_k}, index_to_chunk_id size={len(index_to_chunk_id)})"
        )
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
    chunk_results: Dict,
    query_embed: torch.Tensor,
    top_k: int,
    triple_index=None,
    chunk_to_triple_positions: Dict[str, List[int]] = None,
    triple_weight: float = 0.3,
) -> Dict:
    """对 chunk 检索结果重排序

    最终分数 = (1 - triple_weight) * 文本相似度 + triple_weight * 关联三元组最大相似度。
    三元组相似度从 FAISS triple_index 中通过 reconstruct 取出预计算嵌入，避免重新编码。

    Args:
        chunk_results (`Dict`): search_chunks 的返回结果
        query_embed (`torch.Tensor`): 查询嵌入向量
        top_k (`int`): 最终返回数量
        triple_index (`faiss.Index`, optional):
            FAISS 三元组索引，传入后启用 triple 加权。
        chunk_to_triple_positions (`Dict[str, List[int]]`, optional):
            {chunk_id: [FAISS triple 位置]}。
        triple_weight (`float`): 三元组相似度权重，默认 0.3。

    Returns:
        `Dict`:
            - "chunk_ids": List[str] — 重排序后的 top-k chunk ID
            - "scores": List[float] — 最终融合分数
            - "chunk_contents": List[str] — 对应 chunk 文本
    """
    chunk_ids = chunk_results.get("chunk_ids", [])
    scores = chunk_results.get("scores", [])
    chunk_contents = chunk_results.get("chunk_contents", [])
    if not chunk_ids:
        logger.info("rerank_chunks called with empty chunk_ids, returning empty")
        return {"chunk_ids": [], "scores": [], "chunk_contents": []}
    logger.info(f"rerank_chunks: re-ranking {len(chunk_ids)} chunks (triple_weight={triple_weight})")

    reranked = []
    for cid, faiss_score, content in zip(chunk_ids, scores, chunk_contents):
        try:
            triple_max_sim = 0.0
            if triple_index is not None and chunk_to_triple_positions:
                positions = chunk_to_triple_positions.get(cid, [])
                if positions:
                    vecs = []
                    for pos in positions:
                        raw = triple_index.reconstruct(int(pos)).astype("float32")
                        vecs.append(torch.from_numpy(raw).to(query_embed.device))
                    if vecs:
                        triple_embeds = torch.stack(vecs)
                        triple_sims = F.cosine_similarity(
                            query_embed.unsqueeze(0), triple_embeds, dim=1
                        )
                        triple_max_sim = max(0.0, triple_sims.max().item())

            text_sim = max(0.0, faiss_score)
            final_score = (1 - triple_weight) * text_sim + triple_weight * triple_max_sim
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
    不匹配或强制重建时重新编码。

    Args:
        encoder: SentenceTransformer 编码器
        chunk2id (`Dict[str, str]`): {chunk_id: chunk_text}
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称
        batch_size (`int`): 编码批次大小
        force (`bool`): 是否强制重建（忽略缓存）

    Returns:
        `Tuple[Dict[str, torch.Tensor], faiss.Index, Dict[int, str]]`:
            - {chunk_id: 嵌入向量}
            - FAISS IndexFlatIP
            - {FAISS 索引位置: chunk_id}
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
    """Chunk 嵌入缓存文件路径 (.pt)

    Args:
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称

    Returns:
        `str`: PyTorch 缓存文件路径
    """
    return os.path.join(cache_dir, dataset, "chunk_embedding_cache.pt")


def _chunk_index_path(cache_dir: str, dataset: str) -> str:
    """Chunk FAISS 索引文件路径 (.index)

    Args:
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称

    Returns:
        `str`: FAISS 索引文件路径
    """
    return os.path.join(cache_dir, dataset, "chunk.index")


def _chunk_id_map_path(cache_dir: str, dataset: str) -> str:
    """Chunk ID 映射文件路径 (.json)

    Args:
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称

    Returns:
        `str`: JSON 映射文件路径
    """
    return os.path.join(cache_dir, dataset, "chunk_id_map.json")


def _save_chunk_cache(
    cache: dict,
    index: faiss.Index,
    cache_dir: str,
    dataset: str,
    chunk2id: Dict[str, str],
):
    """持久化 chunk 嵌入、FAISS 索引和 ID 映射

    Args:
        cache (`dict`): {chunk_id: 嵌入向量}
        index (`faiss.Index`): FAISS 索引
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称
        chunk2id (`Dict[str, str]`): chunk 数据集（用于重建 id_map）
    """
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
    """从磁盘加载 chunk 缓存

    三个文件（嵌入缓存、FAISS 索引、ID 映射）缺一不可。

    Args:
        cache_dir (`str`): 缓存根目录
        dataset (`str`): 数据集名称

    Returns:
        `Optional[Tuple[Dict, faiss.Index, Dict[int, str]]]`:
            ({chunk_id: 嵌入}, FAISS 索引, {FAISS 位置: chunk_id})
            任意文件缺失或损坏返回 None
    """
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


# ─── 工具函数（三元组 → chunk 回溯） ───


def extract_chunk_ids_from_nodes(graph, nodes: list) -> set:
    """从一组节点中提取所有的 chunk_id

    通过 get_node_chunk_id 读取每个节点的 properties["chunk id"]，
    用于将图谱检索结果反向关联回原始文本块。

    Args:
        graph: NetworkX MultiDiGraph
        nodes (`list`): 节点 ID 列表

    Returns:
        `set`: chunk_id 集合
    """
    chunk_ids = set()
    for node in nodes:
        if node in graph.nodes:
            cid = get_node_chunk_id(graph, node)
            if cid:
                chunk_ids.add(str(cid))
    return chunk_ids


def extract_chunk_ids_from_triples(graph, scored_triples: list) -> set:
    """从带分数的三元组中提取所有的 chunk_id

    遍历三元组的头节点和尾节点，调用 extract_chunk_ids_from_nodes。

    Args:
        graph: NetworkX MultiDiGraph
        scored_triples (`list`): [(h, r, t, score), ...]

    Returns:
        `set`: chunk_id 集合
    """
    nodes = []
    for t in scored_triples:
        if len(t) >= 3:
            nodes.extend([t[0], t[2]])
    return extract_chunk_ids_from_nodes(graph, nodes)
