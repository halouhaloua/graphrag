from agentscope.tool import FunctionTool

from chronicle_writer.tools.reference_tool import _db_factory


async def get_outline_tree(project_id: str) -> str:
    """获取项目的完整大纲树（层级结构）。

    Args:
        project_id: 项目ID

    Returns:
        包含层次结构的大纲JSON
    """
    from sqlalchemy import select
    from chronicle_writer.model import ChronicleSection

    async with _db_factory() as db:
        stmt = (
            select(ChronicleSection)
            .where(
                ChronicleSection.project_id == project_id,
                ChronicleSection.is_deleted.is_(False),
            )
            .order_by(ChronicleSection.sort_order)
        )
        result = await db.execute(stmt)
        sections = result.scalars().all()

        def build_tree(parent_id=None):
            children = [s for s in sections if s.parent_id == parent_id]
            return [
                {
                    "id": s.id,
                    "title": s.title,
                    "level": s.level,
                    "sort_order": s.sort_order,
                    "status": s.status,
                    "children": build_tree(s.id),
                }
                for s in sorted(children, key=lambda x: x.sort_order)
            ]

        import json

        return json.dumps(build_tree(), ensure_ascii=False)


async def update_section_title(section_id: str, title: str) -> str:
    """修改章节标题。

    Args:
        section_id: 章节ID
        title: 新标题

    Returns:
        更新结果JSON
    """
    from sqlalchemy import select
    from chronicle_writer.model import ChronicleSection
    import json

    async with _db_factory() as db:
        stmt = select(ChronicleSection).where(
            ChronicleSection.id == section_id,
            ChronicleSection.is_deleted.is_(False),
        )
        result = await db.execute(stmt)
        s = result.scalar_one_or_none()
        if not s:
            return json.dumps({"error": "章节不存在"})
        s.title = title
        await db.flush()
        return json.dumps(
            {"id": section_id, "title": title, "status": "updated"}, ensure_ascii=False
        )


async def reorder_sections(project_id: str, section_ids: list) -> str:
    """重排章节顺序。

    Args:
        project_id: 项目ID
        section_ids: 按新顺序排列的章节ID列表

    Returns:
        重排结果JSON
    """
    import json
    from sqlalchemy import select
    from chronicle_writer.model import ChronicleSection

    async with _db_factory() as db:
        for idx, sid in enumerate(section_ids):
            stmt = select(ChronicleSection).where(
                ChronicleSection.id == sid,
                ChronicleSection.project_id == project_id,
                ChronicleSection.is_deleted.is_(False),
            )
            result = await db.execute(stmt)
            s = result.scalar_one_or_none()
            if s:
                s.sort_order = idx * 10
        await db.flush()
        return json.dumps(
            {"status": "reordered", "count": len(section_ids)}, ensure_ascii=False
        )


outline_tool = FunctionTool(
    func=get_outline_tree,
    name="GetOutlineTree",
    description="获取项目的完整大纲树（含层级结构）",
    is_read_only=True,
)

update_title_tool = FunctionTool(
    func=update_section_title,
    name="UpdateSectionTitle",
    description="修改章节标题",
    is_read_only=False,
)

reorder_tool = FunctionTool(
    func=reorder_sections,
    name="ReorderSections",
    description="重排项目章节顺序",
    is_read_only=False,
)
