from typing import List, Optional
import json
import mimetypes
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    UploadFile,
    File,
)
from fastapi.responses import FileResponse, Response
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from utils.security import get_current_user
from core.user.model import User

from rag.kb_manager.schema import (
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseResponse,
    KnowledgeBaseListResponse,
    KnowledgeBaseFileResponse,
    KnowledgeBaseFileListResponse,
    FileSchemaUpdate,
    FileUploadResponseWrapper,
    DeleteResponse,
    RoleInfo,
    DeptInfo,
    UserInfoSimple,
    KBPermissionUpdateRequest,
    KBPermissionBatchUpdate,
    KBPermissionDetailsResponse,
    KBAccessCheckResponse,
    KbFileTextContent,
    KbFileTextUpdate,
)
from rag.kb_manager.db_service import (
    KnowledgeBaseService,
    KnowledgeBaseFileService,
)
from rag.kb_manager.service import (
    upload_files_to_kb,
    clear_cache_files,
    KnowledgeBasePermissionService,
)
from rag.graph_manager.db_service import KnowledgeGraphService
from rag.kb_manager.model import KnowledgeBaseFile


# =============================================
# KB CRUD Router
# =============================================
router = APIRouter(prefix="/api", tags=["知识库管理"])

# =============================================
# Permission Router (sub-router)
# =============================================
perm_router = APIRouter(prefix="/api/knowledge-base", tags=["知识库权限管理"])


# ─── Knowledge Base CRUD ───


