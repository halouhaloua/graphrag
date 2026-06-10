import asyncio
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AsyncSessionLocal
from app.base_schema import PaginatedResponse
from utils.security import get_current_user
from core.user.model import User

from ai_workflow.workflow.events import WorkflowEventType
from ai_workflow.workflow.model import WorkflowDef, WorkflowInstance, WorkflowNodeLog
from ai_workflow.workflow.schema import (
    WorkflowDefCreate,
    WorkflowDefUpdate,
    WorkflowDefOut,
    WorkflowInstanceOut,
    WorkflowNodeLogOut,
    WorkflowRunRequest,
)
from ai_workflow.workflow.service import WorkflowEngine
from ai_workflow.nodes.registry import NodeRegistry

router = APIRouter(tags=["AI工作流"])


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _serialize_nodes(nodes: list) -> str:
    return json.dumps(
        [n.model_dump() if hasattr(n, "model_dump") else n for n in nodes],
        ensure_ascii=False,
    )


def _serialize_edges(edges: list) -> str:
    return json.dumps(
        [e.model_dump() if hasattr(e, "model_dump") else e for e in edges],
        ensure_ascii=False,
    )


async def _ensure_def_exists(def_id: str, db: AsyncSession) -> WorkflowDef:
    wf_def = await db.get(WorkflowDef, def_id)
    if not wf_def or wf_def.is_deleted:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return wf_def


async def _ensure_instance_exists(inst_id: str, db: AsyncSession) -> WorkflowInstance:
    inst = await db.get(WorkflowInstance, inst_id)
    if not inst or inst.is_deleted:
        raise HTTPException(status_code=404, detail="实例不存在")
    return inst


# ─── 工作流定义 CRUD ───────────────────────────────


