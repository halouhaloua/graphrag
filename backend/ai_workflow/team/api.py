import asyncio
import json
import logging
from typing import Optional

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.base_schema import PaginatedResponse
from utils.security import get_current_user
from core.user.model import User

from ai_workflow.team.model import TeamConfig
from ai_workflow.team.schema import (
    TeamConfigCreate,
    TeamConfigUpdate,
    TeamConfigOut,
    TeamRunRequest,
    TeamYamlImport,
)
from ai_workflow.team.service import TeamExecutor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/teams", tags=["AI团队"])


async def _ensure_team_exists(team_id: str, db: AsyncSession) -> TeamConfig:
    team = await db.get(TeamConfig, team_id)
    if not team or team.is_deleted:
        raise HTTPException(status_code=404, detail="团队配置不存在")
    return team


@router.post("", response_model=TeamConfigOut, summary="创建团队配置")
async def create_team(
    data: TeamConfigCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    team = TeamConfig(
        name=data.name,
        description=data.description,
        team_rules=data.team_rules,
        start_role=data.start_role,
        roles=json.dumps(
            {k: v.model_dump() for k, v in data.roles.items()},
            ensure_ascii=False,
        ),
        sys_creator_id=user.id,
    )
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return team


@router.get(
    "", response_model=PaginatedResponse[TeamConfigOut], summary="获取团队配置列表"
)
async def list_teams(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(
        default=20, ge=1, le=100, alias="pageSize", description="每页数量"
    ),
    name: Optional[str] = Query(None, description="名称搜索"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = select(TeamConfig).where(not TeamConfig.is_deleted)
    if name:
        query = query.where(TeamConfig.name.ilike(f"%{name}%"))
    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar()
    items = (
        (
            await db.execute(
                query.order_by(TeamConfig.sys_create_datetime.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return PaginatedResponse(items=list(items), total=total)


@router.get("/{team_id}", response_model=TeamConfigOut, summary="获取团队配置详情")
async def get_team(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await _ensure_team_exists(team_id, db)


@router.put("/{team_id}", response_model=TeamConfigOut, summary="更新团队配置")
async def update_team(
    team_id: str,
    data: TeamConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    team = await _ensure_team_exists(team_id, db)
    update_data = data.model_dump(exclude_unset=True)
    if "roles" in update_data:
        update_data["roles"] = json.dumps(
            {k: v.model_dump() for k, v in update_data["roles"].items()},
            ensure_ascii=False,
        )
    for key, value in update_data.items():
        setattr(team, key, value)
    await db.commit()
    await db.refresh(team)
    return team


@router.delete("/{team_id}", summary="删除团队配置")
async def delete_team(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    team = await _ensure_team_exists(team_id, db)
    team.is_deleted = True
    await db.commit()
    return {"message": "已删除"}


@router.post("/import", response_model=TeamConfigOut, summary="从YAML导入团队配置")
async def import_team(
    data: TeamYamlImport,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        parsed = yaml.safe_load(data.yaml_content)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML解析失败: {e}")

    if not isinstance(parsed, dict) or "roles" not in parsed:
        raise HTTPException(status_code=400, detail="YAML必须包含roles字段")

    team = TeamConfig(
        name=data.name or parsed.get("name", "未命名团队"),
        description=data.description or parsed.get("description", ""),
        team_rules=parsed.get("team_rules", ""),
        start_role=parsed.get("start_role", ""),
        roles=json.dumps(parsed.get("roles", {}), ensure_ascii=False),
        yaml_source=data.yaml_content,
        sys_creator_id=user.id,
    )
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return team


@router.post("/{team_id}/run", summary="运行团队（异步）")
async def run_team(
    team_id: str,
    req: TeamRunRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    config = await _ensure_team_exists(team_id, db)

    async def _bg():
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as exec_db:
            await TeamExecutor.execute_team(
                config=config,
                input_params=req.input_params,
                db=exec_db,
            )

    asyncio.create_task(_bg())
    return {"message": "团队任务已启动", "team_id": team_id}


@router.post("/{team_id}/stream", summary="SSE 流式运行团队")
async def stream_team(
    team_id: str,
    req: TeamRunRequest = Body(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    config = await _ensure_team_exists(team_id, db)
    queue: asyncio.Queue = asyncio.Queue()

    async def event_generator():
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as exec_db:
            task = asyncio.create_task(
                TeamExecutor.execute_team(
                    config,
                    req.input_params if req else None,
                    exec_db,
                    stream_queue=queue,
                )
            )
            try:
                while True:
                    event = await queue.get()
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event.get("event") in ("workflow_complete", "workflow_error"):
                        break
            except asyncio.CancelledError:
                task.cancel()
            except Exception as e:
                yield f"data: {json.dumps({'event': 'error', 'data': str(e)})}\n\n"
            finally:
                if not task.done():
                    task.cancel()
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
