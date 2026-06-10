"""
RAG文件管理API
"""
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from core.user.model import User
from utils.security import get_current_user

from rag.file_manager.schema import (
    RagFileManagerResponse,
    CreateFolderIn,
    RenameItemIn,
    BatchDeleteIn,
    PaginatedResponse,
    TextContentResponse,
    TextContentUpdate,
    AddToKbIn,
)
from rag.file_manager.service import (
    RagFileManagerService,
    _build_file_response,
    RAG_FILE_STORAGE_PATH,
)

router = APIRouter(prefix="/api/file-manager", tags=["RAG文件管理"])


def _validate_safe_path(user_path: str, base_dir: str) -> str:
    """Validate and normalize a file path to prevent directory traversal."""
    full_path = os.path.normpath(os.path.join(base_dir, user_path.replace("\\", "/")))
    norm_base = os.path.normpath(base_dir)
    if not full_path.startswith(norm_base):
        raise HTTPException(status_code=403, detail="非法的路径")
    return full_path


@router.post("/upload", response_model=RagFileManagerResponse, summary="上传文件")
async def upload_file(
    file: UploadFile = File(...),
    parent_id: Optional[str] = Form(None, alias="parentId"),
    scope: str = Form('personal'),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    file_content = await file.read()
    file_size = len(file_content)

    record = await RagFileManagerService.upload_file(
        db=db,
        file_content=file_content,
        filename=file.filename,
        file_size=file_size,
        scope=scope,
        parent_id=parent_id,
        creator_id=current_user.id,
    )
    return _build_file_response(record)


@router.post("/folder", response_model=RagFileManagerResponse, summary="创建文件夹")
async def create_folder(
    data: CreateFolderIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    folder = await RagFileManagerService.create_folder(
        db=db,
        name=data.name,
        scope=data.scope,
        parent_id=data.parent_id,
        creator_id=current_user.id,
    )
    if not folder:
        raise HTTPException(status_code=422, detail="同名文件夹已存在")
    return _build_file_response(folder)


@router.get("", response_model=PaginatedResponse, summary="获取文件列表")
async def list_files(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    parent_id: Optional[str] = Query(None, alias="parentId"),
    scope: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    file_type: Optional[str] = Query(None, alias="fileType"),
    creator_id: Optional[str] = Query(None, alias="creatorId"),
    db: AsyncSession = Depends(get_db),
):
    items, total = await RagFileManagerService.get_list(
        db=db,
        page=page,
        page_size=page_size,
        parent_id=parent_id,
        scope=scope,
        name=name,
        file_type=file_type,
        creator_id=creator_id,
    )

    result_items = []
    for item in items:
        has_children = False
        if item.file_type == 'folder':
            has_children = await RagFileManagerService.has_children(db, item.id)
        result_items.append(_build_file_response(item, has_children))

    return PaginatedResponse(items=result_items, total=total)


@router.get("/tree", summary="获取文件夹树结构")
async def get_folder_tree(
    scope: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    conditions = [
        RagFileManagerService.model.file_type == 'folder',
        RagFileManagerService.model.is_deleted == False,
    ]
    if scope:
        conditions.append(RagFileManagerService.model.scope == scope)

    from sqlalchemy import select
    query = select(RagFileManagerService.model).where(*conditions).order_by(RagFileManagerService.model.name)
    result = await db.execute(query)
    folders = result.scalars().all()

    return [_build_file_response(f, await RagFileManagerService.has_children(db, f.id)) for f in folders]


@router.get("/file-info/{file_id}", summary="获取文件信息")
async def get_file_info(
    file_id: str,
    db: AsyncSession = Depends(get_db),
):
    record = await RagFileManagerService.get_by_id(db, file_id)
    if not record:
        raise HTTPException(status_code=404, detail="文件不存在")
    return {
        "id": record.id,
        "name": record.name,
        "fileType": record.file_type,
        "size": record.size,
        "fileExt": record.file_ext,
        "mimeType": record.mime_type,
        "storagePath": record.storage_path,
        "scope": record.scope,
    }


@router.put("/{file_id}/rename", response_model=RagFileManagerResponse, summary="重命名")
async def rename_item(
    file_id: str,
    data: RenameItemIn,
    db: AsyncSession = Depends(get_db),
):
    item = await RagFileManagerService.rename_item(db, file_id, data.name)
    if not item:
        raise HTTPException(status_code=400, detail="重命名失败，可能同名文件/文件夹已存在")
    return _build_file_response(item)


@router.delete("/{file_id}", summary="删除文件/文件夹")
async def delete_item(
    file_id: str,
    hard: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
):
    success = await RagFileManagerService.delete_item(db, file_id, hard)
    if not success:
        raise HTTPException(status_code=404, detail="文件不存在")
    return {"message": "删除成功"}


@router.post("/batch/delete", summary="批量删除")
async def batch_delete(
    data: BatchDeleteIn,
    db: AsyncSession = Depends(get_db),
):
    deleted_count = await RagFileManagerService.batch_delete(db, data.ids)
    return {"message": f"成功删除 {deleted_count} 个文件/文件夹"}


@router.get("/stream/{file_id}", summary="流式传输文件")
async def stream_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
):
    record = await RagFileManagerService.get_by_id(db, file_id)
    if not record or record.file_type != 'file':
        raise HTTPException(status_code=404, detail="文件不存在")

    full_path = _validate_safe_path(record.storage_path, RAG_FILE_STORAGE_PATH)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    from urllib.parse import quote
    return FileResponse(
        path=full_path,
        media_type=record.mime_type or 'application/octet-stream',
        headers={
            'Content-Disposition': f"inline; filename*=UTF-8''{quote(record.name)}",
            'Accept-Ranges': 'bytes',
            'Cache-Control': 'public, max-age=86400',
        },
    )


@router.get("/download", summary="下载文件")
async def download_file(
    path: str = Query(..., description="文件存储路径"),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    result = await db.execute(
        select(RagFileManagerService.model).where(
            RagFileManagerService.model.storage_path == path,
            RagFileManagerService.model.file_type == 'file',
            RagFileManagerService.model.is_deleted == False,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="文件不存在")

    full_path = _validate_safe_path(path, RAG_FILE_STORAGE_PATH)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(
        full_path,
        filename=record.name,
        media_type=record.mime_type or 'application/octet-stream',
    )


@router.get("/{file_id}/text", response_model=TextContentResponse, summary="获取文本内容")
async def get_file_text(
    file_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await RagFileManagerService.get_text_content(db, file_id)
    if not result:
        raise HTTPException(status_code=404, detail="文件不存在")
    return result


@router.put("/{file_id}/text", summary="更新文本内容")
async def update_file_text(
    file_id: str,
    data: TextContentUpdate,
    db: AsyncSession = Depends(get_db),
):
    item = await RagFileManagerService.update_text_content(db, file_id, data.text_content)
    if not item:
        raise HTTPException(status_code=404, detail="文件不存在")
    return {"message": "文本内容已保存"}


@router.post("/{file_id}/add-to-kb", summary="添加到知识库")
async def add_file_to_kb(
    file_id: str,
    data: AddToKbIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from rag.kb_manager.service import KnowledgeBasePermissionService
    if not await KnowledgeBasePermissionService.check_kb_access(db, data.kb_id, current_user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    result = await RagFileManagerService.add_to_knowledge_base(
        db, file_id, data.kb_id, creator_id=current_user.id
    )
    if not result:
        raise HTTPException(status_code=404, detail="文件不存在")
    return {"message": "已添加到知识库", "data": result}


@router.post("/{file_id}/ocr", summary="触发传统OCR识别")
async def trigger_ocr(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await RagFileManagerService.trigger_ocr(db, file_id)
    if not result:
        raise HTTPException(status_code=404, detail="文件不存在")
    return result


@router.post("/{file_id}/complex-ocr", summary="触发复杂竖排繁体文本OCR")
async def trigger_complex_ocr(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await RagFileManagerService.trigger_complex_ocr(db, file_id)
    if not result:
        raise HTTPException(status_code=404, detail="文件不存在")
    return result


@router.get("/{file_id}/complex-ocr/estimate", summary="预估复杂OCR时间")
async def estimate_complex_ocr(
    file_id: str,
    db: AsyncSession = Depends(get_db),
):
    record = await RagFileManagerService.get_by_id(db, file_id)
    if not record or record.file_type != 'file':
        raise HTTPException(status_code=404, detail="文件不存在")

    full_path = _validate_safe_path(record.storage_path, RAG_FILE_STORAGE_PATH)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    ext = (record.file_ext or '').lower()
    if ext not in ('.pdf', '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'):
        raise HTTPException(status_code=400, detail="不支持的文件类型")

    import fitz
    doc = fitz.open(full_path)
    total = len(doc)
    doc.close()

    try:
        import torch
        is_gpu = torch.cuda.is_available()
    except ImportError:
        is_gpu = False
    sec_per_page = 3 if is_gpu else 20
    estimated = total * sec_per_page

    return {
        "totalPages": total,
        "estimatedSeconds": estimated,
        "estimatedMinutes": round(estimated / 60, 1),
        "device": "GPU" if is_gpu else "CPU",
    }


@router.get("/proxy/{file_id}", summary="代理文件访问")
async def proxy_file(
    file_id: str,
    download: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    record = await RagFileManagerService.get_by_id(db, file_id)
    if not record or record.file_type != 'file':
        raise HTTPException(status_code=404, detail="文件不存在")

    full_path = _validate_safe_path(record.storage_path, RAG_FILE_STORAGE_PATH)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    disposition = 'attachment' if download else 'inline'
    from urllib.parse import quote
    return FileResponse(
        path=full_path,
        media_type=record.mime_type or 'application/octet-stream',
        headers={
            'Content-Disposition': f"{disposition}; filename*=UTF-8''{quote(record.name)}",
            'Accept-Ranges': 'bytes',
            'Cache-Control': 'public, max-age=86400',
        },
    )
