"""检索核心编排层

职责：
1. RetrievalState：检索运行时的状态容器
2. init_retrieval_state：从 graph_data 创建初始状态
3. build_retrieval_indices：加载/重建 FAISS 索引、文本缓存、倒排索引
4. retrieve：主编排入口（单路径/双路径）
5. retrieve_with_type_filter：Schema 类型过滤编排
6. process_retrieval_results：完整处理流水线（检索→评分→格式化→社区摘要）

整体数据流：
  init_retrieval_state(graph_data, config, chunks_data)
    → RetrievalState  # 包含图、编码器、LLM 客户端、配置、缓存目录
  build_retrieval_indices(state)
    → state.faiss, node_text_cache, node_text_index, chunk_index  # 惰性加载
  process_retrieval_results(state, question, top_k, involved_types)
    → {
        "triples": [str, ...],           # format_scored_triples 结果（已合并）
        "chunk_ids": [str, ...],         # 所有关联的 chunk_id 集合
        "chunk_contents": {id: text},    # chunk_id → 文本内容
        "chunk_retrieval_results": {...},# 直接语义检索的 chunk 结果
        "community_summaries": [dict]    # 关联社区摘要
      }
    , retrieval_time (秒)

检索模式：
  - recall_paths=1: 仅 Path1（节点/关系/关键词/chunk）
  - recall_paths=2: Path1 + Path2（三元组索引/社区）并行
  - involved_types 非空时：Path1 做 Schema 类型过滤，Path2 不变
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import torch
from rag.utils import graph_processor
from rag.utils import call_llm_api
from loguru import logger

from rag.rag_models.retrieval.faiss_index import (
    FAISSIndexSet,
    build_all_indices,
    load_index_set,
    save_index_set,
)
from rag.rag_models.retrieval.text_processor import (
    precompute_node_texts,
    load_node_text_cache,
    save_node_text_cache,
)
from rag.rag_models.retrieval.keyword_search import (
    extract_query_keywords,
    build_and_save_text_index,
    load_text_index,
)
from rag.rag_models.retrieval.chunk_retriever import (
    build_chunk_index,
    extract_chunk_ids_from_nodes,
    extract_chunk_ids_from_triples,
    search_chunks,
    rerank_chunks,
)
from rag.rag_models.retrieval.triple_scorer import (
    merge_and_sort_scored_triples,
    format_scored_triples,
)
from rag.rag_models.retrieval.community_utils import collect_community_summaries
from rag.rag_models.retrieval.type_filter import (
    filter_nodes_by_schema_type,
    similarity_search_on_filtered,
)
from rag.rag_models.retrieval.path1_node_relation import retrieve_path1
from rag.rag_models.retrieval.path2_triple_only import retrieve_path2


@dataclass
class RetrievalState:
    """检索运行时的全部状态

    所有缓存均为惰性加载（在 build_retrieval_indices 中按需加载/重建）。

    Attributes:
        graph: NetworkX MultiDiGraph — 知识图谱
        encoder: SentenceTransformer — 文本编码器
        llm_client: LLM 同步调用客户端
        llm_stream_client: LLM 流式调用客户端
        faiss (`FAISSIndexSet`, optional): 四种 FAISS 索引
        chunk2id (`Dict[str, str]`): {chunk_id: chunk_text}
        chunk_tags (`Dict[str, dict]`): {chunk_id: {macro_tags: ..., entities: ...}}
        config: 全局配置对象
        dataset (`str`): 数据集名称
        top_k (`int`): 检索 top-k 数量
        recall_paths (`int`): 检索路径数（1=仅Path1, 2=Path1+Path2）
        cache_dir (`str`): 缓存根目录
        node_text_cache (`Dict[str, str]`): 惰性加载的节点文本缓存
        node_text_index (`Dict[str, set]`): 惰性加载的倒排索引
        chunk_embedding_cache (`Dict[str, torch.Tensor]`): chunk 嵌入缓存
        chunk_faiss_index: chunk FAISS 索引
        chunk_id_to_index (`Dict[int, str]`): {FAISS位置: chunk_id}
        chunk_embeddings_precomputed (`bool`): chunk 索引是否已构建
        indices_built (`bool`): 所有检索索引是否已加载
    """

    graph: Any = None
    encoder: Any = None
    llm_client: Any = None
    llm_stream_client: Any = None
    faiss: Optional[FAISSIndexSet] = None
    chunk2id: Dict[str, str] = field(default_factory=dict)
    chunk_tags: Dict[str, dict] = field(default_factory=dict)
    config: Any = None
    dataset: str = ""
    top_k: int = 5
    recall_paths: int = 2
    cache_dir: str = "retriever/faiss_cache_new"
    # 惰性缓存（在 build_retrieval_indices 中初始化）
    node_text_cache: Dict[str, str] = field(default_factory=dict)
    node_text_index: Dict[str, set] = field(default_factory=dict)
    chunk_embedding_cache: Dict[str, torch.Tensor] = field(default_factory=dict)
    chunk_faiss_index: Any = None
    chunk_id_to_index: Dict[int, str] = field(default_factory=dict)
    chunk_embeddings_precomputed: bool = False
    indices_built: bool = False


def init_retrieval_state(
    dataset: str,
    config,
    graph_data: Optional[list] = None,
    json_path: str = "",
    chunks_data: Optional[dict] = None,
    top_k: int = 5,
    recall_paths: int = 2,
) -> RetrievalState:
    """从图数据创建检索状态

    支持从内存 graph_data 或文件路径 json_path 加载图，
    其余组件（LLM 客户端、编码器）从 config 获取。

    Args:
        dataset (`str`): 数据集名称
        config: 配置对象（含 embeddings.get_model 等）
        graph_data (`list`, optional):
            图数据列表，格式：[{start_node:{...}, relation:..., end_node:{...}}, ...]
        json_path (`str`, optional):
            图数据 JSON 文件路径（与 graph_data 二选一）
        chunks_data (`dict`, optional):
            {chunk_id: str | dict} chunk 数据。
            dict 格式：{"chunk": str, "macro_tags": {...}, "entities": [...]}
        top_k (`int`): 检索 top-k 数量
        recall_paths (`int`): 检索路径数（1 或 2）

    Returns:
        `RetrievalState`:
            初始化后的检索状态（尚未构建索引，需调用 build_retrieval_indices）
    """
    cfg = config

    if graph_data is not None:
        graph = graph_processor.load_graph_from_json_data(graph_data)
    elif json_path:
        graph = graph_processor.load_graph_from_json(json_path)
    else:
        ds_cfg = cfg.get_dataset_config(dataset)
        if ds_cfg and ds_cfg.graph_output:
            graph = graph_processor.load_graph_from_json(ds_cfg.graph_output)
        else:
            raise ValueError("No graph data or path provided")

    chunk2id = {}
    chunk_tags = {}
    if chunks_data:
        for cid, entry in chunks_data.items():
            if isinstance(entry, str):
                chunk2id[cid] = entry
            else:
                chunk2id[cid] = entry.get("chunk", "")
                tags = {}
                if entry.get("macro_tags"):
                    tags["macro_tags"] = entry["macro_tags"]
                if entry.get("entities"):
                    tags["entities"] = entry["entities"]
                chunk_tags[cid] = tags

    state = RetrievalState(
        graph=graph,
        encoder=cfg.embeddings.get_model(),
        llm_client=call_llm_api.LLMCompletionCall(),
        llm_stream_client=call_llm_api.LLMCompletionCallStream(),
        chunk2id=chunk2id,
        chunk_tags=chunk_tags,
        config=cfg,
        dataset=dataset,
        top_k=top_k if top_k != 5 else cfg.retrieval.top_k,
        recall_paths=(
            recall_paths if recall_paths != 2 else cfg.retrieval.recall_paths
        ),
        cache_dir=cfg.retrieval.cache_dir,
    )
    return state


def build_retrieval_indices(state: RetrievalState):
    """构建/加载所有检索索引

    惰性加载（首次调用时构建，通过 state.indices_built 避免重复）。

    加载顺序：
      1. FAISS 索引（节点/关系/三元组/社区）— 图签名校验
      2. 节点文本缓存 — 图签名校验
      3. 倒排文本索引 — 图签名校验
      4. Chunk 索引（如果有 chunk 数据）— 独立 chunk 签名校验

    Args:
        state (`RetrievalState`): 检索状态，会被原地修改
    """
    if state.indices_built:
        return

    # FAISS 索引
    state.faiss = load_index_set(state.graph, state.cache_dir, state.dataset)
    if state.faiss is None:
        logger.info("Building FAISS indices from scratch...")
        state.faiss = build_all_indices(state.graph, state.encoder)
        save_index_set(state.faiss, state.cache_dir, state.dataset)

    # 节点文本缓存
    state.node_text_cache = load_node_text_cache(
        state.graph, state.cache_dir, state.dataset
    )
    if not state.node_text_cache:
        logger.info("Precomputing node texts...")
        state.node_text_cache = precompute_node_texts(state.graph)
        save_node_text_cache(state.node_text_cache, state.cache_dir, state.dataset)

    # 倒排文本索引
    state.node_text_index = load_text_index(state.graph, state.cache_dir, state.dataset)
    if not state.node_text_index:
        logger.info("Building node text index...")
        state.node_text_index = build_and_save_text_index(
            state.graph, state.node_text_cache, state.cache_dir, state.dataset
        )

    # Chunk 索引
    if state.chunk2id:
        cache, index, id_map = build_chunk_index(
            state.encoder,
            state.chunk2id,
            state.cache_dir,
            state.dataset,
            force=False,
        )
        state.chunk_embedding_cache = cache
        state.chunk_faiss_index = index
        state.chunk_id_to_index = id_map
        state.chunk_embeddings_precomputed = True

    state.indices_built = True
    logger.info(f"Retrieval indices built for dataset {state.dataset}")


def _get_query_embedding(state: RetrievalState, query: str) -> torch.Tensor:
    """对查询文本编码为向量，自动跟随编码器所在设备

    Args:
        state (`RetrievalState`): 检索状态
        query (`str`): 查询文本

    Returns:
        `torch.Tensor`:
            查询嵌入向量（float32）
    """
    embed = state.encoder.encode(query, convert_to_tensor=True)
    return embed.float()


def _chunk_retrieval_fn(state: RetrievalState):
    """返回一个闭包，供 path1 检索时作为 chunk 检索回调

    闭包模式允许延迟绑定 state 的状态。

    Args:
        state (`RetrievalState`): 检索状态

    Returns:
        `Callable`:
            接收 (query_embed, top_k) 的闭包，返回 chunk 检索结果 dict
    """

    def _fn(query_embed: torch.Tensor, top_k: int) -> Dict:
        if not state.chunk_embeddings_precomputed:
            return {"chunk_ids": [], "scores": [], "chunk_contents": []}
        results = search_chunks(
            state.chunk_faiss_index,
            query_embed,
            state.chunk2id,
            state.chunk_id_to_index,
            top_k,
        )
        return rerank_chunks(
            state.encoder, results, query_embed, top_k, state.chunk_tags
        )

    return _fn


def retrieve(
    state: RetrievalState,
    question: str,
    involved_types: dict,
) -> Tuple[torch.Tensor, Dict]:
    """主编排入口

    根据 recall_paths 选择检索策略：
    - 1：仅 Path1（节点/关系检索）
    - 2：Path1 + Path2 并行检索

    关键词在主调线程中提取（避免 spaCy 线程安全问题），
    传入 Path1 时已提取完毕。

    Args:
        state (`RetrievalState`): 检索状态
        question (`str`): 用户问题
        involved_types (`dict`):
            涉及的数据类型（当前未用于普通检索，仅供接口统一）

    Returns:
        `Tuple[torch.Tensor, Dict]`:
            - query_embed: 查询嵌入向量
            - result: 检索结果 dict，包含 "path1_results" / "path2_results" / "chunk_ids"
    """
    if not state.indices_built:
        build_retrieval_indices(state)

    question_embed = _get_query_embedding(state, question)
    keywords = extract_query_keywords(question) if question else []

    if state.recall_paths == 1:
        path1 = retrieve_path1(
            state.graph,
            state.faiss,
            state.encoder,
            question_embed,
            question,
            keywords,
            state.node_text_cache,
            state.node_text_index,
            _chunk_retrieval_fn(state),
            state.config,
            state.top_k,
        )
        chunk_ids = extract_chunk_ids_from_nodes(state.graph, path1["top_nodes"])
        if path1.get("chunk_results"):
            chunk_ids.update(path1["chunk_results"].get("chunk_ids", []))
        result = {"path1_results": path1, "chunk_ids": list(chunk_ids)}
    else:
        result = _parallel_dual_path(state, question_embed, question, keywords)

    return question_embed, result


def _parallel_dual_path(
    state: RetrievalState,
    question_embed: torch.Tensor,
    question: str,
    keywords: List[str],
) -> Dict:
    """双路径检索

    Path1 在主线程运行（其内部已有 ThreadPoolExecutor 用于子任务并行），
    Path2 在单独线程中运行，完成后合并两者结果。
    避免嵌套 ThreadPoolExecutor 导致线程过度订阅。

    Args:
        state (`RetrievalState`): 检索状态
        question_embed (`torch.Tensor`): 查询嵌入
        question (`str`): 用户问题
        keywords (`List[str]`): 关键词列表

    Returns:
        `Dict`:
            - "path1_results": Path1 检索结果
            - "path2_results": Path2 检索结果
            - "chunk_ids": 合并后的 chunk_id 列表
    """
    path2_result = [None]

    def _run_path2():
        path2_result[0] = retrieve_path2(
            state.graph,
            state.faiss,
            question_embed,
            state.top_k,
        )

    path2_thread = threading.Thread(target=_run_path2)
    path2_thread.start()

    path1_results = retrieve_path1(
        state.graph,
        state.faiss,
        state.encoder,
        question_embed,
        question,
        keywords,
        state.node_text_cache,
        state.node_text_index,
        _chunk_retrieval_fn(state),
        state.config,
        state.top_k,
    )

    path2_thread.join()
    path2_results = path2_result[0]

    path1_chunk_ids = extract_chunk_ids_from_nodes(
        state.graph, path1_results.get("top_nodes", [])
    )
    path2_chunk_ids = extract_chunk_ids_from_triples(
        state.graph, path2_results.get("scored_triples", [])
    )
    path3_chunk_ids = set()
    if path1_results.get("chunk_results"):
        path3_chunk_ids = set(path1_results["chunk_results"].get("chunk_ids", []))

    all_chunk_ids = path1_chunk_ids | path2_chunk_ids | path3_chunk_ids
    return {
        "path1_results": path1_results,
        "path2_results": path2_results,
        "chunk_ids": list(all_chunk_ids),
    }


# ─── 类型过滤检索 ───


def retrieve_with_type_filter(
    state: RetrievalState,
    question: str,
    involved_types: dict,
) -> Tuple[torch.Tensor, Dict]:
    """带 Schema 类型过滤的检索

    当 involved_types 为空时退化为普通 retrieve()。
    recall_paths=2 时：Path1 使用类型过滤，Path2 使用原始逻辑（无过滤）。

    Args:
        state (`RetrievalState`): 检索状态
        question (`str`): 用户问题
        involved_types (`dict`):
            {"nodes": [...], "relations": [...], "attributes": [...]}
            从 GraphQ 分解中获取

    Returns:
        `Tuple[torch.Tensor, Dict]`:
            同 retrieve() 的返回格式
    """
    if not involved_types or not any(
        involved_types.get(k, []) for k in ["nodes", "relations", "attributes"]
    ):
        return retrieve(state, question)

    question_embed = _get_query_embedding(state, question)
    target_node_types = involved_types.get("nodes", [])

    if state.recall_paths == 1:
        filtered_nodes = filter_nodes_by_schema_type(state.graph, target_node_types)
        if filtered_nodes:
            node_results = similarity_search_on_filtered(
                state.faiss, question_embed, filtered_nodes, state.top_k
            )
            triple_list = []
            for n in node_results.get("top_nodes", []):
                for _, v, d in state.graph.out_edges(n, data=True):
                    triple_list.append((n, d.get("relation", ""), v))
            chunk_ids = extract_chunk_ids_from_nodes(
                state.graph, node_results.get("top_nodes", [])
            )
            result = {
                "path1_results": {
                    "top_nodes": node_results["top_nodes"],
                    "one_hop_triples": triple_list,
                },
                "chunk_ids": list(chunk_ids),
            }
        else:
            _, result = retrieve(state, question)
    else:
        # Path1 类型过滤 + Path2 原始检索，避免重复计算查询嵌入
        hybrid = _hybrid_type_filtered(
            state, question_embed, question, target_node_types
        )
        path2_results = retrieve_path2(
            state.graph, state.faiss, question_embed, state.top_k
        )
        chunk_ids = hybrid.get("chunk_ids", [])
        path2_chunk_ids = extract_chunk_ids_from_triples(
            state.graph, path2_results.get("scored_triples", [])
        )
        result = {
            "path1_results": hybrid.get("path1_results", {}),
            "path2_results": path2_results,
            "chunk_ids": list(set(chunk_ids) | path2_chunk_ids),
        }

    return question_embed, result


def _hybrid_type_filtered(
    state,
    question_embed,
    question,
    target_node_types,
):
    """对 Path1 使用类型过滤，返回过滤后的节点和三元组

    .. note::
        question 参数当前未使用，保留接口一致性。

    Args:
        state (`RetrievalState`): 检索状态
        question_embed (`torch.Tensor`): 查询嵌入
        question (`str`): 用户问题（未使用）
        target_node_types (`list`): 目标节点类型列表

    Returns:
        `Dict`:
            - "path1_results": {"top_nodes": [...], "one_hop_triples": [...]}
            - "chunk_ids": List[str]
    """
    filtered_nodes = filter_nodes_by_schema_type(state.graph, target_node_types)
    path1_results = {}
    if filtered_nodes:
        node_results = similarity_search_on_filtered(
            state.faiss, question_embed, filtered_nodes, state.top_k
        )
        triple_list = []
        for n in node_results.get("top_nodes", []):
            for _, v, d in state.graph.out_edges(n, data=True):
                triple_list.append((n, d.get("relation", ""), v))
        path1_results = {
            "top_nodes": node_results["top_nodes"],
            "one_hop_triples": triple_list,
        }
    chunk_ids = extract_chunk_ids_from_nodes(
        state.graph, path1_results.get("top_nodes", [])
    )
    return {"path1_results": path1_results, "chunk_ids": list(chunk_ids)}


# ─── 完整处理流水线 ───


def process_retrieval_results(
    state: RetrievalState,
    question: str,
    top_k: int = 20,
    involved_types: dict = None,
) -> Tuple[Dict, float]:
    """完整的检索处理流水线

    步骤：
      1. 检索（带可选类型过滤）
      2. Chunk 重排序
      3. 三元组合并/评分/格式化
      4. 社区摘要收集
      5. 封装返回结果

    Args:
        state (`RetrievalState`): 检索状态
        question (`str`): 用户问题
        top_k (`int`): 返回 top-k 三元组数量
        involved_types (`dict`, optional):
            {"nodes": [...], "relations": [...], "attributes": [...]}

    Returns:
        `Tuple[Dict, float]`:
            - retrieval_results: Dict
                - "triples": List[str] — format_scored_triples 结果
                - "chunk_ids": List[str] — 所有关联 chunk_id
                - "chunk_contents": Dict[str, str] — {chunk_id: text}
                - "chunk_retrieval_results": Dict — 直接语义 chunk 检索结果
                - "community_summaries": List[Dict] — 社区信息
            - retrieval_time: float — 检索耗时（秒）
    """
    start = time.time()

    if involved_types:
        question_embed, results = retrieve_with_type_filter(
            state, question, involved_types
        )
    else:
        question_embed, results = retrieve(state, question)

    retrieval_time = time.time() - start

    # 处理 chunk 检索结果
    chunk_results = results.get("path1_results", {}).get("chunk_results")
    if chunk_results:
        chunk_retrieval_results = chunk_results
        chunk_retrieval_ids = set(chunk_results.get("chunk_ids", []))
    else:
        chunk_retrieval_results = {
            "chunk_ids": [],
            "scores": [],
            "chunk_contents": [],
        }
        chunk_retrieval_ids = set()

    # 三元组评分与合并
    scored_triples = _collect_all_scored(state, results, question_embed)
    limited_scored = scored_triples[:top_k]
    formatted_triples = format_scored_triples(state.graph, limited_scored)
    triple_chunk_ids = extract_chunk_ids_from_triples(state.graph, limited_scored)

    # 合并 chunk_id（直接语义召回 + 三元组回溯）
    all_chunk_ids = chunk_retrieval_ids | triple_chunk_ids
    matching_chunks = {}
    for cid in all_chunk_ids:
        if cid in state.chunk2id:
            matching_chunks[cid] = state.chunk2id[cid]

    # 社区摘要
    community_summaries = collect_community_summaries(state.graph, limited_scored)

    retrieval_results = {
        "triples": formatted_triples,
        "chunk_ids": list(all_chunk_ids),
        "chunk_contents": matching_chunks,
        "chunk_retrieval_results": chunk_retrieval_results,
        "community_summaries": community_summaries,
    }
    return retrieval_results, retrieval_time


def _collect_all_scored(
    state: RetrievalState,
    results: Dict,
    question_embed: torch.Tensor,
) -> List:
    """收集并合并两条路径的带分三元组

    Args:
        state (`RetrievalState`): 检索状态
        results (`Dict`): retrieve() 返回的结果
        question_embed (`torch.Tensor`): 查询嵌入

    Returns:
        `List[Tuple[str, str, str, float]]`:
            [(头ID, 关系, 尾ID, score), ...] 按分数降序
    """
    path2_scored = results.get("path2_results", {}).get("scored_triples", [])
    path1_triples = results.get("path1_results", {}).get("one_hop_triples", [])
    if not path1_triples and not path2_scored:
        return []
    return merge_and_sort_scored_triples(
        path1_triples,
        path2_scored,
        state.encoder,
        question_embed,
        top_k=20,
        graph=state.graph,
    )
