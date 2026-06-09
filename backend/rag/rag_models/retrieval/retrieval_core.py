"""检索核心编排层

职责：
1. RetrievalState：检索运行时的状态容器（含 top_k_triple / top_k_chunk / chunk_to_triple_positions）
2. init_retrieval_state：从 graph_data + chunks_data 创建初始状态
3. build_retrieval_indices：加载/重建 FAISS 索引、文本缓存、倒排索引、chunk→triple 位置映射
4. retrieve：主编排入口（单路径/双路径），支持 adj_triple/adj_chunk 调整
5. retrieve_with_type_filter：Schema 类型过滤编排
6. process_retrieval_results：完整处理流水线，支持 retrieval_type 参数（micro/macro）

整体数据流：
  init_retrieval_state(graph_data, config, chunks_data, top_k_triple, top_k_chunk)
    → RetrievalState
  build_retrieval_indices(state)
    → state.faiss, node_text_cache, node_text_index, chunk_index, chunk_to_triple_positions
  process_retrieval_results(state, question, involved_types, retrieval_type)
    → {
        "triples": [str, ...],           # format_scored_triples（含 description 行）
        "chunk_ids": [str, ...],         # 所有关联的 chunk_id（直接召回 ∪ 三元组回溯）
        "chunk_contents": {id: text},
        "chunk_retrieval_results": {...},
        "community_summaries": [dict]    # 含 key_members 增强信息
      }
    , retrieval_time (秒)

检索模式：
  - recall_paths=1: 仅 Path1（节点/关系/关键词/chunk）
  - recall_paths=2: Path1 + Path2（三元组索引/社区）并行
  - involved_types 非空时：Path1 做 Schema 类型过滤，Path2 不变
  - retrieval_type: "micro"（微观，偏实体/chunk）| "macro"（宏观，偏三元组/社区）
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
        config: 全局配置对象
        dataset (`str`): 数据集名称
        top_k_triple (`int`): 三元组检索 top-k 数量
        top_k_chunk (`int`): 直接 chunk 语义召回 top-k 数量
        recall_paths (`int`): 检索路径数（1=仅Path1, 2=Path1+Path2）
        cache_dir (`str`): 缓存根目录
        node_text_cache (`Dict[str, str]`): 惰性加载的节点文本缓存
        node_text_index (`Dict[str, set]`): 惰性加载的倒排索引
        chunk_embedding_cache (`Dict[str, torch.Tensor]`): chunk 嵌入缓存
        chunk_faiss_index: chunk FAISS 索引
        chunk_id_to_index (`Dict[int, str]`): {FAISS位置: chunk_id}
        chunk_embeddings_precomputed (`bool`): chunk 索引是否已构建
        chunk_to_triple_positions (`Dict[str, List[int]]`): {chunk_id: [FAISS triple 位置]}
        indices_built (`bool`): 所有检索索引是否已加载
    """

    graph: Any = None
    encoder: Any = None
    llm_client: Any = None
    llm_stream_client: Any = None
    faiss: Optional[FAISSIndexSet] = None
    chunk2id: Dict[str, str] = field(default_factory=dict)
    config: Any = None
    dataset: str = ""
    top_k_triple: int = 5
    top_k_chunk: int = 5
    recall_paths: int = 2
    cache_dir: str = "retriever/faiss_cache_new"
    # 惰性缓存（在 build_retrieval_indices 中初始化）
    node_text_cache: Dict[str, str] = field(default_factory=dict)
    node_text_index: Dict[str, set] = field(default_factory=dict)
    chunk_embedding_cache: Dict[str, torch.Tensor] = field(default_factory=dict)
    chunk_faiss_index: Any = None
    chunk_id_to_index: Dict[int, str] = field(default_factory=dict)
    chunk_embeddings_precomputed: bool = False
    chunk_to_triple_positions: Dict[str, List[int]] = field(default_factory=dict)
    indices_built: bool = False


