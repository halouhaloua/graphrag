import json

from agentscope.tool import ToolBase, ToolChunk
from agentscope.permission import (
    PermissionContext,
    PermissionDecision,
    PermissionBehavior,
)
from agentscope.message import TextBlock

from chronicle_writer.model import ChronicleSection
from chronicle_writer.tools.reference_tool import _db_factory


class SectionCRUDTool(ToolBase):
    """章节增删改查工具"""

    name = "SectionCRUD"
    description = (
        "创建、读取、更新、删除志书章节。action: create/read/update/delete/list"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "read", "update", "delete", "list"],
                "description": "操作类型",
            },
            "project_id": {"type": "string", "description": "项目ID"},
            "section_id": {"type": "string", "description": "章节ID"},
            "title": {"type": "string", "description": "章节标题"},
            "content": {"type": "string", "description": "正文内容（HTML）"},
            "parent_id": {"type": "string", "description": "父章节ID"},
            "level": {"type": "integer", "description": "层级"},
            "sort_order": {"type": "integer", "description": "排序"},
        },
        "required": ["action"],
    }
    is_concurrency_safe = False
    is_read_only = False

    def __init__(self):
        pass

    async def check_permissions(
        self,
        tool_input: dict,
        context: PermissionContext,
    ) -> PermissionDecision:
        if tool_input.get("action") in ("read", "list"):
            return PermissionDecision(behavior=PermissionBehavior.ALLOW)
        return PermissionDecision(behavior=PermissionBehavior.ALLOW)

    async def __call__(self, action: str, **kwargs) -> ToolChunk:
        if action == "list":
            return await self._list_sections(kwargs.get("project_id", ""))
        elif action == "read":
            return await self._read_section(kwargs.get("section_id", ""))
        elif action == "create":
            return await self._create_section(kwargs)
        elif action == "update":
            return await self._update_section(kwargs)
        elif action == "delete":
            return await self._delete_section(kwargs.get("section_id", ""))
        else:
            return ToolChunk(
                content=[
                    TextBlock(text=json.dumps({"error": f"Unknown action: {action}"}))
                ]
            )

    async def _list_sections(self, project_id: str) -> ToolChunk:
        async with _db_factory() as db:
            from sqlalchemy import select

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
            data = [
                {
                    "id": s.id,
                    "title": s.title,
                    "parent_id": s.parent_id,
                    "level": s.level,
                    "sort_order": s.sort_order,
                    "status": s.status,
                    "word_count": s.word_count,
                }
                for s in sections
            ]
            return ToolChunk(
                content=[TextBlock(text=json.dumps(data, ensure_ascii=False))]
            )

    async def _read_section(self, section_id: str) -> ToolChunk:
        async with _db_factory() as db:
            from sqlalchemy import select

            stmt = select(ChronicleSection).where(
                ChronicleSection.id == section_id,
                ChronicleSection.is_deleted.is_(False),
            )
            result = await db.execute(stmt)
            s = result.scalar_one_or_none()
            if not s:
                return ToolChunk(
                    content=[TextBlock(text=json.dumps({"error": "Section not found"}))]
                )
            data = {
                "id": s.id,
                "title": s.title,
                "content": s.content,
                "parent_id": s.parent_id,
                "level": s.level,
                "sort_order": s.sort_order,
                "status": s.status,
                "word_count": s.word_count,
            }
            return ToolChunk(
                content=[TextBlock(text=json.dumps(data, ensure_ascii=False))]
            )

    async def _create_section(self, kwargs: dict) -> ToolChunk:
        async with _db_factory() as db:
            section = ChronicleSection(
                project_id=kwargs.get("project_id", ""),
                parent_id=kwargs.get("parent_id"),
                title=kwargs.get("title", "未命名章节"),
                level=kwargs.get("level", 1),
                sort_order=kwargs.get("sort_order", 0),
                content=kwargs.get("content", ""),
                status="pending",
            )
            db.add(section)
            await db.flush()
            await db.refresh(section)
            return ToolChunk(
                content=[
                    TextBlock(
                        text=json.dumps(
                            {
                                "id": section.id,
                                "title": section.title,
                                "status": "created",
                            },
                            ensure_ascii=False,
                        )
                    )
                ]
            )

    async def _update_section(self, kwargs: dict) -> ToolChunk:
        section_id = kwargs.get("section_id", "")
        async with _db_factory() as db:
            from sqlalchemy import select

            stmt = select(ChronicleSection).where(
                ChronicleSection.id == section_id,
                ChronicleSection.is_deleted.is_(False),
            )
            result = await db.execute(stmt)
            s = result.scalar_one_or_none()
            if not s:
                return ToolChunk(
                    content=[TextBlock(text=json.dumps({"error": "Section not found"}))]
                )
            if "title" in kwargs:
                s.title = kwargs["title"]
            if "content" in kwargs:
                s.content = kwargs["content"]
                s.word_count = len(kwargs["content"])
            if "status" in kwargs:
                s.status = kwargs["status"]
            if "sort_order" in kwargs:
                s.sort_order = kwargs["sort_order"]
            await db.flush()
            return ToolChunk(
                content=[
                    TextBlock(
                        text=json.dumps(
                            {
                                "id": s.id,
                                "title": s.title,
                                "status": "updated",
                                "word_count": s.word_count,
                            },
                            ensure_ascii=False,
                        )
                    )
                ]
            )

    async def _delete_section(self, section_id: str) -> ToolChunk:
        async with _db_factory() as db:
            from sqlalchemy import select

            stmt = select(ChronicleSection).where(
                ChronicleSection.id == section_id,
                ChronicleSection.is_deleted.is_(False),
            )
            result = await db.execute(stmt)
            s = result.scalar_one_or_none()
            if not s:
                return ToolChunk(
                    content=[TextBlock(text=json.dumps({"error": "Section not found"}))]
                )
            s.is_deleted = True
            await db.flush()
            return ToolChunk(
                content=[
                    TextBlock(text=json.dumps({"id": section_id, "status": "deleted"}))
                ]
            )
