import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AsyncSessionLocal
from app.base_schema import PaginatedResponse
from utils.security import get_current_user
from core.user.model import User

from ai_workflow.conversation.model import WorkflowConversation
from ai_workflow.conversation.schema import (
    ConversationCreate,
    ConversationOut,
    TurnRequest,
    TurnOut,
)
from ai_workflow.conversation.service import ConversationService
from ai_workflow.workflow.events import WorkflowEventType
from ai_workflow.workflow.model import WorkflowDef, WorkflowInstance
from ai_workflow.workflow.service import WorkflowEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["AI工作流-会话"])


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _ensure_conv_exists(conv_id: str, db: AsyncSession) -> WorkflowConversation:
    conv = await db.get(WorkflowConversation, conv_id)
    if not conv or conv.is_deleted:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conv


# ─── CRUD ───────────────────────────────────────────────


@router.post("", response_model=ConversationOut, summary="创建会话")
async def create_conversation(
    data: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = await ConversationService.create_conversation(
        workflow_def_id=data.workflow_def_id,
        user_id=user.id,
        db=db,
    )
    return conv


@router.get(
    "",
    response_model=PaginatedResponse[ConversationOut],
    summary="获取会话列表",
)
async def list_conversations(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize", description="每页数量"),
    workflow_def_id: Optional[str] = Query(
        None, alias="defId", description="按工作流过滤"
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(WorkflowConversation).where(
        WorkflowConversation.sys_creator_id == user.id,
        WorkflowConversation.is_deleted == False,  # noqa: E712
    )
    if workflow_def_id:
        query = query.where(WorkflowConversation.workflow_def_id == workflow_def_id)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    items = (
        (
            await db.execute(
                query.order_by(WorkflowConversation.sys_create_datetime.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    # 计算每个会话的 turn_count
    result = []
    for item in items:
        turn_count = (
            await db.execute(
                select(func.count()).where(
                    WorkflowInstance.conversation_id == item.id,
                    WorkflowInstance.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar()
        conv_out = ConversationOut.model_validate(item)
        conv_out.turn_count = turn_count or 0
        result.append(conv_out)

    return PaginatedResponse(items=result, total=total)


@router.get(
    "/{conv_id}",
    summary="获取会话详情（含历史 turn）",
)
async def get_conversation(
    conv_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = await _ensure_conv_exists(conv_id, db)

    turns_result = await db.execute(
        select(WorkflowInstance)
        .where(
            WorkflowInstance.conversation_id == conv_id,
            WorkflowInstance.is_deleted == False,  # noqa: E712
        )
        .order_by(WorkflowInstance.turn_index)
    )
    turns_raw = turns_result.scalars().all()

    turns = []
    for t in turns_raw:
        try:
            inp = json.loads(t.input_params) if t.input_params else {}
        except (json.JSONDecodeError, TypeError):
            inp = {}
        input_message = inp.get("message", "") if isinstance(inp, dict) else ""
        turns.append(
            TurnOut(
                turn_index=t.turn_index or 0,
                input_message=input_message,
                output_result=t.output_result,
                status=t.status,
                started_at=t.started_at,
                finished_at=t.finished_at,
            )
        )

    conv_out = ConversationOut.model_validate(conv)
    conv_out.turn_count = len(turns)
    return {
        **conv_out.model_dump(),
        "turns": [t.model_dump() for t in turns],
    }


@router.delete("/{conv_id}", summary="删除会话")
async def delete_conversation(
    conv_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = await _ensure_conv_exists(conv_id, db)
    conv.is_deleted = True
    await db.commit()
    return {"message": "已删除"}


# ─── 对话执行 ────────────────────────────────────────


@router.post(
    "/{conv_id}/turns",
    summary="发送消息（SSE 流式返回）",
)
async def send_turn(
    conv_id: str,
    req: TurnRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _ensure_conv_exists(conv_id, db)
    queue: asyncio.Queue = asyncio.Queue()

    async def event_generator():
        task: Optional[asyncio.Task] = None
        original_nodes: Optional[str] = None
        instance_id: Optional[str] = None
        wf_def_id: Optional[str] = None
        try:
            async with AsyncSessionLocal() as exec_db:
                instance, original_nodes = await ConversationService.execute_turn(
                    conversation_id=conv_id,
                    message=req.message,
                    db=exec_db,
                    user_id=user.id,
                    stream_queue=queue,
                )
                instance_id = instance.id
                wf_def_id = instance.workflow_def_id

                task = asyncio.create_task(
                    WorkflowEngine.execute_instance(
                        instance.id, exec_db, stream_queue=queue
                    )
                )
                WorkflowEngine.register_running_task(instance.id, task)

                while True:
                    event = await queue.get()
                    yield _sse(event)
                    if event.get("event") in (
                        WorkflowEventType.WORKFLOW_COMPLETE,
                        WorkflowEventType.WORKFLOW_ERROR,
                    ):
                        break
        except asyncio.CancelledError:
            if task and not task.done():
                task.cancel()
        except Exception as e:
            yield _sse(
                {
                    "event": WorkflowEventType.WORKFLOW_ERROR,
                    "data": json.dumps({"error": str(e)}),
                }
            )
        finally:
            if task and not task.done():
                task.cancel()
            WorkflowEngine.cancel_running_task(instance_id or "")
            # 恢复工作流定义的原始节点（移除临时注入的 history）
            if original_nodes is not None and wf_def_id:
                try:
                    async with AsyncSessionLocal() as cleanup_db:
                        wf_def = await cleanup_db.get(WorkflowDef, wf_def_id)
                        if wf_def:
                            wf_def.nodes = original_nodes
                            await cleanup_db.commit()
                except Exception:
                    logger.exception("恢复工作流节点定义失败")
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
