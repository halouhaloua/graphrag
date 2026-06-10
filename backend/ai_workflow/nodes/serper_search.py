import asyncio
import json
import logging
import os
import time
from typing import Any, Dict

import aiohttp

from ai_workflow.nodes.base import BaseNode, NodeContext
from ai_workflow.nodes.registry import register_node
from utils.redis import RedisClient

logger = logging.getLogger(__name__)


class AsyncRateLimiter:
    """异步请求限速器，漏斗桶算法"""

    def __init__(self, max_requests_per_minute: int):
        self.rate = max_requests_per_minute / 60.0
        self.capacity = max_requests_per_minute
        self.water = 0
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.time()
            leaked = (now - self.last_update) * self.rate
            self.water = max(0, self.water - leaked)
            self.last_update = now
            if self.water >= self.capacity:
                wait = (self.water - self.capacity + 1) / self.rate
                await asyncio.sleep(wait)
                self.water = max(0, self.water - self.rate * wait)
            self.water += 1


@register_node(
    "serper_search",
    metadata={
        "name": "Serper搜索引擎",
        "description": "通过Serper API搜索最新信息（新闻、论坛、博客等）",
        "params": {
            "query": {"type": "str", "required": True, "description": "搜索关键词"},
            "country": {"type": "str", "default": "cn", "description": "国家代码"},
            "language": {"type": "str", "default": "zh", "description": "语言代码"},
            "max_results": {"type": "int", "default": 10, "description": "最大结果数"},
        },
        "output": {"results": "搜索结果列表", "count": "数量", "success": "是否成功"},
    },
)
class SerperSearchNode(BaseNode):
    """Serper搜索引擎节点"""

    _rate_limiter = AsyncRateLimiter(max_requests_per_minute=5)

    async def execute(
        self, params: Dict[str, Any], context: NodeContext
    ) -> Dict[str, Any]:
        query = str(params.get("query", ""))
        if not query:
            raise ValueError("query参数不能为空")

        api_key = os.getenv("SERPER_SEARCH_API_KEY", "")
        if not api_key:
            raise ValueError("未设置SERPER_SEARCH_API_KEY环境变量")

        country = str(params.get("country", "cn"))
        language = str(params.get("language", "zh"))
        max_results = int(params.get("max_results", 10))

        cache_key = f"serper:{query.lower()}:{country}:{language}:{max_results}"

        redis_client = await RedisClient.get_client()
        cached = await redis_client.get(cache_key)
        if cached:
            try:
                cached_data = json.loads(cached)
                return {
                    "success": True,
                    "results": cached_data,
                    "count": len(cached_data),
                }
            except json.JSONDecodeError:
                pass

        await self._rate_limiter.acquire()

        try:
            headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
            payload = {"q": query, "gl": country, "hl": language, "num": max_results}

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://google.serper.dev/search", headers=headers, json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "error": f"API请求失败: {error_text}",
                            "results": [],
                            "count": 0,
                        }

                    data = await response.json()

            results = []
            answer_box = data.get("answerBox")
            if answer_box:
                results.append(
                    {
                        "title": answer_box.get("title", ""),
                        "link": "",
                        "snippet": answer_box.get("answer", ""),
                        "is_answer_box": True,
                    }
                )

            for item in data.get("organic", []):
                results.append(
                    {
                        "title": item.get("title", ""),
                        "link": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                    }
                )

            if results:
                ttl = int(os.getenv("SERPER_CACHE_TTL", "600"))
                await redis_client.set(
                    cache_key, json.dumps(results, ensure_ascii=False), ex=ttl
                )

            return {"success": True, "results": results, "count": len(results)}

        except Exception as e:
            logger.error(f"Serper搜索失败: {e}")
            return {"success": False, "error": str(e), "results": [], "count": 0}