@router.post("/defs", response_model=WorkflowDefOut, summary="创建工作流定义")
async def create_workflow_def(
    data: WorkflowDefCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    nodes_raw = _serialize_nodes(data.nodes)
    edges_raw = _serialize_edges(data.edges)
    nodes_parsed = [n.model_dump() for n in data.nodes]

    ok, err, _ = WorkflowEngine.validate_dag(
        nodes_parsed, [e.model_dump() for e in data.edges]
    )
    if not ok:
        raise HTTPException(status_code=400, detail=f"工作流无效: {err}")

    wf_def = WorkflowDef(
        name=data.name,
        description=data.description,
        nodes=nodes_raw,
        edges=edges_raw,
        global_params=json.dumps(data.global_params, ensure_ascii=False)
        if data.global_params
        else None,
        sys_creator_id=user.id,
    )
    db.add(wf_def)
    await db.commit()
    await db.refresh(wf_def)
    return wf_def


@router.get(
    "/defs",
    response_model=PaginatedResponse[WorkflowDefOut],
    summary="获取工作流定义列表",
)
async def list_workflow_defs(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(
        default=20, ge=1, le=100, alias="pageSize", description="每页数量"
    ),
    name: Optional[str] = Query(None, description="名称模糊搜索"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = select(WorkflowDef).where(not WorkflowDef.is_deleted)
    if name:
        query = query.where(WorkflowDef.name.ilike(f"%{name}%"))

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    items = (
        (
            await db.execute(
                query.order_by(WorkflowDef.sys_create_datetime.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    return PaginatedResponse(items=list(items), total=total)


@router.get(
    "/defs/{def_id}", response_model=WorkflowDefOut, summary="获取工作流定义详情"
)
async def get_workflow_def(
    def_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await _ensure_def_exists(def_id, db)


@router.put("/defs/{def_id}", response_model=WorkflowDefOut, summary="更新工作流定义")
async def update_workflow_def(
    def_id: str,
    data: WorkflowDefUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    wf_def = await _ensure_def_exists(def_id, db)

    update_data = data.model_dump(exclude_unset=True)

    if "nodes" in update_data:
        nodes_list = update_data["nodes"]
        update_data["nodes"] = _serialize_nodes(nodes_list)
    if "edges" in update_data:
        edges_list = update_data["edges"]
        update_data["edges"] = _serialize_edges(edges_list)
    if "global_params" in update_data:
        val = update_data["global_params"]
        update_data["global_params"] = (
            json.dumps(val, ensure_ascii=False) if val else None
        )

    for key, value in update_data.items():
        setattr(wf_def, key, value)

    await db.commit()
    await db.refresh(wf_def)
    return wf_def


@router.delete("/defs/{def_id}", summary="删除工作流定义")
async def delete_workflow_def(
    def_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    wf_def = await _ensure_def_exists(def_id, db)
    wf_def.is_deleted = True
    await db.commit()
    return {"message": "已删除"}


@router.post("/defs/{def_id}/publish", summary="发布/取消发布工作流定义")
async def publish_workflow_def(
    def_id: str,
    publish: bool = Query(True, description="是否发布"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    wf_def = await _ensure_def_exists(def_id, db)

    if publish:
        nodes = json.loads(wf_def.nodes)
        edges = json.loads(wf_def.edges) if wf_def.edges else []
        ok, err, _ = WorkflowEngine.validate_dag(nodes, edges)
        if not ok:
            raise HTTPException(status_code=400, detail=f"工作流无效，无法发布: {err}")

    wf_def.is_published = publish
    await db.commit()
    return {"message": "已发布" if publish else "已取消发布", "is_published": publish}


# ─── 工作流执行 ────────────────────────────────────


@router.post(
    "/defs/{def_id}/run",
    response_model=WorkflowInstanceOut,
    summary="执行工作流（异步）",
)
async def run_workflow(
    def_id: str,
    req: WorkflowRunRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wf_def = await _ensure_def_exists(def_id, db)
    if not wf_def.is_published:
        raise HTTPException(status_code=400, detail="工作流未发布，请先发布")

    instance = await WorkflowEngine.create_instance(
        def_id=def_id,
        input_params=req.input_params,
        user_id=user.id,
        db=db,
    )

    async def _bg():
        async with AsyncSessionLocal() as exec_db:
            await WorkflowEngine.execute_instance(instance.id, exec_db)

    asyncio.create_task(_bg())
    return instance


@router.get(
    "/instances",
    response_model=PaginatedResponse[WorkflowInstanceOut],
    summary="获取工作流实例列表",
)
async def list_instances(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(
        default=20, ge=1, le=100, alias="pageSize", description="每页数量"
    ),
    status: Optional[str] = Query(None, description="按状态过滤"),
    def_id: Optional[str] = Query(None, alias="defId", description="按工作流定义过滤"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = (
        select(WorkflowInstance)
        .where(WorkflowInstance.sys_creator_id == user.id)
        .where(not WorkflowInstance.is_deleted)
    )
    if status:
        query = query.where(WorkflowInstance.status == status)
    if def_id:
        query = query.where(WorkflowInstance.workflow_def_id == def_id)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    items = (
        (
            await db.execute(
                query.order_by(WorkflowInstance.sys_create_datetime.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    return PaginatedResponse(items=list(items), total=total)


@router.get(
    "/instances/{inst_id}",
    response_model=WorkflowInstanceOut,
    summary="获取工作流实例详情",
)
async def get_instance(
    inst_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await _ensure_instance_exists(inst_id, db)


@router.get(
    "/instances/{inst_id}/logs",
    response_model=list[WorkflowNodeLogOut],
    summary="获取实例的节点执行日志",
)
async def get_instance_logs(
    inst_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    await _ensure_instance_exists(inst_id, db)
    logs = (
        (
            await db.execute(
                select(WorkflowNodeLog)
                .where(WorkflowNodeLog.instance_id == inst_id)
                .order_by(WorkflowNodeLog.started_at)
            )
        )
        .scalars()
        .all()
    )
    return list(logs)


@router.get(
    "/instances/{inst_id}/stream",
    summary="SSE 流式执行工作流",
)
async def stream_instance(
    inst_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    inst = await _ensure_instance_exists(inst_id, db)
    if inst.sys_creator_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问此实例")

    queue: asyncio.Queue = asyncio.Queue()

    async def event_generator():
        async with AsyncSessionLocal() as exec_db:
            task = asyncio.create_task(
                WorkflowEngine.execute_instance(inst_id, exec_db, stream_queue=queue)
            )
            try:
                while True:
                    event = await queue.get()
                    yield _sse(event)
                    if event.get("event") in (
                        WorkflowEventType.WORKFLOW_COMPLETE,
                        WorkflowEventType.WORKFLOW_ERROR,
                    ):
                        break
            except asyncio.CancelledError:
                task.cancel()
            except Exception as e:
                yield _sse({"event": "error", "data": str(e)})
            finally:
                if not task.done():
                    task.cancel()
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/instances/{inst_id}/cancel", summary="取消工作流执行")
async def cancel_instance(
    inst_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    inst = await _ensure_instance_exists(inst_id, db)
    if inst.sys_creator_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作此实例")
    if inst.status not in ("pending", "running"):
        raise HTTPException(
            status_code=400,
            detail=f"实例状态为 {inst.status}，无法取消",
        )
    inst.status = "cancelled"
    inst.finished_at = datetime.now()
    await db.commit()
    return {"message": "已取消", "status": "cancelled"}


# ─── 节点类型 ──────────────────────────────────────


@router.get("/nodes", summary="获取已注册的节点类型列表")
async def list_node_types(
    _user: User = Depends(get_current_user),
):
    return NodeRegistry.get_all_metadata()
