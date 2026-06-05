import asyncio
from collections import defaultdict
from typing import Any, Dict, List, Optional

import networkx as nx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rag.config import get_config
from rag.rag_models.constructor.tree_comm import FastTreeComm
from rag.utils.graph_processor import load_graph_from_json_data


def _filter_community_data(data: List[Dict]) -> List[Dict]:
    return [
        r
        for r in data
        if r["start_node"]["label"] != "community"
        and r["end_node"]["label"] != "community"
    ]


def _merge_graphs(
    old_graph: nx.MultiDiGraph, new_graph: nx.MultiDiGraph
) -> nx.MultiDiGraph:
    merged = nx.MultiDiGraph()
    seen: set = set()

    for g in [old_graph, new_graph]:
        for n, attrs in g.nodes(data=True):
            key = (attrs["label"], attrs["properties"]["name"])
            if key not in seen:
                seen.add(key)
                merged.add_node(n, **attrs)

    for g in [old_graph, new_graph]:
        for u, v, attrs in g.edges(data=True):
            merged.add_edge(u, v, **attrs)

    return merged


def _format_graph_output(graph: nx.MultiDiGraph) -> List[Dict]:
    output = []
    for u, v, data in graph.edges(data=True):
        relationship = {
            "start_node": {
                "label": graph.nodes[u]["label"],
                "properties": graph.nodes[u]["properties"],
            },
            "relation": data.get("relation", "related_to"),
            "end_node": {
                "label": graph.nodes[v]["label"],
                "properties": graph.nodes[v]["properties"],
            },
        }
        output.append(relationship)
    return output


def merge_graphs_service(
    old_graph_data: List[Dict],
    new_graph_data: List[Dict],
    struct_weight: float = 0.3,
    max_total_communities: Optional[int] = None,
    chunks_data: Optional[Dict[str, Any]] = None,
) -> Dict:
    old_filtered = _filter_community_data(old_graph_data)
    new_filtered = _filter_community_data(new_graph_data)

    old_graph = load_graph_from_json_data(old_filtered)
    new_graph = load_graph_from_json_data(new_filtered)

    merged_graph = _merge_graphs(old_graph, new_graph)

    logger.info(
        f"Merged graph: {merged_graph.number_of_nodes()} nodes, "
        f"{merged_graph.number_of_edges()} edges"
    )

    config = get_config()
    tc = FastTreeComm(
        merged_graph,
        struct_weight=struct_weight,
        config=config,
        chunks_data=chunks_data,
    )

    level2_nodes = [n for n, d in merged_graph.nodes(data=True) if d.get("level") == 2]

    if max_total_communities is not None:
        config.tree_comm.max_total_communities = max_total_communities

    comm_to_nodes = tc.detect_communities(level2_nodes)
    tc.create_super_nodes_with_keywords(comm_to_nodes, level=4)

    merged_output = _format_graph_output(merged_graph)

    return {
        "merged_graph_data": merged_output,
        "community_count": len(comm_to_nodes),
        "total_nodes": merged_graph.number_of_nodes(),
        "total_edges": merged_graph.number_of_edges(),
    }


async def _get_or_create_virtual_file(kb_id: str, db: AsyncSession, kb_name: str = ""):
    """Find existing merged virtual file or create one."""
    from rag.kb_manager.model import KnowledgeBaseFile

    query = select(KnowledgeBaseFile).where(
        KnowledgeBaseFile.kb_id == kb_id,
        KnowledgeBaseFile.file_type == "merged",
        KnowledgeBaseFile.is_deleted == False,
    )
    result = await db.execute(query)
    virtual = result.scalar_one_or_none()
    if virtual:
        return virtual

    from app.base_model import generate_nanoid

    virtual = KnowledgeBaseFile(
        id=generate_nanoid(),
        kb_id=kb_id,
        filename="全部图谱（已合并）",
        content="",
        file_type="merged",
        file_size=0,
        has_graph=True,
    )
    db.add(virtual)
    await db.flush()
    await db.refresh(virtual)
    logger.info(f"Created virtual merged file {virtual.id} for KB {kb_id}")
    return virtual


_kb_merge_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def merge_kb_graphs_service(kb_id: str, db: AsyncSession) -> Dict:
    async with _kb_merge_locks[kb_id]:
        return await _merge_kb_graphs_service_impl(kb_id, db)


