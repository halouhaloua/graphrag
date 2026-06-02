from urllib.parse import parse_qs

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

from rag.graph_manager.schema import (
    ConstructGraphResponse,
    QuestionRequest,
    GraphCategoryUpdate,
    GraphNodesCreate,
    GraphEdgesCreate,
    GraphEdgeDeleteRequest,
    GraphEdgeUpdateRequest,
)
from rag.graph_manager.service import (
    GRAPHRAG_AVAILABLE,
    construct_file_graph_service,
    ask_file_question_stream,
    get_file_graph_service,
    update_node_category_service,
    add_graph_edges_service,
    add_graph_nodes_service,
    delete_graph_node_service,
    delete_graph_edge_service,
    update_graph_edge_service,
    get_file_graph_nodes_service,
    get_file_graph_edges_service,
)
from rag.graph_manager.db_service import KnowledgeGraphService
from rag.graph_manager.socket_manager import manager
from rag.kb_manager.db_service import KnowledgeBaseFileService
from rag.kb_manager.service import KnowledgeBasePermissionService
from utils.security import verify_access_token, get_current_user
from core.user.model import User

router = APIRouter(prefix="/api", tags=["知识图谱管理"])
ws_router = APIRouter(prefix="/api", tags=["知识图谱WebSocket"])


