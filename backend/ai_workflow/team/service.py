"""多智能体团队执行器

基于 AgentScope Toolkit 管理工具（标准 OpenAI function calling 格式），
替代了旧的 XML 解析方式。团队间的 handoff / final_answer 仍由应用层控制。
"""

import asyncio
import json
import logging
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from ai_workflow.workflow.events import WorkflowEventType
from ai_workflow.nodes.registry import NodeRegistry
from ai_workflow.team.model import TeamConfig
from ai_workflow.team.tool_adapter import NodeToolAdapter
from ai_workflow.team.team_tools import HandoffTool, FinalAnswerTool
from app.config import settings

logger = logging.getLogger(__name__)

MAX_TEAM_STEPS = 100
DEFAULT_MAX_ITER = 25


class TeamExecutor:
    """多智能体团队执行器

    按团队配置（TeamConfig），以 LLM 驱动各角色顺序执行任务：
    起始角色 → LLM 推理 → 工具调用/文本回复 → handoff/final_answer → 下一角色/结束

    工具采用标准 OpenAI function calling 格式（通过 AgentScope Toolkit），
    不再使用 XML 解析。
    """

    @staticmethod
    async def execute_team(
        config: TeamConfig,
        input_params: Optional[dict],
        db: AsyncSession,
        stream_queue: Optional[asyncio.Queue] = None,
    ) -> dict:
        """执行团队任务

        Args:
            config: 团队配置对象
            input_params: 用户输入的参数（支持 ``input`` 键）
            db: 数据库会话
            stream_queue: SSE 事件推送队列

        Returns:
            dict: ``{"success": bool, "result": str, "steps": int}``
        """
        roles: dict = json.loads(config.roles)
        start_role = config.start_role
        if start_role not in roles:
            raise ValueError(f"起始角色 {start_role} 不存在于角色定义中")

        await TeamExecutor._push_event(
            stream_queue,
            WorkflowEventType.TEAM_START,
            {
                "team_name": config.name,
                "start_role": start_role,
                "roles": list(roles.keys()),
            },
        )

        current_role = start_role
        context_summary = (input_params or {}).get("input", "")
        step = 0

        while step < MAX_TEAM_STEPS:
            step += 1
            role_def = roles[current_role]

            await TeamExecutor._push_event(
                stream_queue,
                WorkflowEventType.TEAM_ROLE_START,
                {"role": current_role, "step": step},
            )

            result_text, action = await TeamExecutor._run_role(
                role_name=current_role,
                role_def=role_def,
                context_summary=context_summary,
                stream_queue=stream_queue,
                team_rules=config.team_rules,
                db=db,
            )

            action_type = action.get("type", "")

            if action_type == "handoff":
                target_role = action.get("target_role", "")
                handoff_context = action.get("context", "")
                context_summary = f"[{current_role} 完成]\n{handoff_context}"
                await TeamExecutor._push_event(
                    stream_queue,
                    WorkflowEventType.TEAM_HANDOFF,
                    {"from_role": current_role, "to_role": target_role},
                )
                current_role = target_role if target_role in roles else start_role
                continue

            elif action_type == "final_answer":
                final_result = action.get("result", result_text)
                await TeamExecutor._push_event(
                    stream_queue,
                    WorkflowEventType.TEAM_ROLE_COMPLETE,
                    {"role": current_role, "action": "final_answer"},
                )
                result = {"success": True, "result": final_result, "steps": step}
                await TeamExecutor._push_event(
                    stream_queue,
                    WorkflowEventType.WORKFLOW_COMPLETE,
                    {"result": final_result, "steps": step},
                )
                return result

            # 未知或超时 → 继续下一角色

        final = {"success": True, "result": "", "steps": step}
        await TeamExecutor._push_event(
            stream_queue,
            WorkflowEventType.WORKFLOW_COMPLETE,
            {"result": "", "steps": step},
        )
        return final

    @staticmethod
    async def _run_role(
        role_name: str,
        role_def: dict,
        context_summary: str,
        stream_queue: Optional[asyncio.Queue] = None,
        team_rules: str = "",
        db: Optional[AsyncSession] = None,
    ) -> tuple[str, dict]:
        """运行单个角色直至其调用 handoff 或 final_answer

        使用 AgentScope Toolkit 管理工具，LLM 调用通过标准 OpenAI function calling 完成。

        Returns:
            tuple: (角色累积文本, 动作字典)
        """
        tool_names: list[str] = role_def.get("tools", [])
        max_iter = int(role_def.get("max_iterations", DEFAULT_MAX_ITER))
        model_name = role_def.get("model_name", settings.LLM_MODEL)
        agent_desc = role_def.get("agent_description", "")

        # 构建 Toolkit（仅注册真实节点工具，handoff/final_answer 在循环中检测）
        unresolved_tools = [
            t
            for t in tool_names
            if t not in ("handoff", "final_answer") and not NodeRegistry.get(t)
        ]
        for t in unresolved_tools:
            logger.warning("角色 %s 的工具 '%s' 未注册，已忽略", role_name, t)
        toolkit_tools: list = [
            NodeToolAdapter(t, settings, db=db, stream_queue=stream_queue, log=logger)
            for t in tool_names
            if t not in ("handoff", "final_answer") and NodeRegistry.get(t)
        ]
        # handoff / final_answer 也通过 OpenAI tools 格式暴露
        toolkit_tools += [HandoffTool(), FinalAnswerTool()]

        # 构建 system prompt
        system_parts = [
            team_rules,
            f"\n\n## 你的角色\n{agent_desc}",
            "\n\n## 工作方式\n使用可用工具完成你的任务。",
            "\n当你完成当前角色的工作后，调用 **handoff** 工具将任务交接给下一个角色。",
            "\n当所有工作完成时，调用 **final_answer** 工具提交最终答案。",
            "\n\n### 重要规则\n1. 提供完整准确的参数。",
            "\n2. handoff 时必须在 context 中总结已完成的工作和剩余任务。",
            "\n3. 当本角色的任务全部完成后，使用 handoff 或 final_answer。",
        ]
        system_prompt = "".join(system_parts)

        client = AsyncOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
        )

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        if context_summary:
            messages.append({"role": "user", "content": context_summary})

        full_text = ""
        action: dict = {}
        _MAX_TEXT_LENGTH = 50000

        for _ in range(max_iter):
            try:
                # 构建 tools 参数
                tools_param = [
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.input_schema,
                        },
                    }
                    for tool in toolkit_tools
                ]

                completion = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    tools=tools_param if tools_param else None,
                    temperature=0.3,
                    parallel_tool_calls=False,
                )
            except Exception as e:
                logger.error("角色 %s LLM 调用失败: %s", role_name, e)
                return full_text, {"type": "error", "message": str(e)}

            choice = completion.choices[0]
            text = choice.message.content or ""
            if len(full_text) + len(text) > _MAX_TEXT_LENGTH:
                logger.warning(
                    "角色 %s 输出超过 %d 字符限制，已截断", role_name, _MAX_TEXT_LENGTH
                )
                full_text += text[: _MAX_TEXT_LENGTH - len(full_text)]
            else:
                full_text += text

            # 检查 tool_calls
            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}

                    if name == "handoff":
                        action = {"type": "handoff", **args}
                        break
                    if name == "final_answer":
                        action = {
                            "type": "final_answer",
                            "result": args.get("result", ""),
                        }
                        break

                if action:
                    break  # handoff/final_answer → 跳出角色循环

                # 回注工具结果
                messages.append(choice.message.model_dump(exclude_none=True))
                for tc in choice.message.tool_calls:
                    tool = next(
                        (t for t in toolkit_tools if t.name == tc.function.name), None
                    )
                    if tool:
                        try:
                            args = json.loads(tc.function.arguments)
                            chunk = await tool(**args)
                            tool_text = chunk.content[0].text if chunk.content else ""
                        except Exception as e:
                            tool_text = json.dumps(
                                {"error": str(e)}, ensure_ascii=False
                            )
                    else:
                        tool_text = json.dumps(
                            {"error": f"未知工具 {tc.function.name}"},
                            ensure_ascii=False,
                        )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": tool_text,
                        }
                    )
                continue

            # 达到 max_tokens → 记录警告
            if choice.finish_reason == "length":
                logger.warning(
                    "角色 %s 达到 max_tokens 限制（iter %d），响应可能被截断",
                    role_name, _,
                )

            # 无工具调用 → 文本响应，提示继续
            messages.append({"role": "assistant", "content": text or ""})
            messages.append(
                {
                    "role": "user",
                    "content": "请继续你的任务。如果需要其他角色协助，使用 handoff 工具；如果任务完成，使用 final_answer 工具。",
                }
            )

        # 达到最大迭代次数仍无 handoff/final_answer → 返回已有文本作为最终答案
        logger.warning("角色 %s 达到最大迭代次数 %d，返回已有文本", role_name, max_iter)
        return full_text, action if action else {
            "type": "final_answer",
            "result": full_text,
        }

    @staticmethod
    async def _push_event(
        queue: Optional[asyncio.Queue],
        event: str,
        data: dict,
    ) -> None:
        from ai_workflow.events import push_event

        await push_event(queue, event, data)