async def _merge_kb_graphs_service_impl(kb_id: str, db: AsyncSession) -> Dict:
    from rag.kb_manager.db_service import KnowledgeBaseFileService
    from rag.graph_manager.db_service import KnowledgeGraphService
    from rag.graph_manager.model import KnowledgeGraph as KGraphModel
    from rag.kb_manager.model import KnowledgeBase

    files = await KnowledgeBaseFileService.get_files_by_kb(db, kb_id)
    files_with_graph = [
        f
        for f in files
        if getattr(f, "has_graph", False) and getattr(f, "file_type", "") != "merged"
    ]

    if not files_with_graph:
        raise ValueError("知识库中没有已构建图谱的文件（不含已合并的虚拟文件）")

    kb_result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = kb_result.scalar_one_or_none()
    virtual = await _get_or_create_virtual_file(kb_id, db, kb.name if kb else "")

    # ── 只有一个文件时直接复制图谱数据，跳过昂贵的合并+社区检测 ──
    if len(files_with_graph) == 1:
        single = files_with_graph[0]
        kg = await KnowledgeGraphService.get_by_file(db, single.id)
        if not kg:
            raise ValueError(f"文件 {single.id} 的图谱数据不存在")

        merged_graph_data = kg.graph_data if isinstance(kg.graph_data, list) else (
            list(kg.graph_data) if kg.graph_data else []
        )
        merged_chunks = kg.chunks_data or {}

        graph = load_graph_from_json_data(merged_graph_data) if merged_graph_data else nx.MultiDiGraph()
        community_count = sum(
            1 for _, d in graph.nodes(data=True) if d.get("label") == "community"
        )

        existing_kg = await KnowledgeGraphService.get_by_file(db, virtual.id)
        if existing_kg:
            existing_kg.graph_data = merged_graph_data
            existing_kg.chunks_data = merged_chunks
        else:
            from app.base_model import generate_nanoid

            kg_record = KGraphModel(
                id=generate_nanoid(),
                file_id=virtual.id,
                graph_data=merged_graph_data,
                chunks_data=merged_chunks,
            )
            db.add(kg_record)
            await db.flush()
            await db.refresh(kg_record)

        virtual.has_graph = True
        await db.flush()

        logger.info(
            f"KB {kb_id} single-file graph copied to virtual file {virtual.id}: "
            f"{graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges, "
            f"{community_count} communities"
        )

        return {
            "virtual_file_id": virtual.id,
            "community_count": community_count,
            "total_nodes": graph.number_of_nodes(),
            "total_edges": graph.number_of_edges(),
            "file_count": 1,
        }

    # ── 多个文件走完整合并 ──
    all_graph_data: List[Dict] = []
    all_chunks: Dict[str, Any] = {}
    for f in files_with_graph:
        kg = await KnowledgeGraphService.get_by_file(db, f.id)
        if kg:
            if kg.graph_data:
                if isinstance(kg.graph_data, list):
                    all_graph_data.extend(kg.graph_data)
                else:
                    all_graph_data.append(kg.graph_data)
            if kg.chunks_data:
                all_chunks.update(kg.chunks_data)

    result = merge_graphs_service(
        old_graph_data=[],
        new_graph_data=all_graph_data,
        struct_weight=0.3,
        chunks_data=all_chunks,
    )

    merged_graph_data = result["merged_graph_data"]

    existing_kg = await KnowledgeGraphService.get_by_file(db, virtual.id)
    if existing_kg:
        existing_kg.graph_data = merged_graph_data
        existing_kg.chunks_data = all_chunks
    else:
        from app.base_model import generate_nanoid

        kg_record = KGraphModel(
            id=generate_nanoid(),
            file_id=virtual.id,
            graph_data=merged_graph_data,
            chunks_data=all_chunks,
        )
        db.add(kg_record)
        await db.flush()
        await db.refresh(kg_record)

    virtual.has_graph = True
    await db.flush()

    logger.info(
        f"KB {kb_id} merged graph saved to virtual file {virtual.id}: "
        f"{result['total_nodes']} nodes, {result['total_edges']} edges, "
        f"{result['community_count']} communities, {len(files_with_graph)} files"
    )

    return {
        "virtual_file_id": virtual.id,
        "community_count": result["community_count"],
        "total_nodes": result["total_nodes"],
        "total_edges": result["total_edges"],
        "file_count": len(files_with_graph),
    }


async def get_kb_merged_visualization_service(kb_id: str, db: AsyncSession) -> Dict:
    from rag.graph_manager.db_service import KnowledgeGraphService
    from rag.graph_manager.service import prepare_graph_visualization_from_data

    virtual = await _get_or_create_virtual_file(kb_id, db)
    kg = await KnowledgeGraphService.get_by_file(db, virtual.id)
    if not kg or not kg.graph_data:
        raise ValueError("合并图谱不存在，请先合并")

    vis_data = await prepare_graph_visualization_from_data(kg.graph_data)
    return vis_data