def init_retrieval_state(
    dataset: str,
    config,
    graph_data: Optional[list] = None,
    json_path: str = "",
    chunks_data: Optional[dict] = None,
    top_k_triple: int = 5,
    top_k_chunk: int = 5,
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
            dict 格式：{"chunk": str, "entities": [...]}
        top_k_triple (`int`): 三元组检索 top-k 数量
        top_k_chunk (`int`): 直接 chunk 语义召回 top-k 数量
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
    if chunks_data:
        for cid, entry in chunks_data.items():
            if isinstance(entry, str):
                chunk2id[cid] = entry
            else:
                chunk2id[cid] = entry.get("chunk", "")
    else:
        # fallback: 从 graph_data 节点属性中扫描 "chunk id"，重建 chunk_id 列表
        if graph_data:
            chunk_id_set = set()
            for rel in graph_data:
                for side in ("start_node", "end_node"):
                    props = rel.get(side, {}).get("properties", {})
                    cid = props.get("chunk id")
                    if cid:
                        if isinstance(cid, list):
                            for c in cid:
                                chunk_id_set.add(str(c))
                        else:
                            chunk_id_set.add(str(cid))
            if chunk_id_set:
                logger.warning(
                    f"chunks_data is empty for dataset {dataset}, "
                    f"reconstructed {len(chunk_id_set)} chunk IDs from graph_data node properties. "
                    "Chunk content will be unavailable, only chunk IDs are recovered."
                )
                for cid in chunk_id_set:
                    chunk2id[cid] = f"[chunk {cid}]"

    state = RetrievalState(
        graph=graph,
        encoder=cfg.embeddings.get_model(),
        llm_client=call_llm_api.LLMCompletionCall(),
        llm_stream_client=call_llm_api.LLMCompletionCallStream(),
        chunk2id=chunk2id,
        config=cfg,
        dataset=dataset,
        top_k_triple=top_k_triple if top_k_triple != 5 else cfg.retrieval.top_k_triple,
        top_k_chunk=top_k_chunk if top_k_chunk != 5 else cfg.retrieval.top_k_chunk,
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

    # 建立 chunk_id → FAISS triple position 映射
    if state.faiss and state.faiss.triple_map:
        chunk_to_pos: Dict[str, List[int]] = {}
        for pos, triple_data in state.faiss.triple_map.items():
            h_id, _, t_id = triple_data[0], triple_data[1], triple_data[2]
            h_data = state.graph.nodes.get(h_id)
            if h_data:
                h_cid = h_data.get("properties", {}).get("chunk id")
                if h_cid:
                    if isinstance(h_cid, list):
                        for c in h_cid:
                            chunk_to_pos.setdefault(c, []).append(pos)
                    else:
                        chunk_to_pos.setdefault(h_cid, []).append(pos)
            t_data = state.graph.nodes.get(t_id)
            if t_data:
                t_cid = t_data.get("properties", {}).get("chunk id")
                if t_cid:
                    if isinstance(t_cid, list):
                        for c in t_cid:
                            chunk_to_pos.setdefault(c, []).append(pos)
                    else:
                        chunk_to_pos.setdefault(t_cid, []).append(pos)
        state.chunk_to_triple_positions = chunk_to_pos
        logger.debug(
            f"Built chunk_to_triple_positions for {len(chunk_to_pos)} chunks "
            f"(from {len(state.faiss.triple_map)} triples)"
        )

    # Chunk 索引
    if state.chunk2id:
        logger.info(f"Building chunk index: {len(state.chunk2id)} chunks for dataset {state.dataset}")
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
    else:
        logger.warning(f"chunk2id is empty for dataset {state.dataset}, chunk retrieval will be skipped")

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
            接收 (query_embed) 的闭包，返回 chunk 检索结果 dict（chunk top-k 由 state.top_k_chunk 内部决定）
    """

    def _fn(query_embed: torch.Tensor) -> Dict:
        if not state.chunk_embeddings_precomputed:
            logger.warning(
                f"chunk_embeddings_precomputed=False for dataset {state.dataset}, "
                f"chunk retrieval returning empty results (chunk2id size={len(state.chunk2id)})"
            )
            return {"chunk_ids": [], "scores": [], "chunk_contents": []}
        chunk_top_k = state.top_k_chunk
        results = search_chunks(
            state.chunk_faiss_index,
            query_embed,
            state.chunk2id,
            state.chunk_id_to_index,
            chunk_top_k,
        )
        triple_weight = getattr(state.config, "retrieval", None)
        triple_weight = getattr(triple_weight, "triple_weight", 0.3) if triple_weight else 0.3
        return rerank_chunks(
            results, query_embed, chunk_top_k,
            triple_index=state.faiss.triple_index if state.faiss else None,
            chunk_to_triple_positions=state.chunk_to_triple_positions,
            triple_weight=triple_weight,
        )

    return _fn


def retrieve(
    state: RetrievalState,
    question: str,
    involved_types: dict,
    adj_triple: int = None,
    adj_chunk: int = None,
) -> Tuple[torch.Tensor, Dict]:
    """主编排入口

    根据 recall_paths 选择检索策略：
    - 1：仅 Path1（节点/关系检索）
    - 2：Path1 + Path2 并行检索

    Args:
        state (`RetrievalState`): 检索状态
        question (`str`): 用户问题
        involved_types (`dict`):
            涉及的数据类型
        adj_triple (`int`, optional):
            调整后的三元组 top_k，None 时使用 state.top_k_triple
        adj_chunk (`int`, optional):
            调整后的 chunk top_k，None 时使用 state.top_k_chunk

    Returns:
        `Tuple[torch.Tensor, Dict]`:
            - query_embed: 查询嵌入向量
            - result: 检索结果 dict
    """
    if adj_triple is None:
        adj_triple = state.top_k_triple
    if adj_chunk is None:
        adj_chunk = state.top_k_chunk

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
            adj_triple,
        )
        chunk_ids = extract_chunk_ids_from_nodes(state.graph, path1["top_nodes"])
        if path1.get("chunk_results"):
            chunk_ids.update(path1["chunk_results"].get("chunk_ids", []))
        result = {"path1_results": path1, "chunk_ids": list(chunk_ids)}
    else:
        result = _parallel_dual_path(state, question_embed, question, keywords, adj_triple=adj_triple)

    return question_embed, result


def _parallel_dual_path(
    state: RetrievalState,
    question_embed: torch.Tensor,
    question: str,
    keywords: List[str],
    adj_triple: int = None,
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

    if adj_triple is None:
        adj_triple = state.top_k_triple

    def _run_path2():
        path2_result[0] = retrieve_path2(
            state.graph, state.faiss, question_embed, adj_triple,
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
        adj_triple,
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
    adj_triple: int = None,
    adj_chunk: int = None,
) -> Tuple[torch.Tensor, Dict]:
    """带 Schema 类型过滤的检索

    当 involved_types 为空时退化为普通 retrieve()。
    recall_paths=2 时：Path1 使用类型过滤，Path2 使用原始逻辑（无过滤）。

    Args:
        state (`RetrievalState`): 检索状态
        question (`str`): 用户问题
        involved_types (`dict`):
            {"nodes": [...], "relations": [...], "attributes": [...]}
        adj_triple (`int`, optional):
            调整后的三元组 top_k
        adj_chunk (`int`, optional):
            调整后的 chunk top_k

    Returns:
        `Tuple[torch.Tensor, Dict]`:
            同 retrieve() 的返回格式
    """
    if adj_triple is None:
        adj_triple = state.top_k_triple
    if adj_chunk is None:
        adj_chunk = state.top_k_chunk

    if not involved_types or not any(
        involved_types.get(k, []) for k in ["nodes", "relations", "attributes"]
    ):
        return retrieve(state, question, {}, adj_triple=adj_triple, adj_chunk=adj_chunk)

    question_embed = _get_query_embedding(state, question)
    target_node_types = involved_types.get("nodes", [])

    if state.recall_paths == 1:
        filtered_nodes = filter_nodes_by_schema_type(state.graph, target_node_types)
        if filtered_nodes:
            hybrid = _hybrid_type_filtered(
                state, question_embed, question, target_node_types
            )
            result = {
                "path1_results": hybrid.get("path1_results", {}),
                "chunk_ids": hybrid.get("chunk_ids", []),
            }
        else:
            _, result = retrieve(state, question, {}, adj_triple=adj_triple, adj_chunk=adj_chunk)
    else:
        hybrid = _hybrid_type_filtered(
            state, question_embed, question, target_node_types
        )
        path2_results = retrieve_path2(
            state.graph, state.faiss, question_embed, adj_triple
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
    """对 Path1 使用类型过滤，返回过滤后的节点、三元组和 chunk 检索结果

    .. note::
        question 参数当前未使用，保留接口一致性。

    Args:
        state (`RetrievalState`): 检索状态
        question_embed (`torch.Tensor`): 查询嵌入
        question (`str`): 用户问题（未使用）
        target_node_types (`list`): 目标节点类型列表

    Returns:
        `Dict`:
            - "path1_results": {
                "top_nodes": [...],
                "one_hop_triples": [...],
                "chunk_results": {...}
              }
            - "chunk_ids": List[str]
    """
    filtered_nodes = filter_nodes_by_schema_type(state.graph, target_node_types)
    path1_results = {}

    # 1) 类型过滤节点检索
    if filtered_nodes:
        node_results = similarity_search_on_filtered(
            state.faiss, question_embed, filtered_nodes, state.top_k_triple
        )
        triple_list = []
        for n in node_results.get("top_nodes", []):
            for _, v, d in state.graph.out_edges(n, data=True):
                triple_list.append((n, d.get("relation", ""), v))
        path1_results = {
            "top_nodes": node_results["top_nodes"],
            "one_hop_triples": triple_list,
        }

    # 2) chunk 直接语义检索
    chunk_fn = _chunk_retrieval_fn(state)
    chunk_results = chunk_fn(question_embed)
    path1_results["chunk_results"] = chunk_results

    # 3) 合并 chunk IDs（节点回溯 + 直接语义召回）
    node_chunk_ids = extract_chunk_ids_from_nodes(
        state.graph, path1_results.get("top_nodes", [])
    )
    direct_chunk_ids = set(chunk_results.get("chunk_ids", []))
    all_chunk_ids = set(node_chunk_ids) | direct_chunk_ids

    return {
        "path1_results": path1_results,
        "chunk_ids": list(all_chunk_ids),
    }


# ─── 完整处理流水线 ───


def process_retrieval_results(
    state: RetrievalState,
    question: str,
    involved_types: dict = None,
    retrieval_type: str = "micro",
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
        involved_types (`dict`, optional):
            {"nodes": [...], "relations": [...], "attributes": [...]}
        retrieval_type (`str`): 检索类型 "micro" | "macro"，决定 top_k 缩放

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

    # 根据 retrieval_type 计算调整后的 top_k
    type_scales = getattr(
        getattr(state.config, "retrieval", None),
        "retrieval_type_scales", {},
    ).get(retrieval_type)
    if type_scales:
        adj_triple = max(1, int(state.top_k_triple * type_scales.path2_scale))
        adj_chunk = max(1, int(state.top_k_chunk * type_scales.chunk_scale))
    else:
        adj_triple = state.top_k_triple
        adj_chunk = state.top_k_chunk

    if involved_types:
        question_embed, results = retrieve_with_type_filter(
            state, question, involved_types, adj_triple=adj_triple, adj_chunk=adj_chunk
        )
    else:
        question_embed, results = retrieve(
            state, question, involved_types, adj_triple=adj_triple, adj_chunk=adj_chunk
        )

    retrieval_time = time.time() - start

    # 处理 chunk 检索结果
    chunk_results = results.get("path1_results", {}).get("chunk_results")
    if chunk_results:
        chunk_retrieval_results = chunk_results
        chunk_retrieval_ids = set(chunk_results.get("chunk_ids", []))
        if not chunk_retrieval_ids:
            logger.debug(f"chunk_retrieval returned empty chunk_ids for question: {question[:50]}")
    else:
        logger.warning(f"chunk_results key missing in path1_results for question: {question[:50]}")
        chunk_retrieval_results = {
            "chunk_ids": [],
            "scores": [],
            "chunk_contents": [],
        }
        chunk_retrieval_ids = set()

    # 三元组评分与合并
    scored_triples = _collect_all_scored(state, results, question_embed)
    limited_scored = scored_triples[:adj_triple]
    formatted_triples = format_scored_triples(state.graph, limited_scored)
    triple_chunk_ids = extract_chunk_ids_from_triples(state.graph, limited_scored)

    # 合并 chunk_id（直接语义召回 + 三元组回溯）
    all_chunk_ids = chunk_retrieval_ids | triple_chunk_ids
    matching_chunks = {}
    for cid in all_chunk_ids:
        if cid in state.chunk2id:
            matching_chunks[cid] = state.chunk2id[cid]

    # 社区摘要
    community_summaries = collect_community_summaries(
        state.graph, limited_scored, chunk2id=state.chunk2id
    )

    # 收集实体名→描述（用于 LLM 上下文的 === Entities ===）
    entity_dict: Dict[str, str] = {}
    triples_data = []
    for h, r, t, _score in limited_scored:
        h_name = h_desc = t_name = t_desc = ""
        h_nd = state.graph.nodes.get(h)
        if h_nd and h_nd.get("label") == "entity":
            hp = h_nd.get("properties", {})
            h_name = hp.get("name", "")
            h_desc = hp.get("description", "") or ""
        t_nd = state.graph.nodes.get(t)
        if t_nd and t_nd.get("label") == "entity":
            tp = t_nd.get("properties", {})
            t_name = tp.get("name", "")
            t_desc = tp.get("description", "") or ""

        # 收集 entity_dict
        for ename, edesc in [(h_name, h_desc), (t_name, t_desc)]:
            if ename and ename not in entity_dict:
                entity_dict[ename] = edesc

        # 收集结构化三元组数据
        if h_name and t_name and r:
            r_desc = ""
            edge_data = state.graph.get_edge_data(h, t)
            if edge_data:
                for attrs in edge_data.values():
                    if attrs.get("relation") == r:
                        r_desc = attrs.get("description", "") or ""
                        break
            triples_data.append({
                "head": {"name": h_name, "description": h_desc},
                "relation": r,
                "relation_description": r_desc,
                "tail": {"name": t_name, "description": t_desc},
            })

    retrieval_results = {
        "triples": formatted_triples,
        "triples_data": triples_data,
        "chunk_ids": list(all_chunk_ids),
        "chunk_contents": matching_chunks,
        "chunk_retrieval_results": chunk_retrieval_results,
        "community_summaries": community_summaries,
        "entities": entity_dict,
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
        top_k=state.top_k_triple,
        graph=state.graph,
    )