# ──────────────────────────────────────────────
# WebSocket (token auth from query string)
# ──────────────────────────────────────────────
@ws_router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    query_string = websocket.scope.get('query_string', b'').decode('utf-8')
    token = None
    if query_string:
        query_params = parse_qs(query_string)
        token_list = query_params.get('token', [])
        if token_list:
            token = token_list[0]

    if not token or not verify_access_token(token):
        await websocket.accept()
        await websocket.close(code=4001)
        return

    await manager.connect(websocket, client_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(client_id)


@router.get("/status")
async def get_status():
    return {
        "message": "GraphRAG Unified Interface is running!",
        "status": "ok",
        "graphrag_available": GRAPHRAG_AVAILABLE,
    }


# ──────────────────────────────────────────────
# Status
# ──────────────────────────────────────────────
@router.get("/knowledge-base/{kb_id}/files/{file_id}/status", summary="文件状态")
async def get_file_status(
    kb_id: str, file_id: str, db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    return {"has_graph": f.has_graph, "id": f.id, "kb_id": f.kb_id}


# ──────────────────────────────────────────────
# Graph Construction / Reconstruction
# ──────────────────────────────────────────────
@router.post(
    "/knowledge-base/{kb_id}/files/{file_id}/construct-graph",
    summary="构建文件图谱",
)
async def construct_file_graph(
    kb_id: str,
    file_id: str,
    client_id: str = Query("default"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not GRAPHRAG_AVAILABLE:
        raise HTTPException(status_code=503, detail="GraphRAG components not available.")

    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        graph_vis_data = await construct_file_graph_service(file_id, client_id, db)
        return ConstructGraphResponse(
            success=True, message="图谱构建成功", graph_data=graph_vis_data
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/knowledge-base/{kb_id}/files/{file_id}/reconstruct",
    summary="重建文件图谱",
)
async def reconstruct_file_graph(
    kb_id: str,
    file_id: str,
    client_id: str = Query("default"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not GRAPHRAG_AVAILABLE:
        raise HTTPException(status_code=503, detail="GraphRAG components not available.")

    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")

    await KnowledgeGraphService.delete_by_file(db, file_id)
    await KnowledgeBaseFileService.update_file_graph_status(db, file_id, False)

    try:
        graph_vis_data = await construct_file_graph_service(file_id, client_id, db)
        return ConstructGraphResponse(
            success=True, message="图谱重建成功", graph_data=graph_vis_data
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────
# Graph Query
# ──────────────────────────────────────────────
@router.get(
    "/knowledge-base/{kb_id}/files/{file_id}/graph",
    summary="获取图谱可视化数据",
)
async def get_file_graph(
    kb_id: str,
    file_id: str,
    max_nodes: int = Query(500, alias="maxNodes", le=10000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not f.has_graph:
        raise HTTPException(status_code=400, detail="该文件尚未构建图谱")
    return await get_file_graph_service(file_id, db, max_nodes=max_nodes)


@router.get(
    "/knowledge-base/{kb_id}/files/{file_id}/graph/nodes",
    summary="分页获取节点列表",
)
async def get_file_graph_nodes(
    kb_id: str,
    file_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500, alias="pageSize"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not f.has_graph:
        raise HTTPException(status_code=400, detail="该文件尚未构建图谱")
    return await get_file_graph_nodes_service(file_id, page, page_size, db)


@router.get(
    "/knowledge-base/{kb_id}/files/{file_id}/graph/edges",
    summary="分页获取边列表",
)
async def get_file_graph_edges(
    kb_id: str,
    file_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500, alias="pageSize"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not f.has_graph:
        raise HTTPException(status_code=400, detail="该文件尚未构建图谱")
    return await get_file_graph_edges_service(file_id, page, page_size, db)


# ──────────────────────────────────────────────
# Triple Management
# ──────────────────────────────────────────────
@router.put(
    "/knowledge-base/{kb_id}/files/{file_id}/graph/node/category",
    summary="修改节点类别",
)
async def update_graph_node_category(
    kb_id: str,
    file_id: str,
    data: GraphCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not f.has_graph:
        raise HTTPException(status_code=400, detail="该文件尚未构建图谱")
    try:
        return await update_node_category_service(file_id, data.node_name, data.new_category, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/knowledge-base/{kb_id}/files/{file_id}/graph/edges",
    summary="批量添加边",
)
async def add_graph_edges(
    kb_id: str,
    file_id: str,
    data: GraphEdgesCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not f.has_graph:
        raise HTTPException(status_code=400, detail="该文件尚未构建图谱")
    try:
        return await add_graph_edges_service(file_id, [e.model_dump() for e in data.edges], db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/knowledge-base/{kb_id}/files/{file_id}/graph/nodes",
    summary="批量添加节点",
)
async def add_graph_nodes(
    kb_id: str,
    file_id: str,
    data: GraphNodesCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not f.has_graph:
        raise HTTPException(status_code=400, detail="该文件尚未构建图谱")
    try:
        return await add_graph_nodes_service(file_id, [n.model_dump() for n in data.nodes], db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/knowledge-base/{kb_id}/files/{file_id}/graph/nodes/{node_name}",
    summary="删除节点（连带所有关联边）",
)
async def delete_graph_node(
    kb_id: str,
    file_id: str,
    node_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not f.has_graph:
        raise HTTPException(status_code=400, detail="该文件尚未构建图谱")
    try:
        return await delete_graph_node_service(file_id, node_name, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/knowledge-base/{kb_id}/files/{file_id}/graph/edge",
    summary="删除单条边",
)
async def delete_graph_edge(
    kb_id: str,
    file_id: str,
    data: GraphEdgeDeleteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not f.has_graph:
        raise HTTPException(status_code=400, detail="该文件尚未构建图谱")
    try:
        return await delete_graph_edge_service(file_id, data.source, data.relation, data.target, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/knowledge-base/{kb_id}/files/{file_id}/graph/edge",
    summary="编辑单条边",
)
async def update_graph_edge(
    kb_id: str,
    file_id: str,
    data: GraphEdgeUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not f.has_graph:
        raise HTTPException(status_code=400, detail="该文件尚未构建图谱")
    try:
        return await update_graph_edge_service(
            file_id,
            data.source, data.relation, data.target,
            new_source=data.new_source,
            new_relation=data.new_relation,
            new_target=data.new_target,
            new_source_category=data.new_source_category,
            new_target_category=data.new_target_category,
            db=db,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────
# Question Answering
# ──────────────────────────────────────────────
@router.post(
    "/knowledge-base/{kb_id}/files/{file_id}/ask-question",
    summary="针对文件提问（SSE流式）",
)
async def ask_file_question(
    kb_id: str,
    file_id: str,
    request: QuestionRequest,
    client_id: str = Query("default"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not GRAPHRAG_AVAILABLE:
        raise HTTPException(status_code=503, detail="GraphRAG components not available.")

    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not f.has_graph:
        raise HTTPException(status_code=400, detail="该文件尚未构建图谱，请先构建")

    return StreamingResponse(
        ask_file_question_stream(file_id, request.question, client_id, db),
        media_type="text/event-stream",
    )