async def get_merged_graph_status_service(kb_id: str, db: AsyncSession) -> Dict:
    from rag.graph_manager.db_service import KnowledgeGraphService

    virtual = await _get_or_create_virtual_file(kb_id, db)
    kg = await KnowledgeGraphService.get_by_file(db, virtual.id)
    if not kg or not kg.graph_data:
        return {"exists": False, "file_count": 0, "virtual_file_id": virtual.id}

    graph = load_graph_from_json_data(kg.graph_data)
    return {
        "exists": True,
        "file_count": len([f async for f in _get_real_files_with_graph(kb_id, db)]),
        "total_nodes": graph.number_of_nodes(),
        "total_edges": graph.number_of_edges(),
        "virtual_file_id": virtual.id,
        "built_at": kg.built_at.isoformat() if kg.built_at else None,
    }


async def _get_real_files_with_graph(kb_id: str, db: AsyncSession) -> list:
    from rag.kb_manager.db_service import KnowledgeBaseFileService

    files = await KnowledgeBaseFileService.get_files_by_kb(db, kb_id)
    return [
        f
        for f in files
        if getattr(f, "has_graph", False) and getattr(f, "file_type", "") != "merged"
    ]


async def incremental_update_file_service(
    kb_id: str, file_id: str, additional_text: str, db: AsyncSession
) -> Dict:
    from rag.kb_manager.db_service import KnowledgeBaseFileService
    from rag.graph_manager.db_service import KnowledgeGraphService
    from rag.graph_manager.service import get_config_instance, GRAPHRAG_AVAILABLE
    from rag.graph_manager.model import KnowledgeGraph as KGraphModel

    if not GRAPHRAG_AVAILABLE:
        raise ValueError("GraphRAG components not available.")

    file_record = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not file_record:
        raise ValueError("文件不存在")

    existing_kg = await KnowledgeGraphService.get_by_file(db, file_id)

    # 构建新文本的图谱
    cfg = get_config_instance()
    from rag.rag_models.constructor import kt_gen as constructor
    from rag.kb_manager.service import _ensure_schema

    schema = _ensure_schema(file_record.schema_json)
    builder = constructor.KTBuilder(
        file_id,
        None,
        mode=cfg.construction.mode,
        config=cfg,
        schema_data=schema,
    )

    def build_sync():
        return builder.build_knowledge_graph(
            documents=[{"title": file_record.filename, "text": additional_text}]
        )

    import asyncio

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, build_sync)

    new_graph_data = (
        builder.format_output() if hasattr(builder, "format_output") else []
    )
    new_chunks = dict(getattr(builder, "all_chunks", {})) or {}

    # 合并 chunks（先合并，用于社区摘要增强）
    merged_chunks: Dict[str, Any] = (
        dict(existing_kg.chunks_data) if existing_kg and existing_kg.chunks_data else {}
    )
    merged_chunks.update(new_chunks)

    # 合并图谱
    result = merge_graphs_service(
        old_graph_data=existing_kg.graph_data if existing_kg else [],
        new_graph_data=new_graph_data,
        chunks_data=merged_chunks,
    )

    # 追加文件内容
    file_record.content = (file_record.content or "") + "\n" + additional_text

    # 更新 KnowledgeGraph
    if existing_kg:
        existing_kg.graph_data = result["merged_graph_data"]
        existing_kg.chunks_data = merged_chunks
    else:
        from app.base_model import generate_nanoid

        kg = KGraphModel(
            id=generate_nanoid(),
            file_id=file_id,
            graph_data=result["merged_graph_data"],
            chunks_data=merged_chunks,
        )
        db.add(kg)

    # agent 模式下，将发现的 schema 新类型持久化到 DB
    if getattr(builder, "schema_updated", False):
        from rag.rag_models.constructor.db_service import update_file_schema

        await update_file_schema(db, file_id, builder.schema)

    file_record.has_graph = True
    await db.flush()

    # 自动触发 KB 级合并
    try:
        await merge_kb_graphs_service(kb_id, db)
    except Exception as e:
        logger.warning(f"KB auto-merge after incremental update failed: {e}")

    await db.commit()

    logger.info(
        f"Incremental update file {file_id}: "
        f"{result['total_nodes']} nodes, {result['total_edges']} edges, "
        f"{result['community_count']} communities"
    )

    return {
        "community_count": result["community_count"],
        "total_nodes": result["total_nodes"],
        "total_edges": result["total_edges"],
    }
