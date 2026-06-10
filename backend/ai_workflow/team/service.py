import asyncio
import json
import logging
import re
from typing import Any, Optional

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from ai_workflow.api.events import WorkflowEventType
from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import NodeRegistry
from ai_workflow.team.model import TeamConfig
from ai_workflow.team.prompts import ROLE_SYSTEM_PROMPT, TOOL_DESCRIPTIONS

logger = logging.getLogger(__name__)

_HANDOFF_PATTERN = re.compile(
    r"<handoff>.*?<target_role>(.*?)</target_role>.*?<context>(.*?)</context>.*?</handoff>",
    re.DOTALL,
)
_FINAL_ANSWER_PATTERN = re.compile(
    r"<final_answer>.*?<result>(.*?)</result>.*?</final_answer>",
    re.DOTALL,
)
_TOOL_CALL_PATTERN = re.compile(
    r"<action>.*?<(\w+)>(.*?)</\1>.*?</action>",
    re.DOTALL,
)

MAX_TEAM_STEPS = 100


class TeamExecutor:
    """多智能体团队执行器

    按 YAML 定义的团队配置，以 LLM 驱动各角色顺序执行任务：
    起始角色 → LLM 推理 → 工具调用 / handoff → 下一角色 → ... → final_answer
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
            input_params: 用户输入的参数
            db: 数据库会话
            stream_queue: SSE 事件推送队列

        Returns:
            dict: 团队执行结果
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

        settings_module = __import__("app.config", fromlist=["settings"])
        settings = settings_module.settings

        current_role = start_role
        context_summary = input_params.get("input", "") if input_params else ""
        role_histories: dict[str, list[dict]] = {name: [] for name in roles}
        final_result = ""
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
                settings=settings,
                stream_queue=stream_queue,
                team_rules=config.team_rules,
            )

            role_histories[current_role].append(result_text)
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
                break

            elif action_type in roles:
                context_summary = (
                    f"[{current_role} 执行工具]\n{action.get('tool_result', '')}"
                )
                current_role = action_type
                continue

            else:
                # 未知 action，继续当前角色
                continue

        result = {"success": True, "result": final_result, "steps": step}
        await TeamExecutor._push_event(
            stream_queue,
            WorkflowEventType.WORKFLOW_COMPLETE,
            {"result": final_result, "steps": step},
        )
        return result

    @staticmethod
    async def _run_role(
        role_name: str,
        role_def: dict,
        context_summary: str,
        settings: Any,
        stream_queue: Optional[asyncio.Queue] = None,
        team_rules: str = "",
    ) -> tuple[str, dict]:
        """运行单个角色直至其调用 handoff 或 final_answer

        Returns:
            tuple: (完整响应文本, 解析出的动作字典)
        """
        tools = role_def.get("tools", [])
        max_iter = int(role_def.get("max_iterations", 25))
        model_name = role_def.get("model_name", settings.LLM_MODEL)
        agent_desc = role_def.get("agent_description", "")

        tool_descs = "\n".join(
            f"- {t}: {TOOL_DESCRIPTIONS.get(t, '无描述')}"
            for t in tools
            if t in TOOL_DESCRIPTIONS
        )
        system_prompt = ROLE_SYSTEM_PROMPT.format(
            team_rules=team_rules,
            agent_description=agent_desc,
            tools_description=tool_descs,
        )

        client = AsyncOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
        )

        messages = [{"role": "system", "content": system_prompt}]
        if context_summary:
            messages.append({"role": "user", "content": context_summary})

        full_text = ""
        for _ in range(max_iter):
            try:
                completion = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=0.3,
                )
                text = completion.choices[0].message.content or ""
            except Exception as e:
                logger.error(f"角色 {role_name} LLM 调用失败: {e}")
                return full_text, {"type": "error", "message": str(e)}

            full_text += text

            action = TeamExecutor._parse_action(text, tools)

            if action["type"] in ("handoff", "final_answer"):
                return full_text, action

            if action["type"] == "tool_call":
                tool_result = await TeamExecutor._execute_node_tool(
                    action["tool_name"],
                    action["tool_args"],
                    settings,
                )
                tool_msg = f"工具 {action['tool_name']} 执行结果:\n{tool_result}"
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": tool_msg})

            elif action["type"] in tools:
                return full_text, action

            else:
                messages.append({"role": "assistant", "content": text})
                messages.append(
                    {
                        "role": "user",
                        "content": "请继续你的任务，使用合适的工具或 handoff/final_answer",
                    }
                )

        return full_text, {"type": "final_answer", "result": full_text}

    @staticmethod
    def _parse_action(text: str, available_tools: list[str]) -> dict:
        """从 LLM 响应中解析动作"""
        handoff_match = _HANDOFF_PATTERN.search(text)
        if handoff_match:
            return {
                "type": "handoff",
                "target_role": handoff_match.group(1).strip(),
                "context": handoff_match.group(2).strip(),
            }

        final_match = _FINAL_ANSWER_PATTERN.search(text)
        if final_match:
            return {"type": "final_answer", "result": final_match.group(1).strip()}

        tool_match = _TOOL_CALL_PATTERN.search(text)
        if tool_match:
            tool_name = tool_match.group(1)
            raw_args = tool_match.group(2).strip()
            args_dict = TeamExecutor._parse_xml_args(raw_args)

            if tool_name in available_tools:
                return {
                    "type": "tool_call",
                    "tool_name": tool_name,
                    "tool_args": args_dict,
                }

            if tool_name in ("handoff", "final_answer"):
                return {"type": tool_name, **args_dict}

        return {"type": "unknown"}

    @staticmethod
    def _parse_xml_args(xml_text: str) -> dict:
        """解析 XML 格式的参数为字典"""
        args = {}
        pattern = re.compile(r"<(\w+)>(.*?)</\1>", re.DOTALL)
        for match in pattern.finditer(xml_text):
            key = match.group(1)
            value = match.group(2).strip()
            args[key] = value
        return args

    @staticmethod
    async def _execute_node_tool(
        tool_name: str,
        tool_args: dict,
        settings: Any,
    ) -> str:
        """通过 NodeRegistry 执行工具节点"""
        node_cls = NodeRegistry.get(tool_name)
        if not node_cls:
            return f"错误: 未知工具 {tool_name}"

        try:
            node: BaseNode = node_cls()
            context = NodeContext(
                db=None,
                settings=settings,
                logger=logger,
                node_id=tool_name,
                instance_id="",
            )
            result = await node.execute(tool_args, context)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            logger.error(f"工具 {tool_name} 执行失败: {e}")
            return f"错误: {e}"

    @staticmethod
    async def _push_event(
        queue: Optional[asyncio.Queue],
        event: str,
        data: dict,
    ):
        if queue is None:
            return
        await queue.put(
            {
                "event": event,
                "data": json.dumps(data, ensure_ascii=False),
            }
        )
