from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

from rag.graph_merge.schema import GraphMergeRequest, GraphMergeResponse, KbMergeResponse, IncrementalUpdateResponse
from rag.graph_merge.service import (
    merge_graphs_service,
    merge_kb_graphs_service,
    get_kb_merged_visualization_service,
    get_merged_graph_status_service,
    incremental_update_file_service,
)

router = APIRouter(prefix="/api", tags=["图谱合并"])


@router.post("/graph-merge/merge", summary="增量合并新旧图谱")
async def merge_graphs(req: GraphMergeRequest):
    try:
        result = merge_graphs_service(
            old_graph_data=req.old_graph_data,
            new_graph_data=req.new_graph_data,
            struct_weight=req.struct_weight,
            max_total_communities=req.max_total_communities,
        )
        return GraphMergeResponse(
            success=True,
            message="图谱合并完成",
            **result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/knowledge-base/{kb_id}/merge-graphs", summary="合并知识库下所有图谱")
async def merge_kb_graphs(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await merge_kb_graphs_service(kb_id, db)
        await db.commit()
        return KbMergeResponse(success=True, message="知识库图谱合并完成", **result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/knowledge-base/{kb_id}/merged-graph",
    summary="获取合并后图谱的可视化数据",
)
async def get_kb_merged_graph(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        vis_data = await get_kb_merged_visualization_service(kb_id, db)
        return vis_data
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/knowledge-base/{kb_id}/merged-graph/status",
    summary="获取合并图谱的状态信息",
)
async def get_kb_merged_graph_status(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_merged_graph_status_service(kb_id, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/knowledge-base/{kb_id}/files/{file_id}/incremental-update",
    summary="单文件增量更新：上传新文本/Word/PDF 并合并图谱",
)
async def incremental_file_update(
    kb_id: str,
    file_id: str,
    file: UploadFile = File(..., description="新增的文本/Word/PDF 文件"),
    db: AsyncSession = Depends(get_db),
):
    import os
    import tempfile
    import uuid

    try:
        suffix = os.path.splitext(file.filename or ".txt")[1].lower()
        tmp_path = os.path.join(tempfile.gettempdir(), f"incr_{uuid.uuid4().hex}{suffix}")
        with open(tmp_path, "wb") as f:
            f.write(await file.read())

        from rag.kb_manager.service import extract_text_from_document

        content = await extract_text_from_document(tmp_path, suffix)

        os.remove(tmp_path)

        if not content.strip():
            raise HTTPException(status_code=400, detail="无法提取文本内容")

        result = await incremental_update_file_service(kb_id, file_id, content, db)
        return IncrementalUpdateResponse(
            success=True,
            message="增量更新完成",
            **result,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


