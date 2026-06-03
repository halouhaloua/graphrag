from agentscope.tool import FunctionTool

from chronicle_writer.tools.reference_tool import _db_factory


async def query_file_content(file_id: str, query: str = "") -> str:
    """查询知识库中指定文件的内容。

    Args:
        file_id: 文件ID
        query: （可选）搜索关键词，返回匹配段落

    Returns:
        文件内容或匹配段落
    """
    try:
        from sqlalchemy import select
        from rag.kb_manager.model import KnowledgeBaseFile

        async with _db_factory() as db:
            stmt = select(KnowledgeBaseFile).where(
                KnowledgeBaseFile.id == file_id,
                KnowledgeBaseFile.is_deleted.is_(False),
            )
            result = await db.execute(stmt)
            f = result.scalar_one_or_none()
            if not f:
                return f"文件 {file_id} 不存在"
            content = f.content or ""
            if query and content:
                lines = content.split("\n")
                matched = [line for line in lines if query.lower() in line.lower()]
                if matched:
                    return "\n".join(matched[:10])
            return content[:5000] if content else "文件无文本内容"
    except ImportError:
        return "文件查询模块不可用"
    except Exception as e:
        return f"查询失败: {e}"


file_query_tool = FunctionTool(
    func=query_file_content,
    name="FileQuery",
    description="查询知识库中指定文件的内容，可按关键词过滤",
    is_read_only=True,
)
