import asyncio
import json
import os
import re
import time
import uuid

from openai import OpenAI, AsyncOpenAI
from openai import (
    APIError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
)
from loguru import logger
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.config import settings


_MAX_RETRIES = 3
_RETRY_DELAY = 1.0  # 初始延迟（秒），后续指数退避


async def _async_retry(coro_factory, retries=_MAX_RETRIES):
    """为异步 LLM 调用添加指数退避重试"""
    last_exc = None
    for attempt in range(retries):
        try:
            return await coro_factory()
        except (RateLimitError, APITimeoutError, InternalServerError, APIError) as e:
            last_exc = e
            if attempt < retries - 1:
                delay = _RETRY_DELAY * (2 ** attempt)
                logger.warning(f"LLM API 调用失败 (尝试 {attempt + 1}/{retries}): {e}，{delay}s 后重试")
                await asyncio.sleep(delay)
            else:
                logger.error(f"LLM API 调用在 {retries} 次重试后仍然失败: {e}")
                raise
        except Exception as e:
            logger.error(f"LLM API 非预期错误: {e}")
            raise


def _sync_retry(func, retries=_MAX_RETRIES):
    """为同步 LLM 调用添加指数退避重试"""
    last_exc = None
    for attempt in range(retries):
        try:
            return func()
        except (RateLimitError, APITimeoutError, InternalServerError, APIError) as e:
            last_exc = e
            if attempt < retries - 1:
                delay = _RETRY_DELAY * (2 ** attempt)
                logger.warning(f"LLM API 调用失败 (尝试 {attempt + 1}/{retries}): {e}，{delay}s 后重试")
                time.sleep(delay)
            else:
                logger.error(f"LLM API 调用在 {retries} 次重试后仍然失败: {e}")
                raise
        except Exception as e:
            logger.error(f"LLM API 非预期错误: {e}")
            raise


class LLMCompletionCallStream:
    def __init__(self):
        self.llm_model: str = settings.LLM_MODEL
        self.llm_base_url = settings.LLM_BASE_URL
        self.llm_api_key = settings.LLM_API_KEY
        if not self.llm_api_key:
            raise ValueError("LLM API key not provided")
        self.client = AsyncOpenAI(base_url=self.llm_base_url, api_key=self.llm_api_key)

    async def _stream_create(self, **kwargs):
        """带重试的流式创建"""
        async def _create():
            return await self.client.chat.completions.create(**kwargs)
        return await _async_retry(_create)

    async def call_api_stream(self, content: str):
        try:
            response = await self._stream_create(
                model=self.llm_model,
                messages=[{"role": "user", "content": content}],
                temperature=0.3,
                stream=True,
                extra_body={"thinking": {"type": "disabled"}}
            )
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"LLM streaming api calling failed. Error: {e}")
            raise e

    async def call_api_stream_messages(self, messages: list, temperature: float = 0.3):
        try:
            response = await self._stream_create(
                model=self.llm_model,
                messages=messages,
                temperature=temperature,
                stream=True,
                extra_body={"thinking": {"type": "disabled"}}
            )
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"LLM streaming api calling failed. Error: {e}")
            raise e


class LLMCompletionCall:
    def __init__(self):
        self.llm_model: str = settings.LLM_MODEL
        self.llm_base_url = settings.LLM_BASE_URL
        self.llm_api_key = settings.LLM_API_KEY
        if not self.llm_api_key:
            raise ValueError("LLM API key not provided")
        self.client = OpenAI(base_url=self.llm_base_url, api_key=self.llm_api_key)

    def call_api(self, content: str) -> str:
        def _call():
            return self.client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": content}],
                temperature=0.3,
                extra_body={"thinking": {"type": "disabled"}}
            )
        try:
            completion = _sync_retry(_call)
            raw = completion.choices[0].message.content or ""
            return self._clean_llm_content(raw)
        except Exception as e:
            logger.error(f"LLM api calling failed after retries. Error: {e}")
            raise e

    @staticmethod
    def _clean_llm_content(text: str) -> str:
        if not isinstance(text, str):
            return ""
        t = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        t = re.sub(r"[\u200B-\u200D\uFEFF]", "", t)
        fence_re = re.compile(
            r"^\s*```(?:\s*\w+)?\s*\n(?P<body>[\s\S]*?)\n\s*```\s*$", re.MULTILINE
        )
        m = fence_re.match(t)
        if m:
            t = m.group("body").strip()
        else:
            if t.startswith("```") and t.endswith("```") and len(t) >= 6:
                t = t[3:-3].strip()
        if t.lower().startswith("json\n"):
            t = t.split("\n", 1)[1].strip()
        return t


# ─── OpenAI 兼容的聊天补全 SSE 接口 ───

class ChatMessage(BaseModel):
    role: str = Field(..., description="消息角色: system/user/assistant")
    content: str = Field(..., description="消息内容")


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="", description="模型名称，为空则使用环境变量 LLM_MODEL")
    messages: list[ChatMessage] = Field(..., description="对话消息列表")
    temperature: float = Field(default=0.7, ge=0, le=2, description="采样温度")
    stream: bool = Field(default=True, description="是否流式返回")
    max_tokens: int | None = Field(default=None, description="最大生成 token 数")


router = APIRouter(prefix="/api/llm", tags=["LLM 对话"])


def _sse_openai(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post(
    "/v1/chat/completions",
    summary="OpenAI 兼容的流式聊天补全接口",
)
async def chat_completions(req: ChatCompletionRequest):
    model = req.model or os.getenv("LLM_MODEL", "deepseek-chat")
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    async def generate():
        yield _sse_openai({
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        })

        try:
            caller = LLMCompletionCallStream()
            full_content = ""
            async for chunk in caller.call_api_stream_messages(
                [m.model_dump() for m in req.messages],
                temperature=req.temperature,
            ):
                full_content += chunk
                yield _sse_openai({
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}],
                })
        except Exception as e:
            yield _sse_openai({
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            })
            yield _sse_openai({
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": f"\n\n[错误]: {e}"}, "finish_reason": None}],
            })

        yield _sse_openai({
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        })
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
