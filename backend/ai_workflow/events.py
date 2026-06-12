"""工作流事件推送工具

提供 SSE 事件推送函数和 SSE 格式化函数，供 WorkflowEngine、TeamExecutor
及各 API 路由模块共用。
"""

import asyncio
import json
from typing import Optional


async def push_event(
    queue: Optional[asyncio.Queue],
    event: str,
    data: dict,
) -> None:
    """向 SSE 流推送事件"""
    if queue is None:
        return
    await queue.put(
        {
            "event": event,
            "data": json.dumps(data, ensure_ascii=False),
        }
    )


def sse_encode(data: dict) -> str:
    """将 dict 编码为 SSE 格式 (data: <json>\\n\\n)"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
