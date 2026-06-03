"""
基于 IRCoT 的知识图谱召回函数。
仅对外暴露 ircot_recall(query, kb_ids) 和 set_active_kb_ids(kb_ids)。
"""

from typing import Optional

from loguru import logger

# ─── 模块级活动上下文 ───
# 由 workflow start 时设置，RAGSearchTool/VerifyFactTool 自动读取
_active_kb_ids: list[str] = []


def set_active_kb_ids(kb_ids: list[str]):
    global _active_kb_ids
    _active_kb_ids = list(kb_ids)


def get_active_kb_ids() -> list[str]:
    return list(_active_kb_ids)


# ─── 核心召回函数 ───


async def ircot_recall(query: str, kb_ids: Optional[list[str]] = None) -> dict:
    """
    IRCoT 知识图谱召回（纯函数，无 SSE/流式）。

    流程:
      1. 读取 kb_ids（参数优先，否则回退 _active_kb_ids）
      2. 查询 DB 获取这些 KB 下所有 has_graph=True 的文件
      3. 逐个文件构建 retrieval state，执行 IRCoT 检索
      4. 跨文件去重合并结果

    Args:
        query: 搜索查询语句
        kb_ids: 知识库 ID 列表（可选，不传则从活动上下文读取）

    Returns:
        {
            "triples": ["(subject, relation, object) [score]", ...],
            "chunk_contents": ["chunk_text", ...],
            "sub_questions": [{"sub-question": "..."}, ...],
            "file_count": int,
            "triple_count": int,
        }
    """
    from chronicle_writer.tools.reference_tool import _db_factory

    kb_ids = kb_ids or get_active_kb_ids()
    if not kb_ids:
        return {
            "triples": [],
            "chunk_contents": [],
            "sub_questions": [],
            "file_count": 0,
            "triple_count": 0,
            "error": "未设置知识库检索范围",
        }

    try:
        from rag.config import get_config
        from rag.graph_manager.db_service import KnowledgeGraphService

        cfg = get_config()
    except ImportError:
        return {
            "triples": [],
            "chunk_contents": [],
            "sub_questions": [],
            "file_count": 0,
            "triple_count": 0,
            "error": "RAG 模块不可用",
        }

    # 1. 查询所有需要搜索的文件
    async with _db_factory() as db:
        from rag.kb_manager.model import KnowledgeBaseFile
        from sqlalchemy import select

        stmt = select(KnowledgeBaseFile).where(
            KnowledgeBaseFile.kb_id.in_(kb_ids),
            KnowledgeBaseFile.has_graph.is_(True),
            KnowledgeBaseFile.is_deleted.is_(False),
        )
        result = await db.execute(stmt)
        files = list(result.scalars().all())

        if not files:
            return {
                "triples": [],
                "chunk_contents": [],
                "sub_questions": [],
                "file_count": 0,
                "triple_count": 0,
                "message": "所选知识库中无已构建图谱的文件",
            }

        # 2. 逐个文件执行 IRCoT 检索（非流式）
        all_triples: set = set()
        all_chunk_contents: dict[str, str] = {}
        all_sub_questions: list = []
        _schema: Optional[dict] = None

        for file in files[:5]:
            graph_record = await KnowledgeGraphService.get_by_file(db, file.id)
            if not graph_record or not graph_record.graph_data:
                continue

            if _schema is None and file.schema_json:
                _schema = file.schema_json

            try:
                result = await _search_single_file(
                    file,
                    graph_record,
                    query,
                    cfg,
                    _schema,
                )
                all_triples.update(result.get("triples", []))
                all_chunk_contents.update(result.get("chunk_contents", {}))
                if result.get("sub_questions"):
                    all_sub_questions = result["sub_questions"]
            except Exception as e:
                logger.warning(f"File {file.id} search failed: {e}")
                continue

        # 3. 格式化返回
        triples_list = list(all_triples)
        triples_list.sort(key=_extract_score, reverse=True)
        triples_list = triples_list[:60]

        return {
            "triples": triples_list,
            "chunk_contents": list(all_chunk_contents.values())[:20],
            "sub_questions": all_sub_questions,
            "file_count": len(files),
            "triple_count": len(triples_list),
        }


async def _search_single_file(
    file,
    graph_record,
    query: str,
    cfg,
    schema: Optional[dict],
) -> dict:
    """对单个文件执行 IRCoT 检索，返回 triples + chunks + sub_questions"""
    from rag.kb_manager.service import _ensure_schema
    from rag.rag_models.retrieval import agentic_decomposer as decomposer
    from rag.rag_models.retrieval.retrieval_core import (
        init_retrieval_state,
        build_retrieval_indices,
        process_retrieval_results,
    )

    import asyncio

    schema_data = _ensure_schema(schema or file.schema_json)
    graphq = decomposer.GraphQ(file.id, config=None, schema_data=schema_data)
    chunks_data = getattr(graph_record, "chunks_data", None)

    state = init_retrieval_state(
        dataset_name=file.id,
        cfg=cfg,
        graph_data=graph_record.graph_data,
        chunks_data=chunks_data,
        top_k=cfg.retrieval.top_k_filter,
        recall_paths=cfg.retrieval.recall_paths,
    )

    # build_retrieval_indices is synchronous (uses SentenceTransformer/FAISS)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: build_retrieval_indices(state))

    # 问题分解
    try:
        decomposition = graphq.decompose(query, "")
        sub_questions = decomposition.get("sub_questions", [])
        involved_types = decomposition.get("involved_types", {})
    except Exception as e:
        logger.warning(f"Decompose failed for {file.id}: {e}")
        sub_questions = [{"sub-question": query}]
        involved_types = {"nodes": [], "relations": [], "attributes": []}

    # 逐子问题检索
    all_triples: set = set()
    all_chunk_contents: dict[str, str] = {}

    for sq in sub_questions:
        sq_text = sq.get("sub-question", query)
        retrieval_results = process_retrieval_results(
            state,
            sq_text,
            top_k=cfg.retrieval.top_k_filter,
            involved_types=involved_types,
        )

        triples = retrieval_results.get("triples", []) or []
        chunk_ids = retrieval_results.get("chunk_ids", []) or []
        chunk_contents = retrieval_results.get("chunk_contents", []) or []

        all_triples.update(triples)

        if isinstance(chunk_contents, dict):
            all_chunk_contents.update(chunk_contents)
        else:
            for i_c, cid in enumerate(chunk_ids):
                if i_c < len(chunk_contents):
                    all_chunk_contents[cid] = chunk_contents[i_c]

    return {
        "triples": list(all_triples),
        "chunk_contents": all_chunk_contents,
        "sub_questions": sub_questions,
    }


def _extract_score(triple_str: str) -> float:
    """从 '(..., ..., ...) [0.95]' 中提取分数"""
    try:
        if "[" in triple_str and triple_str.endswith("]"):
            score_str = triple_str[triple_str.rindex("[") + 1 : -1]
            return float(score_str)
    except (ValueError, IndexError):
        pass
    return 0.0
