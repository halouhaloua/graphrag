"""LLM 对话节点，支持工具调用（ReAct 循环）

当配置了 ``tools`` 参数时，ChatNode 将运行 ReAct 循环：
LLM 推理 → 工具调用 → 结果回注 → 继续，直到 LLM 输出最终答案或达到轮数上限。
工具通过 ``NodeToolAdapter`` 适配，复用 ``@register_node`` 注册的节点。
当 ``tools`` 为空时保持原有单次 LLM 调用逻辑，完全向后兼容。
"""

import json
import logging
from typing import Any, Dict

from openai import AsyncOpenAI

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import register_node, NodeRegistry
from ai_workflow.team.tool_adapter import NodeToolAdapter

logger = logging.getLogger(__name__)


@register_node(
    "chat",
    metadata={
        "name": "LLM对话",
        "description": "调用大语言模型进行对话，支持工具调用",
        "params": {
            "user_question": {
                "type": "str",
                "required": True,
                "description": "用户问题",
            },
            "system_prompt": {
                "type": "str",
                "default": "",
                "description": "系统提示词",
            },
            "temperature": {
                "type": "float",
                "default": 0.7,
                "description": "温度参数",
            },
            "tools": {
                "type": "list",
                "default": [],
                "description": "可用工具列表（节点类型标识符，如 serper_search, web_crawler）",
            },
            "max_tool_rounds": {
                "type": "int",
                "default": 10,
                "description": "最大工具调用轮数",
            },
        },
        "output": {"result": "LLM响应文本"},
    },
)
class ChatNode(BaseNode):
    """LLM对话节点

    通过 ai-admin 的 LLM 配置调用大语言模型。
    当 ``tools`` 参数非空时，运行 ReAct 循环（LLM → 工具 → LLM → ... → 最终答案）。
    当 ``tools`` 为空时，走原始单次调用路径。
    """

    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        user_question = params.get("user_question", "")
        if not user_question:
            return {"result": "", "error": "user_question 不能为空"}

        temperature = float(params.get("temperature", 0.7))
        system_prompt = str(params.get("system_prompt", ""))
        tool_names: list[str] = params.get("tools", []) or []
        max_rounds = int(params.get("max_tool_rounds", 10))

        settings = context.settings
        client = AsyncOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
        )

        # 构建消息
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_question})

        # 无工具路径 — 原始单次调用
        if not tool_names:
            try:
                completion = await client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=messages,
                    temperature=temperature,
                )
                text = completion.choices[0].message.content or ""
                return {"result": text}
            except Exception as e:
                return {"result": "", "error": f"LLM 调用失败: {e}"}

        # 有工具路径 — ReAct 循环
        adapters = [
            NodeToolAdapter(t, settings, logger)
            for t in tool_names
            if t != "chat" and NodeRegistry.get(t)
        ]
        unresolved = [t for t in tool_names if t not in ("chat",) and not NodeRegistry.get(t)]
        for t in unresolved:
            logger.warning("ChatNode 工具 '%s' 未注册，已忽略", t)

        # 构造 OpenAI tools 参数
        tools_param = [
            {
                "type": "function",
                "function": {
                    "name": a.name,
                    "description": a.description,
                    "parameters": a.input_schema,
                },
            }
            for a in adapters
        ]

        full_text = ""
        for _ in range(max_rounds):
            try:
                completion = await client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=messages,
                    tools=tools_param if tools_param else None,
                    temperature=temperature,
                    parallel_tool_calls=False,
                )
            except Exception as e:
                logger.error("ChatNode LLM 调用失败: %s", e)
                return {"result": full_text, "error": f"LLM 调用失败: {e}"}

            choice = completion.choices[0]
            text = choice.message.content or ""
            full_text += text

            # LLM 自行决定结束 → 返回最终答案
            if choice.finish_reason == "stop":
                return {"result": full_text}

            # 工具调用 → 执行并回注
            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                messages.append(choice.message.model_dump(exclude_none=True))
                for tc in choice.message.tool_calls:
                    adapter = next(
                        (a for a in adapters if a.name == tc.function.name), None
                    )
                    if not adapter:
                        tool_text = json.dumps(
                            {"error": f"未知工具 {tc.function.name}"},
                            ensure_ascii=False,
                        )
                    else:
                        try:
                            args = json.loads(tc.function.arguments)
                            chunk = await adapter(**args)
                            tool_text = chunk.content[0].text if chunk.content else ""
                        except Exception as e:
                            tool_text = json.dumps(
                                {"error": str(e)}, ensure_ascii=False
                            )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_text,
                    })
                continue

            # 其他情况（如 length）→ 继续
            messages.append({"role": "assistant", "content": text or ""})

        return {"result": full_text}
