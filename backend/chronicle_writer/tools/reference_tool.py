import json
from typing import Optional

from agentscope.tool import FunctionTool

from chronicle_writer.model import ChronicleReference

_db_factory = None


def init_tools(db_factory):
    global _db_factory
    _db_factory = db_factory


async def add_reference(
    project_id: str,
    section_id: str,
    ref_key: str,
    source_type: str = "kg_file",
    source_title: str = "",
    author: str = "",
    publisher: str = "",
    year: str = "",
    citation_text: str = "",
    quote_text: str = "",
) -> str:
    """添加一条参考文献记录到项目中。

    Args:
        project_id: 项目ID
        section_id: 章节ID
        ref_key: 引用键，如 ref_001
        source_type: 来源类型: kg_file/kb_document/book/periodical/archive/website/other
        source_title: 来源标题
        author: 作者
        publisher: 出版者
        year: 年份
        citation_text: 格式化引文
        quote_text: 原文引述

    Returns:
        创建的参考文献信息JSON
    """
    async with _db_factory() as db:
        ref = ChronicleReference(
            project_id=project_id,
            section_id=section_id,
            ref_key=ref_key,
            source_type=source_type,
            source_title=source_title,
            author=author,
            publisher=publisher,
            year=year,
            citation_text=citation_text,
            quote_text=quote_text,
            confidence=1.0,
            verified=True,
        )
        db.add(ref)
        await db.flush()
        await db.refresh(ref)
        return json.dumps(
            {"id": ref.id, "ref_key": ref_key, "status": "created"}, ensure_ascii=False
        )


async def list_references(
    project_id: str,
    section_id: Optional[str] = None,
) -> str:
    """列出项目的参考文献列表。

    Args:
        project_id: 项目ID
        section_id: (可选)章节ID过滤

    Returns:
        参考文献列表JSON
    """
    from sqlalchemy import select

    async with _db_factory() as db:
        filters = [
            ChronicleReference.project_id == project_id,
            ChronicleReference.is_deleted.is_(False),
        ]
        if section_id:
            filters.append(ChronicleReference.section_id == section_id)
        stmt = (
            select(ChronicleReference)
            .where(*filters)
            .order_by(ChronicleReference.ref_key)
        )
        result = await db.execute(stmt)
        refs = result.scalars().all()
        data = [
            {
                "id": r.id,
                "ref_key": r.ref_key,
                "source_title": r.source_title,
                "citation_text": r.citation_text,
                "verified": r.verified,
            }
            for r in refs
        ]
        return json.dumps(data, ensure_ascii=False)


add_reference_tool = FunctionTool(
    func=add_reference,
    name="AddReference",
    description="添加一条参考文献记录到项目中",
    is_read_only=False,
)

list_references_tool = FunctionTool(
    func=list_references,
    name="ListReferences",
    description="列出项目的参考文献列表",
    is_read_only=True,
)
