"""团队 Handoff / FinalAnswer 工具

两个特殊的工具（handoff / final_answer）供 LLM 在多角色团队中切换角色和结束任务。
它们被注入到每个角色的 ``Toolkit`` 中，采用标准 OpenAI function calling 格式。
"""

from agentscope.message import TextBlock
from agentscope.permission import (
    PermissionBehavior,
    PermissionContext,
    PermissionDecision,
)
from agentscope.tool import ToolBase, ToolChunk


class HandoffTool(ToolBase):
    """角色交接工具"""

    name = "handoff"
    description = "将任务交接给其他角色。调用此工具表示你已完成当前角色的工作。"
    input_schema = {
        "type": "object",
        "properties": {
            "target_role": {
                "type": "string",
                "description": "目标角色名称",
            },
            "context": {
                "type": "string",
                "description": "已完成工作的总结和需要继续完成的任务",
            },
        },
        "required": ["target_role", "context"],
    }
    is_concurrency_safe = True

    async def check_permissions(
        self,
        tool_input: dict,
        context: PermissionContext,
    ) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW)

    async def __call__(self, target_role: str, context: str) -> ToolChunk:
        return ToolChunk(
            content=[TextBlock(text=f"已交接给 {target_role}")],
        )


class FinalAnswerTool(ToolBase):
    """最终答案提交工具"""

    name = "final_answer"
    description = "提交最终答案，结束整个任务。所有角色工作完成后调用此工具。"
    input_schema = {
        "type": "object",
        "properties": {
            "result": {
                "type": "string",
                "description": "最终答案",
            },
        },
        "required": ["result"],
    }
    is_concurrency_safe = True

    async def check_permissions(
        self,
        tool_input: dict,
        context: PermissionContext,
    ) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW)

    async def __call__(self, result: str) -> ToolChunk:
        return ToolChunk(
            content=[TextBlock(text=result)],
        )
