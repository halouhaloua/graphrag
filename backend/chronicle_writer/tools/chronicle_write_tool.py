"""ChronicleWriteTool — 外部执行的志书写作工具"""

from agentscope.tool import ToolBase
from agentscope.permission import (
    PermissionContext,
    PermissionDecision,
    PermissionBehavior,
)


class ChronicleWriteTool(ToolBase):
    """志书写作工具 — 自动完成资料检索、大纲生成、正文撰写、审校全流程

    设置为 is_external_tool=True，执行委派给外部（service 层），
    不阻塞主智能体的 ReAct 循环。
    """

    name = "ChronicleWrite"
    description = (
        "志书写作工具。自动完成资料检索、大纲生成、正文撰写、审校全流程。"
        "调用前请确保已通过对话收集齐 title、topic、chronicle_type、"
        "region_name、scope_description 五项信息。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "志书标题",
            },
            "topic": {
                "type": "string",
                "description": "主题/写作重点，如经济变迁、文化发展",
            },
            "chronicle_type": {
                "type": "string",
                "enum": ["town", "county", "special"],
                "description": "志书类型",
            },
            "region_name": {
                "type": "string",
                "description": "地区名称",
            },
            "scope_description": {
                "type": "string",
                "description": "断限说明",
            },
        },
        "required": ["title", "chronicle_type"],
    }
    is_concurrency_safe = False
    is_external_tool = True

    async def check_permissions(
        self,
        tool_input: dict,
        context: PermissionContext,
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Chronicle writing is allowed.",
        )