@router.post("/knowledge-base", response_model=KnowledgeBaseResponse, summary="创建知识库")
async def create_knowledge_base(
    data: KnowledgeBaseCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    existing = await KnowledgeBaseService.get_by_field(db, field="name", value=data.name)
    if existing:
        raise HTTPException(status_code=400, detail="知识库名称已存在")
    kb = await KnowledgeBaseService.create(db, data)
    # 自动授予创建者访问权限
    from rag.kb_manager.model import KnowledgeBaseUser
    db.add(KnowledgeBaseUser(user_id=user.id, kb_id=kb.id))
    if data.permissions:
        await KnowledgeBasePermissionService.set_kb_permissions(
            db, kb.id,
            role_ids=data.permissions.role_ids,
            dept_ids=data.permissions.dept_ids,
            user_ids=data.permissions.user_ids,
        )
    await db.commit()
    return kb


@router.get("/knowledge-bases", response_model=KnowledgeBaseListResponse, summary="知识库列表")
async def list_knowledge_bases(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=500, alias="pageSize"),
    name: str = Query(default=None, description="知识库名称搜索"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb_ids = await KnowledgeBasePermissionService.get_user_visible_kb_ids(db, user)
    if kb_ids is not None:
        base_query = (
            select(KnowledgeBaseService.model)
            .where(
                KnowledgeBaseService.model.id.in_(kb_ids),
                KnowledgeBaseService.model.is_deleted == False,
            )
        )
        if name:
            base_query = base_query.where(KnowledgeBaseService.model.name.ilike(f"%{name}%"))
        count_result = await db.execute(select(sa_func.count()).select_from(base_query.subquery()))
        total = count_result.scalar() or 0
        offset = (page - 1) * page_size
        result = await db.execute(
            base_query.order_by(
                KnowledgeBaseService.model.sort.desc(),
                KnowledgeBaseService.model.sys_create_datetime.desc(),
            ).offset(offset).limit(page_size)
        )
        items = list(result.scalars().all())
    else:
        items, total = await KnowledgeBaseService.get_list_with_file_count(
            db, page=page, page_size=page_size, name=name
        )

    for item in items:
        count_query = (
            select(sa_func.count(KnowledgeBaseFile.id))
            .where(
                KnowledgeBaseFile.kb_id == item.id,
                KnowledgeBaseFile.is_deleted == False,
            )
        )
        cnt = await db.execute(count_query)
        item.file_count = cnt.scalar() or 0

    return KnowledgeBaseListResponse(items=items, total=total)


@router.get("/knowledge-base/{kb_id}", response_model=KnowledgeBaseResponse, summary="知识库详情")
async def get_knowledge_base(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = await KnowledgeBaseService.get_by_id(db, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    kb.file_count = await KnowledgeBaseFileService.count_by_kb(db, kb_id)
    return kb


@router.put("/knowledge-base/{kb_id}", response_model=KnowledgeBaseResponse, summary="更新知识库")
async def update_knowledge_base(
    kb_id: str,
    data: KnowledgeBaseUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    if data.name:
        existing = await KnowledgeBaseService.get_by_field(db, field="name", value=data.name)
        if existing and existing.id != kb_id:
            raise HTTPException(status_code=400, detail="知识库名称已存在")
    # 分离 permissions 字段，先更新基本信息
    permissions_data = data.permissions
    update_data = data.model_copy(update={"permissions": None})
    result = await KnowledgeBaseService.update(db, record_id=kb_id, data=update_data)
    if not result:
        raise HTTPException(status_code=404, detail="知识库不存在")
    # 更新权限
    if permissions_data is not None:
        await KnowledgeBasePermissionService.set_kb_permissions(
            db, kb_id,
            role_ids=permissions_data.role_ids,
            dept_ids=permissions_data.dept_ids,
            user_ids=permissions_data.user_ids,
        )
    return result


@router.delete("/knowledge-base/{kb_id}", summary="删除知识库")
async def delete_knowledge_base(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    kb = await KnowledgeBaseService.get_by_id(db, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    files = await KnowledgeBaseFileService.get_files_by_kb(db, kb_id)
    for f in files:
        await clear_cache_files(kb_id, f.id)
        await KnowledgeGraphService.delete_by_file(db, f.id)
        await KnowledgeBaseFileService.delete(db, f.id)
    success = await KnowledgeBaseService.delete(db, kb_id)
    if not success:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return DeleteResponse(msg="知识库删除成功")


# ─── File Management ───


@router.post(
    "/knowledge-base/{kb_id}/files/upload",
    summary="上传文件到知识库",
)
async def upload_kb_files(
    kb_id: str,
    files: List[UploadFile] = File(...),
    schema_file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = await KnowledgeBaseService.get_by_id(db, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")

    schema_json = None
    if schema_file:
        try:
            schema_content = await schema_file.read()
            schema_json = json.loads(schema_content)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Schema文件格式错误，需要JSON格式")

    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一个文件")

    try:
        results = await upload_files_to_kb(kb_id, files, schema_json, db)
        return FileUploadResponseWrapper(items=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/knowledge-base/{kb_id}/files",
    response_model=KnowledgeBaseFileListResponse,
    summary="文件列表",
)
async def list_kb_files(kb_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    kb = await KnowledgeBaseService.get_by_id(db, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    files = await KnowledgeBaseFileService.get_files_by_kb(db, kb_id)
    return KnowledgeBaseFileListResponse(items=files, total=len(files))


@router.get(
    "/knowledge-base/{kb_id}/files/{file_id}",
    response_model=KnowledgeBaseFileResponse,
    summary="文件详情",
)
async def get_kb_file(kb_id: str, file_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    return f


@router.get(
    "/knowledge-base/{kb_id}/files/{file_id}/preview",
    summary="文件预览（PDF/Word/文本）",
)
async def preview_kb_file(
    kb_id: str, file_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    from rag.kb_manager.service import DATA_UPLOAD_DIR
    ext = f.file_type or ".bin"
    file_path = DATA_UPLOAD_DIR / kb_id / f"{file_id}{ext}"
    if file_path.exists():
        media_type, _ = mimetypes.guess_type(str(file_path))
        disposition = f"inline; filename*=UTF-8''{quote(f.filename)}"
        return FileResponse(
            str(file_path),
            media_type=media_type or "application/octet-stream",
            headers={"Content-Disposition": disposition},
        )
    content = f.content or "(无内容)"
    media_type = "text/plain; charset=utf-8"
    return Response(content=content, media_type=media_type)


@router.get(
    "/knowledge-base/{kb_id}/files/{file_id}/content",
    summary="文件提取文本内容",
)
async def get_kb_file_content(
    kb_id: str, file_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    return {"content": f.content or "", "filename": f.filename}


@router.put(
    "/knowledge-base/{kb_id}/files/{file_id}/schema",
    summary="更新文件Schema",
)
async def update_file_schema(
    kb_id: str, file_id: str, data: FileSchemaUpdate, db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    f.schema_json = data.schema_definition
    await db.flush()
    await db.commit()
    return {"msg": "Schema更新成功"}


@router.delete(
    "/knowledge-base/{kb_id}/files/{file_id}",
    summary="删除文件",
)
async def delete_kb_file(kb_id: str, file_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    f = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not f or f.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文件不存在")
    await clear_cache_files(kb_id, file_id)
    await KnowledgeGraphService.delete_by_file(db, file_id)
    success = await KnowledgeBaseFileService.delete(db, file_id)
    if not success:
        raise HTTPException(status_code=404, detail="文件不存在")
    return DeleteResponse(msg="文件删除成功")


# ─── KB File Cross-KB Tree & Text ───


@router.get(
    "/knowledge-base/files/tree",
    summary="KB文件目录树（知识库资料）",
)
async def get_kb_file_tree(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb_ids = await KnowledgeBasePermissionService.get_user_visible_kb_ids(db, user)
    query = select(KnowledgeBaseService.model).where(
        KnowledgeBaseService.model.is_deleted == False,
    )
    if kb_ids is not None:
        query = query.where(KnowledgeBaseService.model.id.in_(kb_ids))
    result = await db.execute(query.order_by(KnowledgeBaseService.model.sort.desc()))
    kbs = result.scalars().all()
    return [
        {
            "id": kb.id,
            "name": kb.name,
            "fileType": "folder",
            "hasChildren": True,
        }
        for kb in kbs
    ]


@router.get(
    "/knowledge-base/files/{file_id}/text",
    response_model=KbFileTextContent,
    summary="获取KB文件文本内容",
)
async def get_kb_file_text(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await KnowledgeBaseFileService.get_text_content(db, file_id)
    if not result:
        raise HTTPException(status_code=404, detail="文件不存在")
    kb = await KnowledgeBaseService.get_by_id(db, result["kbId"])
    if not kb or not await KnowledgeBasePermissionService.check_kb_access(db, result["kbId"], user):
        raise HTTPException(status_code=403, detail="无权访问该文件")
    result["kbName"] = kb.name
    return result


@router.put(
    "/knowledge-base/files/{file_id}/text",
    summary="保存KB文件文本内容",
)
async def update_kb_file_text(
    file_id: str,
    data: KbFileTextUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file = await KnowledgeBaseFileService.get_by_id(db, file_id)
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not await KnowledgeBasePermissionService.check_kb_access(db, file.kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该文件")
    await KnowledgeBaseFileService.update_text_content(db, file_id, data.textContent)
    return {"message": "文本内容已保存"}


# ─── Permission Management ───


@perm_router.get(
    "/roles",
    response_model=List[RoleInfo],
    summary="获取所有角色（用于KB权限分配）",
)
async def list_roles_for_permission(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from core.role.model import Role as RoleModel
    query = select(RoleModel).where(
        RoleModel.is_deleted == False,
        RoleModel.status == True,
    ).order_by(RoleModel.priority.desc())
    result = await db.execute(query)
    return result.scalars().all()


@perm_router.get(
    "/role/{role_id}/kb-permissions",
    response_model=KnowledgeBaseListResponse,
    summary="获取角色已分配的知识库列表",
)
async def get_role_kb_permissions(
    role_id: str,
    db: AsyncSession = Depends(get_db),
):
    kb_ids = await KnowledgeBasePermissionService.get_role_kb_ids(db, role_id)
    if not kb_ids:
        return KnowledgeBaseListResponse(items=[], total=0)

    query = (
        select(KnowledgeBaseService.model)
        .where(
            KnowledgeBaseService.model.id.in_(kb_ids),
            KnowledgeBaseService.model.is_deleted == False,
        )
    )
    result = await db.execute(query)
    items = list(result.scalars().all())

    for item in items:
        count_query = (
            select(sa_func.count(KnowledgeBaseFile.id))
            .where(
                KnowledgeBaseFile.kb_id == item.id,
                KnowledgeBaseFile.is_deleted == False,
            )
        )
        cnt = await db.execute(count_query)
        item.file_count = cnt.scalar() or 0

    return KnowledgeBaseListResponse(items=items, total=len(items))


@perm_router.put(
    "/role/{role_id}/kb-permissions",
    summary="更新角色的知识库权限",
)
async def update_role_kb_permissions(
    role_id: str,
    data: KBPermissionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="仅超级管理员可管理知识库权限")
    if data.kb_ids:
        result = await db.execute(
            select(KnowledgeBaseService.model.id).where(
                KnowledgeBaseService.model.id.in_(data.kb_ids),
                KnowledgeBaseService.model.is_deleted == False,
            )
        )
        existing_ids = {row[0] for row in result}
        invalid_ids = set(data.kb_ids) - existing_ids
        if invalid_ids:
            raise HTTPException(status_code=400, detail=f"知识库不存在: {', '.join(invalid_ids)}")
    await KnowledgeBasePermissionService.set_role_kbs(db, role_id, data.kb_ids)
    return {"msg": "权限更新成功"}


@perm_router.get(
    "/kb-access-check/{kb_id}",
    response_model=KBAccessCheckResponse,
    summary="验证当前用户是否有权访问指定知识库",
)
async def check_kb_access(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    has_access = await KnowledgeBasePermissionService.check_kb_access(
        db, kb_id, current_user
    )
    return KBAccessCheckResponse(has_access=has_access)


# ─── 部门列表（用于权限分配选择器） ───


@perm_router.get(
    "/departments",
    response_model=List[DeptInfo],
    summary="获取所有部门（用于KB权限分配）",
)
async def list_departments_for_permission(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from core.dept.model import Dept
    query = select(Dept).where(
        Dept.is_deleted == False,
        Dept.status == True,
    ).order_by(Dept.level, Dept.name)
    result = await db.execute(query)
    return result.scalars().all()


# ─── 用户搜索（用于权限分配选择器） ───


@perm_router.get(
    "/users",
    response_model=List[UserInfoSimple],
    summary="搜索用户（用于KB权限分配）",
)
async def list_users_for_permission(
    name: str = Query(default=None, description="用户名/真实姓名搜索"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from core.user.model import User
    query = select(User).where(
        User.is_deleted == False,
        User.user_status == 1,
    )
    if name:
        query = query.where(
            (User.username.ilike(f"%{name}%")) | (User.name.ilike(f"%{name}%"))
        )
    query = query.order_by(User.name).limit(200)
    result = await db.execute(query)
    return result.scalars().all()


# ─── 部门 KB 权限管理 ───


@perm_router.get(
    "/dept/{dept_id}/kb-permissions",
    response_model=KnowledgeBaseListResponse,
    summary="获取部门已分配的知识库列表",
)
async def get_dept_kb_permissions(
    dept_id: str,
    db: AsyncSession = Depends(get_db),
):
    kb_ids = await KnowledgeBasePermissionService.get_dept_kb_ids(db, dept_id)
    if not kb_ids:
        return KnowledgeBaseListResponse(items=[], total=0)
    query = (
        select(KnowledgeBaseService.model)
        .where(
            KnowledgeBaseService.model.id.in_(kb_ids),
            KnowledgeBaseService.model.is_deleted == False,
        )
    )
    result = await db.execute(query)
    items = list(result.scalars().all())
    for item in items:
        cnt = await db.execute(
            select(sa_func.count(KnowledgeBaseFile.id))
            .where(KnowledgeBaseFile.kb_id == item.id, KnowledgeBaseFile.is_deleted == False)
        )
        item.file_count = cnt.scalar() or 0
    return KnowledgeBaseListResponse(items=items, total=len(items))


@perm_router.put(
    "/dept/{dept_id}/kb-permissions",
    summary="更新部门的知识库权限",
)
async def update_dept_kb_permissions(
    dept_id: str,
    data: KBPermissionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="仅超级管理员可管理知识库权限")
    if data.kb_ids:
        result = await db.execute(
            select(KnowledgeBaseService.model.id).where(
                KnowledgeBaseService.model.id.in_(data.kb_ids),
                KnowledgeBaseService.model.is_deleted == False,
            )
        )
        existing_ids = {row[0] for row in result}
        invalid_ids = set(data.kb_ids) - existing_ids
        if invalid_ids:
            raise HTTPException(status_code=400, detail=f"知识库不存在: {', '.join(invalid_ids)}")
    await KnowledgeBasePermissionService.set_dept_kbs(db, dept_id, data.kb_ids)
    return {"msg": "权限更新成功"}


# ─── 用户 KB 权限管理 ───


@perm_router.get(
    "/user/{user_id}/kb-permissions",
    response_model=KnowledgeBaseListResponse,
    summary="获取用户已分配的知识库列表",
)
async def get_user_kb_permissions(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    kb_ids = await KnowledgeBasePermissionService.get_user_kb_ids(db, user_id)
    if not kb_ids:
        return KnowledgeBaseListResponse(items=[], total=0)
    query = (
        select(KnowledgeBaseService.model)
        .where(
            KnowledgeBaseService.model.id.in_(kb_ids),
            KnowledgeBaseService.model.is_deleted == False,
        )
    )
    result = await db.execute(query)
    items = list(result.scalars().all())
    for item in items:
        cnt = await db.execute(
            select(sa_func.count(KnowledgeBaseFile.id))
            .where(KnowledgeBaseFile.kb_id == item.id, KnowledgeBaseFile.is_deleted == False)
        )
        item.file_count = cnt.scalar() or 0
    return KnowledgeBaseListResponse(items=items, total=len(items))


@perm_router.put(
    "/user/{user_id}/kb-permissions",
    summary="更新用户的知识库权限",
)
async def update_user_kb_permissions(
    user_id: str,
    data: KBPermissionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="仅超级管理员可管理知识库权限")
    if data.kb_ids:
        result = await db.execute(
            select(KnowledgeBaseService.model.id).where(
                KnowledgeBaseService.model.id.in_(data.kb_ids),
                KnowledgeBaseService.model.is_deleted == False,
            )
        )
        existing_ids = {row[0] for row in result}
        invalid_ids = set(data.kb_ids) - existing_ids
        if invalid_ids:
            raise HTTPException(status_code=400, detail=f"知识库不存在: {', '.join(invalid_ids)}")
    await KnowledgeBasePermissionService.set_user_kbs(db, user_id, data.kb_ids)
    return {"msg": "权限更新成功"}


# ─── KB 维度权限查询与修改 ───


@perm_router.get(
    "/{kb_id}/permissions",
    response_model=KBPermissionDetailsResponse,
    summary="获取知识库的所有权限配置",
)
async def get_kb_permissions(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_id, current_user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    return await KnowledgeBasePermissionService.get_kb_permissions(db, kb_id)


@perm_router.put(
    "/{kb_id}/permissions",
    response_model=KBPermissionDetailsResponse,
    summary="批量更新知识库的权限配置",
)
async def update_kb_permissions(
    kb_id: str,
    data: KBPermissionBatchUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="仅超级管理员可管理知识库权限")
    kb = await KnowledgeBaseService.get_by_id(db, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if data.is_public is not None:
        kb.is_public = data.is_public
    await KnowledgeBasePermissionService.set_kb_permissions(
        db, kb_id,
        role_ids=data.role_ids,
        dept_ids=data.dept_ids,
        user_ids=data.user_ids,
        auto_commit=False,
    )
    await db.commit()
    return await KnowledgeBasePermissionService.get_kb_permissions(db, kb_id)
