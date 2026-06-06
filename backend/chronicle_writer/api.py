import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from loguru import logger

from app.database import get_db
from utils.security import get_current_user
from core.user.model import User

from chronicle_writer.schema import (
    ChronicleChatRequest,
    ProjectDetail,
    SectionNode,
    SectionListResponse,
    ReviewItem,
    ReviewListResponse,
    LogEntry,
    LogListResponse,
)
from chronicle_writer.service import ChronicleChatService

router = APIRouter(tags=["志书写作"])


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ─── 辅助函数 ───


async def _ensure_project_exists(project_id: str, db: AsyncSession) -> None:
    """检查项目是否存在且未被删除，不存在则抛出 404。"""
    from chronicle_writer.model import ChronicleProject

    stmt = select(ChronicleProject).where(
        ChronicleProject.id == project_id,
        ChronicleProject.is_deleted.is_(False),
    )
    proj = (await db.execute(stmt)).scalar_one_or_none()
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")


def _build_section_tree(sections: list) -> list[SectionNode]:
    """从扁平的 ChronicleSection 列表构建树形结构。"""
    nodes: dict[str, SectionNode] = {}
    for s in sections:
        nodes[s.id] = SectionNode(
            id=s.id,
            title=s.title,
            level=s.level,
            sort_order=s.sort_order,
            content=s.content or "",
            word_count=s.word_count or 0,
            status=s.status,
            children=[],
        )
    roots: list[SectionNode] = []
    for s in sections:
        node = nodes[s.id]
        if s.parent_id and s.parent_id in nodes:
            nodes[s.parent_id].children.append(node)
        else:
            roots.append(node)

    def _sort_subtree(items: list[SectionNode]) -> None:
        items.sort(key=lambda n: (n.level, n.sort_order))
        for n in items:
            _sort_subtree(n.children)

    _sort_subtree(roots)
    return roots


# ─── 流式聊天 ───


@router.post("/chat", summary="志书写作对话（SSE流式）")
async def chronicle_chat(
    req: ChronicleChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    service = ChronicleChatService()

    async def event_stream():
        try:
            async for event in service.chat(req, user.id, db):
                yield _sse(event)
                if event.get("type") in ("done", "error"):
                    break
        except Exception as e:
            logger.error(f"chat failed: {e}")
            yield _sse({"type": "error", "message": str(e)})
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ─── 项目详情 ───


@router.get(
    "/project/{project_id}",
    response_model=ProjectDetail,
    summary="获取项目详情（含章节树、审查摘要、报告）",
)
async def get_project_detail(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from chronicle_writer.model import (
        ChronicleProject,
        ChronicleSection,
        ChronicleReview,
    )

    # 查项目
    stmt = select(ChronicleProject).where(
        ChronicleProject.id == project_id,
        ChronicleProject.is_deleted.is_(False),
    )
    proj = (await db.execute(stmt)).scalar_one_or_none()
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    # 查章节
    sec_stmt = (
        select(ChronicleSection)
        .where(
            ChronicleSection.project_id == project_id,
            ChronicleSection.is_deleted.is_(False),
        )
        .order_by(ChronicleSection.sort_order)
    )
    sections = (await db.execute(sec_stmt)).scalars().all()
    tree = _build_section_tree(sections)

    # 查审查摘要
    rev_stmt = (
        select(
            ChronicleReview.severity,
            func.count(ChronicleReview.id).label("count"),
        )
        .where(
            ChronicleReview.project_id == project_id,
            ChronicleReview.is_deleted.is_(False),
        )
        .group_by(ChronicleReview.severity)
    )
    rows = (await db.execute(rev_stmt)).all()
    review_summary = {row.severity: row.count for row in rows}

    return ProjectDetail(
        id=proj.id,
        title=proj.title,
        chronicle_type=proj.chronicle_type,
        region_name=proj.region_name,
        scope_description=proj.scope_description,
        status=proj.status,
        word_count=proj.word_count or 0,
        report=proj.report,
        conversation_id=proj.conversation_id,
        sections=tree,
        review_summary=review_summary,
        created_at=proj.sys_create_datetime.isoformat(),
    )


@router.get(
    "/project/{project_id}/sections",
    response_model=SectionListResponse,
    summary="获取项目章节树",
)
async def get_project_sections(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _ensure_project_exists(project_id, db)

    from chronicle_writer.model import ChronicleSection

    stmt = (
        select(ChronicleSection)
        .where(
            ChronicleSection.project_id == project_id,
            ChronicleSection.is_deleted.is_(False),
        )
        .order_by(ChronicleSection.sort_order)
    )
    sections = (await db.execute(stmt)).scalars().all()
    tree = _build_section_tree(sections)
    return SectionListResponse(items=tree, total=len(tree))


@router.get(
    "/project/{project_id}/reviews",
    response_model=ReviewListResponse,
    summary="获取项目审查记录",
)
async def get_project_reviews(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _ensure_project_exists(project_id, db)

    from chronicle_writer.model import ChronicleReview

    stmt = (
        select(ChronicleReview)
        .where(
            ChronicleReview.project_id == project_id,
            ChronicleReview.is_deleted.is_(False),
        )
        .order_by(ChronicleReview.sys_create_datetime)
    )
    items = (await db.execute(stmt)).scalars().all()
    return ReviewListResponse(
        items=[
            ReviewItem(
                id=r.id,
                section_id=r.section_id,
                review_type=r.review_type,
                severity=r.severity,
                issue=r.issue,
                suggestion=r.suggestion,
                resolved=r.resolved,
            )
            for r in items
        ],
        total=len(items),
    )


@router.get(
    "/project/{project_id}/log",
    response_model=LogListResponse,
    summary="获取项目工作流日志",
)
async def get_project_log(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _ensure_project_exists(project_id, db)

    from chronicle_writer.model import ChronicleWorkflowLog

    stmt = (
        select(ChronicleWorkflowLog)
        .where(
            ChronicleWorkflowLog.project_id == project_id,
            ChronicleWorkflowLog.is_deleted.is_(False),
        )
        .order_by(ChronicleWorkflowLog.sys_create_datetime)
    )
    items = (await db.execute(stmt)).scalars().all()
    return LogListResponse(
        items=[
            LogEntry(
                stage=log.stage,
                event_type=log.event_type,
                message=log.message,
                created_at=log.sys_create_datetime.isoformat(),
            )
            for log in items
        ],
        total=len(items),
    )
