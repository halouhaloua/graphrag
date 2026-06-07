"""提示词构建与答案生成

功能：
- 根据数据集类型构建不同风格的 LLM 提示词
- 支持同步与流式答案生成

数据流：
  build_prompt(config, dataset, question, sub_questions, context) → str
  generate_answer(llm_client, prompt) → str
  generate_answer_stream(llm_stream_client, prompt) → AsyncGenerator[str]  # SSE

提示词模板来源：
  1. 优先：config 中配置的 retrieval prompt（支持 general / novel_chs / novel_eng）
  2. fallback：硬编码默认模板（novel / novel_eng / general）
"""

from typing import Any, AsyncGenerator

from rag.utils import call_llm_api
from loguru import logger


def build_prompt(
    config: Any,
    dataset: str,
    question: str,
    sub_questions: list,
    context: str,
) -> str:
    """根据 dataset 类型选择对应的提示词模板

    优先使用 config 中配置的 prompt template，
    无 config 时使用硬编码默认模板（novel / novel_eng / general）。

    Args:
        config: 配置对象（含 get_prompt_formatted 方法）
        dataset (`str`): 数据集名称（决定模板类型）
        question (`str`): 用户原始问题
        sub_questions (`list`): GraphQ 分解后的子问题列表
        context (`str`): 检索到的知识上下文（含三元组、chunk、社区摘要）

    Returns:
        `str`: 完整的 LLM 提示词
    """
    if config is not None:
        if dataset == "novel":
            return config.get_prompt_formatted(
                "retrieval",
                "novel_chs",
                question=question,
                context=context,
            )
        elif dataset == "novel_eng":
            return config.get_prompt_formatted(
                "retrieval",
                "novel_eng",
                question=question,
                context=context,
            )
        else:
            return config.get_prompt_formatted(
                "retrieval",
                "general",
                question=question,
                context=context,
            )

    if dataset == "novel":
        return f"""
        你是小说知识助手，你的任务是根据提供的小说知识库回答问题。
        1. 如果知识库中的信息不足以回答问题，请根据你的推理和知识回答。
        2. 回答要简洁明了。
        3. 对于事实性问题，提供具体的事实或人物名称。
        4. 对于时间性问题，提供具体的时间、年份或时间段。
        问题：{question}
        相关知识：{context}
        答案（简洁明了）：
        """
    elif dataset == "novel_eng":
        return f"""
        You are a novel knowledge assistant. Your task is to answer the question based on the provided novel knowledge context.
        1. If the knowledge is insufficient, answer the question based on your own knowledge.
        2. Be precise and concise in your answer.
        3. For factual questions, provide the specific fact or entity name
        4. For temporal questions, provide the specific date, year, or time period

        Question: {question}

        The question is broken down into sub-question to help thinking:{sub_questions}

        Knowledge Context:
        {context}

        Answer (be specific and direct):
        """
    else:
        return f"""
        You are an expert knowledge assistant. Your task is to answer the question based on the provided knowledge context.

        1. Use ONLY the information from the provided knowledge context and try your best to answer the question.
        2. If the knowledge is insufficient, reject to answer the question.
        3. Be precise and concise in your answer
        4. For factual questions, provide the specific fact or entity name
        5. For temporal questions, provide the specific date, year, or time period

        The question is broken down into sub-question to help thinking:{sub_questions}

        Question: {question}

        Knowledge Context:
        {context}

        Answer (be specific and direct):
        """


def generate_answer(llm_client: call_llm_api.LLMCompletionCall, prompt: str) -> str:
    """同步生成答案

    Args:
        llm_client (`LLMCompletionCall`): LLM 同步调用客户端
        prompt (`str`): 完整提示词（由 build_prompt 生成）

    Returns:
        `str`: LLM 生成的答案文本
    """
    answer = llm_client.call_api(prompt)
    logger.info(f"Answer: {answer}")
    return answer


async def generate_answer_stream(
    llm_stream_client: call_llm_api.LLMCompletionCallStream,
    prompt: str,
) -> AsyncGenerator[str, None]:
    """流式生成答案（用于 SSE 场景）

    每次 yield 一个 token，调用方接收后通过 SSE 推送给前端。

    Args:
        llm_stream_client (`LLMCompletionCallStream`): LLM 流式调用客户端
        prompt (`str`): 完整提示词

    Yields:
        `str`: 单个 token 文本
    """
    async for token in llm_stream_client.call_api_stream(prompt):
        yield token
