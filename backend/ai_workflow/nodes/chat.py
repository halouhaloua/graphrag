from typing import Any, Dict

from openai import AsyncOpenAI

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import register_node


@register_node(
    "chat",
    metadata={
        "name": "LLM对话",
        "description": "调用大语言模型进行对话",
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
            "temperature": {"type": "float", "default": 0.7, "description": "温度参数"},
        },
        "output": {"result": "LLM响应文本"},
    },
)
class ChatNode(BaseNode):
    """LLM对话节点

    通过 ai-admin 的 LLM 配置调用大语言模型，
    支持 system_prompt 和 temperature 参数。
    """

    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        user_question = params.get("user_question", "")
        if not user_question:
            return {"result": "", "error": "user_question 不能为空"}

        temperature = float(params.get("temperature", 0.7))
        system_prompt = str(params.get("system_prompt", ""))

        settings = context.settings
        client = AsyncOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
        )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_question})

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
